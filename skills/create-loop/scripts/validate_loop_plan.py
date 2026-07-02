#!/usr/bin/env python3
"""Validate a create-loop YAML artifact against its schema and graph rules.

Kinds: loop_plan (default), node_contract, evidence_ledger, loop_meta,
loops_index, node_runtime.

For every kind the CRITICAL checks (required fields, enum legality, pattern
rules, and the graph rules R1-R5/R7/R8) are hand-rolled from the canonical
enums in references/loop_plan_spec.md + state_model.md + recursive_loops.md +
subgraph_subloop_policy.md, so the acceptance gate never depends on a
third-party library. jsonschema is used ONLY as a bonus structural layer when
importable (guarded try/except); its absence never hard-fails validation.

Exit codes: 0 valid, 1 structural/graph error(s), 2 load/usage error.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - environment guard
    print(
        "error: PyYAML is required but not importable. Install with: pip install pyyaml",
        file=sys.stderr,
    )
    sys.exit(2)

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
# gate is only for trivial mechanical edits; fanout/compensation/approval may be
# gate-exempt at plan level (approval self-gates via its human_approval handoff,
# fanout only dispatches, compensation is a saga undo whose gate is its pair's).
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
)
INDEX_CHILD_ENTRY_REQUIRED: tuple[str, ...] = (
    "loop_id", "slug", "path", "status", "parent_node_id",
)
RUNTIME_SUBGRAPH_REQUIRED: tuple[str, ...] = (
    "subgraph_id", "title", "status", "spawn_reason", "scope", "nodes", "edges",
    "completion_gate", "outputs", "promotion_policy",
)

SCHEMA_BY_KIND: dict[str, str] = {
    "loop_plan": "loop.plan.schema.json",
    "node_contract": "node.contract.schema.json",
    "evidence_ledger": "evidence.ledger.schema.json",
    "loop_meta": "loop.meta.schema.json",
    "loops_index": "loops.index.schema.json",
    "node_runtime": "node.runtime.schema.json",
}


def load_yaml(path: str) -> Any:
    """Load a YAML document, exiting 2 with a clear message on any failure."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except FileNotFoundError:
        print(f"error: file not found: {path}", file=sys.stderr)
        sys.exit(2)
    except (yaml.YAMLError, OSError) as exc:
        print(f"error: could not parse YAML {path}: {exc}", file=sys.stderr)
        sys.exit(2)


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


def check_node_fields(node: Any, scope: str, errors: list[str]) -> None:
    """Hand-rolled per-node structural + enum checks (R4, R5, R7, R8)."""
    if not isinstance(node, dict):
        errors.append(f"[R5 MISSING REQUIRED FIELD] {scope}: node is not a mapping")
        return
    node_id = node.get("id")
    label = f"node {node_id!r}" if node_id is not None else f"node (no id) in {scope}"

    # R5: required fields present (id first, so the message is actionable).
    for field in NODE_REQUIRED:
        if field not in node:
            errors.append(
                f"[R5 MISSING REQUIRED FIELD] {label}: missing required field "
                f"{field!r}"
            )

    # R4: status enum.
    status = node.get("status")
    if "status" in node and status not in NODE_STATUSES:
        errors.append(
            f"[R4 BAD STATUS] {label}: status {status!r} is not one of the 15 "
            f"node statuses"
        )

    # kind enum (feeds R3 gate-exemption decision).
    kind = node.get("kind")
    if "kind" in node and kind not in NODE_KINDS:
        errors.append(
            f"[R4 BAD KIND] {label}: kind {kind!r} is not one of the 8 node kinds"
        )

    # R7: gate kind.
    check_gate(node.get("gate"), label, errors)

    # R3: non-trivial node must carry a gate.
    if kind in GATE_REQUIRED_KINDS and node.get("gate") is None:
        errors.append(
            f"[R3 MISSING EVIDENCE GATE] {label}: non-trivial node of kind "
            f"{kind!r} has gate: null; only trivial nodes may omit a gate"
        )

    # R8: on_failure enum.
    on_failure = node.get("on_failure")
    if "on_failure" in node and on_failure not in ON_FAILURE:
        errors.append(
            f"[R8 BAD on_failure] {label}: on_failure {on_failure!r} is not one of "
            f"{sorted(ON_FAILURE)}"
        )

    # R13: child_loops reference list.
    if "child_loops" in node:
        check_child_loops(node.get("child_loops"), label, errors)


