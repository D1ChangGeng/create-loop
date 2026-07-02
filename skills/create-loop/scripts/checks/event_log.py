"""event_log checks (R23, R24). The event log is the primary source of truth;
these rules keep it replayable: R24 requires strictly monotonic seq; R23 rejects
an in-doubt non-idempotent transaction (a pre_effect with no matching post_effect
and no idempotency_key, which recovery cannot safely replay).
"""
from __future__ import annotations

from typing import Any

EVENT_KINDS = frozenset({"pre_effect", "post_effect", "note", "mutation"})
MUTATION_TYPES = frozenset({
    "add_action", "add_subgraph", "promote_subgraph_to_subloop", "add_child_loop",
    "update_dependency", "split_node", "merge_nodes", "cancel_node",
    "deprecate_node", "update_gate", "update_artifact_contract",
    "update_assumption", "update_risk",
})


def validate_event_log(doc: Any, errors: list[str]) -> None:
    if not isinstance(doc, dict):
        errors.append("[R24 EVENTLOG-SEQ] event_log: document is not a mapping")
        return
    entries = doc.get("entries")
    if not isinstance(entries, list):
        errors.append("[R24 EVENTLOG-SEQ] event_log: entries must be a list")
        return

    prev = None
    for idx, e in enumerate(entries):
        if not isinstance(e, dict):
            errors.append(f"[R24 EVENTLOG-SEQ] event_log entries[{idx}] is not an object")
            continue
        seq = e.get("seq")
        if not isinstance(seq, int) or isinstance(seq, bool):
            errors.append(f"[R24 EVENTLOG-SEQ] event_log entries[{idx}]: seq {seq!r} must be an integer")
        elif prev is not None and seq <= prev:
            errors.append(
                f"[R24 EVENTLOG-SEQ] event_log entries[{idx}]: seq {seq} is not "
                f"strictly greater than the previous seq {prev} (log must be "
                f"strictly monotonic)"
            )
        else:
            prev = seq
        kind = e.get("kind")
        if "kind" in e and kind not in EVENT_KINDS:
            errors.append(
                f"[R31 BAD-EVENT-KIND] event_log entries[{idx}]: kind {kind!r} is not "
                f"one of {sorted(EVENT_KINDS)}"
            )
        if kind == "mutation":
            mtype = e.get("mutation_type")
            if mtype not in MUTATION_TYPES:
                errors.append(
                    f"[R39 UNTRACKED-MUTATION] event_log entries[{idx}]: a mutation "
                    f"event must carry a valid 'mutation_type' (one of "
                    f"{sorted(MUTATION_TYPES)}); got {mtype!r}. Live plan changes must "
                    f"be typed, not untracked edits."
                )
            if not e.get("reason"):
                errors.append(
                    f"[R39 UNTRACKED-MUTATION] event_log entries[{idx}]: a mutation "
                    f"event must carry a non-empty 'reason' — a change without a reason "
                    f"is how a live plan corrupts into scope creep."
                )

    resolved: set[tuple[Any, Any]] = set()
    for e in entries:
        if isinstance(e, dict) and e.get("kind") == "post_effect":
            resolved.add((e.get("node_id"), e.get("seq")))
    post_nodes = {n for (n, _s) in resolved}

    for idx, e in enumerate(entries):
        if not isinstance(e, dict) or e.get("kind") != "pre_effect":
            continue
        node_id = e.get("node_id")
        later_post = any(
            isinstance(p, dict) and p.get("kind") == "post_effect"
            and p.get("node_id") == node_id
            and isinstance(p.get("seq"), int) and isinstance(e.get("seq"), int)
            and p["seq"] > e["seq"]
            for p in entries
        )
        if not later_post and not e.get("idempotency_key"):
            errors.append(
                f"[R23 IN-DOUBT-NONIDEMPOTENT] event_log entries[{idx}] "
                f"(node {node_id!r}, seq {e.get('seq')!r}): a pre_effect with no "
                f"matching post_effect and no idempotency_key is an in-doubt "
                f"transaction — recovery cannot safely replay it. Provide an "
                f"idempotency_key or resolve the effect (add its post_effect)."
            )
