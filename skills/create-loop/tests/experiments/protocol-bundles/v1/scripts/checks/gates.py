"""Gate checks: gate kind enum (R7) and missing-gate on non-trivial nodes (R3)."""
from __future__ import annotations

from typing import Any

from checks import GATE_KINDS, GATE_REQUIRED_KINDS


def check_gate(gate: Any, scope: str, errors: list[str]) -> None:
    """Validate a gate object's kind enum (R7). Skips when gate is null/absent."""
    if gate is None:
        return
    if not isinstance(gate, dict):
        errors.append(f"[R7 BAD GATE KIND] {scope}: gate must be an object or null")
        return
    kind = gate.get("kind")
    if kind not in GATE_KINDS:
        errors.append(
            f"[R7 BAD GATE KIND] {scope}: gate.kind {kind!r} is not one of the 8 "
            f"gate kinds ({sorted(GATE_KINDS)})"
        )


def check_gate_required(kind: Any, gate: Any, label: str, errors: list[str]) -> None:
    """R3: a non-trivial node (by kind) must carry a gate; null is trivial-only.
    R34: an `approval` node must carry a `human_approval` gate — it is the
    control point that suspends on waiting_user and records the user's verdict."""
    if kind == "approval":
        gate_kind = gate.get("kind") if isinstance(gate, dict) else None
        if gate_kind != "human_approval":
            errors.append(
                f"[R34 APPROVAL-GATE-REQUIRED] {label}: an 'approval' node must have "
                f"a gate with kind 'human_approval' (found {gate_kind!r}); without it "
                f"the approval cannot suspend on waiting_user or record a user verdict"
            )
        return
    if kind in GATE_REQUIRED_KINDS and gate is None:
        errors.append(
            f"[R3 MISSING EVIDENCE GATE] {label}: non-trivial node of kind "
            f"{kind!r} has gate: null; only trivial nodes may omit a gate"
        )
