from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

_WS = re.compile(r"\s+")


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


def check_ledger_verifier_independence(ledger: Any, plan: Any, errors: list[str]) -> None:
    """Check R36 verifier provenance and R47 blind-review file ordering.

    R47 compares only the verdict and producer-claim file mtimes. That
    comparison does not establish that the reviewer was blind or independent.
    """
    if not isinstance(ledger, dict) or not isinstance(plan, dict):
        return
    risk_by_id: dict[str, Any] = {}
    produces_by_id: dict[str, Any] = {}

    def walk(nodes: Any) -> None:
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            nid = node.get("id")
            if isinstance(nid, str):
                risk_by_id[nid] = node.get("risk")
                produces_by_id[nid] = node.get("produces")
            sub = node.get("subgraph")
            if isinstance(sub, dict):
                walk(sub.get("nodes"))

    walk(plan.get("nodes"))
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        return
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        nid = entry.get("node_id")
        risk = risk_by_id.get(nid)
        produces = produces_by_id.get(nid)
        side_effecting = isinstance(produces, list) and len(produces) > 0
        if risk in ("med", "high") and side_effecting and entry.get("verifier") == "agent":
            errors.append(
                f"[R36 SELF-VERIFY-RISK] ledger entry[{idx}] for node {nid!r} "
                f"(risk={risk!r}, side-effecting): verifier is 'agent'. A med/high-risk "
                f"side-effecting node needs an independent verifier "
                f"(user/subagent/script), not self-certification."
            )

        if entry.get("assurance") != "blind":
            continue
        verdict_path = entry.get("artifact_path")
        claim_path = entry.get("producer_claim_path")
        if not isinstance(verdict_path, str) or not isinstance(claim_path, str):
            continue
        verdict = Path(verdict_path)
        claim = Path(claim_path)
        if not verdict.is_file() or not claim.is_file():
            continue
        if verdict.stat().st_mtime > claim.stat().st_mtime:
            errors.append(
                f"[R47 BLIND-ORDER-VIOLATION] ledger entry[{idx}] for node {nid!r}: "
                "reviewer verdict file mtime is after producer claim file mtime; "
                "this establishes an ordering violation only and does not license "
                "the conclusion that the reviewer was not blind or not independent"
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
    dissent_nodes = {
        event.get("node_id")
        for event in event_entries
        if isinstance(event, dict) and event.get("kind") == "dissent"
    }
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        return
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        node_id = entry.get("node_id")
        is_active_blind_failure = (
            entry.get("status", "active") == "active"
            and entry.get("assurance") == "blind"
            and entry.get("verdict") == "fail"
        )
        if is_active_blind_failure and node_id in completed_nodes and node_id not in dissent_nodes:
            errors.append(
                f"[R48 MISSING-DISSENT] ledger entry[{idx}] "
                f"{entry.get('entry_id')!r} for completed node {node_id!r} is an "
                "active blind failure, but the event log has no dissent event for "
                "that node; this checks record absence only and does not license "
                "any conclusion that the override was wrong or unjustified, or "
                "that either verdict or the completed design is correct"
            )
