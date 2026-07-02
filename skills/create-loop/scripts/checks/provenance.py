"""Plan provenance checks (R26, R27): plan_history integrity and goal-change
detection. A goal/true_intent change must be recorded as a new plan_history
entry whose hashes match the current content, so a silent mutation is rejected.
"""
from __future__ import annotations

import hashlib
import re
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
    """R36: a med/high-risk side-effecting node may not be self-verified by the
    agent that produced it. Cross-references each ledger entry's node against the
    plan's risk + produces to require an independent verifier."""
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

