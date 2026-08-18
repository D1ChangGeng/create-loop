#!/usr/bin/env python3
"""Run the committed deterministic validator catalog against frozen sources.

The tool profile is a validated experiment declaration, not an OS capability
sandbox. Validators execute only from temporary copies of the frozen source
bytes so a live-worktree change cannot race the authoritative replay.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import site
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any


HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from schema_runtime import SchemaError, check_schema, validate  # noqa: E402
from snapshot_tools import SnapshotError, _read_archive, validate_source_snapshot  # noqa: E402


CATALOG_SCHEMA = HERE / "deterministic-fixture-catalog.schema.json"
TOOL_PROFILE_SCHEMA = HERE / "tool-profile.schema.json"
CASE_RESULT_SCHEMA = HERE / "deterministic-case-result.schema.json"
AUTHORITATIVE_RUN_SCHEMA = HERE / "deterministic-authoritative-run.schema.json"

EXECUTION_LAUNCHER = r"""
import base64
import hashlib
import json
import os
import runpy
import shutil
import sys
import tempfile
import traceback
from pathlib import Path, PurePosixPath


def canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def below(root, relative):
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or "\\" in relative or any(part in {"", ".", ".."} for part in path.parts):
        raise RuntimeError(f"unsafe captured source path: {relative!r}")
    return root.joinpath(*path.parts)


def tree_sha256(root):
    entries = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink():
            raise RuntimeError(f"captured fixture contains a symlink: {path}")
        if path.is_file():
            data = path.read_bytes()
            entries.append({"path": path.relative_to(root).as_posix(), "sha256": sha256_bytes(data), "size": len(data)})
    return sha256_bytes(canonical_bytes(entries))


def fixture_sha256(path):
    if path.is_symlink():
        raise RuntimeError(f"captured fixture is a symlink: {path}")
    if path.is_file():
        return sha256_bytes(path.read_bytes())
    if path.is_dir():
        return tree_sha256(path)
    raise RuntimeError(f"captured fixture is missing: {path}")


def source_state(root):
    directories = []
    files = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink():
            raise RuntimeError(f"captured source contains a symlink: {path}")
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            directories.append(relative)
        elif path.is_file():
            data = path.read_bytes()
            record = {"path": relative, "sha256": sha256_bytes(data), "size": len(data)}
            if os.name != "nt":
                record["mode"] = "0755" if path.stat().st_mode & 0o111 else "0644"
            files.append(record)
    return {"directories": directories, "files": files}


def expected_source_state(items):
    directories = set()
    files = []
    for item in items:
        path = PurePosixPath(item["path"])
        current = path.parent
        while current != PurePosixPath("."):
            directories.add(current.as_posix())
            current = current.parent
        record = {key: item[key] for key in ("path", "sha256", "size")}
        if os.name != "nt":
            record["mode"] = item["mode"]
        files.append(record)
    return {"directories": sorted(directories), "files": files}


def validator_exit_code(value):
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    print(value, file=sys.stderr)
    return 1


