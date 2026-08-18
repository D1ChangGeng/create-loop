#!/usr/bin/env python3
"""Validate, plan, or delegate one frozen real-task pilot episode.

All commands are offline except ``execute``. Execution remains one episode at a
time and requires both the explicit ``--execute`` flag and an external immutable
authorization grant. This module never creates grants and never calls Codex
directly; it delegates to the separately frozen adapter.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable


HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from schema_runtime import SchemaError, check_schema, validate  # noqa: E402

import snapshot_tools as snapshots  # noqa: E402
import workspace_builder as workspaces  # noqa: E402
import network_execution_boundary as execution_boundary  # noqa: E402


PREREGISTRATION = HERE / "pilot-preregistration.json"
PREREGISTRATION_SCHEMA = HERE / "pilot-preregistration.schema.json"
RUN_PLAN = HERE / "pilot-run-plan.json"
RUN_PLAN_SCHEMA = HERE / "pilot-run-plan.schema.json"
SCENARIOS = HERE / "pilot-scenarios.json"
EVALUATOR = HERE / "pilot-evaluator-manifest.json"
ADAPTER = HERE / "codex_exec_adapter.py"
CASE_ORDER = ("N0", "T2", "T3", "T5", "S1", "T7")
EXPECTED_PROTOCOL_ORDER = {
    "N0": ("v1", "v2"),
    "T2": ("v2", "v1"),
    "T3": ("v1", "v2"),
    "T5": ("v2", "v1"),
    "S1": ("v1", "v2"),
    "T7": ("v2", "v1"),
}


class PilotError(RuntimeError):
    """A frozen pilot identity or execution boundary failed."""


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
        raise PilotError(f"value is not strict canonical JSON: {exc}") from exc


def sha256_file(path: Path) -> str:
    return snapshots.sha256_file(path)


def sha256_bytes(value: bytes) -> str:
    return snapshots.sha256_bytes(value)


def load_json(path: Path, label: str) -> Any:
    try:
        return snapshots.load_json(path)
    except snapshots.SnapshotError as exc:
        raise PilotError(f"cannot load {label}: {exc}") from exc


def validate_schema(instance: Any, schema_path: Path, label: str) -> None:
    schema = load_json(schema_path, f"{label} schema")
    try:
        check_schema(schema)
        errors = validate(instance, schema)
    except SchemaError as exc:
        raise PilotError(f"{label} schema is unsupported: {exc}") from exc
    if errors:
        raise PilotError(f"{label} schema validation failed: {'; '.join(errors)}")


def _bound_file(root: Path, binding: dict[str, Any], label: str) -> Path:
    relative = binding.get("path")
    if not isinstance(relative, str):
        raise PilotError(f"{label} path is invalid")
    if Path(relative).is_absolute() or "\\" in relative or ".." in Path(relative).parts:
        raise PilotError(f"{label} path is unsafe")
    path = root.joinpath(*relative.split("/")).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise PilotError(f"{label} escapes the experiment root") from exc
    if not path.is_file() or path.is_symlink():
        raise PilotError(f"{label} is not a regular frozen file")
    if sha256_file(path) != binding.get("sha256"):
        raise PilotError(f"{label} hash drifted")
    return path


def _load_bound_identity(
    root: Path,
    binding: dict[str, Any],
    label: str,
    schema_name: str,
) -> dict[str, Any]:
    path = _bound_file(root, binding, label)
    value = load_json(path, label)
    validate_schema(value, root / schema_name, label)
    if value.get("id") != binding.get("id"):
        raise PilotError(f"{label} ID drifted")
    return value


def _validate_budget_and_policy(preregistration: dict[str, Any]) -> None:
    hard = preregistration["budgets"]["hard"]
    pilot = preregistration["budgets"]["pilot"]
    if hard != {"max_calls": 126, "max_total_tokens": 7_560_000, "max_wall_seconds": 113_400}:
        raise PilotError("hard call/token/time budget drifted")
    if pilot != {
        "max_calls": 23,
        "max_total_tokens": 1_330_000,
        "max_wall_seconds": 20_100,
        "calibration_max_total_tokens": 10_000,
        "calibration_max_wall_seconds": 300,
    }:
        raise PilotError("pilot call/token/time budget drifted")
    policy = preregistration["measurement_policy"]
    if policy["usd_cost"] != "not-measured":
        raise PilotError("USD cost must remain not-measured")
    encoded = canonical_bytes(preregistration).lower()
    forbidden = (b"cost_usd", b"usd_budget", b"billable_tokens", b"pricing")
    if any(token in encoded for token in forbidden):
        raise PilotError("pilot preregistration contains a forbidden pricing or billable-token field")
    if preregistration["formal_execution_enabled"] is not False:
        raise PilotError("formal_execution_enabled must remain false")
    formal = preregistration["formal_experiment"]
    if formal["execution_enabled"] is not False or formal["independent_real_task_claim"] is not False:
        raise PilotError("legacy formal shell must remain disabled and cannot claim independent real tasks")


def load_and_validate_preregistration(
    experiment_dir: Path = HERE,
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = experiment_dir.resolve()
    preregistration = load_json(root / "pilot-preregistration.json", "pilot preregistration")
    validate_schema(preregistration, root / "pilot-preregistration.schema.json", "pilot preregistration")
    _validate_budget_and_policy(preregistration)

    scenarios_path = _bound_file(root, preregistration["scenario_manifest"], "pilot scenarios")
    scenarios = load_json(scenarios_path, "pilot scenarios")
    validate_schema(scenarios, root / "pilot-scenarios.schema.json", "pilot scenarios")
    evaluator_path = _bound_file(root, preregistration["evaluator_manifest"], "pilot evaluator")
    evaluator = load_json(evaluator_path, "pilot evaluator")
    validate_schema(evaluator, root / "pilot-evaluator-manifest.schema.json", "pilot evaluator")
    instrument_binding = preregistration["instrument_manifest"]
    instrument_path = root / instrument_binding["path"]
    if instrument_path.resolve() != (root / "instrument-manifest.json").resolve() or not instrument_path.is_file():
        raise PilotError("instrument manifest path drifted")
    instrument = load_json(instrument_path, "instrument manifest")
    try:
        snapshots.validate_instrument_manifest(
            root,
            instrument,
            expected_inputs=snapshots.EXPERIMENT_INSTRUMENT_INPUTS,
        )
    except snapshots.SnapshotError as exc:
        raise PilotError(f"instrument manifest is invalid: {exc}") from exc

    provider = _load_bound_identity(
        root,
        preregistration["provider"],
        "provider profile",
        "provider-profile.schema.json",
    )
    identities = preregistration["cli_identities"]
    if identities["calibration_reuses"] != "producer":
        raise PilotError("calibration must reuse the producer CLI identity")
    producer_slot = identities["producer"]
    reviewer_slot = identities["reviewer"]
    if producer_slot["status"] != "frozen" or producer_slot["binding"] is None:
        raise PilotError("producer CLI identity is unresolved")
    cli = _load_bound_identity(
        root,
        producer_slot["binding"],
        "producer CLI identity",
        "cli-identity.schema.json",
    )
    profile = _load_bound_identity(
        root,
        preregistration["execution"]["tool_profile"],
        "tool profile",
        "tool-profile.schema.json",
    )
    adapter = _bound_file(root, preregistration["execution"]["adapter"], "Codex adapter")
    if adapter.resolve() != (root / "codex_exec_adapter.py").resolve():
        raise PilotError("pilot preregistration must bind codex_exec_adapter.py")
    if (
        provider["provider_key"] != "custom"
        or provider["display_name"] != "Zeo"
        or provider["wire_api"] != "responses"
        or provider["base_url"] != "https://api.payapionline.top/v1"
        or provider["auth_source"] != "CODEX_HOME"
        or provider["model"] != "gpt-5.6-sol"
        or provider["reasoning_effort"] != "ultra"
    ):
        raise PilotError("provider identity drifted from custom/Zeo Responses ultra")
    if (
        cli["version"] != "0.144.1"
        or cli.get("platform", "windows") != "windows"
        or cli.get("native_executable_sha256")
        != "cbacbb9726262ef558b4af0438a1b2a5bba9076132401d947b5b4d2bf92ab0e4"
    ):
        raise PilotError("producer Codex CLI identity drifted")
    if reviewer_slot["status"] == "frozen" and reviewer_slot["binding"] is not None:
        reviewer_cli = _load_bound_identity(
            root,
            reviewer_slot["binding"],
            "reviewer CLI identity",
            "cli-identity.schema.json",
        )
        if reviewer_cli["version"] != "0.144.1" or reviewer_cli.get("platform") != "linux":
            raise PilotError("reviewer Codex CLI identity drifted")
    if profile["id"] != "provider-workspace-no-publish":
        raise PilotError("pilot tool profile drifted")
    if scenarios["campaign_id"] != preregistration["campaign_id"] or evaluator["campaign_id"] != preregistration["campaign_id"]:
        raise PilotError("pilot campaign identity drifted")
    return preregistration, scenarios


def execution_status(preregistration: dict[str, Any], experiment_dir: Path) -> dict[str, Any]:
    blockers = execution_boundary.inspect_execution_blockers(preregistration, experiment_dir)
    return {"execution_blocked": bool(blockers), "blockers": blockers}


def _protocol_bundle_binding(experiment_dir: Path, protocol: str) -> dict[str, str]:
    path = experiment_dir / "protocol-bundles" / protocol / "bundle-manifest.json"
    if not path.is_file() or path.is_symlink():
        raise PilotError(f"frozen {protocol} protocol bundle manifest is missing")
    manifest = load_json(path, f"{protocol} protocol bundle")
    validate_schema(manifest, experiment_dir / "protocol-bundle-manifest.schema.json", f"{protocol} protocol bundle")
    if manifest["protocol"] != protocol:
        raise PilotError(f"{protocol} protocol bundle identity drifted")
    return {
        "path": path.relative_to(experiment_dir).as_posix(),
        "sha256": sha256_file(path),
    }


def build_run_plan(
    preregistration: dict[str, Any],
    scenarios: dict[str, Any],
    *,
    experiment_dir: Path = HERE,
) -> dict[str, Any]:
    preregistration_sha256 = sha256_bytes(canonical_bytes(preregistration))
    cases = scenarios["cases"]
    if [case["case_id"] for case in cases] != list(CASE_ORDER):
        raise PilotError("pilot cases must be ordered N0/T2/T3/T5/S1/T7")
    arms: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    pair_semantics: dict[str, str] = {}
    for case_index, case in enumerate(cases, start=1):
        case_id = case["case_id"]
        protocol_order = tuple(case["protocol_order"])
        if protocol_order != EXPECTED_PROTOCOL_ORDER[case_id]:
            raise PilotError(f"pilot case {case_id} protocol order drifted")
        workspace_seed = preregistration["execution"]["workspace_seed"] + case_index
        for arm_position, protocol in enumerate(protocol_order, start=1):
            try:
                manifest, _, _ = workspaces.build_pilot_manifest(
                    pair_id=case["pair_id"],
                    case=case,
                    protocol=protocol,
                    workspace_seed=workspace_seed,
                    source_binding=preregistration[
                        "baseline" if protocol == "v1" else "candidate"
                    ],
                    tool_profile_path=experiment_dir / preregistration["execution"]["tool_profile"]["path"],
                    tool_profile_root=experiment_dir,
                )
            except workspaces.WorkspaceError as exc:
                raise PilotError(f"cannot build pilot workspace contract for {case_id}/{protocol}: {exc}") from exc
            source_key = "baseline" if protocol == "v1" else "candidate"
            source_binding = preregistration[source_key]
            manifest["protocol_source"] = {
                "protocol": protocol,
                "aggregate_sha256": source_binding["aggregate_sha256"],
                "manifest": source_binding["manifest"],
            }
            manifest["protocol_bundle"]["source_aggregate_sha256"] = source_binding["aggregate_sha256"]
            semantic = manifest["semantic_case_sha256"]
            previous = pair_semantics.setdefault(case["pair_id"], semantic)
            if previous != semantic:
                raise PilotError(f"pilot pair {case['pair_id']} semantic case differs by protocol")
            arm_id = f"{case['pair_id']}-{protocol}"
            episodes = []
            for episode in case["episodes"]:
                item = {
                    "run_id": f"{arm_id}-{episode['episode_id']}",
                    "episode_id": episode["episode_id"],
                    "sequence": episode["sequence"],
                    "fresh_session": episode["fresh_session"],
                    "prompt": episode["prompt"],
                    "injection_ref": episode["injection_ref"],
                    "termination": episode["termination"],
                }
                episodes.append(item)
                runs.append({
                    "run_id": item["run_id"],
                    "arm_id": arm_id,
                    "pair_id": case["pair_id"],
                    "case_id": case_id,
                    "protocol": protocol,
                    "episode_id": item["episode_id"],
                    "sequence": item["sequence"],
                    "fresh_session": item["fresh_session"],
                    "injection_ref": item["injection_ref"],
                    "termination": item["termination"],
                })
            source = manifest["protocol_source"]
            arms.append({
                "arm_id": arm_id,
                "pair_id": case["pair_id"],
                "case_id": case_id,
                "scenario_slug": case["slug"],
                "protocol": protocol,
                "arm_position": arm_position,
                "workspace_seed": workspace_seed,
                "input_sha256": case["input_sha256"],
                "semantic_case_sha256": semantic,
                "initial_workspace_manifest_sha256": sha256_bytes(workspaces.canonical_bytes(manifest)),
                "protocol_source": source,
                "protocol_bundle": _protocol_bundle_binding(experiment_dir, protocol),
                "tool_profile": manifest["tool_profile"],
                "episodes": episodes,
            })
    return {
        "schema_version": "1.0",
        "campaign_id": preregistration["campaign_id"],
        "preregistration_sha256": preregistration_sha256,
        "algorithm": "fixed-pilot-order-v1",
        "pair_count": 6,
        "arm_count": 12,
        "producer_episode_count": 18,
        "arms": arms,
        "runs": runs,
    }


def validate_run_plan(
    plan: dict[str, Any],
    preregistration: dict[str, Any],
    scenarios: dict[str, Any],
    *,
    experiment_dir: Path = HERE,
) -> None:
    validate_schema(plan, experiment_dir / "pilot-run-plan.schema.json", "pilot run plan")
    expected = build_run_plan(preregistration, scenarios, experiment_dir=experiment_dir)
    if plan != expected:
        raise PilotError("pilot run plan does not match the deterministic frozen plan")


def load_and_validate(
    experiment_dir: Path = HERE,
    run_plan_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    preregistration, scenarios = load_and_validate_preregistration(experiment_dir)
    path = run_plan_path or experiment_dir / "pilot-run-plan.json"
    plan = load_json(path, "pilot run plan")
    validate_run_plan(plan, preregistration, scenarios, experiment_dir=experiment_dir)
    return preregistration, scenarios, plan


def select_episode(plan: dict[str, Any], run_id: str, episode_id: str) -> dict[str, Any]:
    matches = [run for run in plan["runs"] if run["run_id"] == run_id]
    if len(matches) != 1:
        raise PilotError("run_id is not present exactly once in the pilot plan")
    if matches[0]["episode_id"] != episode_id:
        raise PilotError("episode_id does not match the selected run")
    return matches[0]


def adapter_command(
    *,
    experiment_dir: Path,
    run_plan_path: Path,
    preregistration: dict[str, Any],
    plan: dict[str, Any],
    run_id: str,
    episode_id: str,
    authorization: Path,
    authority_freeze: Path,
    execution_root: Path,
    output_dir: Path,
    codex_executable: str,
) -> list[str]:
    select_episode(plan, run_id, episode_id)
    adapter_path = _bound_file(experiment_dir, preregistration["execution"]["adapter"], "Codex adapter")
    command = [sys.executable, str(adapter_path)] if adapter_path.suffix.lower() == ".py" else [str(adapter_path)]
    command.extend([
        "--experiment-dir", str(experiment_dir),
        "--run-plan", str(run_plan_path),
        "--output-dir", str(output_dir),
        "--run-id", run_id,
        "--episode-id", episode_id,
        "--authorization", str(authorization),
        "--authority-freeze", str(authority_freeze),
        "--execution-root", str(execution_root),
        "--model", preregistration["execution"]["model"],
        "--reasoning-effort", preregistration["execution"]["reasoning_effort"],
        "--tool-profile", str(experiment_dir / preregistration["execution"]["tool_profile"]["path"]),
        "--codex-executable", codex_executable,
        "--preregistration-sha256", plan["preregistration_sha256"],
        "--run-plan-sha256", sha256_bytes(canonical_bytes(plan)),
        "--baseline-source-sha256", preregistration["baseline"]["aggregate_sha256"],
        "--candidate-source-sha256", preregistration["candidate"]["aggregate_sha256"],
        "--instrument-manifest-sha256", snapshots.instrument_manifest_sha256(
            load_json(experiment_dir / preregistration["instrument_manifest"]["path"], "instrument manifest")
        ),
        "--max-total-tokens-per-call", str(preregistration["execution"]["scored_call_limit"]["max_total_tokens"]),
        "--max-seconds-per-call", str(preregistration["execution"]["scored_call_limit"]["max_wall_seconds"]),
    ])
    return command


def execute_one(
    *,
    experiment_dir: Path,
    run_plan_path: Path,
    run_id: str,
    episode_id: str,
    authorization: Path,
    authority_freeze: Path,
    execution_root: Path,
    output_dir: Path,
    codex_executable: str,
    execute: bool,
) -> subprocess.CompletedProcess[str]:
    import pilot_freeze

    if not execute:
        raise PilotError("adapter execution requires the explicit --execute flag")
    try:
        pilot_freeze.validate_grant_authority(
            authorization,
            authority_freeze,
            expected_role="producer",
            experiment_dir=experiment_dir,
        )
    except (pilot_freeze.PilotFreezeError, pilot_freeze.guard.GuardError) as exc:
        raise PilotError(f"producer grant authority is invalid: {exc}") from exc
    try:
        preregistration_value = load_json(
            experiment_dir / "pilot-preregistration.json", "pilot preregistration"
        )
        execution_boundary.require_execution_ready(
            preregistration_value, experiment_dir, required_role="producer"
        )
    except execution_boundary.ExecutionBoundaryError as exc:
        raise PilotError(f"Pilot execution boundary is not ready: {exc}") from exc
    preregistration, _, plan = load_and_validate(experiment_dir, run_plan_path)
    command = adapter_command(
        experiment_dir=experiment_dir,
        run_plan_path=run_plan_path,
        preregistration=preregistration,
        plan=plan,
        run_id=run_id,
        episode_id=episode_id,
        authorization=authorization,
        authority_freeze=authority_freeze,
        execution_root=execution_root,
        output_dir=output_dir,
        codex_executable=codex_executable,
    )
    return subprocess.run(command, text=True, capture_output=True, check=False)


def _write_run_plan(path: Path, plan: dict[str, Any]) -> None:
    snapshots.write_bytes_atomic(path, canonical_bytes(plan))


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--experiment-dir", type=Path, default=HERE)
    commands = value.add_subparsers(dest="command", required=True)
    commands.add_parser("validate")
    plan = commands.add_parser("plan")
    plan.add_argument("--output", type=Path)
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--run-plan", type=Path)
    preflight.add_argument("--run-id", required=True)
    preflight.add_argument("--episode-id", required=True)
    execute = commands.add_parser("execute")
    execute.add_argument("--run-plan", type=Path, required=True)
    execute.add_argument("--run-id", required=True)
    execute.add_argument("--episode-id", required=True)
    execute.add_argument("--authorization", type=Path, required=True)
    execute.add_argument("--authority-freeze", type=Path, required=True)
    execute.add_argument("--execution-root", type=Path, required=True)
    execute.add_argument("--output-dir", type=Path, required=True)
    execute.add_argument("--codex-executable", default="codex")
    execute.add_argument("--execute", action="store_true")
    return value


def main(argv: Iterable[str] | None = None) -> int:
    args = parser().parse_args(list(argv) if argv is not None else None)
    root = args.experiment_dir.resolve()
    try:
        if args.command == "execute":
            completed = execute_one(
                experiment_dir=root,
                run_plan_path=args.run_plan.resolve(),
                run_id=args.run_id,
                episode_id=args.episode_id,
                authorization=args.authorization.resolve(),
                authority_freeze=args.authority_freeze.resolve(),
                execution_root=args.execution_root.resolve(),
                output_dir=args.output_dir.resolve(),
                codex_executable=args.codex_executable,
                execute=args.execute,
            )
            if completed.returncode != 0:
                raise PilotError(f"adapter failed: {completed.stderr.strip()}")
            result: Any = json.loads(completed.stdout)
            json.dump(result, sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
            sys.stdout.write("\n")
            return 0

        preregistration, scenarios = load_and_validate_preregistration(root)
        expected = build_run_plan(preregistration, scenarios, experiment_dir=root)
        if args.command == "validate":
            plan = load_json(root / "pilot-run-plan.json", "pilot run plan")
            validate_run_plan(plan, preregistration, scenarios, experiment_dir=root)
            result: Any = {
                "status": "valid", "producer_episodes": len(plan["runs"]), "network_calls": 0,
                **execution_status(preregistration, root),
            }
        elif args.command == "plan":
            if args.output:
                _write_run_plan(args.output, expected)
                result = {
                    "status": "written", "path": str(args.output),
                    "producer_episodes": len(expected["runs"]),
                    **execution_status(preregistration, root),
                }
            else:
                result = {"status": "planned", "plan": expected, **execution_status(preregistration, root)}
        elif args.command == "preflight":
            plan_path = args.run_plan or root / "pilot-run-plan.json"
            plan = load_json(plan_path, "pilot run plan")
            validate_run_plan(plan, preregistration, scenarios, experiment_dir=root)
            select_episode(plan, args.run_id, args.episode_id)
            with tempfile.TemporaryDirectory(prefix="create-loop-pilot-preflight-") as temporary:
                command = [
                    sys.executable,
                    str(root / "codex_exec_adapter.py"),
                    "--experiment-dir", str(root),
                    "--run-plan", str(plan_path),
                    "--output-dir", temporary,
                    "--run-id", args.run_id,
                    "--episode-id", args.episode_id,
                    "--tool-profile", str(root / preregistration["execution"]["tool_profile"]["path"]),
                    "--preregistration-sha256", plan["preregistration_sha256"],
                    "--run-plan-sha256", sha256_bytes(canonical_bytes(plan)),
                    "--preflight",
                ]
                completed = subprocess.run(command, text=True, capture_output=True, check=False)
            if completed.returncode != 0:
                raise PilotError(f"adapter preflight failed: {completed.stderr.strip()}")
            result = json.loads(completed.stdout)
        json.dump(result, sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0
    except (PilotError, json.JSONDecodeError) as exc:
        print(f"pilot error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
