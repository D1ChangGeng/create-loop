#!/usr/bin/env python3
"""Validate a create-loop YAML artifact against its schema and graph rules.

Kinds: loop_plan (default), node_contract, evidence_ledger.

For loop_plan the CRITICAL checks (required fields, enum legality, and the
graph rules R1-R5/R7/R8) are hand-rolled from the canonical enums in
references/loop_plan_spec.md + state_model.md, so the acceptance gate never
depends on a third-party library. jsonschema is used ONLY as a bonus
structural layer when importable (guarded try/except); its absence never
hard-fails validation.

Exit codes: 0 valid, 1 structural/graph error(s), 2 load/usage error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - environment guard
    print(
        "error: PyYAML is required but not importable. Install with: pip install pyyaml",
        file=sys.stderr,
    )
    sys.exit(2)

# --- Canonical enums (verbatim from references; do NOT rename) ---------------
NODE_STATUSES: frozenset[str] = frozenset({
    "undiscovered", "discovered", "needs_clarification", "pending", "ready",
    "running", "waiting_external", "waiting_user", "blocked", "verifying",
    "verification_failed", "retry_pending", "completed", "cancelled", "deprecated",
})
NODE_KINDS: frozenset[str] = frozenset({
    "milestone", "gate", "mapper", "branch", "fanout", "join", "approval",
    "compensation",
})
GATE_KINDS: frozenset[str] = frozenset({
    "automated_check", "test", "llm_judge", "self_consistency",
    "evaluator_optimizer", "step_verifier", "human_approval", "artifact_exists",
})
ON_FAILURE: frozenset[str] = frozenset({
    "local_retry", "local_patch", "replan", "escalate",
})

# Kinds that MUST carry a gate (non-trivial). Per evidence_gates.md §6 a null
# gate is only for trivial mechanical edits; fanout/compensation/approval may be
# gate-exempt at plan level (approval self-gates via its human_approval handoff,
# fanout only dispatches, compensation is a saga undo whose gate is its pair's).
GATE_REQUIRED_KINDS: frozenset[str] = frozenset({
    "milestone", "gate", "mapper", "branch", "join",
})

PLAN_REQUIRED: tuple[str, ...] = (
    "schema_version", "plan_id", "goal", "true_intent", "non_goals",
    "success_criteria", "failure_criteria", "termination", "constraints",
    "nodes", "created", "plan_version",
)
NODE_REQUIRED: tuple[str, ...] = (
    "id", "kind", "title", "design_invariant", "status", "requires", "produces",
    "inputs", "preconditions", "postconditions", "gate", "retry_policy",
    "on_failure", "priority", "risk", "parallelizable", "allow_subgraph",
    "subgraph", "assignee", "notes",
)
LEDGER_REQUIRED: tuple[str, ...] = ("schema_version", "entries")
CONTRACT_REQUIRED: tuple[str, ...] = (
    "node_id", "plan_id", "cache_key", "attempt", "status", "gate",
    "retry_policy", "on_failure", "evidence_ref", "started", "finished",
    "compensation_of",
)

SCHEMA_BY_KIND: dict[str, str] = {
    "loop_plan": "loop.plan.schema.json",
    "node_contract": "node.contract.schema.json",
    "evidence_ledger": "evidence.ledger.schema.json",
}


def load_yaml(path: str) -> Any:
    """Load a YAML document, exiting 2 with a clear message on any failure."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except FileNotFoundError:
        print(f"error: file not found: {path}", file=sys.stderr)
        sys.exit(2)
    except (yaml.YAMLError, OSError) as exc:
        print(f"error: could not parse YAML {path}: {exc}", file=sys.stderr)
        sys.exit(2)


def check_gate(gate: Any, scope: str, errors: list[str]) -> None:
    """Validate a gate object's kind enum (R7). Skips when gate is null/absent."""
    if gate is None:
        return
    if not isinstance(gate, dict):
        errors.append(f"[R7 BAD GATE KIND] {scope}: gate must be an object or null")
        return
    kind = gate.get("kind")
    if kind not in GATE_KINDS:
        errors.append(
            f"[R7 BAD GATE KIND] {scope}: gate.kind {kind!r} is not one of the 8 "
            f"gate kinds ({sorted(GATE_KINDS)})"
        )


