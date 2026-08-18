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

The individual rule checks live in the `checks/` package (one module per
concern); this file owns argparse, the per-kind dispatch, the plan-level
orchestration (R18 + plan/termination required fields), and the jsonschema
bonus layer. Exit codes: 0 valid, 1 structural/graph error(s), 2 load/usage
error.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import math
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

from checks import (
    ASSURANCE_CLASSES,
    CONTRACT_REQUIRED,
    GATE_KINDS,
    HIP_ANSWER_FORMATS,
    HIP_DEFAULT_MODES,
    HIP_REQUIRED_WHEN_TOKENS,
    LEDGER_ENTRY_REQUIRED,
    LEDGER_REQUIRED,
    NODE_STATUSES,
    ON_FAILURE,
    PLAN_REQUIRED,
)
from checks.gates import check_gate
from checks.index import validate_loops_index, validate_index_reconciliation
from checks.meta import validate_loop_meta
from checks.nodes import validate_nodes_recursive
from checks.provenance import (
    check_evidence_identity,
    check_ledger_node_resolution,
    check_goal_citation_resolution,
    check_ledger_verifier_independence,
    check_plan_provenance,
)
from checks.claim import validate_claim
from checks.caps import check_caps, check_contract_cost
from checks.retirement import check_retirement
from checks.artifact_index import validate_artifact_index
from checks.event_log import validate_event_log
from checks.loop_state import validate_loop_state
from checks.runtime import validate_node_runtime
from validate_checkpoint import (
    validate_checkpoint_schema,
    validate_consistency,
    validate_transition_closure,
)

SCHEMA_BY_KIND: dict[str, str] = {
    "loop_plan": "loop.plan.schema.json",
    "node_contract": "node.contract.schema.json",
    "evidence_ledger": "evidence.ledger.schema.json",
    "loop_meta": "loop.meta.schema.json",
    "loops_index": "loops.index.schema.json",
    "node_runtime": "node.runtime.schema.json",
    "claim": "claim.schema.json",
    "event_log": "event_log.schema.json",
    "loop_state": "loop.state.schema.json",
    "artifact_index": "artifact.index.schema.json",
    "checkpoint": "checkpoint.schema.json",
}

LEDGER_ALLOWED_FIELDS: frozenset[str] = frozenset({
    "schema_version", "entries", "relations",
})
LEDGER_ENTRY_ALLOWED_FIELDS: frozenset[str] = frozenset({
    *LEDGER_ENTRY_REQUIRED,
    "producer_claim_path", "review_context", "success_criteria_id",
    "overrides_entry_id", "supersedes", "status", "superseded_by",
})
LEDGER_RELATION_ALLOWED_FIELDS: frozenset[str] = frozenset({
    "relation_id", "source_entry_id", "target_entry_id", "relation", "reason",
})
RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _unexpected_mapping_keys(
    value: dict[Any, Any],
    allowed: frozenset[str] | set[str],
    scope: str,
    errors: list[str],
) -> None:
    non_string = sorted((key for key in value if not isinstance(key, str)), key=repr)
    if non_string:
        errors.append(
            f"[R38 EVIDENCE-SHAPE] {scope}: mapping keys must be strings; "
            f"found {non_string!r}"
        )
    unexpected = sorted(
        (key for key in value if isinstance(key, str) and key not in allowed)
    )
    if unexpected:
        errors.append(
            f"[R38 EVIDENCE-SHAPE] {scope}: unexpected field(s) {unexpected!r}"
        )


def _validate_ledger_timestamp(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not RFC3339_RE.fullmatch(value):
        errors.append(f"[R38 EVIDENCE-SHAPE] {label} must be a valid RFC 3339 date-time")
        return
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"[R38 EVIDENCE-SHAPE] {label} must be a valid RFC 3339 date-time")
        return
    if parsed.tzinfo is None:
        errors.append(f"[R38 EVIDENCE-SHAPE] {label} must include a timezone")


def _validate_review_context(value: Any, scope: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"[R38 EVIDENCE-SHAPE] {scope} must be an object")
        return
    _unexpected_mapping_keys(
        value,
        {"review_id", "delivered_context_sha256", "producer_claim_access"},
        scope,
        errors,
    )
    review_id = value.get("review_id")
    if not isinstance(review_id, str) or not review_id:
        errors.append(f"[R38 EVIDENCE-SHAPE] {scope}.review_id must be a non-empty string")
    digest = value.get("delivered_context_sha256")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        errors.append(
            f"[R38 EVIDENCE-SHAPE] {scope}.delivered_context_sha256 must be a lowercase SHA-256"
        )
    access = value.get("producer_claim_access")
    if access not in {"withheld", "available", "unknown"}:
        errors.append(
            f"[R38 EVIDENCE-SHAPE] {scope}.producer_claim_access must be withheld, available, or unknown"
        )


