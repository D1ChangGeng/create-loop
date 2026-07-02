#!/usr/bin/env python3
"""check_loop_integrity.py — whole-loop-directory anti-corruption gate.

The per-file validators (validate_loop_plan.py / validate_checkpoint.py) each see
ONE artifact. Corruption in a long-running loop is usually CROSS-file: the
checkpoint says a node is completed but the ledger has no passing evidence; an
INDEX lists a child loop whose directory is gone; an evidence artifact_path
points at a file that was deleted. This gate runs the per-file validators AND the
cross-file reconciliation, over an entire loop directory, and is meant to run at
every session start, after every node completion, and after every plan mutation.

Contract: exit 0 = the loop directory is internally consistent and safe to
advance. Exit 1 = at least one integrity violation; the caller MUST NOT advance
normal work and should enter a recovery subgraph (see recovery_protocol.md).

Usage:
    python3 scripts/check_loop_integrity.py <loop-dir>
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

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


def check_loop_dir(loop_dir: Path) -> list[str]:
    problems: list[str] = []
    plan_p = loop_dir / "loop.plan.yaml"
    ckpt_p = loop_dir / "checkpoint.yaml"
    ledger_p = loop_dir / "evidence.ledger.yaml"
    meta_p = loop_dir / "loop.meta.yaml"
    child_index_p = loop_dir / "_loops" / "INDEX.yaml"

    if not plan_p.exists():
        return [f"[INTEGRITY] {loop_dir}: no loop.plan.yaml — not a loop directory"]

    # 1. Per-file structural validators (compose, don't duplicate).
    rc, out = _run_validator("validate_loop_plan.py", str(plan_p))
    if rc != 0:
        problems.append(f"[INTEGRITY:graph] loop.plan invalid:\n{out}")
    if ckpt_p.exists():
        cargs = [str(ckpt_p), "--plan", str(plan_p)]
        rc, out = _run_validator("validate_checkpoint.py", *cargs)
        if rc != 0:
            problems.append(f"[INTEGRITY:state] checkpoint invalid:\n{out}")
    if ledger_p.exists():
        rc, out = _run_validator(
            "validate_loop_plan.py", "--kind", "evidence_ledger",
            str(ledger_p), "--plan", str(plan_p),
        )
        if rc != 0:
            problems.append(f"[INTEGRITY:evidence] ledger invalid:\n{out}")
    if child_index_p.exists():
        rc, out = _run_validator(
            "validate_loop_plan.py", "--kind", "loops_index",
            str(child_index_p), "--root", str(loop_dir / "_loops"),
        )
        if rc != 0:
            problems.append(f"[INTEGRITY:index] child INDEX invalid:\n{out}")

    plan = _load(plan_p) or {}
    ckpt = _load(ckpt_p) or {}
    ledger = _load(ledger_p) or {}
    nodes = {n.get("id"): n for n in plan.get("nodes", []) if isinstance(n, dict)}

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

    # 4. Completed node needs active passing evidence — but ONLY when a ledger
    #    exists (no ledger = legal minimal mode, not corruption; do not remove).
    if ledger_p.exists():
        passed = {
            e.get("node_id")
            for e in (ledger.get("entries") or [])
            if isinstance(e, dict) and e.get("verdict") == "pass"
            and e.get("status", "active") == "active"
        }
        for nid, st in (ckpt.get("node_states") or {}).items():
            if st == "completed" and nid in nodes and nid not in passed:
                problems.append(
                    f"[INTEGRITY:evidence] node {nid!r} is 'completed' in the checkpoint "
                    f"but has no active passing evidence entry — degrade to "
                    f"verification_failed."
                )

    # 5. cross-file: every evidence artifact_path exists on disk (relative to loop dir).
    for e in (ledger.get("entries") or []):
        if not isinstance(e, dict) or e.get("status", "active") != "active":
            continue
        ap = e.get("artifact_path")
        if isinstance(ap, str) and ap and not ap.startswith(("http://", "https://")):
            if not (loop_dir / ap).exists() and not Path(ap).exists():
                problems.append(
                    f"[INTEGRITY:evidence] evidence {e.get('entry_id')!r} artifact_path "
                    f"{ap!r} does not exist — evidence is invalid, mark it 'invalid'."
                )

    # 6. cross-file: meta identity present when this is a child loop dir.
    if meta_p.exists():
        meta = _load(meta_p) or {}
        if not meta.get("loop_id"):
            problems.append("[INTEGRITY:identity] loop.meta.yaml has no loop_id")

    return problems


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_loop_integrity.py <loop-dir>", file=sys.stderr)
        return 2
    loop_dir = Path(sys.argv[1]).resolve()
    if not loop_dir.is_dir():
        print(f"error: {loop_dir} is not a directory", file=sys.stderr)
        return 2
    problems = check_loop_dir(loop_dir)
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
    print(f"INTEGRITY OK: {loop_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