def check_child_loops(child_loops: Any, label: str, errors: list[str]) -> None:
    """Validate a node's child_loops reference list (R13)."""
    if not isinstance(child_loops, list):
        errors.append(
            f"[R13 BAD child_loops] {label}: child_loops must be a list "
            f"(empty [] when the node has no materialized children)"
        )
        return
    for idx, ref in enumerate(child_loops):
        ref_scope = f"{label} child_loops[{idx}]"
        if not isinstance(ref, dict):
            errors.append(
                f"[R13 BAD child_loops] {ref_scope}: entry must be an object with "
                f"{list(CHILD_LOOP_REF_REQUIRED)}"
            )
            continue
        for field in CHILD_LOOP_REF_REQUIRED:
            if field not in ref:
                errors.append(
                    f"[R13 BAD child_loops] {ref_scope}: missing required field "
                    f"{field!r}"
                )
        loop_id = ref.get("loop_id")
        if "loop_id" in ref and not (
            isinstance(loop_id, str) and LOOP_ID_RE.match(loop_id)
        ):
            errors.append(
                f"[R13 BAD child_loops] {ref_scope}: loop_id {loop_id!r} does not "
                f"match the loop-id pattern L<seq>[.<seq>]"
            )
        status = ref.get("status")
        if "status" in ref and status not in NODE_STATUSES:
            errors.append(
                f"[R13 BAD child_loops] {ref_scope}: status {status!r} is not one "
                f"of the 15 node statuses"
            )