def check_node_fields(node: Any, scope: str, errors: list[str]) -> None:
    """Hand-rolled per-node structural + enum checks (R4, R5, R7, R8)."""
    if not isinstance(node, dict):
        errors.append(f"[R5 MISSING REQUIRED FIELD] {scope}: node is not a mapping")
        return
    node_id = node.get("id")
    label = f"node {node_id!r}" if node_id is not None else f"node (no id) in {scope}"

    # R5: required fields present (id first, so the message is actionable).
    for field in NODE_REQUIRED:
        if field not in node:
            errors.append(
                f"[R5 MISSING REQUIRED FIELD] {label}: missing required field "
                f"{field!r}"
            )

    # R4: status enum.
    status = node.get("status")
    if "status" in node and status not in NODE_STATUSES:
        errors.append(
            f"[R4 BAD STATUS] {label}: status {status!r} is not one of the 15 "
            f"node statuses"
        )

    # kind enum (feeds R3 gate-exemption decision).
    kind = node.get("kind")
    if "kind" in node and kind not in NODE_KINDS:
        errors.append(
            f"[R4 BAD KIND] {label}: kind {kind!r} is not one of the 8 node kinds"
        )

    # R7: gate kind.
    check_gate(node.get("gate"), label, errors)

    # R3: non-trivial node must carry a gate.
    if kind in GATE_REQUIRED_KINDS and node.get("gate") is None:
        errors.append(
            f"[R3 MISSING EVIDENCE GATE] {label}: non-trivial node of kind "
            f"{kind!r} has gate: null; only trivial nodes may omit a gate"
        )

    # R8: on_failure enum.
    on_failure = node.get("on_failure")
    if "on_failure" in node and on_failure not in ON_FAILURE:
        errors.append(
            f"[R8 BAD on_failure] {label}: on_failure {on_failure!r} is not one of "
            f"{sorted(ON_FAILURE)}"
        )


