from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
EXPERIMENTS = ROOT / "skills" / "create-loop" / "tests" / "experiments"
sys.path.insert(0, str(EXPERIMENTS))

import pilot_harness as pilot  # noqa: E402
import pilot_freeze as freeze  # noqa: E402


class PilotHarnessTests(unittest.TestCase):
    def load(self, name: str) -> dict:
        return json.loads((EXPERIMENTS / name).read_text(encoding="utf-8"))

    def test_repository_plan_has_exact_fixed_identity_and_order(self) -> None:
        preregistration, scenarios, plan = pilot.load_and_validate(EXPERIMENTS)
        self.assertEqual((plan["pair_count"], plan["arm_count"], plan["producer_episode_count"]), (6, 12, 18))
        self.assertEqual(len(plan["arms"]), 12)
        self.assertEqual(len(plan["runs"]), 18)
        self.assertEqual(
            [row["run_id"] for row in plan["runs"]],
            [
                "PL-N0-P01-v1-E01", "PL-N0-P01-v2-E01",
                "PL-T2-P01-v2-E01", "PL-T2-P01-v1-E01",
                "PL-T3-P01-v1-E01", "PL-T3-P01-v1-E02", "PL-T3-P01-v2-E01", "PL-T3-P01-v2-E02",
                "PL-T5-P01-v2-E01", "PL-T5-P01-v2-E02", "PL-T5-P01-v1-E01", "PL-T5-P01-v1-E02",
                "PL-S1-P01-v1-E01", "PL-S1-P01-v1-E02", "PL-S1-P01-v2-E01", "PL-S1-P01-v2-E02",
                "PL-T7-P01-v2-E01", "PL-T7-P01-v1-E01",
            ],
        )
        self.assertEqual(preregistration["pilot"]["review_calls"], 4)
        self.assertEqual(scenarios["review_count"], 4)

    def test_preregistration_locks_budget_provider_and_no_usd_measurement(self) -> None:
        preregistration, _ = pilot.load_and_validate_preregistration(EXPERIMENTS)
        self.assertEqual(preregistration["execution"]["model"], "gpt-5.6-sol")
        self.assertEqual(preregistration["execution"]["reasoning_effort"], "ultra")
        self.assertEqual(preregistration["budgets"]["hard"], {"max_calls": 126, "max_total_tokens": 7_560_000, "max_wall_seconds": 113_400})
        self.assertEqual(preregistration["budgets"]["pilot"]["max_calls"], 23)
        self.assertEqual(preregistration["budgets"]["pilot"]["max_total_tokens"], 1_330_000)
        self.assertEqual(preregistration["budgets"]["pilot"]["max_wall_seconds"], 20_100)
        self.assertEqual(preregistration["measurement_policy"]["usd_cost"], "not-measured")
        self.assertFalse(preregistration["formal_execution_enabled"])
        self.assertFalse(preregistration["formal_experiment"]["independent_real_task_claim"])

    def test_plan_tampering_and_mismatched_episode_fail_closed(self) -> None:
        preregistration, scenarios, plan = pilot.load_and_validate(EXPERIMENTS)
        plan["runs"][0]["protocol"] = "v2"
        with self.assertRaisesRegex(pilot.PilotError, "deterministic frozen plan"):
            pilot.validate_run_plan(plan, preregistration, scenarios, experiment_dir=EXPERIMENTS)
        with self.assertRaisesRegex(pilot.PilotError, "episode_id does not match"):
            pilot.select_episode(self.load("pilot-run-plan.json"), "PL-T3-P01-v1-E02", "E01")

    def test_execute_without_explicit_flag_never_launches_adapter(self) -> None:
        with mock.patch.object(pilot.subprocess, "run", side_effect=AssertionError("launched")):
            with self.assertRaisesRegex(pilot.PilotError, "explicit --execute"):
                pilot.execute_one(
                    experiment_dir=EXPERIMENTS,
                    run_plan_path=EXPERIMENTS / "pilot-run-plan.json",
                    run_id="PL-N0-P01-v1-E01",
                    episode_id="E01",
                    authorization=Path("missing-grant.json"),
                    authority_freeze=Path("missing-final-freeze.json"),
                    execution_root=Path("missing-execution"),
                    output_dir=Path("missing-output"),
                    codex_executable="codex",
                    execute=False,
                )

    def test_adapter_command_delegates_exactly_one_episode_without_usd(self) -> None:
        preregistration = self.load("pilot-preregistration.json")
        plan = self.load("pilot-run-plan.json")
        with mock.patch.object(pilot, "_bound_file", return_value=EXPERIMENTS / "codex_exec_adapter.py"):
            command = pilot.adapter_command(
                experiment_dir=EXPERIMENTS,
                run_plan_path=EXPERIMENTS / "pilot-run-plan.json",
                preregistration=preregistration,
                plan=plan,
                run_id="PL-T5-P01-v2-E02",
                episode_id="E02",
                authorization=Path("grant.json"),
                authority_freeze=Path("final-freeze.json"),
                execution_root=Path("execution"),
                output_dir=Path("output"),
                codex_executable="fake-codex",
            )
        self.assertEqual(command.count("--run-id"), 1)
        self.assertEqual(command[command.index("--run-id") + 1], "PL-T5-P01-v2-E02")
        self.assertEqual(command[command.index("--episode-id") + 1], "E02")
        self.assertEqual(command[command.index("--authority-freeze") + 1], "final-freeze.json")
        self.assertNotIn("cost", " ".join(command).lower())
        self.assertNotIn("usd", " ".join(command).lower())

    def test_authority_failure_precedes_static_profile_validation_and_adapter_launch(self) -> None:
        authorization = Path("execution/grant.json")
        authority_freeze = Path("final-freeze.json")
        with (
            mock.patch.object(
                freeze,
                "validate_grant_authority",
                side_effect=freeze.PilotFreezeError("freeze drifted"),
            ) as authority,
            mock.patch.object(pilot, "load_and_validate", side_effect=AssertionError("provider/profile read")),
            mock.patch.object(pilot, "adapter_command", side_effect=AssertionError("adapter command built")),
            mock.patch.object(pilot.subprocess, "run", side_effect=AssertionError("adapter launched")) as launch,
        ):
            with self.assertRaisesRegex(pilot.PilotError, "producer grant authority is invalid"):
                pilot.execute_one(
                    experiment_dir=EXPERIMENTS,
                    run_plan_path=EXPERIMENTS / "pilot-run-plan.json",
                    run_id="PL-N0-P01-v1-E01",
                    episode_id="E01",
                    authorization=authorization,
                    authority_freeze=authority_freeze,
                    execution_root=Path("execution"),
                    output_dir=Path("output"),
                    codex_executable="codex",
                    execute=True,
                )
        authority.assert_called_once_with(
            authorization,
            authority_freeze,
            expected_role="producer",
            experiment_dir=EXPERIMENTS,
        )
        launch.assert_not_called()

    def test_execute_cli_checks_authority_before_preregistration_or_launch(self) -> None:
        with (
            mock.patch.object(
                freeze,
                "validate_grant_authority",
                side_effect=freeze.PilotFreezeError("freeze drifted"),
            ),
            mock.patch.object(
                pilot,
                "load_and_validate_preregistration",
                side_effect=AssertionError("provider/profile read"),
            ) as preregistration,
            mock.patch.object(pilot.subprocess, "run", side_effect=AssertionError("adapter launched")) as launch,
        ):
            result = pilot.main([
                "--experiment-dir", str(EXPERIMENTS),
                "execute",
                "--run-plan", str(EXPERIMENTS / "pilot-run-plan.json"),
                "--run-id", "PL-N0-P01-v1-E01",
                "--episode-id", "E01",
                "--authorization", "execution/grant.json",
                "--authority-freeze", "final-freeze.json",
                "--execution-root", "execution",
                "--output-dir", "output",
                "--execute",
            ])
        self.assertEqual(result, 2)
        preregistration.assert_not_called()
        launch.assert_not_called()

    def test_cli_plan_is_read_only_and_matches_frozen_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "plan.json"
            result = subprocess.run(
                [sys.executable, str(EXPERIMENTS / "pilot_harness.py"), "plan", "--output", str(output)],
                text=True,
                capture_output=True,
                check=False,
                env={**dict(__import__("os").environ), "PYTHONDONTWRITEBYTECODE": "1"},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_bytes(), (EXPERIMENTS / "pilot-run-plan.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
