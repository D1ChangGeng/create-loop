#!/usr/bin/env python3
"""Inspect cross-file references in a loop directory.

This script checks the plan and checkpoint structures; checkpoint-to-plan node
and identity references; declared event-log and evidence-ledger file references;
JSON syntax on every event-log JSONL line; active passing ledger entries for
completed nodes; active evidence artifact paths; optional child-index references;
and child-loop metadata identity when those optional artifacts exist.

Success licenses only the reported cross-file reference checks. It does not
license the conclusions that the loop is correct, the work is adequate, or the
loop is complete; those are semantic judgments for the runner.

Usage:
    python3 scripts/check_loop_integrity.py <loop-dir>
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

import yaml

from checks.checkpoint_projection import check_checkpoint_projection
from checks.event_log import validate_event_log
from checks.provenance import (
    check_event_evidence_references,
    check_missing_dissent,
    current_evidence_by_node,
)
from validate_loop_plan import validate_evidence_ledger_shape

HERE = Path(__file__).resolve().parent


def _load(path: Path):
    try:
        return yaml.safe_load(path.read_text())
    except FileNotFoundError:
        return None
    except yaml.YAMLError as exc:  # pragma: no cover - surfaced as a violation
        return {"__parse_error__": str(exc)}


def _run_validator(script: str, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(HERE / script), *args],
        capture_output=True, text=True,
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def _confined_reference(loop_dir: Path, ref, fallback: str, label: str) -> tuple[Path, str | None]:
    value = ref if isinstance(ref, str) and ref else fallback
    normalized = value.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(value)
    if (
        not posix.parts
        or posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or ".." in posix.parts
        or any(":" in part for part in posix.parts)
    ):
        return loop_dir / fallback, f"[INTEGRITY:path] {label} must be relative to the loop directory: {value!r}"
    candidate = Path(*posix.parts)
    root = loop_dir.resolve()
    resolved = (loop_dir / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return loop_dir / fallback, f"[INTEGRITY:path] {label} escapes the loop directory: {value!r}"
    return resolved, None


def _load_jsonl(path: Path) -> tuple[list[dict], list[str]]:
    entries: list[dict] = []
    problems: list[str] = []
    try:
        with path.open(encoding="utf-8") as event_log:
            for line_number, line in enumerate(event_log, start=1):
                try:
                    entry = json.loads(line)
                    if isinstance(entry, dict):
                        entries.append(entry)
                    else:
                        problems.append(
                            f"[INTEGRITY:event-log] {path}:{line_number}: JSONL entry "
                            "must be an object"
                        )
                except json.JSONDecodeError as exc:
                    problems.append(
                        f"[INTEGRITY:event-log] {path}:{line_number}: malformed JSONL: {exc}"
                    )
    except OSError as exc:
        problems.append(f"[INTEGRITY:event-log] cannot read {path}: {exc}")
    return entries, problems


def _plan_nodes(plan: dict) -> dict[str, dict]:
    nodes: dict[str, dict] = {}

    def walk(raw_nodes) -> None:
        if not isinstance(raw_nodes, list):
            return
        for node in raw_nodes:
            if not isinstance(node, dict):
                continue
            node_id = node.get("id")
            if isinstance(node_id, str):
                nodes[node_id] = node
            subgraph = node.get("subgraph")
            if isinstance(subgraph, dict):
                walk(subgraph.get("nodes"))

    walk(plan.get("nodes"))
    return nodes


def check_loop_dir(loop_dir: Path) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    checks: list[str] = []
    plan_p = loop_dir / "loop.plan.yaml"
    ckpt_p = loop_dir / "checkpoint.yaml"
    meta_p = loop_dir / "loop.meta.yaml"
    child_index_p = loop_dir / "_loops" / "INDEX.yaml"

    if not plan_p.exists():
        return [f"[INTEGRITY] {loop_dir}: no loop.plan.yaml — not a loop directory"], checks

    # 1. Per-file structural validators (compose, don't duplicate).
    rc, out = _run_validator("validate_loop_plan.py", str(plan_p))
    checks.append("loop.plan structural validation")
    if rc != 0:
        problems.append(f"[INTEGRITY:graph] loop.plan invalid:\n{out}")
    if not ckpt_p.exists():
        problems.append(
            f"[R42 INCOMPLETE-STATE] {loop_dir}: checkpoint.yaml is required for resume"
        )
        return problems, checks

    cargs = [str(ckpt_p), "--plan", str(plan_p)]
    rc, out = _run_validator("validate_checkpoint.py", *cargs)
    checks.append("checkpoint structural validation and plan linkage")
    if rc != 0:
        problems.append(f"[INTEGRITY:state] checkpoint invalid:\n{out}")

    plan = _load(plan_p) or {}
    ckpt = _load(ckpt_p) or {}
    ledger_ref = ckpt.get("evidence_ledger_ref")
    event_log_ref = ckpt.get("event_log_ref")
    ledger_p, ledger_ref_problem = _confined_reference(
        loop_dir, ledger_ref, "evidence.ledger.yaml", "checkpoint.evidence_ledger_ref"
    )
    event_log_p, event_ref_problem = _confined_reference(
        loop_dir, event_log_ref, "event_log.jsonl", "checkpoint.event_log_ref"
    )
    problems.extend(problem for problem in (ledger_ref_problem, event_ref_problem) if problem)
    event_entries: list[dict] = []

    if event_log_p.exists():
        event_entries, event_problems = _load_jsonl(event_log_p)
        problems.extend(event_problems)
    else:
        problems.append(
            f"[R42 INCOMPLETE-STATE] checkpoint.event_log_ref points to missing "
            f"file: {event_log_p}"
        )
    checks.append("declared event-log existence and line-by-line JSONL parsing")

    if isinstance(ledger_ref, str) and ledger_ref and not ledger_p.exists():
        problems.append(
            f"[R42 INCOMPLETE-STATE] checkpoint.evidence_ledger_ref points to missing "
            f"file: {ledger_p}"
        )

    if ledger_p.exists():
        rc, out = _run_validator(
            "validate_loop_plan.py", "--kind", "evidence_ledger",
            str(ledger_p), "--plan", str(plan_p),
        )
        checks.append("evidence-ledger structural validation and plan linkage")
        if rc != 0:
            problems.append(f"[INTEGRITY:evidence] ledger invalid:\n{out}")
    if child_index_p.exists():
        rc, out = _run_validator(
            "validate_loop_plan.py", "--kind", "loops_index",
            str(child_index_p), "--root", str(loop_dir / "_loops"),
        )
        checks.append("optional child INDEX references")
        if rc != 0:
            problems.append(f"[INTEGRITY:index] child INDEX invalid:\n{out}")

    loaded_ledger = _load(ledger_p) or {}
    ledger_shape_errors: list[str] = []
    validate_evidence_ledger_shape(loaded_ledger, ledger_shape_errors)
    ledger = loaded_ledger if not ledger_shape_errors else {}
    nodes = _plan_nodes(plan) if isinstance(plan, dict) else {}
    if event_log_p.exists():
        event_errors: list[str] = []
        validate_event_log(event_entries, event_errors, node_ids=set(nodes))
        check_event_evidence_references(event_entries, ledger, event_errors)
        problems.extend(f"[INTEGRITY:event-log] {error}" for error in event_errors)
        checks.append(
            "event-log replay safety, legal transitions, node identity, exact "
            "effects, and evidence-reference causality"
        )
        valid_seqs = [
            event.get("seq") for event in event_entries
            if isinstance(event.get("seq"), int) and not isinstance(event.get("seq"), bool)
        ]
        tail_seq = max(valid_seqs) if valid_seqs else 0
        if ckpt.get("last_event_seq") != tail_seq:
            problems.append(
                f"[R49 CHECKPOINT-EVENT-SEQ] checkpoint.last_event_seq "
                f"{ckpt.get('last_event_seq')!r} != event-log tail seq {tail_seq!r}"
            )
        checks.append("checkpoint last_event_seq reconciliation")

    # 2. cross-file: checkpoint plan linkage.
    if ckpt and plan.get("plan_id") and ckpt.get("plan_id") not in (None, plan["plan_id"]):
        problems.append(
            f"[INTEGRITY:state] checkpoint.plan_id {ckpt.get('plan_id')!r} != "
            f"loop.plan.plan_id {plan['plan_id']!r}"
        )

    # 3. cross-file: every checkpoint node exists in the plan.
    for nid in (ckpt.get("node_states") or {}):
        if nid not in nodes:
            problems.append(
                f"[INTEGRITY:state] checkpoint node_states references {nid!r} which is "
                f"not a node in loop.plan"
            )
    missing_checkpoint_nodes = sorted(set(nodes) - set(ckpt.get("node_states") or {}))
    if missing_checkpoint_nodes:
        problems.append(
            f"[INTEGRITY:state] checkpoint.node_states omits plan node(s), including "
            f"nested subgraph nodes: {missing_checkpoint_nodes!r}"
        )

    completed_nodes = {
        nid for nid, status in (ckpt.get("node_states") or {}).items()
        if status == "completed" and nid in nodes
    }
    if completed_nodes and not ledger_p.exists():
        problems.append(
            "[R42 INCOMPLETE-STATE] checkpoint has completed node(s) but no evidence "
            f"ledger exists at {ledger_p}"
        )

    # 4. Every completed node needs active passing evidence when a ledger exists.
    if ledger_p.exists():
        current_evidence = current_evidence_by_node(ledger, problems)
        completion_authorized = {
            node_id for node_id, entry in current_evidence.items()
            if entry.get("verdict") == "pass"
            and (entry.get("assurance") == "external"
                 or entry.get("gate_kind") == "human_approval")
        }
        for nid, st in (ckpt.get("node_states") or {}).items():
            if st == "completed" and nid in nodes and nid not in completion_authorized:
                problems.append(
                    f"[R43 SELF-ATTESTED-COMPLETION] node {nid!r} is 'completed' "
                    "but has no active passing entry whose declared assurance is "
                    "'external' or whose declared gate_kind is 'human_approval'; "
                    "this checks only those literal ledger fields and does not "
                    "license any conclusion about evidence adequacy, correctness, "
                    "or whether the node is genuinely done"
                )
    checks.append("completed-node declared evidence authorization fields")

    check_missing_dissent(ledger, ckpt, event_entries, problems)
    checks.append("completed-node blind-failure dissent records")

    if event_log_p.exists() and ledger_p.exists():
        check_checkpoint_projection(plan, event_entries, ledger, ckpt, problems)
        checks.append("canonical checkpoint node_states projection consistency (R49)")

    # 6. cross-file: every evidence artifact_path exists on disk (relative to loop dir).
    for e in (ledger.get("entries") or []):
        if not isinstance(e, dict) or e.get("status", "active") != "active":
            continue
        ap = e.get("artifact_path")
        if isinstance(ap, str) and ap and not ap.startswith(("http://", "https://")):
            artifact_p, artifact_problem = _confined_reference(
                loop_dir, ap, "__invalid_evidence_path__", f"evidence {e.get('entry_id')!r} artifact_path"
            )
            if artifact_problem:
                problems.append(artifact_problem)
            elif not artifact_p.exists():
                problems.append(
                    f"[INTEGRITY:evidence] evidence {e.get('entry_id')!r} artifact_path "
                    f"{ap!r} does not exist — evidence is invalid, mark it 'invalid'."
                )
    checks.append("active evidence artifact paths")

    # 7. Validate optional control artifacts whenever they are present.
    optional_files = (
        (loop_dir / "loop.state.yaml", "loop_state"),
        (loop_dir / "artifact.index.yaml", "artifact_index"),
        (loop_dir / "artifacts" / "INDEX.yaml", "artifact_index"),
    )
    for path, kind in optional_files:
        if not path.exists():
            continue
        rc, out = _run_validator("validate_loop_plan.py", "--kind", kind, str(path))
        checks.append(f"optional {kind} validation")
        if rc != 0:
            problems.append(f"[INTEGRITY:{kind}] {path} invalid:\n{out}")
    contracts_dir = loop_dir / "contracts"
    if contracts_dir.is_dir():
        for path in sorted(contracts_dir.glob("*.claim")):
            rc, out = _run_validator("validate_loop_plan.py", "--kind", "claim", str(path))
            checks.append("optional claim validation")
            if rc != 0:
                problems.append(f"[INTEGRITY:claim] {path} invalid:\n{out}")
        for path in sorted(contracts_dir.glob("*.yaml")):
            rc, out = _run_validator("validate_loop_plan.py", "--kind", "node_contract", str(path))
            checks.append("optional node-contract validation")
            if rc != 0:
                problems.append(f"[INTEGRITY:node-contract] {path} invalid:\n{out}")
    runtime_dir = loop_dir / "runtime"
    if runtime_dir.is_dir():
        for path in sorted(runtime_dir.rglob("*.yaml")):
            rc, out = _run_validator("validate_loop_plan.py", "--kind", "node_runtime", str(path))
            checks.append("optional node-runtime validation")
            if rc != 0:
                problems.append(f"[INTEGRITY:node-runtime] {path} invalid:\n{out}")
    nodes_dir = loop_dir / "nodes"
    if nodes_dir.is_dir():
        for path in sorted(nodes_dir.glob("*/node.contract.yaml")):
            rc, out = _run_validator("validate_loop_plan.py", "--kind", "node_contract", str(path))
            checks.append("optional canonical node-contract validation")
            if rc != 0:
                problems.append(f"[INTEGRITY:node-contract] {path} invalid:\n{out}")
        for path in sorted(nodes_dir.glob("*/node.runtime.yaml")):
            rc, out = _run_validator("validate_loop_plan.py", "--kind", "node_runtime", str(path))
            checks.append("optional canonical node-runtime validation")
            if rc != 0:
                problems.append(f"[INTEGRITY:node-runtime] {path} invalid:\n{out}")

    # 8. cross-file: meta identity present when this is a child loop dir.
    if meta_p.exists():
        rc, out = _run_validator(
            "validate_loop_plan.py", "--kind", "loop_meta", str(meta_p)
        )
        checks.append("optional loop metadata validation")
        if rc != 0:
            problems.append(f"[INTEGRITY:identity] loop.meta.yaml invalid:\n{out}")

    return problems, checks


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_loop_integrity.py <loop-dir>", file=sys.stderr)
        return 2
    loop_dir = Path(sys.argv[1]).resolve()
    if not loop_dir.is_dir():
        print(f"error: {loop_dir} is not a directory", file=sys.stderr)
        return 2
    problems, checks = check_loop_dir(loop_dir)
    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        print(
            f"\nINTEGRITY GATE FAILED ({len(problems)} violation(s)) for {loop_dir}.\n"
            f"Do NOT advance normal work — enter a recovery subgraph "
            f"(references/recovery_protocol.md).",
            file=sys.stderr,
        )
        return 1
    print(f"CROSS-FILE REFERENCES OK: {loop_dir}")
    print("Checks run:")
    for check in checks:
        print(f"- {check}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
