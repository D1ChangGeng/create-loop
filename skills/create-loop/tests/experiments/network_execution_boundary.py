#!/usr/bin/env python3
"""Fail-closed Pilot execution readiness checks for model-process egress.

The tool profile remains a workload declaration.  This module separately
requires frozen CLI identities and an authenticated OS-enforced network boundary
before any Pilot freeze, grant, ledger, credential, or process-launch path may
be considered executable.  Offline validation may call
``inspect_execution_blockers`` and report the returned stable blocker records.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from types import MappingProxyType
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from schema_runtime import SchemaError, check_schema, validate  # noqa: E402


BOUNDARY_SCHEMA = "network-execution-boundary.schema.json"
CLI_SCHEMA = "cli-identity.schema.json"
PROVIDER_SCHEMA = "provider-profile.schema.json"
REQUIRED_ROLES = ("calibration", "producer", "reviewer")
CLI_IDENTITY_ROLE = {
    "calibration": "producer",
    "producer": "producer",
    "reviewer": "reviewer",
}
# Production backends are added only with an implemented repository adapter and
# its reviewed SHA-256.  An empty registry deliberately keeps the live Pilot
# blocked on this machine. Tests may patch this immutable mapping with the hash
# of a real fake adapter script; a self-declared backend document alone is never
# sufficient.
TRUSTED_LAUNCH_BACKENDS: Mapping[str, str] = MappingProxyType({})
BLOCKER_ORDER = {
    "producer_cli_identity": 0,
    "reviewer_cli_identity": 1,
    "network_boundary": 2,
}


class ExecutionBoundaryError(RuntimeError):
    """The Pilot does not have a frozen, verifiable execution boundary."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path, label: str) -> Any:
    if not path.is_file() or path.is_symlink():
        raise ExecutionBoundaryError(f"{label} must be a regular non-symlink file")
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle, parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-standard JSON constant {value!r}")
            ))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise ExecutionBoundaryError(f"cannot read strict JSON {label}: {exc}") from exc


def _validate_schema(value: Any, schema_path: Path, label: str) -> None:
    schema = _load_json(schema_path, f"{label} schema")
    try:
        check_schema(schema)
        errors = validate(value, schema)
    except SchemaError as exc:
        raise ExecutionBoundaryError(f"{label} schema is unsupported: {exc}") from exc
    if errors:
        raise ExecutionBoundaryError(f"{label} schema validation failed: {'; '.join(errors)}")


def _confined_binding(
    root: Path,
    binding: Mapping[str, Any],
    label: str,
    *,
    require_id: bool = False,
) -> Path:
    fields = {"path", "sha256"} | ({"id"} if require_id else set())
    if not isinstance(binding, Mapping) or set(binding) != fields:
        raise ExecutionBoundaryError(f"{label} binding has the wrong fields")
    relative = binding.get("path")
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ExecutionBoundaryError(f"{label} path is invalid")
    posix = PurePosixPath(relative)
    if posix.is_absolute() or any(part in {"", ".", ".."} for part in posix.parts):
        raise ExecutionBoundaryError(f"{label} path is unsafe")
    resolved_root = root.resolve()
    path = resolved_root.joinpath(*posix.parts)
    try:
        path.resolve().relative_to(resolved_root)
    except ValueError as exc:
        raise ExecutionBoundaryError(f"{label} escapes the experiment root") from exc
    if not path.is_file() or path.is_symlink():
        raise ExecutionBoundaryError(f"{label} must be a regular non-symlink file")
    if _sha256_file(path) != binding.get("sha256"):
        raise ExecutionBoundaryError(f"{label} hash drifted")
    return path


def _executable_binding(binding: Mapping[str, Any], label: str) -> Path:
    if not isinstance(binding, Mapping) or set(binding) != {"path", "sha256"}:
        raise ExecutionBoundaryError(f"{label} binding has the wrong fields")
    raw = binding.get("path")
    if not isinstance(raw, str) or not raw or "\0" in raw:
        raise ExecutionBoundaryError(f"{label} path is invalid")
    path = Path(raw).resolve()
    if not path.is_file() or path.is_symlink():
        raise ExecutionBoundaryError(f"{label} must be a regular non-symlink file")
    if _sha256_file(path) != binding.get("sha256"):
        raise ExecutionBoundaryError(f"{label} hash drifted")
    return path


