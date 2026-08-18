#!/usr/bin/env python3
"""Assemble the frozen real-task Pilot without launching a provider.

This controller owns ordering, immutable episode snapshots, anonymous review
inputs, post-seal decoding, and the final evaluation hand-off.  It deliberately
has no provider-launch command and never creates an authorization grant.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import evaluation  # noqa: E402
import execution_guard as guard  # noqa: E402
import pilot_freeze  # noqa: E402
import pilot_runners  # noqa: E402
import snapshot_tools as snapshots  # noqa: E402
from schema_runtime import SchemaError, check_schema, validate  # noqa: E402


CAMPAIGN_ID = "create-loop-v1-v2-real-task-pilot-2026"
CASE_ORDER = ("N0", "T2", "T3", "T5", "S1", "T7")
REVIEW_CASES = ("T2", "T3", "T5", "T7")
TWO_EPISODE_CASES = {"T3", "T5", "S1"}
EXPECTED_RUN_ORDER = (
    "PL-N0-P01-v1-E01",
    "PL-N0-P01-v2-E01",
    "PL-T2-P01-v2-E01",
    "PL-T2-P01-v1-E01",
    "PL-T3-P01-v1-E01",
    "PL-T3-P01-v1-E02",
    "PL-T3-P01-v2-E01",
    "PL-T3-P01-v2-E02",
    "PL-T5-P01-v2-E01",
    "PL-T5-P01-v2-E02",
    "PL-T5-P01-v1-E01",
    "PL-T5-P01-v1-E02",
    "PL-S1-P01-v1-E01",
    "PL-S1-P01-v1-E02",
    "PL-S1-P01-v2-E01",
    "PL-S1-P01-v2-E02",
    "PL-T7-P01-v2-E01",
    "PL-T7-P01-v1-E01",
)
ROLE_LIMITS = {
    "calibration": {
        "per_call": {"max_total_tokens": 10_000, "max_wall_seconds": 300},
        "total": {"max_calls": 1, "max_total_tokens": 10_000, "max_wall_seconds": 300},
    },
    "producer": {
        "per_call": {"max_total_tokens": 60_000, "max_wall_seconds": 900},
        "total": {"max_calls": 18, "max_total_tokens": 1_080_000, "max_wall_seconds": 16_200},
    },
    "reviewer": {
        "per_call": {"max_total_tokens": 60_000, "max_wall_seconds": 900},
        "total": {"max_calls": 4, "max_total_tokens": 240_000, "max_wall_seconds": 3_600},
    },
}
FREEZE_BINDING_ALIASES = {
    "preregistration": ("preregistration", "pilot_preregistration"),
    "run_plan": ("run_plan", "pilot_run_plan"),
    "scenarios": ("scenarios", "scenario_manifest", "pilot_scenarios"),
    "evaluator": ("evaluator", "evaluator_manifest", "pilot_evaluator"),
    "calibration_result": ("calibration_result", "pilot_calibration_result"),
    "pre_calibration_freeze": ("pre_calibration_freeze", "pre_freeze"),
}
FROZEN_EVALUATION_INPUTS = {
    "scenarios": "pilot-scenarios.json",
    "run_plan": "pilot-run-plan.json",
    "evaluator": "pilot-evaluator-manifest.json",
    "calibration_result": "pilot-calibration-result.json",
}


class CampaignError(RuntimeError):
    """A Pilot campaign assembly invariant failed closed."""


def canonical_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CampaignError(f"value is not strict canonical JSON: {exc}") from exc


def sha256_bytes(value: bytes) -> str:
    return snapshots.sha256_bytes(value)


def sha256_file(path: Path) -> str:
    return snapshots.sha256_file(path)


def load_json(path: Path, label: str) -> Any:
    try:
        return snapshots.load_json(path)
    except snapshots.SnapshotError as exc:
        raise CampaignError(f"cannot load {label}: {exc}") from exc


def validate_schema(value: Any, schema_path: Path, label: str) -> None:
    schema = load_json(schema_path, f"{label} schema")
    try:
        check_schema(schema)
        errors = validate(value, schema)
    except SchemaError as exc:
        raise CampaignError(f"{label} schema is unsupported: {exc}") from exc
    if errors:
        raise CampaignError(f"{label} schema validation failed: {'; '.join(errors)}")


def _write_immutable(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not path.is_file() or path.is_symlink() or path.read_bytes() != data:
            raise CampaignError(f"immutable campaign output drifted: {path}")
        return
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise CampaignError(f"immutable campaign output appeared concurrently: {path}") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def write_json(path: Path, value: Any) -> None:
    _write_immutable(path, canonical_bytes(value))


def _canonical_relative(relative: str, label: str) -> PurePosixPath:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise CampaignError(f"{label} path is unsafe")
    path = PurePosixPath(relative)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise CampaignError(f"{label} path is unsafe")
    return path


def _confined_path(root: Path, relative: str, label: str) -> Path:
    pure = _canonical_relative(relative, label)
    path = root.joinpath(*pure.parts).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise CampaignError(f"{label} escapes its root") from exc
    return path


def _regular_file(path: Path, label: str) -> Path:
    if not path.is_file() or path.is_symlink():
        raise CampaignError(f"{label} must be a regular non-symlink file")
    return path


def _relative_binding(path: Path, root: Path) -> dict[str, str]:
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise CampaignError(f"campaign artifact escapes the input root: {path}") from exc
    return {"path": relative, "sha256": sha256_file(path)}


def _document_hash(value: dict[str, Any]) -> str:
    return sha256_bytes(canonical_bytes(value))


def _binding_candidates(document: dict[str, Any], name: str) -> list[dict[str, str]]:
    aliases = set(FREEZE_BINDING_ALIASES[name])
    values: list[Any] = []
    for container in (document, document.get("bindings"), document.get("inputs"), document.get("authority")):
        if isinstance(container, dict):
            values.extend(container.get(alias) for alias in aliases if alias in container)
    files = document.get("files")
    if isinstance(files, list):
        values.extend(
            item for item in files
            if isinstance(item, dict) and item.get("role") in aliases
        )
    result = []
    for value in values:
        if isinstance(value, dict) and set(value) >= {"path", "sha256"}:
            result.append({"path": value["path"], "sha256": value["sha256"]})
    unique = {(item["path"], item["sha256"]): item for item in result}
    return list(unique.values())


def _freeze_binding(
    freeze_path: Path,
    document: dict[str, Any],
    name: str,
    *,
    required: bool = True,
) -> tuple[Path, dict[str, str]] | None:
    candidates = _binding_candidates(document, name)
    if not candidates:
        if required:
            raise CampaignError(f"final Pilot freeze lacks {name} binding")
        return None
    if len(candidates) != 1:
        raise CampaignError(f"final Pilot freeze has ambiguous {name} bindings")
    binding = candidates[0]
    # Static protocol inputs are rooted at the frozen experiment bundle.  The
    # two-stage calibration artifacts are rooted beside the freeze output.
    base = HERE if name in {
        "preregistration", "run_plan", "scenarios", "evaluator",
    } else freeze_path.parent
    path = _confined_path(base, binding["path"], f"final freeze {name}")
    _regular_file(path, f"final freeze {name}")
    if sha256_file(path) != binding["sha256"]:
        raise CampaignError(f"final freeze {name} hash drifted")
    return path, binding


def _calibration_grant_binding(
    freeze_path: Path,
    document: dict[str, Any],
) -> tuple[Path, dict[str, str]]:
    artifacts = document.get("calibration_artifacts")
    candidates = [
        item for item in artifacts
        if isinstance(item, dict) and item.get("role") == "grant"
    ] if isinstance(artifacts, list) else []
    if len(candidates) != 1:
        raise CampaignError("final Pilot freeze must bind exactly one calibration grant artifact")
    artifact = candidates[0]
    if not isinstance(artifact.get("path"), str) or not isinstance(artifact.get("sha256"), str):
        raise CampaignError("final Pilot freeze calibration grant binding is malformed")
    binding = {"path": artifact["path"], "sha256": artifact["sha256"]}
    path = _confined_path(freeze_path.parent, binding["path"], "final freeze calibration grant")
    _regular_file(path, "final freeze calibration grant")
    if sha256_file(path) != binding["sha256"]:
        raise CampaignError("final freeze calibration grant hash drifted")
    return path, binding


def load_final_freeze(path: Path) -> dict[str, Any]:
    freeze_path = _regular_file(path.resolve(), "final Pilot freeze")
    document = load_json(freeze_path, "final Pilot freeze")
    if not isinstance(document, dict):
        raise CampaignError("final Pilot freeze must be an object")
    experiment_id = document.get("experiment_id", document.get("campaign_id"))
    if experiment_id != CAMPAIGN_ID:
        raise CampaignError("final Pilot freeze campaign identity drifted")
    if document.get("formal_execution_enabled", False) is not False:
        raise CampaignError("final Pilot freeze must keep formal execution disabled")
    if document.get("stop_after_report", True) is not True:
        raise CampaignError("final Pilot freeze must stop after the Pilot report")
    validate_schema(document, HERE / "pilot-final-freeze.schema.json", "final Pilot freeze")
    try:
        pilot_freeze.validate_final_freeze(freeze_path, experiment_dir=HERE)
    except pilot_freeze.PilotFreezeError as exc:
        raise CampaignError(f"final Pilot freeze is not authoritative: {exc}") from exc
    status_values = [document.get(key) for key in ("status", "phase", "freeze_stage") if key in document]
    if status_values and not any(
        isinstance(value, str) and ("final" in value.lower() or "frozen" in value.lower())
        for value in status_values
    ):
        raise CampaignError("the supplied freeze is not marked final")
    bindings = {
        name: _freeze_binding(freeze_path, document, name)
        for name in FREEZE_BINDING_ALIASES
    }
    bindings["calibration_grant"] = _calibration_grant_binding(freeze_path, document)
    preregistration = load_json(bindings["preregistration"][0], "frozen Pilot preregistration")
    run_plan = load_json(bindings["run_plan"][0], "frozen Pilot run plan")
    scenarios = load_json(bindings["scenarios"][0], "frozen Pilot scenarios")
    evaluator = load_json(bindings["evaluator"][0], "frozen Pilot evaluator")
    if not all(isinstance(item, dict) for item in (preregistration, run_plan, scenarios, evaluator)):
        raise CampaignError("final Pilot freeze bound a non-object control document")
    if run_plan.get("preregistration_sha256") != _document_hash(preregistration):
        raise CampaignError("frozen run plan does not bind the frozen preregistration")
    for label, value in (
        ("preregistration", preregistration.get("campaign_id")),
        ("run plan", run_plan.get("campaign_id")),
        ("scenarios", scenarios.get("campaign_id")),
        ("evaluator", evaluator.get("campaign_id")),
    ):
        if value != CAMPAIGN_ID:
            raise CampaignError(f"frozen {label} campaign identity drifted")
    validate_run_order(run_plan)
    return {
        "path": freeze_path,
        "sha256": sha256_file(freeze_path),
        "document": document,
        "bindings": bindings,
        "preregistration": preregistration,
        "run_plan": run_plan,
        "scenarios": scenarios,
        "evaluator": evaluator,
    }


def validate_run_order(plan: dict[str, Any]) -> None:
    runs = plan.get("runs")
    if not isinstance(runs, list):
        raise CampaignError("frozen Pilot run plan lacks producer episodes")
    actual = tuple(item.get("run_id") for item in runs if isinstance(item, dict))
    if actual != EXPECTED_RUN_ORDER or len(actual) != len(runs):
        raise CampaignError("producer episodes drifted from the fixed 18-call order")
    if plan.get("producer_episode_count") != 18 or plan.get("arm_count") != 12 or plan.get("pair_count") != 6:
        raise CampaignError("frozen Pilot plan counts drifted")


def producer_schedule(plan: dict[str, Any]) -> list[dict[str, Any]]:
    validate_run_order(plan)
    return [dict(item) for item in plan["runs"]]


def _expected_calls(plan: dict[str, Any], role: str) -> set[tuple[str, str]]:
    if role == "calibration":
        return {("pilot-calibration", "calibration")}
    if role == "producer":
        return {(item["run_id"], item["episode_id"]) for item in plan["runs"]}
    return {(f"PL-{case_id}-P01-review", "review") for case_id in REVIEW_CASES}


def preflight_authorities(
    freeze: dict[str, Any],
    authorities: dict[str, tuple[Path, Path]],
) -> dict[str, dict[str, Any]]:
    if set(authorities) != set(ROLE_LIMITS):
        raise CampaignError("calibration, producer, and reviewer authorities are all required")
    preregistration = freeze["preregistration"]
    plan = freeze["run_plan"]
    plan_hash = _document_hash(plan)
    grants: dict[str, dict[str, Any]] = {}
    roots: dict[str, Path] = {}
    grant_hashes: dict[str, str] = {}
    expected_adapter = pilot_runners.adapter.adapter_binding()
    for role in ("calibration", "producer", "reviewer"):
        root, grant_path = authorities[role]
        root = root.resolve()
        _regular_file(grant_path, f"{role} grant")
        grant_path = grant_path.resolve()
        authority_freeze_path = (
            freeze["bindings"]["pre_calibration_freeze"][0]
            if role == "calibration"
            else freeze["path"]
        )
        try:
            grant = pilot_freeze.validate_grant_authority(
                grant_path,
                authority_freeze_path,
                expected_role=role,
                experiment_dir=HERE,
            )
        except (pilot_freeze.PilotFreezeError, guard.GuardError) as exc:
            raise CampaignError(f"{role} grant authority is invalid: {exc}") from exc
        if grant["role"] != role or grant["execution_root_sha256"] != guard._root_path_sha256(root):
            raise CampaignError(f"{role} grant role or execution root drifted")
        calls = {(item["run_id"], item["episode_id"]) for item in grant["authorized_calls"]}
        if calls != _expected_calls(plan, role) or len(calls) != len(grant["authorized_calls"]):
            raise CampaignError(f"{role} grant authorized call exact set drifted")
        if grant["limits"] != ROLE_LIMITS[role]:
            raise CampaignError(f"{role} grant budget drifted")
        identity_role = "reviewer" if role == "reviewer" else "producer"
        identity_slot = preregistration["cli_identities"][identity_role]
        if identity_slot["status"] != "frozen" or identity_slot["binding"] is None:
            raise CampaignError(f"{identity_role} CLI identity is unresolved")
        expected = {
            "experiment_id": CAMPAIGN_ID,
            "adapter": expected_adapter,
            "cli_identity": identity_slot["binding"],
            "provider_profile": preregistration["provider"],
            "model": preregistration["execution"]["model"],
            "reasoning_effort": preregistration["execution"]["reasoning_effort"],
            "tool_profile": preregistration["execution"]["tool_profile"],
        }
        for field, value in expected.items():
            if grant.get(field) != value:
                raise CampaignError(f"{role} grant {field} drifted")
        if role in {"producer", "reviewer"}:
            if grant.get("preregistration_sha256") != plan["preregistration_sha256"] or grant.get("run_plan_sha256") != plan_hash:
                raise CampaignError(f"{role} grant does not bind the final Pilot plan")
        else:
            frozen_grant_path, frozen_grant_binding = freeze["bindings"]["calibration_grant"]
            if (
                grant_path != frozen_grant_path.resolve()
                or sha256_file(grant_path) != frozen_grant_binding["sha256"]
            ):
                raise CampaignError("final Pilot freeze binds another calibration grant")
        grants[role] = grant
        roots[role] = root
        grant_hashes[role] = sha256_file(grant_path)
    if len({path.resolve() for path in roots.values()}) != 3:
        raise CampaignError("Pilot roles must use three independent execution roots")
    if len(set(grant_hashes.values())) != 3:
        raise CampaignError("Pilot roles must use three independent grants")
    for field in ("authorization_id", "execution_id"):
        if len({grant[field] for grant in grants.values()}) != 3:
            raise CampaignError(f"Pilot roles must use independent {field} values")
    return {
        role: {"root": roots[role], "grant_path": authorities[role][1].resolve(), "grant": grants[role], "grant_sha256": grant_hashes[role]}
        for role in grants
    }


def _path_identity(relative: str) -> str:
    return "/".join(part.casefold() for part in _canonical_relative(relative, "artifact").parts)


def _register_path(identities: set[str], relative: str, label: str) -> PurePosixPath:
    pure = _canonical_relative(relative, label)
    identity = _path_identity(relative)
    parts = identity.split("/")
    prefixes = {"/".join(parts[:index]) for index in range(1, len(parts))}
    if identity in identities or identities.intersection(prefixes) or any(
        existing.startswith(identity + "/") for existing in identities
    ):
        raise CampaignError(f"{label} collides after path normalization or case folding")
    identities.add(identity)
    return pure


def _copy_tree_exact(source: Path, target: Path) -> None:
    if not source.is_dir() or source.is_symlink():
        raise CampaignError("episode workspace must be a real directory")
    if target.exists():
        raise CampaignError(f"immutable episode workspace already exists: {target}")
    identities: set[str] = set()
    target.mkdir(parents=True)
    try:
        for path in sorted(source.rglob("*"), key=lambda item: item.relative_to(source).as_posix()):
            if path.is_symlink():
                raise CampaignError("episode workspace contains a symlink")
            relative = path.relative_to(source).as_posix()
            if path.is_dir():
                pure = _canonical_relative(relative, "episode workspace directory")
                destination = target.joinpath(*pure.parts)
                destination.mkdir(parents=True, exist_ok=True)
            elif path.is_file():
                pure = _register_path(identities, relative, "episode workspace file")
                destination = target.joinpath(*pure.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                _write_immutable(destination, path.read_bytes())
            else:
                raise CampaignError("episode workspace contains an unsupported filesystem entry")
    except BaseException:
        _remove_tree(target)
        raise


def _remove_tree(path: Path) -> None:
    if not path.exists():
        return

    def make_writable_and_retry(function: Any, failed_path: str, _: Any) -> None:
        os.chmod(failed_path, stat.S_IWRITE | stat.S_IREAD)
        function(failed_path)

    shutil.rmtree(path, onerror=make_writable_and_retry)


def _make_read_only(path: Path) -> None:
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    except OSError as exc:
        raise CampaignError(f"cannot make frozen campaign input read-only: {path}") from exc


def _frozen_bundle_paths(campaign_root: Path) -> dict[str, Path]:
    root = campaign_root / "frozen-evaluation-inputs"
    return {name: root / filename for name, filename in FROZEN_EVALUATION_INPUTS.items()}


def _validate_frozen_bundle(
    *,
    freeze: dict[str, Any],
    campaign_root: Path,
) -> dict[str, Path]:
    paths = _frozen_bundle_paths(campaign_root)
    root = next(iter(paths.values())).parent
    if not root.is_dir() or root.is_symlink():
        raise CampaignError("frozen evaluation input bundle is not a real directory")
    actual = {path.name for path in root.iterdir() if path.is_file() and not path.is_symlink()}
    if actual != {path.name for path in paths.values()} or any(
        not path.is_file() or path.is_symlink() for path in root.iterdir()
    ):
        raise CampaignError("frozen evaluation input bundle exact set drifted")
    for name, destination in paths.items():
        source, binding = freeze["bindings"][name]
        _regular_file(source, f"final freeze {name}")
        if sha256_file(source) != binding["sha256"]:
            raise CampaignError(f"final freeze {name} hash drifted before bundling")
        if sha256_file(destination) != binding["sha256"]:
            raise CampaignError(f"frozen evaluation input {name} drifted")
        if os.stat(destination).st_mode & 0o222:
            raise CampaignError(f"frozen evaluation input {name} is writable")
    return paths


def _ensure_frozen_bundle(
    *,
    freeze: dict[str, Any],
    campaign_root: Path,
) -> dict[str, Path]:
    paths = _frozen_bundle_paths(campaign_root)
    bundle_root = next(iter(paths.values())).parent
    if bundle_root.exists():
        return _validate_frozen_bundle(freeze=freeze, campaign_root=campaign_root)
    bundle_root.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=".frozen-evaluation-inputs.staging-", dir=bundle_root.parent))
    payload = staging_root / "payload"
    payload.mkdir()
    try:
        for name, filename in FROZEN_EVALUATION_INPUTS.items():
            source, binding = freeze["bindings"][name]
            _regular_file(source, f"final freeze {name}")
            source_bytes = source.read_bytes()
            if sha256_bytes(source_bytes) != binding["sha256"]:
                raise CampaignError(f"final freeze {name} hash drifted before bundling")
            destination = payload / filename
            _write_immutable(destination, source_bytes)
            _make_read_only(destination)
        try:
            os.rename(payload, bundle_root)
        except OSError as exc:
            raise CampaignError("cannot atomically publish frozen evaluation input bundle") from exc
    finally:
        _remove_tree(staging_root)
    return _validate_frozen_bundle(freeze=freeze, campaign_root=campaign_root)


def _episode_capture_paths(campaign_root: Path, run_id: str) -> tuple[Path, Path, Path, Path]:
    episode_root = campaign_root / "producer-episodes" / run_id
    return (
        episode_root,
        episode_root / "artifacts",
        episode_root / "workspace",
        episode_root / "episode.json",
    )


def _captured_prefix(campaign_root: Path) -> list[str]:
    capture_root = campaign_root / "producer-episodes"
    if not capture_root.exists():
        return []
    if not capture_root.is_dir() or capture_root.is_symlink():
        raise CampaignError("producer episode capture root is unsafe")
    entries = list(capture_root.iterdir())
    if any(not path.is_dir() or path.is_symlink() for path in entries):
        raise CampaignError("producer episode capture root contains an unpublished entry")
    actual = {path.name for path in entries}
    expected_prefix = list(EXPECTED_RUN_ORDER[: len(actual)])
    if actual != set(expected_prefix):
        raise CampaignError("captured producer episodes are not a fixed-order prefix")
    for run_id in expected_prefix:
        _regular_file(capture_root / run_id / "episode.json", f"producer episode {run_id}")
    return expected_prefix


def _artifact_binding(campaign_root: Path, path: Path, label: str) -> dict[str, str]:
    _regular_file(path, label)
    return _relative_binding(path, campaign_root)


def capture_episode(
    *,
    freeze: dict[str, Any],
    campaign_root: Path,
    producer_output: Path,
    run_id: str,
) -> dict[str, Any]:
    campaign_root = campaign_root.resolve()
    producer_output = producer_output.resolve()
    prefix = _captured_prefix(campaign_root)
    if len(prefix) >= len(EXPECTED_RUN_ORDER) or EXPECTED_RUN_ORDER[len(prefix)] != run_id:
        expected = EXPECTED_RUN_ORDER[len(prefix)] if len(prefix) < len(EXPECTED_RUN_ORDER) else "none"
        raise CampaignError(f"episode capture is out of order; next expected run is {expected}")
    rows = {item["run_id"]: item for item in freeze["run_plan"]["runs"]}
    row = rows[run_id]
    arm_id = row["arm_id"]
    raw = producer_output / "runs" / run_id
    workspace = producer_output / "arms" / arm_id / "workspace"
    initial = _regular_file(raw / "workspace-initial-manifest.json", "episode initial workspace manifest")
    final = _regular_file(raw / "workspace-final-manifest.json", "episode final workspace manifest")
    evidence = _regular_file(raw / "evidence-manifest.json", "episode evidence manifest")
    interrupted = run_id in {"PL-S1-P01-v1-E01", "PL-S1-P01-v2-E01"}
    episode_root, published_archive, published_workspace, published_binding = _episode_capture_paths(campaign_root, run_id)
    capture_root = episode_root.parent
    capture_root.mkdir(parents=True, exist_ok=True)
    if capture_root.is_symlink() or not capture_root.is_dir():
        raise CampaignError("producer episode capture root is unsafe")
    if episode_root.exists():
        raise CampaignError(f"immutable producer episode already exists: {run_id}")
    staging_root = Path(tempfile.mkdtemp(prefix=f".{run_id}.staging-", dir=capture_root))
    payload = staging_root / "payload"
    payload.mkdir()
    staged_archive = payload / "artifacts"
    staged_workspace = payload / "workspace"
    staged_binding = payload / "episode.json"

    def staged_binding_for(staged: Path, published: Path, label: str) -> dict[str, str]:
        _regular_file(staged, label)
        return {
            "path": published.relative_to(campaign_root).as_posix(),
            "sha256": sha256_file(staged),
        }

    try:
        _copy_tree_exact(raw, staged_archive)
        staged_initial = staged_archive / initial.relative_to(raw)
        staged_final = staged_archive / final.relative_to(raw)
        staged_evidence = staged_archive / evidence.relative_to(raw)
        staged_trace = staged_archive / "trace.json"
        staged_receipt = staged_archive / "usage-receipt.json"
        staged_interruption = staged_archive / "controller-interruption.json"
        _copy_tree_exact(workspace, staged_workspace)
        initial_value = load_json(staged_initial, "captured episode initial workspace manifest")
        final_value = load_json(staged_final, "captured episode final workspace manifest")
        validate_schema(
            initial_value,
            HERE / "initial-workspace-manifest.schema.json",
            "captured episode initial workspace manifest",
        )
        validate_schema(
            final_value,
            HERE / "final-workspace-manifest.schema.json",
            "captured episode final workspace manifest",
        )
        validate_schema(
            load_json(staged_evidence, "captured episode evidence manifest"),
            HERE / ("interruption-evidence-manifest.schema.json" if interrupted else "evidence-manifest.schema.json"),
            "captured episode evidence manifest",
        )
        try:
            evaluation._pilot_validate_final_manifest(
                staged_workspace,
                initial_value,
                final_value,
                f"captured workspace {run_id}",
            )
        except evaluation.EvaluationError as exc:
            raise CampaignError(f"captured workspace {run_id} does not match its manifest: {exc}") from exc
        if interrupted:
            _regular_file(staged_interruption, "controller interruption manifest")
            if staged_trace.exists() or staged_receipt.exists():
                raise CampaignError("controlled S1 interruption contains settled-only artifacts")
            outcome = "controller-interrupted"
            trace = None
            receipt = None
            interruption = staged_binding_for(
                staged_interruption,
                published_archive / "controller-interruption.json",
                "controller interruption manifest",
            )
        else:
            _regular_file(staged_trace, "episode trace")
            _regular_file(staged_receipt, "episode usage receipt")
            if staged_interruption.exists():
                raise CampaignError("settled producer episode contains interruption evidence")
            outcome = "settled"
            trace = staged_binding_for(staged_trace, published_archive / "trace.json", "episode trace")
            receipt = staged_binding_for(staged_receipt, published_archive / "usage-receipt.json", "episode usage receipt")
            interruption = None
        binding = {
            "run_id": run_id,
            "arm_id": arm_id,
            "pair_id": row["pair_id"],
            "case_id": row["case_id"],
            "protocol": row["protocol"],
            "episode_id": row["episode_id"],
            "outcome": outcome,
            "trace": trace,
            "usage_receipt": receipt,
            "interruption_manifest": interruption,
            "initial_workspace_manifest": staged_binding_for(
                staged_initial,
                published_archive / initial.relative_to(raw),
                "episode initial workspace manifest",
            ),
            "final_workspace_manifest": staged_binding_for(
                staged_final,
                published_archive / final.relative_to(raw),
                "episode final workspace manifest",
            ),
            "evidence_manifest": staged_binding_for(
                staged_evidence,
                published_archive / evidence.relative_to(raw),
                "episode evidence manifest",
            ),
            "workspace_root": {"path": published_workspace.relative_to(campaign_root).as_posix()},
        }
        write_json(staged_binding, binding)
        try:
            os.rename(payload, episode_root)
        except OSError as exc:
            raise CampaignError(f"cannot atomically publish producer episode {run_id}") from exc
        return binding
    finally:
        _remove_tree(staging_root)


def load_episode_bindings(campaign_root: Path) -> list[dict[str, Any]]:
    campaign_root = campaign_root.resolve()
    prefix = _captured_prefix(campaign_root)
    if tuple(prefix) != EXPECTED_RUN_ORDER:
        missing = EXPECTED_RUN_ORDER[len(prefix)] if len(prefix) < len(EXPECTED_RUN_ORDER) else "unknown"
        raise CampaignError(f"producer episode set is incomplete; first missing run is {missing}")
    return [
        load_json(campaign_root / "producer-episodes" / run_id / "episode.json", f"producer episode {run_id}")
        for run_id in EXPECTED_RUN_ORDER
    ]


def write_arm_episode_bindings(campaign_root: Path, episodes: list[dict[str, Any]]) -> list[Path]:
    by_arm: dict[str, list[dict[str, Any]]] = {}
    for episode in episodes:
        by_arm.setdefault(episode["arm_id"], []).append(episode)
    paths: list[Path] = []
    for arm_id in sorted(by_arm):
        rows = sorted(by_arm[arm_id], key=lambda item: item["episode_id"])
        case_id = rows[0]["case_id"]
        final_episode = "E02" if case_id in TWO_EPISODE_CASES else "E01"
        final = next((item for item in rows if item["episode_id"] == final_episode), None)
        if final is None:
            raise CampaignError(f"arm {arm_id} lacks its final episode")
        interruption = next((item["interruption_manifest"] for item in rows if item["outcome"] == "controller-interrupted"), None)
        value = {"arm_id": arm_id, "final": final, "interruption": interruption}
        path = campaign_root / "episode-bindings" / f"{arm_id}.json"
        write_json(path, value)
        paths.append(path)
    if len(paths) != 12:
        raise CampaignError("arm episode binding exact set drifted")
    return paths


def _scenario_maps(freeze: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    scenarios = {item["case_id"]: item for item in freeze["scenarios"]["cases"]}
    assignments = {item["pair_id"]: item for item in freeze["evaluator"]["blind_assignments"]}
    if set(scenarios) != set(CASE_ORDER) or set(assignments) != {f"PL-{case}-P01" for case in REVIEW_CASES}:
        raise CampaignError("frozen Pilot scenario or blind assignment exact set drifted")
    return scenarios, assignments


def _presented_file(path: str, entry: dict[str, Any]) -> dict[str, Any]:
    media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return {
        "path": path,
        "sha256": entry["sha256"],
        "size": entry["size"],
        "media_type": media_type,
        "purpose": "anonymous task deliverable",
    }


def prepare_blind_reviews(
    *,
    freeze: dict[str, Any],
    campaign_root: Path,
    reviewer_grant_path: Path,
) -> list[Path]:
    campaign_root = campaign_root.resolve()
    episodes = load_episode_bindings(campaign_root)
    write_arm_episode_bindings(campaign_root, episodes)
    final_by_arm = {
        item["arm_id"]: item for item in episodes
        if item["episode_id"] == ("E02" if item["case_id"] in TWO_EPISODE_CASES else "E01")
    }
    scenarios, assignments = _scenario_maps(freeze)
    reviewer_grant = guard.load_grant(reviewer_grant_path)
    if reviewer_grant["role"] != "reviewer":
        raise CampaignError("blind manifests require a reviewer grant")
    output_paths: list[Path] = []
    for case_id in REVIEW_CASES:
        pair_id = f"PL-{case_id}-P01"
        scenario = scenarios[case_id]
        assignment = assignments[pair_id]
        pair_root = campaign_root / "review-input" / pair_id
        context_path = pair_root / "context" / "task.md"
        context = (
            f"# Anonymous task review: {scenario['title']}\n\n"
            f"Task: {scenario['input']['task']}\n\n"
            "Compare A and B only against this task and the delivered files. "
            "Report correctness gaps, severe regressions, and concrete counterexamples.\n"
        ).encode("utf-8")
        _write_immutable(context_path, context)
        presented: list[dict[str, Any]] = []
        for label in ("A", "B"):
            arm_id = assignment[label]
            episode = final_by_arm.get(arm_id)
            if episode is None:
                raise CampaignError(f"blind assignment {pair_id}/{label} lacks a final episode")
            final_path = _confined_path(campaign_root, episode["final_workspace_manifest"]["path"], "final workspace manifest")
            final_manifest = load_json(final_path, "final workspace manifest")
            if sha256_file(final_path) != episode["final_workspace_manifest"]["sha256"]:
                raise CampaignError("blind source final workspace manifest drifted")
            by_path = {item["path"]: item for item in final_manifest["files"]}
            expected_paths = scenario["presented_paths"]
            identities: set[str] = set()
            files: list[dict[str, Any]] = []
            source_root = _confined_path(campaign_root, episode["workspace_root"]["path"], "captured episode workspace")
            deliverable_root = pair_root / label / "deliverables"
            for relative in expected_paths:
                pure = _register_path(identities, relative, f"presented {pair_id}/{label}")
                entry = by_path.get(relative)
                if entry is None:
                    raise CampaignError(f"presented deliverable is absent: {pair_id}/{label}/{relative}")
                source = _regular_file(source_root.joinpath(*pure.parts), "presented source deliverable")
                if sha256_file(source) != entry["sha256"] or source.stat().st_size != entry["size"]:
                    raise CampaignError("presented source deliverable drifted")
                target = deliverable_root.joinpath(*pure.parts)
                _write_immutable(target, source.read_bytes())
                files.append(_presented_file(relative, entry))
            artifact = {
                "schema_version": "1.0",
                "algorithm": "sha256-pilot-presented-artifact-v1",
                "pair_id": pair_id,
                "case_id": case_id,
                "final_workspace_manifest_sha256": sha256_file(final_path),
                "files": files,
                "aggregate_sha256": sha256_bytes(canonical_bytes(files)),
            }
            validate_schema(artifact, HERE / "pilot-presented-artifact.schema.json", "presented artifact")
            artifact_path = pair_root / label / "artifact.json"
            write_json(artifact_path, artifact)
            presented.append({
                "label": label,
                "artifact": _relative_binding(artifact_path, campaign_root),
                "deliverable_root": deliverable_root.relative_to(campaign_root).as_posix(),
                "final_workspace_manifest_sha256": sha256_file(final_path),
                "evidence_manifest_sha256": episode["evidence_manifest"]["sha256"],
            })
        manifest = {
            "schema_version": "1.0",
            "experiment_id": CAMPAIGN_ID,
            "review_id": f"{pair_id}-review",
            "pair_id": pair_id,
            "case_id": case_id,
            "reviewer": {
                "id": reviewer_grant["execution_id"],
                "kind": "model",
                "model": reviewer_grant["model"],
                "reasoning_effort": reviewer_grant["reasoning_effort"],
                "context_isolation": "fresh-session",
            },
            "producer_protocols_withheld": True,
            "reviewer_grant_sha256": sha256_file(reviewer_grant_path),
            "presented": presented,
            "delivered_context": [{
                **_relative_binding(context_path, campaign_root),
                "purpose": "neutral task and review question",
            }],
            "created_at": reviewer_grant["authorized_at"],
        }
        validate_schema(manifest, HERE / "pilot-blind-review-manifest.schema.json", "blind review manifest")
        manifest_path = pair_root / "blind-manifest.json"
        write_json(manifest_path, manifest)
        pilot_runners._review_context_check(campaign_root, manifest)
        output_paths.append(manifest_path)
    return output_paths


def decode_reviews(
    *,
    freeze: dict[str, Any],
    campaign_root: Path,
    review_seal_path: Path,
    output: Path,
) -> dict[str, Any]:
    campaign_root = campaign_root.resolve()
    seal_path = _regular_file(review_seal_path.resolve(), "review seal")
    seal = load_json(seal_path, "review seal")
    validate_schema(seal, HERE / "pilot-review-seal.schema.json", "review seal")
    if seal["experiment_id"] != CAMPAIGN_ID or seal["assignments_decoded"] is not False:
        raise CampaignError("review seal identity or decode boundary drifted")
    pairs = {item["pair_id"]: item for item in seal["pairs"]}
    expected_pairs = {f"PL-{case}-P01" for case in REVIEW_CASES}
    if set(pairs) != expected_pairs or len(pairs) != 4:
        raise CampaignError("all four exact reviews must be sealed before decode")
    if seal["aggregate_sha256"] != sha256_bytes(canonical_bytes(seal["pairs"])):
        raise CampaignError("review seal aggregate hash drifted")
    _, assignments = _scenario_maps(freeze)
    decoded: list[dict[str, Any]] = []
    for pair_id in sorted(expected_pairs):
        sealed = pairs[pair_id]
        for field in ("blind_manifest", "review_result", "usage_receipt"):
            path = _confined_path(campaign_root, sealed[field]["path"], f"sealed {pair_id} {field}")
            _regular_file(path, f"sealed {pair_id} {field}")
            if sha256_file(path) != sealed[field]["sha256"]:
                raise CampaignError(f"sealed {pair_id} {field} hash drifted")
        review_path = _confined_path(campaign_root, sealed["review_result"]["path"], "sealed review result")
        review = load_json(review_path, f"review result {pair_id}")
        validate_schema(review, HERE / "pilot-blind-review-result.schema.json", f"review result {pair_id}")
        labels = {label: assignments[pair_id][label] for label in ("A", "B")}
        preference = review["preference"]
        preferred_arm = labels.get(preference)
        decoded.append({
            "pair_id": pair_id,
            "labels": labels,
            "preference": preference,
            "preferred_arm": preferred_arm,
            "preferred_protocol": preferred_arm.rsplit("-", 1)[1] if preferred_arm is not None else None,
            "severe_regression_arms": sorted(labels[label] for label in review["severe_regression_labels"]),
            "review_result_sha256": sha256_file(review_path),
        })
    result = {
        "schema_version": "1.0",
        "algorithm": "sealed-pilot-review-decode-v1",
        "experiment_id": CAMPAIGN_ID,
        "review_seal": _relative_binding(seal_path, campaign_root),
        "reviews": decoded,
        "aggregate_sha256": sha256_bytes(canonical_bytes(decoded)),
    }
    validate_schema(result, HERE / "pilot-decoded-reviews.schema.json", "decoded reviews")
    write_json(output, result)
    return result


def finalize_oracles(
    *,
    campaign_root: Path,
    observations_root: Path,
    attestations_root: Path,
    output_root: Path,
) -> list[Path]:
    campaign_root = campaign_root.resolve()
    paths: list[Path] = []
    for case_id in CASE_ORDER:
        for protocol in ("v1", "v2"):
            arm_id = f"PL-{case_id}-P01-{protocol}"
            observation = _regular_file(observations_root / f"{arm_id}.json", f"oracle observation {arm_id}")
            attestation = _regular_file(attestations_root / f"{arm_id}.json", f"maintainer attestation {arm_id}")
            value = load_json(attestation, f"maintainer attestation {arm_id}")
            validate_schema(value, HERE / "pilot-oracle-judgment.schema.json", f"maintainer attestation {arm_id}")
            if value.get("evaluator", {}).get("kind") != "human":
                raise CampaignError(f"maintainer attestation {arm_id} must be human-attested")
            if value.get("arm_id") != arm_id or value.get("observation_sha256") != sha256_file(observation):
                raise CampaignError(f"maintainer attestation {arm_id} identity drifted")
            output = output_root / f"{arm_id}.json"
            pilot_runners.finalize_oracle(
                observation_path=observation,
                judgment_path=attestation,
                output=output,
            )
            paths.append(output)
    if len(paths) != 12:
        raise CampaignError("oracle result exact set drifted")
    return paths


def _authority_binding(campaign_root: Path, root: Path) -> dict[str, Any]:
    root = root.resolve()
    try:
        relative_root = root.relative_to(campaign_root.resolve()).as_posix()
    except ValueError as exc:
        raise CampaignError("authority execution root escapes the campaign root") from exc
    return {
        "root": {"path": relative_root},
        "grant": _relative_binding(root / "grant.json", campaign_root),
        "ledger_anchor": _relative_binding(root / "ledger-anchor.json", campaign_root),
        "spend_summary": _relative_binding(root / "spend-summary.json", campaign_root),
    }


def _hash_without(document: dict[str, Any], field: str) -> str:
    return sha256_bytes(canonical_bytes({key: value for key, value in document.items() if key != field}))


def assemble_evaluation_input(
    *,
    freeze: dict[str, Any],
    campaign_root: Path,
    authority_roots: dict[str, Path],
    oracle_root: Path,
    review_results_root: Path,
    reviewer_output_root: Path,
    review_seal_path: Path,
    output: Path,
) -> dict[str, Any]:
    campaign_root = campaign_root.resolve()
    frozen_inputs = _ensure_frozen_bundle(freeze=freeze, campaign_root=campaign_root)
    episodes = load_episode_bindings(campaign_root)
    expected_arm_ids = [f"PL-{case}-P01-{protocol}" for case in CASE_ORDER for protocol in ("v1", "v2")]
    oracle_results = []
    for arm_id in expected_arm_ids:
        path = _regular_file(oracle_root / f"{arm_id}.json", f"oracle result {arm_id}")
        oracle_results.append({"arm_id": arm_id, **_relative_binding(path, campaign_root)})
    blind_manifests = []
    review_results = []
    reviewer_receipts = []
    for case_id in REVIEW_CASES:
        pair_id = f"PL-{case_id}-P01"
        blind = _regular_file(campaign_root / "review-input" / pair_id / "blind-manifest.json", f"blind manifest {pair_id}")
        review = _regular_file(review_results_root / f"{pair_id}-review-result.json", f"review result {pair_id}")
        receipt = _regular_file(reviewer_output_root / f"{pair_id}-review" / "usage-receipt.json", f"review receipt {pair_id}")
        blind_manifests.append({"pair_id": pair_id, **_relative_binding(blind, campaign_root)})
        review_results.append({"pair_id": pair_id, **_relative_binding(review, campaign_root)})
        reviewer_receipts.append({"pair_id": pair_id, **_relative_binding(receipt, campaign_root)})
    manifest = {
        "schema_version": "1.0",
        "experiment_id": CAMPAIGN_ID,
        "pilot_scenarios": _relative_binding(frozen_inputs["scenarios"], campaign_root),
        "pilot_run_plan": _relative_binding(frozen_inputs["run_plan"], campaign_root),
        "pilot_evaluator": _relative_binding(frozen_inputs["evaluator"], campaign_root),
        "calibration_authority": _authority_binding(campaign_root, authority_roots["calibration"]),
        "calibration_result": _relative_binding(frozen_inputs["calibration_result"], campaign_root),
        "producer_authority": _authority_binding(campaign_root, authority_roots["producer"]),
        "reviewer_authority": _authority_binding(campaign_root, authority_roots["reviewer"]),
        "producer_episodes": episodes,
        "oracle_results": oracle_results,
        "blind_manifests": blind_manifests,
        "blind_review_results": review_results,
        "reviewer_receipts": reviewer_receipts,
        "review_seal": _relative_binding(review_seal_path, campaign_root),
        "aggregate_sha256": "0" * 64,
    }
    manifest["aggregate_sha256"] = _hash_without(manifest, "aggregate_sha256")
    validate_schema(manifest, HERE / "pilot-evaluation-input-manifest.schema.json", "Pilot evaluation input manifest")
    write_json(output, manifest)
    return manifest


def write_report_and_stop(
    *,
    campaign_root: Path,
    final_freeze_path: Path,
    evaluation_input_path: Path,
    decoded_reviews_path: Path,
    observations_root: Path,
    attestations_root: Path,
    oracle_root: Path,
    report_path: Path,
    evidence_manifest_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    campaign_root = campaign_root.resolve()
    report = evaluation.evaluate_pilot(campaign_root, evaluation_input_path)
    if report.get("formal_execution_enabled") is not False:
        raise CampaignError("Pilot report attempted to enable formal execution")
    write_json(report_path, report)
    files: list[dict[str, str]] = [
        {"role": "final_freeze", "id": "final-freeze", **_relative_binding(final_freeze_path, campaign_root)},
        {"role": "decoded_reviews", "id": "decoded-reviews", **_relative_binding(decoded_reviews_path, campaign_root)},
        {"role": "evaluation_input", "id": "evaluation-input", **_relative_binding(evaluation_input_path, campaign_root)},
        {"role": "report", "id": "pilot-report", **_relative_binding(report_path, campaign_root)},
    ]
    for case_id in CASE_ORDER:
        for protocol in ("v1", "v2"):
            arm_id = f"PL-{case_id}-P01-{protocol}"
            for role, root in (
                ("oracle_observation", observations_root),
                ("maintainer_attestation", attestations_root),
                ("oracle_result", oracle_root),
            ):
                path = _regular_file(root / f"{arm_id}.json", f"{role} {arm_id}")
                files.append({"role": role, "id": arm_id, **_relative_binding(path, campaign_root)})
    files.sort(key=lambda item: (item["role"], item["id"]))
    evidence = {
        "schema_version": "1.0",
        "algorithm": "sha256-pilot-campaign-evidence-v1",
        "experiment_id": CAMPAIGN_ID,
        "campaign_status": "pilot-complete-stopped",
        "stop_after_report": True,
        "formal_execution_enabled": False,
        "next_action": "await-user-decision",
        "files": files,
        "aggregate_sha256": sha256_bytes(canonical_bytes(files)),
    }
    validate_schema(evidence, HERE / "pilot-campaign-evidence-manifest.schema.json", "Pilot campaign evidence manifest")
    write_json(evidence_manifest_path, evidence)
    return report, evidence


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    commands = value.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--final-freeze", type=Path, required=True)
    capture = commands.add_parser("capture")
    capture.add_argument("--final-freeze", type=Path, required=True)
    capture.add_argument("--campaign-root", type=Path, required=True)
    capture.add_argument("--producer-output", type=Path, required=True)
    capture.add_argument("--run-id", required=True)
    reviews = commands.add_parser("prepare-reviews")
    reviews.add_argument("--final-freeze", type=Path, required=True)
    reviews.add_argument("--campaign-root", type=Path, required=True)
    reviews.add_argument("--reviewer-grant", type=Path, required=True)
    decode = commands.add_parser("decode-reviews")
    decode.add_argument("--final-freeze", type=Path, required=True)
    decode.add_argument("--campaign-root", type=Path, required=True)
    decode.add_argument("--review-seal", type=Path, required=True)
    decode.add_argument("--output", type=Path, required=True)
    return value


def main(argv: Iterable[str] | None = None) -> int:
    args = parser().parse_args(list(argv) if argv is not None else None)
    try:
        freeze = load_final_freeze(args.final_freeze)
        if args.command == "plan":
            result: Any = {"status": "valid", "network_calls": 0, "producer_episodes": producer_schedule(freeze["run_plan"])}
        elif args.command == "capture":
            result = capture_episode(
                freeze=freeze,
                campaign_root=args.campaign_root,
                producer_output=args.producer_output,
                run_id=args.run_id,
            )
        elif args.command == "prepare-reviews":
            paths = prepare_blind_reviews(
                freeze=freeze,
                campaign_root=args.campaign_root,
                reviewer_grant_path=args.reviewer_grant,
            )
            result = {"status": "prepared", "network_calls": 0, "blind_manifests": [str(path) for path in paths]}
        else:
            result = decode_reviews(
                freeze=freeze,
                campaign_root=args.campaign_root,
                review_seal_path=args.review_seal,
                output=args.output,
            )
        json.dump(result, sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0
    except (CampaignError, guard.GuardError, evaluation.EvaluationError, pilot_runners.RunnerError) as exc:
        print(f"pilot campaign error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
