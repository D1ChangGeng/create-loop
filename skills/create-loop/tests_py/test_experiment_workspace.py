from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = SKILL_ROOT / "tests" / "experiments"
sys.path.insert(0, str(EXPERIMENTS))

import workspace_builder as builder  # noqa: E402


class ExperimentWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.scenarios = builder.load_json(EXPERIMENTS / "scenarios.json")["scenarios"]
        self.preregistration = builder.load_json(EXPERIMENTS / "preregistration.json")

    def manifest(self, scenario: dict, protocol: str = "v2", seed: int = 20260801):
        return builder.build_manifest(
            experiment_id="create-loop-v1-v2-paired-2026",
            pair_id=f"S{scenario['id']:02d}-P01",
            scenario=scenario,
            protocol=protocol,
            workspace_seed=seed,
            source_binding=self.preregistration[
                "baseline" if protocol == "v1" else "candidate"
            ]["source_snapshot"],
        )

    def test_all_fourteen_builtin_fixtures_build_offline(self) -> None:
        self.assertEqual(len(self.scenarios), 14)
        for scenario in self.scenarios:
            for protocol in ("v1", "v2"):
                manifest, files, presented = self.manifest(scenario, protocol)
                target = Path(self.temp.name) / f"{scenario['id']}-{protocol}"
                builder.materialize_workspace(target, files)
                builder.validate_workspace(target, manifest)
                self.assertEqual(manifest["scenario_slug"], scenario["slug"])
                self.assertTrue(presented)

    def test_manifest_and_materialization_are_deterministic(self) -> None:
        scenario = self.scenarios[1]
        first, first_files, _ = self.manifest(scenario)
        second, second_files, _ = self.manifest(scenario)
        self.assertEqual(builder.canonical_bytes(first), builder.canonical_bytes(second))
        self.assertEqual(first_files, second_files)
        first_root = Path(self.temp.name) / "first"
        second_root = Path(self.temp.name) / "second"
        builder.materialize_workspace(first_root, first_files)
        builder.materialize_workspace(second_root, second_files)
        first_state = {path.relative_to(first_root).as_posix(): path.read_bytes() for path in first_root.rglob("*") if path.is_file()}
        second_state = {path.relative_to(second_root).as_posix(): path.read_bytes() for path in second_root.rglob("*") if path.is_file()}
        self.assertEqual(first_state, second_state)

    def test_manifest_requires_explicit_frozen_source_binding(self) -> None:
        scenario = self.scenarios[0]
        with self.assertRaises(TypeError):
            builder.build_manifest(
                experiment_id="create-loop-v1-v2-paired-2026",
                pair_id="S01-P01",
                scenario=scenario,
                protocol="v2",
                workspace_seed=20260801,
            )
        invalid = json.loads(json.dumps(self.preregistration["candidate"]["source_snapshot"]))
        invalid["manifest"]["path"] = "baseline-source.json"
        with self.assertRaisesRegex(builder.WorkspaceError, "v2 protocol source"):
            builder.build_manifest(
                experiment_id="create-loop-v1-v2-paired-2026",
                pair_id="S01-P01",
                scenario=scenario,
                protocol="v2",
                workspace_seed=20260801,
                source_binding=invalid,
            )

    def test_copied_fixture_manifest_does_not_read_live_preregistration(self) -> None:
        self.assertFalse(hasattr(builder, "PREREGISTRATION_PATH"))
        copied_root = Path(self.temp.name) / "isolated-experiments"
        shutil.copytree(EXPERIMENTS, copied_root)
        frozen = builder.load_json(copied_root / "preregistration.json")
        expected = frozen["candidate"]["source_snapshot"]
        manifest, files, _ = builder.build_manifest(
            experiment_id=frozen["experiment_id"],
            pair_id="S01-P01",
            scenario=self.scenarios[0],
            protocol="v2",
            workspace_seed=frozen["execution_config"]["workspace_seed"],
            source_binding=expected,
            tool_profile_path=copied_root / frozen["execution_config"]["tool_profile"]["path"],
            tool_profile_root=copied_root,
        )
        self.assertEqual(manifest["protocol_source"]["aggregate_sha256"], expected["aggregate_sha256"])
        target = Path(self.temp.name) / "isolated-workspace"
        builder.materialize_workspace(target, files)
        builder.validate_workspace(target, manifest)

    def test_common_case_binding_is_pair_stable_but_variant_is_explicit(self) -> None:
        scenario = self.scenarios[3]
        v1, _, _ = self.manifest(scenario, "v1")
        v2, _, _ = self.manifest(scenario, "v2")
        self.assertEqual(v1["semantic_case_sha256"], v2["semantic_case_sha256"])
        self.assertEqual(v1["fixture_id"], v2["fixture_id"])
        self.assertNotEqual(v1["variant_sha256"], v2["variant_sha256"])
        changed, _, _ = self.manifest(scenario, "v2", seed=20260802)
        self.assertNotEqual(builder.canonical_bytes(v2), builder.canonical_bytes(changed))

    def test_protocol_variants_carry_distinct_execution_instructions(self) -> None:
        scenario = self.scenarios[3]
        files_by_protocol = {}
        for protocol in ("v1", "v2"):
            _, files, _ = self.manifest(scenario, protocol)
            files_by_protocol[protocol] = {item["path"]: item["content"] for item in files}
        self.assertIn("v1 compatibility protocol", files_by_protocol["v1"]["AGENTS.md"])
        self.assertIn("opt-in create-loop v2 protocol", files_by_protocol["v2"]["AGENTS.md"])

    def test_target_must_be_empty_and_workspace_drift_is_rejected(self) -> None:
        manifest, files, _ = self.manifest(self.scenarios[0])
        target = Path(self.temp.name) / "workspace"
        target.mkdir()
        (target / "preexisting.txt").write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(builder.WorkspaceError, "must be empty"):
            builder.materialize_workspace(target, files)
        shutil.rmtree(target)
        builder.materialize_workspace(target, files)
        (target / "app" / "config.txt").write_text("drift\n", encoding="utf-8")
        with self.assertRaisesRegex(builder.WorkspaceError, "drifted"):
            builder.validate_workspace(target, manifest)

    def test_path_escape_collision_and_windows_device_names_fail_closed(self) -> None:
        cases = [
            [{"path": "../escape", "content": "x", "mode": "0644", "purpose": "x"}],
            [
                {"path": "A.txt", "content": "x", "mode": "0644", "purpose": "x"},
                {"path": "a.txt", "content": "y", "mode": "0644", "purpose": "x"},
            ],
            [{"path": "CON.txt", "content": "x", "mode": "0644", "purpose": "x"}],
            [{"path": "trailing.", "content": "x", "mode": "0644", "purpose": "x"}],
        ]
        for case in cases:
            with self.assertRaises(builder.WorkspaceError):
                builder._normalize_files(case)

    def test_tool_profile_is_real_bound_content(self) -> None:
        profile = builder.validate_tool_profile()
        self.assertEqual(profile["network"], "denied")
        self.assertEqual(profile["publish"], "denied")
        manifest, _, _ = self.manifest(self.scenarios[0])
        self.assertEqual(manifest["tool_profile"]["sha256"], builder.sha256_file(builder.TOOL_PROFILE_PATH))
        with mock.patch.object(builder, "TOOL_PROFILE_PATH", Path(self.temp.name) / "missing.json"):
            with self.assertRaises(builder.WorkspaceError):
                builder.validate_tool_profile(builder.TOOL_PROFILE_PATH)

        provider = builder.validate_tool_profile(EXPERIMENTS / "tool-profiles" / "provider-workspace-no-publish.json")
        self.assertEqual(provider["network"], "provider-api-only")
        self.assertEqual(provider["environment"]["credential_allow"], ["CODEX_HOME"])

    def test_presented_artifact_resolves_real_declared_files(self) -> None:
        scenario = self.scenarios[0]
        manifest, files, presented = self.manifest(scenario)
        target = Path(self.temp.name) / "presented"
        builder.materialize_workspace(target, files)
        (target / "app" / "config.txt").write_text("greeting=new\n", encoding="utf-8", newline="\n")
        result = builder.build_presented_artifact(target, manifest, presented)
        self.assertEqual(result["files"][0]["path"], "app/config.txt")
        self.assertNotIn("protocol", result)
        (target / "app" / "config.txt").unlink()
        with self.assertRaisesRegex(builder.WorkspaceError, "missing"):
            builder.build_presented_artifact(target, manifest, presented)

    def test_presented_output_must_remain_outside_workspace(self) -> None:
        scenario = self.scenarios[0]
        manifest, files, presented = self.manifest(scenario)
        target = Path(self.temp.name) / "presented-output-workspace"
        builder.materialize_workspace(target, files)
        (target / "app" / "config.txt").write_text("greeting=new\n", encoding="utf-8", newline="\n")
        artifact = builder.build_presented_artifact(target, manifest, presented)
        before = {path.relative_to(target).as_posix(): path.read_bytes() for path in target.rglob("*") if path.is_file()}
        with self.assertRaisesRegex(builder.WorkspaceError, "must be outside"):
            builder.write_presented_artifact(target, target / "presented.json", artifact)
        after = {path.relative_to(target).as_posix(): path.read_bytes() for path in target.rglob("*") if path.is_file()}
        self.assertEqual(after, before)
        external = Path(self.temp.name) / "presented.json"
        builder.write_presented_artifact(target, external, artifact)
        self.assertEqual(json.loads(external.read_text(encoding="utf-8")), artifact)

    def test_manifest_writer_must_remain_outside_workspace(self) -> None:
        manifest, files, _ = self.manifest(self.scenarios[0])
        target = Path(self.temp.name) / "manifest-output-workspace"
        builder.materialize_workspace(target, files)
        before = {path.relative_to(target).as_posix(): path.read_bytes() for path in target.rglob("*") if path.is_file()}
        with self.assertRaisesRegex(builder.WorkspaceError, "must be outside"):
            builder.write_workspace_manifest(target, target / "app" / "config.txt", manifest)
        after = {path.relative_to(target).as_posix(): path.read_bytes() for path in target.rglob("*") if path.is_file()}
        self.assertEqual(after, before)
        external = Path(self.temp.name) / "function-workspace-manifest.json"
        builder.write_workspace_manifest(target, external, manifest)
        self.assertEqual(json.loads(external.read_text(encoding="utf-8")), manifest)

    def test_cli_rejects_manifest_inside_target_before_materialization(self) -> None:
        target = Path(self.temp.name) / "cli-contained-workspace"
        _, files, _ = self.manifest(self.scenarios[0])
        builder.materialize_workspace(target, files)
        before = {path.relative_to(target).as_posix(): path.read_bytes() for path in target.rglob("*") if path.is_file()}
        with self.assertRaisesRegex(builder.WorkspaceError, "must be outside"):
            builder.main([
                "--scenario-id", "1", "--protocol", "v2", "--pair-id", "S01-P01",
                "--preregistration", str(EXPERIMENTS / "preregistration.json"),
                "--target", str(target), "--manifest", str(target / "app" / "config.txt"),
            ])
        after = {path.relative_to(target).as_posix(): path.read_bytes() for path in target.rglob("*") if path.is_file()}
        self.assertEqual(after, before)

    def test_cli_rejects_manifest_alias_into_target_before_materialization(self) -> None:
        target = Path(self.temp.name) / "cli-alias-workspace"
        alias = Path(self.temp.name) / "cli-alias"
        target.mkdir()
        try:
            alias.symlink_to(target, target_is_directory=True)
        except OSError:
            if os.name != "nt":
                self.skipTest("directory symlink unavailable")
            result = subprocess.run(
                ["cmd", "/d", "/c", "mklink", "/J", str(alias), str(target)],
                text=True,
                capture_output=True,
                check=False,
            )
            if result.returncode != 0:
                self.skipTest("directory junction unavailable")
        with self.assertRaisesRegex(builder.WorkspaceError, "must be outside"):
            builder.main([
                "--scenario-id", "1", "--protocol", "v2", "--pair-id", "S01-P01",
                "--preregistration", str(EXPERIMENTS / "preregistration.json"),
                "--target", str(target), "--manifest", str(alias / "app" / "config.txt"),
            ])
        self.assertEqual(list(target.iterdir()), [])

    @unittest.skipUnless(os.name == "nt", "Windows path identity control")
    def test_cli_rejects_case_alias_into_target_before_materialization(self) -> None:
        target = Path(self.temp.name) / "cli-case-workspace"
        target.mkdir()
        case_alias = target.with_name(target.name.upper())
        with self.assertRaisesRegex(builder.WorkspaceError, "must be outside"):
            builder.main([
                "--scenario-id", "1", "--protocol", "v2", "--pair-id", "S01-P01",
                "--preregistration", str(EXPERIMENTS / "preregistration.json"),
                "--target", str(target), "--manifest", str(case_alias / "app" / "config.txt"),
            ])
        self.assertEqual(list(target.iterdir()), [])

    def test_cli_build_does_not_launch_subprocess_or_network(self) -> None:
        target = Path(self.temp.name) / "cli-workspace"
        manifest = Path(self.temp.name) / "workspace-manifest.json"
        with mock.patch("subprocess.run", side_effect=AssertionError("subprocess launched")):
            self.assertEqual(builder.main([
                "--scenario-id", "1", "--protocol", "v2", "--pair-id", "S01-P01",
                "--preregistration", str(EXPERIMENTS / "preregistration.json"),
                "--target", str(target), "--manifest", str(manifest),
            ]), 0)
        self.assertTrue(target.is_dir())
        self.assertEqual(json.loads(manifest.read_text(encoding="utf-8"))["scenario_id"], 1)
        self.assertFalse(manifest.is_relative_to(target))

    def test_pilot_contract_is_six_pairs_eighteen_episodes_and_evaluator_is_separate(self) -> None:
        pilot = builder.load_pilot_scenarios()
        evaluator = builder.load_pilot_evaluator()
        self.assertEqual([item["case_id"] for item in pilot["cases"]], ["N0", "T2", "T3", "T5", "S1", "T7"])
        self.assertEqual(sum(len(item["episodes"]) * 2 for item in pilot["cases"]), 18)
        self.assertEqual(sum(item["review_required"] for item in pilot["cases"]), 4)
        self.assertEqual(len(evaluator["blind_assignments"]), 4)
        self.assertEqual(evaluator["classification"], "evaluator-only-do-not-deliver-to-producer-or-reviewer")

    def test_pilot_hidden_check_criterion_mapping_is_exact_and_excludes_trace_review(self) -> None:
        evaluator = builder.load_pilot_evaluator()
        for case in evaluator["cases"]:
            expected = {
                criterion["id"] for criterion in case["criteria"] if criterion["measurement"] != "trace-review"
            }
            covered = [
                criterion_ref
                for check in case["hidden_checks"]
                for criterion_ref in check["criterion_refs"]
            ]
            self.assertEqual(set(covered), expected)
            self.assertEqual(len(covered), len(set(covered)))

        fixtures = [
            ("unknown or cross-case", lambda value: value["cases"][0]["hidden_checks"][0]["criterion_refs"].append("T2-BEHAVIOR")),
            ("cannot claim trace-review", lambda value: value["cases"][1]["hidden_checks"][0]["criterion_refs"].append("T2-FALSE-COMPLETE")),
            ("coverage is not exact", lambda value: value["cases"][5]["hidden_checks"][0]["criterion_refs"].pop()),
            ("covered by multiple", lambda value: value["cases"][5]["hidden_checks"].append({
                **value["cases"][5]["hidden_checks"][0],
                "id": "T7-HC2",
                "criterion_refs": ["T7-EOL-EXACT"],
            })),
        ]
        source = builder.load_json(builder.PILOT_EVALUATOR_PATH)
        for label, mutate in fixtures:
            with self.subTest(label=label):
                value = json.loads(json.dumps(source))
                mutate(value)
                path = Path(self.temp.name) / f"evaluator-{label.replace(' ', '-')}.json"
                path.write_bytes(builder.canonical_bytes(value))
                with self.assertRaisesRegex(builder.WorkspaceError, label):
                    builder.load_pilot_evaluator(path)

    def test_pilot_workspace_contains_no_hidden_rubric_or_injection_bytes(self) -> None:
        pilot_preregistration = builder.load_json(EXPERIMENTS / "pilot-preregistration.json")
        for case_id in ("N0", "T2", "T3", "T5", "S1", "T7"):
            case = builder.load_pilot_case(case_id)
            for protocol in ("v1", "v2"):
                manifest, files, _ = builder.build_pilot_manifest(
                    pair_id=case["pair_id"], case=case, protocol=protocol, workspace_seed=20260805,
                    source_binding=pilot_preregistration["baseline" if protocol == "v1" else "candidate"],
                )
                visible = builder.canonical_bytes({"manifest": manifest, "files": files})
                for forbidden in (b"pilot-evaluator/", b"hidden_checks", b"blind_assignments", b"action_rubric"):
                    self.assertNotIn(forbidden, visible)
                target = Path(self.temp.name) / f"pilot-{case_id}-{protocol}"
                builder.materialize_workspace(target, files)
                builder.validate_workspace(target, manifest)
                agents = (target / "AGENTS.md").read_text(encoding="utf-8")
                self.assertIn("../protocol-bundle/SKILL.md", agents)
                self.assertTrue(manifest["evaluator_content_excluded"])

    def test_protocol_bundle_is_complete_frozen_and_outside_workspace(self) -> None:
        root = Path(self.temp.name) / "v1" / "protocol-bundle"
        manifest = builder.build_protocol_bundle("v1", root)
        builder.validate_protocol_bundle(root, manifest)
        self.assertTrue((root / "SKILL.md").is_file())
        self.assertGreater(len(manifest["files"]), 100)
        with self.assertRaises(PermissionError):
            (root / "SKILL.md").write_text("drift", encoding="utf-8")

        candidate = builder.load_json(builder.CANDIDATE_SOURCE_PATH)
        for entry in candidate["files"]:
            path = builder.SKILL_ROOT / entry["path"]
            entry["sha256"] = builder.sha256_file(path)
            entry["size"] = path.stat().st_size
        candidate["aggregate_sha256"] = builder.sha256_bytes(builder.canonical_bytes(candidate["files"]))
        current_manifest = Path(self.temp.name) / "candidate-source.json"
        current_manifest.write_bytes(builder.canonical_bytes(candidate))
        v2_root = Path(self.temp.name) / "v2" / "protocol-bundle"
        with mock.patch.object(builder, "CANDIDATE_SOURCE_PATH", current_manifest):
            manifest = builder.build_protocol_bundle("v2", v2_root)
            builder.validate_protocol_bundle(v2_root, manifest)
        self.assertTrue((v2_root / "SKILL.md").is_file())
        stale = json.loads(json.dumps(candidate))
        stale["files"][0]["sha256"] = "0" * 64
        current_manifest.write_bytes(builder.canonical_bytes(stale))
        with self.assertRaises(builder.WorkspaceError):
            with mock.patch.object(builder, "CANDIDATE_SOURCE_PATH", current_manifest):
                builder.build_protocol_bundle("v2", Path(self.temp.name) / "stale-v2")

    def test_t3_and_t5_injections_are_staged_and_hash_bound(self) -> None:
        source_binding = builder.load_json(EXPERIMENTS / "pilot-preregistration.json")["candidate"]
        for case_id, expected_path in (("T3", "test/cache-integration.test.mjs"), ("T5", "src/payments/resume.ts")):
            case = builder.load_pilot_case(case_id)
            manifest, files, _ = builder.build_pilot_manifest(
                pair_id=case["pair_id"], case=case, protocol="v2", workspace_seed=20260805,
                source_binding=source_binding,
            )
            workspace = Path(self.temp.name) / f"inject-{case_id}"
            builder.materialize_workspace(workspace, files)
            before = builder.snapshot_workspace(workspace)
            if case_id == "T3":
                self.assertFalse((workspace / expected_path).exists())
            receipt = builder.apply_pilot_injection(workspace, case_id, "E02")
            after = builder.snapshot_workspace(workspace)
            self.assertEqual(receipt["before_workspace_sha256"], before["aggregate_sha256"])
            self.assertEqual(receipt["after_workspace_sha256"], after["aggregate_sha256"])
            self.assertNotEqual(before["aggregate_sha256"], after["aggregate_sha256"])
            self.assertTrue((workspace / expected_path).is_file())
            with self.assertRaisesRegex(builder.WorkspaceError, "only before E02"):
                builder.apply_pilot_injection(workspace, case_id, "E01")

    def test_s1_recovery_barrier_requires_exactly_one_real_effect(self) -> None:
        case = builder.load_pilot_case("S1")
        _, files, _ = builder.build_pilot_manifest(
            pair_id=case["pair_id"], case=case, protocol="v2", workspace_seed=20260805,
            source_binding=builder.load_json(EXPERIMENTS / "pilot-preregistration.json")["candidate"],
        )
        workspace = Path(self.temp.name) / "effect"
        builder.materialize_workspace(workspace, files)
        with self.assertRaisesRegex(builder.WorkspaceError, "exactly one"):
            builder.apply_pilot_injection(workspace, "S1", "E02")
        reality = workspace / "reality" / "account.json"
        reality.write_text('{"applied_count":1,"operation_ids":["pilot-credit-001"]}\n', encoding="utf-8", newline="\n")
        receipt = builder.apply_pilot_injection(workspace, "S1", "E02")
        self.assertEqual(receipt["changed_files"][0]["path"], "reality/account.json")

    def test_s1_effect_tool_waits_at_reality_boundary_until_controller_release(self) -> None:
        case = builder.load_pilot_case("S1")
        _, files, _ = builder.build_pilot_manifest(
            pair_id=case["pair_id"], case=case, protocol="v2", workspace_seed=20260805,
            source_binding=builder.load_json(EXPERIMENTS / "pilot-preregistration.json")["candidate"],
        )
        workspace = Path(self.temp.name) / "effect-tool-barrier"
        builder.materialize_workspace(workspace, files)
        process = subprocess.Popen(
            [sys.executable, "tools/apply_credit.py", "pilot-credit-001"],
            cwd=workspace,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            marker = workspace / "reality" / "effect-applied-before-post.json"
            deadline = time.monotonic() + 5
            while not marker.is_file() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertIsNone(process.poll(), "effect tool exited before the controller boundary")
            self.assertTrue(marker.is_file())
            self.assertEqual(
                json.loads((workspace / "reality/account.json").read_text(encoding="utf-8")),
                {"applied_count": 1, "operation_ids": ["pilot-credit-001"]},
            )
            self.assertFalse((workspace / "reality/effect-post.json").exists())
            (workspace / "reality/controller-release").write_text("release\n", encoding="utf-8", newline="\n")
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertIn('"applied_count": 1', stdout)
            self.assertEqual(
                json.loads((workspace / "reality/effect-post.json").read_text(encoding="utf-8")),
                {"operation_id": "pilot-credit-001", "outcome": "ok"},
            )
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
