#!/usr/bin/env python3
"""Build and verify the pilot's two-stage execution authority chain.

This module is deliberately offline.  It never launches Codex, creates an
authorization grant, settles usage, or refreshes the repository-wide source
freeze.  A calibration grant binds the pre-calibration manifest; producer and
reviewer grants bind the final manifest created only after raw calibration
evidence has been replayed and reconciled.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

import codex_exec_adapter as adapter
import execution_guard as guard
import pilot_harness
import snapshot_tools as snapshots
import workspace_builder as workspaces
import network_execution_boundary as execution_boundary
from schema_runtime import SchemaError, check_schema, validate


HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parents[1]
REPO_ROOT = SKILL_ROOT.parents[1]
PRE_FREEZE_SCHEMA = HERE / "pilot-pre-calibration-freeze.schema.json"
FINAL_FREEZE_SCHEMA = HERE / "pilot-final-freeze.schema.json"
CALIBRATION_SCHEMA = HERE / "pilot-calibration-result.schema.json"
RECEIPT_SCHEMA = HERE / "usage-receipt.schema.json"
EVIDENCE_SCHEMA = HERE / "evidence-manifest.schema.json"
COMPLETION_SCHEMA = HERE / "completion-claim.schema.json"
CLI_SCHEMA = HERE / "cli-identity.schema.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
CALIBRATION_CALL = {"run_id": "pilot-calibration", "episode_id": "calibration"}
CALIBRATION_LIMITS = {
    "per_call": {"max_total_tokens": 10_000, "max_wall_seconds": 300},
    "total": {"max_calls": 1, "max_total_tokens": 10_000, "max_wall_seconds": 300},
}
PILOT_FREEZE_DOCUMENTS: dict[str, str] = {
    "baseline-source.tar": "source",
    "instrument-manifest.json": "instrument",
    "pilot-preregistration.json": "preregistration",
    "pilot-run-plan.json": "run-plan",
}
PILOT_STATIC_INPUTS: dict[str, str] = {
    **snapshots.EXPERIMENT_INSTRUMENT_INPUTS,
    **PILOT_FREEZE_DOCUMENTS,
}


class PilotFreezeError(RuntimeError):
    """A two-stage pilot authority invariant failed."""


def canonical_bytes(value: Any) -> bytes:
    try:
        return snapshots.canonical_bytes(value)
    except snapshots.SnapshotError as exc:
        raise PilotFreezeError(f"value is not strict canonical JSON: {exc}") from exc


def sha256_bytes(value: bytes) -> str:
    return snapshots.sha256_bytes(value)


def sha256_file(path: Path) -> str:
    return snapshots.sha256_file(path)


def _now_text(value: datetime | None = None) -> str:
    return (value or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def _load_json(path: Path, label: str) -> Any:
    if not path.is_file() or path.is_symlink():
        raise PilotFreezeError(f"{label} must be a regular non-symlink file")
    try:
        return snapshots.load_json(path)
    except snapshots.SnapshotError as exc:
        raise PilotFreezeError(f"cannot load {label}: {exc}") from exc


def _validate_schema(value: Any, schema_path: Path, label: str) -> None:
    schema = _load_json(schema_path, f"{label} schema")
    try:
        check_schema(schema)
        errors = validate(value, schema)
    except SchemaError as exc:
        raise PilotFreezeError(f"{label} schema is unsupported: {exc}") from exc
    if errors:
        raise PilotFreezeError(f"{label} schema validation failed: {'; '.join(errors)}")


def _safe_relative(value: str, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise PilotFreezeError(f"{label} path is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise PilotFreezeError(f"{label} path is unsafe")
    return path


def _resolve_file(root: Path, value: str, label: str) -> Path:
    relative = _safe_relative(value, label)
    resolved_root = root.resolve()
    path = resolved_root.joinpath(*relative.parts)
    try:
        path.resolve().relative_to(resolved_root)
    except ValueError as exc:
        raise PilotFreezeError(f"{label} escapes its authority root") from exc
    if not path.is_file() or path.is_symlink():
        raise PilotFreezeError(f"{label} must be a regular non-symlink file")
    return path


def _binding(path: Path, root: Path) -> dict[str, str]:
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise PilotFreezeError("authority binding escaped its root") from exc
    return {"path": relative, "sha256": sha256_file(path)}


def _confined_regular_file(path: Path, root: Path, label: str) -> Path:
    resolved_root = root.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise PilotFreezeError(f"{label} escaped its authority root") from exc
    if not path.is_file() or path.is_symlink():
        raise PilotFreezeError(f"{label} must be a regular non-symlink file")
    return resolved


def _canonical_grant(execution_root: Path, authority_root: Path) -> tuple[Path, dict[str, Any]]:
    root = execution_root.resolve()
    if not root.is_dir() or execution_root.is_symlink():
        raise PilotFreezeError("calibration execution root must be a regular directory")
    try:
        root.relative_to(authority_root.resolve())
    except ValueError as exc:
        raise PilotFreezeError("calibration execution root escaped its authority root") from exc
    grant_path = _confined_regular_file(root / "grant.json", authority_root, "calibration grant")
    grant = guard.load_grant(grant_path)
    if grant["execution_root_sha256"] != guard._root_path_sha256(root):
        raise PilotFreezeError("calibration grant belongs to another execution root")
    return grant_path, grant


def _load_binding(root: Path, binding: Mapping[str, Any], label: str) -> Path:
    if not isinstance(binding, Mapping) or set(binding) != {"path", "sha256"}:
        raise PilotFreezeError(f"{label} binding has the wrong fields")
    path = _resolve_file(root, binding["path"], label)
    if sha256_file(path) != binding["sha256"]:
        raise PilotFreezeError(f"{label} hash drifted")
    return path


def _entry(path: Path, root: Path, role: str) -> dict[str, Any]:
    binding = _binding(path, root)
    return {**binding, "role": role, "size": path.stat().st_size}


def _aggregate(entries: Iterable[dict[str, Any]]) -> str:
    return sha256_bytes(canonical_bytes(list(entries)))


def _manifest_bytes(value: dict[str, Any], schema_path: Path, label: str) -> bytes:
    _validate_schema(value, schema_path, label)
    return canonical_bytes(value)


def _cli_binding(
    root: Path,
    preregistration: Mapping[str, Any],
    role: str,
) -> tuple[dict[str, str], dict[str, Any]]:
    identities = preregistration.get("cli_identities")
    if not isinstance(identities, Mapping) or identities.get("calibration_reuses") != "producer":
        raise PilotFreezeError("pilot CLI identities must make calibration reuse producer")
    slot = identities.get(role)
    if not isinstance(slot, Mapping):
        raise PilotFreezeError(f"pilot {role} CLI identity is missing")
    expected_platform = "windows" if role == "producer" else "linux"
    if (
        slot.get("status") != "frozen"
        or slot.get("platform") != expected_platform
        or slot.get("arch") != "x86_64"
        or slot.get("version") != "0.144.1"
    ):
        reason = slot.get("reason")
        suffix = f": {reason}" if isinstance(reason, str) and reason else ""
        raise PilotFreezeError(f"pilot {role} CLI identity is unresolved or drifted{suffix}")
    binding = slot.get("binding")
    if not isinstance(binding, Mapping) or set(binding) != {"id", "path", "sha256"}:
        raise PilotFreezeError(f"pilot {role} CLI identity binding is invalid")
    identity_path = _load_binding(
        root,
        {"path": binding["path"], "sha256": binding["sha256"]},
        f"{role} CLI identity",
    )
    identity = _load_json(identity_path, f"{role} CLI identity")
    _validate_schema(identity, CLI_SCHEMA, f"{role} CLI identity")
    if (
        identity.get("id") != binding["id"]
        or identity.get("version") != slot["version"]
        or identity.get("platform", "windows") != expected_platform
        or identity.get("arch", "x86_64") != slot["arch"]
    ):
        raise PilotFreezeError(f"pilot {role} CLI identity document drifted")
    return {"path": binding["path"], "sha256": binding["sha256"]}, identity


def _validate_cli_identities(
    root: Path,
    preregistration: Mapping[str, Any],
) -> dict[str, dict[str, str]]:
    producer, _ = _cli_binding(root, preregistration, "producer")
    reviewer, _ = _cli_binding(root, preregistration, "reviewer")
    if producer == reviewer:
        raise PilotFreezeError("producer and reviewer CLI identities must be independent")
    return {"producer_cli": producer, "reviewer_cli": reviewer}


def _expected_bindings(root: Path, preregistration: dict[str, Any]) -> dict[str, dict[str, str]]:
    cli_bindings = _validate_cli_identities(root, preregistration)
    return {
        "preregistration": _binding(root / "pilot-preregistration.json", root),
        "run_plan": _binding(root / "pilot-run-plan.json", root),
        "instrument": _binding(root / preregistration["instrument_manifest"]["path"], root),
        "scenarios": _binding(root / preregistration["scenario_manifest"]["path"], root),
        "evaluator": _binding(root / preregistration["evaluator_manifest"]["path"], root),
        "adapter": _binding(root / preregistration["execution"]["adapter"]["path"], root),
        "provider": _binding(root / preregistration["provider"]["path"], root),
        **cli_bindings,
        "tool_profile": _binding(root / preregistration["execution"]["tool_profile"]["path"], root),
        "protocol_v1": _binding(root / "protocol-bundles/v1/bundle-manifest.json", root),
        "protocol_v2": _binding(root / "protocol-bundles/v2/bundle-manifest.json", root),
    }


def _validate_protocol_bundles(root: Path) -> None:
    for protocol in ("v1", "v2"):
        bundle_root = root / "protocol-bundles" / protocol
        try:
            workspaces.validate_protocol_bundle(bundle_root)
        except workspaces.WorkspaceError as exc:
            raise PilotFreezeError(f"{protocol} protocol bundle is invalid: {exc}") from exc


def _static_entries(
    root: Path,
    preregistration: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for relative, role in sorted(PILOT_STATIC_INPUTS.items()):
        entries.append(_entry(_resolve_file(root, relative, f"static input {relative}"), root, role))
    if preregistration is not None:
        for name, binding in sorted(_validate_cli_identities(root, preregistration).items()):
            relative = binding["path"]
            if relative not in PILOT_STATIC_INPUTS:
                entries.append(_entry(_resolve_file(root, relative, name), root, "tool-profile"))
    for protocol in ("v1", "v2"):
        bundle_root = root / "protocol-bundles" / protocol
        for path in sorted(bundle_root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
            if path.is_symlink():
                raise PilotFreezeError(f"protocol bundle contains a symlink: {path}")
            if path.is_file():
                entries.append(_entry(path, root, f"protocol-{protocol}"))
    paths = [item["path"] for item in entries]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        entries.sort(key=lambda item: item["path"])
        paths = [item["path"] for item in entries]
        if len(paths) != len(set(paths)):
            raise PilotFreezeError("authority freeze inputs contain duplicate paths")
    return entries


def _validate_static_authority(root: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    preregistration_path = root / "pilot-preregistration.json"
    preregistration = _load_json(preregistration_path, "pilot preregistration")
    _validate_schema(
        preregistration,
        root / "pilot-preregistration.schema.json",
        "pilot preregistration",
    )
    _validate_cli_identities(root, preregistration)
    try:
        validated_preregistration, _, plan = pilot_harness.load_and_validate(root)
    except pilot_harness.PilotError as exc:
        raise PilotFreezeError(f"pilot static authority is invalid: {exc}") from exc
    if validated_preregistration != preregistration:
        raise PilotFreezeError("pilot preregistration changed during static validation")
    _validate_protocol_bundles(root)
    instrument_path = root / preregistration["instrument_manifest"]["path"]
    instrument = _load_json(instrument_path, "instrument manifest")
    baseline_path = _load_binding(root, preregistration["baseline"]["manifest"], "baseline source")
    candidate_path = _load_binding(root, preregistration["candidate"]["manifest"], "candidate source")
    baseline = _load_json(baseline_path, "baseline source")
    candidate = _load_json(candidate_path, "candidate source")
    try:
        snapshots.validate_source_snapshot(
            baseline,
            archive_bytes=(root / "baseline-source.tar").read_bytes(),
        )
        snapshots.validate_source_snapshot(
            candidate,
            skill_root=SKILL_ROOT,
            repo_root=REPO_ROOT,
        )
    except (OSError, snapshots.SnapshotError) as exc:
        raise PilotFreezeError(f"pilot source freeze is invalid: {exc}") from exc
    if (
        preregistration["baseline"]["aggregate_sha256"] != baseline["aggregate_sha256"]
        or preregistration["candidate"]["aggregate_sha256"] != candidate["aggregate_sha256"]
        or preregistration["baseline"]["origin_commit"] != baseline["origin"]["commit"]
        or preregistration["candidate"]["origin_commit"] != candidate["origin"]["base_git_commit"]
    ):
        raise PilotFreezeError("pilot source identity drifted from preregistration")
    source_snapshots = [
        preregistration["baseline"]["aggregate_sha256"],
        preregistration["candidate"]["aggregate_sha256"],
    ]
    if instrument.get("source_snapshots") != source_snapshots:
        raise PilotFreezeError("instrument source snapshots drifted from pilot preregistration")
    if plan.get("preregistration_sha256") != sha256_file(root / "pilot-preregistration.json"):
        raise PilotFreezeError("run plan preregistration binding drifted")
    entries = _static_entries(root, preregistration)
    return preregistration, plan, entries


def build_pre_calibration_freeze(
    experiment_dir: Path = HERE,
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    root = experiment_dir.resolve()
    preregistration, _, entries = _validate_static_authority(root)
    try:
        execution_boundary.require_execution_ready(preregistration, root)
    except execution_boundary.ExecutionBoundaryError as exc:
        raise PilotFreezeError(f"Pilot execution boundary is not ready: {exc}") from exc
    manifest = {
        "schema_version": "1.0",
        "kind": "pilot-authority-freeze",
        "experiment_id": preregistration["campaign_id"],
        "phase": "pre-calibration",
        "algorithm": "sha256-pilot-authority-freeze-v1",
        "created_at": created_at or _now_text(),
        "source_snapshots": [
            preregistration["baseline"]["aggregate_sha256"],
            preregistration["candidate"]["aggregate_sha256"],
        ],
        "bindings": _expected_bindings(root, preregistration),
        "files": entries,
        "aggregate_sha256": _aggregate(entries),
    }
    _manifest_bytes(manifest, PRE_FREEZE_SCHEMA, "pre-calibration freeze")
    return manifest


def build_calibration_result(
    *,
    experiment_id: str,
    pre_freeze_path: Path,
    execution_root: Path,
    raw_provider_events_path: Path,
    usage_receipt_path: Path,
    evidence_manifest_path: Path,
    response_path: Path,
    authority_root: Path,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Derive the calibration result from raw JSONL and immutable artifact bytes."""
    root = authority_root.resolve()
    grant_path, _ = _canonical_grant(execution_root, root)
    artifacts = {
        "pre_calibration_freeze": pre_freeze_path,
        "raw_provider_events": raw_provider_events_path,
        "usage_receipt": usage_receipt_path,
        "evidence_manifest": evidence_manifest_path,
        "response": response_path,
    }
    for label, path in artifacts.items():
        _confined_regular_file(path, root, f"calibration {label}")
    records, usage, request_id = _usage_from_raw(raw_provider_events_path)
    result = {
        "schema_version": "1.0",
        "experiment_id": experiment_id,
        "run_id": "pilot-calibration",
        "episode_id": "calibration",
        "binding_root": "experiment-authority-root",
        "pre_calibration_freeze": _binding(pre_freeze_path, root),
        "grant": _binding(grant_path, root),
        "provider_request_ids": [request_id],
        "provider_request_identity": {
            "value": request_id,
            "observations": _provider_observations(records, request_id),
        },
        "usage": {"value": usage, "observation": _usage_observation(records, usage)},
        "usage_receipt": _binding(usage_receipt_path, root),
        "evidence_manifest": _binding(evidence_manifest_path, root),
        "raw_provider_events": _binding(raw_provider_events_path, root),
        "response": _binding(response_path, root),
        "generated_at": generated_at or _now_text(),
    }
    _validate_schema(result, CALIBRATION_SCHEMA, "pilot calibration result")
    return result