def main():
    payload = json.load(sys.stdin)
    original_cwd = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="create-loop-validator-input-") as temporary:
        root = Path(temporary)
        source_root = root / "source"
        source_root.mkdir()
        entries = []
        for item in payload["source_files"]:
            target = below(source_root, item["path"])
            data = base64.b64decode(item["data"], validate=True)
            if len(data) != item["size"] or sha256_bytes(data) != item["sha256"]:
                raise RuntimeError(f"captured source bytes drifted: {item['path']}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(int(item["mode"], 8))
            entries.append({key: item[key] for key in ("path", "sha256", "size", "mode")})
        if sha256_bytes(canonical_bytes(entries)) != payload["source_sha256"]:
            raise RuntimeError("captured source aggregate drifted")
        frozen_source_state = expected_source_state(payload["source_files"])
        if source_state(source_root) != frozen_source_state:
            raise RuntimeError("materialized captured source drifted")

        source_fixture = below(source_root, payload["fixture"])
        if fixture_sha256(source_fixture) != payload["source_fixture_sha256"]:
            raise RuntimeError("captured source fixture drifted")
        case_root = root / "case"
        case_root.mkdir()
        mutation = payload["mutation"]
        if mutation == "none":
            fixture = case_root / ("loop" if source_fixture.is_dir() else source_fixture.name)
            if source_fixture.is_dir():
                shutil.copytree(source_fixture, fixture)
            else:
                shutil.copyfile(source_fixture, fixture)
        elif mutation == "empty-object":
            fixture = case_root / "loop.plan.yaml"
            fixture.write_bytes(b"{}\n")
        elif mutation == "tamper-goal":
            if not source_fixture.is_dir():
                raise RuntimeError("tamper-goal requires a directory fixture")
            fixture = case_root / "loop"
            shutil.copytree(source_fixture, fixture)
            goal_path = fixture / "goal.json"
            goal = json.loads(goal_path.read_text(encoding="utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            goal["goal"] += " tampered"
            goal_path.write_bytes(canonical_bytes(goal))
        else:
            raise RuntimeError(f"unsupported fixture mutation: {mutation}")
        if fixture_sha256(fixture) != payload["executed_fixture_sha256"]:
            raise RuntimeError("captured executed fixture drifted")

        validator_path = below(source_root, payload["validator"])
        try:
            os.chdir(source_root)
            sys.path[:] = [str(source_root / "scripts"), str(source_root)] + [entry for entry in sys.path if entry]
            sys.argv = [str(validator_path), str(fixture)]
            try:
                runpy.run_path(str(validator_path), run_name="__main__")
                returncode = 0
            except SystemExit as exc:
                returncode = validator_exit_code(exc.code)
            except BaseException:
                traceback.print_exc()
                returncode = 2
            if source_state(source_root) != frozen_source_state:
                return 87
            if fixture_sha256(fixture) != payload["executed_fixture_sha256"]:
                return 86
            return returncode
        finally:
            os.chdir(original_cwd)


try:
    raise SystemExit(main())
except SystemExit:
    raise
except BaseException:
    traceback.print_exc()
    raise SystemExit(2)
"""

try:
    IMPORTED_RUNNER_BYTES = Path(__file__).resolve().read_bytes()
except OSError as exc:  # pragma: no cover - an unreadable imported module cannot run usefully
    raise RuntimeError(f"cannot capture imported deterministic runner bytes: {exc}") from exc
IMPORTED_RUNNER_SHA256 = hashlib.sha256(IMPORTED_RUNNER_BYTES).hexdigest()


class DeterministicRunnerError(RuntimeError):
    """A committed deterministic suite input or execution failed closed."""


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json_bytes(data: bytes, label: str) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant {value!r}")

    try:
        text = data.decode("utf-8")
        return json.loads(text, parse_constant=reject_constant)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise DeterministicRunnerError(f"cannot parse strict JSON {label}: {exc}") from exc


def load_json(path: Path) -> Any:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise DeterministicRunnerError(f"cannot read strict JSON {path}: {exc}") from exc
    return load_json_bytes(data, str(path))


def _resolve_below(root: Path, relative: str, label: str) -> Path:
    posix = PurePosixPath(relative)
    if posix.is_absolute() or ".." in posix.parts or "\\" in relative:
        raise DeterministicRunnerError(f"{label} path must remain below its root")
    candidate = (root / Path(*posix.parts)).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise DeterministicRunnerError(f"{label} path escapes its root") from exc
    return candidate


def _validate_schema_document(value: Any, schema: dict[str, Any], label: str) -> None:
    try:
        check_schema(schema)
        errors = validate(value, schema)
    except SchemaError as exc:
        raise DeterministicRunnerError(f"{label} schema is unsupported: {exc}") from exc
    if errors:
        raise DeterministicRunnerError(f"{label} schema validation failed: {'; '.join(errors)}")


def load_catalog_bytes(
    data: bytes,
    *,
    schema_bytes: bytes | None = None,
    label: str = "deterministic fixture catalog",
) -> dict[str, Any]:
    catalog = load_json_bytes(data, label)
    try:
        captured_schema = schema_bytes if schema_bytes is not None else CATALOG_SCHEMA.read_bytes()
    except OSError as exc:
        raise DeterministicRunnerError(f"cannot read deterministic catalog schema: {exc}") from exc
    schema = load_json_bytes(captured_schema, "deterministic catalog schema")
    _validate_schema_document(catalog, schema, "catalog")
    case_ids = [case["case_id"] for case in catalog["cases"]]
    if len(case_ids) != len(set(case_ids)):
        raise DeterministicRunnerError("catalog case IDs must be unique")
    if {case["expected"] for case in catalog["cases"]} != {"accept", "reject"}:
        raise DeterministicRunnerError("catalog must contain both accept and reject controls")
    return catalog


def load_catalog(path: Path) -> dict[str, Any]:
    try:
        data = path.read_bytes()
        schema_bytes = CATALOG_SCHEMA.read_bytes()
    except OSError as exc:
        raise DeterministicRunnerError(f"cannot read deterministic fixture catalog {path}: {exc}") from exc
    return load_catalog_bytes(data, schema_bytes=schema_bytes, label=str(path))


def _load_source_binding(experiment_dir: Path, preregistration: dict[str, Any], protocol: str) -> tuple[dict[str, Any], bytes | None]:
    key = "baseline" if protocol == "v1" else "candidate"
    binding = preregistration[key]["source_snapshot"]
    manifest_path = _resolve_below(experiment_dir, binding["manifest"]["path"], f"{protocol} source manifest")
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise DeterministicRunnerError(f"{protocol} source manifest binding drifted")
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as exc:
        raise DeterministicRunnerError(f"cannot read {protocol} source manifest: {exc}") from exc
    if sha256_bytes(manifest_bytes) != binding["manifest"]["sha256"]:
        raise DeterministicRunnerError(f"{protocol} source manifest binding drifted")
    manifest = load_json_bytes(manifest_bytes, str(manifest_path))
    if manifest["protocol"] != protocol or manifest["aggregate_sha256"] != binding["aggregate_sha256"]:
        raise DeterministicRunnerError(f"{protocol} source identity drifted")
    origin = manifest["origin"]
    if origin.get("commit", origin.get("base_git_commit")) != binding["origin_commit"]:
        raise DeterministicRunnerError(f"{protocol} source origin drifted")
    archive_bytes: bytes | None = None
    if binding.get("archive") is not None:
        archive_path = _resolve_below(experiment_dir, binding["archive"]["path"], f"{protocol} source archive")
        if not archive_path.is_file() or archive_path.is_symlink():
            raise DeterministicRunnerError(f"{protocol} source archive binding drifted")
        try:
            archive_bytes = archive_path.read_bytes()
        except OSError as exc:
            raise DeterministicRunnerError(f"cannot read {protocol} source archive: {exc}") from exc
        if sha256_bytes(archive_bytes) != binding["archive"]["sha256"]:
            raise DeterministicRunnerError(f"{protocol} source archive binding drifted")
    return manifest, archive_bytes


def _capture_manifest_source(manifest: dict[str, Any], source: Path) -> dict[str, bytes]:
    captured: dict[str, bytes] = {}
    for entry in manifest["files"]:
        source_path = _resolve_below(source, entry["path"], "source snapshot member")
        if not source_path.is_file() or source_path.is_symlink():
            raise DeterministicRunnerError(f"source snapshot member is not a regular file: {entry['path']}")
        data = source_path.read_bytes()
        if len(data) != entry["size"] or sha256_bytes(data) != entry["sha256"]:
            raise DeterministicRunnerError(f"source snapshot member drifted while capturing: {entry['path']}")
        captured[entry["path"]] = data
    return captured


def _capture_archive_source(manifest: dict[str, Any], archive_bytes: bytes) -> dict[str, bytes]:
    captured = {relative: data for relative, data, _ in _read_archive(archive_bytes)}
    _validate_captured_source(manifest, captured)
    return captured


def _validate_captured_source(manifest: dict[str, Any], captured: dict[str, bytes]) -> None:
    if set(captured) != {entry["path"] for entry in manifest["files"]}:
        raise DeterministicRunnerError("captured source path set drifted from the frozen manifest")
    for entry in manifest["files"]:
        data = captured[entry["path"]]
        if len(data) != entry["size"] or sha256_bytes(data) != entry["sha256"]:
            raise DeterministicRunnerError(f"captured source member drifted: {entry['path']}")


def _captured_fixture(captured: dict[str, bytes], relative: str) -> tuple[str, dict[str, bytes]]:
    if relative in captured:
        return "file", {PurePosixPath(relative).name: captured[relative]}
    prefix = f"{relative.rstrip('/')}/"
    files = {
        path[len(prefix):]: data
        for path, data in captured.items()
        if path.startswith(prefix)
    }
    if not files:
        raise DeterministicRunnerError(f"captured fixture does not exist: {relative}")
    return "directory", files


def _captured_tree_sha256(files: dict[str, bytes]) -> str:
    entries = [
        {"path": path, "sha256": sha256_bytes(data), "size": len(data)}
        for path, data in sorted(files.items())
    ]
    return sha256_bytes(canonical_bytes(entries))


def _expected_fixture_hashes(captured: dict[str, bytes], definition: dict[str, Any]) -> tuple[str, str]:
    kind, files = _captured_fixture(captured, definition["fixture"])
    source_hash = sha256_bytes(next(iter(files.values()))) if kind == "file" else _captured_tree_sha256(files)
    mutation = definition["mutation"]
    if mutation == "none":
        return source_hash, source_hash
    if mutation == "empty-object":
        return source_hash, sha256_bytes(b"{}\n")
    if mutation == "tamper-goal":
        if kind != "directory" or "goal.json" not in files:
            raise DeterministicRunnerError("tamper-goal requires a directory fixture with goal.json")
        mutated = dict(files)
        goal = load_json_bytes(mutated["goal.json"], "captured fixture goal.json")
        if not isinstance(goal, dict) or not isinstance(goal.get("goal"), str):
            raise DeterministicRunnerError("tamper-goal fixture goal.json lacks a string goal")
        goal["goal"] += " tampered"
        mutated["goal.json"] = canonical_bytes(goal)
        return source_hash, _captured_tree_sha256(mutated)
    raise DeterministicRunnerError(f"unsupported fixture mutation: {mutation}")


def _execution_source_files(manifest: dict[str, Any], captured: dict[str, bytes]) -> list[dict[str, Any]]:
    _validate_captured_source(manifest, captured)
    return [
        {
            **entry,
            "data": base64.b64encode(captured[entry["path"]]).decode("ascii"),
        }
        for entry in manifest["files"]
    ]


def _instrument_entries(experiment_dir: Path, preregistration: dict[str, Any]) -> dict[str, dict[str, Any]]:
    binding = preregistration["instrument_manifest"]
    manifest_path = _resolve_below(experiment_dir, binding["path"], "instrument manifest")
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise DeterministicRunnerError("instrument manifest binding drifted")
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as exc:
        raise DeterministicRunnerError(f"cannot read instrument manifest: {exc}") from exc
    if sha256_bytes(manifest_bytes) != binding["sha256"]:
        raise DeterministicRunnerError("instrument manifest binding drifted")
    manifest = load_json_bytes(manifest_bytes, str(manifest_path))
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(files, list) or not all(isinstance(entry, dict) for entry in files):
        raise DeterministicRunnerError("instrument manifest file bindings are invalid")
    paths = [entry.get("path") for entry in files]
    if any(not isinstance(path, str) for path in paths) or len(paths) != len(set(paths)):
        raise DeterministicRunnerError("instrument manifest file bindings are not unique")
    return {entry["path"]: entry for entry in files}


def _require_instrument_bytes(
    entries: dict[str, dict[str, Any]],
    canonical_path: str,
    data: bytes,
    label: str,
) -> None:
    entry = entries.get(canonical_path)
    if (
        entry is None
        or entry.get("sha256") != sha256_bytes(data)
        or entry.get("size") != len(data)
    ):
        raise DeterministicRunnerError(f"{label} is not the frozen instrument input")


def _load_tool_profile_bytes(
    data: bytes,
    *,
    schema_bytes: bytes | None = None,
    label: str = "deterministic tool profile",
) -> dict[str, Any]:
    profile = load_json_bytes(data, label)
    schema = load_json_bytes(
        schema_bytes if schema_bytes is not None else TOOL_PROFILE_SCHEMA.read_bytes(),
        "deterministic tool profile schema",
    )
    _validate_schema_document(profile, schema, "tool profile")
    required_capabilities = {"execute-local", "read-workspace", "write-declared-workspace-paths"}
    if profile["network"] != "denied" or profile["publish"] != "denied":
        raise DeterministicRunnerError("deterministic tool profile must deny network and publish")
    if profile["external_effects"] != "simulated-workspace-only" or profile["writable_roots"] != ["workspace"]:
        raise DeterministicRunnerError("deterministic tool profile must confine effects to the temporary workspace")
    if set(profile["allowed_capabilities"]) != required_capabilities:
        raise DeterministicRunnerError("deterministic tool profile allowed capabilities drifted")
    required_denials = {"credentials", "delete-outside-workspace", "network", "payment", "publish"}
    if set(profile["denied_capabilities"]) != required_denials:
        raise DeterministicRunnerError("deterministic tool profile denied capabilities drifted")
    if set(profile["environment"]["allow"]) != {"PATH", "PYTHONIOENCODING", "PYTHONDONTWRITEBYTECODE"}:
        raise DeterministicRunnerError("deterministic tool profile environment allowlist drifted")
    if set(profile["environment"]["deny_prefixes"]) != {"ANTHROPIC_", "AWS_", "GITHUB_TOKEN", "OPENAI_"}:
        raise DeterministicRunnerError("deterministic tool profile environment deny prefixes drifted")
    if profile["environment"]["credential_allow"] != []:
        raise DeterministicRunnerError("deterministic tool profile must not allow credentials")
    return profile


def _load_tool_profile(path: Path, schema_path: Path = TOOL_PROFILE_SCHEMA) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise DeterministicRunnerError("deterministic tool profile must be a regular file")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise DeterministicRunnerError(f"cannot read deterministic tool profile {path}: {exc}") from exc
    try:
        schema_bytes = schema_path.read_bytes()
    except OSError as exc:
        raise DeterministicRunnerError(f"cannot read deterministic tool profile schema {schema_path}: {exc}") from exc
    return _load_tool_profile_bytes(data, schema_bytes=schema_bytes, label=str(path))


def _subprocess_environment(profile: dict[str, Any], protocol: str) -> dict[str, str]:
    deny_prefixes = tuple(prefix.casefold() for prefix in profile["environment"]["deny_prefixes"])
    environment = {
        name: os.environ[name]
        for name in profile["environment"]["allow"]
        if name in os.environ and not name.casefold().startswith(deny_prefixes)
    }
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    if protocol == "v1" and site.ENABLE_USER_SITE:
        user_site = site.getusersitepackages()
        if user_site:
            environment["PYTHONPATH"] = user_site
    return environment


def _validate_result(value: dict[str, Any], schema_bytes: bytes, label: str) -> None:
    _validate_schema_document(value, load_json_bytes(schema_bytes, f"{label} schema"), label)


def _run_case(
    manifest: dict[str, Any],
    captured_source: dict[str, bytes],
    case: dict[str, Any],
    protocol: str,
    environment: dict[str, str],
    case_result_schema_bytes: bytes,
) -> dict[str, Any]:
    definition = case["protocols"][protocol]
    validator_name = definition["validator"]
    validator_rel = "scripts/validate_loop_plan.py" if validator_name == "validate_loop_plan" else "scripts/validate_loop_dir.py"
    validator_bytes = captured_source.get(validator_rel)
    if validator_bytes is None:
        raise DeterministicRunnerError(f"captured {protocol} validator is missing")
    validator_sha256 = sha256_bytes(validator_bytes)
    source_fixture_hash, executed_fixture_hash = _expected_fixture_hashes(captured_source, definition)
    execution_payload = {
        "source_files": _execution_source_files(manifest, captured_source),
        "source_sha256": manifest["aggregate_sha256"],
        "validator": validator_rel,
        "fixture": definition["fixture"],
        "mutation": definition["mutation"],
        "source_fixture_sha256": source_fixture_hash,
        "executed_fixture_sha256": executed_fixture_hash,
    }
    try:
        command = [sys.executable]
        if protocol == "v2":
            command.append("-s")
        command.extend(["-c", EXECUTION_LAUNCHER])
        completed = subprocess.run(
            command,
            env=environment,
            text=True,
            input=json.dumps(execution_payload, sort_keys=True, separators=(",", ":")),
            capture_output=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise DeterministicRunnerError(f"{protocol} validator execution failed: {exc}") from exc
    if completed.returncode == 86:
        raise DeterministicRunnerError(f"{protocol} validator mutated its executed fixture")
    if completed.returncode == 87:
        raise DeterministicRunnerError(f"{protocol} validator mutated its captured source tree")
    actual = "accept" if completed.returncode == 0 else "reject" if completed.returncode == 1 else "error"
    result = {
        "schema_version": "1.0",
        "algorithm": "create-loop-deterministic-case-result-v1",
        "case_id": case["case_id"],
        "protocol": protocol,
        "expected": case["expected"],
        "actual": actual,
        "validator": {
            "id": validator_name,
            "sha256": validator_sha256,
        },
        "source_fixture_sha256": source_fixture_hash,
        "executed_fixture_sha256": executed_fixture_hash,
        "returncode": completed.returncode,
    }
    _validate_result(result, case_result_schema_bytes, "deterministic case result")
    return result


def run_suite(
    experiment_dir: Path,
    preregistration: dict[str, Any],
    protocol: str,
    *,
    catalog_path: Path,
    tool_profile_path: Path,
    candidate_skill_root: Path = SKILL_ROOT,
    runner_path: Path | None = None,
) -> dict[str, Any]:
    if protocol not in {"v1", "v2"}:
        raise DeterministicRunnerError(f"unsupported protocol: {protocol}")
    experiment_dir = experiment_dir.resolve()
    candidate_skill_root = candidate_skill_root.resolve()
    runner_path = (runner_path or Path(__file__)).resolve()
    if not runner_path.is_file() or runner_path.is_symlink():
        raise DeterministicRunnerError("deterministic runner must be a regular file")
    try:
        catalog_bytes = catalog_path.read_bytes()
        tool_profile_bytes = tool_profile_path.read_bytes()
        runner_bytes = runner_path.read_bytes()
        catalog_schema_bytes = (experiment_dir / "deterministic-fixture-catalog.schema.json").read_bytes()
        tool_profile_schema_bytes = (experiment_dir / "tool-profile.schema.json").read_bytes()
        case_result_schema_bytes = (experiment_dir / "deterministic-case-result.schema.json").read_bytes()
        authoritative_run_schema_bytes = (experiment_dir / "deterministic-authoritative-run.schema.json").read_bytes()
    except OSError as exc:
        raise DeterministicRunnerError(f"cannot capture deterministic input bytes: {exc}") from exc
    if runner_bytes != IMPORTED_RUNNER_BYTES:
        raise DeterministicRunnerError("runner_path bytes do not match the imported deterministic runner")
    expected_profile = preregistration["execution_config"]["tool_profile"]
    if sha256_bytes(tool_profile_bytes) != expected_profile["sha256"]:
        raise DeterministicRunnerError("deterministic tool profile hash drifted from preregistration")
    instrument_entries = _instrument_entries(experiment_dir, preregistration)
    for canonical_path, data, label in (
        ("deterministic-fixture-catalog.json", catalog_bytes, "deterministic fixture catalog"),
        ("deterministic_runner.py", runner_bytes, "deterministic runner"),
        (expected_profile["path"], tool_profile_bytes, "deterministic tool profile"),
        ("deterministic-fixture-catalog.schema.json", catalog_schema_bytes, "deterministic catalog schema"),
        ("tool-profile.schema.json", tool_profile_schema_bytes, "deterministic tool-profile schema"),
        ("deterministic-case-result.schema.json", case_result_schema_bytes, "deterministic case-result schema"),
        ("deterministic-authoritative-run.schema.json", authoritative_run_schema_bytes, "deterministic authoritative-run schema"),
    ):
        _require_instrument_bytes(instrument_entries, canonical_path, data, label)
    catalog = load_catalog_bytes(catalog_bytes, schema_bytes=catalog_schema_bytes, label=str(catalog_path))
    tool_profile = _load_tool_profile_bytes(
        tool_profile_bytes,
        schema_bytes=tool_profile_schema_bytes,
        label=str(tool_profile_path),
    )
    if tool_profile["id"] != expected_profile["id"]:
        raise DeterministicRunnerError("deterministic tool profile ID drifted from preregistration")
    manifest, archive_bytes = _load_source_binding(experiment_dir, preregistration, protocol)
    try:
        if protocol == "v1":
            if archive_bytes is None:
                raise DeterministicRunnerError("v1 deterministic execution requires the frozen source archive")
            validate_source_snapshot(manifest, archive_bytes=archive_bytes)
            captured_source = _capture_archive_source(manifest, archive_bytes)
        else:
            captured_source = _capture_manifest_source(manifest, candidate_skill_root)
            validate_source_snapshot(manifest)
    except SnapshotError as exc:
        raise DeterministicRunnerError(f"{protocol} source snapshot validation failed: {exc}") from exc
    _validate_captured_source(manifest, captured_source)
    environment = _subprocess_environment(tool_profile, protocol)
    cases = [
        _run_case(manifest, captured_source, case, protocol, environment, case_result_schema_bytes)
        for case in catalog["cases"]
    ]
    result = {
        "schema_version": "1.0",
        "algorithm": "create-loop-deterministic-validator-run-v1",
        "experiment_id": preregistration["experiment_id"],
        "preregistration_sha256": sha256_bytes(canonical_bytes(preregistration)),
        "protocol": protocol,
        "source_sha256": manifest["aggregate_sha256"],
        "fixture_catalog_sha256": sha256_bytes(catalog_bytes),
        "runner_sha256": IMPORTED_RUNNER_SHA256,
        "tool_profile_sha256": sha256_bytes(tool_profile_bytes),
        "cases": cases,
    }
    _validate_result(result, authoritative_run_schema_bytes, "deterministic authoritative run")
    return result


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--experiment-dir", type=Path, default=HERE)
    value.add_argument("--preregistration", type=Path)
    value.add_argument("--protocol", choices=("v1", "v2"), required=True)
    value.add_argument("--catalog", type=Path)
    value.add_argument("--tool-profile", type=Path)
    value.add_argument("--candidate-skill-root", type=Path, default=SKILL_ROOT)
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    experiment_dir = args.experiment_dir.resolve()
    preregistration_path = (args.preregistration or experiment_dir / "preregistration.json").resolve()
    catalog_path = (args.catalog or experiment_dir / "deterministic-fixture-catalog.json").resolve()
    tool_profile_path = (args.tool_profile or experiment_dir / "tool-profiles" / "local-full-no-publish.json").resolve()
    try:
        result = run_suite(
            experiment_dir,
            load_json(preregistration_path),
            args.protocol,
            catalog_path=catalog_path,
            tool_profile_path=tool_profile_path,
            candidate_skill_root=args.candidate_skill_root,
        )
    except DeterministicRunnerError as exc:
        print(f"deterministic runner error: {exc}", file=sys.stderr)
        return 2
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
