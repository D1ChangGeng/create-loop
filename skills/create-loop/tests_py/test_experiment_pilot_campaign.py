from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = SKILL_ROOT / "tests" / "experiments"
sys.path.insert(0, str(EXPERIMENTS))

import pilot_campaign as campaign  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(campaign.canonical_bytes(value))


class PilotCampaignTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def plan(self) -> dict:
        return json.loads((EXPERIMENTS / "pilot-run-plan.json").read_text(encoding="utf-8"))

    def preregistration_with_reviewer(self) -> dict:
        prereg = json.loads((EXPERIMENTS / "pilot-preregistration.json").read_text(encoding="utf-8"))
        prereg["cli_identities"]["reviewer"] = {
            "status": "frozen", "platform": "linux", "arch": "x86_64",
            "version": "0.144.1",
            "binding": {
                "id": "codex-0.144.1-linux-test",
                "path": "cli-identities/codex-0.144.1-linux-test.json",
                "sha256": "d" * 64,
            },
            "reason": None,
        }
        return prereg

    def test_fixed_producer_order_and_missing_episode_fail_closed(self) -> None:
        plan = self.plan()
        self.assertEqual(
            tuple(item["run_id"] for item in campaign.producer_schedule(plan)),
            campaign.EXPECTED_RUN_ORDER,
        )
        plan["runs"][0], plan["runs"][1] = plan["runs"][1], plan["runs"][0]
        with self.assertRaisesRegex(campaign.CampaignError, "fixed 18-call order"):
            campaign.producer_schedule(plan)
        capture_root = self.root / "campaign"
        first = capture_root / "producer-episodes" / campaign.EXPECTED_RUN_ORDER[0] / "episode.json"
        write_json(first, {"run_id": campaign.EXPECTED_RUN_ORDER[0]})
        with self.assertRaisesRegex(campaign.CampaignError, "first missing run"):
            campaign.load_episode_bindings(capture_root)

    def grant_value(self, role: str, root: Path, plan: dict) -> dict:
        prereg = self.preregistration_with_reviewer()
        calls = sorted(
            campaign._expected_calls(plan, role),
            key=lambda item: (item[0], item[1]),
        )
        authority_hash = "f" * 64 if role != "calibration" else "e" * 64
        return {
            "schema_version": "2.0",
            "authorization_id": f"authorization-{role}",
            "execution_id": f"execution-{role}",
            "execution_root_sha256": campaign.guard._root_path_sha256(root),
            "experiment_id": campaign.CAMPAIGN_ID,
            "preregistration_sha256": plan["preregistration_sha256"],
            "run_plan_sha256": campaign._document_hash(plan),
            "role": role,
            "adapter": campaign.pilot_runners.adapter.adapter_binding(),
            "cli_identity": prereg["cli_identities"][
                "reviewer" if role == "reviewer" else "producer"
            ]["binding"] or prereg["cli_identities"]["producer"]["binding"],
            "provider_profile": prereg["provider"],
            "model": prereg["execution"]["model"],
            "reasoning_effort": prereg["execution"]["reasoning_effort"],
            "tool_profile": prereg["execution"]["tool_profile"],
            "authorized_calls": [
                {"run_id": run_id, "episode_id": episode_id}
                for run_id, episode_id in calls
            ],
            "limits": campaign.ROLE_LIMITS[role],
            "authorized_by": "unit-test",
            "authorized_at": "2026-08-05T00:00:00Z",
            "expires_at": "2030-01-01T00:00:00Z",
            "authority_evidence_sha256": authority_hash,
        }

    def test_authority_preflight_rejects_budget_and_identity_aliasing(self) -> None:
        plan = self.plan()
        prereg = self.preregistration_with_reviewer()
        final_freeze = self.root / "final-freeze.json"
        pre_freeze = self.root / "pre-freeze.json"
        final_freeze.write_text("final\n", encoding="utf-8", newline="\n")
        pre_freeze.write_text("pre\n", encoding="utf-8", newline="\n")
        freeze = {
            "preregistration": prereg,
            "run_plan": plan,
            "path": final_freeze,
            "sha256": campaign.sha256_file(final_freeze),
            "document": {},
            "bindings": {
                "pre_calibration_freeze": (
                    pre_freeze,
                    {"path": pre_freeze.name, "sha256": campaign.sha256_file(pre_freeze)},
                ),
            },
        }
        authorities = {}
        for role in campaign.ROLE_LIMITS:
            root = self.root / role
            root.mkdir()
            grant = self.grant_value(role, root, plan)
            grant["authority_evidence_sha256"] = campaign.sha256_file(
                pre_freeze if role == "calibration" else final_freeze
            )
            path = root / "grant.json"
            write_json(path, grant)
            authorities[role] = (root, path)
        freeze["bindings"]["calibration_grant"] = (
            authorities["calibration"][1],
            {
                "path": "calibration/grant.json",
                "sha256": campaign.sha256_file(authorities["calibration"][1]),
            },
        )

        def validate_authority(
            grant_path: Path,
            authority_path: Path,
            *,
            expected_role: str,
            experiment_dir: Path,
        ) -> dict:
            self.assertEqual(grant_path, authorities[expected_role][1].resolve())
            self.assertEqual(
                authority_path.resolve(),
                (pre_freeze if expected_role == "calibration" else final_freeze).resolve(),
            )
            self.assertEqual(experiment_dir, campaign.HERE)
            return campaign.guard.load_grant(grant_path)

        authority_validator = mock.patch.object(
            campaign.pilot_freeze,
            "validate_grant_authority",
            side_effect=validate_authority,
        )
        with authority_validator:
            checked = campaign.preflight_authorities(freeze, authorities)
        self.assertEqual(set(checked), set(campaign.ROLE_LIMITS))

        producer_path = authorities["producer"][1]
        producer = json.loads(producer_path.read_text())
        producer["limits"]["total"]["max_total_tokens"] -= 1
        producer_path.unlink()
        write_json(producer_path, producer)
        with authority_validator:
            with self.assertRaisesRegex(campaign.CampaignError, "budget drifted"):
                campaign.preflight_authorities(freeze, authorities)

        producer["limits"] = campaign.ROLE_LIMITS["producer"]
        producer["authorization_id"] = "authorization-reviewer"
        producer_path.unlink()
        write_json(producer_path, producer)
        with authority_validator:
            with self.assertRaisesRegex(campaign.CampaignError, "independent authorization_id"):
                campaign.preflight_authorities(freeze, authorities)

    def test_authority_preflight_requires_each_execution_root_grant_json(self) -> None:
        plan = self.plan()
        prereg = self.preregistration_with_reviewer()
        final_freeze = self.root / "final-freeze.json"
        pre_freeze = self.root / "pre-freeze.json"
        final_freeze.write_text("final\n", encoding="utf-8", newline="\n")
        pre_freeze.write_text("pre\n", encoding="utf-8", newline="\n")
        authorities = {}
        for role in campaign.ROLE_LIMITS:
            root = self.root / role
            root.mkdir()
            canonical = root / "grant.json"
            write_json(canonical, self.grant_value(role, root, plan))
            authorities[role] = (root, canonical)
        copied = self.root / "copied-producer-grant.json"
        copied.write_bytes(authorities["producer"][1].read_bytes())
        authorities["producer"] = (authorities["producer"][0], copied)
        freeze = {
            "preregistration": prereg,
            "run_plan": plan,
            "path": final_freeze,
            "bindings": {
                "pre_calibration_freeze": (pre_freeze, {"path": "pre-freeze.json", "sha256": "1" * 64}),
                "calibration_grant": (authorities["calibration"][1], {"path": "calibration/grant.json", "sha256": campaign.sha256_file(authorities["calibration"][1])}),
            },
        }
        def reject_copied_producer(
            grant_path: Path,
            authority_path: Path,
            *,
            expected_role: str,
            experiment_dir: Path,
        ) -> dict:
            del authority_path, experiment_dir
            if expected_role == "producer":
                self.assertEqual(grant_path, copied.resolve())
                raise campaign.pilot_freeze.PilotFreezeError(
                    "pilot authority requires the canonical execution-root grant.json"
                )
            return campaign.guard.load_grant(grant_path)

        with mock.patch.object(
            campaign.pilot_freeze,
            "validate_grant_authority",
            side_effect=reject_copied_producer,
        ):
            with self.assertRaisesRegex(campaign.CampaignError, "canonical execution-root grant.json"):
                campaign.preflight_authorities(freeze, authorities)

    def test_calibration_grant_binding_uses_exact_final_freeze_artifact_role(self) -> None:
        freeze_path = self.root / "authority" / "final-freeze.json"
        grant_path = self.root / "authority" / "calibration" / "grant.json"
        write_json(grant_path, {"role": "calibration"})
        document = {
            "calibration_artifacts": [
                {
                    "role": "grant",
                    "path": "calibration/grant.json",
                    "sha256": campaign.sha256_file(grant_path),
                    "size": grant_path.stat().st_size,
                },
                {
                    "role": "response",
                    "path": "calibration/grant.json",
                    "sha256": campaign.sha256_file(grant_path),
                    "size": grant_path.stat().st_size,
                },
            ],
        }
        resolved, binding = campaign._calibration_grant_binding(freeze_path, document)
        self.assertEqual(resolved, grant_path.resolve())
        self.assertEqual(binding["sha256"], campaign.sha256_file(grant_path))

        document["calibration_artifacts"].append(dict(document["calibration_artifacts"][0]))
        with self.assertRaisesRegex(campaign.CampaignError, "exactly one calibration grant"):
            campaign._calibration_grant_binding(freeze_path, document)

    def test_path_registration_rejects_case_and_prefix_collisions(self) -> None:
        for paths in (("A/file.txt", "a/FILE.txt"), ("dir", "dir/file.txt")):
            identities: set[str] = set()
            campaign._register_path(identities, paths[0], "artifact")
            with self.assertRaisesRegex(campaign.CampaignError, "collides"):
                campaign._register_path(identities, paths[1], "artifact")

    def test_exact_tree_copy_allows_nested_directories(self) -> None:
        source = self.root / "source"
        (source / "nested").mkdir(parents=True)
        (source / "nested/file.txt").write_text("evidence\n", encoding="utf-8")
        target = self.root / "target"
        campaign._copy_tree_exact(source, target)
        self.assertEqual((target / "nested/file.txt").read_text(encoding="utf-8"), "evidence\n")

    def producer_capture_fixture(self) -> tuple[dict, Path, str]:
        plan = self.plan()
        run_id = campaign.EXPECTED_RUN_ORDER[0]
        row = next(item for item in plan["runs"] if item["run_id"] == run_id)
        producer_output = self.root / "producer-output"
        raw = producer_output / "runs" / run_id
        workspace = producer_output / "arms" / row["arm_id"] / "workspace"
        for name in (
            "workspace-initial-manifest.json",
            "workspace-final-manifest.json",
            "evidence-manifest.json",
            "trace.json",
            "usage-receipt.json",
        ):
            write_json(raw / name, {"name": name})
        (workspace / "nested").mkdir(parents=True)
        (workspace / "nested" / "deliverable.txt").write_text("complete\n", encoding="utf-8")
        return {"run_plan": plan}, producer_output, run_id

    def test_episode_capture_publishes_one_complete_directory_atomically(self) -> None:
        freeze, producer_output, run_id = self.producer_capture_fixture()
        campaign_root = self.root / "campaign"
        with (
            mock.patch.object(campaign, "validate_schema"),
            mock.patch.object(campaign.evaluation, "_pilot_validate_final_manifest"),
        ):
            binding = campaign.capture_episode(
                freeze=freeze,
                campaign_root=campaign_root,
                producer_output=producer_output,
                run_id=run_id,
            )
        episode_root = campaign_root / "producer-episodes" / run_id
        self.assertEqual(
            {path.name for path in episode_root.iterdir()},
            {"artifacts", "workspace", "episode.json"},
        )
        self.assertEqual(binding, json.loads((episode_root / "episode.json").read_text(encoding="utf-8")))
        self.assertTrue((episode_root / "artifacts" / "trace.json").is_file())
        self.assertTrue((episode_root / "workspace" / "nested" / "deliverable.txt").is_file())
        self.assertEqual(list((campaign_root / "producer-episodes").glob(".*.staging-*")), [])

    def test_episode_capture_failure_leaves_no_published_or_staged_artifacts(self) -> None:
        freeze, producer_output, run_id = self.producer_capture_fixture()
        campaign_root = self.root / "campaign"
        real_copy = campaign._copy_tree_exact
        calls = 0

        def fail_second_copy(source: Path, target: Path) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise campaign.CampaignError("injected workspace snapshot failure")
            real_copy(source, target)

        with (
            mock.patch.object(campaign, "validate_schema"),
            mock.patch.object(campaign, "_copy_tree_exact", side_effect=fail_second_copy),
        ):
            with self.assertRaisesRegex(campaign.CampaignError, "injected workspace snapshot failure"):
                campaign.capture_episode(
                    freeze=freeze,
                    campaign_root=campaign_root,
                    producer_output=producer_output,
                    run_id=run_id,
                )
        capture_root = campaign_root / "producer-episodes"
        self.assertTrue(capture_root.is_dir())
        self.assertEqual(list(capture_root.iterdir()), [])
        self.assertFalse((campaign_root / "producer-artifacts").exists())
        self.assertFalse((campaign_root / "episode-workspaces").exists())

    def test_evaluation_input_copies_external_frozen_inputs_into_read_only_bundle(self) -> None:
        campaign_root = self.root / "campaign"
        campaign_root.mkdir()
        frozen_root = self.root / "outside-freeze"
        bindings = {}
        originals = {}
        for name, filename in campaign.FROZEN_EVALUATION_INPUTS.items():
            source = frozen_root / filename
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes((name + "\r\n").encode("utf-8"))
            originals[name] = source.read_bytes()
            bindings[name] = (source, {"path": filename, "sha256": campaign.sha256_file(source)})
        freeze = {"bindings": bindings}

        authority_roots = {}
        for role in ("calibration", "producer", "reviewer"):
            root = campaign_root / role
            authority_roots[role] = root
            for name in ("grant.json", "ledger-anchor.json", "spend-summary.json"):
                write_json(root / name, {"role": role, "name": name})
        oracle_root = campaign_root / "oracles"
        for case_id in campaign.CASE_ORDER:
            for protocol in ("v1", "v2"):
                arm_id = f"PL-{case_id}-P01-{protocol}"
                write_json(oracle_root / f"{arm_id}.json", {"arm_id": arm_id})
        review_results = campaign_root / "review-results"
        reviewer_output = campaign_root / "reviewer-output"
        for case_id in campaign.REVIEW_CASES:
            pair_id = f"PL-{case_id}-P01"
            write_json(campaign_root / "review-input" / pair_id / "blind-manifest.json", {"pair_id": pair_id})
            write_json(review_results / f"{pair_id}-review-result.json", {"pair_id": pair_id})
            write_json(reviewer_output / f"{pair_id}-review" / "usage-receipt.json", {"pair_id": pair_id})
        review_seal = campaign_root / "review-seal.json"
        write_json(review_seal, {"sealed": True})

        with (
            mock.patch.object(campaign, "load_episode_bindings", return_value=[]),
            mock.patch.object(campaign, "validate_schema"),
        ):
            manifest = campaign.assemble_evaluation_input(
                freeze=freeze,
                campaign_root=campaign_root,
                authority_roots=authority_roots,
                oracle_root=oracle_root,
                review_results_root=review_results,
                reviewer_output_root=reviewer_output,
                review_seal_path=review_seal,
                output=campaign_root / "evaluation-input.json",
            )
        for name, field in (
            ("scenarios", "pilot_scenarios"),
            ("run_plan", "pilot_run_plan"),
            ("evaluator", "pilot_evaluator"),
            ("calibration_result", "calibration_result"),
        ):
            copied = campaign_root / manifest[field]["path"]
            self.assertTrue(copied.is_relative_to(campaign_root))
            self.assertEqual(copied.read_bytes(), originals[name])
            self.assertEqual(os.stat(copied).st_mode & 0o222, 0)
        self.assertEqual(list(campaign_root.glob(".frozen-evaluation-inputs.staging-*")), [])

    def test_frozen_bundle_copy_failure_cleans_read_only_staging(self) -> None:
        campaign_root = self.root / "campaign"
        campaign_root.mkdir()
        frozen_root = self.root / "outside-freeze"
        bindings = {}
        for name, filename in campaign.FROZEN_EVALUATION_INPUTS.items():
            source = frozen_root / filename
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes((name + "\n").encode("utf-8"))
            bindings[name] = (source, {"path": filename, "sha256": campaign.sha256_file(source)})
        calls = 0
        real_read_only = campaign._make_read_only

        def fail_after_read_only(path: Path) -> None:
            nonlocal calls
            calls += 1
            real_read_only(path)
            if calls == 2:
                raise campaign.CampaignError("injected bundle copy failure")

        with mock.patch.object(campaign, "_make_read_only", side_effect=fail_after_read_only):
            with self.assertRaisesRegex(campaign.CampaignError, "injected bundle copy failure"):
                campaign._ensure_frozen_bundle(
                    freeze={"bindings": bindings},
                    campaign_root=campaign_root,
                )
        self.assertFalse((campaign_root / "frozen-evaluation-inputs").exists())
        self.assertEqual(list(campaign_root.glob(".frozen-evaluation-inputs.staging-*")), [])

    def minimal_freeze(self) -> dict:
        assignments = json.loads((EXPERIMENTS / "pilot-evaluator-manifest.json").read_text())["blind_assignments"]
        return {
            "scenarios": {"cases": []},
            "evaluator": {"blind_assignments": assignments},
        }

    def test_decode_requires_complete_seal_before_reading_assignments(self) -> None:
        seal = {
            "schema_version": "1.0",
            "experiment_id": campaign.CAMPAIGN_ID,
            "reviewer_authority": {
                "grant_sha256": "1" * 64,
                "ledger_anchor_sha256": "2" * 64,
                "spend_summary_sha256": "3" * 64,
            },
            "pairs": [],
            "assignments_decoded": False,
            "aggregate_sha256": campaign.sha256_bytes(campaign.canonical_bytes([])),
            "sealed_at": "2026-08-05T00:00:00Z",
        }
        path = self.root / "seal.json"
        write_json(path, seal)
        with mock.patch.object(campaign, "_scenario_maps", side_effect=AssertionError("decoded early")):
            with self.assertRaises(campaign.CampaignError):
                campaign.decode_reviews(
                    freeze=self.minimal_freeze(),
                    campaign_root=self.root,
                    review_seal_path=path,
                    output=self.root / "decoded.json",
                )

    def test_report_writer_stops_and_records_no_formal_expansion(self) -> None:
        report = {"formal_execution_enabled": False, "decision": {"recommendation": "pilot-complete-await-user-decision"}}
        final_freeze = self.root / "final-freeze.json"
        evaluation_input = self.root / "evaluation-input.json"
        decoded = self.root / "decoded.json"
        for path in (final_freeze, evaluation_input, decoded):
            write_json(path, {"x": path.stem})
        observations = self.root / "observations"
        attestations = self.root / "attestations"
        oracles = self.root / "oracles"
        for case_id in campaign.CASE_ORDER:
            for protocol in ("v1", "v2"):
                arm_id = f"PL-{case_id}-P01-{protocol}"
                for root in (observations, attestations, oracles):
                    write_json(root / f"{arm_id}.json", {"arm_id": arm_id})
        with mock.patch.object(campaign.evaluation, "evaluate_pilot", return_value=report):
            result, evidence = campaign.write_report_and_stop(
                campaign_root=self.root,
                final_freeze_path=final_freeze,
                evaluation_input_path=evaluation_input,
                decoded_reviews_path=decoded,
                observations_root=observations,
                attestations_root=attestations,
                oracle_root=oracles,
                report_path=self.root / "pilot-report.json",
                evidence_manifest_path=self.root / "campaign-evidence.json",
            )
        self.assertIs(result, report)
        self.assertEqual(evidence["campaign_status"], "pilot-complete-stopped")
        self.assertTrue(evidence["stop_after_report"])
        self.assertFalse(evidence["formal_execution_enabled"])
        self.assertEqual(evidence["next_action"], "await-user-decision")
        self.assertEqual(len(evidence["files"]), 40)


if __name__ == "__main__":
    unittest.main()