def _validate_ledger_entry_shape(entry: dict[str, Any], idx: int, errors: list[str]) -> None:
    scope = f"ledger entry[{idx}]"
    _unexpected_mapping_keys(entry, LEDGER_ENTRY_ALLOWED_FIELDS, scope, errors)
    for field in ("entry_id", "node_id"):
        if not isinstance(entry.get(field), str) or not entry.get(field):
            errors.append(f"[R38 EVIDENCE-SHAPE] {scope}.{field} must be a non-empty string")
    for field in ("gate_kind", "verdict", "verifier", "assurance"):
        if not isinstance(entry.get(field), str):
            errors.append(f"[R38 EVIDENCE-SHAPE] {scope}.{field} must be a string")
    artifact_path = entry.get("artifact_path")
    if not isinstance(artifact_path, str) or not artifact_path:
        errors.append(
            f"[R38 EVIDENCE-SHAPE] {scope}.artifact_path must be a non-empty string"
        )
    if not isinstance(entry.get("rationale"), str):
        errors.append(f"[R38 EVIDENCE-SHAPE] {scope}.rationale must be a string")
    _validate_ledger_timestamp(entry.get("recorded"), f"{scope}.recorded", errors)
    score = entry.get("score")
    if score is not None and (
        not isinstance(score, (int, float))
        or isinstance(score, bool)
        or (isinstance(score, float) and not math.isfinite(score))
        or score < 0
        or score > 1
    ):
        errors.append(
            f"[R38 EVIDENCE-SHAPE] {scope}.score must be null or a number from 0 to 1"
        )
    for field in (
        "producer_claim_path", "success_criteria_id", "overrides_entry_id",
    ):
        if field in entry and not isinstance(entry.get(field), str):
            errors.append(f"[R38 EVIDENCE-SHAPE] {scope}.{field} must be a string")
    for field in ("supersedes", "superseded_by"):
        if field in entry and entry.get(field) is not None and not isinstance(entry.get(field), str):
            errors.append(
                f"[R38 EVIDENCE-SHAPE] {scope}.{field} must be a string or null"
            )
    if "status" in entry and not isinstance(entry.get("status"), str):
        errors.append(f"[R38 EVIDENCE-SHAPE] {scope}.status must be a string")
    if "review_context" in entry:
        _validate_review_context(entry.get("review_context"), f"{scope}.review_context", errors)


def _validate_ledger_relation_shape(relation: dict[str, Any], idx: int, errors: list[str]) -> None:
    scope = f"ledger.relations[{idx}]"
    _unexpected_mapping_keys(relation, LEDGER_RELATION_ALLOWED_FIELDS, scope, errors)
    for field in (
        "relation_id", "source_entry_id", "target_entry_id", "relation", "reason",
    ):
        if not isinstance(relation.get(field), str) or not relation.get(field):
            errors.append(
                f"[R38 EVIDENCE-SHAPE] {scope}.{field} must be a non-empty string"
            )


