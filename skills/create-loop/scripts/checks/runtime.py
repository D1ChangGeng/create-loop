"""node.runtime.yaml checks: subgraph required fields (R5), subgraph status
enum (R14), and the node-status crossover guard (R15)."""
from __future__ import annotations

from typing import Any

from checks import NODE_STATUSES, RUNTIME_SUBGRAPH_REQUIRED, SUBGRAPH_STATUSES


def validate_node_runtime(doc: Any, errors: list[str]) -> None:
    """Validate a node.runtime.yaml (R14, R15 — subgraph status enum)."""
    if not isinstance(doc, dict):
        errors.append("[R5 MISSING REQUIRED FIELD] node.runtime: document is not a mapping")
        return
    for field in ("node_id", "runtime_subgraphs"):
        if field not in doc:
            errors.append(
                f"[R5 MISSING REQUIRED FIELD] node.runtime: missing required field "
                f"{field!r}"
            )
    subgraphs = doc.get("runtime_subgraphs")
    if not isinstance(subgraphs, list):
        if "runtime_subgraphs" in doc:
            errors.append(
                "[R5 MISSING REQUIRED FIELD] node.runtime: runtime_subgraphs must "
                "be a list"
            )
        return
    for idx, sg in enumerate(subgraphs):
        scope = f"node.runtime runtime_subgraphs[{idx}]"
        if not isinstance(sg, dict):
            errors.append(f"[R5 MISSING REQUIRED FIELD] {scope}: subgraph must be an object")
            continue
        sg_id = sg.get("subgraph_id")
        label = f"{scope} ({sg_id!r})" if sg_id is not None else scope
        for field in RUNTIME_SUBGRAPH_REQUIRED:
            if field not in sg:
                errors.append(
                    f"[R5 MISSING REQUIRED FIELD] {label}: missing required field "
                    f"{field!r}"
                )
        if "subgraph_id" in sg and not (
            isinstance(sg_id, str) and sg_id.startswith("SG-")
        ):
            errors.append(
                f"[R5 BAD subgraph_id] {label}: subgraph_id {sg_id!r} must start "
                f"with 'SG-'"
            )

        status = sg.get("status")
        if "status" in sg and status not in SUBGRAPH_STATUSES:
            if status in NODE_STATUSES:
                errors.append(
                    f"[R15 SUBGRAPH-STATUS-CROSSOVER] {label}: status {status!r} is a "
                    f"node status, not a subgraph status — the two enums are disjoint; "
                    f"use one of {sorted(SUBGRAPH_STATUSES)}"
                )
            else:
                errors.append(
                    f"[R14 BAD subgraph status] {label}: status {status!r} is not one "
                    f"of the 8 subgraph statuses {sorted(SUBGRAPH_STATUSES)}"
                )

        sg_nodes = sg.get("nodes")
        if isinstance(sg_nodes, list):
            for nidx, sg_node in enumerate(sg_nodes):
                if not isinstance(sg_node, dict):
                    continue
                n_status = sg_node.get("status")
                if "status" in sg_node and n_status not in SUBGRAPH_STATUSES:
                    if n_status in NODE_STATUSES:
                        errors.append(
                            f"[R15 SUBGRAPH-STATUS-CROSSOVER] {label} nodes[{nidx}]: "
                            f"status {n_status!r} is a node status, not a subgraph "
                            f"status — the two enums are disjoint"
                        )
                    else:
                        errors.append(
                            f"[R14 BAD subgraph status] {label} nodes[{nidx}]: status "
                            f"{n_status!r} is not one of the 8 subgraph statuses"
                        )
                # R25: a completed subgraph node must carry its evidence artifact.
                if n_status == "completed" and not sg_node.get("output"):
                    errors.append(
                        f"[R25 SUBGRAPH-FAKE-COMPLETION] {label} nodes[{nidx}] "
                        f"({sg_node.get('id')!r}): status is 'completed' but 'output' "
                        f"is null/empty — a completed subgraph node MUST record its "
                        f"evidence artifact in 'output'."
                    )

        # R25: a completed subgraph must record how completion was verified.
        if sg.get("status") == "completed":
            cg = sg.get("completion_gate")
            pass_condition = cg.get("pass_condition") if isinstance(cg, dict) else None
            if not pass_condition:
                errors.append(
                    f"[R25 SUBGRAPH-FAKE-COMPLETION] {label}: status is 'completed' "
                    f"but completion_gate.pass_condition is missing/empty — a "
                    f"completed subgraph MUST record how completion was verified."
                )
