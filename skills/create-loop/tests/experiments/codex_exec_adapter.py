#!/usr/bin/env python3
"""Execute one authorized Phase 5 run through ``codex exec``.

The adapter is deliberately one-run-at-a-time. It reserves the full per-run
budget before spawning Codex, preserves the provider JSONL byte-for-byte, and
settles only after strict provider request and usage evidence is available.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Iterable


HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import execution_guard as guard  # noqa: E402
import network_execution_boundary as execution_boundary  # noqa: E402
import workspace_builder as workspaces  # noqa: E402
from schema_runtime import SchemaError, check_schema, validate  # noqa: E402


ADAPTER_ID = "codex-exec"
ADAPTER_VERSION = "2.0"
TRACE_SCHEMA = HERE / "trace.schema.json"
COMPLETION_SCHEMA = HERE / "completion-claim.schema.json"
FINAL_WORKSPACE_SCHEMA = HERE / "final-workspace-manifest.schema.json"
INITIAL_WORKSPACE_SCHEMA = HERE / "initial-workspace-manifest.schema.json"
EVIDENCE_SCHEMA = HERE / "evidence-manifest.schema.json"
INTERRUPTION_EVIDENCE_SCHEMA = HERE / "interruption-evidence-manifest.schema.json"
TRACE_SOURCE_SCHEMA = HERE / "trace-source.schema.json"
PROVIDER_SCHEMA = HERE / "provider-profile.schema.json"
CLI_SCHEMA = HERE / "cli-identity.schema.json"
INTERRUPTION_SCHEMA = HERE / "controller-interruption.schema.json"
POPULATION_SEAL_SCHEMA = HERE / "workspace-population-seal.schema.json"
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REASONING_EFFORTS = {"low", "medium", "high", "xhigh", "max", "ultra"}
PRODUCTION_PROFILE = "provider-workspace-no-publish"
PLATFORM_ENV = {
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "SYSTEMDRIVE",
    "TEMP",
    "TMP",
}


class AdapterError(RuntimeError):
    """One adapter invariant failed before authoritative settlement."""


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
        raise AdapterError(f"value is not canonical JSON: {exc}") from exc


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant {value!r}")


def load_json(path: Path, label: str) -> Any:
    if not path.is_file() or path.is_symlink():
        raise AdapterError(f"{label} must be a regular non-symlink file")
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle, parse_constant=_reject_constant)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise AdapterError(f"cannot read strict JSON {label}: {exc}") from exc


def _validate_schema(instance: Any, schema_path: Path, label: str) -> None:
    schema = load_json(schema_path, f"{label} schema")
    try:
        check_schema(schema)
        errors = validate(instance, schema)
    except SchemaError as exc:
        raise AdapterError(f"{label} schema is unsupported: {exc}") from exc
    if errors:
        raise AdapterError(f"{label} schema validation failed: {'; '.join(errors)}")


def _write_new_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise AdapterError(f"immutable output already exists: {path}") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _write_new_json(path: Path, value: Any) -> None:
    _write_new_bytes(path, canonical_bytes(value))


def _now_text(value: datetime | None = None) -> str:
    return (value or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def adapter_binding() -> dict[str, str]:
    return {
        "id": ADAPTER_ID,
        "version": ADAPTER_VERSION,
        "sha256": sha256_file(Path(__file__).resolve()),
    }


def _binding(value: Any, label: str, *, include_id: bool = False) -> dict[str, Any]:
    required = {"path", "sha256"} | ({"id"} if include_id else set())
    if not isinstance(value, dict) or set(value) != required:
        raise AdapterError(f"{label} has the wrong fields")
    if not isinstance(value["path"], str) or SHA256.fullmatch(str(value["sha256"])) is None:
        raise AdapterError(f"{label} is invalid")
    if include_id and (not isinstance(value["id"], str) or SAFE_ID.fullmatch(value["id"]) is None):
        raise AdapterError(f"{label} ID is invalid")
    return value


def _validate_run_plan(plan: Any) -> dict[str, Any]:
    fields = {
        "schema_version", "campaign_id", "preregistration_sha256", "algorithm",
        "pair_count", "arm_count", "producer_episode_count", "arms", "runs",
    }
    if not isinstance(plan, dict) or set(plan) != fields:
        raise AdapterError("pilot run plan has the wrong top-level fields")
    if (
        plan["schema_version"] != "1.0"
        or plan["algorithm"] != "fixed-pilot-order-v1"
        or not isinstance(plan["campaign_id"], str)
        or SAFE_ID.fullmatch(plan["campaign_id"]) is None
        or SHA256.fullmatch(str(plan["preregistration_sha256"])) is None
        or plan["pair_count"] != 6
        or plan["arm_count"] != 12
        or plan["producer_episode_count"] != 18
        or not isinstance(plan["arms"], list)
        or len(plan["arms"]) != 12
        or not isinstance(plan["runs"], list)
        or len(plan["runs"]) != 18
    ):
        raise AdapterError("pilot run plan identity or cardinality is invalid")
    arm_fields = {
        "arm_id", "pair_id", "case_id", "scenario_slug", "protocol", "arm_position",
        "workspace_seed", "input_sha256", "semantic_case_sha256",
        "initial_workspace_manifest_sha256", "protocol_source", "protocol_bundle",
        "tool_profile", "episodes",
    }
    episode_fields = {
        "run_id", "episode_id", "sequence", "fresh_session", "prompt",
        "injection_ref", "termination",
    }
    seen_arms: set[str] = set()
    seen_runs: set[str] = set()
    pairs: dict[str, list[dict[str, Any]]] = {}
    episode_count = 0
    projected_runs: list[dict[str, Any]] = []
    for arm in plan["arms"]:
        if not isinstance(arm, dict) or set(arm) != arm_fields:
            raise AdapterError("pilot arm has the wrong fields")
        arm_id = arm["arm_id"]
        protocol = arm["protocol"]
        if (
            not isinstance(arm_id, str)
            or SAFE_ID.fullmatch(arm_id) is None
            or arm_id in seen_arms
            or protocol not in {"v1", "v2"}
            or arm_id != f"{arm['pair_id']}-{protocol}"
            or arm["arm_position"] not in {1, 2}
            or not isinstance(arm["workspace_seed"], int)
            or isinstance(arm["workspace_seed"], bool)
            or arm["workspace_seed"] < 0
            or not isinstance(arm["scenario_slug"], str)
            or not arm["scenario_slug"]
        ):
            raise AdapterError("pilot arm identity is inconsistent")
        seen_arms.add(arm_id)
        for field in ("input_sha256", "semantic_case_sha256", "initial_workspace_manifest_sha256"):
            if SHA256.fullmatch(str(arm[field])) is None:
                raise AdapterError(f"pilot arm has invalid {field}")
        source = arm["protocol_source"]
        if (
            not isinstance(source, dict)
            or set(source) != {"protocol", "aggregate_sha256", "manifest"}
            or source["protocol"] != protocol
            or SHA256.fullmatch(str(source["aggregate_sha256"])) is None
        ):
            raise AdapterError("pilot arm protocol source is invalid")
        _binding(source["manifest"], "protocol source manifest")
        _binding(arm["protocol_bundle"], "protocol bundle")
        _binding(arm["tool_profile"], "tool profile", include_id=True)
        episodes = arm["episodes"]
        if not isinstance(episodes, list) or len(episodes) not in {1, 2}:
            raise AdapterError("pilot arm episodes are invalid")
        for expected_sequence, episode in enumerate(episodes, start=1):
            if not isinstance(episode, dict) or set(episode) != episode_fields:
                raise AdapterError("pilot episode has the wrong fields")
            episode_id = f"E{expected_sequence:02d}"
            run_id = episode["run_id"]
            if (
                episode["episode_id"] != episode_id
                or episode["sequence"] != expected_sequence
                or episode["fresh_session"] is not True
                or not isinstance(run_id, str)
                or run_id != f"{arm_id}-{episode_id}"
                or run_id in seen_runs
                or not isinstance(episode["prompt"], str)
                or not episode["prompt"].strip()
                or episode["termination"] not in {"normal", "controller-kill-after-reality-before-post"}
            ):
                raise AdapterError("pilot episode identity is inconsistent")
            seen_runs.add(run_id)
            episode_count += 1
            projected_runs.append({
                "run_id": run_id,
                "arm_id": arm_id,
                "pair_id": arm["pair_id"],
                "case_id": arm["case_id"],
                "protocol": protocol,
                "episode_id": episode_id,
                "sequence": expected_sequence,
                "fresh_session": episode["fresh_session"],
                "injection_ref": episode["injection_ref"],
                "termination": episode["termination"],
            })
        pairs.setdefault(arm["pair_id"], []).append(arm)
    if episode_count != plan["producer_episode_count"] or len(pairs) != plan["pair_count"]:
        raise AdapterError("pilot run plan counts are inconsistent")
    for pair_id, arms in pairs.items():
        if (
            len(arms) != 2
            or {arm["protocol"] for arm in arms} != {"v1", "v2"}
            or {arm["arm_position"] for arm in arms} != {1, 2}
            or len({arm["workspace_seed"] for arm in arms}) != 1
            or len({arm["semantic_case_sha256"] for arm in arms}) != 1
        ):
            raise AdapterError(f"pilot pair {pair_id} is incomplete or unbalanced")
    if plan["runs"] != projected_runs:
        raise AdapterError("pilot flat runs drifted from the ordered arm episodes")
    return plan


def _select_episode(
    plan: dict[str, Any], run_id: str | None, episode_id: str | None
) -> tuple[dict[str, Any], dict[str, Any]]:
    matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for arm in plan["arms"]:
        for episode in arm["episodes"]:
            if run_id is None or episode["run_id"] == run_id:
                matches.append((arm, episode))
    if run_id is None:
        raise AdapterError("production execution requires explicit --run-id")
    if len(matches) != 1:
        raise AdapterError("run_id is not present exactly once in the pilot plan")
    arm, episode = matches[0]
    if episode_id != episode["episode_id"]:
        raise AdapterError("episode_id does not match the selected run")
    return arm, episode


def _confined_file(base: Path, relative: str, label: str) -> Path:
    posix = PurePosixPath(relative)
    if posix.is_absolute() or ".." in posix.parts or "\\" in relative:
        raise AdapterError(f"{label} path escapes the experiment directory")
    path = (base / Path(*posix.parts)).resolve()
    try:
        path.relative_to(base.resolve())
    except ValueError as exc:
        raise AdapterError(f"{label} path escapes the experiment directory") from exc
    if not path.is_file() or path.is_symlink():
        raise AdapterError(f"{label} must be a regular non-symlink file")
    return path


def _load_bound_profile(
    experiment_dir: Path,
    arm: dict[str, Any],
    grant_value: dict[str, Any] | None,
    explicit: Path | None,
    *,
    production: bool,
) -> tuple[Path, dict[str, Any]]:
    binding = arm["tool_profile"]
    if grant_value is not None and grant_value["tool_profile"] != binding:
        raise AdapterError("authorization tool profile drifted from the run plan")
    expected = _confined_file(experiment_dir, binding["path"], "tool profile")
    if explicit is not None and explicit.resolve() != expected:
        raise AdapterError("explicit tool profile does not match the run plan")
    if sha256_file(expected) != binding["sha256"]:
        raise AdapterError("tool profile hash drifted from the run plan")
    try:
        profile = workspaces.validate_tool_profile(expected)
    except workspaces.WorkspaceError as exc:
        raise AdapterError(f"tool profile is invalid: {exc}") from exc
    if profile["id"] != binding["id"]:
        raise AdapterError("tool profile ID drifted from the run plan")
    if production and (
        profile["id"] != PRODUCTION_PROFILE
        or profile["network"] != "provider-api-only"
        or "provider-model-call" not in profile["allowed_capabilities"]
        or profile["publish"] != "denied"
        or profile["external_effects"] != "simulated-workspace-only"
        or profile["writable_roots"] != ["workspace"]
    ):
        raise AdapterError("production execution requires the provider-workspace-no-publish profile")
    return expected, profile


def _load_bound_identity(
    experiment_dir: Path,
    binding: dict[str, Any],
    schema_path: Path,
    label: str,
) -> tuple[Path, dict[str, Any]]:
    path = _confined_file(experiment_dir, binding["path"], label)
    if sha256_file(path) != binding["sha256"]:
        raise AdapterError(f"{label} hash drifted")
    value = load_json(path, label)
    _validate_schema(value, schema_path, label)
    if value["id"] != binding["id"]:
        raise AdapterError(f"{label} ID drifted")
    return path, value


def _verify_cli_identity(executable: str, identity: dict[str, Any]) -> None:
    launcher = Path(executable).resolve()
    if sha256_file(launcher) != identity["launcher_sha256"]:
        raise AdapterError("Codex launcher hash drifted from the frozen CLI identity")
    entrypoint = launcher.parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
    package = launcher.parent / "node_modules" / "@openai" / "codex" / "package.json"
    if not entrypoint.is_file() or sha256_file(entrypoint) != identity["entrypoint_sha256"]:
        raise AdapterError("Codex entrypoint hash drifted from the frozen CLI identity")
    if not package.is_file() or sha256_file(package) != identity["package_sha256"]:
        raise AdapterError("Codex package hash drifted from the frozen CLI identity")
    native_candidates = sorted(
        launcher.parent.glob("node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/*/bin/codex.exe")
    )
    if len(native_candidates) != 1 or sha256_file(native_candidates[0]) != identity["native_executable_sha256"]:
        raise AdapterError("Codex native executable hash drifted from the frozen CLI identity")
    package_value = load_json(package, "Codex package")
    if package_value.get("version") != identity["version"]:
        raise AdapterError("Codex package version drifted from the frozen CLI identity")


def _verify_frozen_cli_identity(executable: str, identity: dict[str, Any]) -> None:
    _verify_cli_identity(executable, identity)


def _clean_environment(profile: dict[str, Any]) -> dict[str, str]:
    configured = set(profile["environment"]["allow"])
    allowed = configured | PLATFORM_ENV
    credentials = set(profile["environment"]["credential_allow"])
    denied_prefixes = tuple(profile["environment"]["deny_prefixes"])
    result: dict[str, str] = {}
    for name in sorted(allowed):
        if name not in os.environ:
            continue
        if name in credentials:
            result[name] = os.environ[name]
            continue
        if any(name == prefix or name.startswith(prefix) for prefix in denied_prefixes):
            continue
        result[name] = os.environ[name]
    if "PATH" not in result or not result["PATH"]:
        raise AdapterError("tool profile environment must provide PATH")
    if "CODEX_HOME" in configured and "CODEX_HOME" not in credentials:
        raise AdapterError("CODEX_HOME requires explicit credential_allow")
    result["PYTHONIOENCODING"] = "utf-8"
    result["PYTHONDONTWRITEBYTECODE"] = "1"
    result["NO_COLOR"] = "1"
    return result


def _resolve_codex(executable: str, environment: dict[str, str]) -> str:
    candidate = Path(executable)
    if candidate.is_absolute() or candidate.parent != Path("."):
        resolved = candidate.resolve()
        if not resolved.is_file():
            raise AdapterError("codex executable does not exist")
        return str(resolved)
    resolved = shutil.which(executable, path=environment["PATH"])
    if resolved is None:
        raise AdapterError("codex executable is not available on the clean PATH")
    return resolved


def _source_manifest_binding(
    experiment_dir: Path, arm: dict[str, Any]
) -> tuple[Path, dict[str, Any]]:
    binding = arm["protocol_source"]["manifest"]
    path = _confined_file(experiment_dir, binding["path"], "protocol source manifest")
    if sha256_file(path) != binding["sha256"]:
        raise AdapterError("protocol source manifest file hash drifted")
    manifest = load_json(path, "protocol source manifest")
    if (
        manifest.get("protocol") != arm["protocol"]
        or manifest.get("aggregate_sha256") != arm["protocol_source"]["aggregate_sha256"]
    ):
        raise AdapterError("protocol source manifest identity drifted")
    return path, manifest


def _case_for_arm(experiment_dir: Path, arm: dict[str, Any]) -> dict[str, Any]:
    try:
        case = workspaces.load_pilot_case(
            arm["case_id"], experiment_dir / "pilot-scenarios.json"
        )
    except workspaces.WorkspaceError as exc:
        raise AdapterError(f"pilot case is invalid: {exc}") from exc
    if (
        case["pair_id"] != arm["pair_id"]
        or case["slug"] != arm["scenario_slug"]
        or case["input_sha256"] != arm["input_sha256"]
        or case["protocol_order"][arm["arm_position"] - 1] != arm["protocol"]
    ):
        raise AdapterError("pilot case identity drifted from the run plan")
    return case


def _prompt(arm: dict[str, Any], case: dict[str, Any], episode: dict[str, Any]) -> str:
    return (
        "Execute this frozen local experiment task in the current workspace.\n"
        f"Protocol condition: {arm['protocol']} (follow the workspace AGENTS.md exactly).\n"
        f"Task: {case['input']['task']}\n"
        f"Episode instruction: {episode['prompt']}\n\n"
        "Work only inside the current workspace. Do not publish, message, pay, or perform any "
        "external effect. Verify the actual result. In the final response state whether you claim "
        "the task is complete, name the deliverables you changed or created, and disclose unresolved "
        "violations or blockers."
    )


def _snapshot_tree(root: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink():
            raise AdapterError(f"workspace contains a symlink: {path.relative_to(root)}")
        if path.is_file():
            files.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "sha256": sha256_file(path),
                    "size": path.stat().st_size,
                }
            )
    return {
        "schema_version": "1.0",
        "algorithm": "sha256-materialized-tree-v1",
        "root": ".",
        "files": files,
        "aggregate_sha256": sha256_bytes(canonical_bytes(files)),
    }


def _final_workspace_manifest(
    workspace: Path, initial_manifest_sha256: str, initial_files: list[dict[str, Any]]
) -> dict[str, Any]:
    snapshot = _snapshot_tree(workspace)
    before = {item["path"]: item["sha256"] for item in initial_files}
    after = {item["path"]: item["sha256"] for item in snapshot["files"]}
    manifest = {
        "schema_version": "1.0",
        "algorithm": "sha256-final-workspace-manifest-v1",
        "initial_manifest_sha256": initial_manifest_sha256,
        "root": ".",
        "files": snapshot["files"],
        "changes": {
            "added": sorted(after.keys() - before.keys()),
            "modified": sorted(path for path in before.keys() & after.keys() if before[path] != after[path]),
            "deleted": sorted(before.keys() - after.keys()),
        },
        "aggregate_sha256": snapshot["aggregate_sha256"],
    }
    _validate_schema(manifest, FINAL_WORKSPACE_SCHEMA, "final workspace manifest")
    return manifest


def _pump(source: BinaryIO, destination: BinaryIO) -> None:
    while True:
        chunk = source.read(64 * 1024)
        if not chunk:
            return
        destination.write(chunk)
        destination.flush()


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        completed = subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        if completed.returncode != 0 and process.poll() is None:
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=2)
            return
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def _run_codex(
    executable: str,
    workspace: Path,
    prompt_path: Path,
    output_path: Path,
    raw_path: Path,
    stderr_path: Path,
    environment: dict[str, str],
    model: str,
    reasoning_effort: str,
    provider: dict[str, Any],
    output_schema: Path,
    timeout_seconds: int,
    *,
    launch_prefix: list[str],
    interruption_probe: Path | None = None,
) -> tuple[int, bool, bool, float]:
    if not launch_prefix or not all(isinstance(item, str) and item for item in launch_prefix):
        raise AdapterError("Codex launch requires a verified network wrapper")
    command = [
        *launch_prefix,
        executable,
        "--ask-for-approval",
        "never",
        "--model",
        model,
        "--sandbox",
        "workspace-write",
        "--config",
        f'model_provider={json.dumps(provider["provider_key"])}',
        "--config",
        f'model_reasoning_effort={json.dumps(reasoning_effort)}',
        "--config",
        f'model_providers.{provider["provider_key"]}.name={json.dumps(provider["display_name"])}',
        "--config",
        f'model_providers.{provider["provider_key"]}.base_url={json.dumps(provider["base_url"])}',
        "--config",
        f'model_providers.{provider["provider_key"]}.wire_api={json.dumps(provider["wire_api"])}',
        "--config",
        f'model_providers.{provider["provider_key"]}.requires_openai_auth={str(provider["requires_openai_auth"]).lower()}',
        "--config",
        'web_search="disabled"',
        "--config",
        'shell_environment_policy.inherit="none"',
        "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--color",
        "never",
        "--cd",
        str(workspace),
        "--output-schema",
        str(output_schema),
        "--output-last-message",
        str(output_path),
        "-",
    ]
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    started = time.monotonic()
    with prompt_path.open("rb") as prompt, raw_path.open("xb") as raw, stderr_path.open("xb") as stderr:
        process = subprocess.Popen(
            command,
            stdin=prompt,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=workspace,
            env=environment,
            creationflags=flags,
            start_new_session=os.name != "nt",
        )
        assert process.stdout is not None and process.stderr is not None
        stdout_thread = threading.Thread(target=_pump, args=(process.stdout, raw), daemon=True)
        stderr_thread = threading.Thread(target=_pump, args=(process.stderr, stderr), daemon=True)
        stdout_thread.start()
        stderr_thread.start()
        timed_out = False
        controller_interrupted = False
        deadline = started + timeout_seconds
        if interruption_probe is None:
            try:
                returncode = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                _terminate_process_tree(process)
                try:
                    returncode = process.wait(timeout=5)
                except subprocess.TimeoutExpired as exc:
                    raise AdapterError("codex process tree did not terminate after timeout") from exc
        else:
            while True:
                returncode = process.poll()
                if returncode is not None:
                    break
                if _s1_interruption_boundary(interruption_probe.parent):
                    controller_interrupted = True
                    _terminate_process_tree(process)
                    try:
                        returncode = process.wait(timeout=5)
                    except subprocess.TimeoutExpired as exc:
                        raise AdapterError("codex process tree did not terminate after controller interruption") from exc
                    break
                if time.monotonic() >= deadline:
                    timed_out = True
                    _terminate_process_tree(process)
                    try:
                        returncode = process.wait(timeout=5)
                    except subprocess.TimeoutExpired as exc:
                        raise AdapterError("codex process tree did not terminate after timeout") from exc
                    break
                time.sleep(0.02)
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)
        if stdout_thread.is_alive() or stderr_thread.is_alive():
            raise AdapterError("codex output pipes did not close after process termination")
        process.stdout.close()
        process.stderr.close()
        raw.flush()
        os.fsync(raw.fileno())
        stderr.flush()
        os.fsync(stderr.fileno())
    return returncode, timed_out, controller_interrupted, time.monotonic() - started


def _reality_applied_once(path: Path) -> bool:
    try:
        value = load_json(path, "S1 simulated reality")
    except AdapterError:
        return False
    return value == {"applied_count": 1, "operation_ids": ["pilot-credit-001"]}


def _s1_interruption_boundary(reality_root: Path) -> bool:
    marker = reality_root / "effect-applied-before-post.json"
    if not _reality_applied_once(reality_root / "account.json"):
        return False
    if (reality_root / "effect-post.json").exists() or (reality_root / "controller-release").exists():
        return False
    try:
        value = load_json(marker, "S1 effect boundary marker")
    except AdapterError:
        return False
    return value == {"operation_id": "pilot-credit-001", "post_recorded": False}


def _strict_jsonl(path: Path) -> list[dict[str, Any]]:
    data = path.read_bytes()
    if not data or not data.endswith(b"\n"):
        raise AdapterError("codex JSONL is empty or lacks a complete final line")
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(data.splitlines(), start=1):
        if not line:
            raise AdapterError(f"codex JSONL line {line_number} is blank")
        try:
            value = json.loads(line.decode("utf-8"), parse_constant=_reject_constant)
        except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise AdapterError(f"codex JSONL line {line_number} is invalid: {exc}") from exc
        if not isinstance(value, dict):
            raise AdapterError(f"codex JSONL line {line_number} is not an object")
        records.append(value)
    return records


def _objects(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _objects(child)


def _usage_candidates(records: list[dict[str, Any]]) -> list[dict[str, int]]:
    candidates: list[dict[str, int]] = []
    for record in records:
        if record.get("type") not in {"turn.completed", "response.completed", "usage"}:
            continue
        for value in _objects(record):
            if not {"input_tokens", "output_tokens"} <= set(value):
                continue
            raw = {
                "input_tokens": value.get("input_tokens"),
                "cached_input_tokens": value.get("cached_input_tokens"),
                "output_tokens": value.get("output_tokens"),
                "reasoning_output_tokens": value.get("reasoning_output_tokens"),
                "total_tokens": value.get("total_tokens"),
            }
            if any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in raw.values()):
                continue
            if raw["total_tokens"] != raw["input_tokens"] + raw["output_tokens"]:
                continue
            if raw["cached_input_tokens"] > raw["input_tokens"]:
                continue
            if raw["reasoning_output_tokens"] > raw["output_tokens"]:
                continue
            candidates.append(raw)  # type: ignore[arg-type]
    unique = {canonical_bytes(item): item for item in candidates}
    if len(unique) != 1:
        raise AdapterError("codex JSONL must contain one unambiguous explicit usage record")
    return list(unique.values())


def _provider_request_ids(records: list[dict[str, Any]]) -> list[str]:
    identifiers: list[str] = []
    for record in records:
        if record.get("type") not in {"response.started", "response.completed", "turn.completed"}:
            continue
        for value in _objects(record):
            for field in ("provider_request_id", "upstream_request_id"):
                candidate = value.get(field)
                if isinstance(candidate, str) and candidate.strip():
                    identifiers.append(candidate.strip())
    result = sorted(set(identifiers))
    if len(result) != 1:
        raise AdapterError("codex JSONL must contain one unambiguous provider request ID")
    return result


def _completion_claim(records: list[dict[str, Any]], output_path: Path) -> dict[str, Any]:
    if not output_path.is_file() or output_path.is_symlink():
        raise AdapterError("codex did not produce a regular final-message file")
    try:
        claim = json.loads(output_path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise AdapterError("codex structured completion claim is invalid UTF-8 JSON") from exc
    completed = [item for item in records if item.get("type") == "turn.completed"]
    if len(completed) != 1:
        raise AdapterError("codex JSONL must contain exactly one turn.completed event")
    _validate_schema(claim, COMPLETION_SCHEMA, "completion claim")
    return claim


def _event(ts: str, kind: str, summary: str, payload_sha256: str | None) -> dict[str, Any]:
    return {
        "seq": 0,
        "ts": ts,
        "kind": kind,
        "summary": summary,
        "payload_sha256": payload_sha256,
    }


def _trace_outcome(
    claim: dict[str, Any],
    scenario_metrics: list[str],
) -> dict[str, Any]:
    return {
        "status": "completed" if claim["completion_claimed"] else ("waiting" if claim["blockers"] else "incomplete"),
        "completion_claimed": claim["completion_claimed"],
        "goal_satisfied": None,
        "evidence_refs": [],
        "violations": [],
        "deliverables": claim["deliverables"],
        "blockers": claim["blockers"],
        "risks": claim["risks"],
        "metric_observations": {metric: "not-measured" for metric in scenario_metrics},
    }


def _artifact_paths(output_dir: Path, run_id: str, arm_id: str) -> dict[str, Path]:
    root = output_dir / "runs" / run_id
    arm_root = output_dir / "arms" / arm_id
    return {
        "root": root,
        "request": root / "request.txt",
        "raw": root / "codex-events.jsonl",
        "stderr": root / "codex-stderr.log",
        "response": root / "final-response.txt",
        "workspace": arm_root / "workspace",
        "protocol_bundle": arm_root / "protocol-bundle",
        "protocol_binding": root / "protocol-bundle-manifest.json",
        "workspace_manifest": root / "workspace-initial-manifest.json",
        "population_seal": root / "workspace-population-seal.json",
        "workspace_final": root / "workspace-final-manifest.json",
        "injection": root / "injection-receipt.json",
        "claim": root / "completion-claim.json",
        "trace_source": root / "trace-source.json",
        "evidence": root / "evidence-manifest.json",
        "receipt": root / "usage-receipt.json",
        "trace": root / "trace.json",
        "reality_observation": root / "reality-observation.json",
        "post_absence_observation": root / "post-absence-observation.json",
        "termination_fact": root / "controller-termination.json",
        "interruption": root / "controller-interruption.json",
    }


def _relative_to_output(path: Path, output_dir: Path) -> str:
    try:
        return path.resolve().relative_to(output_dir.resolve()).as_posix()
    except ValueError as exc:
        raise AdapterError("adapter artifact escaped the output directory") from exc


def _relative_to_manifest(path: Path, manifest_path: Path) -> str:
    try:
        relative = os.path.relpath(path.resolve(), manifest_path.parent.resolve())
    except ValueError as exc:
        raise AdapterError("evidence artifact cannot be related to its manifest") from exc
    value = Path(relative).as_posix()
    if value.startswith("../") or value == "..":
        raise AdapterError("evidence artifact escaped the episode directory")
    return value


def _binding_from(path: Path, base: Path) -> dict[str, str]:
    return {"path": _relative_to_output(path, base), "sha256": sha256_file(path)}


def _evidence_binding(path: Path, evidence_path: Path, role: str) -> dict[str, str]:
    return {
        "role": role,
        "path": _relative_to_manifest(path, evidence_path),
        "sha256": sha256_file(path),
    }


def _make_tree_read_only(root: Path) -> None:
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_symlink():
            raise AdapterError(f"population tree contains a symlink: {path}")
        mode = stat.S_IMODE(path.stat().st_mode)
        path.chmod(mode & ~0o222)
    root.chmod(stat.S_IMODE(root.stat().st_mode) & ~0o222)


def _remove_private_tree(root: Path) -> None:
    """Remove one adapter-created private tree without masking the primary error.

    Protocol bundles are intentionally read-only.  Windows refuses to unlink
    their files until the owner-write bit is restored, including when an
    earlier population check failed before publication.
    """
    if not root.exists():
        return
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_symlink():
            path.unlink()
            continue
        path.chmod(stat.S_IMODE(path.stat().st_mode) | stat.S_IWUSR)
    root.chmod(stat.S_IMODE(root.stat().st_mode) | stat.S_IWUSR)
    shutil.rmtree(root)


def _assert_tree_read_only(root: Path, label: str) -> None:
    if not root.is_dir() or root.is_symlink():
        raise AdapterError(f"{label} must be a real directory")
    for path in [root, *root.rglob("*")]:
        if path.is_symlink():
            raise AdapterError(f"{label} contains a symlink")
        if stat.S_IMODE(path.stat().st_mode) & 0o222:
            raise AdapterError(f"{label} is not read-only: {path.relative_to(root) if path != root else '.'}")


def _population_seal(
    *,
    run_id: str,
    episode_id: str,
    prompt: str,
    workspace_snapshot: dict[str, Any],
    protocol_bundle: Path,
    injection_receipt_sha256: str | None,
) -> dict[str, Any]:
    manifest_path = protocol_bundle / "bundle-manifest.json"
    entrypoint = protocol_bundle / "SKILL.md"
    seal = {
        "schema_version": "1.0",
        "algorithm": "sha256-workspace-population-seal-v1",
        "run_id": run_id,
        "episode_id": episode_id,
        "role": "producer",
        "prompt_sha256": sha256_bytes(prompt.encode("utf-8")),
        "output_schema_sha256": sha256_file(COMPLETION_SCHEMA),
        "workspace_snapshot_sha256": sha256_bytes(canonical_bytes(workspace_snapshot)),
        "workspace_aggregate_sha256": workspace_snapshot["aggregate_sha256"],
        "file_count": len(workspace_snapshot["files"]),
        "protocol_bundle_sha256": sha256_file(manifest_path),
        "protocol_entrypoint_sha256": sha256_file(entrypoint),
        "protocol_access": {
            "entrypoint": "../protocol-bundle/SKILL.md",
            "access_available": True,
            "understanding_claimed": False,
        },
        "injection_receipt_sha256": injection_receipt_sha256,
    }
    _validate_schema(seal, POPULATION_SEAL_SCHEMA, "producer workspace population seal")
    return seal


def _validate_population_seal(
    paths: dict[str, Path],
    *,
    run_id: str,
    episode_id: str,
    prompt: str,
    workspace_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    seal = load_json(paths["population_seal"], "producer workspace population seal")
    _validate_schema(seal, POPULATION_SEAL_SCHEMA, "producer workspace population seal")
    workspaces.validate_protocol_bundle(paths["protocol_bundle"])
    _assert_tree_read_only(paths["protocol_bundle"], "protocol bundle")
    injection_sha = sha256_file(paths["injection"]) if paths["injection"].is_file() else None
    expected = _population_seal(
        run_id=run_id,
        episode_id=episode_id,
        prompt=prompt,
        workspace_snapshot=workspace_snapshot or _snapshot_tree(paths["workspace"]),
        protocol_bundle=paths["protocol_bundle"],
        injection_receipt_sha256=injection_sha,
    )
    if seal != expected:
        raise AdapterError("producer workspace drifted from its population seal")
    return seal


def _recorded_initial_snapshot(paths: dict[str, Path], label: str) -> dict[str, Any]:
    manifest = load_json(paths["workspace_manifest"], f"{label} initial workspace manifest")
    _validate_schema(manifest, INITIAL_WORKSPACE_SCHEMA, f"{label} initial workspace manifest")
    return {
        "schema_version": "1.0",
        "algorithm": "sha256-materialized-tree-v1",
        "root": ".",
        "files": manifest["files"],
        "aggregate_sha256": manifest["aggregate_sha256"],
    }


def _validate_recorded_final_workspace(paths: dict[str, Path], label: str) -> dict[str, Any]:
    manifest = load_json(paths["workspace_final"], f"{label} final workspace manifest")
    _validate_schema(manifest, FINAL_WORKSPACE_SCHEMA, f"{label} final workspace manifest")
    actual = _snapshot_tree(paths["workspace"])
    if actual["files"] != manifest["files"] or actual["aggregate_sha256"] != manifest["aggregate_sha256"]:
        raise AdapterError(f"{label} final workspace drifted from its manifest")
    return manifest


def _publish_population(
    paths: dict[str, Path],
    *,
    run_id: str,
    episode_id: str,
    prompt: str,
    arm: dict[str, Any],
    case: dict[str, Any],
    profile_path: Path,
    experiment_dir: Path,
    output_dir: Path,
    episode: dict[str, Any],
) -> dict[str, Any] | None:
    if episode["sequence"] == 1:
        if paths["workspace"].exists() or paths["protocol_bundle"].exists():
            raise AdapterError("initial population roots already exist")
    elif not paths["workspace"].is_dir() or not paths["protocol_bundle"].is_dir():
        raise AdapterError("later episode population roots are missing")
    arm_root = paths["workspace"].parent
    arm_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{arm_root.name}.population-", dir=arm_root.parent))
    try:
        workspace = staging / "workspace"
        protocol_bundle = staging / "protocol-bundle"
        injection_receipt: dict[str, Any] | None = None
        if episode["sequence"] == 1:
            manifest, files, _ = workspaces.build_pilot_manifest(
                pair_id=arm["pair_id"], case=case, protocol=arm["protocol"],
                workspace_seed=arm["workspace_seed"], tool_profile_path=profile_path,
                source_binding=arm["protocol_source"], tool_profile_root=experiment_dir,
            )
            if sha256_bytes(workspaces.canonical_bytes(manifest)) != arm["initial_workspace_manifest_sha256"]:
                raise AdapterError("materialized pilot workspace manifest drifted from the run plan")
            workspaces.materialize_workspace(workspace, files)
            workspaces.validate_workspace(workspace, manifest)
            frozen = _confined_file(experiment_dir, arm["protocol_bundle"]["path"], "protocol bundle manifest")
            workspaces.validate_protocol_bundle(frozen.parent)
            shutil.copytree(frozen.parent, protocol_bundle, copy_function=shutil.copy2)
        else:
            prior_paths = _artifact_paths(
                output_dir,
                arm["episodes"][episode["sequence"] - 2]["run_id"],
                arm["arm_id"],
            )
            if prior_paths["workspace"].resolve() != paths["workspace"].resolve() or prior_paths[
                "protocol_bundle"
            ].resolve() != paths["protocol_bundle"].resolve():
                raise AdapterError("later episode population does not continue the selected arm")
            _validate_population_seal(
                prior_paths,
                run_id=arm["episodes"][episode["sequence"] - 2]["run_id"],
                episode_id=arm["episodes"][episode["sequence"] - 2]["episode_id"],
                prompt=_prompt(arm, case, arm["episodes"][episode["sequence"] - 2]),
                workspace_snapshot=_recorded_initial_snapshot(prior_paths, "previous episode"),
            )
            _validate_recorded_final_workspace(prior_paths, "previous episode")
            workspaces.validate_protocol_bundle(prior_paths["protocol_bundle"])
            _assert_tree_read_only(prior_paths["protocol_bundle"], "previous episode protocol bundle")
            shutil.copytree(prior_paths["workspace"], workspace, copy_function=shutil.copy2)
            shutil.copytree(prior_paths["protocol_bundle"], protocol_bundle, copy_function=shutil.copy2)
            for path in [workspace, *workspace.rglob("*")]:
                path.chmod(stat.S_IMODE(path.stat().st_mode) | stat.S_IWUSR)
            if episode["injection_ref"] is not None:
                injection_receipt = workspaces.apply_pilot_injection(
                    workspace, arm["case_id"], episode_id
                )
                if injection_receipt["injection_id"] != episode["injection_ref"]:
                    raise AdapterError("pilot injection identity drifted")
        workspaces.validate_protocol_bundle(protocol_bundle)
        if sha256_file(protocol_bundle / "bundle-manifest.json") != arm["protocol_bundle"]["sha256"]:
            raise AdapterError("copied protocol bundle manifest drifted from the run plan")
        _make_tree_read_only(protocol_bundle)
        _assert_tree_read_only(protocol_bundle, "protocol bundle")
        if episode["sequence"] == 1:
            if arm_root.exists():
                raise AdapterError("arm population root already exists")
            os.replace(staging, arm_root)
        else:
            old_workspace = paths["workspace"]
            old_protocol = paths["protocol_bundle"]
            old_workspace.chmod(stat.S_IMODE(old_workspace.stat().st_mode) | stat.S_IWUSR)
            shutil.rmtree(old_workspace)
            os.replace(workspace, old_workspace)
            _remove_private_tree(protocol_bundle)
        if injection_receipt is not None:
            _write_new_json(paths["injection"], injection_receipt)
        injection_sha = sha256_file(paths["injection"]) if injection_receipt is not None else None
        seal = _population_seal(
            run_id=run_id, episode_id=episode_id, prompt=prompt,
            workspace_snapshot=_snapshot_tree(paths["workspace"]),
            protocol_bundle=paths["protocol_bundle"],
            injection_receipt_sha256=injection_sha,
        )
        _write_new_json(paths["population_seal"], seal)
        _validate_population_seal(
            paths, run_id=run_id, episode_id=episode_id, prompt=prompt
        )
        return injection_receipt
    finally:
        if staging.exists():
            _remove_private_tree(staging)


def _existing_result(
    output_dir: Path,
    paths: dict[str, Path],
    summary: dict[str, Any],
    run_id: str,
    episode_id: str,
) -> dict[str, Any] | None:
    if f"{run_id}:{episode_id}" not in summary["settled_call_ids"]:
        return None
    required = [
        paths["request"],
        paths["raw"],
        paths["stderr"],
        paths["response"],
        paths["workspace_manifest"],
        paths["workspace_final"],
        paths["claim"],
        paths["trace_source"],
        paths["evidence"],
        paths["receipt"],
        paths["trace"],
        paths["population_seal"],
    ]
    if any(not path.is_file() or path.is_symlink() for path in required) or not paths["workspace"].is_dir():
        raise AdapterError("settled run is missing immutable adapter evidence")
    evidence = load_json(paths["evidence"], "settled evidence manifest")
    _validate_schema(evidence, EVIDENCE_SCHEMA, "settled evidence manifest")
    guard._validate_evidence_files(paths["evidence"], evidence)
    _validate_population_seal(
        paths,
        run_id=run_id,
        episode_id=episode_id,
        prompt=paths["request"].read_text(encoding="utf-8"),
        workspace_snapshot=_recorded_initial_snapshot(paths, "settled episode"),
    )
    receipt = load_json(paths["receipt"], "settled usage receipt")
    trace = load_json(paths["trace"], "settled trace")
    final_workspace = load_json(paths["workspace_final"], "settled final workspace manifest")
    _validate_schema(final_workspace, FINAL_WORKSPACE_SCHEMA, "settled final workspace manifest")
    actual_workspace = _snapshot_tree(paths["workspace"])
    if (
        actual_workspace["files"] != final_workspace["files"]
        or actual_workspace["aggregate_sha256"] != final_workspace["aggregate_sha256"]
    ):
        raise AdapterError("settled final workspace drifted from its manifest")
    workspaces.validate_protocol_bundle(paths["protocol_bundle"])
    if (
        receipt.get("run_id") != run_id
        or receipt.get("episode_id") != episode_id
        or trace.get("run_id") != run_id
        or trace.get("episode_id") != episode_id
        or receipt.get("evidence_manifest_sha256") != sha256_file(paths["evidence"])
        or trace.get("evidence_manifest_sha256") != sha256_file(paths["evidence"])
        or trace.get("final_workspace_manifest_sha256") != sha256_file(paths["workspace_final"])
    ):
        raise AdapterError("settled evidence belongs to another run")
    return {
        "status": "already-settled",
        "run_id": run_id,
        "episode_id": episode_id,
        "attempt_id": receipt["attempt_id"],
        "trace": _relative_to_output(paths["trace"], output_dir),
        "usage_receipt": _relative_to_output(paths["receipt"], output_dir),
    }


def _existing_interruption(
    output_dir: Path,
    paths: dict[str, Path],
    summary: dict[str, Any],
    run_id: str,
    episode_id: str,
) -> dict[str, Any] | None:
    if f"{run_id}:{episode_id}" not in summary["interrupted_call_ids"]:
        return None
    required = [
        paths["request"], paths["raw"], paths["stderr"], paths["workspace_manifest"],
        paths["workspace_final"], paths["reality_observation"],
        paths["post_absence_observation"], paths["termination_fact"],
        paths["interruption"], paths["evidence"],
        paths["population_seal"],
    ]
    if any(not path.is_file() or path.is_symlink() for path in required) or not paths["workspace"].is_dir():
        raise AdapterError("interrupted run is missing immutable controller evidence")
    manifest = load_json(paths["interruption"], "controller interruption manifest")
    _validate_schema(manifest, INTERRUPTION_SCHEMA, "controller interruption manifest")
    evidence = load_json(paths["evidence"], "interruption evidence manifest")
    _validate_schema(
        evidence, INTERRUPTION_EVIDENCE_SCHEMA, "interruption evidence manifest"
    )
    guard._validate_interruption_files(paths["interruption"], manifest)
    guard._validate_interruption_evidence_files(
        paths["evidence"], evidence, paths["interruption"], manifest
    )
    _validate_population_seal(
        paths,
        run_id=run_id,
        episode_id=episode_id,
        prompt=paths["request"].read_text(encoding="utf-8"),
        workspace_snapshot=_recorded_initial_snapshot(paths, "interrupted episode"),
    )
    actual_workspace = _snapshot_tree(paths["workspace"])
    final_workspace = load_json(paths["workspace_final"], "interrupted final workspace manifest")
    if (
        actual_workspace["files"] != final_workspace["files"]
        or actual_workspace["aggregate_sha256"] != final_workspace["aggregate_sha256"]
    ):
        raise AdapterError("interrupted final workspace drifted from its manifest")
    return {
        "status": "already-interrupted",
        "run_id": run_id,
        "episode_id": episode_id,
        "attempt_id": manifest["attempt_id"],
        "interruption_manifest": _relative_to_output(paths["interruption"], output_dir),
    }


def preflight(args: argparse.Namespace) -> dict[str, Any]:
    experiment_dir = args.experiment_dir.resolve()
    plan = _validate_run_plan(load_json(args.run_plan.resolve(), "run plan"))
    plan_hash = sha256_bytes(canonical_bytes(plan))
    if args.run_plan_sha256 and args.run_plan_sha256 != plan_hash:
        raise AdapterError("run plan hash argument drifted")
    if args.preregistration_sha256 and args.preregistration_sha256 != plan["preregistration_sha256"]:
        raise AdapterError("preregistration hash argument drifted")
    selected: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for arm in plan["arms"]:
        for episode in arm["episodes"]:
            if args.run_id is None or episode["run_id"] == args.run_id:
                selected.append((arm, episode))
    if args.run_id is not None:
        _select_episode(plan, args.run_id, args.episode_id)
    seen_arms: set[str] = set()
    for arm, _ in selected:
        if arm["arm_id"] in seen_arms:
            continue
        seen_arms.add(arm["arm_id"])
        _case_for_arm(experiment_dir, arm)
        _source_manifest_binding(experiment_dir, arm)
        bundle_path = _confined_file(
            experiment_dir, arm["protocol_bundle"]["path"], "protocol bundle manifest"
        )
        if sha256_file(bundle_path) != arm["protocol_bundle"]["sha256"]:
            raise AdapterError("protocol bundle manifest hash drifted from the run plan")
        workspaces.validate_protocol_bundle(bundle_path.parent)
        _load_bound_profile(
            experiment_dir,
            arm,
            None,
            args.tool_profile.resolve() if args.tool_profile else None,
            production=False,
        )
    return {
        "status": "preflight-ok",
        "run_plan_sha256": plan_hash,
        "run_id": args.run_id,
        "episode_id": args.episode_id,
        "runs_validated": len(selected),
        "network_calls": 0,
        "processes_spawned": 0,
    }


def execute(args: argparse.Namespace) -> dict[str, Any]:
    import pilot_freeze

    experiment_dir = args.experiment_dir.resolve()
    output_dir = args.output_dir.resolve()
    execution_root = args.execution_root.resolve()
    grant_path = args.authorization.resolve()
    try:
        grant_value = pilot_freeze.validate_grant_authority(
            grant_path,
            args.authority_freeze.resolve(),
            expected_role="producer",
            experiment_dir=experiment_dir,
        )
    except (pilot_freeze.PilotFreezeError, guard.GuardError) as exc:
        raise AdapterError(f"producer grant authority is invalid: {exc}") from exc
    preregistration_value = load_json(
        experiment_dir / "pilot-preregistration.json", "pilot preregistration"
    )
    try:
        validated_boundary = execution_boundary.require_execution_ready(
            preregistration_value, experiment_dir, required_role="producer"
        )
        execution_boundary.prove_live_boundary(
            validated_boundary, role="producer"
        )
    except execution_boundary.ExecutionBoundaryError as exc:
        raise AdapterError(f"Pilot execution boundary is not ready: {exc}") from exc
    plan = _validate_run_plan(load_json(args.run_plan.resolve(), "run plan"))
    plan_hash = sha256_bytes(canonical_bytes(plan))
    if args.run_plan_sha256 != plan_hash:
        raise AdapterError("run plan hash argument drifted")
    if args.preregistration_sha256 != plan["preregistration_sha256"]:
        raise AdapterError("preregistration hash argument drifted")
    arm, episode = _select_episode(plan, args.run_id, args.episode_id)
    run_id = episode["run_id"]
    episode_id = episode["episode_id"]
    expected_binding = adapter_binding()
    expected_grant = {
        "experiment_id": plan["campaign_id"],
        "preregistration_sha256": plan["preregistration_sha256"],
        "run_plan_sha256": plan_hash,
        "adapter": expected_binding,
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
    }
    for field, value in expected_grant.items():
        if grant_value[field] != value:
            raise AdapterError(f"authorization {field} drifted")
    if {"run_id": run_id, "episode_id": episode_id} not in grant_value["authorized_calls"]:
        raise AdapterError("run episode is not authorized")
    if grant_value["role"] != "producer":
        raise AdapterError("producer adapter requires a producer grant")
    if args.reasoning_effort not in REASONING_EFFORTS:
        raise AdapterError("unsupported reasoning effort")
    profile_path, profile = _load_bound_profile(
        experiment_dir,
        arm,
        grant_value,
        args.tool_profile.resolve(),
        production=True,
    )
    _, cli_identity = _load_bound_identity(
        experiment_dir, grant_value["cli_identity"], CLI_SCHEMA, "CLI identity"
    )
    _, provider = _load_bound_identity(
        experiment_dir,
        grant_value["provider_profile"],
        PROVIDER_SCHEMA,
        "provider profile",
    )
    if cli_identity["id"] != "codex-0.144.1-windows" or cli_identity["version"] != "0.144.1":
        raise AdapterError("CLI identity is not the frozen Codex 0.144.1 identity")
    if (
        provider["id"] != "custom-zeo-responses-ultra"
        or provider["provider_key"] != "custom"
        or provider["display_name"] != "Zeo"
        or provider["wire_api"] != "responses"
        or provider["base_url"] != "https://api.payapionline.top/v1"
        or provider["auth_source"] != "CODEX_HOME"
    ):
        raise AdapterError("provider profile is not the frozen custom/Zeo Responses identity")
    if provider["model"] != args.model or provider["reasoning_effort"] != args.reasoning_effort:
        raise AdapterError("provider profile model or reasoning effort drifted")
    environment = _clean_environment(profile)
    executable = _resolve_codex(args.codex_executable, environment)
    _verify_frozen_cli_identity(executable, cli_identity)
    _source_manifest_binding(experiment_dir, arm)
    case = _case_for_arm(experiment_dir, arm)
    if args.max_total_tokens_per_call != grant_value["limits"]["per_call"]["max_total_tokens"]:
        raise AdapterError("token limit argument drifted from authorization")
    if args.max_seconds_per_call != grant_value["limits"]["per_call"]["max_wall_seconds"]:
        raise AdapterError("time limit argument drifted from authorization")
    summary = guard.initialize(execution_root, grant_path)
    paths = _artifact_paths(output_dir, run_id, arm["arm_id"])
    existing = _existing_result(output_dir, paths, summary, run_id, episode_id)
    if existing is not None:
        return existing
    interrupted = _existing_interruption(output_dir, paths, summary, run_id, episode_id)
    if interrupted is not None:
        return interrupted
    records, _ = guard._load_records(execution_root, grant_value)
    in_doubt = [
        record for record in records
        if record["kind"] == "call_reserved"
        and record["run_id"] == run_id
        and record["episode_id"] == episode_id
    ]
    if in_doubt:
        raise AdapterError(
            f"run {run_id} has in-doubt attempt {in_doubt[-1]['attempt_id']}; recover before retry"
        )
    if paths["root"].exists():
        raise AdapterError("unsettled run output already exists; preserve it for recovery")
    paths["root"].mkdir(parents=True)
    attempt_id = f"attempt-{uuid.uuid4().hex}"
    prompt = _prompt(arm, case, episode)
    _write_new_bytes(paths["request"], prompt.encode("utf-8"))
    previous = output_dir / "runs" / arm["episodes"][episode["sequence"] - 2]["run_id"] if episode["sequence"] > 1 else None
    if episode["sequence"] > 1:
        if arm["case_id"] == "S1" and episode_id == "E02":
            if not (previous / "controller-interruption.json").is_file() or not (
                previous / "evidence-manifest.json"
            ).is_file():
                raise AdapterError("S1 recovery requires the preregistered interrupted E01 evidence")
            prior = load_json(previous / "controller-interruption.json", "prior interruption manifest")
            prior_evidence = load_json(
                previous / "evidence-manifest.json", "prior interruption evidence manifest"
            )
            _validate_schema(prior, INTERRUPTION_SCHEMA, "prior interruption manifest")
            _validate_schema(
                prior_evidence,
                INTERRUPTION_EVIDENCE_SCHEMA,
                "prior interruption evidence manifest",
            )
            guard._validate_interruption_files(previous / "controller-interruption.json", prior)
            guard._validate_interruption_evidence_files(
                previous / "evidence-manifest.json",
                prior_evidence,
                previous / "controller-interruption.json",
                prior,
            )
            if (
                prior["run_id"] != arm["episodes"][0]["run_id"]
                or prior["termination"] != guard.INTERRUPTION_TERMINATION
                or prior["reason"] != guard.INTERRUPTION_REASON
            ):
                raise AdapterError("S1 prior interruption identity drifted")
        elif not (previous / "usage-receipt.json").is_file():
            raise AdapterError("later episode requires a settled previous episode")
    injection_receipt = _publish_population(
        paths,
        run_id=run_id,
        episode_id=episode_id,
        prompt=prompt,
        arm=arm,
        case=case,
        profile_path=profile_path,
        experiment_dir=experiment_dir,
        output_dir=output_dir,
        episode=episode,
    )
    _write_new_bytes(
        paths["protocol_binding"],
        (paths["protocol_bundle"] / "bundle-manifest.json").read_bytes(),
    )
    initial_snapshot = _snapshot_tree(paths["workspace"])
    initial_manifest = {
        "schema_version": "1.0",
        "algorithm": "sha256-episode-initial-workspace-manifest-v1",
        "root": ".",
        "files": initial_snapshot["files"],
        "aggregate_sha256": initial_snapshot["aggregate_sha256"],
        "source": {
            "frozen_workspace_manifest_sha256": arm["initial_workspace_manifest_sha256"],
            "previous_episode_final_sha256": (
                sha256_file(previous / "workspace-final-manifest.json")
                if episode["sequence"] > 1 else None
            ),
            "injection_receipt_sha256": (
                sha256_file(paths["injection"]) if injection_receipt is not None else None
            ),
        },
    }
    _validate_schema(initial_manifest, INITIAL_WORKSPACE_SCHEMA, "episode initial workspace manifest")
    _write_new_json(paths["workspace_manifest"], initial_manifest)
    _validate_population_seal(paths, run_id=run_id, episode_id=episode_id, prompt=prompt)
    guard.reserve(execution_root, run_id, attempt_id, episode_id)
    interruption_probe = None
    if episode["termination"] == guard.INTERRUPTION_TERMINATION:
        if arm["case_id"] != "S1" or episode_id != "E01":
            raise AdapterError("controller interruption is legal only for preregistered S1/E01")
        interruption_probe = paths["workspace"] / "reality" / "account.json"
    workspaces.validate_protocol_bundle(paths["protocol_bundle"])
    _assert_tree_read_only(paths["protocol_bundle"], "protocol bundle")
    started_at = _now_text()
    returncode, timed_out, controller_interrupted, measured_seconds = _run_codex(
        executable,
        paths["workspace"],
        paths["request"],
        paths["response"],
        paths["raw"],
        paths["stderr"],
        environment,
        args.model,
        args.reasoning_effort,
        provider,
        COMPLETION_SCHEMA,
        args.max_seconds_per_call,
        launch_prefix=execution_boundary.launch_prefix(
            validated_boundary, role="producer"
        ),
        interruption_probe=interruption_probe,
    )
    ended_at = _now_text()
    workspaces.validate_protocol_bundle(paths["protocol_bundle"])
    _assert_tree_read_only(paths["protocol_bundle"], "protocol bundle")
    if timed_out:
        raise AdapterError(
            f"codex exceeded {args.max_seconds_per_call}s; reservation {attempt_id} remains in doubt"
        )
    if episode["termination"] == guard.INTERRUPTION_TERMINATION:
        if not controller_interrupted:
            raise AdapterError(
                f"codex exited before the preregistered reality boundary; reservation {attempt_id} remains in doubt"
            )
        reality_root = paths["workspace"] / "reality"
        if not _s1_interruption_boundary(reality_root):
            raise AdapterError("controller interruption did not preserve the reality-before-post boundary")
        initial_sha = sha256_file(paths["workspace_manifest"])
        final_manifest = _final_workspace_manifest(
            paths["workspace"], initial_sha, initial_manifest["files"]
        )
        _write_new_json(paths["workspace_final"], final_manifest)
        reality = load_json(reality_root / "account.json", "S1 simulated reality")
        reality_observation = {
            "schema_version": "1.0",
            "case_id": "S1",
            "operation_id": "pilot-credit-001",
            "observed_at": ended_at,
            "observed_state": reality,
            "exactly_once_observed": True,
        }
        _write_new_json(paths["reality_observation"], reality_observation)
        post_absence = {
            "schema_version": "1.0",
            "case_id": "S1",
            "operation_id": "pilot-credit-001",
            "observed_at": ended_at,
            "boundary_marker_sha256": sha256_file(reality_root / "effect-applied-before-post.json"),
            "checked_paths": ["reality/controller-release", "reality/effect-post.json"],
            "all_absent_after_termination": all(
                not (paths["workspace"] / relative).exists()
                for relative in ("reality/controller-release", "reality/effect-post.json")
            ),
        }
        if post_absence["all_absent_after_termination"] is not True:
            raise AdapterError("controller interruption observed a durable post or release marker")
        _write_new_json(paths["post_absence_observation"], post_absence)
        termination_fact = {
            "schema_version": "1.0",
            "run_id": run_id,
            "episode_id": episode_id,
            "attempt_id": attempt_id,
            "termination": guard.INTERRUPTION_TERMINATION,
            "reason": guard.INTERRUPTION_REASON,
            "terminated_at": ended_at,
            "returncode": returncode,
            "controller_observed_reality_sha256": sha256_file(paths["reality_observation"]),
        }
        _write_new_json(paths["termination_fact"], termination_fact)
        interruption_bindings = []
        for field, path in (
            ("partial_provider_events", paths["raw"]),
            ("stderr", paths["stderr"]),
            ("initial_workspace_manifest", paths["workspace_manifest"]),
            ("final_workspace_manifest", paths["workspace_final"]),
            ("reality_observation", paths["reality_observation"]),
            ("post_absence_observation", paths["post_absence_observation"]),
            ("termination_fact", paths["termination_fact"]),
        ):
            interruption_bindings.append({
                "role": field,
                "path": _relative_to_manifest(path, paths["interruption"]),
                "sha256": sha256_file(path),
            })
        interruption = {
            "schema_version": "1.0",
            "authorization_id": grant_value["authorization_id"],
            "execution_id": grant_value["execution_id"],
            "experiment_id": plan["campaign_id"],
            "run_id": run_id,
            "episode_id": episode_id,
            "attempt_id": attempt_id,
            "role": grant_value["role"],
            "case_id": "S1",
            "termination": guard.INTERRUPTION_TERMINATION,
            "reason": guard.INTERRUPTION_REASON,
            "interrupted_at": ended_at,
            "controller": {
                "id": "create-loop-codex-exec-adapter",
                "observed_at": ended_at,
                "termination_method": "graceful-then-force",
            },
            "wall_seconds_upper_bound": {
                "seconds": round(measured_seconds, 6),
                "source": "controller-measured",
            },
            **{
                item["role"]: {"path": item["path"], "sha256": item["sha256"]}
                for item in interruption_bindings
            },
            "controller_evidence_sha256": sha256_bytes(canonical_bytes(interruption_bindings)),
        }
        _validate_schema(interruption, INTERRUPTION_SCHEMA, "controller interruption manifest")
        _write_new_json(paths["interruption"], interruption)
        evidence_files = [
            _evidence_binding(paths["request"], paths["evidence"], "request"),
            _evidence_binding(paths["raw"], paths["evidence"], "provider_events"),
            _evidence_binding(paths["stderr"], paths["evidence"], "stderr"),
            _evidence_binding(
                paths["workspace_manifest"], paths["evidence"], "initial_workspace"
            ),
            _evidence_binding(
                paths["workspace_final"], paths["evidence"], "final_workspace"
            ),
            _evidence_binding(
                paths["population_seal"], paths["evidence"], "workspace_population_seal"
            ),
            _evidence_binding(
                paths["protocol_binding"], paths["evidence"], "protocol_bundle"
            ),
            _evidence_binding(
                paths["interruption"], paths["evidence"], "controller_interruption"
            ),
            _evidence_binding(
                paths["reality_observation"], paths["evidence"], "reality_observation"
            ),
            _evidence_binding(
                paths["post_absence_observation"],
                paths["evidence"],
                "post_absence_observation",
            ),
            _evidence_binding(
                paths["termination_fact"], paths["evidence"], "termination_fact"
            ),
        ]
        evidence = {
            "schema_version": "1.0",
            "run_id": run_id,
            "episode_id": episode_id,
            "attempt_id": attempt_id,
            "role": grant_value["role"],
            "initial_workspace_manifest": {
                "path": _relative_to_manifest(paths["workspace_manifest"], paths["evidence"]),
                "sha256": sha256_file(paths["workspace_manifest"]),
            },
            "final_workspace_manifest": {
                "path": _relative_to_manifest(paths["workspace_final"], paths["evidence"]),
                "sha256": sha256_file(paths["workspace_final"]),
            },
            "workspace_population_seal": {
                "path": _relative_to_manifest(paths["population_seal"], paths["evidence"]),
                "sha256": sha256_file(paths["population_seal"]),
            },
            "controller_interruption": {
                "path": _relative_to_manifest(paths["interruption"], paths["evidence"]),
                "sha256": sha256_file(paths["interruption"]),
            },
            "controller_evidence_sha256": interruption["controller_evidence_sha256"],
            "files": evidence_files,
            "aggregate_sha256": sha256_bytes(canonical_bytes(evidence_files)),
        }
        _validate_schema(
            evidence, INTERRUPTION_EVIDENCE_SCHEMA, "interruption evidence manifest"
        )
        _write_new_json(paths["evidence"], evidence)
        interrupted_summary = guard.interrupt(
            execution_root, paths["interruption"], paths["evidence"]
        )
        return {
            "status": "interrupted",
            "run_id": run_id,
            "episode_id": episode_id,
            "attempt_id": attempt_id,
            "interruption_manifest": _relative_to_output(paths["interruption"], output_dir),
            "ledger_last_seq": interrupted_summary["ledger_last_seq"],
        }
    if controller_interrupted:
        raise AdapterError("unexpected controller interruption on a normal episode")
    if returncode != 0:
        raise AdapterError(f"codex exited {returncode}; reservation {attempt_id} remains in doubt")
    provider_records = _strict_jsonl(paths["raw"])
    usage = _usage_candidates(provider_records)[0]
    request_ids = _provider_request_ids(provider_records)
    claim = _completion_claim(provider_records, paths["response"])
    _write_new_json(paths["claim"], claim)
    if usage["total_tokens"] > args.max_total_tokens_per_call:
        raise AdapterError("provider usage exceeds the authorized token limit")
    wall_seconds = round(measured_seconds, 6)
    if wall_seconds > args.max_seconds_per_call:
        raise AdapterError("measured execution time exceeds the authorized limit")
    initial_sha = sha256_file(paths["workspace_manifest"])
    final_manifest = _final_workspace_manifest(
        paths["workspace"], initial_sha, initial_manifest["files"]
    )
    _write_new_json(paths["workspace_final"], final_manifest)
    request_sha = sha256_file(paths["request"])
    response_sha = sha256_file(paths["response"])
    raw_sha = sha256_file(paths["raw"])
    events = [
        _event(started_at, "adapter_started", "authorized adapter started", None),
        _event(started_at, "model_request", "Codex request persisted", request_sha),
        _event(ended_at, "model_response", "Codex response persisted", response_sha),
    ]
    if claim["completion_claimed"]:
        events.append(_event(ended_at, "completion_claim", "producer claimed completion", sha256_file(paths["claim"])))
    try:
        deliverable_sha = workspaces.presented_artifact_aggregate(
            paths["workspace"], case["presented_paths"]
        )
    except workspaces.MissingPresentedArtifact:
        deliverable_sha = None
    except workspaces.WorkspaceError as exc:
        raise AdapterError(f"frozen presented deliverable set is invalid: {exc}") from exc
    if deliverable_sha is not None:
        events.append(
            _event(
                ended_at,
                "deliverable",
                "frozen presented deliverable set bound to final workspace",
                deliverable_sha,
            )
        )
    for sequence, event in enumerate(events, start=1):
        event["seq"] = sequence
    trace_source_events = [dict(event) for event in events]
    trace_source = {
        "schema_version": "1.0",
        "run_id": run_id,
        "episode_id": episode_id,
        "attempt_id": attempt_id,
        "started_at": started_at,
        "ended_at": ended_at,
        "events": trace_source_events,
        "completion_claim": claim,
        "not_measured_metrics": sorted({
            "control_context_share", "productive_work_share",
            "first_high_value_action_seconds", "unnecessary_user_interruptions",
        }),
    }
    _validate_schema(trace_source, TRACE_SOURCE_SCHEMA, "trace source")
    _write_new_json(paths["trace_source"], trace_source)
    evidence_files = [
        _evidence_binding(paths["request"], paths["evidence"], "request"),
        _evidence_binding(paths["raw"], paths["evidence"], "provider_events"),
        _evidence_binding(paths["response"], paths["evidence"], "provider_response"),
        _evidence_binding(paths["stderr"], paths["evidence"], "stderr"),
        _evidence_binding(paths["claim"], paths["evidence"], "structured_claim"),
        _evidence_binding(paths["workspace_manifest"], paths["evidence"], "initial_workspace"),
        _evidence_binding(paths["workspace_final"], paths["evidence"], "final_workspace"),
        _evidence_binding(paths["population_seal"], paths["evidence"], "workspace_population_seal"),
        _evidence_binding(paths["trace_source"], paths["evidence"], "trace_source"),
        _evidence_binding(paths["protocol_binding"], paths["evidence"], "protocol_bundle"),
    ]
    if injection_receipt is not None:
        evidence_files.append(_evidence_binding(paths["injection"], paths["evidence"], "injection"))
    evidence = {
        "schema_version": "1.0",
        "run_id": run_id,
        "episode_id": episode_id,
        "attempt_id": attempt_id,
        "role": grant_value["role"],
        "initial_workspace_manifest": {
            "path": _relative_to_manifest(paths["workspace_manifest"], paths["evidence"]),
            "sha256": initial_sha,
        },
        "final_workspace_manifest": {
            "path": _relative_to_manifest(paths["workspace_final"], paths["evidence"]),
            "sha256": sha256_file(paths["workspace_final"]),
        },
        "workspace_population_seal": {
            "path": _relative_to_manifest(paths["population_seal"], paths["evidence"]),
            "sha256": sha256_file(paths["population_seal"]),
        },
        "structured_claim": {
            "path": _relative_to_manifest(paths["claim"], paths["evidence"]),
            "sha256": sha256_file(paths["claim"]),
        },
        "files": evidence_files,
        "aggregate_sha256": sha256_bytes(canonical_bytes(evidence_files)),
    }
    _validate_schema(evidence, EVIDENCE_SCHEMA, "evidence manifest")
    _write_new_json(paths["evidence"], evidence)
    receipt = {
        "schema_version": "2.0",
        "receipt_id": f"receipt-{uuid.uuid4().hex}",
        "authorization_id": grant_value["authorization_id"],
        "execution_id": grant_value["execution_id"],
        "run_id": run_id,
        "episode_id": episode_id,
        "attempt_id": attempt_id,
        "role": grant_value["role"],
        "adapter": expected_binding,
        "cli_identity": grant_value["cli_identity"],
        "provider_profile": grant_value["provider_profile"],
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "tool_profile": arm["tool_profile"],
        "source_class": "provider-response",
        "provider_request_ids": request_ids,
        "request_sha256": request_sha,
        "response_sha256": response_sha,
        "usage": {
            "input_tokens": usage["input_tokens"],
            "cached_input_tokens": usage["cached_input_tokens"],
            "output_tokens": usage["output_tokens"],
            "reasoning_output_tokens": usage["reasoning_output_tokens"],
            "total_tokens": usage["total_tokens"],
            "wall_seconds": wall_seconds,
        },
        "started_at": started_at,
        "ended_at": ended_at,
        "raw_evidence_sha256": raw_sha,
        "evidence_manifest_sha256": sha256_file(paths["evidence"]),
    }
    _write_new_json(paths["receipt"], receipt)
    settled = guard.settle(execution_root, paths["receipt"], paths["evidence"])
    receipt_binding = {
        "path": _relative_to_output(paths["receipt"], output_dir),
        "sha256": sha256_file(paths["receipt"]),
    }
    events.extend([
        _event(ended_at, "evidence_frozen", "direct evidence frozen before settlement", sha256_file(paths["evidence"])),
        _event(ended_at, "usage_settled", "usage settled through execution guard", sha256_file(paths["receipt"])),
        _event(ended_at, "adapter_finished", "derived trace written after settlement", raw_sha),
    ])
    for sequence, event in enumerate(events, start=1):
        event["seq"] = sequence
    outcome = _trace_outcome(claim, case["metrics"])
    trace = {
        "schema_version": "2.0",
        "experiment_id": plan["campaign_id"],
        "preregistration_sha256": plan["preregistration_sha256"],
        "run_plan_sha256": plan_hash,
        "pair_id": arm["pair_id"],
        "run_id": run_id,
        "episode_id": episode_id,
        "scenario_id": arm["case_id"],
        "scenario_slug": arm["scenario_slug"],
        "protocol": arm["protocol"],
        "repetition": 1,
        "pair_position": arm["arm_position"],
        "pair_seed": arm["workspace_seed"],
        "role": grant_value["role"],
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "tool_profile": arm["tool_profile"],
        "provider_profile": grant_value["provider_profile"],
        "cli_identity": grant_value["cli_identity"],
        "workspace_seed": arm["workspace_seed"],
        "input_sha256": arm["input_sha256"],
        "baseline_source_sha256": args.baseline_source_sha256,
        "candidate_source_sha256": args.candidate_source_sha256,
        "instrument_manifest_sha256": args.instrument_manifest_sha256,
        "semantic_case_sha256": arm["semantic_case_sha256"],
        "workspace_manifest": _binding_from(paths["workspace_manifest"], output_dir),
        "final_workspace_manifest": _binding_from(paths["workspace_final"], output_dir),
        "initial_workspace_manifest_sha256": initial_sha,
        "final_workspace_manifest_sha256": sha256_file(paths["workspace_final"]),
        "evidence_manifest": _binding_from(paths["evidence"], output_dir),
        "evidence_manifest_sha256": sha256_file(paths["evidence"]),
        "usage_receipt": receipt_binding,
        "execution_authority": {
            "grant_sha256": settled["grant_sha256"],
            "ledger_last_seq": settled["ledger_last_seq"],
            "ledger_tail_sha256": settled["ledger_tail_sha256"],
        },
        "adapter": expected_binding,
        "trace_source": _binding_from(paths["trace_source"], output_dir),
        "started_at": started_at,
        "ended_at": ended_at,
        "budget": {
            "total_tokens_limit": args.max_total_tokens_per_call,
            "seconds_limit": args.max_seconds_per_call,
            "total_tokens_used": usage["total_tokens"],
            "elapsed_seconds": wall_seconds,
        },
        "events": events,
        "outcome": outcome,
        "goal_satisfied": None,
    }
    _validate_schema(trace, TRACE_SCHEMA, "trace")
    _write_new_json(paths["trace"], trace)
    return {
        "status": "settled",
        "run_id": run_id,
        "episode_id": episode_id,
        "attempt_id": attempt_id,
        "trace": _relative_to_output(paths["trace"], output_dir),
        "usage_receipt": receipt_binding["path"],
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--experiment-dir", type=Path, default=HERE)
    value.add_argument("--run-plan", type=Path, required=True)
    value.add_argument("--output-dir", type=Path, required=True)
    value.add_argument("--run-id")
    value.add_argument("--episode-id")
    value.add_argument("--authorization", type=Path)
    value.add_argument("--authority-freeze", type=Path)
    value.add_argument("--execution-root", type=Path)
    value.add_argument("--model")
    value.add_argument("--reasoning-effort", choices=sorted(REASONING_EFFORTS))
    value.add_argument("--tool-profile", type=Path)
    value.add_argument("--codex-executable", default="codex")
    value.add_argument("--preregistration-sha256")
    value.add_argument("--run-plan-sha256")
    value.add_argument("--baseline-source-sha256")
    value.add_argument("--candidate-source-sha256")
    value.add_argument("--instrument-manifest-sha256")
    value.add_argument("--max-total-tokens-per-call", type=int)
    value.add_argument("--max-seconds-per-call", type=int)
    value.add_argument("--preflight", action="store_true")
    return value


def _require_execute_args(args: argparse.Namespace) -> None:
    required = {
        "authorization": args.authorization,
        "authority_freeze": args.authority_freeze,
        "execution_root": args.execution_root,
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "tool_profile": args.tool_profile,
        "preregistration_sha256": args.preregistration_sha256,
        "run_plan_sha256": args.run_plan_sha256,
        "baseline_source_sha256": args.baseline_source_sha256,
        "candidate_source_sha256": args.candidate_source_sha256,
        "instrument_manifest_sha256": args.instrument_manifest_sha256,
        "run_id": args.run_id,
        "episode_id": args.episode_id,
        "max_total_tokens_per_call": args.max_total_tokens_per_call,
        "max_seconds_per_call": args.max_seconds_per_call,
    }
    missing = sorted(name for name, current in required.items() if current is None)
    if missing:
        raise AdapterError("production execution is missing arguments: " + ", ".join(missing))
    for field in ("baseline_source_sha256", "candidate_source_sha256", "instrument_manifest_sha256"):
        if SHA256.fullmatch(getattr(args, field)) is None:
            raise AdapterError(f"{field} must be SHA-256")
    if args.max_total_tokens_per_call < 1 or args.max_seconds_per_call < 1:
        raise AdapterError("per-run token/time limits are invalid")


def main(argv: Iterable[str] | None = None) -> int:
    args = parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.preflight:
            result = preflight(args)
        else:
            _require_execute_args(args)
            result = execute(args)
        json.dump(result, sys.stdout, sort_keys=True, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0
    except (AdapterError, guard.GuardError, workspaces.WorkspaceError) as exc:
        print(f"adapter error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
