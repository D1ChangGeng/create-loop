"""Recursion/cost cap checks (R28, R29). R28 rejects a plan whose declared
child_loops structure exceeds termination.max_depth / max_child_loops. R29
rejects a node.contract missing its cost_units accrual field.
"""
from __future__ import annotations

from typing import Any


def check_caps(doc: Any, errors: list[str]) -> None:
    if not isinstance(doc, dict):
        return
    term = doc.get("termination")
    if not isinstance(term, dict):
        return
    max_depth = term.get("max_depth")
    max_child = term.get("max_child_loops")

    total = 0
    max_seen_depth = 0

    def walk(nodes: Any, depth: int) -> None:
        nonlocal total, max_seen_depth
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            child_loops = node.get("child_loops")
            if isinstance(child_loops, list) and child_loops:
                total += len(child_loops)
                max_seen_depth = max(max_seen_depth, depth + 1)
            sub = node.get("subgraph")
            if isinstance(sub, dict):
                walk(sub.get("nodes"), depth)

    walk(doc.get("nodes"), 0)

    if isinstance(max_depth, int) and max_seen_depth > max_depth:
        errors.append(
            f"[R28 CAP-EXCEEDED] plan declares child loops at depth {max_seen_depth} "
            f"but termination.max_depth is {max_depth}"
        )
    if isinstance(max_child, int) and total > max_child:
        errors.append(
            f"[R28 CAP-EXCEEDED] plan declares {total} child loop reference(s) but "
            f"termination.max_child_loops is {max_child}"
        )


def check_contract_cost(doc: Any, errors: list[str]) -> None:
    if isinstance(doc, dict) and "cost_units" not in doc:
        errors.append(
            "[R29 MISSING-COST] node.contract: missing required field 'cost_units' "
            "(per-node cost accrual; enables the enforced cost budget)"
        )
