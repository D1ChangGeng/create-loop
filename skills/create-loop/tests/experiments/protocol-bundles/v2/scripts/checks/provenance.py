from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any

_WS = re.compile(r"\s+")
_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def _norm_hash(text: Any) -> str:
    normalized = _WS.sub(" ", str(text)).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def check_plan_provenance(doc: Any, errors: list[str]) -> None:
    if not isinstance(doc, dict):
        return
    history = doc.get("plan_history")
    if not isinstance(history, list) or not history:
        errors.append(
            "[R27 BAD plan_history] plan.plan_history must be a non-empty list "
            "(at least one entry describing the current version)"
        )
        return

    for idx, entry in enumerate(history):
        if not isinstance(entry, dict):
            errors.append(f"[R27 BAD plan_history] plan_history[{idx}] is not an object")
            continue
        for field in ("plan_version", "reason", "superseded_at", "goal_hash", "true_intent_hash"):
            if field not in entry:
                errors.append(
                    f"[R27 BAD plan_history] plan_history[{idx}]: missing required "
                    f"field {field!r}"
                )

    versions = [e.get("plan_version") for e in history if isinstance(e, dict)]
    if versions != sorted(v for v in versions if isinstance(v, int)) or len(set(versions)) != len(versions):
        errors.append(
            "[R27 BAD plan_history] plan_history plan_version values must be unique "
            "and strictly increasing"
        )

    latest = history[-1]
    if not isinstance(latest, dict):
        return

    if latest.get("plan_version") != doc.get("plan_version"):
        errors.append(
            f"[R27 BAD plan_history] latest plan_history.plan_version "
            f"{latest.get('plan_version')!r} != plan.plan_version "
            f"{doc.get('plan_version')!r}"
        )

    expected_goal = _norm_hash(doc.get("goal", ""))
    expected_intent = _norm_hash(doc.get("true_intent", ""))
    if latest.get("goal_hash") != expected_goal or latest.get("true_intent_hash") != expected_intent:
        errors.append(
            "[R26 UNAPPROVED-GOAL-CHANGE] the current goal/true_intent does not "
            "match the latest plan_history hashes. A goal change must be recorded "
            "as a new plan_history entry (with an approved human_approval); a hash "
            "mismatch means the goal was mutated without an approved, provenanced "
            "version bump."
        )


