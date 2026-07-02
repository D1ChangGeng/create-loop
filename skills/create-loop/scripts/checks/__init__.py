"""Canonical enums, patterns, and required-field sets for the create-loop checks.

Single source of truth: every check module imports its constants from here so
the 15 node statuses, 8 gate kinds, 8 node kinds, on_failure ladder, loop_id /
slug patterns, subgraph statuses, and per-kind required-field tuples are defined
exactly ONCE and can never diverge. Values are verbatim from references/
(loop_plan_spec.md + state_model.md + recursive_loops.md +
subgraph_subloop_policy.md); do NOT rename.
"""
from __future__ import annotations

import re

# --- Canonical enums (verbatim from references; do NOT rename) ---------------
NODE_STATUSES: frozenset[str] = frozenset({
    "undiscovered", "discovered", "needs_clarification", "pending", "ready",
    "running", "waiting_external", "waiting_user", "blocked", "verifying",
    "verification_failed", "retry_pending", "completed", "cancelled", "deprecated",
})
NODE_KINDS: frozenset[str] = frozenset({
    "milestone", "gate", "mapper", "branch", "fanout", "join", "approval",
    "compensation",
})
GATE_KINDS: frozenset[str] = frozenset({
    "automated_check", "test", "llm_judge", "self_consistency",
    "evaluator_optimizer", "step_verifier", "human_approval", "artifact_exists",
})
ON_FAILURE: frozenset[str] = frozenset({
    "local_retry", "local_patch", "replan", "escalate",
})
# The 8 SUBGRAPH statuses — DISTINCT from the 15 node statuses; the two enums
# never overlap in scope (subgraph_subloop_policy.md §8). Terminal: completed,
# failed, promoted_to_subloop, cancelled.
SUBGRAPH_STATUSES: frozenset[str] = frozenset({
    "proposed", "admitted", "running", "blocked", "completed", "failed",
    "promoted_to_subloop", "cancelled",
})
# loop.meta.yaml.type enum (2 values).
LOOP_META_TYPES: frozenset[str] = frozenset({"root_loop", "child_loop"})

# human_intervention_policy enums (OPTIONAL top-level plan field). The policy
# encodes the Human Decision Package rules (references/human_approval.md). The
# field is optional: a plan without it stays valid; when present, its enum-typed
# members are checked here (rule R18).
HIP_DEFAULT_MODES: frozenset[str] = frozenset({
    "structured_decision_package", "direct_question",
})
HIP_ANSWER_FORMATS: frozenset[str] = frozenset({"yaml", "json", "structured_text"})
# The 10 canonical decision-package trigger tokens.
HIP_REQUIRED_WHEN_TOKENS: frozenset[str] = frozenset({
    "top_level_goal_change", "scope_expansion", "major_resource_cost",
    "external_side_effect", "irreversible_operation",
    "legal_security_compliance_licensing_risk",
    "permission_or_credential_required", "user_value_preference_required",
    "no_evidence_backed_dominant_option", "long_term_knowledge_promotion",
})

# loop_id pattern (recursive_loops.md §3.3): top-level L<seq> (3-digit
# zero-padded) plus one ".<local-seq>" (2-digit zero-padded) per recursion
# level. e.g. L001, L001.02, L001.02.01.
LOOP_ID_RE = re.compile(r"^L\d{3}(\.\d{2})*$")
# slug rule (recursive_loops.md §3.4): lowercase kebab-case, English only, no
# uppercase/underscore/space, no punctuation but the hyphen, <= 32 chars.
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SLUG_MAX_LEN: int = 32

# Kinds that MUST carry a gate (non-trivial). Per evidence_gates.md §6 a null
# gate is only for trivial mechanical edits; fanout/compensation may be
# gate-exempt at plan level (fanout only dispatches, compensation is a saga undo
# whose gate is its pair's). approval is NOT exempt: it must carry a
# human_approval gate (R34, checks/gates.py) — it is the human-decision control point.
GATE_REQUIRED_KINDS: frozenset[str] = frozenset({
    "milestone", "gate", "mapper", "branch", "join",
})

PLAN_REQUIRED: tuple[str, ...] = (
    "schema_version", "plan_id", "goal", "true_intent", "non_goals",
    "success_criteria", "failure_criteria", "termination", "constraints",
    "nodes", "created", "plan_version",
)
NODE_REQUIRED: tuple[str, ...] = (
    "id", "kind", "title", "design_invariant", "status", "requires", "produces",
    "inputs", "preconditions", "postconditions", "gate", "retry_policy",
    "on_failure", "priority", "risk", "parallelizable", "allow_subgraph",
    "subgraph", "child_loops", "assignee", "notes",
)
LEDGER_REQUIRED: tuple[str, ...] = ("schema_version", "entries")
CONTRACT_REQUIRED: tuple[str, ...] = (
    "node_id", "plan_id", "cache_key", "attempt", "status", "gate",
    "retry_policy", "on_failure", "evidence_ref", "started", "finished",
    "compensation_of",
)

CHILD_LOOP_REF_REQUIRED: tuple[str, ...] = (
    "loop_id", "path", "spawn_reason", "status", "closeout",
)
LOOP_META_REQUIRED: tuple[str, ...] = (
    "loop_id", "slug", "title", "type", "parent", "root", "status",
    "created_at", "created_by", "depth", "scope", "return_contract",
)
PARENT_REF_REQUIRED: tuple[str, ...] = (
    "loop_id", "path", "parent_node_id", "spawn_reason",
)
INDEX_LOOP_ENTRY_REQUIRED: tuple[str, ...] = (
    "loop_id", "slug", "path", "status", "title", "checkpoint", "updated_at",
    "current_active_node",
)
INDEX_CHILD_ENTRY_REQUIRED: tuple[str, ...] = (
    "loop_id", "slug", "path", "status", "parent_node_id", "current_active_node",
)
RUNTIME_SUBGRAPH_REQUIRED: tuple[str, ...] = (
    "subgraph_id", "title", "status", "spawn_reason", "scope", "nodes", "edges",
    "completion_gate", "outputs", "promotion_policy",
)
