#!/usr/bin/env python3
"""Build and validate deterministic Phase 5 source and instrument snapshots."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping


HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from project_loop import ProjectionError, canonical_output_path  # noqa: E402
from schema_runtime import SchemaError, validate  # noqa: E402


SOURCE_SCHEMA = HERE / "source-snapshot.schema.json"
INSTRUMENT_SCHEMA = HERE / "instrument-manifest.schema.json"
SUBJECT_INCLUDE = (
    "AGENTS.md",
    "README.md",
    "SKILL.md",
    "examples",
    "references",
    "schemas",
    "scripts",
    "templates",
)
CACHE_EXCLUDE = ("**/__pycache__/**", "**/*.pyc")
ORIGIN_KINDS = {"git-commit", "dirty-worktree"}
ROLE_NAMES = {
    "source",
    "harness",
    "adapter",
    "schema",
    "scenario",
    "fixture",
    "evaluation",
    "tool-profile",
    "enforcement",
}
REQUIRED_INSTRUMENT_ROLES = set(ROLE_NAMES)
EXPERIMENT_INSTRUMENT_INPUTS = {
    "authorization-grant.schema.json": "schema",
    "baseline-source.json": "source",
    "blind-review-manifest.schema.json": "schema",
    "blind-review-result.schema.json": "schema",
    "candidate-source.json": "source",
    "cli-identities/codex-0.144.1-windows.json": "tool-profile",
    "cli-identity.schema.json": "schema",
    "codex_exec_adapter.py": "adapter",
    "completion-claim.schema.json": "schema",
    "controller-interruption.schema.json": "schema",
    "deterministic-authoritative-run.schema.json": "schema",
    "deterministic-case-result.schema.json": "schema",
    "deterministic-fixture-catalog.json": "fixture",
    "deterministic-fixture-catalog.schema.json": "schema",
    "deterministic_runner.py": "evaluation",
    "deterministic-suite-result.schema.json": "schema",
    "evaluation-input-manifest.schema.json": "schema",
    "evaluation-spec.json": "evaluation",
    "evaluation-spec.schema.json": "schema",
    "evaluation.py": "evaluation",
    "evidence-manifest.schema.json": "schema",
    "interruption-evidence-manifest.schema.json": "schema",
    "execution-ledger-record.schema.json": "schema",
    "execution_guard.py": "enforcement",
    "experiment_harness.py": "harness",
    "final-workspace-manifest.schema.json": "schema",
    "freeze_experiment.py": "harness",
    "instrument-manifest.schema.json": "schema",
    "initial-workspace-manifest.schema.json": "schema",
    "oracle-result.schema.json": "schema",
    "network-execution-boundary.schema.json": "schema",
    "network_execution_boundary.py": "enforcement",
    "pilot-blind-review-manifest.schema.json": "schema",
    "pilot-blind-review-result.schema.json": "schema",
    "pilot-calibration-result.schema.json": "schema",
    "pilot-campaign-evidence-manifest.schema.json": "schema",
    "pilot_campaign.py": "harness",
    "pilot-decoded-reviews.schema.json": "schema",
    "pilot-final-freeze.schema.json": "schema",
    "pilot-evaluation-input-manifest.schema.json": "schema",
    "pilot-evaluator-manifest.json": "evaluation",
    "pilot-evaluator-manifest.schema.json": "schema",
    "pilot-evaluator/S1/hidden_check.py": "evaluation",
    "pilot-evaluator/T2/hidden_test.mjs": "evaluation",
    "pilot-evaluator/T3/injected/client-runtime.ts": "evaluation",
    "pilot-evaluator/T3/integration-failure.test.mjs": "evaluation",
    "pilot-evaluator/T5/hidden_test.mjs": "evaluation",
    "pilot-evaluator/T5/injected/resume.ts": "evaluation",
    "pilot-evaluator/T7/hidden_check.py": "evaluation",
    "pilot-fixtures/CC0-1.0.txt": "fixture",
    "pilot-fixtures/N0/README.md": "fixture",
    "pilot-fixtures/N0/fixture.json": "fixture",
    "pilot-fixtures/S1/fixture.json": "fixture",
    "pilot-fixtures/T2/README.md": "fixture",
    "pilot-fixtures/T2/fixture.json": "fixture",
    "pilot-fixtures/T3/README.md": "fixture",
    "pilot-fixtures/T3/fixture.json": "fixture",
    "pilot-fixtures/T5/README.md": "fixture",
    "pilot-fixtures/T5/fixture.json": "fixture",
    "pilot-fixtures/T7/fixture.json": "fixture",
    "pilot_harness.py": "harness",
    "pilot-oracle-result.schema.json": "schema",
    "pilot-oracle-judgment.schema.json": "schema",
    "pilot-oracle-observation.schema.json": "schema",
    "pilot-preregistration.schema.json": "schema",
    "pilot-pre-calibration-freeze.schema.json": "schema",
    "pilot-presented-artifact.schema.json": "schema",
    "pilot-report.schema.json": "schema",
    "pilot-review-claim.schema.json": "schema",
    "pilot-review-seal.schema.json": "schema",
    "pilot_runners.py": "harness",
    "pilot_freeze.py": "enforcement",
    "reviewer-isolation-manifest.schema.json": "schema",
    "reviewer_isolation.py": "enforcement",
    "pilot-run-plan.schema.json": "schema",
    "pilot-scenarios.json": "scenario",
    "pilot-scenarios.schema.json": "schema",
    "pilot-workspace-manifest.schema.json": "schema",
    "workspace-population-seal.schema.json": "schema",
    "preregistration.schema.json": "schema",
    "presented-artifact.schema.json": "schema",
    "protocol-bundle-manifest.schema.json": "schema",
    "provider-profile.schema.json": "schema",
    "provider-profiles/custom-zeo-responses.json": "tool-profile",
    "report.schema.json": "schema",
    "scenarios.json": "scenario",
    "scenarios.schema.json": "schema",
    "snapshot_tools.py": "harness",
    "source-snapshot.schema.json": "schema",
    "spend-summary.schema.json": "schema",
    "tool-profile.schema.json": "schema",
    "tool-profiles/local-full-no-publish.json": "tool-profile",
    "trace.schema.json": "schema",
    "trace-source.schema.json": "schema",
    "usage-receipt.schema.json": "schema",
    "workspace-manifest.schema.json": "schema",
    "workspace_builder.py": "fixture",
    "tool-profiles/provider-workspace-no-publish.json": "tool-profile",
}
EXPERIMENT_NON_INSTRUMENT_FILES = {
    "baseline-source.tar",
    "instrument-manifest.json",
    "pilot-preregistration.json",
    "pilot-run-plan.json",
    "preregistration.json",
}
EXPERIMENT_NON_INSTRUMENT_PREFIXES = ("protocol-bundles/",)
SNAPSHOT_PATH = re.compile(r"^[A-Za-z0-9._/-]+$")


class SnapshotError(RuntimeError):
    """A deterministic snapshot invariant failed."""


def repository_instrument_input_paths(root: Path = HERE) -> set[str]:
    """Return every live experiment asset that must be frozen as an instrument input."""
    paths: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        relative = path.relative_to(root).as_posix()
        if relative in EXPERIMENT_NON_INSTRUMENT_FILES:
            continue
        if any(relative.startswith(prefix) for prefix in EXPERIMENT_NON_INSTRUMENT_PREFIXES):
            continue
        paths.add(relative)
    return paths


def validate_repository_instrument_input_set(root: Path = HERE) -> None:
    """Fail closed when a live experiment asset is absent from the canonical input map."""
    expected = set(EXPERIMENT_INSTRUMENT_INPUTS)
    actual = repository_instrument_input_paths(root)
    if actual == expected:
        return
    unclassified = sorted(actual - expected)
    missing = sorted(expected - actual)
    details: list[str] = []
    if unclassified:
        details.append("unclassified=" + ", ".join(unclassified))
    if missing:
        details.append("missing=" + ", ".join(missing))
    raise SnapshotError("repository instrument input exact set drifted: " + "; ".join(details))


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant {value!r}")


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle, parse_constant=_reject_json_constant)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"cannot read strict JSON {path}: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise SnapshotError(f"value is not strict canonical JSON: {exc}") from exc
    return (encoded + "\n").encode("utf-8")


def write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_json_atomic(path: Path, value: Any) -> None:
    write_bytes_atomic(path, canonical_bytes(value))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_schema(instance: Any, schema_path: Path, label: str) -> None:
    schema = load_json(schema_path)
    try:
        errors = validate(instance, schema)
    except SchemaError as exc:
        raise SnapshotError(f"{label} schema is unsupported: {exc}") from exc
    if errors:
        raise SnapshotError(f"{label} schema validation failed: {'; '.join(errors)}")


def _relative_path(value: str, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise SnapshotError(f"{label} must be a non-empty relative POSIX path")
    if SNAPSHOT_PATH.fullmatch(value) is None:
        raise SnapshotError(f"{label} contains unsupported path characters: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or value.startswith("/") or "\\" in value or ".." in path.parts or "." in path.parts:
        raise SnapshotError(f"{label} is unsafe: {value!r}")
    if any(not part for part in path.parts):
        raise SnapshotError(f"{label} is unsafe: {value!r}")
    try:
        canonical = canonical_output_path(value)
    except ProjectionError as exc:
        raise SnapshotError(f"{label} is not materializable: {value!r}") from exc
    if canonical != value:
        raise SnapshotError(f"{label} is not canonical POSIX form: {value!r}")
    return path


def _resolve_below(root: Path, relative: str, label: str) -> Path:
    posix = _relative_path(relative, label)
    resolved_root = root.resolve()
    candidate = resolved_root.joinpath(*posix.parts)
    try:
        candidate.resolve(strict=False).relative_to(resolved_root)
    except ValueError as exc:
        raise SnapshotError(f"{label} escapes {root}: {relative!r}") from exc
    return candidate


def _excluded(relative: PurePosixPath) -> bool:
    return "__pycache__" in relative.parts or relative.suffix == ".pyc"


def _entry(path: str, data: bytes, mode: str) -> dict[str, Any]:
    return {"path": path, "sha256": sha256_bytes(data), "size": len(data), "mode": mode}


def _validate_exact_paths(entries: list[dict[str, Any]], label: str) -> None:
    paths = [entry["path"] for entry in entries]
    for path in paths:
        _relative_path(path, f"{label} path")
    if paths != sorted(paths):
        raise SnapshotError(f"{label} file paths must be sorted")
    if len(paths) != len(set(paths)):
        raise SnapshotError(f"{label} contains duplicate file paths")
    identities: dict[str, str] = {}
    for path in paths:
        key = path.lower()
        if key in identities and identities[key] != path:
            raise SnapshotError(f"{label} contains Windows-colliding paths: {identities[key]!r}, {path!r}")
        identities[key] = path


def _aggregate(entries: list[dict[str, Any]]) -> str:
    return sha256_bytes(canonical_bytes(entries))


def _validate_origin(origin: Mapping[str, Any]) -> None:
    kind = origin.get("kind")
    if kind not in ORIGIN_KINDS:
        raise SnapshotError(f"unsupported origin kind: {kind!r}")
    exact_keys = {"kind", "commit"} if kind == "git-commit" else {"kind", "base_git_commit"}
    if set(origin) != exact_keys:
        raise SnapshotError(f"{kind} origin must contain exactly {sorted(exact_keys)}")
    commit = origin["commit" if kind == "git-commit" else "base_git_commit"]
    if not isinstance(commit, str) or len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        raise SnapshotError(f"{kind} origin requires a lowercase 40-character commit")


def _worktree_modes(repo_root: Path, skill_root: Path) -> dict[str, str]:
    resolved_repo = repo_root.resolve()
    resolved_skill = skill_root.resolve()
    try:
        skill_prefix = resolved_skill.relative_to(resolved_repo).as_posix()
    except ValueError as exc:
        raise SnapshotError("skill root must stay below repository root") from exc
    raw = _run_git(resolved_repo, "ls-files", "-s", "-z", "--", skill_prefix)
    modes: dict[str, str] = {}
    for record in (item for item in raw.split(b"\0") if item):
        try:
            metadata, encoded_path = record.split(b"\t", 1)
            mode, object_id, stage = metadata.decode("ascii").split(" ")
            full_path = PurePosixPath(encoded_path.decode("utf-8", errors="strict"))
            relative = full_path.relative_to(PurePosixPath(skill_prefix)).as_posix()
        except (UnicodeDecodeError, ValueError) as exc:
            raise SnapshotError("cannot parse git index modes for source snapshot") from exc
        if stage != "0" or len(object_id) != 40 or any(char not in "0123456789abcdef" for char in object_id):
            raise SnapshotError(f"unsupported git index entry for {relative!r}")
        normalized_mode = _git_mode(mode, relative)
        previous = modes.get(relative)
        if previous is not None and previous != normalized_mode:
            raise SnapshotError(f"git index contains conflicting entries for {relative!r}")
        modes[relative] = normalized_mode
    return modes


def _walk_worktree(root: Path, include: Iterable[str], *, tracked_modes: Mapping[str, str]) -> list[tuple[str, bytes, str]]:
    resolved_root = root.resolve()
    found: list[tuple[str, bytes, str]] = []
    for name in sorted(include):
        target = _resolve_below(resolved_root, name, "subject include")
        if target.is_symlink():
            raise SnapshotError(f"subject include is a symlink: {name}")
        if target.is_file():
            candidates = [target]
        elif target.is_dir():
            candidates = sorted(target.rglob("*"), key=lambda path: path.relative_to(resolved_root).as_posix())
        else:
            raise SnapshotError(f"subject include is missing: {name}")
        for path in candidates:
            relative = PurePosixPath(path.relative_to(resolved_root).as_posix())
            if _excluded(relative):
                continue
            if path.is_symlink():
                raise SnapshotError(f"subject source contains a symlink: {relative.as_posix()}")
            if path.is_dir():
                continue
            if not path.is_file():
                raise SnapshotError(f"subject source is not a regular file: {relative.as_posix()}")
            relative_name = relative.as_posix()
            mode = tracked_modes.get(relative_name, "0644")
            found.append((relative_name, path.read_bytes(), mode))
    return found


def build_worktree_snapshot(
    skill_root: Path,
    *,
    repo_root: Path,
    snapshot_id: str,
    protocol: str,
    base_git_commit: str,
    include: Iterable[str] = SUBJECT_INCLUDE,
) -> dict[str, Any]:
    include_list = list(include)
    if tuple(include_list) != SUBJECT_INCLUDE:
        raise SnapshotError("subject include set drifted")
    resolved_base = _resolve_commit(repo_root, "HEAD")
    if base_git_commit != resolved_base:
        raise SnapshotError("dirty-worktree base_git_commit must equal the repository HEAD")
    tracked_modes = _worktree_modes(repo_root, skill_root)
    entries = [
        _entry(path, data, mode)
        for path, data, mode in _walk_worktree(skill_root, include_list, tracked_modes=tracked_modes)
    ]
    _validate_exact_paths(entries, "source snapshot")
    result = {
        "schema_version": "1.0",
        "algorithm": "sha256-source-snapshot-v1",
        "snapshot_id": snapshot_id,
        "protocol": protocol,
        "root": ".",
        "include": include_list,
        "exclude": list(CACHE_EXCLUDE),
        "origin": {"kind": "dirty-worktree", "base_git_commit": base_git_commit},
        "files": entries,
        "aggregate_sha256": _aggregate(entries),
        "archive": None,
    }
    validate_source_snapshot(result, skill_root=skill_root, repo_root=repo_root)
    return result


def _run_git(repo_root: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            input=input_bytes,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise SnapshotError(f"cannot execute git: {exc}") from exc
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise SnapshotError(f"git {' '.join(args)} failed: {message}")
    return completed.stdout


def _resolve_commit(repo_root: Path, revision: str) -> str:
    commit = _run_git(repo_root, "rev-parse", "--verify", f"{revision}^{{commit}}").decode("ascii").strip()
    if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        raise SnapshotError(f"git returned an invalid commit for {revision!r}")
    return commit


def _git_mode(mode: str, path: str) -> str:
    if mode == "100644":
        return "0644"
    if mode == "100755":
        return "0755"
    if mode == "120000":
        raise SnapshotError(f"Git snapshot contains a symlink: {path}")
    raise SnapshotError(f"Git snapshot contains unsupported mode {mode} at {path}")


def _git_subject_files(repo_root: Path, commit: str, skill_rel: str, include: Iterable[str]) -> list[tuple[str, bytes, str]]:
    prefix = PurePosixPath(skill_rel)
    _relative_path(prefix.as_posix(), "skill_rel")
    raw = _run_git(repo_root, "ls-tree", "-r", "-z", commit, "--", *[f"{prefix.as_posix()}/{item}" for item in include])
    records = [record for record in raw.split(b"\0") if record]
    objects: list[tuple[str, str, str]] = []
    for record in records:
        try:
            metadata, encoded_path = record.split(b"\t", 1)
            mode, object_type, object_id = metadata.decode("ascii").split(" ")
            full_path = encoded_path.decode("utf-8", errors="strict")
            relative = PurePosixPath(full_path).relative_to(prefix)
        except (UnicodeDecodeError, ValueError) as exc:
            raise SnapshotError("cannot parse git tree entry for source snapshot") from exc
        if len(object_id) != 40 or any(char not in "0123456789abcdef" for char in object_id):
            raise SnapshotError(f"Git snapshot contains an invalid object ID at {relative.as_posix()}")
        if _excluded(relative):
            continue
        if object_type != "blob":
            raise SnapshotError(f"Git snapshot contains non-blob object at {relative.as_posix()}")
        objects.append((relative.as_posix(), object_id, _git_mode(mode, relative.as_posix())))
    paths = {path for path, _, _ in objects}
    for item in include:
        if not any(path == item or path.startswith(f"{item}/") for path in paths):
            raise SnapshotError(f"Git snapshot include is missing at {commit}: {item}")
    if not objects:
        raise SnapshotError(f"Git snapshot has no subject files at {commit}")
    request = b"".join(f"{object_id}\n".encode("ascii") for _, object_id, _ in objects)
    response = _run_git(repo_root, "cat-file", "--batch", input_bytes=request)
    stream = io.BytesIO(response)
    found: list[tuple[str, bytes, str]] = []
    for path, object_id, mode in objects:
        try:
            header = stream.readline().decode("ascii").strip().split(" ")
        except UnicodeDecodeError as exc:
            raise SnapshotError(f"invalid git cat-file response for {path}") from exc
        if len(header) != 3 or header[0] != object_id or header[1] != "blob":
            raise SnapshotError(f"unexpected git cat-file response for {path}")
        try:
            size = int(header[2])
        except ValueError as exc:
            raise SnapshotError(f"invalid git blob size for {path}") from exc
        if size < 0:
            raise SnapshotError(f"invalid negative git blob size for {path}")
        data = stream.read(size)
        if len(data) != size or stream.read(1) != b"\n":
            raise SnapshotError(f"truncated git blob for {path}")
        found.append((path, data, mode))
    if stream.read(1) != b"":
        raise SnapshotError("git cat-file returned unexpected trailing data")
    return sorted(found, key=lambda item: item[0])


def _split_ustar_path(path: str) -> tuple[str, str]:
    encoded = path.encode("utf-8")
    if len(encoded) <= 100:
        return path, ""
    positions = [index for index, char in enumerate(path) if char == "/"]
    for index in reversed(positions):
        prefix, name = path[:index], path[index + 1:]
        if len(name.encode("utf-8")) <= 100 and len(prefix.encode("utf-8")) <= 155:
            return name, prefix
    raise SnapshotError(f"path cannot be represented by ustar: {path}")


def build_ustar_bytes(files: Iterable[tuple[str, bytes, str]]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for path, data, mode in sorted(files, key=lambda item: item[0]):
            _relative_path(path, "archive path")
            _split_ustar_path(path)
            info = tarfile.TarInfo(path)
            info.size = len(data)
            info.mode = int(mode, 8)
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.type = tarfile.REGTYPE
            archive.addfile(info, io.BytesIO(data))
    return output.getvalue()


def build_git_snapshot(
    repo_root: Path,
    *,
    revision: str,
    skill_rel: str,
    snapshot_id: str,
    protocol: str,
    include: Iterable[str] = SUBJECT_INCLUDE,
) -> tuple[dict[str, Any], bytes]:
    include_list = list(include)
    if tuple(include_list) != SUBJECT_INCLUDE:
        raise SnapshotError("subject include set drifted")
    commit = _resolve_commit(repo_root, revision)
    files = _git_subject_files(repo_root, commit, skill_rel, include_list)
    entries = [_entry(path, data, mode) for path, data, mode in files]
    _validate_exact_paths(entries, "source snapshot")
    archive = build_ustar_bytes(files)
    result = {
        "schema_version": "1.0",
        "algorithm": "sha256-source-snapshot-v1",
        "snapshot_id": snapshot_id,
        "protocol": protocol,
        "root": ".",
        "include": include_list,
        "exclude": list(CACHE_EXCLUDE),
        "origin": {"kind": "git-commit", "commit": commit},
        "files": entries,
        "aggregate_sha256": _aggregate(entries),
        "archive": {"format": "ustar-v1", "sha256": sha256_bytes(archive), "size": len(archive)},
    }
    validate_source_snapshot(result, archive_bytes=archive)
    return result, archive


def _read_archive(archive_bytes: bytes) -> list[tuple[str, bytes, str]]:
    found: list[tuple[str, bytes, str]] = []
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
            members = archive.getmembers()
            member_names = [member.name for member in members]
            if len(member_names) != len(set(member_names)):
                raise SnapshotError("archive contains duplicate member paths")
            for member in members:
                path = _relative_path(member.name, "archive member")
                if not member.isreg() or member.issym() or member.islnk():
                    raise SnapshotError(f"archive member is not a regular file: {member.name}")
                if member.uid != 0 or member.gid != 0 or member.uname or member.gname or member.mtime != 0:
                    raise SnapshotError(f"archive member metadata is not deterministic: {member.name}")
                if member.mode not in {0o644, 0o755}:
                    raise SnapshotError(f"archive member mode is unsupported: {member.name}")
                handle = archive.extractfile(member)
                if handle is None:
                    raise SnapshotError(f"cannot read archive member: {member.name}")
                data = handle.read()
                if len(data) != member.size:
                    raise SnapshotError(f"archive member size mismatch: {member.name}")
                found.append((path.as_posix(), data, f"{member.mode:04o}"))
    except (tarfile.TarError, OSError) as exc:
        raise SnapshotError(f"cannot read deterministic ustar archive: {exc}") from exc
    return sorted(found, key=lambda item: item[0])


def validate_source_snapshot(
    manifest: dict[str, Any],
    *,
    archive_bytes: bytes | None = None,
    skill_root: Path | None = None,
    repo_root: Path | None = None,
) -> None:
    validate_schema(manifest, SOURCE_SCHEMA, "source snapshot")
    if tuple(manifest["include"]) != SUBJECT_INCLUDE or tuple(manifest["exclude"]) != CACHE_EXCLUDE:
        raise SnapshotError("source snapshot include or exclude set drifted")
    _validate_origin(manifest["origin"])
    entries = manifest["files"]
    _validate_exact_paths(entries, "source snapshot")
    for entry in entries:
        if _excluded(PurePosixPath(entry["path"])):
            raise SnapshotError(f"source snapshot contains an excluded path: {entry['path']}")
    if manifest["aggregate_sha256"] != _aggregate(entries):
        raise SnapshotError("source snapshot aggregate hash mismatch")

    if skill_root is not None:
        if manifest["origin"]["kind"] != "dirty-worktree" or manifest["archive"] is not None:
            raise SnapshotError("worktree validation requires dirty-worktree origin and no archive")
        if repo_root is None:
            raise SnapshotError("worktree validation requires the repository root")
        resolved_base = _resolve_commit(repo_root, "HEAD")
        if manifest["origin"]["base_git_commit"] != resolved_base:
            raise SnapshotError("source snapshot base commit drifted from repository HEAD")
        tracked_modes = _worktree_modes(repo_root, skill_root)
        current = [
            _entry(path, data, mode)
            for path, data, mode in _walk_worktree(skill_root, manifest["include"], tracked_modes=tracked_modes)
        ]
        _validate_exact_paths(current, "current source")
        if current != entries:
            raise SnapshotError("source snapshot drifted from current worktree")

    archive_binding = manifest["archive"]
    if archive_bytes is None:
        if archive_binding is not None:
            raise SnapshotError("source snapshot archive bytes are required")
        if manifest["origin"]["kind"] != "dirty-worktree":
            raise SnapshotError("git-commit source snapshots require an archive")
        return
    if archive_binding is None:
        raise SnapshotError("archive bytes were supplied without an archive binding")
    if archive_binding["size"] != len(archive_bytes) or archive_binding["sha256"] != sha256_bytes(archive_bytes):
        raise SnapshotError("source snapshot archive size or hash mismatch")
    archive_files = _read_archive(archive_bytes)
    archive_entries = [_entry(path, data, mode) for path, data, mode in archive_files]
    _validate_exact_paths(archive_entries, "archive")
    if archive_entries != entries:
        raise SnapshotError("source snapshot archive does not match its file manifest")
    if build_ustar_bytes(archive_files) != archive_bytes:
        raise SnapshotError("source snapshot archive is not canonical deterministic ustar")


def _normalize_instrument_inputs(inputs: Mapping[str, str]) -> list[tuple[str, str]]:
    normalized: list[tuple[str, str]] = []
    for path, role in inputs.items():
        normalized_path = _relative_path(path, "instrument input").as_posix()
        if role not in ROLE_NAMES:
            raise SnapshotError(f"unsupported instrument role {role!r} for {path}")
        if _excluded(PurePosixPath(normalized_path)):
            raise SnapshotError(f"instrument input is excluded: {path}")
        normalized.append((normalized_path, role))
    normalized.sort()
    paths = [path for path, _ in normalized]
    if len(paths) != len(set(paths)):
        raise SnapshotError("instrument inputs contain duplicate paths")
    return normalized


def build_instrument_manifest(
    root: Path,
    inputs: Mapping[str, str],
    *,
    source_snapshots: Iterable[str] = ("0" * 64, "f" * 64),
    content_overrides: Mapping[str, bytes] | None = None,
) -> dict[str, Any]:
    normalized = _normalize_instrument_inputs(inputs)
    overrides = dict(content_overrides or {})
    normalized_override_paths = {
        _relative_path(path, "instrument content override").as_posix()
        for path in overrides
    }
    if normalized_override_paths != set(overrides):
        raise SnapshotError("instrument content override paths must be canonical")
    unknown_overrides = normalized_override_paths - {path for path, _ in normalized}
    if unknown_overrides:
        raise SnapshotError(f"instrument content overrides are not declared inputs: {sorted(unknown_overrides)}")
    entries: list[dict[str, Any]] = []
    for relative, role in normalized:
        if relative in overrides:
            data = overrides[relative]
            if not isinstance(data, bytes):
                raise SnapshotError(f"instrument content override must be bytes: {relative}")
        else:
            path = _resolve_below(root, relative, "instrument input")
            if path.is_symlink() or not path.is_file():
                raise SnapshotError(f"instrument input must be a regular non-symlink file: {relative}")
            data = path.read_bytes()
        entries.append({"path": relative, "role": role, "sha256": sha256_bytes(data), "size": len(data)})
    source_snapshot_list = list(source_snapshots)
    if len(source_snapshot_list) != 2 or len(set(source_snapshot_list)) != 2:
        raise SnapshotError("instrument manifest requires two distinct source snapshot hashes")
    manifest = {
        "schema_version": "1.0",
        "algorithm": "sha256-instrument-manifest-v1",
        "root": ".",
        "include": [path for path, _ in normalized],
        "exclude": list(CACHE_EXCLUDE),
        "files": entries,
        "source_snapshots": source_snapshot_list,
        "aggregate_sha256": _aggregate(entries),
    }
    validate_instrument_manifest(root, manifest, content_overrides=overrides)
    return manifest


def validate_instrument_manifest(
    root: Path,
    manifest: dict[str, Any],
    *,
    expected_inputs: Mapping[str, str] | None = None,
    content_overrides: Mapping[str, bytes] | None = None,
) -> None:
    validate_schema(manifest, INSTRUMENT_SCHEMA, "instrument manifest")
    if tuple(manifest["exclude"]) != CACHE_EXCLUDE:
        raise SnapshotError("instrument exclude set drifted")
    if len(manifest["source_snapshots"]) != 2 or len(set(manifest["source_snapshots"])) != 2:
        raise SnapshotError("instrument manifest must bind two distinct source snapshots")
    entries = manifest["files"]
    paths = [entry["path"] for entry in entries]
    if manifest["include"] != paths:
        raise SnapshotError("instrument include set must exactly equal the file manifest paths")
    _validate_exact_paths(entries, "instrument manifest")
    if expected_inputs is not None:
        expected = _normalize_instrument_inputs(expected_inputs)
        actual = [(entry["path"], entry["role"]) for entry in entries]
        if actual != expected:
            raise SnapshotError("instrument manifest path and role set drifted")
    roles = {entry["role"] for entry in entries}
    if not REQUIRED_INSTRUMENT_ROLES <= roles:
        raise SnapshotError(
            f"instrument manifest is missing required roles {sorted(REQUIRED_INSTRUMENT_ROLES - roles)}"
        )
    if manifest["aggregate_sha256"] != _aggregate(entries):
        raise SnapshotError("instrument aggregate hash mismatch")
    overrides = dict(content_overrides or {})
    unknown_overrides = set(overrides) - set(paths)
    if unknown_overrides:
        raise SnapshotError(f"instrument content overrides are not declared inputs: {sorted(unknown_overrides)}")
    for entry in entries:
        if entry["role"] not in ROLE_NAMES:
            raise SnapshotError(f"unsupported instrument role: {entry['role']!r}")
        if entry["path"] in overrides:
            data = overrides[entry["path"]]
            if not isinstance(data, bytes):
                raise SnapshotError(f"instrument content override must be bytes: {entry['path']}")
            actual_size = len(data)
            actual_sha256 = sha256_bytes(data)
        else:
            path = _resolve_below(root, entry["path"], "instrument file")
            if path.is_symlink() or not path.is_file():
                raise SnapshotError(f"instrument file must be a regular non-symlink file: {entry['path']}")
            actual_size = path.stat().st_size
            actual_sha256 = sha256_file(path)
        if actual_size != entry["size"] or actual_sha256 != entry["sha256"]:
            raise SnapshotError(f"instrument file drifted: {entry['path']}")


def instrument_manifest_sha256(manifest: dict[str, Any]) -> str:
    return sha256_bytes(canonical_bytes(manifest))


def _cli(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    git_parser = commands.add_parser("git-source")
    git_parser.add_argument("--repo-root", type=Path, required=True)
    git_parser.add_argument("--revision", required=True)
    git_parser.add_argument("--skill-rel", default="skills/create-loop")
    git_parser.add_argument("--snapshot-id", required=True)
    git_parser.add_argument("--protocol", choices=("v1", "v2"), required=True)
    git_parser.add_argument("--manifest", type=Path, required=True)
    git_parser.add_argument("--archive", type=Path, required=True)

    worktree_parser = commands.add_parser("worktree-source")
    worktree_parser.add_argument("--repo-root", type=Path, required=True)
    worktree_parser.add_argument("--skill-root", type=Path, required=True)
    worktree_parser.add_argument("--snapshot-id", required=True)
    worktree_parser.add_argument("--protocol", choices=("v1", "v2"), required=True)
    worktree_parser.add_argument("--base-git-commit", required=True)
    worktree_parser.add_argument("--manifest", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "git-source":
        manifest, archive = build_git_snapshot(
            args.repo_root,
            revision=args.revision,
            skill_rel=args.skill_rel,
            snapshot_id=args.snapshot_id,
            protocol=args.protocol,
        )
        write_json_atomic(args.manifest, manifest)
        write_bytes_atomic(args.archive, archive)
    else:
        manifest = build_worktree_snapshot(
            args.skill_root,
            repo_root=args.repo_root,
            snapshot_id=args.snapshot_id,
            protocol=args.protocol,
            base_git_commit=args.base_git_commit,
        )
        write_json_atomic(args.manifest, manifest)
    return 0


__all__ = [
    "CACHE_EXCLUDE",
    "INSTRUMENT_SCHEMA",
    "REQUIRED_INSTRUMENT_ROLES",
    "EXPERIMENT_INSTRUMENT_INPUTS",
    "ROLE_NAMES",
    "SOURCE_SCHEMA",
    "SUBJECT_INCLUDE",
    "SnapshotError",
    "build_git_snapshot",
    "build_instrument_manifest",
    "build_ustar_bytes",
    "build_worktree_snapshot",
    "canonical_bytes",
    "load_json",
    "sha256_bytes",
    "sha256_file",
    "instrument_manifest_sha256",
    "validate_instrument_manifest",
    "validate_schema",
    "validate_source_snapshot",
    "write_bytes_atomic",
    "write_json_atomic",
]


if __name__ == "__main__":
    try:
        raise SystemExit(_cli(sys.argv[1:]))
    except SnapshotError as exc:
        print(f"snapshot error: {exc}", file=sys.stderr)
        raise SystemExit(2)
