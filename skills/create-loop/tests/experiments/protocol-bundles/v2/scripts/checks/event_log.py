"""Replay-safety checks for the v1 append-only event log."""
from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from checks import (
    EVENT_EFFECT_KINDS,
    EVENT_KINDS,
    EVENT_TRANSITION_REQUIRED,
    LEGAL_EVENT_TRANSITIONS,
    MUTATION_TYPES,
    NODE_STATUSES,
    POST_EFFECT_OUTCOMES,
)


EVENT_ALLOWED_FIELDS: frozenset[str] = frozenset({
    "seq", "node_id", "ts", "kind", "from_status", "to_status", "phase",
    "intent", "idempotency_key", "effect_id", "attempt_id", "outcome",
    "result_hash", "mutation_type", "reason", "evidence_refs",
    "failed_entry_id", "overriding_entry_id",
})
TRANSITION_EVENT_KINDS: frozenset[str] = frozenset({
    "pre_effect", "post_effect", "reopen",
})
RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def _is_nullable_string(value: Any) -> bool:
    return value is None or isinstance(value, str)


def _validate_rfc3339(value: Any, label: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value:
        errors.append(f"[R24 EVENTLOG-FIELD] {label} must be a non-empty RFC 3339 timestamp")
        return None
    if not RFC3339_RE.fullmatch(value):
        errors.append(f"[R24 EVENTLOG-FIELD] {label} must be a valid RFC 3339 timestamp")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"[R24 EVENTLOG-FIELD] {label} must be a valid RFC 3339 timestamp")
        return None
    if parsed.tzinfo is None:
        errors.append(f"[R24 EVENTLOG-FIELD] {label} must include a timezone")
        return None
    return parsed


def _validate_entry_shape(entry: dict[str, Any], idx: int, errors: list[str]) -> None:
    scope = f"event_log entries[{idx}]"
    unexpected = sorted(set(entry) - EVENT_ALLOWED_FIELDS)
    if unexpected:
        errors.append(
            f"[R24 EVENTLOG-FIELD] {scope}: unexpected field(s) {unexpected!r}; "
            "event records use the exact event_log schema field set"
        )

    _validate_rfc3339(entry.get("ts"), f"{scope}.ts", errors)
    phase = entry.get("phase")
    if phase is not None and (
        not isinstance(phase, int) or isinstance(phase, bool) or phase < 0
    ):
        errors.append(f"[R24 EVENTLOG-FIELD] {scope}.phase must be null or a non-negative integer")
    for field in ("intent", "idempotency_key", "result_hash", "reason"):
        if field in entry and not _is_nullable_string(entry.get(field)):
            errors.append(f"[R24 EVENTLOG-FIELD] {scope}.{field} must be a string or null")
    if "outcome" in entry and entry.get("outcome") not in POST_EFFECT_OUTCOMES | {None}:
        errors.append(f"[R24 EVENTLOG-FIELD] {scope}.outcome must be ok, fail, or null")
    if "mutation_type" in entry and entry.get("mutation_type") not in MUTATION_TYPES | {None}:
        errors.append(
            f"[R24 EVENTLOG-FIELD] {scope}.mutation_type must be a known mutation type or null"
        )
    for field in ("effect_id", "attempt_id"):
        if field in entry and not (isinstance(entry.get(field), str) and entry.get(field)):
            errors.append(f"[R24 EVENTLOG-FIELD] {scope}.{field} must be a non-empty string")
    for field in ("failed_entry_id", "overriding_entry_id"):
        if field in entry and not isinstance(entry.get(field), str):
            errors.append(f"[R24 EVENTLOG-FIELD] {scope}.{field} must be a string")
    if "evidence_refs" in entry:
        refs = entry.get("evidence_refs")
        if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
            errors.append(
                f"[R24 EVENTLOG-FIELD] {scope}.evidence_refs must be an array of strings"
            )

def _entries(doc: Any, errors: list[str]) -> list[Any] | None:
    if isinstance(doc, list):
        return doc
    if not isinstance(doc, dict):
        errors.append("[R24 EVENTLOG-SEQ] event_log: document is not a mapping or JSONL entry list")
        return None
    unexpected = sorted(set(doc) - {"schema_version", "entries"})
    if unexpected:
        errors.append(
            f"[R24 EVENTLOG-FIELD] event_log: unexpected field(s) {unexpected!r}; "
            "wrapper records use only schema_version and entries"
        )
    if not isinstance(doc.get("schema_version"), str):
        errors.append("[R24 EVENTLOG-FIELD] event_log.schema_version must be a string")
    entries = doc.get("entries")
    if not isinstance(entries, list):
        errors.append("[R24 EVENTLOG-SEQ] event_log: entries must be a list")
        return None
    return entries


