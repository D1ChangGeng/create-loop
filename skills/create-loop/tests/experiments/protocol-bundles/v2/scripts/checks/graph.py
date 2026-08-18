"""Graph checks over one plan/subgraph scope: cycle (R1) and dangling dep (R2)."""
from __future__ import annotations

from typing import Any


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