def validate_pre_calibration_freeze(
    path: Path,
    *,
    experiment_dir: Path = HERE,
) -> dict[str, Any]:
    root = experiment_dir.resolve()
    value = _load_json(path, "pre-calibration freeze")
    _validate_schema(value, PRE_FREEZE_SCHEMA, "pre-calibration freeze")
    expected = build_pre_calibration_freeze(root, created_at=value["created_at"])
    if value != expected:
        raise PilotFreezeError("pre-calibration freeze drifted from its exact static input set")
    return value


def _usage_from_raw(path: Path) -> tuple[list[dict[str, Any]], dict[str, int], str]:
    try:
        records = adapter._strict_jsonl(path)
        candidates = adapter._usage_candidates(records)
        request_ids = adapter._provider_request_ids(records)
    except adapter.AdapterError as exc:
        raise PilotFreezeError(f"calibration raw JSONL is not authoritative: {exc}") from exc
    if len(candidates) != 1 or len(request_ids) != 1:
        raise PilotFreezeError("calibration raw JSONL must contain one request identity and one usage record")
    return records, candidates[0], request_ids[0]


def _json_pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _walk_json(value: Any, pointer: str = "") -> Iterable[tuple[str, Any]]:
    yield pointer, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_json(child, f"{pointer}/{_json_pointer_token(key)}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_json(child, f"{pointer}/{index}")


def _provider_observations(records: list[dict[str, Any]], request_id: str) -> list[dict[str, str]]:
    observations: set[tuple[str, str, str]] = set()
    for index, record in enumerate(records):
        event_type = record.get("type")
        if not isinstance(event_type, str):
            continue
        for pointer, value in _walk_json(record, f"/{index}"):
            if not isinstance(value, dict):
                continue
            for field in ("provider_request_id", "upstream_request_id"):
                if value.get(field) == request_id:
                    observations.add((event_type, f"{pointer}/{field}", field))
    if not observations:
        raise PilotFreezeError("calibration request identity lacks a source observation")
    return [
        {"event_type": event_type, "json_pointer": pointer, "field": field}
        for event_type, pointer, field in sorted(observations)
    ]


def _usage_observation(
    records: list[dict[str, Any]], usage: dict[str, int]
) -> dict[str, str]:
    found: list[tuple[str, str]] = []
    for index, record in enumerate(records):
        event_type = record.get("type")
        if event_type not in {"turn.completed", "response.completed", "usage"}:
            continue
        for pointer, value in _walk_json(record, f"/{index}"):
            if isinstance(value, dict) and value == usage:
                found.append((event_type, pointer))
    if len(found) != 1:
        raise PilotFreezeError("calibration usage must have one exact event and JSON pointer")
    event_type, pointer = found[0]
    return {"event_type": event_type, "json_pointer": pointer}


def _calibration_artifact_paths(
    authority_root: Path,
    calibration_result_path: Path,
    result: dict[str, Any],
) -> dict[str, Path]:
    root = authority_root.resolve()
    calibration_result = _confined_regular_file(
        calibration_result_path, root, "pilot calibration result"
    )
    return {
        "calibration_result": calibration_result,
        "grant": _load_binding(root, result["grant"], "calibration grant"),
        "raw_provider_events": _load_binding(root, result["raw_provider_events"], "calibration raw events"),
        "usage_receipt": _load_binding(root, result["usage_receipt"], "calibration usage receipt"),
        "evidence_manifest": _load_binding(root, result["evidence_manifest"], "calibration evidence manifest"),
        "response": _load_binding(root, result["response"], "calibration response"),
    }


def validate_calibration_result(
    calibration_result_path: Path,
    *,
    pre_freeze_path: Path,
    authority_root: Path,
    experiment_dir: Path = HERE,
) -> dict[str, Any]:
    experiment_root = experiment_dir.resolve()
    authority = authority_root.resolve()
    pre = validate_pre_calibration_freeze(pre_freeze_path, experiment_dir=experiment_root)
    result = _load_json(calibration_result_path, "pilot calibration result")
    _validate_schema(result, CALIBRATION_SCHEMA, "pilot calibration result")
    if result["experiment_id"] != pre["experiment_id"]:
        raise PilotFreezeError("calibration result experiment identity drifted")
    if result["binding_root"] != "experiment-authority-root":
        raise PilotFreezeError("calibration result uses the wrong binding root")
    _confined_regular_file(calibration_result_path, authority, "pilot calibration result")
    pre_binding = result["pre_calibration_freeze"]
    if _load_binding(authority, pre_binding, "calibration pre-freeze").resolve() != pre_freeze_path.resolve():
        raise PilotFreezeError("calibration result binds a different pre-calibration freeze")
    artifacts = _calibration_artifact_paths(authority, calibration_result_path, result)
    if artifacts["grant"].name != "grant.json":
        raise PilotFreezeError("calibration result does not bind the canonical grant.json")
    execution_root = artifacts["grant"].parent
    canonical_grant_path, grant = _canonical_grant(execution_root, authority)
    if artifacts["grant"] != canonical_grant_path:
        raise PilotFreezeError("calibration result does not bind the canonical grant.json")
    if grant["role"] != "calibration":
        raise PilotFreezeError("calibration result grant has the wrong role")
    if grant["authorized_calls"] != [CALIBRATION_CALL] or grant["limits"] != CALIBRATION_LIMITS:
        raise PilotFreezeError("calibration grant call or budget drifted")
    if grant["authority_evidence_sha256"] != sha256_file(pre_freeze_path):
        raise PilotFreezeError("calibration grant does not bind the pre-calibration freeze")
    records, usage, request_id = _usage_from_raw(artifacts["raw_provider_events"])
    if result["provider_request_ids"] != [request_id]:
        raise PilotFreezeError("calibration result request identity disagrees with raw JSONL")
    expected_identity = {
        "value": request_id,
        "observations": _provider_observations(records, request_id),
    }
    if result["provider_request_identity"] != expected_identity:
        raise PilotFreezeError("calibration request observations disagree with raw JSONL")
    if result["usage"] != {"value": usage, "observation": _usage_observation(records, usage)}:
        raise PilotFreezeError("calibration result usage disagrees with raw JSONL")
    receipt = _load_json(artifacts["usage_receipt"], "calibration usage receipt")
    _validate_schema(receipt, RECEIPT_SCHEMA, "calibration usage receipt")
    if (
        receipt["role"] != "calibration"
        or receipt["run_id"] != "pilot-calibration"
        or receipt["episode_id"] != "calibration"
        or receipt["authorization_id"] != grant["authorization_id"]
        or receipt["execution_id"] != grant["execution_id"]
        or receipt["adapter"] != grant["adapter"]
        or receipt["cli_identity"] != grant["cli_identity"]
        or receipt["provider_profile"] != grant["provider_profile"]
        or receipt["model"] != grant["model"]
        or receipt["reasoning_effort"] != grant["reasoning_effort"]
        or receipt["tool_profile"] != grant["tool_profile"]
        or receipt["source_class"] != "provider-response"
        or receipt["provider_request_ids"] != [request_id]
        or {field: receipt["usage"][field] for field in usage} != usage
        or receipt["raw_evidence_sha256"] != sha256_file(artifacts["raw_provider_events"])
        or receipt["evidence_manifest_sha256"] != sha256_file(artifacts["evidence_manifest"])
        or receipt["response_sha256"] != sha256_file(artifacts["response"])
    ):
        raise PilotFreezeError("calibration receipt disagrees with raw evidence or grant authority")
    evidence = _load_json(artifacts["evidence_manifest"], "calibration evidence manifest")
    _validate_schema(evidence, EVIDENCE_SCHEMA, "calibration evidence manifest")
    if (
        evidence["role"] != "calibration"
        or evidence["run_id"] != "pilot-calibration"
        or evidence["episode_id"] != "calibration"
    ):
        raise PilotFreezeError("calibration evidence identity drifted")
    evidence_root = artifacts["evidence_manifest"].parent
    roles: dict[str, Path] = {}
    for item in evidence["files"]:
        path = _resolve_file(evidence_root, item["path"], f"calibration evidence {item['role']}")
        if sha256_file(path) != item["sha256"]:
            raise PilotFreezeError(f"calibration evidence file drifted: {item['role']}")
        if item["role"] in roles:
            raise PilotFreezeError(f"calibration evidence role is duplicated: {item['role']}")
        roles[item["role"]] = path
    if evidence["aggregate_sha256"] != _aggregate(evidence["files"]):
        raise PilotFreezeError("calibration evidence aggregate hash drifted")
    required_roles = {
        "request", "provider_events", "provider_response", "structured_claim",
        "initial_workspace", "final_workspace",
    }
    if not required_roles <= set(roles):
        raise PilotFreezeError("calibration evidence lacks required direct artifacts")
    if (
        roles["provider_events"].resolve() != artifacts["raw_provider_events"].resolve()
        or roles["provider_response"].resolve() != artifacts["response"].resolve()
        or receipt["request_sha256"] != sha256_file(roles["request"])
    ):
        raise PilotFreezeError("calibration evidence manifest points to different raw artifacts")
    for field, role in (
        ("initial_workspace_manifest", "initial_workspace"),
        ("final_workspace_manifest", "final_workspace"),
        ("structured_claim", "structured_claim"),
    ):
        binding_path = _load_binding(evidence_root, evidence[field], f"calibration {field}")
        if binding_path.resolve() != roles[role].resolve():
            raise PilotFreezeError(f"calibration evidence {field} points to a different artifact")
    response = _load_json(artifacts["response"], "calibration response")
    _validate_schema(response, COMPLETION_SCHEMA, "calibration response")
    return result


def build_final_freeze(
    *,
    experiment_dir: Path,
    authority_root: Path,
    pre_freeze_path: Path,
    calibration_result_path: Path,
    created_at: str | None = None,
) -> dict[str, Any]:
    root = experiment_dir.resolve()
    preregistration, _, entries = _validate_static_authority(root)
    try:
        execution_boundary.require_execution_ready(preregistration, root)
    except execution_boundary.ExecutionBoundaryError as exc:
        raise PilotFreezeError(f"Pilot execution boundary is not ready: {exc}") from exc
    authority = authority_root.resolve()
    pre = validate_pre_calibration_freeze(pre_freeze_path, experiment_dir=root)
    result = validate_calibration_result(
        calibration_result_path,
        pre_freeze_path=pre_freeze_path,
        authority_root=authority,
        experiment_dir=root,
    )
    if pre["files"] != entries or pre["bindings"] != _expected_bindings(root, preregistration):
        raise PilotFreezeError("static authority changed after calibration")
    artifact_paths = _calibration_artifact_paths(authority, calibration_result_path, result)
    artifacts = [
        _entry(path, authority, role)
        for role, path in sorted(artifact_paths.items())
    ]
    manifest = {
        "schema_version": "1.0",
        "kind": "pilot-authority-freeze",
        "experiment_id": preregistration["campaign_id"],
        "phase": "final-pilot",
        "algorithm": "sha256-pilot-authority-freeze-v1",
        "created_at": created_at or _now_text(),
        "binding_root": "experiment-authority-root",
        "pre_calibration_freeze": _binding(pre_freeze_path, authority),
        "calibration_result": _binding(calibration_result_path, authority),
        "calibration_artifacts": artifacts,
        "source_snapshots": pre["source_snapshots"],
        "bindings": pre["bindings"],
        "files": entries,
        "aggregate_sha256": _aggregate(entries),
    }
    _manifest_bytes(manifest, FINAL_FREEZE_SCHEMA, "final pilot freeze")
    return manifest


def validate_final_freeze(
    path: Path,
    *,
    experiment_dir: Path,
) -> dict[str, Any]:
    value = _load_json(path, "final pilot freeze")
    _validate_schema(value, FINAL_FREEZE_SCHEMA, "final pilot freeze")
    authority = path.resolve().parent
    if value["binding_root"] != "experiment-authority-root":
        raise PilotFreezeError("final pilot freeze uses the wrong binding root")
    pre_path = _load_binding(authority, value["pre_calibration_freeze"], "final freeze pre-freeze")
    calibration_path = _load_binding(
        authority, value["calibration_result"], "final freeze calibration result"
    )
    expected = build_final_freeze(
        experiment_dir=experiment_dir,
        authority_root=authority,
        pre_freeze_path=pre_path,
        calibration_result_path=calibration_path,
        created_at=value["created_at"],
    )
    if value != expected:
        raise PilotFreezeError("final pilot freeze drifted from calibration evidence or static inputs")
    return value


def validate_grant_authority(
    grant_path: Path,
    authority_freeze_path: Path,
    *,
    expected_role: str,
    experiment_dir: Path = HERE,
) -> dict[str, Any]:
    root = experiment_dir.resolve()
    canonical_grant_path = grant_path.resolve()
    if canonical_grant_path.name != "grant.json":
        raise PilotFreezeError("pilot authority requires the canonical execution-root grant.json")
    grant = guard.load_grant(canonical_grant_path)
    if grant["execution_root_sha256"] != guard._root_path_sha256(canonical_grant_path.parent):
        raise PilotFreezeError("pilot grant belongs to another execution root")
    if grant["role"] != expected_role:
        raise PilotFreezeError(f"expected a {expected_role} grant")
    if expected_role == "calibration":
        authority = validate_pre_calibration_freeze(authority_freeze_path, experiment_dir=experiment_dir)
        expected_phase = "pre-calibration"
    elif expected_role in {"producer", "reviewer"}:
        authority = validate_final_freeze(authority_freeze_path, experiment_dir=experiment_dir)
        expected_phase = "final-pilot"
    else:
        raise PilotFreezeError(f"unsupported pilot grant role: {expected_role}")
    if authority["phase"] != expected_phase:
        raise PilotFreezeError(f"{expected_role} grant is bound to the wrong freeze phase")
    if grant["authority_evidence_sha256"] != sha256_file(authority_freeze_path):
        raise PilotFreezeError(f"{expected_role} grant authority evidence hash drifted")
    preregistration = _load_json(root / "pilot-preregistration.json", "pilot preregistration")
    try:
        execution_boundary.require_execution_ready(preregistration, root)
    except execution_boundary.ExecutionBoundaryError as exc:
        raise PilotFreezeError(f"Pilot execution boundary is not ready: {exc}") from exc
    return grant


def _write_new(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_bytes(value)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    except FileExistsError as exc:
        raise PilotFreezeError(f"immutable freeze already exists: {path}") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--experiment-dir", type=Path, default=HERE)
    commands = value.add_subparsers(dest="command", required=True)
    pre = commands.add_parser("pre-calibration")
    pre.add_argument("--output", type=Path, required=True)
    check_pre = commands.add_parser("check-pre-calibration")
    check_pre.add_argument("--freeze", type=Path, required=True)
    final = commands.add_parser("final")
    final.add_argument("--pre-freeze", type=Path, required=True)
    final.add_argument("--calibration-result", type=Path, required=True)
    final.add_argument("--output", type=Path, required=True)
    check_final = commands.add_parser("check-final")
    check_final.add_argument("--freeze", type=Path, required=True)
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "pre-calibration":
            _write_new(args.output, build_pre_calibration_freeze(args.experiment_dir))
        elif args.command == "check-pre-calibration":
            validate_pre_calibration_freeze(args.freeze, experiment_dir=args.experiment_dir)
        elif args.command == "final":
            _write_new(
                args.output,
                build_final_freeze(
                    experiment_dir=args.experiment_dir,
                    authority_root=args.output.resolve().parent,
                    pre_freeze_path=args.pre_freeze,
                    calibration_result_path=args.calibration_result,
                ),
            )
        else:
            validate_final_freeze(args.freeze, experiment_dir=args.experiment_dir)
        return 0
    except (PilotFreezeError, guard.GuardError) as exc:
        print(f"pilot freeze error: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