def check_graph(nodes: list[Any], scope: str, errors: list[str]) -> None:
    """Hand-rolled graph checks over one plan/subgraph scope (R1, R2)."""
    defined: set[str] = {
        n["id"] for n in nodes if isinstance(n, dict) and isinstance(n.get("id"), str)
    }
    adjacency: dict[str, list[str]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = node.get("id")
        if not isinstance(nid, str):
            continue
        requires = node.get("requires") or []
        deps = [d for d in requires if isinstance(d, str)]
        adjacency[nid] = deps
        # R2: dangling dependency.
        for dep in deps:
            if dep not in defined:
                errors.append(
                    f"[R2 DANGLING DEP] {scope}node {nid!r}: requires {dep!r} which "
                    f"is not the id of any defined node"
                )

    # R1: cycle detection via white(0)/gray(1)/black(2) DFS coloring.
    color: dict[str, int] = {nid: 0 for nid in adjacency}
    stack: list[str] = []

    def visit(nid: str) -> bool:
        color[nid] = 1
        stack.append(nid)
        for dep in adjacency.get(nid, []):
            if dep not in color:
                continue  # dangling; already reported by R2.
            if color[dep] == 1:
                cycle = stack[stack.index(dep):] + [dep]
                errors.append(
                    f"[R1 CYCLE] {scope}dependency cycle detected: "
                    f"{' -> '.join(cycle)}"
                )
                return True
            if color[dep] == 0 and visit(dep):
                return True
        stack.pop()
        color[nid] = 2
        return False

    for nid in adjacency:
        if color[nid] == 0 and visit(nid):
            break


def validate_nodes_recursive(nodes: Any, scope: str, errors: list[str]) -> None:
    """Validate a node list and recurse into any materialised subgraphs."""
    if not isinstance(nodes, list) or not nodes:
        errors.append(f"[R5 MISSING REQUIRED FIELD] {scope}nodes must be a non-empty list")
        return
    for node in nodes:
        check_node_fields(node, scope, errors)
        if isinstance(node, dict):
            sub = node.get("subgraph")
            if isinstance(sub, dict) and isinstance(sub.get("nodes"), list):
                child_scope = f"{scope}subgraph[{node.get('id')}]/"
                validate_nodes_recursive(sub["nodes"], child_scope, errors)
                check_graph(sub["nodes"], child_scope, errors)
    check_graph(nodes, scope, errors)


def validate_loop_plan(doc: Any, errors: list[str]) -> None:
    """Structural + graph validation for a loop.plan document."""
    if not isinstance(doc, dict):
        errors.append("[R5 MISSING REQUIRED FIELD] plan: document is not a mapping")
        return
    for field in PLAN_REQUIRED:
        if field not in doc:
            errors.append(
                f"[R5 MISSING REQUIRED FIELD] plan: missing top-level field {field!r}"
            )
    if isinstance(doc.get("termination"), dict):
        for field in ("max_iterations", "max_wall_clock_hours", "max_cost_units", "done_when"):
            if field not in doc["termination"]:
                errors.append(
                    f"[R5 MISSING REQUIRED FIELD] termination: missing {field!r}"
                )
    validate_nodes_recursive(doc.get("nodes"), "", errors)


def validate_flat_status_and_gate(doc: Any, required: tuple[str, ...], errors: list[str]) -> None:
    """Shared checks for node_contract: required fields + status + gate kind."""
    if not isinstance(doc, dict):
        errors.append("[R5 MISSING REQUIRED FIELD] document is not a mapping")
        return
    for field in required:
        if field not in doc:
            errors.append(f"[R5 MISSING REQUIRED FIELD] missing field {field!r}")
    status = doc.get("status")
    if "status" in doc and status not in NODE_STATUSES:
        errors.append(f"[R4 BAD STATUS] status {status!r} is not a valid node status")
    check_gate(doc.get("gate"), "contract", errors)
    on_failure = doc.get("on_failure")
    if "on_failure" in doc and on_failure not in ON_FAILURE:
        errors.append(f"[R8 BAD on_failure] on_failure {on_failure!r} is invalid")


def validate_evidence_ledger(doc: Any, errors: list[str]) -> None:
    """Structural checks for an evidence.ledger document."""
    if not isinstance(doc, dict):
        errors.append("[R5 MISSING REQUIRED FIELD] ledger: document is not a mapping")
        return
    for field in LEDGER_REQUIRED:
        if field not in doc:
            errors.append(f"[R5 MISSING REQUIRED FIELD] ledger: missing field {field!r}")
    entries = doc.get("entries")
    if not isinstance(entries, list):
        return
    valid_verdicts = {"pass", "fail", "inconclusive"}
    valid_verifiers = {"agent", "subagent", "user", "script"}
    for idx, entry in enumerate(entries):
        scope = f"ledger entry[{idx}]"
        if not isinstance(entry, dict):
            errors.append(f"[R5 MISSING REQUIRED FIELD] {scope}: not a mapping")
            continue
        for field in ("entry_id", "node_id", "gate_kind", "verdict", "score",
                      "artifact_path", "rationale", "recorded", "verifier"):
            if field not in entry:
                errors.append(f"[R5 MISSING REQUIRED FIELD] {scope}: missing {field!r}")
        if entry.get("gate_kind") not in GATE_KINDS and "gate_kind" in entry:
            errors.append(f"[R7 BAD GATE KIND] {scope}: gate_kind {entry.get('gate_kind')!r} invalid")
        if entry.get("verdict") not in valid_verdicts and "verdict" in entry:
            errors.append(f"[R4 BAD VERDICT] {scope}: verdict {entry.get('verdict')!r} invalid")
        if entry.get("verifier") not in valid_verifiers and "verifier" in entry:
            errors.append(f"[R4 BAD VERIFIER] {scope}: verifier {entry.get('verifier')!r} invalid")


def run_jsonschema_bonus(doc: Any, kind: str, errors: list[str]) -> None:
    """Optional structural layer: run jsonschema only if importable."""
    try:
        import jsonschema  # noqa: F401
        from jsonschema import Draft7Validator
    except ImportError:
        return
    schema_path = Path(__file__).resolve().parent.parent / "schemas" / SCHEMA_BY_KIND[kind]
    if not schema_path.exists():
        return
    try:
        import json
        with open(schema_path, "r", encoding="utf-8") as fh:
            schema = json.load(fh)
        validator = Draft7Validator(schema)
    except (OSError, ValueError) as exc:
        print(f"warning: jsonschema bonus layer skipped ({exc})", file=sys.stderr)
        return
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "<root>"
        errors.append(f"[jsonschema] {loc}: {err.message}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a create-loop YAML artifact.")
    parser.add_argument(
        "--kind",
        choices=("loop_plan", "node_contract", "evidence_ledger"),
        default="loop_plan",
        help="Artifact kind (default: loop_plan).",
    )
    parser.add_argument("file", help="Path to the YAML artifact.")
    args = parser.parse_args()

    doc = load_yaml(args.file)
    errors: list[str] = []

    if args.kind == "loop_plan":
        validate_loop_plan(doc, errors)
    elif args.kind == "node_contract":
        validate_flat_status_and_gate(doc, CONTRACT_REQUIRED, errors)
    else:
        validate_evidence_ledger(doc, errors)

    # Bonus jsonschema layer, merged in (deduplicated against hand-rolled errors).
    schema_errors: list[str] = []
    run_jsonschema_bonus(doc, args.kind, schema_errors)
    for msg in schema_errors:
        if msg not in errors:
            errors.append(msg)

    if errors:
        for msg in errors:
            print(msg, file=sys.stderr)
        print(f"error: {args.file} is invalid ({len(errors)} problem(s))", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