def _timestamp(value: str, label: str) -> datetime:
    if not isinstance(value, str):
        raise ExecutionBoundaryError(f"{label} must be an RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExecutionBoundaryError(f"{label} must be an RFC 3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise ExecutionBoundaryError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _validate_cli_identity(
    preregistration: Mapping[str, Any],
    root: Path,
    role: str,
) -> dict[str, Any]:
    identities = preregistration.get("cli_identities")
    if not isinstance(identities, Mapping):
        raise ExecutionBoundaryError("cli_identities is missing")
    if identities.get("calibration_reuses") != "producer":
        raise ExecutionBoundaryError("calibration must reuse the producer CLI identity")
    slot = identities.get(role)
    if not isinstance(slot, Mapping):
        raise ExecutionBoundaryError(f"{role} CLI slot is missing")
    status = slot.get("status")
    if status != "frozen":
        reason = slot.get("reason")
        suffix = f": {reason}" if isinstance(reason, str) and reason else ""
        raise ExecutionBoundaryError(f"{role} CLI identity is unresolved{suffix}")
    binding = slot.get("binding")
    path = _confined_binding(root, binding, f"{role} CLI identity", require_id=True)
    identity = _load_json(path, f"{role} CLI identity")
    _validate_schema(identity, root / CLI_SCHEMA, f"{role} CLI identity")
    expected_platform = "windows" if role == "producer" else "linux"
    actual_platform = identity.get("platform", "windows")
    if (
        identity.get("id") != binding.get("id")
        or identity.get("version") != slot.get("version")
        or actual_platform != expected_platform
        or slot.get("platform") != expected_platform
        or slot.get("arch") != "x86_64"
    ):
        raise ExecutionBoundaryError(f"{role} CLI identity document drifted")
    return {"binding": dict(binding), "path": path, "document": identity}


def _identity_role(role: str) -> str:
    try:
        return CLI_IDENTITY_ROLE[role]
    except KeyError as exc:
        raise ExecutionBoundaryError(f"unsupported network-bound role: {role}") from exc


def _cli_blocker(
    preregistration: Mapping[str, Any],
    root: Path,
    role: str,
) -> dict[str, str] | None:
    code = f"{role}_cli_identity"
    try:
        _validate_cli_identity(preregistration, root, role)
    except ExecutionBoundaryError as exc:
        detail = str(exc)
        state = "missing" if detail.endswith("is missing") else (
            "unresolved" if "unresolved" in detail else "invalid"
        )
        return {"code": code, "state": state, "detail": detail}
    return None


def _validate_boundary(
    preregistration: Mapping[str, Any],
    root: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    execution = preregistration.get("execution")
    if not isinstance(execution, Mapping):
        raise ExecutionBoundaryError("execution configuration is missing")
    slot = execution.get("network_boundary")
    if not isinstance(slot, Mapping):
        raise ExecutionBoundaryError("network execution boundary is missing")
    status = slot.get("status")
    if status != "frozen":
        reason = slot.get("reason")
        suffix = f": {reason}" if isinstance(reason, str) and reason else ""
        raise ExecutionBoundaryError(f"network execution boundary is unresolved{suffix}")
    if slot.get("reason") is not None:
        raise ExecutionBoundaryError("frozen network execution boundary must not carry a reason")
    binding = slot.get("binding")
    path = _confined_binding(root, binding, "network execution boundary", require_id=True)
    boundary = _load_json(path, "network execution boundary")
    _validate_schema(boundary, root / BOUNDARY_SCHEMA, "network execution boundary")
    if boundary.get("id") != binding.get("id"):
        raise ExecutionBoundaryError("network execution boundary ID drifted")
    if tuple(boundary.get("roles", ())) != REQUIRED_ROLES:
        raise ExecutionBoundaryError("network execution boundary must cover calibration, producer, and reviewer")

    provider_binding = preregistration.get("provider")
    provider_path = _confined_binding(root, provider_binding, "provider profile", require_id=True)
    provider = _load_json(provider_path, "provider profile")
    _validate_schema(provider, root / PROVIDER_SCHEMA, "provider profile")
    if provider.get("id") != provider_binding.get("id"):
        raise ExecutionBoundaryError("provider profile ID drifted")
    if boundary.get("provider_profile_sha256") != provider_binding.get("sha256"):
        raise ExecutionBoundaryError("network execution boundary binds a different provider profile")
    endpoint = boundary["allowed_endpoint"]
    parsed = urlsplit(provider.get("base_url", ""))
    if (
        parsed.scheme != endpoint["scheme"]
        or parsed.hostname != endpoint["host"]
        or (parsed.port or 443) != endpoint["port"]
        or (parsed.path.rstrip("/") or "/") != (endpoint["path_prefix"].rstrip("/") or "/")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ExecutionBoundaryError("network execution boundary endpoint differs from the frozen provider")

    enforcement = boundary["enforcement"]
    verification = boundary["verification"]
    trusted_adapter_sha256 = TRUSTED_LAUNCH_BACKENDS.get(enforcement["backend"])
    if trusted_adapter_sha256 is None:
        raise ExecutionBoundaryError("network execution backend is not implemented or trusted")
    _confined_binding(root, enforcement["backend_identity"], "network backend identity")
    launcher_path = _executable_binding(enforcement["launcher"], "network launcher")
    adapter_path = _confined_binding(root, enforcement["adapter"], "network launch adapter")
    if enforcement["adapter"]["sha256"] != trusted_adapter_sha256:
        raise ExecutionBoundaryError("network launch adapter is not the registered backend implementation")
    launch_arguments = enforcement["launch_arguments"]
    if launch_arguments.count("{command}") != 1 or launch_arguments[-1] != "{command}":
        raise ExecutionBoundaryError("network launch arguments must end with one exact command marker")
    if launch_arguments.count("{adapter}") != 1:
        raise ExecutionBoundaryError("network launch arguments must contain one exact adapter marker")
    if enforcement["session_id"] != verification["session_id"]:
        raise ExecutionBoundaryError("network launcher and probes belong to different sessions")
    if enforcement["launcher"]["sha256"] != verification["launcher_sha256"]:
        raise ExecutionBoundaryError("network probe launcher hash differs from the launch wrapper")
    if enforcement["adapter"]["sha256"] != verification["adapter_sha256"]:
        raise ExecutionBoundaryError("network probe adapter hash differs from the launch adapter")
    for field in ("policy_export", "provider_probe", "denied_probe"):
        _confined_binding(root, verification[field], f"network {field.replace('_', ' ')}")
    verified_at = _timestamp(verification["verified_at"], "network verification verified_at")
    valid_until = _timestamp(verification["valid_until"], "network verification valid_until")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if valid_until <= verified_at:
        raise ExecutionBoundaryError("network verification validity interval is invalid")
    if current >= valid_until:
        raise ExecutionBoundaryError("network execution boundary proof is expired")
    return {
        "binding": dict(binding),
        "path": path,
        "document": boundary,
        "provider": provider,
        "launch": {
            "backend": enforcement["backend"],
            "session_id": enforcement["session_id"],
            "launcher": str(launcher_path),
            "launcher_sha256": enforcement["launcher"]["sha256"],
            "adapter": str(adapter_path),
            "adapter_sha256": enforcement["adapter"]["sha256"],
            "arguments": list(launch_arguments),
        },
    }


def launch_prefix(validated: Mapping[str, Any], *, role: str) -> list[str]:
    """Return the verified host-outer wrapper for native Windows roles.

    The v1 boundary document has one host executable binding and one outer
    command marker.  That shape can protect the native Windows producer (and
    the calibration call that reuses it), but it cannot place a Linux enforcer
    inside WSL before the reviewer bubblewrap/Codex process tree.  Reviewer
    execution therefore remains fail-closed until a role/platform-specific
    launch contract is implemented.
    """
    if role not in REQUIRED_ROLES:
        raise ExecutionBoundaryError(f"unsupported network-bound role: {role}")
    if role == "reviewer":
        raise ExecutionBoundaryError(
            "network boundary v1 cannot compose the WSL reviewer launch; "
            "a guest-local role/platform contract is required"
        )
    launch = validated.get("launch")
    if not isinstance(launch, Mapping):
        raise ExecutionBoundaryError("validated execution boundary lacks a launch contract")
    launcher = launch.get("launcher")
    launcher_hash = launch.get("launcher_sha256")
    adapter = launch.get("adapter")
    adapter_hash = launch.get("adapter_sha256")
    arguments = launch.get("arguments")
    session_id = launch.get("session_id")
    if (
        not isinstance(launcher, str)
        or not isinstance(launcher_hash, str)
        or not isinstance(adapter, str)
        or not isinstance(adapter_hash, str)
        or not isinstance(arguments, list)
        or not isinstance(session_id, str)
        or not all(isinstance(item, str) and item for item in arguments)
    ):
        raise ExecutionBoundaryError("validated execution launch contract is malformed")
    path = Path(launcher)
    adapter_path = Path(adapter)
    if not path.is_file() or path.is_symlink() or _sha256_file(path) != launcher_hash:
        raise ExecutionBoundaryError("network launcher drifted after readiness validation")
    if (
        not adapter_path.is_file()
        or adapter_path.is_symlink()
        or _sha256_file(adapter_path) != adapter_hash
        or TRUSTED_LAUNCH_BACKENDS.get(str(launch.get("backend"))) != adapter_hash
    ):
        raise ExecutionBoundaryError("network launch adapter drifted after readiness validation")
    prefix: list[str] = [str(path)]
    for item in arguments:
        if item == "{command}":
            return prefix
        value = (
            item.replace("{role}", role)
            .replace("{session_id}", session_id)
            .replace("{adapter}", str(adapter_path))
        )
        if "{" in value or "}" in value:
            raise ExecutionBoundaryError("network launch arguments contain an unknown placeholder")
        prefix.append(value)
    raise ExecutionBoundaryError("validated execution launch contract lacks its command marker")


def _probe_script() -> str:
    return (
        "import socket,sys\n"
        "host=sys.argv[1]; expected=sys.argv[2]\n"
        "try:\n"
        "    with socket.create_connection((host,443),timeout=5): pass\n"
        "    connected=True\n"
        "except OSError:\n"
        "    connected=False\n"
        "sys.exit(0 if connected==(expected=='allowed') else 97)\n"
    )


def prove_live_boundary(
    validated: Mapping[str, Any], *, role: str, timeout_seconds: int = 15,
) -> None:
    """Run fresh allow/deny probes through the exact provider launch wrapper."""
    prefix = launch_prefix(validated, role=role)
    document = validated.get("document")
    if not isinstance(document, Mapping):
        raise ExecutionBoundaryError("validated execution boundary lacks its document")
    allowed_host = document["allowed_endpoint"]["host"]
    environment = {
        key: os.environ[key]
        for key in ("SYSTEMROOT", "WINDIR", "COMSPEC")
        if key in os.environ
    }
    for label, host, expected in (
        ("provider", allowed_host, "allowed"),
        ("arbitrary", "example.com", "denied"),
    ):
        try:
            completed = subprocess.run(
                [*prefix, sys.executable, "-c", _probe_script(), host, expected],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=environment,
                timeout=timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ExecutionBoundaryError(f"live {label} network probe could not run") from exc
        if completed.returncode != 0:
            raise ExecutionBoundaryError(f"live {label} network probe failed closed")


def inspect_execution_blockers(
    preregistration: Mapping[str, Any],
    root: Path,
    *,
    required_role: str | None = None,
) -> list[dict[str, str]]:
    """Return stable, machine-readable blockers without authorizing execution."""
    requested_roles = REQUIRED_ROLES if required_role is None else (required_role,)
    identity_roles = tuple(dict.fromkeys(_identity_role(role) for role in requested_roles))
    blockers: list[dict[str, str]] = []
    for role in identity_roles:
        blocker = _cli_blocker(preregistration, root, role)
        if blocker is not None:
            blockers.append(blocker)
    try:
        validated_boundary = _validate_boundary(preregistration, root)
        for role in requested_roles:
            launch_prefix(validated_boundary, role=role)
    except ExecutionBoundaryError as exc:
        detail = str(exc)
        state = "missing" if detail.endswith("is missing") else (
            "unresolved" if "unresolved" in detail else "invalid"
        )
        blockers.append({"code": "network_boundary", "state": state, "detail": detail})
    blockers.sort(key=lambda item: (BLOCKER_ORDER.get(item["code"], 99), item["code"], item["detail"]))
    return blockers


def require_execution_ready(
    preregistration: Mapping[str, Any],
    root: Path,
    *,
    required_role: str | None = None,
) -> dict[str, Any]:
    """Return validated authority for one role, or for the complete Pilot."""
    requested_roles = REQUIRED_ROLES if required_role is None else (required_role,)
    identity_roles = tuple(dict.fromkeys(_identity_role(role) for role in requested_roles))
    validated_cli: dict[str, dict[str, Any]] = {}
    identity_blockers: list[dict[str, str]] = []
    for role in identity_roles:
        try:
            validated_cli[role] = _validate_cli_identity(preregistration, root, role)
        except ExecutionBoundaryError as exc:
            detail = str(exc)
            state = "missing" if detail.endswith("is missing") else (
                "unresolved" if "unresolved" in detail else "invalid"
            )
            identity_blockers.append({
                "code": f"{role}_cli_identity", "state": state, "detail": detail,
            })
    identity_blockers.sort(
        key=lambda item: (BLOCKER_ORDER.get(item["code"], 99), item["code"], item["detail"])
    )
    if identity_blockers:
        summary = ", ".join(
            f"{item['code']}:{item['state']}" for item in identity_blockers
        )
        raise ExecutionBoundaryError(f"Pilot execution is blocked ({summary})")

    try:
        validated_boundary = _validate_boundary(preregistration, root)
        for role in requested_roles:
            launch_prefix(validated_boundary, role=role)
    except ExecutionBoundaryError as exc:
        detail = str(exc)
        state = "missing" if detail.endswith("is missing") else (
            "unresolved" if "unresolved" in detail else "invalid"
        )
        raise ExecutionBoundaryError(
            f"Pilot execution is blocked (network_boundary:{state})"
        ) from exc
    return {**validated_boundary, "cli_identities": validated_cli}


__all__ = [
    "ExecutionBoundaryError",
    "inspect_execution_blockers",
    "launch_prefix",
    "prove_live_boundary",
    "require_execution_ready",
]