def validate_evidence_ledger_shape(doc: Any, errors: list[str]) -> None:
    """Validate the exact ledger envelope before semantic consumers run."""
    if not isinstance(doc, dict):
        errors.append("[R5 MISSING REQUIRED FIELD] ledger: document is not a mapping")
        return
    _unexpected_mapping_keys(doc, LEDGER_ALLOWED_FIELDS, "ledger", errors)
    for field in LEDGER_REQUIRED:
        if field not in doc:
            errors.append(f"[R5 MISSING REQUIRED FIELD] ledger: missing field {field!r}")
    if not isinstance(doc.get("schema_version"), str):
        errors.append("[R38 EVIDENCE-SHAPE] ledger.schema_version must be a string")
    entries = doc.get("entries")
    if not isinstance(entries, list):
        errors.append("[R38 EVIDENCE-SHAPE] ledger.entries must be a list")
        return
    for idx, entry in enumerate(entries):
        scope = f"ledger entry[{idx}]"
        if not isinstance(entry, dict):
            errors.append(f"[R5 MISSING REQUIRED FIELD] {scope}: not a mapping")
            continue
        _validate_ledger_entry_shape(entry, idx, errors)
        for field in LEDGER_ENTRY_REQUIRED:
            if field not in entry:
                if field == "assurance":
                    errors.append(
                        f"[R44 MISSING-ASSURANCE] {scope}: declared assurance field is "
                        "absent; this establishes field absence only and does not license "
                        "any conclusion about evidence adequacy or correctness"
                    )
                else:
                    errors.append(f"[R5 MISSING REQUIRED FIELD] {scope}: missing {field!r}")
    relations = doc.get("relations", [])
    if not isinstance(relations, list):
        errors.append("[R38 EVIDENCE-SHAPE] ledger.relations must be a list when present")
        return
    for idx, relation in enumerate(relations):
        if not isinstance(relation, dict):
            errors.append(
                f"[R38 EVIDENCE-SHAPE] ledger.relations[{idx}] must be an object"
            )
            continue
        _validate_ledger_relation_shape(relation, idx, errors)


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
    check_plan_provenance(doc, errors)
    check_caps(doc, errors)
    check_retirement(doc, errors)
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
    shape_errors: list[str] = []
    validate_evidence_ledger_shape(doc, shape_errors)
    errors.extend(shape_errors)
    if not isinstance(doc, dict):
        return
    entries = doc.get("entries")
    if not isinstance(entries, list):
        return
    valid_verdicts = {"pass", "fail", "inconclusive"}
    valid_verifiers = {"agent", "subagent", "user", "script"}
    valid_status = {"active", "challenged", "superseded", "stale", "invalid", "retired"}
    ids = {
        e.get("entry_id")
        for e in entries
        if isinstance(e, dict) and isinstance(e.get("entry_id"), str)
    }
    for idx, entry in enumerate(entries):
        scope = f"ledger entry[{idx}]"
        if not isinstance(entry, dict):
            errors.append(f"[R5 MISSING REQUIRED FIELD] {scope}: not a mapping")
            continue
        if "assurance" in entry and (
            not isinstance(entry.get("assurance"), str)
            or entry.get("assurance") not in ASSURANCE_CLASSES
        ):
            errors.append(
                f"[R44 MISSING-ASSURANCE] {scope}: declared assurance "
                f"{entry.get('assurance')!r} is not one of "
                f"{sorted(ASSURANCE_CLASSES)}; this checks the literal enum only "
                "and does not license any conclusion about evidence adequacy or "
                "correctness"
            )
        if "gate_kind" in entry and (
            not isinstance(entry.get("gate_kind"), str)
            or entry.get("gate_kind") not in GATE_KINDS
        ):
            errors.append(f"[R7 BAD GATE KIND] {scope}: gate_kind {entry.get('gate_kind')!r} invalid")
        if "verdict" in entry and (
            not isinstance(entry.get("verdict"), str)
            or entry.get("verdict") not in valid_verdicts
        ):
            errors.append(f"[R4 BAD VERDICT] {scope}: verdict {entry.get('verdict')!r} invalid")
        if "verifier" in entry and (
            not isinstance(entry.get("verifier"), str)
            or entry.get("verifier") not in valid_verifiers
        ):
            errors.append(f"[R4 BAD VERIFIER] {scope}: verifier {entry.get('verifier')!r} invalid")
        status = entry.get("status")
        if status is not None and (
            not isinstance(status, str) or status not in valid_status
        ):
            errors.append(
                f"[R38 EVIDENCE-LIFECYCLE] {scope}: status {status!r} is not one of "
                f"{sorted(valid_status)}"
            )
        sb = entry.get("superseded_by")
        if isinstance(sb, str) and sb and sb not in ids:
            errors.append(
                f"[R38 EVIDENCE-LIFECYCLE] {scope}: superseded_by {sb!r} references no "
                f"existing entry_id"
            )
        # Verdicts are immutable observations. Lifecycle changes are append-only
        # relations; an old pass remains a historical pass but cannot be current.
    if not shape_errors:
        check_evidence_identity(doc, errors)
        check_ledger_verifier_independence(doc, {}, errors)


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
            "loops_index", "node_runtime", "claim", "event_log", "loop_state",
            "artifact_index", "checkpoint",
        ),
        default="loop_plan",
        help="Artifact kind (default: loop_plan).",
    )
    parser.add_argument("file", help="Path to the YAML artifact.")
    parser.add_argument("--plan", help="For --kind evidence_ledger: the loop.plan for R36 verifier-independence cross-check.")
    parser.add_argument("--root", help="For --kind loops_index: dir the INDEX paths are relative to (R37 reconciliation).")
    args = parser.parse_args()

    doc = load_yaml(args.file)
    errors: list[str] = []

    if args.kind == "loop_plan":
        validate_loop_plan(doc, errors)
    elif args.kind == "node_contract":
        validate_flat_status_and_gate(doc, CONTRACT_REQUIRED, errors)
        check_contract_cost(doc, errors)
    elif args.kind == "evidence_ledger":
        shape_errors: list[str] = []
        validate_evidence_ledger_shape(doc, shape_errors)
        validate_evidence_ledger(doc, errors)
        if args.plan and not shape_errors:
            plan = load_yaml(args.plan)
            check_ledger_node_resolution(doc, plan, errors)
            check_goal_citation_resolution(doc, plan, errors)
    elif args.kind == "loop_meta":
        validate_loop_meta(doc, errors)
    elif args.kind == "loops_index":
        validate_loops_index(doc, errors)
        if args.root:
            validate_index_reconciliation(doc, args.root, errors)
    elif args.kind == "node_runtime":
        validate_node_runtime(doc, errors)
    elif args.kind == "claim":
        validate_claim(doc, errors)
    elif args.kind == "event_log":
        validate_event_log(doc, errors)
    elif args.kind == "loop_state":
        validate_loop_state(doc, errors)
    elif args.kind == "checkpoint":
        validate_checkpoint_schema(doc, errors)
        if args.plan:
            plan = load_yaml(args.plan)
            validate_consistency(doc, plan, args.plan, errors)
            validate_transition_closure(doc, plan, errors)
    else:
        validate_artifact_index(doc, errors)

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
