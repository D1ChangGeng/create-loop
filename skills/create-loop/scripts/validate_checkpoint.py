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

NODE_STATUSES: frozenset[str] = frozenset({
    "undiscovered", "discovered", "needs_clarification", "pending", "ready",
    "running", "waiting_external", "waiting_user", "blocked", "verifying",
    "verification_failed", "retry_pending", "completed", "cancelled", "deprecated",
})

CHECKPOINT_REQUIRED: tuple[str, ...] = (
    "schema_version", "plan_id", "plan_version", "checkpoint_id", "created",
    "phase", "node_states", "ready_set", "last_completed", "blocked",
    "pending_approvals", "next_suggested_action", "open_assumptions",
    "event_log_ref", "evidence_ledger_ref", "cost_units_spent", "iteration",
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
            if status not in NODE_STATUSES:
                errors.append(
                    f"[SCHEMA] checkpoint: node_states[{nid!r}] status {status!r} is "
                    f"not one of the 15 node statuses"
                )
    elif "node_states" in doc:
        errors.append("[SCHEMA] checkpoint: node_states must be a mapping")


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a checkpoint YAML artifact.")
    parser.add_argument("file", help="Path to the checkpoint YAML.")
    parser.add_argument("--plan", help="Path to the loop.plan YAML for R6 consistency.")
    args = parser.parse_args()

    doc = load_yaml(args.file)
    errors: list[str] = []
    validate_checkpoint_schema(doc, errors)

    if args.plan:
        plan = load_yaml(args.plan)
        validate_consistency(doc, plan, args.plan, errors)

    if errors:
        for msg in errors:
            print(msg, file=sys.stderr)
        print(f"error: {args.file} is invalid ({len(errors)} problem(s))", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
