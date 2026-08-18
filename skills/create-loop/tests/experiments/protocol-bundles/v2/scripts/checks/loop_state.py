"""loop.state.yaml checks (R30): the live pointer file must carry the fields a
fresh session needs to see what is active and who holds which node."""
from __future__ import annotations

from typing import Any

LOOP_STATE_REQUIRED = (
    "loop_id", "plan_id", "plan_version", "phase", "active_node", "ready_set",
    "lease_index", "event_log_ref", "checkpoint_ref", "updated_at",
)


def validate_loop_state(doc: Any, errors: list[str]) -> None:
    if not isinstance(doc, dict):
        errors.append("[R30 BAD-LOOP-STATE] loop.state: document is not a mapping")
        return
    for field in LOOP_STATE_REQUIRED:
        if field not in doc:
            errors.append(f"[R30 BAD-LOOP-STATE] loop.state: missing required field {field!r}")
    li = doc.get("lease_index")
    if "lease_index" in doc and not isinstance(li, list):
        errors.append("[R30 BAD-LOOP-STATE] loop.state: lease_index must be a list")
    elif isinstance(li, list):
        for idx, lease in enumerate(li):
            if not isinstance(lease, dict) or not {"node_id", "owner_id", "lease_expires_at"} <= set(lease):
                errors.append(
                    f"[R30 BAD-LOOP-STATE] loop.state: lease_index[{idx}] must have "
                    f"node_id, owner_id, lease_expires_at"
                )
