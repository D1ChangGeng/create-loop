"""Node retirement / tombstone reconciliation (R40).

Complex loops must retire work, not only grow it. A node that leaves active
service (deprecated / cancelled) is never deleted — deletion would dangle the
references that point at it — it is tombstoned with a `retirement` object so the
retirement is auditable and reconcilable. R40 enforces that contract:

- a `deprecated` or `cancelled` node MUST carry a `retirement` object;
- `retirement.type` 'superseded' / 'merged' MUST name a `superseded_by`;
- when `superseded_by` names a node id, that node MUST exist (no dangling
  tombstone pointer).
"""
from __future__ import annotations

from typing import Any

_RETIRED_STATUS = {"deprecated", "cancelled"}
_NEEDS_REPLACEMENT = {"superseded", "merged"}


def _collect_ids(nodes: Any, out: set[str]) -> None:
    if not isinstance(nodes, list):
        return
    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = node.get("id")
        if isinstance(nid, str):
            out.add(nid)
        sub = node.get("subgraph")
        if isinstance(sub, dict):
            _collect_ids(sub.get("nodes"), out)
        _collect_ids(node.get("child_loops"), out)


def check_retirement(doc: Any, errors: list[str]) -> None:
    if not isinstance(doc, dict):
        return
    all_ids: set[str] = set()
    _collect_ids(doc.get("nodes"), all_ids)

    def walk(nodes: Any) -> None:
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            nid = node.get("id", "?")
            status = node.get("status")
            retirement = node.get("retirement")
            if status in _RETIRED_STATUS and not isinstance(retirement, dict):
                errors.append(
                    f"[R40 RETIREMENT] node {nid!r} is {status!r} but has no "
                    f"'retirement' tombstone — a node leaving active service must "
                    f"record {{type, reason}} so the retirement is auditable."
                )
            if isinstance(retirement, dict):
                rtype = retirement.get("type")
                sb = retirement.get("superseded_by")
                if rtype in _NEEDS_REPLACEMENT and not sb:
                    errors.append(
                        f"[R40 RETIREMENT] node {nid!r}: retirement.type {rtype!r} "
                        f"requires a 'superseded_by' naming the replacement."
                    )
                if isinstance(sb, str) and sb and sb not in all_ids:
                    # A replacement may legitimately be a loop/subgraph id (not a
                    # sibling node); only flag when it looks like a node ref that
                    # resolves to nothing AND no loop/subgraph id shape is present.
                    if not sb.startswith(("L", "SG-")):
                        errors.append(
                            f"[R40 RETIREMENT] node {nid!r}: retirement.superseded_by "
                            f"{sb!r} references no existing node id."
                        )
            sub = node.get("subgraph")
            if isinstance(sub, dict):
                walk(sub.get("nodes"))

    walk(doc.get("nodes"))
