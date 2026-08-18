"""loops.index / _loops INDEX checks: mutually-exclusive shape + entries (R16),
and INDEX-to-directory reconciliation (R37)."""
from __future__ import annotations

import os
from typing import Any

from checks import INDEX_CHILD_ENTRY_REQUIRED, INDEX_LOOP_ENTRY_REQUIRED, NODE_STATUSES


def validate_index_reconciliation(doc: Any, root: str, errors: list[str]) -> None:
    """R37: every path listed in the INDEX must exist on disk under root."""
    if not isinstance(doc, dict):
        return
    entries = doc.get("loops") if "loops" in doc else doc.get("children")
    if not isinstance(entries, list):
        return
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if isinstance(path, str) and not os.path.exists(os.path.join(root, path)):
            errors.append(
                f"[R37 INDEX-RECONCILE] INDEX entry[{idx}] ({entry.get('loop_id')!r}): "
                f"path {path!r} does not exist under {root!r} — the index and the "
                f"loop directory tree have drifted."
            )


def validate_loops_index(doc: Any, errors: list[str]) -> None:
    """Validate a loops.index / _loops INDEX (R16)."""
    if not isinstance(doc, dict):
        errors.append("[R16 BAD INDEX] loops.index: document is not a mapping")
        return
    has_loops = "loops" in doc
    has_children = "children" in doc

    if has_loops and has_children:
        errors.append(
            "[R16 BAD INDEX] loops.index: has BOTH 'loops' and 'children' keys; "
            "a global INDEX carries 'loops' and a local _loops/INDEX carries "
            "'children' — the two shapes are mutually exclusive (oneOf)"
        )
        return
    if not has_loops and not has_children:
        errors.append(
            "[R16 BAD INDEX] loops.index: has NEITHER 'loops' (global) nor "
            "'children' (local) key; exactly one is required"
        )
        return

    if has_loops:
        check_index_entries(
            doc.get("loops"), "loops", INDEX_LOOP_ENTRY_REQUIRED, errors
        )
    else:
        check_index_entries(
            doc.get("children"), "children", INDEX_CHILD_ENTRY_REQUIRED, errors
        )


def check_index_entries(
    entries: Any, key: str, required: tuple[str, ...], errors: list[str]
) -> None:
    """Validate one INDEX entry list's field sets + status enum."""
    if not isinstance(entries, list):
        errors.append(f"[R16 BAD INDEX] loops.index: {key!r} must be a list")
        return
    for idx, entry in enumerate(entries):
        scope = f"loops.index {key}[{idx}]"
        if not isinstance(entry, dict):
            errors.append(f"[R16 BAD INDEX] {scope}: entry must be an object")
            continue
        for field in required:
            if field not in entry:
                errors.append(
                    f"[R16 BAD INDEX] {scope}: missing required field {field!r}"
                )
        status = entry.get("status")
        if "status" in entry and status not in NODE_STATUSES:
            errors.append(
                f"[R16 BAD INDEX] {scope}: status {status!r} is not one of the 15 "
                f"node statuses"
            )
