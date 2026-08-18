#!/usr/bin/env python3
"""Plan and guard the prospective create-loop v1/v2 paired experiment.

Validation and planning are read-only by default. The execute command is a
separate, fail-closed boundary and is intentionally unusable until the frozen
preregistration records an authorized budget and model configuration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parents[1]
SCHEMA_RUNTIME = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCHEMA_RUNTIME))

from schema_runtime import SchemaError, check_schema, validate  # noqa: E402
from snapshot_tools import (  # noqa: E402
    EXPERIMENT_INSTRUMENT_INPUTS,
    REQUIRED_INSTRUMENT_ROLES,
    SnapshotError,
    instrument_manifest_sha256,
    validate_instrument_manifest,
    validate_source_snapshot,
)
from workspace_builder import (  # noqa: E402
    CANONICAL_FIXTURES,
    PRESENTED_SCHEMA,
    TOOL_PROFILE_SCHEMA,
    WORKSPACE_SCHEMA,
    WorkspaceError,
    _builtin_files as builtin_fixture_files,
    build_manifest as build_workspace_manifest,
    canonical_bytes as workspace_canonical_bytes,
    load_json as load_workspace_json,
    sha256_file as workspace_sha256_file,
    validate_tool_profile,
    validate_workspace as validate_materialized_workspace,
)


SCHEMA_FILES = {
    "scenarios": "scenarios.schema.json",
    "preregistration": "preregistration.schema.json",
    "source_snapshot": "source-snapshot.schema.json",
    "instrument_manifest": "instrument-manifest.schema.json",
    "trace": "trace.schema.json",
    "blind_review": "blind-review-manifest.schema.json",
    "workspace_manifest": "workspace-manifest.schema.json",
    "tool_profile": "tool-profile.schema.json",
    "presented_artifact": "presented-artifact.schema.json",
    "report": "report.schema.json",
    "final_workspace": "final-workspace-manifest.schema.json",
    "evidence_manifest": "evidence-manifest.schema.json",
}
CANONICAL_SCENARIO_SLUGS = [
    "simple-short-task",
    "multi-stage-development",
    "research-to-design",
    "blank-session-resume",
    "valid-shape-wrong-content",
    "good-content-invalid-structure",
    "assumption-refuted",
    "conflicting-external-evidence",
    "repeated-tool-failure",
    "non-idempotent-interruption",
    "concurrent-write-conflict",
    "authorization-boundary",
    "mechanisms-green-goal-unmet",
    "counterevidence-after-completion",
]
EXPECTED_METRICS = {
    "goal_quality",
    "blind_pairwise_preference",
    "severe_regression",
    "adversarial_false_completion",
    "real_task_false_completion",
    "authorization_or_effect_omissions",
    "deterministic_rejection_accuracy",
    "deterministic_safety_fixtures_pass_rate",
    "cold_start_fact_accuracy",
    "interruption_recovery_cost",
    "control_write_count",
    "control_context_share",
    "first_high_value_action_seconds",
    "productive_work_share",
    "unnecessary_user_interruptions",
}
EXPECTED_GATES = {
    "adversarial_false_completion_v2_max",
    "real_task_false_completion_ratio_to_v1_max",
    "authorization_or_effect_omissions_v2_max",
    "cold_start_fact_accuracy_v2_min",
    "control_writes_ratio_to_v1_max",
    "control_context_ratio_to_v1_max",
    "control_context_share_total_max",
    "first_high_value_action_ratio_to_v1_max",
    "productive_work_share_gain_points_min",
    "recovery_cost_ratio_to_v1_max",
    "blind_preference_v2_min",
    "severe_regression_v2_max",
    "unnecessary_interruptions_not_above_v1",
    "deterministic_safety_fixtures_pass_rate_min",
}
IMPLEMENTED_OFFLINE_CAPABILITIES = {
    "concrete workspace, oracle, reviewer, and deterministic input schemas are implemented",
    "offline metric and gate formulas are implemented",
}
EXECUTION_BLOCKERS: set[str] = set()
FORMAL_EXECUTION_ENABLED = False


class ExperimentError(RuntimeError):
    """A bounded experiment invariant failed."""


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant {value!r}")

    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle, parse_constant=reject_constant)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ExperimentError(f"cannot read JSON {path}: {exc}") from exc


def parse_timestamp(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExperimentError(f"{label} must be RFC 3339") from exc
    if parsed.utcoffset() is None:
        raise ExperimentError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate_schema(instance: Any, schema_path: Path, label: str) -> None:
    schema = load_json(schema_path)
    try:
        errors = validate(instance, schema)
    except SchemaError as exc:
        raise ExperimentError(f"{label} schema is unsupported: {exc}") from exc
    if errors:
        raise ExperimentError(f"{label} schema validation failed: {'; '.join(errors)}")


def resolve_local_file(base: Path, relative: str, label: str) -> Path:
    posix = PurePosixPath(relative)
    if posix.is_absolute() or ".." in posix.parts or "\\" in relative:
        raise ExperimentError(f"{label} path must remain below {base}")
    candidate = (base / Path(*posix.parts)).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError as exc:
        raise ExperimentError(f"{label} path escapes {base}") from exc
    return candidate


def scenario_input_hash(scenario: dict[str, Any]) -> str:
    return sha256_bytes(canonical_bytes(scenario["input"]))


def validate_scenarios(experiment_dir: Path, scenarios: dict[str, Any]) -> None:
    validate_schema(scenarios, experiment_dir / SCHEMA_FILES["scenarios"], "scenarios")
    actual_ids = [item["id"] for item in scenarios["scenarios"]]
    actual_slugs = [item["slug"] for item in scenarios["scenarios"]]
    if actual_ids != list(range(1, 15)):
        raise ExperimentError("scenarios must contain ordered IDs 1 through 14 exactly once")
    if actual_slugs != CANONICAL_SCENARIO_SLUGS:
        raise ExperimentError("scenario slugs or order drifted from the canonical 14-scenario set")
    for scenario in scenarios["scenarios"]:
        expected = scenario_input_hash(scenario)
        if scenario["input_sha256"] != expected:
            raise ExperimentError(f"scenario {scenario['id']} input_sha256 mismatch")
        overlap = set(scenario["oracle"]["required"]) & set(scenario["oracle"]["forbidden"])
        if overlap:
            raise ExperimentError(f"scenario {scenario['id']} oracle contradicts itself: {sorted(overlap)}")
    fixtures = {scenario["input"]["fixture"] for scenario in scenarios["scenarios"]}
    if fixtures != CANONICAL_FIXTURES:
        raise ExperimentError("scenario fixture set drifted from the canonical offline builders")


def validate_schema_documents(experiment_dir: Path) -> None:
    for label, filename in SCHEMA_FILES.items():
        schema = load_json(experiment_dir / filename)
        try:
            check_schema(schema)
        except SchemaError as exc:
            raise ExperimentError(f"{label} schema is unsupported: {exc}") from exc


def validate_source_binding(
    experiment_dir: Path,
    binding: dict[str, Any],
    *,
    expected_protocol: str,
    current_worktree: bool,
) -> dict[str, Any]:
    manifest_path = resolve_local_file(experiment_dir, binding["manifest"]["path"], f"{expected_protocol} source manifest")
    if sha256_file(manifest_path) != binding["manifest"]["sha256"]:
        raise ExperimentError(f"{expected_protocol} source manifest file hash drifted")
    manifest = load_json(manifest_path)
    archive_bytes: bytes | None = None
    archive_binding = binding.get("archive")
    if archive_binding is not None:
        archive_path = resolve_local_file(experiment_dir, archive_binding["path"], f"{expected_protocol} source archive")
        if sha256_file(archive_path) != archive_binding["sha256"]:
            raise ExperimentError(f"{expected_protocol} source archive hash drifted")
        archive_bytes = archive_path.read_bytes()
    try:
        validate_source_snapshot(
            manifest,
            archive_bytes=archive_bytes,
            skill_root=SKILL_ROOT if current_worktree else None,
            repo_root=SKILL_ROOT.parents[1] if current_worktree else None,
        )
    except SnapshotError as exc:
        raise ExperimentError(f"{expected_protocol} source snapshot invalid: {exc}") from exc
    if manifest["protocol"] != expected_protocol or manifest["aggregate_sha256"] != binding["aggregate_sha256"]:
        raise ExperimentError(f"{expected_protocol} source snapshot binding drifted")
    origin = manifest["origin"]
    actual_commit = origin.get("commit", origin.get("base_git_commit"))
    if actual_commit != binding["origin_commit"]:
        raise ExperimentError(f"{expected_protocol} source origin commit drifted")
    return manifest


def validate_instrument_binding(
    experiment_dir: Path,
    preregistration: dict[str, Any],
    source_aggregates: set[str],
) -> dict[str, Any]:
    binding = preregistration["instrument_manifest"]
    manifest_path = resolve_local_file(experiment_dir, binding["path"], "instrument manifest")
    manifest = load_json(manifest_path)
    if instrument_manifest_sha256(manifest) != binding["sha256"]:
        raise ExperimentError("instrument manifest binding hash drifted")
    try:
        validate_instrument_manifest(
            experiment_dir,
            manifest,
            expected_inputs=EXPERIMENT_INSTRUMENT_INPUTS,
        )
    except SnapshotError as exc:
        raise ExperimentError(f"instrument manifest invalid: {exc}") from exc
    roles = {entry["role"] for entry in manifest["files"]}
    if not REQUIRED_INSTRUMENT_ROLES <= roles:
        raise ExperimentError("instrument manifest required role set drifted")
    if set(manifest["source_snapshots"]) != source_aggregates:
        raise ExperimentError("instrument manifest source snapshot bindings drifted")
    return manifest


def validate_preregistration(experiment_dir: Path, preregistration: dict[str, Any], scenarios: dict[str, Any]) -> None:
    validate_schema(preregistration, experiment_dir / SCHEMA_FILES["preregistration"], "preregistration")
    scenario_binding = preregistration["scenario_manifest"]
    scenario_path = resolve_local_file(experiment_dir, scenario_binding["path"], "scenario manifest")
    if scenario_path != (experiment_dir / "scenarios.json").resolve():
        raise ExperimentError("preregistration must bind the canonical scenarios.json")
    if sha256_file(scenario_path) != scenario_binding["sha256"]:
        raise ExperimentError("scenario manifest hash does not match preregistration")
    if preregistration["pairing"]["pairs_per_scenario"] != scenarios["paired_runs_per_protocol"]:
        raise ExperimentError("pairing repetitions disagree with scenarios")
    expected_metrics = {metric for scenario in scenarios["scenarios"] for metric in scenario["metrics"]}
    declared_metrics = {
        metric
        for group in preregistration["metrics"].values()
        for metric in group
    }
    metric_occurrences = [
        metric
        for group in preregistration["metrics"].values()
        for metric in group
    ]
    if len(metric_occurrences) != len(declared_metrics):
        raise ExperimentError("preregistered metrics contain duplicates across groups")
    if declared_metrics != EXPECTED_METRICS:
        raise ExperimentError(
            f"preregistered metric set drifted: missing={sorted(EXPECTED_METRICS - declared_metrics)}, "
            f"extra={sorted(declared_metrics - EXPECTED_METRICS)}"
        )
    if expected_metrics - declared_metrics:
        raise ExperimentError(f"scenario metrics are not preregistered: {sorted(expected_metrics - declared_metrics)}")
    if set(preregistration["gates"]) != EXPECTED_GATES:
        raise ExperimentError("preregistered gate set drifted")
    review_binding = preregistration["review"]["manifest_schema"]
    review_path = resolve_local_file(experiment_dir, review_binding["path"], "blind review schema")
    if sha256_file(review_path) != review_binding["sha256"]:
        raise ExperimentError("blind review schema hash does not match preregistration")
    if preregistration["authorization"] != {
        "required_file": "authorization-grant.json",
        "schema_file": "authorization-grant.schema.json",
    }:
        raise ExperimentError("authorization grant descriptor drifted")
    tool_binding = preregistration["execution_config"]["tool_profile"]
    tool_path = resolve_local_file(experiment_dir, tool_binding["path"], "tool profile")
    if sha256_file(tool_path) != tool_binding["sha256"]:
        raise ExperimentError("tool profile file hash drifted")
    try:
        profile = validate_tool_profile(tool_path)
    except WorkspaceError as exc:
        raise ExperimentError(f"tool profile invalid: {exc}") from exc
    if profile["id"] != tool_binding["id"]:
        raise ExperimentError("tool profile ID drifted")
    baseline_source = validate_source_binding(
        experiment_dir,
        preregistration["baseline"]["source_snapshot"],
        expected_protocol="v1",
        current_worktree=False,
    )
    candidate_source = validate_source_binding(
        experiment_dir,
        preregistration["candidate"]["source_snapshot"],
        expected_protocol="v2",
        current_worktree=True,
    )
    validate_instrument_binding(
        experiment_dir,
        preregistration,
        {baseline_source["aggregate_sha256"], candidate_source["aggregate_sha256"]},
    )


def load_and_validate(experiment_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_schema_documents(experiment_dir)
    scenarios = load_json(experiment_dir / "scenarios.json")
    preregistration = load_json(experiment_dir / "preregistration.json")
    validate_scenarios(experiment_dir, scenarios)
    validate_preregistration(experiment_dir, preregistration, scenarios)
    validate_baseline_binding(preregistration)
    return scenarios, preregistration


def validate_baseline_binding(preregistration: dict[str, Any]) -> None:
    baseline = preregistration["baseline"]
    baseline_path = SKILL_ROOT / "tests" / "baselines" / "v1-8263f09.json"
    baseline_record = load_json(baseline_path)
    if baseline_record.get("commit") != baseline["source_snapshot"]["origin_commit"]:
        raise ExperimentError("baseline artifact commit does not match preregistration")
    actual = sha256_file(baseline_path)
    if actual != baseline["audit_record_sha256"]:
        raise ExperimentError("baseline commit artifact hash does not match preregistration")


def protocol_order(seed: int, scenario_id: int, repetition: int) -> list[str]:
    first = "v1" if (scenario_id + repetition + seed) % 2 == 0 else "v2"
    return [first, "v2" if first == "v1" else "v1"]


def pair_seed(order_seed: int, scenario_id: int, repetition: int) -> int:
    return int.from_bytes(
        hashlib.sha256(f"{order_seed}:{scenario_id}:{repetition}".encode("ascii")).digest()[:8],
        "big",
    )


def build_run_plan(
    scenarios: dict[str, Any],
    preregistration: dict[str, Any],
    *,
    experiment_dir: Path = HERE,
) -> dict[str, Any]:
    prereg_hash = sha256_bytes(canonical_bytes(preregistration))
    seed = preregistration["pairing"]["order_seed"]
    workspace_seed = preregistration["execution_config"]["workspace_seed"]
    runs = []
    for scenario in scenarios["scenarios"]:
        for repetition in range(1, scenarios["paired_runs_per_protocol"] + 1):
            pair_id = f"S{scenario['id']:02d}-P{repetition:02d}"
            seed_for_pair = pair_seed(workspace_seed, scenario["id"], repetition)
            for position, protocol in enumerate(protocol_order(seed, scenario["id"], repetition), start=1):
                try:
                    workspace_manifest, _, _ = build_workspace_manifest(
                        experiment_id=preregistration["experiment_id"],
                        pair_id=pair_id,
                        scenario=scenario,
                        protocol=protocol,
                        workspace_seed=seed_for_pair,
                        source_binding=preregistration[
                            "baseline" if protocol == "v1" else "candidate"
                        ]["source_snapshot"],
                        tool_profile_path=resolve_local_file(
                            experiment_dir,
                            preregistration["execution_config"]["tool_profile"]["path"],
                            "tool profile",
                        ),
                        tool_profile_root=experiment_dir,
                    )
                except WorkspaceError as exc:
                    raise ExperimentError(f"cannot bind workspace for {pair_id}-{protocol}: {exc}") from exc
                runs.append({
                    "run_id": f"{pair_id}-{protocol}",
                    "pair_id": pair_id,
                    "scenario_id": scenario["id"],
                    "scenario_slug": scenario["slug"],
                    "protocol": protocol,
                    "repetition": repetition,
                    "pair_position": position,
                    "pair_seed": seed_for_pair,
                    "input_sha256": scenario["input_sha256"],
                    "semantic_case_sha256": workspace_manifest["semantic_case_sha256"],
                    "workspace_manifest_sha256": sha256_bytes(workspace_canonical_bytes(workspace_manifest)),
                    "workspace_variant_sha256": workspace_manifest["variant_sha256"],
                    "protocol_source": workspace_manifest["protocol_source"],
                    "tool_profile": workspace_manifest["tool_profile"],
                })
    return {
        "schema_version": "1.0",
        "experiment_id": preregistration["experiment_id"],
        "preregistration_sha256": prereg_hash,
        "algorithm": "counterbalanced-parity-v1",
        "order_seed": seed,
        "pair_count": 42,
        "run_count": 84,
        "runs": runs,
    }


def validate_run_plan(
    plan: dict[str, Any],
    scenarios: dict[str, Any],
    preregistration: dict[str, Any],
    *,
    experiment_dir: Path = HERE,
) -> None:
    expected = build_run_plan(scenarios, preregistration, experiment_dir=experiment_dir)
    if plan != expected:
        raise ExperimentError("run plan does not match deterministic preregistration output")
    if len(plan["runs"]) != 84 or len({run["run_id"] for run in plan["runs"]}) != 84:
        raise ExperimentError("run plan must contain exactly 84 unique runs")
    pair_protocols: dict[str, list[str]] = {}
    position_counts = {"v1": [0, 0], "v2": [0, 0]}
    for run in plan["runs"]:
        pair_protocols.setdefault(run["pair_id"], []).append(run["protocol"])
        position_counts[run["protocol"]][run["pair_position"] - 1] += 1
    if len(pair_protocols) != 42 or any(sorted(protocols) != ["v1", "v2"] for protocols in pair_protocols.values()):
        raise ExperimentError("run plan must contain 42 complete v1/v2 pairs")
    if any(abs(counts[0] - counts[1]) > 1 for counts in position_counts.values()):
        raise ExperimentError("run order is not balanced across protocols")
    for pair_id in pair_protocols:
        pair = [run for run in plan["runs"] if run["pair_id"] == pair_id]
        if len({run["pair_seed"] for run in pair}) != 1:
            raise ExperimentError("paired runs must share one deterministic pair seed")
        if len({run["semantic_case_sha256"] for run in pair}) != 1:
            raise ExperimentError("paired runs must share one semantic case hash")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(json.dumps(value, indent=2, ensure_ascii=False).encode("utf-8") + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def validate_workspace_binding(
    experiment_dir: Path,
    binding: dict[str, Any],
    expected_run: dict[str, Any],
    preregistration: dict[str, Any],
    *,
    workspace_root: Path | None = None,
    binding_root: Path | None = None,
) -> dict[str, Any]:
    manifest_path = resolve_local_file(binding_root or experiment_dir, binding["path"], "workspace manifest")
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ExperimentError("workspace manifest must be a regular non-symlink file")
    if sha256_file(manifest_path) != binding["sha256"]:
        raise ExperimentError("workspace manifest file hash drifted")
    manifest = load_json(manifest_path)
    validate_schema(manifest, experiment_dir / SCHEMA_FILES["workspace_manifest"], "workspace manifest")
    expected_fields = {
        "experiment_id": preregistration["experiment_id"],
        "pair_id": expected_run["pair_id"],
        "scenario_id": expected_run["scenario_id"],
        "scenario_slug": expected_run["scenario_slug"],
        "protocol": expected_run["protocol"],
        "workspace_seed": expected_run["pair_seed"],
        "input_sha256": expected_run["input_sha256"],
        "semantic_case_sha256": expected_run["semantic_case_sha256"],
        "variant_sha256": expected_run["workspace_variant_sha256"],
        "protocol_source": expected_run["protocol_source"],
        "tool_profile": expected_run["tool_profile"],
    }
    for field, value in expected_fields.items():
        if manifest[field] != value:
            raise ExperimentError(f"workspace manifest {field} drifted from run plan")
    if binding["sha256"] != expected_run["workspace_manifest_sha256"]:
        raise ExperimentError("workspace manifest hash drifted from run plan")
    if manifest["builder_sha256"] != workspace_sha256_file(experiment_dir / "workspace_builder.py"):
        raise ExperimentError("workspace manifest builder hash drifted")
    if workspace_root is not None:
        try:
            validate_materialized_workspace(workspace_root.resolve(), manifest)
        except WorkspaceError as exc:
            raise ExperimentError(f"materialized workspace invalid: {exc}") from exc
    return manifest


def validate_presented_artifact_binding(
    review_root: Path,
    binding: dict[str, Any],
    *,
    trace: dict[str, Any],
    workspace_manifest: dict[str, Any],
    schema_root: Path | None = None,
) -> dict[str, Any]:
    path = resolve_local_file(review_root, binding["path"], "presented artifact manifest")
    if not path.is_file() or path.is_symlink():
        raise ExperimentError("presented artifact manifest must be a regular non-symlink file")
    if sha256_file(path) != binding["sha256"]:
        raise ExperimentError("presented artifact manifest file hash drifted")
    artifact = load_json(path)
    validate_schema(artifact, (schema_root or HERE) / PRESENTED_SCHEMA.name, "presented artifact manifest")
    workspace_hash = trace["workspace_manifest"]["sha256"]
    expected = {
        "scenario_id": trace["scenario_id"],
        "scenario_slug": trace["scenario_slug"],
        "semantic_case_sha256": trace["semantic_case_sha256"],
        "workspace_manifest_sha256": workspace_hash,
    }
    for field, value in expected.items():
        if artifact[field] != value:
            raise ExperimentError(f"presented artifact {field} drifted from trace")
    _, declared_paths = builtin_fixture_files(workspace_manifest["fixture_id"], workspace_manifest["protocol"])
    if {item["path"] for item in artifact["files"]} != set(declared_paths):
        raise ExperimentError("presented artifact path set drifted from the fixture declaration")
    for item in artifact["files"]:
        actual = resolve_local_file(path.parent, item["path"], "presented artifact file")
        if not actual.is_file() or actual.is_symlink():
            raise ExperimentError("presented artifact file must be a regular non-symlink file")
        if sha256_file(actual) != item["sha256"] or actual.stat().st_size != item["size"]:
            raise ExperimentError("presented artifact file hash or size drifted")
    if artifact["aggregate_sha256"] != sha256_bytes(workspace_canonical_bytes(artifact["files"])):
        raise ExperimentError("presented artifact aggregate hash drifted")
    return artifact


def _validate_trace(
    experiment_dir: Path,
    trace_path: Path,
    run_plan: dict[str, Any],
    preregistration: dict[str, Any],
    *,
    adapter_path: Path | None = None,
    authorization_path: Path | None = None,
    execution_root: Path | None = None,
    execution_snapshot: object | None = None,
    workspace_root: Path | None = None,
    binding_root: Path | None = None,
) -> dict[str, Any]:
    trace = load_json(trace_path)
    validate_schema(trace, experiment_dir / SCHEMA_FILES["trace"], "trace")
    run_by_id = {run["run_id"]: run for run in run_plan["runs"]}
    expected = run_by_id.get(trace["run_id"])
    if expected is None:
        raise ExperimentError(f"trace has unknown run_id {trace['run_id']}")
    if trace["experiment_id"] != preregistration["experiment_id"]:
        raise ExperimentError("trace experiment_id drifted")
    for field in (
        "pair_id", "scenario_id", "scenario_slug", "protocol", "repetition", "pair_position",
        "pair_seed", "input_sha256", "semantic_case_sha256", "tool_profile",
    ):
        if trace[field] != expected[field]:
            raise ExperimentError(f"trace {trace['run_id']} field {field} drifted from run plan")
    if trace["preregistration_sha256"] != run_plan["preregistration_sha256"]:
        raise ExperimentError("trace preregistration hash drifted")
    if trace["run_plan_sha256"] != sha256_bytes(canonical_bytes(run_plan)):
        raise ExperimentError("trace run plan hash drifted")
    config = preregistration["execution_config"]
    if trace["model"] != config["model"] or trace["reasoning_effort"] != config["reasoning_effort"]:
        raise ExperimentError("trace model configuration drifted")
    if trace["tool_profile"] != config["tool_profile"] or trace["workspace_seed"] != expected["pair_seed"]:
        raise ExperimentError("trace tool profile or workspace seed drifted")
    initial_manifest = validate_workspace_binding(
        experiment_dir,
        trace["workspace_manifest"],
        expected,
        preregistration,
        workspace_root=workspace_root,
        binding_root=binding_root or trace_path.parent,
    )
    if trace["initial_workspace_manifest_sha256"] != trace["workspace_manifest"]["sha256"]:
        raise ExperimentError("trace initial workspace manifest hash drifted")
    artifact_root = binding_root or trace_path.parent
    final_workspace_path = resolve_local_file(
        artifact_root, trace["final_workspace_manifest"]["path"], "trace final workspace manifest"
    )
    if not final_workspace_path.is_file() or final_workspace_path.is_symlink():
        raise ExperimentError("trace final workspace manifest must be a regular non-symlink file")
    if sha256_file(final_workspace_path) != trace["final_workspace_manifest"]["sha256"]:
        raise ExperimentError("trace final workspace manifest hash drifted")
    final_workspace = load_json(final_workspace_path)
    validate_schema(final_workspace, experiment_dir / SCHEMA_FILES["final_workspace"], "final workspace manifest")
    if final_workspace["initial_manifest_sha256"] != trace["initial_workspace_manifest_sha256"]:
        raise ExperimentError("trace final workspace manifest does not bind the initial workspace")
    if trace["final_workspace_manifest_sha256"] != trace["final_workspace_manifest"]["sha256"]:
        raise ExperimentError("trace final workspace manifest source hash drifted")
    initial_paths = {item["path"]: item["sha256"] for item in initial_manifest["files"]}
    final_paths = {item["path"]: item["sha256"] for item in final_workspace["files"]}
    expected_changes = {
        "added": sorted(final_paths.keys() - initial_paths.keys()),
        "modified": sorted(
            path for path in initial_paths.keys() & final_paths.keys()
            if initial_paths[path] != final_paths[path]
        ),
        "deleted": sorted(initial_paths.keys() - final_paths.keys()),
    }
    if final_workspace["changes"] != expected_changes:
        raise ExperimentError("trace final workspace change set is not replayable")
    if final_workspace["aggregate_sha256"] != sha256_bytes(canonical_bytes(final_workspace["files"])):
        raise ExperimentError("trace final workspace aggregate hash drifted")

    evidence_manifest_path = resolve_local_file(
        artifact_root, trace["evidence_manifest"]["path"], "trace evidence manifest"
    )
    if not evidence_manifest_path.is_file() or evidence_manifest_path.is_symlink():
        raise ExperimentError("trace evidence manifest must be a regular non-symlink file")
    if sha256_file(evidence_manifest_path) != trace["evidence_manifest"]["sha256"]:
        raise ExperimentError("trace evidence manifest hash drifted")
    evidence_manifest = load_json(evidence_manifest_path)
    validate_schema(
        evidence_manifest,
        experiment_dir / SCHEMA_FILES["evidence_manifest"],
        "trace evidence manifest",
    )
    if trace["evidence_manifest_sha256"] != trace["evidence_manifest"]["sha256"]:
        raise ExperimentError("trace evidence manifest source hash drifted")
    if evidence_manifest["run_id"] != trace["run_id"] or evidence_manifest["episode_id"] != trace["episode_id"]:
        raise ExperimentError("trace evidence manifest call identity drifted")
    if evidence_manifest["role"] != trace["role"]:
        raise ExperimentError("trace evidence manifest role drifted")
    if evidence_manifest["initial_workspace_manifest"]["sha256"] != trace["initial_workspace_manifest_sha256"]:
        raise ExperimentError("trace evidence manifest initial workspace binding drifted")
    if evidence_manifest["final_workspace_manifest"]["sha256"] != trace["final_workspace_manifest_sha256"]:
        raise ExperimentError("trace evidence manifest final workspace binding drifted")
    if evidence_manifest["aggregate_sha256"] != sha256_bytes(canonical_bytes(evidence_manifest["files"])):
        raise ExperimentError("trace evidence manifest aggregate hash drifted")

    trace_source_path = resolve_local_file(
        artifact_root, trace["trace_source"]["path"], "trace source"
    )
    if not trace_source_path.is_file() or trace_source_path.is_symlink():
        raise ExperimentError("trace source must be a regular non-symlink file")
    if sha256_file(trace_source_path) != trace["trace_source"]["sha256"]:
        raise ExperimentError("trace source hash drifted")
    expected_sources = {
        "baseline_source_sha256": preregistration["baseline"]["source_snapshot"]["aggregate_sha256"],
        "candidate_source_sha256": preregistration["candidate"]["source_snapshot"]["aggregate_sha256"],
        "instrument_manifest_sha256": preregistration["instrument_manifest"]["sha256"],
    }
    for field, value in expected_sources.items():
        if trace[field] != value:
            raise ExperimentError(f"trace {field} drifted")
    if adapter_path is None or authorization_path is None or execution_root is None:
        raise ExperimentError("trace validation requires the bound adapter, authorization grant, and execution root")
    if not adapter_path.is_file() or adapter_path.is_symlink():
        raise ExperimentError("trace adapter must be a regular non-symlink file")
    adapter_sha256 = sha256_file(adapter_path)
    if trace["adapter"]["sha256"] != adapter_sha256:
        raise ExperimentError("trace adapter hash drifted")
    try:
        import execution_guard

        authorization = execution_guard.load_grant(authorization_path)
        guard_grant_path = execution_root.resolve() / "grant.json"
        if authorization_path.resolve() != guard_grant_path:
            raise ExperimentError("trace authorization must be the canonical grant inside the execution root")
        if execution_snapshot is None:
            summary = execution_guard.replay(execution_root.resolve())
        else:
            summary = execution_guard.summary_from_snapshot(
                execution_root.resolve(), execution_snapshot
            )
        execution_guard._validate_shape(summary, "summary")
        if summary["root_path_sha256"] != execution_guard._root_path_sha256(
            execution_root.resolve()
        ):
            raise ExperimentError("execution summary belongs to a different execution root")
        if (
            summary["authorization_id"] != authorization["authorization_id"]
            or summary["execution_id"] != authorization["execution_id"]
            or summary["grant_sha256"] != sha256_file(authorization_path)
        ):
            raise ExperimentError("execution summary belongs to a different authorization")
    except (ImportError, execution_guard.GuardError) as exc:
        raise ExperimentError(f"trace execution authority is invalid: {exc}") from exc
    expected_authorization = {
        "experiment_id": preregistration["experiment_id"],
        "preregistration_sha256": run_plan["preregistration_sha256"],
        "run_plan_sha256": sha256_bytes(canonical_bytes(run_plan)),
        "adapter": trace["adapter"],
        "role": trace["role"],
        "cli_identity": trace["cli_identity"],
        "provider_profile": trace["provider_profile"],
        "model": trace["model"],
        "reasoning_effort": trace["reasoning_effort"],
        "tool_profile": trace["tool_profile"],
    }
    for field, value in expected_authorization.items():
        if authorization[field] != value:
            raise ExperimentError(f"trace authorization {field} drifted")
    if {"run_id": trace["run_id"], "episode_id": trace["episode_id"]} not in authorization["authorized_calls"]:
        raise ExperimentError("trace run episode is outside the authorized call set")
    authority = trace["execution_authority"]
    if authority["grant_sha256"] != sha256_file(authorization_path):
        raise ExperimentError("trace execution authority grant drifted")
    ledger_paths = sorted((execution_root.resolve() / "ledger").glob("*.json"))
    authority_seq = authority["ledger_last_seq"]
    if authority_seq > len(ledger_paths):
        raise ExperimentError("trace execution authority sequence exceeds the durable ledger")
    authority_record_path = ledger_paths[authority_seq - 1]
    if sha256_file(authority_record_path) != authority["ledger_tail_sha256"]:
        raise ExperimentError("trace execution authority historical tail drifted")
    authority_record = load_json(authority_record_path)
    receipt_path = resolve_local_file(binding_root or trace_path.parent, trace["usage_receipt"]["path"], "trace usage receipt")
    if not receipt_path.is_file() or receipt_path.is_symlink():
        raise ExperimentError("trace usage receipt must be a regular non-symlink file")
    if sha256_file(receipt_path) != trace["usage_receipt"]["sha256"]:
        raise ExperimentError("trace usage receipt hash drifted")
    receipt = load_json(receipt_path)
    receipt_store = execution_root.resolve() / "receipts"
    canonical_receipt = receipt_store / f"receipt-{sha256_bytes(canonical_bytes(receipt))}.json"
    if receipt["evidence_manifest_sha256"] != trace["evidence_manifest_sha256"]:
        raise ExperimentError("trace usage receipt evidence binding drifted")
    try:
        execution_guard._validate_shape(receipt, "receipt")
        execution_guard._validate_receipt_binding(
            receipt, authorization, trace["run_id"], receipt["attempt_id"], trace["episode_id"]
        )
    except execution_guard.GuardError as exc:
        raise ExperimentError(f"trace usage receipt is invalid: {exc}") from exc
    if (
        authority_record["kind"] != "call_settled"
        or authority_record["run_id"] != trace["run_id"]
        or authority_record["episode_id"] != trace["episode_id"]
        or authority_record["attempt_id"] != receipt["attempt_id"]
        or authority_record["payload"].get("receipt_sha256") != sha256_file(canonical_receipt)
    ):
        raise ExperimentError("trace execution authority does not anchor its settlement")
    call_id = f"{trace['run_id']}:{trace['episode_id']}"
    if call_id not in summary["settled_call_ids"] or receipt["attempt_id"] not in summary["declared_attempt_ids"]:
        raise ExperimentError("trace usage receipt is not settled by the execution ledger")
    if not canonical_receipt.is_file() or canonical_receipt.is_symlink() or canonical_receipt.read_bytes() != canonical_bytes(receipt):
        raise ExperimentError("trace usage receipt is not the immutable receipt settled by the guard")
    budget = trace["budget"]
    expected_budget = {
        "total_tokens_limit": authorization["limits"]["per_call"]["max_total_tokens"],
        "seconds_limit": authorization["limits"]["per_call"]["max_wall_seconds"],
    }
    if any(budget[field] != value for field, value in expected_budget.items()):
        raise ExperimentError("trace declared budget drifted from preregistration")
    if [event["seq"] for event in trace["events"]] != list(range(1, len(trace["events"]) + 1)):
        raise ExperimentError("trace event sequence must be gapless and start at 1")
    event_kinds = [event["kind"] for event in trace["events"]]
    if event_kinds[0] != "adapter_started" or event_kinds[-1] != "adapter_finished":
        raise ExperimentError("trace must start and finish with adapter lifecycle events")
    started_at = parse_timestamp(trace["started_at"], "trace started_at")
    ended_at = parse_timestamp(trace["ended_at"], "trace ended_at")
    if ended_at < started_at:
        raise ExperimentError("trace ended_at precedes started_at")
    if not (
        parse_timestamp(authorization["authorized_at"], "trace authorized_at")
        <= started_at
        <= parse_timestamp(authorization["expires_at"], "trace expires_at")
    ):
        raise ExperimentError("trace started outside its authorization window")
    event_times = [parse_timestamp(event["ts"], f"trace event {event['seq']} ts") for event in trace["events"]]
    if event_times != sorted(event_times):
        raise ExperimentError("trace event timestamps must be monotonic")
    if event_times[0] < started_at or event_times[-1] > ended_at:
        raise ExperimentError("trace event timestamp falls outside the run interval")
    if budget["total_tokens_used"] > budget["total_tokens_limit"]:
        raise ExperimentError("trace token budget exceeded")
    if Decimal(str(budget["elapsed_seconds"])) > Decimal(budget["seconds_limit"]):
        raise ExperimentError("trace time budget exceeded")
    receipt_budget = {
        "total_tokens_used": receipt["usage"]["total_tokens"],
        "elapsed_seconds": receipt["usage"]["wall_seconds"],
    }
    if any(Decimal(str(budget[field])) != Decimal(str(value)) for field, value in receipt_budget.items()):
        raise ExperimentError("trace budget telemetry drifted from the settled usage receipt")
    evidence_hashes = {
        kind: [event["payload_sha256"] for event in trace["events"] if event["kind"] == kind]
        for kind in ("model_request", "model_response")
    }
    if evidence_hashes != {
        "model_request": [receipt["request_sha256"]],
        "model_response": [receipt["response_sha256"]],
    }:
        raise ExperimentError("trace request/response events do not bind the settled usage receipt")
    wall_seconds = Decimal(str((ended_at - started_at).total_seconds()))
    elapsed_seconds = Decimal(str(budget["elapsed_seconds"]))
    if abs(wall_seconds - elapsed_seconds) > Decimal("1"):
        raise ExperimentError("trace elapsed_seconds disagrees with wall-clock interval")
    outcome = trace["outcome"]
    scenarios = load_json(experiment_dir / "scenarios.json")["scenarios"]
    expected_metric_set = next(set(item["metrics"]) for item in scenarios if item["id"] == trace["scenario_id"])
    if set(outcome["metric_observations"]) != expected_metric_set:
        raise ExperimentError("trace metric observations must exactly match the scenario metric set")
    claim_events = event_kinds.count("completion_claim")
    if outcome["completion_claimed"] != (claim_events > 0):
        raise ExperimentError("trace completion_claimed disagrees with completion events")
    if outcome["status"] == "completed":
        if not outcome["completion_claimed"]:
            raise ExperimentError("completed trace requires a completion claim")
    if outcome["goal_satisfied"] is not None or trace["goal_satisfied"] is not None:
        raise ExperimentError("producer trace cannot decide goal_satisfied")
    return trace


def validate_trace(
    experiment_dir: Path,
    trace_path: Path,
    run_plan: dict[str, Any],
    preregistration: dict[str, Any],
    *,
    adapter_path: Path | None = None,
    authorization_path: Path | None = None,
    execution_root: Path | None = None,
    execution_snapshot: object | None = None,
    workspace_root: Path | None = None,
    binding_root: Path | None = None,
) -> dict[str, Any]:
    """Validate one trace against the execution authority as it exists now."""

    # Snapshots are reusable by design, so accepting one here would let a
    # standalone caller validate against authority bytes that have since drifted.
    if execution_snapshot is not None:
        raise ExperimentError(
            "execution_snapshot is private to the evaluation batch path"
        )

    return _validate_trace(
        experiment_dir,
        trace_path,
        run_plan,
        preregistration,
        adapter_path=adapter_path,
        authorization_path=authorization_path,
        execution_root=execution_root,
        workspace_root=workspace_root,
        binding_root=binding_root,
    )


def _validate_trace_with_execution_snapshot(
    experiment_dir: Path,
    trace_path: Path,
    run_plan: dict[str, Any],
    preregistration: dict[str, Any],
    *,
    adapter_path: Path,
    authorization_path: Path,
    execution_root: Path,
    execution_snapshot: object,
    workspace_root: Path | None = None,
    binding_root: Path | None = None,
) -> dict[str, Any]:
    """Private batch path; its caller must recheck authority after the batch."""

    return _validate_trace(
        experiment_dir,
        trace_path,
        run_plan,
        preregistration,
        adapter_path=adapter_path,
        authorization_path=authorization_path,
        execution_root=execution_root,
        execution_snapshot=execution_snapshot,
        workspace_root=workspace_root,
        binding_root=binding_root,
    )


def validate_trace_set(
    experiment_dir: Path,
    trace_paths: list[Path],
    run_plan: dict[str, Any],
    preregistration: dict[str, Any],
    *,
    adapter_path: Path,
    authorization_path: Path,
    execution_root: Path,
    binding_root: Path | None = None,
) -> None:
    expected_ids = {run["run_id"] for run in run_plan["runs"]}
    actual_ids: list[str] = []
    for trace_path in trace_paths:
        actual_ids.append(validate_trace(
            experiment_dir,
            trace_path,
            run_plan,
            preregistration,
            adapter_path=adapter_path,
            authorization_path=authorization_path,
            execution_root=execution_root,
            binding_root=binding_root,
        )["run_id"])
    duplicates = sorted({run_id for run_id in actual_ids if actual_ids.count(run_id) > 1})
    if duplicates:
        raise ExperimentError(f"duplicate traces: {duplicates}")
    actual_set = set(actual_ids)
    if actual_set != expected_ids:
        missing = sorted(expected_ids - actual_set)
        extra = sorted(actual_set - expected_ids)
        raise ExperimentError(f"trace set is incomplete or unexpected: missing={missing}, extra={extra}")


def blind_assignment(pair_id: str, assignment_seed: int) -> dict[str, str]:
    first = "v1" if (int(pair_id[1:3]) + int(pair_id[5:7]) + assignment_seed) % 2 == 0 else "v2"
    return {"A": first, "B": "v2" if first == "v1" else "v1"}


def validate_blind_review_manifest(
    experiment_dir: Path,
    manifest_path: Path,
    run_plan: dict[str, Any],
    preregistration: dict[str, Any],
    trace_paths: list[Path],
    review_root: Path,
    *,
    adapter_path: Path,
    authorization_path: Path,
    execution_root: Path,
) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    validate_schema(manifest, experiment_dir / SCHEMA_FILES["blind_review"], "blind review manifest")
    if manifest["experiment_id"] != preregistration["experiment_id"]:
        raise ExperimentError("blind review experiment_id drifted")
    if manifest["preregistration_sha256"] != run_plan["preregistration_sha256"]:
        raise ExperimentError("blind review preregistration hash drifted")
    if manifest["assignment_seed"] != preregistration["pairing"]["order_seed"]:
        raise ExperimentError("blind review assignment seed drifted")
    pair_runs = [run for run in run_plan["runs"] if run["pair_id"] == manifest["pair_id"]]
    if len(pair_runs) != 2 or manifest["scenario_id"] != pair_runs[0]["scenario_id"]:
        raise ExperimentError("blind review pair or scenario drifted")
    labels = [item["label"] for item in manifest["presented"]]
    if set(labels) != {"A", "B"} or len(labels) != 2:
        raise ExperimentError("blind review labels must be exactly A and B")
    assignment = blind_assignment(manifest["pair_id"], manifest["assignment_seed"])
    trace_by_protocol: dict[str, tuple[str, dict[str, Any], dict[str, Any]]] = {}
    expected_run_ids = {run["run_id"]: run["protocol"] for run in pair_runs}
    for trace_path in trace_paths:
        trace = load_json(trace_path)
        protocol = expected_run_ids.get(trace.get("run_id"))
        if protocol is not None:
            validated_trace = validate_trace(
                experiment_dir,
                trace_path,
                run_plan,
                preregistration,
                adapter_path=adapter_path,
                authorization_path=authorization_path,
                execution_root=execution_root,
                binding_root=trace_path.parent,
            )
            workspace_manifest = validate_workspace_binding(
                experiment_dir,
                validated_trace["workspace_manifest"],
                next(run for run in pair_runs if run["protocol"] == protocol),
                preregistration,
                binding_root=trace_path.parent,
            )
            trace_by_protocol[protocol] = (sha256_file(trace_path), validated_trace, workspace_manifest)
    if set(trace_by_protocol) != {"v1", "v2"}:
        raise ExperimentError("blind review requires both validated pair traces")
    for item in manifest["presented"]:
        protocol = assignment[item["label"]]
        trace_sha256, trace, workspace_manifest = trace_by_protocol[protocol]
        if item["trace_sha256"] != trace_sha256:
            raise ExperimentError("blind review trace assignment drifted")
        if item["presented_artifact"]["sha256"] == item["trace_sha256"]:
            raise ExperimentError("blind review artifact and trace hashes must identify distinct evidence")
        validate_presented_artifact_binding(
            review_root,
            item["presented_artifact"],
            trace=trace,
            workspace_manifest=workspace_manifest,
        )
    seen_context: set[str] = set()
    for item in manifest["delivered_context"]:
        path = resolve_local_file(review_root, item["path"], "blind review context")
        if not path.is_file() or path.is_symlink():
            raise ExperimentError("blind review context must be a regular non-symlink file")
        relative = path.relative_to(review_root.resolve()).as_posix()
        if relative in seen_context:
            raise ExperimentError("blind review context paths must be unique")
        seen_context.add(relative)
        if sha256_file(path) != item["sha256"]:
            raise ExperimentError("blind review context hash drifted")
    return manifest


def validate_report(
    experiment_dir: Path,
    report_path: Path,
    run_plan: dict[str, Any],
    preregistration: dict[str, Any],
) -> dict[str, Any]:
    report = load_json(report_path)
    validate_schema(report, experiment_dir / SCHEMA_FILES["report"], "report")
    if report["experiment_id"] != preregistration["experiment_id"]:
        raise ExperimentError("report experiment_id drifted")
    if report["preregistration_sha256"] != run_plan["preregistration_sha256"]:
        raise ExperimentError("report preregistration hash drifted")
    if report["run_plan_sha256"] != sha256_bytes(canonical_bytes(run_plan)):
        raise ExperimentError("report run plan hash drifted")
    if set(report["metrics"]) != EXPECTED_METRICS:
        raise ExperimentError("report metric set must exactly match preregistration")
    gate_ids = [item["gate"] for item in report["gate_results"]]
    if len(gate_ids) != len(set(gate_ids)) or set(gate_ids) != EXPECTED_GATES:
        raise ExperimentError("report gate set must exactly match preregistration")
    for item in report["gate_results"]:
        if item["threshold"] != preregistration["gates"][item["gate"]]:
            raise ExperimentError(f"report threshold drifted for {item['gate']}")
    summary = report["run_summary"]
    if summary["planned"] != summary["valid"] + summary["failed"] + summary["missing"] + summary["excluded_with_reason"]:
        raise ExperimentError("report run summary arithmetic is inconsistent")
    eligible = report["decision"]["recommendation"] == "eligible-for-v2-default-review"
    if eligible:
        raise ExperimentError(
            "legacy report cannot claim eligibility without a bound authoritative evaluation manifest and result"
        )
    return report


def aggregate_results(
    preregistration: dict[str, Any],
    run_plan: dict[str, Any],
    *,
    validated_trace_ids: set[str],
    validated_review_pair_ids: set[str],
) -> dict[str, Any]:
    """Build a fail-closed report shell; metric formulas remain an execution blocker."""
    expected_runs = {run["run_id"] for run in run_plan["runs"]}
    expected_pairs = {run["pair_id"] for run in run_plan["runs"]}
    if validated_trace_ids != expected_runs or validated_review_pair_ids != expected_pairs:
        raise ExperimentError("aggregation requires the exact 84-run and 42-pair validated input sets")
    metrics = {
        metric: {"v1": None, "v2": None, "comparison": None, "unit": "uncomputed", "sample_count": 0}
        for metric in sorted(EXPECTED_METRICS)
    }
    gate_results = [
        {
            "gate": gate,
            "status": "insufficient-data",
            "observed": None,
            "threshold": preregistration["gates"][gate],
            "evidence_refs": ["aggregator:formula-not-implemented"],
        }
        for gate in sorted(EXPECTED_GATES)
    ]
    return {
        "schema_version": "1.0",
        "experiment_id": preregistration["experiment_id"],
        "preregistration_sha256": run_plan["preregistration_sha256"],
        "run_plan_sha256": sha256_bytes(canonical_bytes(run_plan)),
        "generated_at": "1970-01-01T00:00:00Z",
        "run_summary": {"planned": 84, "valid": 84, "failed": 0, "missing": 0, "excluded_with_reason": 0},
        "metrics": metrics,
        "gate_results": gate_results,
        "decision": {
            "recommendation": "extend-experiment",
            "rationale": "Metric formulas and oracle/reviewer result inputs remain intentionally unimplemented.",
            "semantic_reviewer": "not-run",
        },
        "limitations": ["deterministic metric aggregation is not yet implemented"],
    }


def validate_authorization(
    authorization_path: Path,
    execution_root: Path,
    preregistration: dict[str, Any],
    preregistration_hash: str,
    run_plan_hash: str,
    authorized_calls: set[tuple[str, str]],
    adapter_path: Path,
    now: datetime,
) -> dict[str, Any]:
    try:
        import execution_guard

        authorization = execution_guard.load_grant(authorization_path)
        if authorization_path.resolve() != execution_root.resolve() / "grant.json":
            raise ExperimentError("authorization must be the canonical grant inside the execution root")
        summary = execution_guard.replay(execution_root.resolve())
    except (ImportError, execution_guard.GuardError) as exc:
        raise ExperimentError(f"authorization grant is invalid: {exc}") from exc
    if authorization["experiment_id"] != preregistration["experiment_id"]:
        raise ExperimentError("authorization experiment_id mismatch")
    if authorization["preregistration_sha256"] != preregistration_hash:
        raise ExperimentError("authorization preregistration hash mismatch")
    if authorization["run_plan_sha256"] != run_plan_hash:
        raise ExperimentError("authorization run plan hash mismatch")
    if authorization["adapter"]["sha256"] != sha256_file(adapter_path):
        raise ExperimentError("authorization adapter hash mismatch")
    config = preregistration["execution_config"]
    if authorization["model"] != config["model"] or authorization["reasoning_effort"] != config["reasoning_effort"]:
        raise ExperimentError("authorization model configuration mismatch")
    if authorization["tool_profile"] != config["tool_profile"]:
        raise ExperimentError("authorization tool profile mismatch")
    actual_calls = {(item["run_id"], item["episode_id"]) for item in authorization["authorized_calls"]}
    if actual_calls != authorized_calls:
        raise ExperimentError("authorization call set mismatch")
    if summary["status"] != "active" or summary["settled_call_ids"] or summary["in_doubt_attempt_ids"]:
        raise ExperimentError("execution root must contain an active, unconsumed authorization")
    authorized_at = parse_timestamp(authorization["authorized_at"], "authorized_at")
    expires_at = parse_timestamp(authorization["expires_at"], "expires_at")
    if not authorized_at <= now.astimezone(timezone.utc) <= expires_at:
        raise ExperimentError("authorization is not currently valid")
    if authorization["limits"]["total"]["max_calls"] != len(authorized_calls):
        raise ExperimentError("authorization total call limit does not match the run plan")
    if preregistration["status"] != "frozen":
        raise ExperimentError("preregistration must be frozen before execution")
    if preregistration["execution_config"]["model"] == "pending-user-confirmation":
        raise ExperimentError("execution model remains pending user confirmation")
    return authorization


def execute_adapter(
    experiment_dir: Path,
    run_plan_path: Path,
    adapter_path: Path,
    authorization_path: Path,
    execution_root: Path,
    output_dir: Path,
    *,
    execute: bool,
    run_id: str | None = None,
    episode_id: str | None = None,
    now: datetime | None = None,
) -> subprocess.CompletedProcess[str]:
    if not execute:
        raise ExperimentError("adapter execution requires the explicit --execute flag")
    if not adapter_path.is_file():
        raise ExperimentError("adapter must be an existing regular file")
    scenarios, preregistration = load_and_validate(experiment_dir)
    run_plan = load_json(run_plan_path)
    validate_run_plan(run_plan, scenarios, preregistration, experiment_dir=experiment_dir)
    if run_id is None or episode_id is None:
        raise ExperimentError("adapter execution requires exactly one --run-id and --episode-id")
    run = next((item for item in run_plan["runs"] if item["run_id"] == run_id), None)
    if run is None:
        raise ExperimentError("adapter run_id is not in the run plan")
    if episode_id != "E01":
        raise ExperimentError("legacy formal plan authorizes only episode E01")
    preregistration_hash = sha256_bytes(canonical_bytes(preregistration))
    run_plan_hash = sha256_bytes(canonical_bytes(run_plan))
    authorization = validate_authorization(
        authorization_path,
        execution_root,
        preregistration,
        preregistration_hash,
        run_plan_hash,
        {(item["run_id"], "E01") for item in run_plan["runs"]},
        adapter_path,
        now or datetime.now(timezone.utc),
    )
    if not FORMAL_EXECUTION_ENABLED or EXECUTION_BLOCKERS:
        blockers = sorted(EXECUTION_BLOCKERS) or ["formal_execution_enabled is false"]
        raise ExperimentError("formal execution remains disabled: " + "; ".join(blockers))
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        str(adapter_path),
        "--run-plan", str(run_plan_path.resolve()),
        "--run-id", run_id,
        "--episode-id", episode_id,
        "--authorization", str(authorization_path.resolve()),
        "--execution-root", str(execution_root.resolve()),
        "--output-dir", str(output_dir.resolve()),
        "--model", authorization["model"],
        "--reasoning-effort", authorization["reasoning_effort"],
        "--tool-profile", str(resolve_local_file(experiment_dir, authorization["tool_profile"]["path"], "authorization tool profile")),
        "--preregistration-sha256", preregistration_hash,
        "--run-plan-sha256", run_plan_hash,
        "--baseline-source-sha256", preregistration["baseline"]["source_snapshot"]["aggregate_sha256"],
        "--candidate-source-sha256", preregistration["candidate"]["source_snapshot"]["aggregate_sha256"],
        "--instrument-manifest-sha256", preregistration["instrument_manifest"]["sha256"],
        "--max-total-tokens-per-call", str(authorization["limits"]["per_call"]["max_total_tokens"]),
        "--max-seconds-per-call", str(authorization["limits"]["per_call"]["max_wall_seconds"]),
    ]
    if adapter_path.suffix.lower() == ".py":
        command.insert(0, sys.executable)
    timeout = authorization["limits"]["per_call"]["max_wall_seconds"] + 30
    return subprocess.run(command, text=True, capture_output=True, check=False, timeout=timeout)


def validate_command(args: argparse.Namespace) -> int:
    experiment_dir = args.experiment_dir.resolve()
    scenarios, preregistration = load_and_validate(experiment_dir)
    run_plan = build_run_plan(scenarios, preregistration, experiment_dir=experiment_dir)
    validate_run_plan(run_plan, scenarios, preregistration, experiment_dir=experiment_dir)
    if args.run_plan:
        validate_run_plan(
            load_json(args.run_plan), scenarios, preregistration, experiment_dir=experiment_dir
        )
    if args.complete_trace_set:
        if args.adapter is None or args.authorization_grant is None or args.execution_root is None:
            raise ExperimentError("trace validation requires --adapter, --authorization-grant, and --execution-root")
        validate_trace_set(
            experiment_dir,
            args.trace,
            run_plan,
            preregistration,
            adapter_path=args.adapter,
            authorization_path=args.authorization_grant,
            execution_root=args.execution_root,
            binding_root=args.binding_root,
        )
    else:
        for trace in args.trace:
            if args.adapter is None or args.authorization_grant is None or args.execution_root is None:
                raise ExperimentError("trace validation requires --adapter, --authorization-grant, and --execution-root")
            validate_trace(
                experiment_dir,
                trace,
                run_plan,
                preregistration,
                adapter_path=args.adapter,
                authorization_path=args.authorization_grant,
                execution_root=args.execution_root,
                binding_root=args.binding_root,
            )
    if args.blind_manifest:
        if len(args.trace) != 2:
            raise ExperimentError("blind manifest validation requires exactly two pair traces")
        if args.adapter is None or args.authorization_grant is None or args.execution_root is None:
            raise ExperimentError("blind manifest validation requires bound execution authority")
        validate_blind_review_manifest(
            experiment_dir,
            args.blind_manifest,
            run_plan,
            preregistration,
            args.trace,
            args.review_root.resolve(),
            adapter_path=args.adapter,
            authorization_path=args.authorization_grant,
            execution_root=args.execution_root,
        )
    if args.report:
        validate_report(experiment_dir, args.report, run_plan, preregistration)
    print(json.dumps({
        "status": "valid",
        "experiment_id": preregistration["experiment_id"],
        "scenario_count": 14,
        "pair_count": 42,
        "planned_run_count": 84,
        "validated_trace_count": len(args.trace),
        "authorization_requirement": preregistration["authorization"],
    }, sort_keys=True))
    return 0


def plan_command(args: argparse.Namespace) -> int:
    experiment_dir = args.experiment_dir.resolve()
    scenarios, preregistration = load_and_validate(experiment_dir)
    run_plan = build_run_plan(scenarios, preregistration, experiment_dir=experiment_dir)
    validate_run_plan(run_plan, scenarios, preregistration, experiment_dir=experiment_dir)
    if args.output:
        write_json(args.output, run_plan)
    else:
        json.dump(run_plan, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    return 0


def execute_command(args: argparse.Namespace) -> int:
    result = execute_adapter(
        args.experiment_dir.resolve(),
        args.run_plan.resolve(),
        args.adapter.resolve(),
        args.authorization.resolve(),
        args.execution_root.resolve(),
        args.output_dir.resolve(),
        execute=args.execute,
        run_id=args.run_id,
        episode_id=args.episode_id,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--experiment-dir", type=Path, default=HERE)
    commands = value.add_subparsers(dest="command", required=True)

    validate_parser = commands.add_parser("validate", help="validate frozen inputs without executing an adapter")
    validate_parser.add_argument("--run-plan", type=Path)
    validate_parser.add_argument("--trace", type=Path, action="append", default=[])
    validate_parser.add_argument("--adapter", type=Path)
    validate_parser.add_argument("--authorization-grant", type=Path)
    validate_parser.add_argument("--execution-root", type=Path)
    validate_parser.add_argument("--binding-root", type=Path)
    validate_parser.add_argument("--complete-trace-set", action="store_true", help="require exactly one valid trace for each of the 84 planned runs")
    validate_parser.add_argument("--blind-manifest", type=Path)
    validate_parser.add_argument("--review-root", type=Path, default=HERE)
    validate_parser.add_argument("--report", type=Path)
    validate_parser.set_defaults(func=validate_command)

    plan_parser = commands.add_parser("plan", help="emit the deterministic 42-pair/84-run plan")
    plan_parser.add_argument("--output", type=Path)
    plan_parser.set_defaults(func=plan_command)

    execute_parser = commands.add_parser("execute", help="launch an explicitly authorized adapter")
    execute_parser.add_argument("--run-plan", type=Path, required=True)
    execute_parser.add_argument("--adapter", type=Path, required=True)
    execute_parser.add_argument("--authorization", type=Path, required=True)
    execute_parser.add_argument("--execution-root", type=Path, required=True)
    execute_parser.add_argument("--output-dir", type=Path, required=True)
    execute_parser.add_argument("--run-id", required=True)
    execute_parser.add_argument("--episode-id", required=True)
    execute_parser.add_argument("--execute", action="store_true", help="acknowledge that this command may consume the authorized budget")
    execute_parser.set_defaults(func=execute_command)
    return value


def main(argv: Iterable[str] | None = None) -> int:
    args = parser().parse_args(list(argv) if argv is not None else None)
    try:
        return args.func(args)
    except ExperimentError as exc:
        print(f"experiment error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
