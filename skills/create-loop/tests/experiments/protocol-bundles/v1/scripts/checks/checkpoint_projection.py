"""Canonical checkpoint projection and R49 snapshot-consistency check."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from checks import NODE_STATUSES


@dataclass(frozen=True, slots=True)
class CheckpointProjection:
    node_states: dict[str, str]
    ready_set: tuple[str, ...]
    last_completed: tuple[str, ...]
    phase: int | None


def project_checkpoint(
    plan: dict[str, Any],
    event_entries: list[dict[str, Any]],
    ledger: dict[str, Any],
) -> CheckpointProjection:
    """Compute the state_model.md canonical checkpoint projection."""
    nodes = {
        node["id"]: node
        for node in plan.get("nodes", [])
        if isinstance(node, dict)
        and isinstance(node.get("id"), str)
        and node.get("status") in NODE_STATUSES
    }
    node_states = {node_id: node["status"] for node_id, node in nodes.items()}
    ordered_events = sorted(
        event_entries,
        key=lambda event: event.get("seq") if isinstance(event.get("seq"), int) else -1,
    )
    phase = None
    for event in ordered_events:
        node_id = event.get("node_id")
        to_status = event.get("to_status")
        if (
            event.get("kind") in ("pre_effect", "post_effect")
            and node_id in node_states
            and to_status in NODE_STATUSES
        ):
            node_states[node_id] = to_status
        if isinstance(event.get("phase"), int):
            phase = event["phase"]

    latest_active = {}
    for entry in ledger.get("entries", []):
        if (
            isinstance(entry, dict)
            and isinstance(entry.get("node_id"), str)
            and entry.get("status", "active") == "active"
        ):
            latest_active[entry["node_id"]] = entry

    last_completed = []
    for node_id, status in node_states.items():
        if status != "verifying":
            continue
        entry = latest_active.get(node_id)
        if not isinstance(entry, dict):
            continue
        verdict = entry.get("verdict")
        completion_authorized = (
            verdict == "pass"
            and (
                entry.get("assurance") == "external"
                or entry.get("gate_kind") == "human_approval"
            )
        )
        if completion_authorized:
            node_states[node_id] = "completed"
            last_completed.append(node_id)
        elif verdict in ("fail", "inconclusive"):
            node_states[node_id] = "verification_failed"

    ready_set = tuple(
        node_id
        for node_id, node in nodes.items()
        if node_states[node_id] == "pending"
        and all(node_states.get(required) == "completed" for required in node.get("requires", []))
    )
    return CheckpointProjection(
        node_states=node_states,
        ready_set=ready_set,
        last_completed=tuple(last_completed),
        phase=phase,
    )


def check_checkpoint_projection(
    plan: Any,
    event_entries: Any,
    ledger: Any,
    checkpoint: Any,
    errors: list[str],
) -> None:
    """R49 compares projected and recorded node statuses, without judging them."""
    if not all(isinstance(value, dict) for value in (plan, ledger, checkpoint)):
        return
    if not isinstance(event_entries, list):
        return
    recorded = checkpoint.get("node_states")
    if not isinstance(recorded, dict):
        return
    projection = project_checkpoint(plan, event_entries, ledger)
    for node_id, projected_status in projection.node_states.items():
        recorded_status = recorded.get(node_id)
        if recorded_status != projected_status:
            errors.append(
                f"[R49 CHECKPOINT-PROJECTION-MISMATCH] node {node_id!r}: projected "
                f"status {projected_status!r} disagrees with checkpoint.node_states "
                f"recorded status {recorded_status!r}; this establishes a replayed-"
                "projection/recorded-snapshot consistency disagreement only and does "
                "not license any conclusion that the loop is broken, work is "
                "incomplete, evidence is inadequate, or the node is or is not done"
            )
