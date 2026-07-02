"""Per-node structural + enum checks (R5, R4, R8), child_loops refs (R13), and
the recursive node-list walker that also drives graph checks on each scope."""
from __future__ import annotations

from typing import Any

from checks import (
    CHILD_LOOP_REF_REQUIRED,
    LOOP_ID_RE,
    NODE_KINDS,
    NODE_REQUIRED,
    NODE_STATUSES,
    ON_FAILURE,
)
from checks.gates import check_gate, check_gate_required
from checks.graph import check_graph


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
    check_gate_required(kind, node.get("gate"), label, errors)

    # R8: on_failure enum.
    on_failure = node.get("on_failure")
    if "on_failure" in node and on_failure not in ON_FAILURE:
        errors.append(
            f"[R8 BAD on_failure] {label}: on_failure {on_failure!r} is not one of "
            f"{sorted(ON_FAILURE)}"
        )

    # R13: child_loops reference list.
    if "child_loops" in node:
        check_child_loops(node.get("child_loops"), label, errors)


def check_child_loops(child_loops: Any, label: str, errors: list[str]) -> None:
    """Validate a node's child_loops reference list (R13)."""
    if not isinstance(child_loops, list):
        errors.append(
            f"[R13 BAD child_loops] {label}: child_loops must be a list "
            f"(empty [] when the node has no materialized children)"
        )
        return
    for idx, ref in enumerate(child_loops):
        ref_scope = f"{label} child_loops[{idx}]"
        if not isinstance(ref, dict):
            errors.append(
                f"[R13 BAD child_loops] {ref_scope}: entry must be an object with "
                f"{list(CHILD_LOOP_REF_REQUIRED)}"
            )
            continue
        for field in CHILD_LOOP_REF_REQUIRED:
            if field not in ref:
                errors.append(
                    f"[R13 BAD child_loops] {ref_scope}: missing required field "
                    f"{field!r}"
                )
        loop_id = ref.get("loop_id")
        if "loop_id" in ref and not (
            isinstance(loop_id, str) and LOOP_ID_RE.match(loop_id)
        ):
            errors.append(
                f"[R13 BAD child_loops] {ref_scope}: loop_id {loop_id!r} does not "
                f"match the loop-id pattern L<seq>[.<seq>]"
            )
        status = ref.get("status")
        if "status" in ref and status not in NODE_STATUSES:
            errors.append(
                f"[R13 BAD child_loops] {ref_scope}: status {status!r} is not one "
                f"of the 15 node statuses"
            )


def validate_nodes_recursive(nodes: Any, scope: str, errors: list[str]) -> None:
    """Validate a node list and recurse into any materialised subgraphs."""
    if not isinstance(nodes, list) or not nodes:
        errors.append(f"[R5 MISSING REQUIRED FIELD] {scope}nodes must be a non-empty list")
        return
    for node in nodes:
        check_node_fields(node, scope, errors)
        if isinstance(node, dict):
            if scope == "" and node.get("design_invariant") is False:
                errors.append(
                    f"[R35 TOPLEVEL-INVARIANT-FALSE] top-level node "
                    f"{node.get('id')!r}: design_invariant must be true — the "
                    f"top-level graph holds only design-time invariants; "
                    f"runtime-discovered work belongs in a subgraph or child loop."
                )
            sub = node.get("subgraph")
            if isinstance(sub, dict) and isinstance(sub.get("nodes"), list):
                child_scope = f"{scope}subgraph[{node.get('id')}]/"
                validate_nodes_recursive(sub["nodes"], child_scope, errors)
                check_graph(sub["nodes"], child_scope, errors)
    check_graph(nodes, scope, errors)
