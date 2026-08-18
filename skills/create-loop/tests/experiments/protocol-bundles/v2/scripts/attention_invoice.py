#!/usr/bin/env python3
"""Measure per-node control-state writes already recorded by a loop.

This is a read-only measurement instrument, not a gate. It always exits zero,
including for missing, empty, or malformed input. It derives its invoice from
the checkpoint-declared event log and persists nothing.

The invoice proves only how many control-state writes were appended per node.
It does not prove that the bookkeeping was necessary, that attention was well
spent, that the work was good, or that the node is genuinely done. A high or
low count is input to the runner's judgment, never a verdict.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import yaml

CONTROL_KINDS = ("pre_effect", "post_effect", "mutation", "dissent", "note")


class InstrumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def declared_path(loop_dir: Path, checkpoint: dict[str, Any], field: str) -> Path:
    ref = checkpoint.get(field)
    if not isinstance(ref, str) or not ref:
        raise ValueError(f"checkpoint has no declared {field}")
    return loop_dir / ref


def load_events(path: Path) -> list[dict[str, Any]]:
    return [
        value
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
        for value in [json.loads(line)]
        if isinstance(value, dict)
    ]


def load_evidence_counts(path: Path) -> Counter[str]:
    document = load_yaml(path) or {}
    entries = document.get("entries", []) if isinstance(document, dict) else []
    return Counter(
        entry["node_id"]
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("node_id"), str)
    )


def measure(loop_dir: Path) -> dict[str, Any]:
    checkpoint_path = loop_dir / "checkpoint.yaml"
    checkpoint = load_yaml(checkpoint_path) or {}
    if not isinstance(checkpoint, dict):
        raise ValueError(f"checkpoint is not a mapping: {checkpoint_path}")

    event_path = declared_path(loop_dir, checkpoint, "event_log_ref")
    evidence_path = declared_path(loop_dir, checkpoint, "evidence_ledger_ref")
    writes: dict[str, Counter[str]] = {}
    for event in load_events(event_path):
        node_id = event.get("node_id")
        kind = event.get("kind")
        if isinstance(node_id, str) and kind in CONTROL_KINDS:
            writes.setdefault(node_id, Counter())[kind] += 1

    evidence = load_evidence_counts(evidence_path)
    node_ids = sorted(set(writes) | set(evidence))
    rows = []
    for node_id in node_ids:
        event_total = sum(writes.get(node_id, Counter()).values())
        rows.append({
            "node_id": node_id,
            **{kind: writes.get(node_id, Counter())[kind] for kind in CONTROL_KINDS},
            "evidence": evidence[node_id],
            "total": event_total + evidence[node_id],
        })

    control_total = sum(row["total"] for row in rows)
    return {
        "loop_dir": str(loop_dir),
        "event_log": str(event_path),
        "evidence_ledger": str(evidence_path),
        "rows": rows,
        "summary": {
            "control_state_writes": control_total,
            "distinct_nodes_touched": len(node_ids),
            "mean_writes_per_node": control_total / len(node_ids) if node_ids else 0.0,
            "orient_distinct_facts_read": "not-derivable",
        },
    }


def print_text(report: dict[str, Any]) -> None:
    print(f"LOOP\t{report['loop_dir']}")
    print(f"EVENT-LOG\t{report['event_log']}")
    print(f"EVIDENCE-LEDGER\t{report['evidence_ledger']}")
    print("NODE\tPRE_EFFECT\tPOST_EFFECT\tMUTATION\tDISSENT\tNOTE\tEVIDENCE\tTOTAL")
    for row in report["rows"]:
        print("\t".join(str(row[key]) for key in (
            "node_id", "pre_effect", "post_effect", "mutation", "dissent",
            "note", "evidence", "total",
        )))
    summary = report["summary"]
    print("SUMMARY")
    print(f"control_state_writes={summary['control_state_writes']}")
    print(f"distinct_nodes_touched={summary['distinct_nodes_touched']}")
    print(f"mean_writes_per_node={summary['mean_writes_per_node']:.2f}")
    print(f"orient_distinct_facts_read={summary['orient_distinct_facts_read']}")
    print("BOUNDARY\tCounts appended control-state writes per node; persists nothing.")
    print("NOT-LICENSED\tNecessity, attention quality, work quality, and genuine node completion remain runner judgments; counts are never verdicts.")


def main(argv: Iterable[str] | None = None) -> int:
    parser = InstrumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("loop_dirs", nargs="+")
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        for value in args.loop_dirs:
            try:
                loop_dir = Path(value).resolve()
                if not loop_dir.is_dir():
                    raise ValueError(f"not a directory: {loop_dir}")
                report = measure(loop_dir)
                if args.as_json:
                    print(json.dumps(report, indent=2, sort_keys=True))
                else:
                    print_text(report)
            except Exception as exc:
                print(f"INSTRUMENT-ERROR\t{value}\t{type(exc).__name__}\t{exc}")
    except Exception as exc:
        print(f"INSTRUMENT-ERROR\t{type(exc).__name__}\t{exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
