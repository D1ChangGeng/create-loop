#!/usr/bin/env python3
"""Refresh Phase 5 candidate and instrument bindings after reviewed source edits."""
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import snapshot_tools as snapshots
import workspace_builder as workspaces


HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parents[1]
REPO_ROOT = SKILL_ROOT.parents[1]
PREREGISTRATION = HERE / "preregistration.json"
CANDIDATE_SOURCE = HERE / "candidate-source.json"
INSTRUMENT_MANIFEST = HERE / "instrument-manifest.json"
PILOT_PREREGISTRATION = HERE / "pilot-preregistration.json"
PILOT_RUN_PLAN = HERE / "pilot-run-plan.json"
PROTOCOL_BUNDLES = HERE / "protocol-bundles"


def _binding(path: Path, root: Path) -> dict[str, str]:
    return {"path": path.relative_to(root).as_posix(), "sha256": snapshots.sha256_file(path)}


def _build_protocol_bundle_bytes(
    experiment_dir: Path,
    candidate_manifest_bytes: bytes,
) -> tuple[dict[str, bytes], dict[str, dict[str, str]]]:
    outputs: dict[str, bytes] = {}
    bindings: dict[str, dict[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="create-loop-pilot-bundles-") as temporary:
        staging = Path(temporary)
        candidate_manifest = staging / "candidate-source.json"
        candidate_manifest.write_bytes(candidate_manifest_bytes)
        original_candidate_path = workspaces.CANDIDATE_SOURCE_PATH
        workspaces.CANDIDATE_SOURCE_PATH = candidate_manifest
        try:
            for protocol in ("v1", "v2"):
                target = staging / protocol
                workspaces.build_protocol_bundle(protocol, target)
                for path in sorted(target.rglob("*"), key=lambda item: item.relative_to(target).as_posix()):
                    if path.is_file():
                        relative = f"protocol-bundles/{protocol}/{path.relative_to(target).as_posix()}"
                        outputs[relative] = path.read_bytes()
                manifest_relative = f"protocol-bundles/{protocol}/bundle-manifest.json"
                manifest_bytes = outputs[manifest_relative]
                bindings[protocol] = {
                    "path": manifest_relative,
                    "sha256": snapshots.sha256_bytes(manifest_bytes),
                }
        finally:
            workspaces.CANDIDATE_SOURCE_PATH = original_candidate_path
    return outputs, bindings


def compute_freeze(
    *,
    experiment_dir: Path = HERE,
    skill_root: Path = SKILL_ROOT,
    repo_root: Path = REPO_ROOT,
) -> dict[Path, bytes]:
    snapshots.validate_repository_instrument_input_set(experiment_dir)
    preregistration_path = experiment_dir / "preregistration.json"
    candidate_source_path = experiment_dir / "candidate-source.json"
    instrument_manifest_path = experiment_dir / "instrument-manifest.json"
    pilot_preregistration_path = experiment_dir / "pilot-preregistration.json"
    pilot_run_plan_path = experiment_dir / "pilot-run-plan.json"
    original_preregistration_bytes = preregistration_path.read_bytes()
    original_pilot_preregistration_bytes = pilot_preregistration_path.read_bytes()
    preregistration = snapshots.load_json(preregistration_path)
    base_commit = preregistration["candidate"]["source_snapshot"]["origin_commit"]
    candidate = snapshots.build_worktree_snapshot(
        skill_root,
        repo_root=repo_root,
        snapshot_id="v2-candidate-worktree",
        protocol="v2",
        base_git_commit=base_commit,
    )
    candidate_bytes = snapshots.canonical_bytes(candidate)
    preregistration["candidate"]["source_snapshot"]["manifest"]["sha256"] = snapshots.sha256_bytes(candidate_bytes)
    preregistration["candidate"]["source_snapshot"]["aggregate_sha256"] = candidate["aggregate_sha256"]
    preregistration["scenario_manifest"]["sha256"] = snapshots.sha256_file(experiment_dir / "scenarios.json")
    preregistration["review"]["manifest_schema"]["sha256"] = snapshots.sha256_file(
        experiment_dir / "blind-review-manifest.schema.json"
    )
    tool_profile = preregistration["execution_config"]["tool_profile"]
    tool_profile["sha256"] = snapshots.sha256_file(experiment_dir / tool_profile["path"])

    pilot = snapshots.load_json(pilot_preregistration_path)
    pilot["baseline"] = {
        "protocol": "v1",
        "origin_commit": preregistration["baseline"]["source_snapshot"]["origin_commit"],
        "manifest": preregistration["baseline"]["source_snapshot"]["manifest"],
        "aggregate_sha256": preregistration["baseline"]["source_snapshot"]["aggregate_sha256"],
    }
    pilot["candidate"] = {
        "protocol": "v2",
        "origin_commit": base_commit,
        "manifest": preregistration["candidate"]["source_snapshot"]["manifest"],
        "aggregate_sha256": candidate["aggregate_sha256"],
    }
    pilot["scenario_manifest"] = _binding(experiment_dir / "pilot-scenarios.json", experiment_dir)
    pilot["evaluator_manifest"] = _binding(experiment_dir / "pilot-evaluator-manifest.json", experiment_dir)
    pilot["provider"] = {
        "id": "custom-zeo-responses-ultra",
        **_binding(experiment_dir / "provider-profiles/custom-zeo-responses.json", experiment_dir),
    }
    producer_cli = {
        "id": "codex-0.144.1-windows",
        **_binding(experiment_dir / "cli-identities/codex-0.144.1-windows.json", experiment_dir),
    }
    pilot["cli_identities"]["calibration_reuses"] = "producer"
    pilot["cli_identities"]["producer"] = {
        "status": "frozen", "platform": "windows", "arch": "x86_64",
        "version": "0.144.1", "binding": producer_cli, "reason": None,
    }
    reviewer = pilot["cli_identities"]["reviewer"]
    if reviewer["status"] == "frozen" and reviewer["binding"] is not None:
        reviewer_path = experiment_dir / reviewer["binding"]["path"]
        reviewer["binding"] = {
            "id": reviewer["binding"]["id"], **_binding(reviewer_path, experiment_dir),
        }
    pilot["execution"]["tool_profile"] = {
        "id": "provider-workspace-no-publish",
        **_binding(experiment_dir / "tool-profiles/provider-workspace-no-publish.json", experiment_dir),
    }
    pilot["execution"]["adapter"] = _binding(experiment_dir / "codex_exec_adapter.py", experiment_dir)
    import pilot_harness

    bundle_outputs, bundle_bindings = _build_protocol_bundle_bytes(experiment_dir, candidate_bytes)
    original_bundle_binding = pilot_harness._protocol_bundle_binding
    pilot_harness._protocol_bundle_binding = lambda _, protocol: bundle_bindings[protocol]
    try:
        plan = pilot_harness.build_run_plan(
            pilot,
            snapshots.load_json(experiment_dir / "pilot-scenarios.json"),
            experiment_dir=experiment_dir,
        )
    finally:
        pilot_harness._protocol_bundle_binding = original_bundle_binding
    plan_bytes = snapshots.canonical_bytes(plan)

    overrides = {"candidate-source.json": candidate_bytes}
    instrument = snapshots.build_instrument_manifest(
        experiment_dir,
        snapshots.EXPERIMENT_INSTRUMENT_INPUTS,
        source_snapshots=(
            preregistration["baseline"]["source_snapshot"]["aggregate_sha256"],
            candidate["aggregate_sha256"],
        ),
        content_overrides=overrides,
    )
    instrument_bytes = snapshots.canonical_bytes(instrument)
    preregistration["instrument_manifest"]["sha256"] = snapshots.instrument_manifest_sha256(instrument)
    pilot["instrument_manifest"] = {"path": "instrument-manifest.json"}
    instrument_hash = snapshots.instrument_manifest_sha256(instrument)
    preregistration["instrument_manifest"]["sha256"] = instrument_hash
    pilot_bytes = snapshots.canonical_bytes(pilot)
    preregistration_bytes = snapshots.canonical_bytes(preregistration)
    candidate_recheck = snapshots.build_worktree_snapshot(
        skill_root,
        repo_root=repo_root,
        snapshot_id="v2-candidate-worktree",
        protocol="v2",
        base_git_commit=base_commit,
    )
    if snapshots.canonical_bytes(candidate_recheck) != candidate_bytes:
        raise snapshots.SnapshotError("candidate source changed while experiment freeze was computed")
    snapshots.validate_instrument_manifest(
        experiment_dir,
        instrument,
        expected_inputs=snapshots.EXPERIMENT_INSTRUMENT_INPUTS,
        content_overrides=overrides,
    )
    if preregistration_path.read_bytes() != original_preregistration_bytes:
        raise snapshots.SnapshotError("preregistration changed while experiment freeze was computed")
    if pilot_preregistration_path.read_bytes() != original_pilot_preregistration_bytes:
        raise snapshots.SnapshotError("pilot preregistration changed while experiment freeze was computed")
    output = {
        candidate_source_path: candidate_bytes,
        instrument_manifest_path: instrument_bytes,
        preregistration_path: preregistration_bytes,
        pilot_preregistration_path: pilot_bytes,
        pilot_run_plan_path: plan_bytes,
    }
    for relative, data in bundle_outputs.items():
        output[experiment_dir / relative] = data
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    expected = compute_freeze()
    if args.check:
        drift = [str(path) for path, data in expected.items() if not path.is_file() or path.read_bytes() != data]
        if drift:
            raise snapshots.SnapshotError("experiment freeze drifted: " + ", ".join(drift))
        return 0
    for path, data in expected.items():
        snapshots.write_bytes_atomic(path, data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