def check_evidence_identity(ledger: Any, errors: list[str]) -> None:
    """Validate immutable evidence identities and append-only relations."""
    if not isinstance(ledger, dict):
        return
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        return
    ids: set[str] = set()
    by_id: dict[str, dict[str, Any]] = {}
    entry_index: dict[str, int] = {}
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        entry_id = entry.get("entry_id")
        if not isinstance(entry_id, str) or not entry_id:
            continue
        if entry_id in ids:
            errors.append(
                f"[R38 EVIDENCE-IDENTITY] ledger entry[{idx}]: duplicate entry_id "
                f"{entry_id!r}; evidence identities are immutable and unique"
            )
        ids.add(entry_id)
        by_id[entry_id] = entry
        entry_index[entry_id] = idx

    def is_strictly_newer(source: Any, target: Any, label: str) -> bool:
        valid = True
        if source not in entry_index or target not in entry_index:
            return valid
        if entry_index[source] <= entry_index[target]:
            errors.append(
                f"[R38 EVIDENCE-RELATION] {label} source entry {source!r} must "
                f"appear after target entry {target!r}; append-only relations "
                "cannot make older evidence replace newer evidence"
            )
            valid = False
        source_recorded = by_id[source].get("recorded")
        target_recorded = by_id[target].get("recorded")
        try:
            source_time = datetime.fromisoformat(source_recorded.replace("Z", "+00:00"))
            target_time = datetime.fromisoformat(target_recorded.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            errors.append(
                f"[R38 EVIDENCE-RELATION] {label} requires valid RFC 3339 "
                "recorded timestamps on both source and target entries"
            )
            return False
        if source_time.tzinfo is None or target_time.tzinfo is None or source_time <= target_time:
            errors.append(
                f"[R38 EVIDENCE-RELATION] {label} source entry "
                f"{source!r}.recorded must be strictly later than target entry "
                f"{target!r}.recorded"
            )
            valid = False
        return valid

    for entry in entries:
        source = entry.get("entry_id")
        status = entry.get("status", "active")
        if status != "active":
            errors.append(
                f"[R38 EVIDENCE-LIFECYCLE] entry {source!r} carries legacy "
                f"status {status!r}; append-only evidence entries must remain "
                "active observations and currentness may change only through a "
                "newer explicit lifecycle relation"
            )
        for field in ("supersedes", "overrides_entry_id"):
            target = entry.get(field)
            if not isinstance(target, str):
                continue
            if target not in by_id:
                errors.append(
                    f"[R38 EVIDENCE-RELATION] entry {source!r} {field} references "
                    f"missing entry {target!r}"
                )
                continue
            if by_id[target].get("node_id") != entry.get("node_id"):
                errors.append(
                    f"[R38 EVIDENCE-RELATION] entry {source!r} {field} crosses "
                    "node boundaries"
                )
            is_strictly_newer(source, target, f"entry {source!r} {field}")

    relations = ledger.get("relations", [])
    if not isinstance(relations, list):
        errors.append("[R38 EVIDENCE-RELATION] ledger.relations must be a list when present")
        return
    relation_ids: set[str] = set()
    graph: dict[str, list[str]] = {}
    prior_challenge_entries: set[str] = set()
    for idx, relation in enumerate(relations):
        if not isinstance(relation, dict):
            errors.append(f"[R38 EVIDENCE-RELATION] ledger.relations[{idx}] is not an object")
            continue
        relation_id = relation.get("relation_id")
        if not isinstance(relation_id, str) or not relation_id:
            errors.append(f"[R38 EVIDENCE-RELATION] ledger.relations[{idx}] has no relation_id")
        elif relation_id in relation_ids:
            errors.append(f"[R38 EVIDENCE-RELATION] duplicate relation_id {relation_id!r}")
        else:
            relation_ids.add(relation_id)
        source = relation.get("source_entry_id")
        target = relation.get("target_entry_id")
        kind = relation.get("relation")
        if source not in by_id or target not in by_id:
            errors.append(
                f"[R38 EVIDENCE-RELATION] ledger.relations[{idx}] must reference "
                "existing source_entry_id and target_entry_id"
            )
            continue
        if source == target:
            errors.append(f"[R38 EVIDENCE-RELATION] ledger.relations[{idx}] is self-referential")
        is_strictly_newer(source, target, f"ledger.relations[{idx}]")
        if kind not in {"supersedes", "invalidates", "challenges", "confirms"}:
            errors.append(
                f"[R38 EVIDENCE-RELATION] ledger.relations[{idx}].relation {kind!r} "
                "is not supersedes/invalidates/challenges/confirms"
            )
        if by_id[source].get("node_id") != by_id[target].get("node_id"):
            errors.append(
                f"[R38 EVIDENCE-RELATION] ledger.relations[{idx}] crosses nodes; "
                "evidence lifecycle relations must stay within one node"
            )
        if (
            kind in {"invalidates", "challenges"}
            and by_id[source].get("verdict") not in {"fail", "inconclusive"}
        ):
            errors.append(
                f"[R38 EVIDENCE-RELATION] ledger.relations[{idx}] {kind} source "
                "must have verdict fail or inconclusive"
            )
        if kind == "confirms" and by_id[source].get("verdict") != "pass":
            errors.append(
                f"[R38 EVIDENCE-RELATION] ledger.relations[{idx}] confirms source "
                "must have verdict pass"
            )
        if kind in {"supersedes", "invalidates"}:
            graph.setdefault(source, []).append(target)
        elif kind == "challenges":
            prior_challenge_entries.add(source)
        elif kind == "confirms" and target not in prior_challenge_entries:
            errors.append(
                f"[R38 EVIDENCE-RELATION] ledger.relations[{idx}] confirms must "
                "target exact prior challenge evidence"
            )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(entry_id: str) -> None:
        if entry_id in visiting:
            errors.append(f"[R38 EVIDENCE-RELATION] lifecycle relation cycle at {entry_id!r}")
            return
        if entry_id in visited:
            return
        visiting.add(entry_id)
        for target in graph.get(entry_id, []):
            visit(target)
        visiting.remove(entry_id)
        visited.add(entry_id)

    for entry_id in graph:
        visit(entry_id)


def current_evidence_by_node(ledger: Any, errors: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """Return the unique current evidence head for each node.

    A newer entry may supersede/override an older entry without mutating the old
    observation. Independent observations are never ordered implicitly: every
    older head must be displaced by an explicit append-only relation before the
    node has a unique current evidence head.
    """
    if not isinstance(ledger, dict) or not isinstance(ledger.get("entries"), list):
        return {}
    entries = [entry for entry in ledger["entries"] if isinstance(entry, dict)]
    by_id = {
        entry.get("entry_id"): entry
        for entry in entries
        if isinstance(entry.get("entry_id"), str)
    }
    displaced: set[str] = set()
    challenge_sources: dict[str, set[str]] = {}
    challenge_resolutions: dict[str, set[str]] = {}
    entry_index = {
        entry.get("entry_id"): index
        for index, entry in enumerate(entries)
        if isinstance(entry.get("entry_id"), str)
    }

    def newer(source: Any, target: Any) -> bool:
        if source not in entry_index or target not in entry_index:
            return False
        if entry_index[source] <= entry_index[target]:
            return False
        try:
            source_time = datetime.fromisoformat(by_id[source]["recorded"].replace("Z", "+00:00"))
            target_time = datetime.fromisoformat(by_id[target]["recorded"].replace("Z", "+00:00"))
        except (KeyError, AttributeError, ValueError):
            return False
        return (
            source_time.tzinfo is not None
            and target_time.tzinfo is not None
            and source_time > target_time
        )

    for entry in entries:
        for field in ("supersedes", "overrides_entry_id"):
            ref = entry.get(field)
            if isinstance(ref, str):
                if errors is not None and ref not in by_id:
                    errors.append(
                        f"[R38 EVIDENCE-RELATION] entry {entry.get('entry_id')!r} "
                        f"{field} references missing entry {ref!r}"
                    )
                elif errors is not None and by_id.get(ref, {}).get("node_id") != entry.get("node_id"):
                    errors.append(
                        f"[R38 EVIDENCE-RELATION] entry {entry.get('entry_id')!r} "
                        f"{field} crosses node boundaries"
                    )
                elif newer(entry.get("entry_id"), ref):
                    displaced.add(ref)
    for relation in ledger.get("relations", []) if isinstance(ledger.get("relations", []), list) else []:
        if not isinstance(relation, dict):
            continue
        target = relation.get("target_entry_id")
        if not isinstance(target, str):
            continue
        source = relation.get("source_entry_id")
        if relation.get("relation") in {"supersedes", "invalidates"} and newer(source, target):
            displaced.add(target)
        elif relation.get("relation") == "challenges":
            source = relation.get("source_entry_id")
            if isinstance(source, str) and newer(source, target):
                challenge_sources.setdefault(target, set()).add(source)
        elif relation.get("relation") == "confirms":
            source = relation.get("source_entry_id")
            if isinstance(source, str) and newer(source, target):
                challenge_resolutions.setdefault(target, set()).add(source)

    eligible_ids = {
        entry.get("entry_id")
        for entry in entries
        if entry.get("entry_id") not in displaced
        and entry.get("status", "active") == "active"
    }
    challenged = {
        target
        for target, sources in challenge_sources.items()
        if target in eligible_ids
        and any(
            source in by_id
            and not any(resolution in eligible_ids for resolution in challenge_resolutions.get(source, set()))
            for source in sources
        )
    }
    unsafe_inactive_negative_nodes = {
        entry.get("node_id")
        for entry in entries
        if entry.get("status", "active") != "active"
        and entry.get("verdict") in {"fail", "inconclusive"}
        and entry.get("entry_id") not in displaced
        and isinstance(entry.get("node_id"), str)
    }
    if errors is not None:
        for node_id in sorted(unsafe_inactive_negative_nodes):
            errors.append(
                f"[R38 EVIDENCE-LIFECYCLE] node {node_id!r} has inactive negative "
                "evidence without a newer explicit superseding/invalidating relation; "
                "it cannot be hidden while older evidence remains current"
            )

    heads: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        entry_id = entry.get("entry_id")
        node_id = entry.get("node_id")
        if not isinstance(node_id, str) or entry_id in displaced or entry_id in challenged:
            continue
        if entry.get("status", "active") != "active":
            continue
        heads.setdefault(node_id, []).append(entry)
    current: dict[str, dict[str, Any]] = {}
    for node_id, candidates in heads.items():
        if node_id in unsafe_inactive_negative_nodes:
            continue
        if len(candidates) == 1:
            current[node_id] = candidates[0]
        elif errors is not None:
            errors.append(
                f"[R38 EVIDENCE-HEAD] node {node_id!r} has {len(candidates)} "
                "undisplaced current evidence heads; append an explicit lifecycle "
                "relation before any head can authorize completion"
            )
    return current


def check_ledger_node_resolution(ledger: Any, plan: Any, errors: list[str]) -> None:
    """Require every evidence entry to name a top-level or nested plan node."""
    if not isinstance(ledger, dict) or not isinstance(plan, dict):
        return
    node_ids: set[str] = set()

    def walk(raw_nodes: Any) -> None:
        if not isinstance(raw_nodes, list):
            return
        for node in raw_nodes:
            if not isinstance(node, dict):
                continue
            node_id = node.get("id")
            if isinstance(node_id, str) and node_id:
                node_ids.add(node_id)
            subgraph = node.get("subgraph")
            if isinstance(subgraph, dict):
                walk(subgraph.get("nodes"))

    walk(plan.get("nodes"))
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        return
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        node_id = entry.get("node_id")
        if isinstance(node_id, str) and node_id and node_id not in node_ids:
            errors.append(
                f"[INTEGRITY:evidence-node] ledger entry[{idx}] node_id "
                f"{node_id!r} does not exist in the current plan, including nested "
                "subgraph nodes"
            )


def check_event_evidence_references(
    event_entries: Any,
    ledger: Any,
    errors: list[str],
) -> None:
    """Resolve mutation refs and prove reopen refs were current counterevidence."""
    if not isinstance(event_entries, list) or not isinstance(ledger, dict):
        return
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        return
    typed_entries = [entry for entry in entries if isinstance(entry, dict)]
    by_id = {
        entry.get("entry_id"): entry
        for entry in typed_entries
        if isinstance(entry.get("entry_id"), str)
    }

    def parse_time(value: Any, label: str, error_tag: str) -> datetime | None:
        if not isinstance(value, str) or not _RFC3339.fullmatch(value):
            errors.append(f"[{error_tag}] {label} must be an RFC 3339 date-time")
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            errors.append(f"[{error_tag}] {label} must be an RFC 3339 date-time")
            return None
        if parsed.tzinfo is None:
            errors.append(f"[{error_tag}] {label} must include a timezone")
            return None
        return parsed

    for event in event_entries:
        if not isinstance(event, dict) or event.get("kind") not in {"mutation", "reopen"}:
            continue
        kind = event.get("kind")
        refs = event.get("evidence_refs")
        if not isinstance(refs, list):
            continue
        missing = [ref for ref in refs if ref not in by_id]
        if missing:
            if kind == "reopen":
                errors.append(
                    f"[R24 ILLEGAL-REOPEN] event {event.get('seq')!r}: "
                    "counterevidence references must resolve in evidence.ledger"
                )
            else:
                errors.append(
                    f"[R39 MUTATION-EVIDENCE] event {event.get('seq')!r}: "
                    "mutation evidence_refs must resolve in evidence.ledger"
                )
        if kind == "mutation":
            event_node = event.get("node_id")
            event_time = parse_time(
                event.get("ts"),
                f"mutation event {event.get('seq')!r}.ts",
                "R39 MUTATION-EVIDENCE",
            )
            for ref in refs:
                evidence = by_id.get(ref)
                if (
                    isinstance(evidence, dict)
                    and evidence.get("node_id") != event_node
                ):
                    errors.append(
                        f"[R39 MUTATION-EVIDENCE] event {event.get('seq')!r}: "
                        f"evidence {ref!r} belongs to node "
                        f"{evidence.get('node_id')!r}, not mutation node "
                        f"{event_node!r}"
                    )
                if not isinstance(evidence, dict):
                    continue
                evidence_time = parse_time(
                    evidence.get("recorded"),
                    f"mutation evidence {ref!r}.recorded",
                    "R39 MUTATION-EVIDENCE",
                )
                if (
                    event_time is not None
                    and evidence_time is not None
                    and evidence_time >= event_time
                ):
                    errors.append(
                        f"[R39 MUTATION-EVIDENCE] event {event.get('seq')!r}: "
                        f"evidence {ref!r} must be recorded strictly before the "
                        "mutation event"
                    )
        if kind != "reopen":
            continue
        if len(refs) != len(set(refs)):
            errors.append(
                f"[R24 ILLEGAL-REOPEN] event {event.get('seq')!r}: "
                "counterevidence references must be unique"
            )
        event_time = parse_time(
            event.get("ts"),
            f"reopen event {event.get('seq')!r}.ts",
            "R24 ILLEGAL-REOPEN",
        )
        if event_time is None:
            continue

        indexed_entries: list[tuple[dict[str, Any], datetime | None]] = []
        for entry in typed_entries:
            entry_id = entry.get("entry_id")
            recorded = parse_time(
                entry.get("recorded"),
                f"ledger entry {entry_id!r}.recorded",
                "R24 ILLEGAL-REOPEN",
            ) if isinstance(entry_id, str) else None
            indexed_entries.append((entry, recorded))

        prior_entries: list[dict[str, Any]] = []
        prior_ids: set[str] = set()
        entry_times: dict[str, datetime | None] = {}
        for entry, recorded in indexed_entries:
            entry_id = entry.get("entry_id")
            if not isinstance(entry_id, str):
                continue
            entry_times[entry_id] = recorded
            if recorded is not None and recorded < event_time:
                prior_entries.append(entry)
                prior_ids.add(entry_id)
        relations = [
            relation
            for relation in ledger.get("relations", [])
            if isinstance(relation, dict)
            and relation.get("source_entry_id") in prior_ids
            and relation.get("target_entry_id") in prior_ids
        ] if isinstance(ledger.get("relations", []), list) else []
        current = current_evidence_by_node({"entries": prior_entries, "relations": relations})
        event_node = event.get("node_id")
        current_entry = current.get(event_node)
        current_id = current_entry.get("entry_id") if isinstance(current_entry, dict) else None
        for ref in refs:
            evidence = by_id.get(ref)
            if not isinstance(evidence, dict):
                continue
            if evidence.get("node_id") != event_node:
                errors.append(
                    f"[R24 ILLEGAL-REOPEN] event {event.get('seq')!r}: "
                    f"counterevidence {ref!r} belongs to node "
                    f"{evidence.get('node_id')!r}, not reopened node {event_node!r}"
                )
            if evidence.get("status", "active") != "active":
                errors.append(
                    f"[R24 ILLEGAL-REOPEN] event {event.get('seq')!r}: "
                    f"counterevidence {ref!r} is not an active immutable observation"
                )
            if evidence.get("verdict") not in {"fail", "inconclusive"}:
                errors.append(
                    f"[R24 ILLEGAL-REOPEN] event {event.get('seq')!r}: "
                    f"counterevidence {ref!r} must have verdict fail or inconclusive"
                )
            recorded = entry_times.get(ref)
            if recorded is None or recorded >= event_time:
                errors.append(
                    f"[R24 ILLEGAL-REOPEN] event {event.get('seq')!r}: "
                    f"counterevidence {ref!r} must be recorded strictly before the "
                    "reopen event"
                )
            if current_id != ref:
                errors.append(
                    f"[R24 ILLEGAL-REOPEN] event {event.get('seq')!r}: "
                    f"counterevidence {ref!r} was not the unique current evidence "
                    f"head for node {event_node!r} when the reopen was recorded"
                )


def check_ledger_verifier_independence(ledger: Any, plan: Any, errors: list[str]) -> None:
    """Validate explicit blind-review context; role labels and mtimes prove nothing."""
    if not isinstance(ledger, dict) or not isinstance(plan, dict):
        return
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        return
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        if entry.get("assurance") != "blind":
            continue
        context = entry.get("review_context")
        valid = (
            isinstance(context, dict)
            and isinstance(context.get("review_id"), str) and context.get("review_id")
            and isinstance(context.get("delivered_context_sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", context.get("delivered_context_sha256", ""))
            and context.get("producer_claim_access") == "withheld"
        )
        if not valid:
            errors.append(
                f"[R47 BLIND-CONTEXT-MISSING] ledger entry[{idx}] for node "
                f"{entry.get('node_id')!r}: assurance 'blind' requires explicit "
                "review_context {review_id, delivered_context_sha256, "
                "producer_claim_access: withheld}; available/unknown access, role "
                "labels, and filesystem mtimes are not proof of blindness"
            )


def check_goal_citation_resolution(ledger: Any, plan: Any, errors: list[str]) -> None:
    """R45 checks whether each present success_criteria_id exists in the plan.

    This exact-id membership check does not license any conclusion that the
    criterion is satisfied, met, or demonstrated by the cited evidence.
    """
    if not isinstance(ledger, dict) or not isinstance(plan, dict):
        return
    criterion_ids = {
        criterion.get("id")
        for criterion in plan.get("success_criteria", [])
        if isinstance(criterion, dict)
    }
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        return
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict) or "success_criteria_id" not in entry:
            continue
        cited_id = entry.get("success_criteria_id")
        if cited_id not in criterion_ids:
            errors.append(
                f"[R45 GOAL-CITATION-UNRESOLVED] ledger entry[{idx}] "
                f"success_criteria_id {cited_id!r}: cited criterion id does not "
                "exist in loop.plan.success_criteria[].id; this checks exact-id "
                "reference validity only and does not license any conclusion "
                "that a criterion is satisfied, met, or demonstrated"
            )


def check_missing_dissent(
    ledger: Any,
    checkpoint: Any,
    event_entries: Any,
    errors: list[str],
) -> None:
    """R48 checks whether completed nodes with active blind failures have dissent events.

    This exact field-and-event presence check does not license any conclusion
    that an override was wrong or unjustified, or that either verdict or the
    completed design is correct.
    """
    if not isinstance(ledger, dict) or not isinstance(checkpoint, dict):
        return
    if not isinstance(event_entries, list):
        return
    completed_nodes = {
        node_id
        for node_id, status in (checkpoint.get("node_states") or {}).items()
        if status == "completed"
    }
    by_id = {
        entry.get("entry_id"): entry
        for entry in ledger.get("entries", [])
        if isinstance(entry, dict) and isinstance(entry.get("entry_id"), str)
    }
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        return

    def parse_recorded(value: Any, label: str) -> datetime | None:
        if not isinstance(value, str) or not value:
            errors.append(f"[R48 INVALID-TIME] {label} must be an RFC 3339 date-time")
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            errors.append(f"[R48 INVALID-TIME] {label} must be an RFC 3339 date-time")
            return None
        if parsed.tzinfo is None:
            errors.append(f"[R48 INVALID-TIME] {label} must include a timezone")
            return None
        return parsed

    current = current_evidence_by_node(ledger)
    entry_indexes = {
        entry.get("entry_id"): idx
        for idx, entry in enumerate(entries)
        if isinstance(entry, dict) and isinstance(entry.get("entry_id"), str)
    }
    for node_id in completed_nodes:
        current_override = current.get(node_id)
        explicit_overrides = [
            entry
            for entry in entries
            if isinstance(entry, dict)
            and entry.get("node_id") == node_id
            and isinstance(entry.get("overrides_entry_id"), str)
        ]
        current_is_authorizing_pass = (
            isinstance(current_override, dict)
            and current_override.get("verdict") == "pass"
            and (
                current_override.get("assurance") == "external"
                or current_override.get("gate_kind") == "human_approval"
            )
        )
        override = current_override if isinstance(current_override, dict) else None
        if current_is_authorizing_pass and not isinstance(
            current_override.get("overrides_entry_id"), str
        ):
            continue
        if not isinstance(override, dict) or not isinstance(override.get("overrides_entry_id"), str):
            override = explicit_overrides[-1] if explicit_overrides else None
        if not isinstance(override, dict):
            continue
        failed_id = override.get("overrides_entry_id")
        failed = by_id.get(failed_id)
        is_explicit_blind_failure_override = (
            isinstance(failed, dict)
            and failed.get("node_id") == node_id
            and failed.get("status", "active") == "active"
            and failed.get("assurance") == "blind"
            and failed.get("verdict") == "fail"
            and override.get("verdict") == "pass"
            and (
                override.get("assurance") == "external"
                or override.get("gate_kind") == "human_approval"
            )
        )
        if not is_explicit_blind_failure_override:
            continue
        override_is_current_active = (
            current_override is override
            and override.get("status", "active") == "active"
        )
        override_time = parse_recorded(
            override.get("recorded"),
            f"ledger entry {override.get('entry_id')!r}.recorded",
        )
        dissent_times = {
            id(event): parse_recorded(
                event.get("recorded", event.get("ts")),
                f"dissent event for node {node_id!r}.ts",
            )
            for event in event_entries
            if isinstance(event, dict)
            and event.get("kind") == "dissent"
            and event.get("node_id") == node_id
            and event.get("failed_entry_id") == failed_id
        }
        exact_dissent = override_is_current_active and any(
            isinstance(event, dict)
            and event.get("kind") == "dissent"
            and event.get("node_id") == node_id
            and event.get("failed_entry_id") == failed_id
            and event.get("overriding_entry_id") == override.get("entry_id")
            and dissent_times.get(id(event)) is not None
            and override_time is not None
            and dissent_times[id(event)] >= override_time
            and isinstance(event.get("reason"), str) and event.get("reason")
            for event in event_entries
        )
        if not exact_dissent:
            idx = entry_indexes.get(failed_id, "?")
            errors.append(
                f"[R48 MISSING-DISSENT] ledger entry[{idx}] "
                f"{failed_id!r} for completed node {node_id!r} is explicitly "
                "overridden, but the overriding entry is not the unique current active "
                "passing head or there is no exact failed-entry -> "
                "overriding-entry -> dissent-event chain; this checks record absence "
                "only and does not license "
                "any conclusion that the override was wrong or unjustified, or "
                "that either verdict or the completed design is correct"
            )