def check_graph(nodes: list[Any], scope: str, errors: list[str]) -> None:
    """Hand-rolled graph checks over one plan/subgraph scope (R1, R2)."""
    defined: set[str] = {
        n["id"] for n in nodes if isinstance(n, dict) and isinstance(n.get("id"), str)
    }
    adjacency: dict[str, list[str]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = node.get("id")
        if not isinstance(nid, str):
            continue
        requires = node.get("requires") or []
        deps = [d for d in requires if isinstance(d, str)]
        adjacency[nid] = deps
        # R2: dangling dependency.
        for dep in deps:
            if dep not in defined:
                errors.append(
                    f"[R2 DANGLING DEP] {scope}node {nid!r}: requires {dep!r} which "
                    f"is not the id of any defined node"
                )

    # R1: cycle detection via white(0)/gray(1)/black(2) DFS coloring.
    color: dict[str, int] = {nid: 0 for nid in adjacency}
    stack: list[str] = []

    def visit(nid: str) -> bool:
        color[nid] = 1
        stack.append(nid)
        for dep in adjacency.get(nid, []):
            if dep not in color:
                continue  # dangling; already reported by R2.
            if color[dep] == 1:
                cycle = stack[stack.index(dep):] + [dep]
                errors.append(
                    f"[R1 CYCLE] {scope}dependency cycle detected: "
                    f"{' -> '.join(cycle)}"
                )
                return True
            if color[dep] == 0 and visit(dep):
                return True
        stack.pop()
        color[nid] = 2
        return False

    for nid in adjacency:
        if color[nid] == 0 and visit(nid):
            break


def validate_nodes_recursive(nodes: Any, scope: str, errors: list[str]) -> None:
    """Validate a node list and recurse into any materialised subgraphs."""
    if not isinstance(nodes, list) or not nodes:
        errors.append(f"[R5 MISSING REQUIRED FIELD] {scope}nodes must be a non-empty list")
        return
    for node in nodes:
        check_node_fields(node, scope, errors)
        if isinstance(node, dict):
            sub = node.get("subgraph")
            if isinstance(sub, dict) and isinstance(sub.get("nodes"), list):
                child_scope = f"{scope}subgraph[{node.get('id')}]/"
                validate_nodes_recursive(sub["nodes"], child_scope, errors)
                check_graph(sub["nodes"], child_scope, errors)
    check_graph(nodes, scope, errors)


def check_human_intervention_policy(policy: Any, errors: list[str]) -> None:
    """Validate the OPTIONAL human_intervention_policy block (R18).

    Absent -> no-op (the field is optional; legacy plans stay valid). Present ->
    the enum-typed members are checked against their canonical token sets.
    """
    if policy is None:
        return
    if not isinstance(policy, dict):
        errors.append(
            "[R18 BAD human_intervention_policy] human_intervention_policy must "
            "be a mapping when present"
        )
        return

    default_mode = policy.get("default_mode")
    if "default_mode" in policy and default_mode not in HIP_DEFAULT_MODES:
        errors.append(
            f"[R18 BAD human_intervention_policy] default_mode {default_mode!r} "
            f"is not one of {sorted(HIP_DEFAULT_MODES)}"
        )

    answer_format = policy.get("preferred_answer_format")
    if "preferred_answer_format" in policy and answer_format not in HIP_ANSWER_FORMATS:
        errors.append(
            f"[R18 BAD human_intervention_policy] preferred_answer_format "
            f"{answer_format!r} is not one of {sorted(HIP_ANSWER_FORMATS)}"
        )

    required_when = policy.get("decision_package_required_when")
    if "decision_package_required_when" in policy:
        if not isinstance(required_when, list):
            errors.append(
                "[R18 BAD human_intervention_policy] decision_package_required_when "
                "must be a list of trigger tokens"
            )
        else:
            for idx, token in enumerate(required_when):
                if token not in HIP_REQUIRED_WHEN_TOKENS:
                    errors.append(
                        f"[R18 BAD human_intervention_policy] "
                        f"decision_package_required_when[{idx}] {token!r} is not one "
                        f"of the 10 trigger tokens {sorted(HIP_REQUIRED_WHEN_TOKENS)}"
                    )


def validate_loop_plan(doc: Any, errors: list[str]) -> None:
    """Structural + graph validation for a loop.plan document."""
    if not isinstance(doc, dict):
        errors.append("[R5 MISSING REQUIRED FIELD] plan: document is not a mapping")
        return
    for field in PLAN_REQUIRED:
        if field not in doc:
            errors.append(
                f"[R5 MISSING REQUIRED FIELD] plan: missing top-level field {field!r}"
            )
    if isinstance(doc.get("termination"), dict):
        for field in ("max_iterations", "max_wall_clock_hours", "max_cost_units", "done_when"):
            if field not in doc["termination"]:
                errors.append(
                    f"[R5 MISSING REQUIRED FIELD] termination: missing {field!r}"
                )
    if "human_intervention_policy" in doc:
        check_human_intervention_policy(doc.get("human_intervention_policy"), errors)
    validate_nodes_recursive(doc.get("nodes"), "", errors)


def validate_flat_status_and_gate(doc: Any, required: tuple[str, ...], errors: list[str]) -> None:
    """Shared checks for node_contract: required fields + status + gate kind."""
    if not isinstance(doc, dict):
        errors.append("[R5 MISSING REQUIRED FIELD] document is not a mapping")
        return
    for field in required:
        if field not in doc:
            errors.append(f"[R5 MISSING REQUIRED FIELD] missing field {field!r}")
    status = doc.get("status")
    if "status" in doc and status not in NODE_STATUSES:
        errors.append(f"[R4 BAD STATUS] status {status!r} is not a valid node status")
    check_gate(doc.get("gate"), "contract", errors)
    on_failure = doc.get("on_failure")
    if "on_failure" in doc and on_failure not in ON_FAILURE:
        errors.append(f"[R8 BAD on_failure] on_failure {on_failure!r} is invalid")


def validate_evidence_ledger(doc: Any, errors: list[str]) -> None:
    """Structural checks for an evidence.ledger document."""
    if not isinstance(doc, dict):
        errors.append("[R5 MISSING REQUIRED FIELD] ledger: document is not a mapping")
        return
    for field in LEDGER_REQUIRED:
        if field not in doc:
            errors.append(f"[R5 MISSING REQUIRED FIELD] ledger: missing field {field!r}")
    entries = doc.get("entries")
    if not isinstance(entries, list):
        return
    valid_verdicts = {"pass", "fail", "inconclusive"}
    valid_verifiers = {"agent", "subagent", "user", "script"}
    for idx, entry in enumerate(entries):
        scope = f"ledger entry[{idx}]"
        if not isinstance(entry, dict):
            errors.append(f"[R5 MISSING REQUIRED FIELD] {scope}: not a mapping")
            continue
        for field in ("entry_id", "node_id", "gate_kind", "verdict", "score",
                      "artifact_path", "rationale", "recorded", "verifier"):
            if field not in entry:
                errors.append(f"[R5 MISSING REQUIRED FIELD] {scope}: missing {field!r}")
        if entry.get("gate_kind") not in GATE_KINDS and "gate_kind" in entry:
            errors.append(f"[R7 BAD GATE KIND] {scope}: gate_kind {entry.get('gate_kind')!r} invalid")
        if entry.get("verdict") not in valid_verdicts and "verdict" in entry:
            errors.append(f"[R4 BAD VERDICT] {scope}: verdict {entry.get('verdict')!r} invalid")
        if entry.get("verifier") not in valid_verifiers and "verifier" in entry:
            errors.append(f"[R4 BAD VERIFIER] {scope}: verifier {entry.get('verifier')!r} invalid")


def validate_loop_meta(doc: Any, errors: list[str]) -> None:
    """Validate a loop.meta.yaml (R9, R10, R11, R12, R17)."""
    if not isinstance(doc, dict):
        errors.append("[R11 MISSING REQUIRED FIELD] loop.meta: document is not a mapping")
        return
    for field in LOOP_META_REQUIRED:
        if field not in doc:
            errors.append(
                f"[R11 MISSING REQUIRED FIELD] loop.meta: missing required field "
                f"{field!r}"
            )

    loop_id = doc.get("loop_id")
    if "loop_id" in doc and not (isinstance(loop_id, str) and LOOP_ID_RE.match(loop_id)):
        errors.append(
            f"[R9 BAD loop_id] loop.meta: loop_id {loop_id!r} matches neither "
            f"L<seq> (e.g. L001) nor L<seq>.<seq> (e.g. L001.02)"
        )

    slug = doc.get("slug")
    if "slug" in doc:
        if not isinstance(slug, str) or not SLUG_RE.match(slug) or len(slug) > SLUG_MAX_LEN:
            errors.append(
                f"[R10 BAD slug] loop.meta: slug {slug!r} is not lowercase kebab-case "
                f"of <= {SLUG_MAX_LEN} chars (no uppercase/underscore/space)"
            )

    meta_type = doc.get("type")
    if "type" in doc and meta_type not in LOOP_META_TYPES:
        errors.append(
            f"[R12 BAD type] loop.meta: type {meta_type!r} is not one of "
            f"{sorted(LOOP_META_TYPES)}"
        )

    status = doc.get("status")
    if "status" in doc and status not in NODE_STATUSES:
        errors.append(
            f"[R4 BAD STATUS] loop.meta: status {status!r} is not one of the 15 "
            f"node statuses"
        )

    parent = doc.get("parent")
    if meta_type == "child_loop":
        if not isinstance(parent, dict):
            errors.append(
                f"[R17 CHILD_LOOP NO PARENT] loop.meta: type is child_loop but "
                f"parent is {parent!r}; a child_loop requires a parent object "
                f"({list(PARENT_REF_REQUIRED)})"
            )
        else:
            for field in PARENT_REF_REQUIRED:
                if field not in parent:
                    errors.append(
                        f"[R17 CHILD_LOOP NO PARENT] loop.meta: parent object "
                        f"missing required field {field!r}"
                    )


def validate_loops_index(doc: Any, errors: list[str]) -> None:
    """Validate a loops.index / _loops INDEX (R16)."""
    if not isinstance(doc, dict):
        errors.append("[R16 BAD INDEX] loops.index: document is not a mapping")
        return
    has_loops = "loops" in doc
    has_children = "children" in doc

    if has_loops and has_children:
        errors.append(
            "[R16 BAD INDEX] loops.index: has BOTH 'loops' and 'children' keys; "
            "a global INDEX carries 'loops' and a local _loops/INDEX carries "
            "'children' — the two shapes are mutually exclusive (oneOf)"
        )
        return
    if not has_loops and not has_children:
        errors.append(
            "[R16 BAD INDEX] loops.index: has NEITHER 'loops' (global) nor "
            "'children' (local) key; exactly one is required"
        )
        return

    if has_loops:
        check_index_entries(
            doc.get("loops"), "loops", INDEX_LOOP_ENTRY_REQUIRED, errors
        )
    else:
        check_index_entries(
            doc.get("children"), "children", INDEX_CHILD_ENTRY_REQUIRED, errors
        )


def check_index_entries(
    entries: Any, key: str, required: tuple[str, ...], errors: list[str]
) -> None:
    """Validate one INDEX entry list's field sets + status enum."""
    if not isinstance(entries, list):
        errors.append(f"[R16 BAD INDEX] loops.index: {key!r} must be a list")
        return
    for idx, entry in enumerate(entries):
        scope = f"loops.index {key}[{idx}]"
        if not isinstance(entry, dict):
            errors.append(f"[R16 BAD INDEX] {scope}: entry must be an object")
            continue
        for field in required:
            if field not in entry:
                errors.append(
                    f"[R16 BAD INDEX] {scope}: missing required field {field!r}"
                )
        status = entry.get("status")
        if "status" in entry and status not in NODE_STATUSES:
            errors.append(
                f"[R16 BAD INDEX] {scope}: status {status!r} is not one of the 15 "
                f"node statuses"
            )


def validate_node_runtime(doc: Any, errors: list[str]) -> None:
    """Validate a node.runtime.yaml (R14, R15 — subgraph status enum)."""
    if not isinstance(doc, dict):
        errors.append("[R5 MISSING REQUIRED FIELD] node.runtime: document is not a mapping")
        return
    for field in ("node_id", "runtime_subgraphs"):
        if field not in doc:
            errors.append(
                f"[R5 MISSING REQUIRED FIELD] node.runtime: missing required field "
                f"{field!r}"
            )
    subgraphs = doc.get("runtime_subgraphs")
    if not isinstance(subgraphs, list):
        if "runtime_subgraphs" in doc:
            errors.append(
                "[R5 MISSING REQUIRED FIELD] node.runtime: runtime_subgraphs must "
                "be a list"
            )
        return
    for idx, sg in enumerate(subgraphs):
        scope = f"node.runtime runtime_subgraphs[{idx}]"
        if not isinstance(sg, dict):
            errors.append(f"[R5 MISSING REQUIRED FIELD] {scope}: subgraph must be an object")
            continue
        sg_id = sg.get("subgraph_id")
        label = f"{scope} ({sg_id!r})" if sg_id is not None else scope
        for field in RUNTIME_SUBGRAPH_REQUIRED:
            if field not in sg:
                errors.append(
                    f"[R5 MISSING REQUIRED FIELD] {label}: missing required field "
                    f"{field!r}"
                )
        if "subgraph_id" in sg and not (
            isinstance(sg_id, str) and sg_id.startswith("SG-")
        ):
            errors.append(
                f"[R5 BAD subgraph_id] {label}: subgraph_id {sg_id!r} must start "
                f"with 'SG-'"
            )

        status = sg.get("status")
        if "status" in sg and status not in SUBGRAPH_STATUSES:
            hint = (
                " (that is a node status, not a subgraph status)"
                if status in NODE_STATUSES else ""
            )
            errors.append(
                f"[R14 BAD subgraph status] {label}: status {status!r} is not one "
                f"of the 8 subgraph statuses {sorted(SUBGRAPH_STATUSES)}{hint}"
            )

        sg_nodes = sg.get("nodes")
        if isinstance(sg_nodes, list):
            for nidx, sg_node in enumerate(sg_nodes):
                if not isinstance(sg_node, dict):
                    continue
                n_status = sg_node.get("status")
                if "status" in sg_node and n_status not in SUBGRAPH_STATUSES:
                    n_hint = (
                        " (that is a node status, not a subgraph status)"
                        if n_status in NODE_STATUSES else ""
                    )
                    errors.append(
                        f"[R14 BAD subgraph status] {label} nodes[{nidx}]: status "
                        f"{n_status!r} is not one of the 8 subgraph statuses{n_hint}"
                    )


def run_jsonschema_bonus(doc: Any, kind: str, errors: list[str]) -> None:
    """Optional structural layer: run jsonschema only if importable."""
    try:
        import jsonschema  # noqa: F401
        from jsonschema import Draft7Validator
    except ImportError:
        return
    schema_path = Path(__file__).resolve().parent.parent / "schemas" / SCHEMA_BY_KIND[kind]
    if not schema_path.exists():
        return
    try:
        import json
        with open(schema_path, "r", encoding="utf-8") as fh:
            schema = json.load(fh)
        validator = Draft7Validator(schema)
    except (OSError, ValueError) as exc:
        print(f"warning: jsonschema bonus layer skipped ({exc})", file=sys.stderr)
        return
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "<root>"
        errors.append(f"[jsonschema] {loc}: {err.message}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a create-loop YAML artifact.")
    parser.add_argument(
        "--kind",
        choices=(
            "loop_plan", "node_contract", "evidence_ledger", "loop_meta",
            "loops_index", "node_runtime",
        ),
        default="loop_plan",
        help="Artifact kind (default: loop_plan).",
    )
    parser.add_argument("file", help="Path to the YAML artifact.")
    args = parser.parse_args()

    doc = load_yaml(args.file)
    errors: list[str] = []

    if args.kind == "loop_plan":
        validate_loop_plan(doc, errors)
    elif args.kind == "node_contract":
        validate_flat_status_and_gate(doc, CONTRACT_REQUIRED, errors)
    elif args.kind == "evidence_ledger":
        validate_evidence_ledger(doc, errors)
    elif args.kind == "loop_meta":
        validate_loop_meta(doc, errors)
    elif args.kind == "loops_index":
        validate_loops_index(doc, errors)
    else:
        validate_node_runtime(doc, errors)

    # Bonus jsonschema layer, merged in (deduplicated against hand-rolled errors).
    schema_errors: list[str] = []
    run_jsonschema_bonus(doc, args.kind, schema_errors)
    for msg in schema_errors:
        if msg not in errors:
            errors.append(msg)

    if errors:
        for msg in errors:
            print(msg, file=sys.stderr)
        print(f"error: {args.file} is invalid ({len(errors)} problem(s))", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
