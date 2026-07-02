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
    CONTRACT_REQUIRED,
    GATE_KINDS,
    HIP_ANSWER_FORMATS,
    HIP_DEFAULT_MODES,
    HIP_REQUIRED_WHEN_TOKENS,
    LEDGER_REQUIRED,
    NODE_STATUSES,
    ON_FAILURE,
    PLAN_REQUIRED,
)
from checks.gates import check_gate
from checks.index import validate_loops_index, validate_index_reconciliation
from checks.meta import validate_loop_meta
from checks.nodes import validate_nodes_recursive
from checks.provenance import check_plan_provenance, check_ledger_verifier_independence
from checks.claim import validate_claim
from checks.caps import check_caps, check_contract_cost
from checks.event_log import validate_event_log
from checks.loop_state import validate_loop_state
from checks.runtime import validate_node_runtime

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
        validate_evidence_ledger(doc, errors)
        if args.plan:
            check_ledger_verifier_independence(doc, load_yaml(args.plan), errors)
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
    else:
        validate_loop_state(doc, errors)

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