def validate_event_log(
    doc: Any,
    errors: list[str],
    *,
    node_ids: set[str] | None = None,
) -> None:
    entries = _entries(doc, errors)
    if entries is None:
        return

    prev = None
    prior_status: dict[str, str] = {}
    for idx, e in enumerate(entries):
        if not isinstance(e, dict):
            errors.append(f"[R24 EVENTLOG-SEQ] event_log entries[{idx}] is not an object")
            continue
        _validate_entry_shape(e, idx, errors)
        seq = e.get("seq")
        if not isinstance(seq, int) or isinstance(seq, bool):
            errors.append(f"[R24 EVENTLOG-SEQ] event_log entries[{idx}]: seq {seq!r} must be an integer")
        elif seq < 0:
            errors.append(
                f"[R24 EVENTLOG-SEQ] event_log entries[{idx}]: seq {seq} must be "
                "a non-negative integer"
            )
        elif prev is not None and seq <= prev:
            errors.append(
                f"[R24 EVENTLOG-SEQ] event_log entries[{idx}]: seq {seq} is not "
                f"strictly greater than the previous seq {prev} (log must be "
                f"strictly monotonic)"
            )
        else:
            prev = seq
        kind = e.get("kind")
        if kind not in EVENT_KINDS:
            errors.append(
                f"[R31 BAD-EVENT-KIND] event_log entries[{idx}]: kind {kind!r} is not "
                f"one of {sorted(EVENT_KINDS)}"
            )
        node_id = e.get("node_id")
        if not isinstance(node_id, str) or not node_id:
            errors.append(f"[R24 EVENTLOG-FIELD] event_log entries[{idx}]: node_id must be a non-empty string")
        if node_ids is not None and node_id not in node_ids:
            errors.append(
                f"[R24 EVENT-NODE-UNKNOWN] event_log entries[{idx}]: node_id "
                f"{node_id!r} does not exist in the current plan (including nested nodes)"
            )
        transition_fields = [field for field in EVENT_TRANSITION_REQUIRED if field in e]
        if transition_fields and kind not in TRANSITION_EVENT_KINDS:
            errors.append(
                f"[R24 ILLEGAL-TRANSITION] event_log entries[{idx}]: {kind!r} "
                "records cannot carry from_status or to_status; only pre_effect, "
                "post_effect, and reopen records can change control state"
            )
        if kind in TRANSITION_EVENT_KINDS:
            for field in EVENT_TRANSITION_REQUIRED:
                status = e.get(field)
                if status not in NODE_STATUSES:
                    errors.append(
                        f"[EVENT-TRANSITION-PAIR] event_log entries[{idx}]: "
                        f"{kind!r} entry with transition data must carry both "
                        f"from_status and to_status as non-null members of the "
                        f"15-status node enum; {field} is {status!r}"
                    )
            from_status = e.get("from_status")
            to_status = e.get("to_status")
            if from_status in NODE_STATUSES and to_status in NODE_STATUSES:
                if kind == "reopen":
                    if (from_status, to_status) != ("completed", "verifying"):
                        errors.append(
                            f"[R24 ILLEGAL-REOPEN] event_log entries[{idx}]: reopen "
                            "must transition completed -> verifying"
                        )
                    refs = e.get("evidence_refs")
                    if not isinstance(refs, list) or not refs or not all(isinstance(ref, str) and ref for ref in refs):
                        errors.append(
                            f"[R24 ILLEGAL-REOPEN] event_log entries[{idx}]: reopen "
                            "must cite non-empty counterevidence in evidence_refs"
                        )
                elif to_status not in LEGAL_EVENT_TRANSITIONS.get(from_status, frozenset()):
                    errors.append(
                        f"[R24 ILLEGAL-TRANSITION] event_log entries[{idx}]: "
                        f"{from_status!r} -> {to_status!r} is not a legal event-log "
                        "transition (verifying -> completed is ledger-derived)"
                    )
                if isinstance(node_id, str):
                    expected = prior_status.get(node_id)
                    ledger_reopen_bridge = (
                        kind == "reopen" and expected == "verifying"
                        and from_status == "completed"
                    )
                    if expected is not None and from_status != expected and not ledger_reopen_bridge:
                        errors.append(
                            f"[R24 TRANSITION-DISCONTINUITY] event_log entries[{idx}]: "
                            f"node {node_id!r} last ended at {expected!r}, but this "
                            f"entry starts at {from_status!r}"
                        )
                    prior_status[node_id] = to_status
        if kind == "post_effect":
            outcome = e.get("outcome")
            if outcome not in POST_EFFECT_OUTCOMES:
                errors.append(
                    f"[R23 EFFECT-OUTCOME] event_log entries[{idx}]: post_effect "
                    f"outcome must be one of {sorted(POST_EFFECT_OUTCOMES)}; got "
                    f"{outcome!r}"
                )
            elif outcome == "fail" and e.get("to_status") in {"verifying", "completed"}:
                errors.append(
                    f"[R23 EFFECT-OUTCOME] event_log entries[{idx}]: a failed "
                    "post_effect cannot advance to verifying or completed; record "
                    "the applicable waiting/blocked/cancelled failure path instead"
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
            if not isinstance(e.get("reason"), str) or not e.get("reason"):
                errors.append(
                    f"[R39 UNTRACKED-MUTATION] event_log entries[{idx}]: a mutation "
                    "event requires a non-empty reason"
                )
            refs = e.get("evidence_refs")
            if not isinstance(refs, list) or not refs or not all(
                isinstance(ref, str) and ref for ref in refs
            ):
                errors.append(
                    f"[R39 UNTRACKED-MUTATION] event_log entries[{idx}]: a mutation "
                    "event requires non-empty evidence_refs"
                )

    _validate_effect_pairs(entries, errors)


def _effect_key(entry: dict[str, Any]) -> tuple[Any, Any] | None:
    effect_id = entry.get("effect_id")
    attempt_id = entry.get("attempt_id")
    if effect_id is None and attempt_id is None:
        return None
    if not (isinstance(effect_id, str) and effect_id and isinstance(attempt_id, str) and attempt_id):
        return ("__invalid__", id(entry))
    return effect_id, attempt_id


def _validate_effect_pairs(entries: list[Any], errors: list[str]) -> None:
    open_exact: dict[tuple[Any, Any], tuple[int, dict[str, Any]]] = {}
    open_legacy: dict[str, tuple[int, dict[str, Any]]] = {}
    seen_exact: set[tuple[Any, Any]] = set()
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict) or entry.get("kind") not in EVENT_EFFECT_KINDS:
            continue
        node_id = entry.get("node_id")
        key = _effect_key(entry)
        if key is not None and key[0] == "__invalid__":
            errors.append(
                f"[R23 EFFECT-IDENTITY] event_log entries[{idx}]: effect_id and "
                "attempt_id must either both be non-empty strings or both be absent"
            )
            continue
        if entry.get("kind") == "pre_effect":
            if key is not None:
                if key in seen_exact or key in open_exact:
                    errors.append(
                        f"[R23 EFFECT-IDENTITY] event_log entries[{idx}]: duplicate "
                        f"effect identity {key!r}"
                    )
                open_exact[key] = (idx, entry)
                seen_exact.add(key)
            else:
                if not isinstance(entry.get("idempotency_key"), str) or not entry.get("idempotency_key"):
                    errors.append(
                        f"[R23 IN-DOUBT-NONIDEMPOTENT] event_log entries[{idx}]: "
                        "legacy pre_effect without effect_id/attempt_id requires a "
                        "non-empty idempotency_key"
                    )
                if isinstance(node_id, str) and node_id in open_legacy:
                    errors.append(
                        f"[R23 LEGACY-EFFECT-AMBIGUOUS] event_log entries[{idx}]: "
                        f"node {node_id!r} starts another legacy effect before the "
                        "prior one is closed"
                    )
                if isinstance(node_id, str):
                    open_legacy[node_id] = (idx, entry)
            continue

        if key is not None:
            pre = open_exact.pop(key, None)
            if pre is None:
                errors.append(
                    f"[R23 EFFECT-PAIR] event_log entries[{idx}]: post_effect "
                    f"identity {key!r} has no matching earlier pre_effect"
                )
            elif pre[1].get("node_id") != node_id:
                errors.append(
                    f"[R23 EFFECT-PAIR] event_log entries[{idx}]: post_effect "
                    f"node {node_id!r} differs from matching pre_effect node "
                    f"{pre[1].get('node_id')!r}"
                )
        else:
            pre = open_legacy.pop(node_id, None) if isinstance(node_id, str) else None
            if pre is None:
                errors.append(
                    f"[R23 LEGACY-EFFECT-AMBIGUOUS] event_log entries[{idx}]: "
                    "legacy post_effect has no unambiguous earlier pre_effect for "
                    f"node {node_id!r}; add effect_id and attempt_id"
                )
            else:
                adjacent = pre[0] == idx - 1
                same_idempotency = (
                    isinstance(pre[1].get("idempotency_key"), str)
                    and pre[1].get("idempotency_key")
                    and entry.get("idempotency_key") == pre[1].get("idempotency_key")
                )
                continuous = pre[1].get("to_status") == entry.get("from_status")
                if not (adjacent and same_idempotency and continuous):
                    errors.append(
                        f"[R23 LEGACY-EFFECT-AMBIGUOUS] event_log entries[{idx}]: "
                        "legacy effect pairing requires adjacent records, the same "
                        "idempotency_key, and a continuous status boundary; add "
                        "effect_id and attempt_id"
                    )

    for key, (idx, entry) in open_exact.items():
        if not entry.get("idempotency_key"):
            errors.append(
                f"[R23 IN-DOUBT-NONIDEMPOTENT] event_log entries[{idx}]: "
                f"unmatched pre_effect {key!r} has no idempotency_key"
            )
    for node_id, (idx, entry) in open_legacy.items():
        if not entry.get("idempotency_key"):
            errors.append(
                f"[R23 IN-DOUBT-NONIDEMPOTENT] event_log entries[{idx}]: "
                f"unmatched legacy pre_effect for node {node_id!r} is unsafe"
            )
