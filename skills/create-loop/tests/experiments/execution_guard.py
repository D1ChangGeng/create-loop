#!/usr/bin/env python3
"""Immutable authorization, evidence-first settlement, and budget replay.

The guard never launches a model.  It reserves one authorized ``run/episode``
call, stores an immutable evidence manifest and provider usage receipt, and only
then appends a settlement record.  Trace/report files are deliberately outside
the authority chain and may be rebuilt from these durable facts.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import time
import uuid
import weakref
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator, Mapping

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "scripts"))
SCHEMAS = {
    "grant": HERE / "authorization-grant.schema.json",
    "record": HERE / "execution-ledger-record.schema.json",
    "receipt": HERE / "usage-receipt.schema.json",
    "summary": HERE / "spend-summary.schema.json",
    "evidence": HERE / "evidence-manifest.schema.json",
    "interruption_evidence": HERE / "interruption-evidence-manifest.schema.json",
    "interruption": HERE / "controller-interruption.schema.json",
}
ZERO = {"calls": 0, "total_tokens": 0, "wall_seconds": Decimal("0")}
DEFAULT_EPISODE_ID = "episode-01"
MAX_REPLAY_CLOCK_SKEW_SECONDS = 5
INTERRUPTION_TERMINATION = "controller-kill-after-reality-before-post"
INTERRUPTION_REASON = "preregistered-s1-effect-reality-boundary"
INTERRUPTION_EVIDENCE_FIELDS = (
    "partial_provider_events",
    "stderr",
    "initial_workspace_manifest",
    "final_workspace_manifest",
    "reality_observation",
    "post_absence_observation",
    "termination_fact",
)
INTERRUPTION_EVIDENCE_ROLE_MAP = (
    ("provider_events", "partial_provider_events"),
    ("stderr", "stderr"),
    ("initial_workspace", "initial_workspace_manifest"),
    ("final_workspace", "final_workspace_manifest"),
    ("reality_observation", "reality_observation"),
    ("post_absence_observation", "post_absence_observation"),
    ("termination_fact", "termination_fact"),
)


class GuardError(RuntimeError):
    """The execution envelope is invalid or unsafe to advance."""


# Cached replay results are keyed by the canonical root and a fingerprint of
# every schema and immutable authority file. Each replay still reads and hashes
# the complete surface before a result may be reused.
_REPLAY_CACHE: dict[str, tuple[tuple[Any, ...], dict[str, Any]]] = {}
_STRICT_JSON_CACHE: dict[tuple[str, str], Any] = {}
_VALIDATED_JSON_CACHE: set[tuple[str, str, str, str]] = set()
_REPLAY_SNAPSHOT_RECORDS: weakref.WeakKeyDictionary[
    ReplaySnapshot, tuple[str, tuple[Any, ...], bytes]
] = weakref.WeakKeyDictionary()


class ReplaySnapshot:
    """Process-local proof of one stable, fully replayed authority surface."""

    __slots__ = ("__weakref__",)

    def __new__(cls) -> ReplaySnapshot:
        raise TypeError("ReplaySnapshot values are issued by replay_snapshot()")


def _snapshot_record(snapshot: ReplaySnapshot) -> tuple[str, tuple[Any, ...], bytes]:
    if type(snapshot) is not ReplaySnapshot:
        raise GuardError("invalid execution replay snapshot")
    record = _REPLAY_SNAPSHOT_RECORDS.get(snapshot)
    if record is None:
        raise GuardError("invalid execution replay snapshot")
    return record


def canonical_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise GuardError(f"value is not canonical JSON: {exc}") from exc


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_fingerprint(path: Path) -> tuple[str, str]:
    return path.resolve().as_posix(), sha256_file(path)


def _store_fingerprint(
    path: Path,
    label: str,
    *,
    allow_directories: bool = False,
) -> tuple[Any, ...]:
    resolved = _require_confined_directory(path.parent, path, label)
    entries: list[tuple[Any, ...]] = []
    for entry in sorted(resolved.iterdir(), key=lambda value: value.name):
        if allow_directories and entry.is_dir() and not entry.is_symlink():
            files: list[tuple[str, str]] = []
            for child in sorted(entry.rglob("*")):
                if child.is_dir() and not child.is_symlink():
                    continue
                if not child.is_file() or child.is_symlink():
                    raise GuardError(f"{label} contains unexpected entries")
                files.append((child.relative_to(entry).as_posix(), sha256_file(child)))
            entries.append((entry.name, tuple(files)))
            continue
        if not entry.is_file() or entry.is_symlink() or entry.suffix != ".json":
            raise GuardError(f"{label} contains unexpected entries")
        digest = sha256_file(entry)
        entries.append((entry.name, digest))
    return tuple(entries)


def _load_strict_json_with_digest(path: Path) -> tuple[Any, str]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant {value!r}")

    try:
        raw = path.read_bytes()
        digest = sha256_bytes(raw)
        key = (path.resolve().as_posix(), digest)
        cached = _STRICT_JSON_CACHE.get(key)
        if cached is None:
            cached = json.loads(raw.decode("utf-8"), parse_constant=reject_constant)
            _STRICT_JSON_CACHE[key] = cached
        return copy.deepcopy(cached), digest
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise GuardError(f"cannot read JSON {path}: {exc}") from exc


def _load_strict_json(path: Path) -> Any:
    return _load_strict_json_with_digest(path)[0]


def _load_validated_json(path: Path, schema_name: str) -> Any:
    value, digest = _load_strict_json_with_digest(path)
    schema_digest = sha256_file(SCHEMAS[schema_name])
    key = (path.resolve().as_posix(), digest, schema_name, schema_digest)
    if key not in _VALIDATED_JSON_CACHE:
        _validate_shape(value, schema_name)
        _VALIDATED_JSON_CACHE.add(key)
    return value


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_immutable(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise GuardError(f"immutable file already exists: {path}") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(path.parent)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _write_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(canonical_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _parse_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise GuardError(f"{label} must be RFC 3339")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GuardError(f"{label} must be RFC 3339") from exc
    if parsed.utcoffset() is None:
        raise GuardError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _now_text(now: datetime | None = None) -> str:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return current.isoformat(timespec="microseconds").replace("+00:00", "Z")


def validate_replay_time(now: datetime | None) -> datetime:
    """Return an aware replay time that is not materially ahead of this host."""

    current = datetime.now(timezone.utc)
    if now is None:
        return current
    if now.utcoffset() is None:
        raise GuardError("replay time must include a timezone")
    replayed_at = now.astimezone(timezone.utc)
    if replayed_at > current + timedelta(seconds=MAX_REPLAY_CLOCK_SKEW_SECONDS):
        raise GuardError("replay time is unreasonably far in the future")
    return replayed_at


def _decimal(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise GuardError(f"{label} must be numeric")
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise GuardError(f"{label} must be numeric") from exc
    if not amount.is_finite() or amount < 0:
        raise GuardError(f"{label} must be finite and non-negative")
    return amount


def _number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


def _max_totals(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return {field: max(left[field], right[field]) for field in left}


def _root_path_sha256(root: Path) -> str:
    resolved = str(root.resolve())
    if os.name == "nt":
        resolved = resolved.casefold()
    return sha256_bytes(resolved.encode("utf-8"))


def _totals(*, calls: int, tokens: int, seconds: Decimal) -> dict[str, Any]:
    return {"calls": calls, "total_tokens": tokens, "wall_seconds": _number(seconds)}


def _internal_totals(value: dict[str, Any], label: str) -> dict[str, Any]:
    if set(value) != {"calls", "total_tokens", "wall_seconds"}:
        raise GuardError(f"{label} has the wrong fields")
    calls = value["calls"]
    tokens = value["total_tokens"]
    if isinstance(calls, bool) or not isinstance(calls, int) or calls < 0:
        raise GuardError(f"{label}.calls must be a non-negative integer")
    if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0:
        raise GuardError(f"{label}.total_tokens must be a non-negative integer")
    return {
        "calls": calls,
        "total_tokens": tokens,
        "wall_seconds": _decimal(value["wall_seconds"], f"{label}.wall_seconds"),
    }


def _sum_totals(values: list[dict[str, Any]]) -> dict[str, Any]:
    total = dict(ZERO)
    for value in values:
        total["calls"] += value["calls"]
        total["total_tokens"] += value["total_tokens"]
        total["wall_seconds"] += value["wall_seconds"]
    return total


def _add_totals(total: dict[str, Any], value: dict[str, Any]) -> None:
    """Add one validated totals value to an accumulator in place."""
    total["calls"] += value["calls"]
    total["total_tokens"] += value["total_tokens"]
    total["wall_seconds"] += value["wall_seconds"]


def _subtract_totals(total: dict[str, Any], value: dict[str, Any]) -> None:
    """Remove one value previously added to an accumulator."""
    total["calls"] -= value["calls"]
    total["total_tokens"] -= value["total_tokens"]
    total["wall_seconds"] -= value["wall_seconds"]


def _public_totals(value: dict[str, Any]) -> dict[str, Any]:
    return _totals(
        calls=value["calls"],
        tokens=value["total_tokens"],
        seconds=value["wall_seconds"],
    )


def _validate_shape(instance: Any, schema_name: str) -> None:
    from schema_runtime import SchemaError, validate_schema_file

    try:
        errors = validate_schema_file(instance, SCHEMAS[schema_name])
    except SchemaError as exc:
        raise GuardError(f"{schema_name} schema is unsupported: {exc}") from exc
    if errors:
        raise GuardError(f"{schema_name} schema validation failed: {'; '.join(errors)}")


def _call_key(run_id: str, episode_id: str) -> tuple[str, str]:
    return run_id, episode_id


def _call_id(run_id: str, episode_id: str) -> str:
    return f"{run_id}:{episode_id}"


def _authorized_call_keys(grant: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        _call_key(item["run_id"], item["episode_id"])
        for item in grant["authorized_calls"]
    }


def load_grant(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise GuardError("authorization grant must be a regular non-symlink file")
    grant = _load_validated_json(path, "grant")
    if _parse_time(grant["expires_at"], "expires_at") <= _parse_time(
        grant["authorized_at"], "authorized_at"
    ):
        raise GuardError("authorization expiry must follow authorization time")
    calls = _authorized_call_keys(grant)
    if len(calls) != len(grant["authorized_calls"]):
        raise GuardError("authorized calls contain duplicate run/episode identities")
    per_call = grant["limits"]["per_call"]
    total = grant["limits"]["total"]
    if total["max_calls"] > len(calls):
        raise GuardError("total max_calls exceeds the authorized call set")
    for field in ("max_total_tokens", "max_wall_seconds"):
        if per_call[field] > total[field]:
            raise GuardError(f"per-call {field} exceeds the total limit")
    return grant


def _validate_grant_root(grant: dict[str, Any], root: Path) -> None:
    if grant["execution_root_sha256"] != _root_path_sha256(root):
        raise GuardError("authorization grant belongs to a different execution root")


def _root_paths(root: Path) -> tuple[Path, Path, Path, Path, Path]:
    return (
        root / "grant.json",
        root / "ledger",
        root / "receipts",
        root / "spend-summary.json",
        root / "ledger-anchor.json",
    )


def _replay_fingerprint(root: Path) -> tuple[Any, ...]:
    grant_path, ledger, receipts, _, anchor_path = _root_paths(root)
    evidences = _evidence_root(root)
    interruptions = _interruption_root(root)
    return (
        _root_path_sha256(root),
        tuple((name, sha256_file(path)) for name, path in sorted(SCHEMAS.items())),
        _file_fingerprint(grant_path),
        _file_fingerprint(anchor_path),
        _store_fingerprint(ledger, "ledger"),
        _store_fingerprint(receipts, "receipt root"),
        _store_fingerprint(evidences, "evidence root", allow_directories=True),
        _store_fingerprint(interruptions, "interruption root"),
    )


def _validate_snapshot_bindings(root: Path, expected_files: Mapping[str, str] | None) -> None:
    if expected_files is None:
        return
    for relative, expected_sha256 in sorted(expected_files.items()):
        if not isinstance(relative, str) or not isinstance(expected_sha256, str):
            raise GuardError("execution snapshot bindings must map relative paths to sha256 values")
        posix = PurePosixPath(relative)
        if posix.is_absolute() or ".." in posix.parts or "\\" in relative:
            raise GuardError("execution snapshot binding path must remain below the execution root")
        candidate = root.joinpath(*posix.parts)
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise GuardError("execution snapshot binding path escapes the execution root") from exc
        if (
            not candidate.is_file()
            or candidate.is_symlink()
            or resolved != candidate.absolute()
            or sha256_file(candidate) != expected_sha256
        ):
            raise GuardError(f"execution snapshot binding hash drifted: {relative}")


def _evidence_root(root: Path) -> Path:
    return root / "evidence"


def _interruption_root(root: Path) -> Path:
    return root / "interruptions"


def _require_confined_directory(root: Path, path: Path, label: str) -> Path:
    root_resolved = root.resolve()
    path_resolved = path.resolve()
    try:
        path_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise GuardError(f"{label} escapes the execution root") from exc
    if not path.is_dir() or path.is_symlink() or path_resolved != path.absolute():
        raise GuardError(f"{label} must be a real directory inside the execution root")
    return path_resolved


def _validate_receipt_binding(
    receipt: dict[str, Any],
    grant: dict[str, Any],
    run_id: str,
    attempt_id: str,
    episode_id: str | None = None,
) -> None:
    expected = {
        "authorization_id": grant["authorization_id"],
        "execution_id": grant["execution_id"],
        "run_id": run_id,
        "episode_id": episode_id or receipt["episode_id"],
        "attempt_id": attempt_id,
        "role": grant["role"],
        "adapter": grant["adapter"],
        "cli_identity": grant["cli_identity"],
        "provider_profile": grant["provider_profile"],
        "model": grant["model"],
        "reasoning_effort": grant["reasoning_effort"],
        "tool_profile": grant["tool_profile"],
    }
    for field, expected_value in expected.items():
        if receipt[field] != expected_value:
            raise GuardError(f"receipt {field} drifted from its reservation")
    if _call_key(receipt["run_id"], receipt["episode_id"]) not in _authorized_call_keys(grant):
        raise GuardError("receipt call is not authorized")
    usage = receipt["usage"]
    if usage["cached_input_tokens"] > usage["input_tokens"]:
        raise GuardError("cached input tokens exceed input tokens")
    if usage["reasoning_output_tokens"] > usage["output_tokens"]:
        raise GuardError("reasoning output tokens exceed output tokens")
    if usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"]:
        raise GuardError("receipt total_tokens disagrees with input plus output")
    started = _parse_time(receipt["started_at"], "receipt started_at")
    ended = _parse_time(receipt["ended_at"], "receipt ended_at")
    if ended < started:
        raise GuardError("receipt ended_at precedes started_at")
    elapsed = _decimal(receipt["usage"]["wall_seconds"], "receipt wall_seconds")
    wall = Decimal(str((ended - started).total_seconds()))
    if abs(elapsed - wall) > Decimal("1"):
        raise GuardError("receipt wall_seconds disagrees with its timestamps")


def _validate_receipt_store(
    root: Path,
    receipts: Path,
    grant: dict[str, Any],
    *,
    load_documents: bool = True,
) -> Path:
    resolved = _require_confined_directory(root, receipts, "receipt root")
    if not load_documents:
        return resolved
    receipt_ids: set[str] = set()
    provider_ids: set[str] = set()
    for entry in receipts.iterdir():
        if not entry.is_file() or entry.is_symlink() or entry.suffix != ".json":
            raise GuardError("receipt root contains unexpected entries")
        receipt = _load_validated_json(entry, "receipt")
        if entry.name != f"receipt-{sha256_bytes(canonical_bytes(receipt))}.json":
            raise GuardError("receipt root contains a non-canonical receipt file")
        _validate_receipt_binding(
            receipt,
            grant,
            receipt["run_id"],
            receipt["attempt_id"],
            receipt["episode_id"],
        )
        if receipt["receipt_id"] in receipt_ids:
            raise GuardError("receipt_id must be unique across receipt files")
        receipt_ids.add(receipt["receipt_id"])
        if provider_ids.intersection(receipt["provider_request_ids"]):
            raise GuardError("provider request IDs must be unique across receipt files")
        provider_ids.update(receipt["provider_request_ids"])
    return resolved


def _validate_evidence_store(
    root: Path,
    evidence_root: Path,
    *,
    load_documents: bool = True,
) -> Path:
    resolved = _require_confined_directory(root, evidence_root, "evidence root")
    if not load_documents:
        return resolved
    for entry in evidence_root.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            continue
        if not entry.is_file() or entry.is_symlink() or entry.suffix != ".json":
            raise GuardError("evidence root contains unexpected entries")
        evidence = _load_strict_json(entry)
        schema_name = (
            "interruption_evidence"
            if "controller_interruption" in evidence
            else "evidence"
        )
        evidence = _load_validated_json(entry, schema_name)
        if entry.name != f"evidence-{sha256_bytes(canonical_bytes(evidence))}.json":
            raise GuardError("evidence root contains a non-canonical manifest")
    return resolved


def _validate_interruption_store(
    root: Path,
    interruption_root: Path,
    grant: dict[str, Any] | None = None,
    *,
    load_documents: bool = True,
) -> Path:
    resolved = _require_confined_directory(root, interruption_root, "interruption root")
    if not load_documents:
        return resolved
    for entry in interruption_root.iterdir():
        if not entry.is_file() or entry.is_symlink() or entry.suffix != ".json":
            raise GuardError("interruption root contains unexpected entries")
        interruption = _load_validated_json(entry, "interruption")
        if entry.name != f"interruption-{sha256_bytes(canonical_bytes(interruption))}.json":
            raise GuardError("interruption root contains a non-canonical manifest")
        if grant is not None:
            _validate_preregistered_interruption(interruption, grant)
    return resolved


def canonical_interruption_evidence_bindings(
    interruption: dict[str, Any],
) -> list[dict[str, str]]:
    return [
        {"role": field, **interruption[field]}
        for field in INTERRUPTION_EVIDENCE_FIELDS
    ]


def _interruption_evidence_binding_map(
    evidence: dict[str, Any],
) -> dict[str, dict[str, str]]:
    by_role: dict[str, dict[str, str]] = {}
    for entry in evidence["files"]:
        role = entry["role"]
        if role in by_role:
            raise GuardError("interruption evidence roles must be unique")
        by_role[role] = entry
    return by_role


def _resolve_manifest_binding(
    base: Path,
    binding: dict[str, str],
    label: str,
) -> Path:
    relative = binding["path"]
    posix = PurePosixPath(relative)
    if posix.is_absolute() or ".." in posix.parts or "\\" in relative:
        raise GuardError(f"{label} path escapes the manifest directory")
    candidate = (base / Path(*posix.parts)).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise GuardError(f"{label} path escapes the manifest directory") from exc
    if not candidate.is_file() or candidate.is_symlink():
        raise GuardError(f"{label} file is missing or unsafe: {relative}")
    if sha256_file(candidate) != binding["sha256"]:
        raise GuardError(f"{label} file hash drifted: {relative}")
    return candidate


def _validate_interruption_files(path: Path, interruption: dict[str, Any]) -> None:
    base = path.parent.resolve()
    bindings = canonical_interruption_evidence_bindings(interruption)
    for binding in bindings:
        _resolve_manifest_binding(base, binding, "interruption")
    if interruption["controller_evidence_sha256"] != sha256_bytes(canonical_bytes(bindings)):
        raise GuardError("interruption controller evidence hash drifted")


def _validate_interruption_evidence_files(
    evidence_path: Path,
    evidence: dict[str, Any],
    interruption_path: Path,
    interruption: dict[str, Any],
    *,
    validate_files: bool = True,
) -> None:
    base = (evidence_path if evidence_path.is_dir() else evidence_path.parent).resolve()
    entries = evidence["files"]
    by_role = _interruption_evidence_binding_map(evidence)
    for entry in entries:
        if validate_files:
            _resolve_manifest_binding(base, entry, "interruption evidence")
    expected_roles = {
        "request", "provider_events", "stderr", "initial_workspace",
        "final_workspace", "workspace_population_seal", "protocol_bundle",
        "controller_interruption", "reality_observation",
        "post_absence_observation", "termination_fact",
    }
    if set(by_role) != expected_roles:
        raise GuardError("interruption evidence role set drifted")
    if evidence["aggregate_sha256"] != sha256_bytes(canonical_bytes(entries)):
        raise GuardError("interruption evidence aggregate hash drifted")
    for top_level, role in (
        ("initial_workspace_manifest", "initial_workspace"),
        ("final_workspace_manifest", "final_workspace"),
        ("workspace_population_seal", "workspace_population_seal"),
        ("controller_interruption", "controller_interruption"),
    ):
        if evidence[top_level] != {
            "path": by_role[role]["path"],
            "sha256": by_role[role]["sha256"],
        }:
            raise GuardError(f"interruption evidence {top_level} binding drifted")
    if by_role["controller_interruption"]["sha256"] != sha256_file(interruption_path):
        raise GuardError("interruption evidence does not bind the controller manifest")
    if evidence["controller_evidence_sha256"] != interruption["controller_evidence_sha256"]:
        raise GuardError("interruption evidence controller aggregate drifted")
    canonical = canonical_interruption_evidence_bindings(interruption)
    if evidence["controller_evidence_sha256"] != sha256_bytes(canonical_bytes(canonical)):
        raise GuardError("interruption controller evidence hash drifted")
    for evidence_role, interruption_role in INTERRUPTION_EVIDENCE_ROLE_MAP:
        if {
            "path": by_role[evidence_role]["path"],
            "sha256": by_role[evidence_role]["sha256"],
        } != interruption[interruption_role]:
            raise GuardError(f"interruption evidence {evidence_role} binding drifted")


def _validate_preregistered_interruption(
    interruption: dict[str, Any], grant: dict[str, Any]
) -> None:
    if (
        interruption["experiment_id"] != grant["experiment_id"]
        or interruption["case_id"] != "S1"
        or interruption["episode_id"] != "E01"
        or interruption["run_id"] not in {"PL-S1-P01-v1-E01", "PL-S1-P01-v2-E01"}
        or interruption["termination"] != INTERRUPTION_TERMINATION
        or interruption["reason"] != INTERRUPTION_REASON
    ):
        raise GuardError("interruption is not the preregistered S1/E01 controller kill")
    observed = _parse_time(interruption["controller"]["observed_at"], "controller observed_at")
    interrupted = _parse_time(interruption["interrupted_at"], "interrupted_at")
    if observed > interrupted:
        raise GuardError("controller observation follows the interruption timestamp")
    wall = _decimal(
        interruption["wall_seconds_upper_bound"]["seconds"],
        "wall_seconds_upper_bound.seconds",
    )
    limit = Decimal(grant["limits"]["per_call"]["max_wall_seconds"])
    if wall > limit:
        raise GuardError("interruption wall upper bound exceeds the reservation")


def _validate_evidence_files(path: Path, evidence: dict[str, Any]) -> None:
    base = (path if path.is_dir() else path.parent).resolve()
    bindings = list(evidence["files"]) + [
        {"path": evidence["initial_workspace_manifest"]["path"], "sha256": evidence["initial_workspace_manifest"]["sha256"]},
        {"path": evidence["final_workspace_manifest"]["path"], "sha256": evidence["final_workspace_manifest"]["sha256"]},
        {"path": evidence["structured_claim"]["path"], "sha256": evidence["structured_claim"]["sha256"]},
    ]
    if "workspace_population_seal" in evidence:
        bindings.append({
            "path": evidence["workspace_population_seal"]["path"],
            "sha256": evidence["workspace_population_seal"]["sha256"],
        })
    seen: dict[str, str] = {}
    for binding in bindings:
        relative = binding["path"]
        posix = PurePosixPath(relative)
        if posix.is_absolute() or ".." in posix.parts or "\\" in relative:
            raise GuardError("evidence file path escapes the manifest directory")
        candidate = (base / Path(*posix.parts)).resolve()
        try:
            candidate.relative_to(base)
        except ValueError as exc:
            raise GuardError("evidence file path escapes the manifest directory") from exc
        if not candidate.is_file() or candidate.is_symlink():
            raise GuardError(f"evidence file is missing or unsafe: {relative}")
        if sha256_file(candidate) != binding["sha256"]:
            raise GuardError(f"evidence file hash drifted: {relative}")
        prior = seen.setdefault(relative, binding["sha256"])
        if prior != binding["sha256"]:
            raise GuardError("evidence manifest binds one path to multiple hashes")
    if evidence["aggregate_sha256"] != sha256_bytes(canonical_bytes(evidence["files"])):
        raise GuardError("evidence aggregate does not match its ordered file bindings")


def _anchor_value(root: Path, records: list[Path], root_id: str) -> dict[str, Any]:
    return {
        "schema_version": "2.0",
        "root_id": root_id,
        "root_path_sha256": _root_path_sha256(root),
        "ledger_last_seq": len(records),
        "ledger_tail_sha256": sha256_file(records[-1]) if records else None,
    }


def _write_anchor(root: Path, records: list[Path], root_id: str) -> None:
    *_, anchor_path = _root_paths(root)
    _write_atomic(anchor_path, _anchor_value(root, records, root_id))


def _load_anchor(root: Path) -> dict[str, Any]:
    *_, anchor_path = _root_paths(root)
    if not anchor_path.is_file() or anchor_path.is_symlink():
        raise GuardError("execution root is missing its ledger anchor")
    anchor = _load_strict_json(anchor_path)
    expected = {
        "schema_version", "root_id", "root_path_sha256",
        "ledger_last_seq", "ledger_tail_sha256",
    }
    if set(anchor) != expected or anchor["schema_version"] != "2.0":
        raise GuardError("ledger anchor has the wrong fields or version")
    if anchor["root_path_sha256"] != _root_path_sha256(root):
        raise GuardError("ledger anchor belongs to a different execution root")
    if (
        isinstance(anchor["ledger_last_seq"], bool)
        or not isinstance(anchor["ledger_last_seq"], int)
        or anchor["ledger_last_seq"] < 1
    ):
        raise GuardError("ledger anchor sequence is invalid")
    if not isinstance(anchor["ledger_tail_sha256"], str):
        raise GuardError("ledger anchor tail hash is invalid")
    return anchor


@contextmanager
def execution_lock(root: Path, *, timeout_seconds: float = 5.0) -> Iterator[None]:
    lock = root / ".lock"
    root.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            lock.mkdir()
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise GuardError("execution root is locked")
            time.sleep(0.01)
    try:
        yield
    finally:
        try:
            lock.rmdir()
        except FileNotFoundError:
            pass


def _record_paths(ledger: Path) -> list[Path]:
    if not ledger.exists():
        return []
    paths = sorted(ledger.glob("*.json"))
    unexpected = [
        entry
        for entry in ledger.iterdir()
        if not entry.is_file() or entry.is_symlink() or entry.suffix != ".json"
    ]
    if unexpected:
        raise GuardError("ledger contains unexpected entries")
    return paths


def _append_record(
    root: Path,
    grant: dict[str, Any],
    kind: str,
    run_id: str | None,
    attempt_id: str | None,
    payload: dict[str, Any],
    *,
    episode_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    _, ledger, _, _, _ = _root_paths(root)
    _require_confined_directory(root, ledger, "ledger root")
    paths = _record_paths(ledger)
    seq = len(paths) + 1
    record_ts = _now_text(now)
    if paths:
        tail = _load_strict_json(paths[-1])
        if _parse_time(record_ts, "new record ts") < _parse_time(tail["ts"], "ledger tail ts"):
            raise GuardError("new ledger timestamp precedes the current tail")
    record = {
        "schema_version": "2.0",
        "seq": seq,
        "record_id": f"record-{seq:06d}-{uuid.uuid4().hex}",
        "previous_record_sha256": sha256_file(paths[-1]) if paths else None,
        "ts": record_ts,
        "kind": kind,
        "authorization_id": grant["authorization_id"],
        "execution_id": grant["execution_id"],
        "run_id": run_id,
        "episode_id": episode_id,
        "attempt_id": attempt_id,
        "payload": payload,
    }
    _validate_shape(record, "record")
    path = ledger / f"{seq:06d}-{record['record_id']}.json"
    _write_immutable(path, record)
    root_id = payload.get("root_id") if kind == "grant_registered" else _load_anchor(root)["root_id"]
    _write_anchor(root, paths + [path], root_id)
    return record


def initialize(root: Path, grant_path: Path, *, now: datetime | None = None) -> dict[str, Any]:
    grant = load_grant(grant_path)
    _validate_grant_root(grant, root)
    current = now or datetime.now(timezone.utc)
    if not _parse_time(grant["authorized_at"], "authorized_at") <= current.astimezone(
        timezone.utc
    ) <= _parse_time(grant["expires_at"], "expires_at"):
        raise GuardError("authorization is not currently valid")
    with execution_lock(root):
        grant_target, ledger, receipts, summary_path, anchor = _root_paths(root)
        evidences = _evidence_root(root)
        interruptions = _interruption_root(root)
        expected = canonical_bytes(grant)
        if grant_target.exists():
            if (
                not grant_target.is_file()
                or grant_target.is_symlink()
                or grant_target.read_bytes() != expected
            ):
                raise GuardError("initialized execution root contains a different grant")
        else:
            if any(path.exists() for path in (ledger, receipts, evidences, interruptions, summary_path, anchor)):
                raise GuardError("unpublished execution root contains unexpected state")
            grant_target.parent.mkdir(parents=True, exist_ok=True)
            _write_immutable(grant_target, grant)
        ledger.mkdir(exist_ok=True)
        receipts.mkdir(exist_ok=True)
        evidences.mkdir(exist_ok=True)
        interruptions.mkdir(exist_ok=True)
        _require_confined_directory(root, ledger, "ledger root")
        _validate_receipt_store(root, receipts, grant, load_documents=False)
        _validate_evidence_store(root, evidences, load_documents=False)
        _validate_interruption_store(root, interruptions, grant, load_documents=False)
        if not _record_paths(ledger):
            if (
                anchor.exists()
                or summary_path.exists()
                or any(receipts.iterdir())
                or any(evidences.iterdir())
                or any(interruptions.iterdir())
            ):
                raise GuardError("execution history is missing while durable control state remains")
            root_id = f"root-{uuid.uuid4().hex}"
            registration = {
                "grant_sha256": sha256_file(grant_target),
                "root_id": root_id,
                "root_path_sha256": _root_path_sha256(root),
            }
            _append_record(root, grant, "grant_registered", None, None, registration, now=current)
        return _replay_locked(root, write_summary=True, now=current)


def _load_records(root: Path, grant: dict[str, Any]) -> tuple[list[dict[str, Any]], list[Path]]:
    _, ledger, _, _, _ = _root_paths(root)
    _require_confined_directory(root, ledger, "ledger root")
    paths = _record_paths(ledger)
    records: list[dict[str, Any]] = []
    previous: str | None = None
    previous_ts: datetime | None = None
    record_ids: set[str] = set()
    for seq, path in enumerate(paths, start=1):
        record = _load_validated_json(path, "record")
        if path.name != f"{seq:06d}-{record['record_id']}.json" or record["seq"] != seq:
            raise GuardError("ledger sequence or filename is not canonical")
        if record["previous_record_sha256"] != previous:
            raise GuardError("ledger previous-record hash chain is broken")
        if record["record_id"] in record_ids:
            raise GuardError("ledger record_id must be unique")
        record_ids.add(record["record_id"])
        timestamp = _parse_time(record["ts"], f"record {seq} ts")
        if previous_ts is not None and timestamp < previous_ts:
            raise GuardError("ledger timestamps must be monotonic")
        previous_ts = timestamp
        if (
            record["authorization_id"] != grant["authorization_id"]
            or record["execution_id"] != grant["execution_id"]
        ):
            raise GuardError("ledger identity drifted from the grant")
        previous = sha256_file(path)
        records.append(record)
    anchor = _load_anchor(root)
    if (
        anchor["ledger_last_seq"] != len(paths)
        or anchor["ledger_tail_sha256"] != (sha256_file(paths[-1]) if paths else None)
    ):
        raise GuardError("ledger tail drifted from its durable anchor")
    if records:
        registration = records[0]["payload"]
        if (
            registration.get("root_id") != anchor["root_id"]
            or registration.get("root_path_sha256") != anchor["root_path_sha256"]
        ):
            raise GuardError("ledger registration drifted from its root anchor")
    return records, paths


def _reservation_from_grant(grant: dict[str, Any]) -> dict[str, Any]:
    limit = grant["limits"]["per_call"]
    return {
        "calls": 1,
        "total_tokens": limit["max_total_tokens"],
        "wall_seconds": Decimal(limit["max_wall_seconds"]),
    }


def _limits_from_grant(grant: dict[str, Any]) -> dict[str, Any]:
    limit = grant["limits"]["total"]
    return {
        "calls": limit["max_calls"],
        "total_tokens": limit["max_total_tokens"],
        "wall_seconds": Decimal(limit["max_wall_seconds"]),
    }


def _exceeds(value: dict[str, Any], limit: dict[str, Any]) -> bool:
    return any(value[field] > limit[field] for field in value)


def _receipt_actual(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "calls": 1,
        "total_tokens": receipt["usage"]["total_tokens"],
        "wall_seconds": _decimal(receipt["usage"]["wall_seconds"], "receipt wall_seconds"),
    }


def _stored_json_path(root: Path, relative: str, label: str) -> Path:
    posix = PurePosixPath(relative)
    if posix.is_absolute() or ".." in posix.parts or "\\" in relative:
        raise GuardError(f"{label} path escapes its store")
    path = (root / Path(*posix.parts)).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise GuardError(f"{label} path escapes its store") from exc
    if not path.is_file() or path.is_symlink():
        raise GuardError(f"{label} must be an immutable regular file")
    return path


def _store_json(path: Path, value: dict[str, Any], label: str) -> None:
    expected = canonical_bytes(value)
    if path.exists():
        if not path.is_file() or path.is_symlink() or path.read_bytes() != expected:
            raise GuardError(f"{label} hash already identifies different evidence")
        return
    _write_immutable(path, value)


def _copy_evidence_files_into_store(
    source_manifest_path: Path,
    stored_manifest_path: Path,
    evidence: dict[str, Any],
) -> None:
    source_base = source_manifest_path.parent.resolve()
    store_base = stored_manifest_path.parent.resolve()
    bindings: list[dict[str, str]] = list(evidence.get("files", []))
    for field in (
        "initial_workspace_manifest",
        "final_workspace_manifest",
        "workspace_population_seal",
        "structured_claim",
        "controller_interruption",
    ):
        binding = evidence.get(field)
        if isinstance(binding, dict):
            bindings.append(binding)
    unique: dict[str, dict[str, str]] = {}
    for binding in bindings:
        relative = binding.get("path")
        if isinstance(relative, str):
            prior = unique.setdefault(relative, binding)
            if prior.get("sha256") != binding.get("sha256"):
                raise GuardError("evidence manifest binds one path to multiple hashes")
    for relative, binding in unique.items():
        source = _resolve_manifest_binding(source_base, binding, "evidence")
        posix = PurePosixPath(relative)
        target = (store_base / stored_manifest_path.stem / Path(*posix.parts)).resolve()
        try:
            target.relative_to(store_base)
        except ValueError as exc:
            raise GuardError("stored evidence path escapes the evidence root") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not target.is_file() or target.is_symlink() or sha256_file(target) != binding["sha256"]:
                raise GuardError("stored evidence file already exists with different bytes")
            continue
        try:
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise GuardError("stored evidence file raced with another writer") from exc
        try:
            with os.fdopen(descriptor, "wb") as handle:
                with source.open("rb") as source_handle:
                    for chunk in iter(lambda: source_handle.read(1024 * 1024), b""):
                        handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            _fsync_directory(target.parent)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        if sha256_file(target) != binding["sha256"]:
            raise GuardError("stored evidence file hash drifted during copy")


def _replay_uncached(root: Path, *, write_summary: bool = False, now: datetime | None = None) -> dict[str, Any]:
    grant_path, _, receipts_root, summary_path, _ = _root_paths(root)
    evidences_root = _evidence_root(root)
    interruptions_root = _interruption_root(root)
    grant = load_grant(grant_path)
    _validate_grant_root(grant, root)
    records, paths = _load_records(root, grant)
    anchor = _load_anchor(root)
    replayed_at = validate_replay_time(now)
    tail_at = _parse_time(records[-1]["ts"], "ledger tail ts")
    if replayed_at.astimezone(timezone.utc) < tail_at:
        raise GuardError("generated_at cannot precede the ledger tail")
    registration = {
        "grant_sha256": sha256_file(grant_path),
        "root_id": anchor["root_id"],
        "root_path_sha256": anchor["root_path_sha256"],
    }
    if not records or records[0]["kind"] != "grant_registered" or records[0]["payload"] != registration:
        raise GuardError("ledger must begin with the exact grant registration")
    _validate_receipt_store(root, receipts_root, grant)
    _validate_evidence_store(root, evidences_root)
    _validate_interruption_store(root, interruptions_root, grant)

    open_attempts: dict[str, tuple[tuple[str, str], dict[str, Any]]] = {}
    seen_calls: set[tuple[str, str]] = set()
    seen_attempts: set[str] = set()
    settled_calls: set[tuple[str, str]] = set()
    interrupted_calls: set[tuple[str, str]] = set()
    interrupted_attempts: list[str] = []
    charged_totals = dict(ZERO)
    actual_totals = dict(ZERO)
    reserved_totals = dict(ZERO)
    receipt_ids: set[str] = set()
    request_ids: set[str] = set()
    breaches: list[str] = []
    declared_attempts: list[str] = []
    status = "active"
    closed_seen = False
    revoked_seen = False

    for record in records:
        kind = record["kind"]
        run_id = record["run_id"]
        episode_id = record["episode_id"]
        attempt_id = record["attempt_id"]
        payload = record["payload"]
        if kind == "grant_registered":
            if record["seq"] != 1 or any(item is not None for item in (run_id, episode_id, attempt_id)):
                raise GuardError("grant registration must be the first control record")
            continue
        if closed_seen:
            raise GuardError("no records may follow execution_closed")
        if kind == "call_reserved":
            if revoked_seen or breaches:
                raise GuardError("cannot reserve after revocation or budget breach")
            if run_id is None or episode_id is None or attempt_id is None:
                raise GuardError("call reservation identity is incomplete")
            call = _call_key(run_id, episode_id)
            if call not in _authorized_call_keys(grant):
                raise GuardError("reservation is outside the authorized call set")
            if call in seen_calls:
                raise GuardError("a run episode cannot be reserved more than once")
            if attempt_id in seen_attempts:
                raise GuardError("attempt_id must be unique")
            reservation = _internal_totals(payload.get("reservation", {}), "reservation")
            if reservation != _reservation_from_grant(grant):
                raise GuardError("reservation must consume the exact per-call maximum")
            proposed = _sum_totals([charged_totals, reserved_totals, reservation])
            if _internal_totals(payload.get("cumulative_after", {}), "cumulative_after") != proposed:
                raise GuardError("reservation cumulative_after is not replayable")
            if _exceeds(proposed, _limits_from_grant(grant)):
                raise GuardError("reservation exceeds the total authorization")
            open_attempts[attempt_id] = (call, reservation)
            _add_totals(reserved_totals, reservation)
            seen_calls.add(call)
            seen_attempts.add(attempt_id)
            continue
        if kind == "call_settled":
            if attempt_id not in open_attempts or run_id is None or episode_id is None:
                raise GuardError("settlement must match one open call reservation")
            call = _call_key(run_id, episode_id)
            if open_attempts[attempt_id][0] != call:
                raise GuardError("settlement call identity drifted from its reservation")
            receipt_path = _stored_json_path(receipts_root, payload.get("receipt_path", ""), "receipt")
            evidence_path = _stored_json_path(evidences_root, payload.get("evidence_path", ""), "evidence")
            if sha256_file(receipt_path) != payload.get("receipt_sha256"):
                raise GuardError("settlement receipt hash drifted")
            if sha256_file(evidence_path) != payload.get("evidence_sha256"):
                raise GuardError("settlement evidence hash drifted")
            receipt = _load_validated_json(receipt_path, "receipt")
            evidence = _load_validated_json(evidence_path, "evidence")
            stored_files = evidence_path.parent / evidence_path.stem
            if not stored_files.is_dir() or stored_files.is_symlink():
                raise GuardError("stored settlement evidence files are missing")
            _validate_evidence_files(stored_files, evidence)
            if receipt["evidence_manifest_sha256"] != sha256_file(evidence_path):
                raise GuardError("receipt does not bind the settlement evidence manifest")
            for field in ("run_id", "episode_id", "attempt_id", "role"):
                if evidence[field] != receipt[field]:
                    raise GuardError(f"evidence {field} drifted from receipt")
            if receipt["receipt_id"] in receipt_ids:
                raise GuardError("receipt_id must be unique across settlements")
            receipt_ids.add(receipt["receipt_id"])
            if request_ids.intersection(receipt["provider_request_ids"]):
                raise GuardError("provider request IDs must be unique across receipts")
            request_ids.update(receipt["provider_request_ids"])
            _validate_receipt_binding(receipt, grant, run_id, attempt_id, episode_id)
            actual = _receipt_actual(receipt)
            if _internal_totals(payload.get("actual", {}), "actual") != actual:
                raise GuardError("settlement actual values drifted from receipt")
            reservation = open_attempts.pop(attempt_id)[1]
            charged = _max_totals(reservation, actual)
            _subtract_totals(reserved_totals, reservation)
            _add_totals(actual_totals, actual)
            _add_totals(charged_totals, charged)
            settled_calls.add(call)
            declared_attempts.append(attempt_id)
            cumulative = _sum_totals([charged_totals, reserved_totals])
            if _internal_totals(payload.get("cumulative_after", {}), "cumulative_after") != cumulative:
                raise GuardError("settlement cumulative_after is not replayable")
            if _exceeds(actual, _reservation_from_grant(grant)) or _exceeds(
                cumulative, _limits_from_grant(grant)
            ):
                breaches.append(attempt_id)
            continue
        if kind == "call_interrupted":
            if attempt_id not in open_attempts or run_id is None or episode_id is None:
                raise GuardError("interruption must match one open call reservation")
            call = _call_key(run_id, episode_id)
            if open_attempts[attempt_id][0] != call:
                raise GuardError("interruption call identity drifted from its reservation")
            interruption_path = _stored_json_path(
                interruptions_root,
                payload.get("interruption_path", ""),
                "interruption",
            )
            if sha256_file(interruption_path) != payload.get("interruption_sha256"):
                raise GuardError("interruption manifest hash drifted")
            evidence_path = _stored_json_path(
                evidences_root,
                payload.get("interruption_evidence_path", ""),
                "interruption evidence",
            )
            if sha256_file(evidence_path) != payload.get("interruption_evidence_sha256"):
                raise GuardError("interruption evidence manifest hash drifted")
            interruption = _load_validated_json(interruption_path, "interruption")
            evidence = _load_validated_json(evidence_path, "interruption_evidence")
            stored_files = evidence_path.parent / evidence_path.stem
            stored_interruption_path = stored_files / "controller-interruption.json"
            if not stored_files.is_dir() or stored_files.is_symlink():
                raise GuardError("stored interruption evidence files are missing")
            stored_interruption = _load_validated_json(
                stored_interruption_path, "interruption"
            )
            if stored_interruption != interruption:
                raise GuardError("stored interruption evidence binds different controller bytes")
            _validate_preregistered_interruption(interruption, grant)
            _validate_interruption_evidence_files(
                stored_files,
                evidence,
                stored_interruption_path,
                interruption,
            )
            evidence_roles = _interruption_evidence_binding_map(evidence)
            if (
                PurePosixPath(evidence_roles["controller_interruption"]["path"]).name
                != "controller-interruption.json"
            ):
                raise GuardError("stored interruption evidence path drifted")
            for evidence_role, interruption_role in INTERRUPTION_EVIDENCE_ROLE_MAP:
                if (
                    PurePosixPath(evidence_roles[evidence_role]["path"]).name
                    != PurePosixPath(interruption[interruption_role]["path"]).name
                ):
                    raise GuardError(
                        f"stored interruption evidence {evidence_role} path drifted"
                    )
            if (
                interruption["authorization_id"] != grant["authorization_id"]
                or interruption["execution_id"] != grant["execution_id"]
                or interruption["run_id"] != run_id
                or interruption["episode_id"] != episode_id
                or interruption["attempt_id"] != attempt_id
                or interruption["role"] != grant["role"]
                or evidence["run_id"] != run_id
                or evidence["episode_id"] != episode_id
                or evidence["attempt_id"] != attempt_id
                or evidence["role"] != grant["role"]
            ):
                raise GuardError("interruption manifest identity drifted")
            if (
                payload.get("termination") != interruption["termination"]
                or payload.get("reason") != interruption["reason"]
                or payload.get("controller_evidence_sha256")
                != interruption["controller_evidence_sha256"]
                or payload.get("controller_evidence_sha256")
                != evidence["controller_evidence_sha256"]
                or payload.get("outcome") != "interrupted"
            ):
                raise GuardError("interruption ledger payload drifted from its manifest")
            reservation = open_attempts.pop(attempt_id)[1]
            if _internal_totals(payload.get("charged", {}), "charged") != reservation:
                raise GuardError("interruption must charge the exact reservation")
            _subtract_totals(reserved_totals, reservation)
            _add_totals(charged_totals, reservation)
            interrupted_calls.add(call)
            interrupted_attempts.append(attempt_id)
            declared_attempts.append(attempt_id)
            cumulative = _sum_totals([charged_totals, reserved_totals])
            if _internal_totals(payload.get("cumulative_after", {}), "cumulative_after") != cumulative:
                raise GuardError("interruption cumulative_after is not replayable")
            continue
        if kind == "grant_revoked":
            if any(item is not None for item in (run_id, episode_id, attempt_id)) or revoked_seen:
                raise GuardError("grant revocation is malformed or duplicated")
            if not isinstance(payload.get("reason"), str):
                raise GuardError("grant revocation requires a reason")
            revoked_seen = True
            status = "revoked"
            continue
        if kind == "execution_closed":
            if any(item is not None for item in (run_id, episode_id, attempt_id)) or open_attempts:
                raise GuardError("execution cannot close with an in-doubt reservation")
            if not isinstance(payload.get("reason"), str):
                raise GuardError("execution closure requires a reason")
            closed_seen = True
            status = "closed"
            continue
        raise GuardError(f"unsupported record kind {kind}")

    settled = dict(actual_totals)
    reserved = dict(reserved_totals)
    charged = _sum_totals([charged_totals, reserved_totals])
    limits = _limits_from_grant(grant)
    remaining = {
        "calls": max(limits["calls"] - charged["calls"], 0),
        "total_tokens": max(limits["total_tokens"] - charged["total_tokens"], 0),
        "wall_seconds": max(limits["wall_seconds"] - charged["wall_seconds"], Decimal("0")),
    }
    if closed_seen:
        status = "closed"
    elif breaches:
        status = "breached"
    elif revoked_seen:
        status = "revoked"
    summary = {
        "schema_version": "2.0",
        "authorization_id": grant["authorization_id"],
        "execution_id": grant["execution_id"],
        "root_id": anchor["root_id"],
        "root_path_sha256": anchor["root_path_sha256"],
        "grant_sha256": sha256_file(grant_path),
        "ledger_last_seq": len(records),
        "ledger_tail_sha256": sha256_file(paths[-1]),
        "status": status,
        "settled": _public_totals(settled),
        "reserved": _public_totals(reserved),
        "charged": _public_totals(charged),
        "remaining": _public_totals(remaining),
        "in_doubt_attempt_ids": sorted(open_attempts),
        "settled_call_ids": sorted(_call_id(*call) for call in settled_calls),
        "settled_run_ids": sorted({call[0] for call in settled_calls}),
        "interrupted_call_ids": sorted(_call_id(*call) for call in interrupted_calls),
        "interrupted_attempt_ids": sorted(interrupted_attempts),
        "breaches": sorted(set(breaches)),
        "declared_attempt_ids": sorted(declared_attempts),
        "generated_at": _now_text(replayed_at),
    }
    _validate_shape(summary, "summary")
    if write_summary:
        _write_atomic(summary_path, summary)
    return summary


def _replay_locked(
    root: Path,
    *,
    write_summary: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    replayed_at = validate_replay_time(now)
    fingerprint = _replay_fingerprint(root)
    ledger_paths = _record_paths(_root_paths(root)[1])
    if ledger_paths:
        tail = _load_strict_json(ledger_paths[-1])
        if replayed_at.astimezone(timezone.utc) < _parse_time(
            tail["ts"], "ledger tail ts"
        ):
            raise GuardError("generated_at cannot precede the ledger tail")
    cache_key = _root_path_sha256(root)
    cached = _REPLAY_CACHE.get(cache_key)
    if cached is not None and cached[0] == fingerprint:
        # The stores are immutable under normal operation, but replay is also a
        # public read API. Re-hash once more before returning so a concurrent
        # out-of-band mutation between fingerprinting and cache lookup cannot
        # authorize stale accounting.
        if _replay_fingerprint(root) != fingerprint:
            return _replay_uncached(root, write_summary=write_summary, now=replayed_at)
        summary = copy.deepcopy(cached[1])
        summary["generated_at"] = _now_text(replayed_at)
        _validate_shape(summary, "summary")
        if write_summary:
            _write_atomic(_root_paths(root)[3], summary)
        return summary
    summary = _replay_uncached(root, write_summary=write_summary, now=replayed_at)
    cached_summary = copy.deepcopy(summary)
    cached_summary.pop("generated_at", None)
    _REPLAY_CACHE[cache_key] = (fingerprint, cached_summary)
    return summary


def replay(root: Path, *, write_summary: bool = False, now: datetime | None = None) -> dict[str, Any]:
    if not write_summary:
        return _replay_locked(root, now=now)
    with execution_lock(root):
        return _replay_locked(root, write_summary=True, now=now)


def replay_snapshots(
    roots: Iterable[Path],
    *,
    expected_files: Iterable[Mapping[str, str] | None] | None = None,
    now: datetime | None = None,
) -> list[ReplaySnapshot]:
    """Take one stable replay cut while holding all execution roots locked."""

    resolved_roots = [root.resolve() for root in roots]
    bindings = (
        list(expected_files)
        if expected_files is not None
        else [None for _ in resolved_roots]
    )
    if len(bindings) != len(resolved_roots):
        raise GuardError("execution snapshot roots and bindings must have equal lengths")
    root_paths = [root.as_posix() for root in resolved_roots]
    if len(set(root_paths)) != len(root_paths):
        raise GuardError("execution snapshot roots must be unique")

    with ExitStack() as stack:
        for root in sorted(resolved_roots, key=lambda value: value.as_posix()):
            stack.enter_context(execution_lock(root))
        before: list[tuple[Any, ...]] = []
        for root, binding in zip(resolved_roots, bindings):
            _validate_snapshot_bindings(root, binding)
            before.append(_replay_fingerprint(root))
        summaries = [_replay_locked(root, now=now) for root in resolved_roots]
        after: list[tuple[Any, ...]] = []
        for root, binding in zip(resolved_roots, bindings):
            _validate_snapshot_bindings(root, binding)
            after.append(_replay_fingerprint(root))
        if before != after:
            raise GuardError("execution authority changed while taking replay snapshot")

        snapshots: list[ReplaySnapshot] = []
        for root, fingerprint, summary in zip(resolved_roots, after, summaries):
            snapshot = object.__new__(ReplaySnapshot)
            _REPLAY_SNAPSHOT_RECORDS[snapshot] = (
                root.as_posix(),
                fingerprint,
                canonical_bytes(summary),
            )
            snapshots.append(snapshot)
        return snapshots


def replay_snapshot(
    root: Path,
    *,
    expected_files: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> ReplaySnapshot:
    """Bind replay output to one stable snapshot of every authority byte."""

    return replay_snapshots(
        [root], expected_files=[expected_files], now=now
    )[0]


def summary_from_snapshot(root: Path, snapshot: ReplaySnapshot) -> dict[str, Any]:
    """Return an isolated summary only from a token issued by this process."""

    root_path, _, summary_bytes = _snapshot_record(snapshot)
    if root_path != root.resolve().as_posix():
        raise GuardError("execution replay snapshot belongs to a different root")
    try:
        return json.loads(summary_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GuardError("execution replay snapshot summary is invalid") from exc


def same_replay_authority(first: ReplaySnapshot, second: ReplaySnapshot) -> bool:
    """Compare exact authority bytes represented by two issued snapshots."""

    first_root, first_fingerprint, first_summary_bytes = _snapshot_record(first)
    second_root, second_fingerprint, second_summary_bytes = _snapshot_record(second)
    try:
        first_summary = json.loads(first_summary_bytes.decode("utf-8"))
        second_summary = json.loads(second_summary_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GuardError("execution replay snapshot summary is invalid") from exc
    first_summary.pop("generated_at", None)
    second_summary.pop("generated_at", None)
    return (
        first_root == second_root
        and first_fingerprint == second_fingerprint
        and canonical_bytes(first_summary) == canonical_bytes(second_summary)
    )


def reserve(
    root: Path,
    run_id: str,
    attempt_id: str,
    episode_id: str = DEFAULT_EPISODE_ID,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    with execution_lock(root):
        grant_path, _, _, _, _ = _root_paths(root)
        grant = load_grant(grant_path)
        _validate_grant_root(grant, root)
        if not _parse_time(grant["authorized_at"], "authorized_at") <= current.astimezone(
            timezone.utc
        ) <= _parse_time(grant["expires_at"], "expires_at"):
            raise GuardError("authorization is not valid at reservation time")
        summary = _replay_locked(root, now=current)
        if summary["status"] != "active":
            raise GuardError(f"execution is not active: {summary['status']}")
        call = _call_key(run_id, episode_id)
        if call not in _authorized_call_keys(grant):
            raise GuardError("run episode is not authorized")
        records, _ = _load_records(root, grant)
        if any(
            record["run_id"] == run_id and record["episode_id"] == episode_id
            for record in records
        ):
            raise GuardError("a run episode cannot be reserved more than once")
        if any(record["attempt_id"] == attempt_id for record in records):
            raise GuardError("attempt_id must be globally unique")
        reservation = _reservation_from_grant(grant)
        proposed = _sum_totals(
            [_internal_totals(summary["charged"], "charged"), reservation]
        )
        if _exceeds(proposed, _limits_from_grant(grant)):
            raise GuardError("reservation would exceed the total authorization")
        _append_record(
            root,
            grant,
            "call_reserved",
            run_id,
            attempt_id,
            {
                "reservation": _public_totals(reservation),
                "cumulative_after": _public_totals(proposed),
            },
            episode_id=episode_id,
            now=current,
        )
        return _replay_locked(root, write_summary=True, now=current)


def settle(
    root: Path,
    receipt_path: Path,
    evidence_path: Path | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    if not receipt_path.is_file() or receipt_path.is_symlink():
        raise GuardError("usage receipt must be a regular non-symlink file")
    evidence_path = evidence_path or receipt_path.with_name("evidence-manifest.json")
    if not evidence_path.is_file() or evidence_path.is_symlink():
        raise GuardError("settlement requires a pre-existing evidence manifest")
    receipt = _load_strict_json(receipt_path)
    evidence = _load_strict_json(evidence_path)
    _validate_shape(receipt, "receipt")
    _validate_shape(evidence, "evidence")
    _validate_evidence_files(evidence_path, evidence)
    if receipt_path.read_bytes() != canonical_bytes(receipt):
        raise GuardError("usage receipt must use canonical JSON bytes")
    if evidence_path.read_bytes() != canonical_bytes(evidence):
        raise GuardError("evidence manifest must use canonical JSON bytes")
    if receipt["evidence_manifest_sha256"] != sha256_file(evidence_path):
        raise GuardError("receipt does not bind the supplied evidence manifest")
    for field in ("run_id", "episode_id", "attempt_id", "role"):
        if evidence[field] != receipt[field]:
            raise GuardError(f"evidence {field} drifted from receipt")

    with execution_lock(root):
        grant_path, _, receipts_root, _, _ = _root_paths(root)
        evidences_root = _evidence_root(root)
        grant = load_grant(grant_path)
        _validate_grant_root(grant, root)
        summary = _replay_locked(root, now=current)
        if summary["status"] not in {"active", "revoked", "breached"}:
            raise GuardError(f"execution cannot settle in status {summary['status']}")
        attempt_id = receipt["attempt_id"]
        if attempt_id not in summary["in_doubt_attempt_ids"]:
            raise GuardError("receipt does not match an in-doubt reservation")
        _validate_receipt_binding(
            receipt,
            grant,
            receipt["run_id"],
            attempt_id,
            receipt["episode_id"],
        )
        records, _ = _load_records(root, grant)
        reservation_record = next(
            record
            for record in records
            if record["kind"] == "call_reserved" and record["attempt_id"] == attempt_id
        )
        if (
            reservation_record["run_id"] != receipt["run_id"]
            or reservation_record["episode_id"] != receipt["episode_id"]
        ):
            raise GuardError("receipt call does not match its reservation")
        reserved_at = _parse_time(reservation_record["ts"], "reservation ts")
        if _parse_time(receipt["started_at"], "receipt started_at") < reserved_at:
            raise GuardError("receipt started before its reservation")
        if _parse_time(receipt["ended_at"], "receipt ended_at") > current.astimezone(timezone.utc):
            raise GuardError("receipt ended after the settlement record time")

        used_receipt_ids: set[str] = set()
        used_request_ids: set[str] = set()
        charged_prior: list[dict[str, Any]] = []
        open_reservations: dict[str, dict[str, Any]] = {}
        for record in records:
            if record["kind"] == "call_reserved":
                open_reservations[record["attempt_id"]] = _internal_totals(
                    record["payload"]["reservation"], "reservation"
                )
            elif record["kind"] == "call_settled":
                prior_path = _stored_json_path(
                    receipts_root, record["payload"]["receipt_path"], "receipt"
                )
                prior = _load_strict_json(prior_path)
                used_receipt_ids.add(prior["receipt_id"])
                used_request_ids.update(prior["provider_request_ids"])
                reservation = open_reservations.pop(record["attempt_id"])
                charged_prior.append(
                    _max_totals(
                        reservation,
                        _internal_totals(record["payload"]["actual"], "actual"),
                    )
                )
        if receipt["receipt_id"] in used_receipt_ids:
            raise GuardError("receipt_id must be unique across settlements")
        if used_request_ids.intersection(receipt["provider_request_ids"]):
            raise GuardError("provider request IDs must be unique across receipts")

        actual = _receipt_actual(receipt)
        reservation = open_reservations.pop(attempt_id)
        cumulative = _sum_totals(
            charged_prior + [_max_totals(reservation, actual)] + list(open_reservations.values())
        )
        evidence_name = f"evidence-{sha256_bytes(canonical_bytes(evidence))}.json"
        stored_evidence = evidences_root / evidence_name
        _store_json(stored_evidence, evidence, "evidence manifest")
        _copy_evidence_files_into_store(evidence_path, stored_evidence, evidence)
        receipt_name = f"receipt-{sha256_bytes(canonical_bytes(receipt))}.json"
        stored_receipt = receipts_root / receipt_name
        _store_json(stored_receipt, receipt, "receipt")
        _append_record(
            root,
            grant,
            "call_settled",
            receipt["run_id"],
            attempt_id,
            {
                "receipt_path": receipt_name,
                "receipt_sha256": sha256_file(stored_receipt),
                "evidence_path": evidence_name,
                "evidence_sha256": sha256_file(stored_evidence),
                "actual": _public_totals(actual),
                "cumulative_after": _public_totals(cumulative),
                "outcome": "settled",
            },
            episode_id=receipt["episode_id"],
            now=current,
        )
        return _replay_locked(root, write_summary=True, now=current)


def interrupt(
    root: Path,
    interruption_path: Path,
    evidence_path: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    if not interruption_path.is_file() or interruption_path.is_symlink():
        raise GuardError("controller interruption manifest must be a regular non-symlink file")
    interruption = _load_strict_json(interruption_path)
    if not evidence_path.is_file() or evidence_path.is_symlink():
        raise GuardError("interruption requires a pre-existing evidence manifest")
    evidence = _load_strict_json(evidence_path)
    _validate_shape(interruption, "interruption")
    _validate_shape(evidence, "interruption_evidence")
    _validate_interruption_files(interruption_path, interruption)
    _validate_interruption_evidence_files(
        evidence_path, evidence, interruption_path, interruption
    )
    if interruption_path.read_bytes() != canonical_bytes(interruption):
        raise GuardError("controller interruption manifest must use canonical JSON bytes")
    if evidence_path.read_bytes() != canonical_bytes(evidence):
        raise GuardError("interruption evidence manifest must use canonical JSON bytes")

    with execution_lock(root):
        grant_path, _, _, _, _ = _root_paths(root)
        interruptions_root = _interruption_root(root)
        evidences_root = _evidence_root(root)
        grant = load_grant(grant_path)
        _validate_grant_root(grant, root)
        _validate_preregistered_interruption(interruption, grant)
        summary = _replay_locked(root, now=current)
        if summary["status"] not in {"active", "revoked", "breached"}:
            raise GuardError(f"execution cannot record interruption in status {summary['status']}")
        attempt_id = interruption["attempt_id"]
        if attempt_id not in summary["in_doubt_attempt_ids"]:
            raise GuardError("interruption does not match an in-doubt reservation")
        records, _ = _load_records(root, grant)
        reservation_record = next(
            record
            for record in records
            if record["kind"] == "call_reserved" and record["attempt_id"] == attempt_id
        )
        if (
            interruption["authorization_id"] != grant["authorization_id"]
            or interruption["execution_id"] != grant["execution_id"]
            or interruption["role"] != grant["role"]
            or interruption["run_id"] != reservation_record["run_id"]
            or interruption["episode_id"] != reservation_record["episode_id"]
            or evidence["run_id"] != interruption["run_id"]
            or evidence["episode_id"] != interruption["episode_id"]
            or evidence["attempt_id"] != interruption["attempt_id"]
            or evidence["role"] != interruption["role"]
        ):
            raise GuardError("interruption manifest does not match its reservation")
        if _parse_time(interruption["interrupted_at"], "interrupted_at") > current.astimezone(timezone.utc):
            raise GuardError("interruption occurred after its ledger record time")

        reservation = _internal_totals(reservation_record["payload"]["reservation"], "reservation")
        cumulative = _internal_totals(summary["charged"], "charged")
        name = f"interruption-{sha256_bytes(canonical_bytes(interruption))}.json"
        stored = interruptions_root / name
        _store_json(stored, interruption, "controller interruption manifest")
        evidence_name = f"evidence-{sha256_bytes(canonical_bytes(evidence))}.json"
        stored_evidence = evidences_root / evidence_name
        _store_json(stored_evidence, evidence, "interruption evidence manifest")
        _copy_evidence_files_into_store(evidence_path, stored_evidence, evidence)
        copied_interruption = stored_evidence.parent / stored_evidence.stem / "controller-interruption.json"
        if sha256_file(copied_interruption) != sha256_file(stored):
            raise GuardError("stored interruption evidence binds different controller bytes")
        _append_record(
            root,
            grant,
            "call_interrupted",
            interruption["run_id"],
            attempt_id,
            {
                "interruption_path": name,
                "interruption_sha256": sha256_file(stored),
                "interruption_evidence_path": evidence_name,
                "interruption_evidence_sha256": sha256_file(stored_evidence),
                "termination": interruption["termination"],
                "reason": interruption["reason"],
                "controller_evidence_sha256": interruption["controller_evidence_sha256"],
                "charged": _public_totals(reservation),
                "cumulative_after": _public_totals(cumulative),
                "outcome": "interrupted",
            },
            episode_id=interruption["episode_id"],
            now=current,
        )
        return _replay_locked(root, write_summary=True, now=current)


def revoke(root: Path, reason: str, *, now: datetime | None = None) -> dict[str, Any]:
    if not reason.strip():
        raise GuardError("revocation requires a reason")
    current = now or datetime.now(timezone.utc)
    with execution_lock(root):
        grant_path, _, _, _, _ = _root_paths(root)
        grant = load_grant(grant_path)
        _validate_grant_root(grant, root)
        summary = _replay_locked(root, now=current)
        if summary["status"] != "active":
            raise GuardError(f"execution cannot be revoked from {summary['status']}")
        _append_record(
            root, grant, "grant_revoked", None, None, {"reason": reason}, now=current
        )
        return _replay_locked(root, write_summary=True, now=current)


def close(root: Path, reason: str, *, now: datetime | None = None) -> dict[str, Any]:
    if not reason.strip():
        raise GuardError("closure requires a reason")
    current = now or datetime.now(timezone.utc)
    with execution_lock(root):
        grant_path, _, _, _, _ = _root_paths(root)
        grant = load_grant(grant_path)
        _validate_grant_root(grant, root)
        summary = _replay_locked(root, now=current)
        if summary["status"] not in {"active", "revoked", "breached"}:
            raise GuardError(f"execution cannot close from {summary['status']}")
        if summary["in_doubt_attempt_ids"]:
            raise GuardError("execution cannot close with in-doubt reservations")
        _append_record(
            root, grant, "execution_closed", None, None, {"reason": reason}, now=current
        )
        return _replay_locked(root, write_summary=True, now=current)


__all__ = [
    "GuardError", "ReplaySnapshot", "close", "execution_lock", "initialize", "interrupt",
    "load_grant", "replay", "replay_snapshot", "replay_snapshots", "reserve", "revoke",
    "same_replay_authority",
    "settle", "sha256_file", "summary_from_snapshot", "validate_replay_time",
]
