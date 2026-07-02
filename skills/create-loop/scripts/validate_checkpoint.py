#!/usr/bin/env python3
"""Validate a checkpoint YAML artifact, optionally against its loop.plan.

Standalone: required-field + enum checks per checkpoint.schema.json.
With --plan: R6 CONSISTENCY — every node_states key, ready_set id, and
last_completed id must be a node id defined in the plan; plan_id and
plan_version must match the plan.

Exit codes: 0 valid, 1 schema/consistency error(s), 2 load error.
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

# Single source of truth: shared enums/patterns come from the checks package.
from checks import LOOP_ID_RE, NODE_STATUSES

CHECKPOINT_REQUIRED: tuple[str, ...] = (
    "schema_version", "plan_id", "plan_version", "checkpoint_id", "checkpoint_seq",
    "created", "phase", "node_states", "ready_set", "last_completed", "blocked",
    "pending_approvals", "next_suggested_action", "open_assumptions",
    "event_log_ref", "evidence_ledger_ref", "cost_units_spent", "iteration",
)
# Optional child-loop checkpoint fields (recursive_loops.md). Recognized but
# never required, so the 17-field base checkpoint keeps validating.
CHILD_LOOP_OPTIONAL: tuple[str, ...] = (
    "loop_id", "parent_loop_id", "parent_node_id", "current_node",
    "last_valid_artifacts", "next_recommended_action", "open_blockers",
)


def validate_child_checkpoint(doc: Any, meta: Any, errors: list[str]) -> None:
    """R33: when the owning loop.meta.type == child_loop, the checkpoint MUST
    carry all 7 child-loop fields so a fresh session can locate its parent and
    return contract. For a root_loop these fields stay optional."""
    if not isinstance(doc, dict) or not isinstance(meta, dict):
        return
    if meta.get("type") != "child_loop":
        return
    for field in CHILD_LOOP_OPTIONAL:
        if field not in doc:
            errors.append(
                f"[R33 CHILD-FIELD-MISSING] child-loop checkpoint: missing required "
                f"field {field!r} (a child_loop checkpoint must carry all 7 "
                f"parent-identity/resume fields)"
            )


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


def collect_plan_node_ids(plan: Any) -> set[str]:
    """Gather all node ids from a plan, recursing into subgraphs."""
    ids: set[str] = set()

    def walk(nodes: Any) -> None:
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            nid = node.get("id")
            if isinstance(nid, str):
                ids.add(nid)
            sub = node.get("subgraph")
            if isinstance(sub, dict):
                walk(sub.get("nodes"))

    if isinstance(plan, dict):
        walk(plan.get("nodes"))
    return ids


def validate_checkpoint_schema(doc: Any, errors: list[str]) -> None:
    """Required-field + node_states status enum checks."""
    if not isinstance(doc, dict):
        errors.append("[SCHEMA] checkpoint: document is not a mapping")
        return
    for field in CHECKPOINT_REQUIRED:
        if field not in doc:
            errors.append(f"[SCHEMA] checkpoint: missing required field {field!r}")
    node_states = doc.get("node_states")
    if isinstance(node_states, dict):
        for nid, status in node_states.items():
            if status == "escalate":
                errors.append(
                    f"[R20 ESCALATE-NOT-A-STATUS] checkpoint: node_states[{nid!r}] uses "
                    f"'escalate', which is an escalation-ladder rung, not a node status. "
                    f"Use 'waiting_user' (bound to an approval node) or 'blocked'."
                )
            elif status not in NODE_STATUSES:
                errors.append(
                    f"[SCHEMA] checkpoint: node_states[{nid!r}] status {status!r} is "
                    f"not one of the 15 node statuses"
                )
    elif "node_states" in doc:
        errors.append("[SCHEMA] checkpoint: node_states must be a mapping")

    for field in ("loop_id", "parent_loop_id"):
        val = doc.get(field)
        if field in doc and not (isinstance(val, str) and LOOP_ID_RE.match(val)):
            errors.append(
                f"[SCHEMA] checkpoint: {field} {val!r} does not match the loop-id "
                f"pattern L<seq>[.<seq>]"
            )

    seq = doc.get("checkpoint_seq")
    if "checkpoint_seq" in doc and not (isinstance(seq, int) and not isinstance(seq, bool) and seq >= 0):
        errors.append(
            f"[R32 BAD-CHECKPOINT-SEQ] checkpoint: checkpoint_seq {seq!r} must be a "
            f"non-negative integer (used for monotonic latest-checkpoint selection)"
        )


def validate_consistency(doc: Any, plan: Any, plan_path: str, errors: list[str]) -> None:
    """R6: checkpoint must be consistent with its plan."""
    if not isinstance(doc, dict) or not isinstance(plan, dict):
        return
    plan_ids = collect_plan_node_ids(plan)

    # plan_id must match.
    if doc.get("plan_id") != plan.get("plan_id"):
        errors.append(
            f"[R6 CONSISTENCY] checkpoint.plan_id {doc.get('plan_id')!r} != "
            f"plan.plan_id {plan.get('plan_id')!r} ({plan_path})"
        )
    # plan_version must match.
    if doc.get("plan_version") != plan.get("plan_version"):
        errors.append(
            f"[R6 CONSISTENCY] checkpoint.plan_version {doc.get('plan_version')!r} != "
            f"plan.plan_version {plan.get('plan_version')!r} ({plan_path})"
        )

    node_states = doc.get("node_states")
    if isinstance(node_states, dict):
        for nid in node_states:
            if nid not in plan_ids:
                errors.append(
                    f"[R6 CONSISTENCY] checkpoint.node_states key {nid!r} has no "
                    f"matching node id in the plan"
                )
    for list_field in ("ready_set", "last_completed"):
        seq = doc.get(list_field)
        if isinstance(seq, list):
            for nid in seq:
                if isinstance(nid, str) and nid not in plan_ids:
                    errors.append(
                        f"[R6 CONSISTENCY] checkpoint.{list_field} id {nid!r} has no "
                        f"matching node id in the plan"
                    )


TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "cancelled", "deprecated"})


def validate_transition_closure(doc: Any, plan: Any, errors: list[str]) -> None:
    """R19: every non-terminal node must have a legal way forward.

    Two dead-end classes are rejected:
      (a) a dependent whose only unmet ``requires`` is a ``deprecated`` node with
          no superseding rewire — it can never become ``ready`` (deadlock);
      (b) a node parked in a non-terminal status whose sole guard is closed
          (handled structurally by the totality guarantee; here we flag the
          deprecated-dependency deadlock, the one case the graph can produce).
    """
    if not isinstance(doc, dict):
        return
    node_states = doc.get("node_states")
    if not isinstance(node_states, dict):
        return

    requires_map: dict[str, list[str]] = {}
    if isinstance(plan, dict):
        def walk(nodes: Any) -> None:
            if not isinstance(nodes, list):
                return
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                nid = node.get("id")
                if isinstance(nid, str):
                    req = node.get("requires")
                    requires_map[nid] = [r for r in req if isinstance(r, str)] if isinstance(req, list) else []
                sub = node.get("subgraph")
                if isinstance(sub, dict):
                    walk(sub.get("nodes"))
        walk(plan.get("nodes"))

    for nid, status in node_states.items():
        if status in TERMINAL_STATUSES:
            continue
        reqs = requires_map.get(nid, [])
        if not reqs:
            continue
        unmet = [r for r in reqs if node_states.get(r) != "completed"]
        if unmet and all(node_states.get(r) == "deprecated" for r in unmet):
            errors.append(
                f"[R19 NON-TERMINAL DEAD-END] node {nid!r} (status {status!r}) is "
                f"blocked solely by deprecated dependency(ies) {unmet!r} with no "
                f"superseding rewire — it can never become ready. Rewire to the "
                f"superseding node or move {nid!r} to needs_clarification."
            )


def validate_claims(doc: Any, claims_dir: str, errors: list[str]) -> None:
    """R22: every node in status ``running`` must hold a claim file, and a
    delegated claim must name a child loop. Single-flight at the node grain."""
    if not isinstance(doc, dict):
        return
    node_states = doc.get("node_states")
    if not isinstance(node_states, dict):
        return
    base = Path(claims_dir)
    for nid, status in node_states.items():
        if status != "running":
            continue
        claim_path = base / f"{nid}.claim"
        if not claim_path.exists():
            errors.append(
                f"[R22 UNCLAIMED-RUNNING] node {nid!r} is 'running' but has no claim "
                f"file at {claim_path} — a running node must hold a claim "
                f"(single-flight). A crashed run leaves an expired claim, not none."
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a checkpoint YAML artifact.")
    parser.add_argument("file", help="Path to the checkpoint YAML.")
    parser.add_argument("--plan", help="Path to the loop.plan YAML for R6 consistency.")
    parser.add_argument("--claims", help="Path to the contracts/ dir holding <node>.claim files (R22).")
    parser.add_argument("--meta", help="Path to the loop.meta.yaml (R33: require child fields when type==child_loop).")
    args = parser.parse_args()

    doc = load_yaml(args.file)
    errors: list[str] = []
    validate_checkpoint_schema(doc, errors)

    if args.plan:
        plan = load_yaml(args.plan)
        validate_consistency(doc, plan, args.plan, errors)
        validate_transition_closure(doc, plan, errors)

    if args.claims:
        validate_claims(doc, args.claims, errors)

    if args.meta:
        validate_child_checkpoint(doc, load_yaml(args.meta), errors)

    if errors:
        for msg in errors:
            print(msg, file=sys.stderr)
        print(f"error: {args.file} is invalid ({len(errors)} problem(s))", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
