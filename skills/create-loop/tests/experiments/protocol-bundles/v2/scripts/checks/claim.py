"""claim file checks (R21): a per-node claim/lease must carry the fields that
make single-flight and lease reconciliation work (owner, acquired/heartbeat/
expiry timestamps, phase). delegated_to is optional (set when a node is
delegated to a live child loop).
"""
from __future__ import annotations

import re
from typing import Any

CLAIM_REQUIRED = (
    "node_id", "owner_id", "acquired_at", "lease_expires_at", "phase", "heartbeat_at",
)
_LOOP_ID_RE = re.compile(r"^L\d{3}(\.\d{2})*$")


def validate_claim(doc: Any, errors: list[str]) -> None:
    if not isinstance(doc, dict):
        errors.append("[R21 BAD-CLAIM] claim: document is not a mapping")
        return
    for field in CLAIM_REQUIRED:
        if field not in doc:
            errors.append(f"[R21 BAD-CLAIM] claim: missing required field {field!r}")
    phase = doc.get("phase")
    if "phase" in doc and not (isinstance(phase, int) and not isinstance(phase, bool) and phase >= 0):
        errors.append(f"[R21 BAD-CLAIM] claim: phase {phase!r} must be a non-negative integer")
    delegated = doc.get("delegated_to")
    if delegated is not None and not (isinstance(delegated, str) and _LOOP_ID_RE.match(delegated)):
        errors.append(
            f"[R21 BAD-CLAIM] claim: delegated_to {delegated!r} must be null or a "
            f"loop id L<seq>[.<seq>]"
        )
