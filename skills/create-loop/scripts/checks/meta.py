"""loop.meta.yaml checks: loop_id (R9), slug (R10), required fields (R11),
type enum (R12), child_loop parent relation (R17)."""
from __future__ import annotations

from typing import Any

from checks import (
    LOOP_ID_RE,
    LOOP_META_REQUIRED,
    LOOP_META_TYPES,
    NODE_STATUSES,
    PARENT_REF_REQUIRED,
    SLUG_MAX_LEN,
    SLUG_RE,
)


def validate_loop_meta(doc: Any, errors: list[str]) -> None:
    """Validate a loop.meta.yaml (R9, R10, R11, R12, R17)."""
    if not isinstance(doc, dict):
        errors.append("[R11 MISSING REQUIRED FIELD] loop.meta: document is not a mapping")
        return
    for field in LOOP_META_REQUIRED:
        if field not in doc:
            errors.append(
                f"[R11 MISSING REQUIRED FIELD] loop.meta: missing required field "
                f"{field!r}"
            )

    loop_id = doc.get("loop_id")
    if "loop_id" in doc and not (isinstance(loop_id, str) and LOOP_ID_RE.match(loop_id)):
        errors.append(
            f"[R9 BAD loop_id] loop.meta: loop_id {loop_id!r} matches neither "
            f"L<seq> (e.g. L001) nor L<seq>.<seq> (e.g. L001.02)"
        )

    slug = doc.get("slug")
    if "slug" in doc:
        if not isinstance(slug, str) or not SLUG_RE.match(slug) or len(slug) > SLUG_MAX_LEN:
            errors.append(
                f"[R10 BAD slug] loop.meta: slug {slug!r} is not lowercase kebab-case "
                f"of <= {SLUG_MAX_LEN} chars (no uppercase/underscore/space)"
            )

    meta_type = doc.get("type")
    if "type" in doc and meta_type not in LOOP_META_TYPES:
        errors.append(
            f"[R12 BAD type] loop.meta: type {meta_type!r} is not one of "
            f"{sorted(LOOP_META_TYPES)}"
        )

    status = doc.get("status")
    if "status" in doc and status not in NODE_STATUSES:
        errors.append(
            f"[R4 BAD STATUS] loop.meta: status {status!r} is not one of the 15 "
            f"node statuses"
        )

    parent = doc.get("parent")
    if meta_type == "child_loop":
        if not isinstance(parent, dict):
            errors.append(
                f"[R17 CHILD_LOOP NO PARENT] loop.meta: type is child_loop but "
                f"parent is {parent!r}; a child_loop requires a parent object "
                f"({list(PARENT_REF_REQUIRED)})"
            )
        else:
            for field in PARENT_REF_REQUIRED:
                if field not in parent:
                    errors.append(
                        f"[R17 CHILD_LOOP NO PARENT] loop.meta: parent object "
                        f"missing required field {field!r}"
                    )
