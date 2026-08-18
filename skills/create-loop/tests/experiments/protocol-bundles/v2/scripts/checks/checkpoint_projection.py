"""Canonical checkpoint projection and R49 snapshot-consistency check."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from checks import NODE_STATUSES, POST_EFFECT_OUTCOMES
from checks.provenance import current_evidence_by_node


@dataclass(frozen=True, slots=True)
class CheckpointProjection:
    node_states: dict[str, str]
    ready_set: tuple[str, ...]
    last_completed: tuple[str, ...]
    phase: int | None
    last_event_seq: int


def _recorded_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def project_checkpoint(
    plan: dict[str, Any],
    event_entries: list[dict[str, Any]],
    ledger: dict[str, Any],
) -> CheckpointProjection:
    """Compute the state_model.md canonical checkpoint projection."""
    nodes: dict[str, dict[str, Any]] = {}

    def walk(raw_nodes: Any) -> None:
        if not isinstance(raw_nodes, list):
            return
        for node in raw_nodes:
            if not isinstance(node, dict):
                continue
            node_id = node.get("id")
            if isinstance(node_id, str) and node.get("status") in NODE_STATUSES:
                nodes[node_id] = node
            subgraph = node.get("subgraph")
            if isinstance(subgraph, dict):
                walk(subgraph.get("nodes"))

    walk(plan.get("nodes"))
    node_states = {node_id: node["status"] for node_id, node in nodes.items()}
    ordered_events = sorted(
        event_entries,
        key=lambda event: event.get("seq") if isinstance(event.get("seq"), int) else -1,
    )
    phase = 0
    last_event_seq = 0
    latest_reopen_time: dict[str, datetime | None] = {}
    for event in ordered_events:
        if isinstance(event.get("seq"), int):
            last_event_seq = event["seq"]
        node_id = event.get("node_id")
        to_status = event.get("to_status")
        kind = event.get("kind")
        transition_is_replayable = (
            kind in ("pre_effect", "reopen")
            or (
                kind == "post_effect"
                and event.get("outcome") in POST_EFFECT_OUTCOMES
                and not (
                    event.get("outcome") == "fail"
                    and to_status in {"verifying", "completed"}
                )
            )
        )
        if (
            transition_is_replayable
            and node_id in node_states
            and to_status in NODE_STATUSES
        ):
            node_states[node_id] = to_status
            if kind == "reopen":
                latest_reopen_time[node_id] = _recorded_time(event.get("ts"))
        if isinstance(event.get("phase"), int):
            phase = event["phase"]

    latest_active = current_evidence_by_node(ledger)

    completed_candidates: list[tuple[str, str]] = []
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
        if completion_authorized and node_id in latest_reopen_time:
            evidence_time = _recorded_time(entry.get("recorded"))
            reopen_time = latest_reopen_time[node_id]
            completion_authorized = (
                evidence_time is not None
                and reopen_time is not None
                and evidence_time > reopen_time
            )
        if completion_authorized:
            node_states[node_id] = "completed"
            completed_candidates.append((str(entry.get("recorded", "")), node_id))
        elif verdict in ("fail", "inconclusive"):
            node_states[node_id] = "verification_failed"

    last_completed: tuple[str, ...] = ()
    if completed_candidates:
        latest_recorded = max(recorded for recorded, _node_id in completed_candidates)
        last_completed = tuple(
            node_id for recorded, node_id in completed_candidates
            if recorded == latest_recorded
        )
    ready_set = tuple(
        node_id
        for node_id, node in nodes.items()
        if node_states[node_id] == "pending"
        and all(node_states.get(required) == "completed" for required in node.get("requires", []))
    )
    return CheckpointProjection(
        node_states=node_states,
        ready_set=ready_set,
        last_completed=last_completed,
        phase=phase,
        last_event_seq=last_event_seq,
    )


def check_checkpoint_projection(
    plan: Any,
    event_entries: Any,
    ledger: Any,
    checkpoint: Any,
    errors: list[str],
) -> None:
    """R49 compares every reconstructible checkpoint field."""
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
    recorded_ids = set(recorded)
    projected_ids = set(projection.node_states)
    if recorded_ids != projected_ids:
        errors.append(
            f"[R49 CHECKPOINT-PROJECTION-MISMATCH] checkpoint.node_states keys "
            f"{sorted(recorded_ids)!r} disagree with recursive plan node set "
            f"{sorted(projected_ids)!r}"
        )
    comparisons = (
        ("ready_set", tuple(checkpoint.get("ready_set", [])), projection.ready_set),
        ("last_completed", tuple(checkpoint.get("last_completed", [])), projection.last_completed),
        ("phase", checkpoint.get("phase"), projection.phase),
        ("last_event_seq", checkpoint.get("last_event_seq"), projection.last_event_seq),
    )
    for field, recorded_value, projected_value in comparisons:
        if recorded_value != projected_value:
            errors.append(
                f"[R49 CHECKPOINT-PROJECTION-MISMATCH] checkpoint.{field} "
                f"{recorded_value!r} disagrees with projected {projected_value!r}"
            )
