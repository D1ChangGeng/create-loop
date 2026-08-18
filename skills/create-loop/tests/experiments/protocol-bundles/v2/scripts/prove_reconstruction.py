#!/usr/bin/env python3
"""Measure whether derived artifact fields can be rebuilt from the event log.

This is a read-only measurement instrument, not a gate. It always exits zero,
including for missing/malformed input and reconstruction disagreements.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterable

import yaml

HERE = Path(__file__).resolve().parent
SCHEMAS = HERE.parent / "schemas"
ARTIFACTS = {
    "artifacts/INDEX.yaml": "artifact.index.schema.json",
    "checkpoint.yaml": "checkpoint.schema.json",
    "loop.state.yaml": "loop.state.schema.json",
    "node.contract.yaml": "node.contract.schema.json",
}
VERDICTS = ("RECONSTRUCTIBLE", "NOT-RECONSTRUCTIBLE", "NO-EVENT-SOURCE", "PLAN-SOURCED",
            "FIELD-ABSENT-ON-DISK")
CLAIMS = {
    ("checkpoint.yaml", "cost_units_spent"),
    ("checkpoint.yaml", "iteration"),
    ("checkpoint.yaml", "node_states"),
    ("node.contract.yaml", "attempt"),
}
MISSING = object()


class InstrumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def schema_fields(schema_name: str) -> list[str]:
    schema = json.loads((SCHEMAS / schema_name).read_text(encoding="utf-8"))
    fields: list[str] = []

    def walk(properties: dict[str, Any], prefix: str = "") -> None:
        for name, definition in properties.items():
            field = f"{prefix}.{name}" if prefix else name
            fields.append(field)
            target = definition
            if "$ref" in target:
                target = schema["$defs"][target["$ref"].rsplit("/", 1)[-1]]
            if isinstance(target.get("properties"), dict):
                walk(target["properties"], field)
            items = target.get("items", {})
            if "$ref" in items:
                items = schema["$defs"][items["$ref"].rsplit("/", 1)[-1]]
            if isinstance(items.get("properties"), dict):
                walk(items["properties"], field + "[]")

    walk(schema["properties"])
    return sorted(fields)


def find_contracts(loop_dir: Path) -> list[Path]:
    candidates = [loop_dir / "node.contract.yaml"]
    candidates.extend(sorted((loop_dir / "contracts").glob("*.yaml")))
    candidates.extend(sorted((loop_dir / "nodes").glob("*/node.contract.yaml")))
    return sorted({path for path in candidates if path.is_file()})


def find_artifact(loop_dir: Path, artifact: str) -> list[Path]:
    if artifact == "node.contract.yaml":
        return find_contracts(loop_dir)
    path = loop_dir / artifact
    return [path] if path.is_file() else []


def find_event_log(loop_dir: Path) -> Path | None:
    checkpoint = loop_dir / "checkpoint.yaml"
    if checkpoint.is_file():
        data = load_yaml(checkpoint) or {}
        ref = data.get("event_log_ref") if isinstance(data, dict) else None
        if isinstance(ref, str) and (loop_dir / ref).is_file():
            return loop_dir / ref
    for relative in ("state/event_log.jsonl", "event_log.jsonl", "events.jsonl", "event_log.yaml"):
        path = loop_dir / relative
        if path.is_file():
            return path
    return None


def load_events(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    if path.suffix == ".jsonl":
        values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        document = load_yaml(path) or {}
        values = document.get("entries", []) if isinstance(document, dict) else []
    return sorted((value for value in values if isinstance(value, dict)), key=lambda value: value.get("seq", -1))


def project(value: Any, field: str) -> Any:
    current = value
    for part in field.split("."):
        is_list = part.endswith("[]")
        key = part[:-2] if is_list else part
        if isinstance(current, list):
            current = [item.get(key, MISSING) if isinstance(item, dict) else MISSING for item in current]
        elif isinstance(current, dict):
            current = current.get(key, MISSING)
        else:
            return MISSING
        if is_list and not isinstance(current, list):
            return MISSING
    return current


def replay(events: list[dict[str, Any]], plan: Any = None,
           ledger: Any = None) -> dict[str, Any]:
    """Rebuild the canonical projection: plan seed, then log, then ledger.

    Mirrors state_model.md "The canonical checkpoint projection". The log alone
    can never yield `completed` — that step reads the evidence ledger, so an
    instrument replaying only events measures a projection the protocol does
    not define.
    """
    states: dict[str, Any] = {}
    attempts: Counter[str] = Counter()
    started: dict[str, Any] = {}
    finished: dict[str, Any] = {}
    last_completed: list[str] = []
    if isinstance(plan, dict):
        for node in plan.get("nodes", []):
            if isinstance(node, dict) and isinstance(node.get("id"), str):
                states[node["id"]] = node.get("status", "pending")
    for event in events:
        node = event.get("node_id")
        if not isinstance(node, str):
            continue
        if event.get("kind") == "pre_effect":
            attempts[node] += 1
            started[node] = event.get("ts")
            finished[node] = None
        elif event.get("kind") == "post_effect":
            finished[node] = event.get("ts")
        if event.get("to_status") is not None:
            states[node] = event["to_status"]
    for node, verdict in ledger_outcomes(ledger).items():
        if states.get(node) == "verifying":
            states[node] = verdict
            if verdict == "completed":
                last_completed.append(node)
    phases = [event["phase"] for event in events if isinstance(event.get("phase"), int)]
    timestamps = [event["ts"] for event in events if isinstance(event.get("ts"), str)]
    return {
        "states": states,
        "attempts": dict(attempts),
        "started": started,
        "finished": finished,
        "last_completed": last_completed[-1:],
        "phase": phases[-1] if phases else MISSING,
        "updated_at": timestamps[-1] if timestamps else MISSING,
    }


def ledger_outcomes(ledger: Any) -> dict[str, str]:
    """Map node_id to the status its latest active entry authorizes."""
    if not isinstance(ledger, dict):
        return {}
    outcomes: dict[str, str] = {}
    entries = [e for e in ledger.get("entries", []) if isinstance(e, dict)]
    entries.sort(key=lambda e: str(e.get("recorded", "")))
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        node = entry.get("node_id")
        if not isinstance(node, str) or entry.get("status") not in (None, "active"):
            continue
        if entry.get("verdict") == "pass":
            authorized = (entry.get("assurance") == "external"
                          or entry.get("gate_kind") == "human_approval")
            outcomes[node] = "completed" if authorized else "verifying"
        elif entry.get("verdict") in ("fail", "inconclusive"):
            outcomes[node] = "verification_failed"
    return outcomes


def reconstruction(artifact: str, field: str, state: dict[str, Any], actual: Any) -> tuple[str, Any, str]:
    root = field.split(".", 1)[0]
    direct: dict[tuple[str, str], Callable[[], Any]] = {
        ("checkpoint.yaml", "node_states"): lambda: state["states"],
        ("checkpoint.yaml", "phase"): lambda: state["phase"],
        ("checkpoint.yaml", "ready_set"): lambda: sorted(node for node, status in state["states"].items() if status == "ready"),
        ("checkpoint.yaml", "last_completed"): lambda: state["last_completed"],
        ("loop.state.yaml", "active_node"): lambda: next(
            (node for node, status in state["states"].items()
             if status == "running"), None),
        ("loop.state.yaml", "phase"): lambda: state["phase"],
        ("loop.state.yaml", "ready_set"): lambda: sorted(node for node, status in state["states"].items() if status == "ready"),
        ("loop.state.yaml", "updated_at"): lambda: state["updated_at"],
    }
    if artifact == "node.contract.yaml" and root in {"node_id", "attempt", "status", "started", "finished"}:
        source = {"attempt": "attempts", "status": "states", "started": "started",
                  "finished": "finished"}.get(root)
        rebuilt = {
            node_id: node_id if source is None else state[source].get(node_id, MISSING)
            for node_id in actual
        }
    elif (artifact, root) in direct:
        rebuilt = direct[(artifact, root)]()
        rebuilt = project({root: rebuilt}, field)
    else:
        if root == "plan_version":
            return ("PLAN-SOURCED", MISSING,
                    "linkage field: loop.plan.yaml is its source (R27 governs it), "
                    "never a reconstruction target")
        if root in {"cost_units_spent", "iteration"}:
            return ("NO-EVENT-SOURCE", MISSING,
                    "snapshot-carried: no event field carries it and no charging "
                    "point is defined, so counting attempts would be an assumption")
        lossy = (artifact == "artifacts/INDEX.yaml" and root == "artifacts") or root == "gate"
        return ("NOT-RECONSTRUCTIBLE" if lossy else "NO-EVENT-SOURCE", MISSING,
                "event schema has only lossy mutation metadata" if lossy else "no event field carries this information")
    if actual is MISSING:
        return ("FIELD-ABSENT-ON-DISK", rebuilt,
                "field not present in this artifact; nothing to compare against")
    if rebuilt is MISSING or (isinstance(rebuilt, dict) and any(value is MISSING for value in rebuilt.values())):
        return "NOT-RECONSTRUCTIBLE", rebuilt, "replay source exists but observed events are insufficient"
    return ("RECONSTRUCTIBLE", rebuilt, "replayed value matches disk") if rebuilt == actual else (
        "NOT-RECONSTRUCTIBLE", rebuilt, "replayed value differs from disk")


def measure(loop_dir: Path) -> dict[str, Any]:
    event_path = find_event_log(loop_dir)
    events = load_events(event_path)
    plan_paths = find_artifact(loop_dir, "loop.plan.yaml")
    ledger_paths = find_artifact(loop_dir, "evidence.ledger.yaml")
    plan = load_yaml(plan_paths[0]) if plan_paths else None
    ledger = load_yaml(ledger_paths[0]) if ledger_paths else None
    state = replay(events, plan, ledger)
    rows: list[dict[str, Any]] = []
    for artifact, schema in sorted(ARTIFACTS.items()):
        paths = find_artifact(loop_dir, artifact)
        documents = [load_yaml(path) or {} for path in paths]
        for field in schema_fields(schema):
            claim = (artifact, field) in CLAIMS
            if not paths:
                verdict, detail, disagreement = "ABSENT-IN-THIS-LOOP", "artifact file absent", False
            else:
                if artifact == "node.contract.yaml":
                    actual = {
                        str(document.get("node_id", path.stem)): project(document, field)
                        for path, document in zip(paths, documents)
                    }
                else:
                    actual = project(documents[0], field)
                verdict, _, detail = reconstruction(artifact, field, state, actual)
                disagreement = claim and verdict != "RECONSTRUCTIBLE"
            rows.append({"artifact": artifact, "field": field, "verdict": verdict,
                         "protocol_claims": claim, "disagreement": disagreement, "detail": detail})
    counts: dict[str, dict[str, int]] = {}
    for artifact in sorted(ARTIFACTS):
        counter = Counter(row["verdict"] for row in rows if row["artifact"] == artifact)
        counts[artifact] = {key: counter[key] for key in (*VERDICTS, "ABSENT-IN-THIS-LOOP")}
    return {"loop_dir": str(loop_dir), "event_log": str(event_path) if event_path else None,
            "rows": rows, "summary": counts}


def print_text(report: dict[str, Any]) -> None:
    print(f"LOOP\t{report['loop_dir']}")
    print(f"EVENT-LOG\t{report['event_log'] or 'ABSENT'}")
    print("ARTIFACT\tFIELD\tVERDICT\tPROTOCOL-CLAIMS\tDISAGREEMENT\tDETAIL")
    for row in report["rows"]:
        print("\t".join((row["artifact"], row["field"], row["verdict"],
                         "CLAIMED" if row["protocol_claims"] else "-",
                         "YES" if row["disagreement"] else "-", row["detail"])))
    print("SUMMARY")
    for artifact, counts in report["summary"].items():
        print("\t".join([artifact] + [f"{key}={counts[key]}" for key in (*VERDICTS, "ABSENT-IN-THIS-LOOP")]))


def main(argv: Iterable[str] | None = None) -> int:
    parser = InstrumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("loop_dir")
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        loop_dir = Path(args.loop_dir).resolve()
        if not loop_dir.is_dir():
            raise ValueError(f"not a directory: {loop_dir}")
        report = measure(loop_dir)
        if args.as_json:
            print(json.dumps(report, indent=2, sort_keys=True, default=lambda _: "<unavailable>"))
        else:
            print_text(report)
    except Exception as exc:
        print(f"INSTRUMENT-ERROR\t{type(exc).__name__}\t{exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
