from __future__ import annotations

import json
import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = SKILL_ROOT / "tests" / "experiments"
sys.path.insert(0, str(EXPERIMENTS))

import pilot_runners as runners  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(runners.canonical_bytes(value))


class PilotRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_provider_observation_requires_direct_identity_evidence(self) -> None:
        records = [
            {"type": "response.started", "provider_request_id": "request-1"},
            {"type": "turn.completed", "provider_request_id": "request-1"},
        ]
        self.assertEqual(
            runners._provider_observations(records, "request-1"),
            [
                {"event_type": "response.started", "field": "provider_request_id"},
                {"event_type": "turn.completed", "field": "provider_request_id"},
            ],
        )
        with self.assertRaisesRegex(runners.RunnerError, "no source event"):
            runners._provider_observations(records, "missing")

    def test_workspace_population_is_atomic_and_recoverable_before_reservation(self) -> None:
        root = self.root / "review-call"
        root.mkdir()
        schema = EXPERIMENTS / "pilot-review-claim.schema.json"
        identity = runners._population_identity(
            run_id="PL-T2-P01-review", episode_id="review", role="reviewer",
            prompt="review\n", output_schema=schema,
        )
        attempts = 0

        def interrupted(staging: Path) -> None:
            nonlocal attempts
            attempts += 1
            (staging / "partial.txt").write_text("partial\n", encoding="utf-8")
            raise RuntimeError("simulated population interruption")

        with self.assertRaisesRegex(RuntimeError, "population interruption"):
            runners._materialize_workspace(
                root=root, identity=identity, workspace_populator=interrupted,
            )
        self.assertEqual(attempts, 1)
        self.assertFalse((root / "workspace").exists())
        self.assertFalse((root / "workspace-population-seal.json").exists())

        def complete(staging: Path) -> None:
            (staging / "context").mkdir()
            (staging / "context/task.md").write_text("task\n", encoding="utf-8")

        workspace, seal = runners._materialize_workspace(
            root=root, identity=identity, workspace_populator=complete,
        )
        self.assertTrue(workspace.is_dir())
        self.assertTrue(seal.is_file())
        seal_document = json.loads(seal.read_text(encoding="utf-8"))
        self.assertEqual(seal_document["workspace_aggregate_sha256"], runners.adapter._snapshot_tree(workspace)["aggregate_sha256"])
        before = runners.sha256_file(seal)
        with mock.patch.object(runners, "tempfile") as forbidden_staging:
            recovered, recovered_seal = runners._materialize_workspace(
                root=root, identity=identity, workspace_populator=complete,
            )
        forbidden_staging.mkdtemp.assert_not_called()
        self.assertEqual(recovered, workspace)
        self.assertEqual(recovered_seal, seal)
        self.assertEqual(runners.sha256_file(seal), before)

        (workspace / "context/task.md").write_text("drift\n", encoding="utf-8")
        with self.assertRaisesRegex(runners.RunnerError, "drifted from its population seal"):
            runners._materialize_workspace(
                root=root, identity=identity, workspace_populator=complete,
            )

    def test_population_schema_accepts_producer_and_evidence_role(self) -> None:
        identity = runners._population_identity(
            run_id="PL-N0-P01-v2-E01", episode_id="E01", role="producer",
            prompt="work\n", output_schema=EXPERIMENTS / "completion-claim.schema.json",
        )
        root = self.root / "producer-call"
        root.mkdir()
        identity.update({
            "protocol_bundle_sha256": "5" * 64,
            "protocol_entrypoint_sha256": "6" * 64,
            "protocol_access": {
                "entrypoint": "../protocol-bundle/SKILL.md",
                "access_available": True,
                "understanding_claimed": False,
            },
            "injection_receipt_sha256": None,
        })
        workspace, seal_path = runners._materialize_workspace(
            root=root,
            identity=identity,
            workspace_populator=lambda staging: (staging / "task.txt").write_text(
                "task\n", encoding="utf-8"
            ),
        )
        self.assertTrue(workspace.is_dir())
        evidence = {
            "schema_version": "1.0",
            "run_id": identity["run_id"],
            "episode_id": identity["episode_id"],
            "attempt_id": "attempt-1",
            "role": "producer",
            "initial_workspace_manifest": {"path": "initial.json", "sha256": "1" * 64},
            "final_workspace_manifest": {"path": "final.json", "sha256": "2" * 64},
            "workspace_population_seal": {
                "path": seal_path.name,
                "sha256": runners.sha256_file(seal_path),
            },
            "structured_claim": {"path": "claim.json", "sha256": "3" * 64},
            "files": [{
                "role": "workspace_population_seal",
                "path": seal_path.name,
                "sha256": runners.sha256_file(seal_path),
            }],
            "aggregate_sha256": "4" * 64,
        }
        runners._validate_schema(evidence, runners.EVIDENCE_SCHEMA, "producer evidence")

    def test_review_context_rejects_protocol_claim_control_and_version_disclosure(self) -> None:
        safe = self.root / "task.md"
        safe.write_text("Judge A and B against the invoice behavior rubric.\n", encoding="utf-8")
        artifact = self.root / "A.json"
        artifact.write_text('{"files":[]}\n', encoding="utf-8")
        blind = {
            "delivered_context": [{"path": "task.md", "sha256": runners.sha256_file(safe), "purpose": "neutral task"}],
            "presented": [{"label": "A", "artifact": {"path": "A.json", "sha256": runners.sha256_file(artifact)}}],
        }
        runners._review_context_check(self.root, blind)
        for name, content in (
            ("protocol-bundle/SKILL.md", "neutral"),
            (".agents/state.json", "neutral"),
            ("claim.json", "completion_claimed=true"),
            ("version.txt", "create-loop v2"),
        ):
            with self.subTest(name=name):
                path = self.root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                changed = json.loads(json.dumps(blind))
                changed["delivered_context"] = [{"path": name.replace("\\", "/"), "sha256": runners.sha256_file(path), "purpose": "neutral task"}]
                with self.assertRaises(runners.RunnerError):
                    runners._review_context_check(self.root, changed)

    def observation(self, case_id: str = "T2") -> dict:
        criteria = [
            {"criterion_id": f"{case_id}-C1", "kind": "required", "statement": "behavior", "measurement": "hidden-test"},
            {"criterion_id": f"{case_id}-C2", "kind": "required", "statement": "semantic", "measurement": "trace-review"},
        ]
        return {
            "schema_version": "1.0", "experiment_id": "create-loop-v1-v2-real-task-pilot-2026",
            "arm_id": f"PL-{case_id}-P01-v2", "pair_id": f"PL-{case_id}-P01", "case_id": case_id,
            "protocol": "v2", "final_episode_id": "E02" if case_id in {"T3", "T5", "S1"} else "E01",
            "trace_sha256": "1" * 64, "initial_workspace_manifest_sha256": "2" * 64,
            "final_workspace_manifest_sha256": "3" * 64, "evidence_manifest_sha256": "4" * 64,
            "evaluator_manifest_sha256": "5" * 64, "criteria": criteria, "hidden_checks": [],
            "workspace_changes": {"added": [], "modified": [], "deleted": []},
            "s1": None, "evidence_refs": ["trace:1"], "observed_at": "2026-08-05T00:00:00Z",
        }

    def judgment(self, observation_path: Path, case_id: str = "T2") -> dict:
        safety = {
            "authorization_omission": None, "in_doubt_effect_omission": None,
            "duplicate_effect": None, "effect_execution_count": None,
            "rationale": "No effect module is in scope.", "evidence_refs": [],
        }
        return {
            "schema_version": "1.0", "experiment_id": "create-loop-v1-v2-real-task-pilot-2026",
            "arm_id": f"PL-{case_id}-P01-v2", "observation_sha256": runners.sha256_file(observation_path),
            "evaluator": {"id": "evaluator-1", "kind": "model"},
            "criterion_results": [
                {"criterion_id": f"{case_id}-C1", "verdict": "satisfied", "rationale": "Hidden fact passed.", "evidence_refs": ["hidden:C1"]},
                {"criterion_id": f"{case_id}-C2", "verdict": "satisfied", "rationale": "Trace evidence supports the claim.", "evidence_refs": ["trace:C2"]},
            ],
            "safety": safety, "created_at": "2026-08-05T00:01:00Z",
        }

    def test_oracle_finalize_requires_semantic_trace_judgment_and_derives_goal(self) -> None:
        observation_path = self.root / "observation.json"
        judgment_path = self.root / "judgment.json"
        output = self.root / "oracle.json"
        write_json(observation_path, self.observation())
        judgment = self.judgment(observation_path)
        judgment["criterion_results"][1]["verdict"] = "indeterminate"
        write_json(judgment_path, judgment)
        with self.assertRaisesRegex(runners.RunnerError, "explicit evaluator judgment"):
            runners.finalize_oracle(observation_path=observation_path, judgment_path=judgment_path, output=output)
        judgment_path.unlink()
        judgment["criterion_results"][1]["verdict"] = "satisfied"
        write_json(judgment_path, judgment)
        result = runners.finalize_oracle(observation_path=observation_path, judgment_path=judgment_path, output=output)
        self.assertTrue(result["goal_satisfied"])
        self.assertTrue(output.is_file())

    def test_s1_failure_produces_a_violated_oracle_instead_of_an_instrument_error(self) -> None:
        observation = self.observation("S1")
        observation["s1"] = {
            "interruption_manifest_sha256": "6" * 64,
            "effect_execution_count": 2,
            "operation_ids": ["pilot-credit-001", "pilot-credit-001-duplicate"],
            "duplicate_effect": True,
        }
        observation_path = self.root / "s1-observation.json"
        write_json(observation_path, observation)
        judgment = self.judgment(observation_path, "S1")
        judgment["safety"] = {
            "authorization_omission": False, "in_doubt_effect_omission": False,
            "duplicate_effect": True, "effect_execution_count": 2,
            "rationale": "Reality was inspected.", "evidence_refs": ["reality:account"],
        }
        judgment_path = self.root / "s1-judgment.json"
        write_json(judgment_path, judgment)
        result = runners.finalize_oracle(
            observation_path=observation_path, judgment_path=judgment_path,
            output=self.root / "s1-oracle.json",
        )
        self.assertFalse(result["goal_satisfied"])
        self.assertTrue(result["safety"]["duplicate_effect"])
        self.assertEqual(result["safety"]["effect_execution_count"], 2)
        self.assertTrue(any(item["verdict"] == "violated" for item in result["criterion_results"]))

    def test_hidden_checks_override_only_their_explicit_criteria(self) -> None:
        observation = self.observation("T2")
        observation["hidden_checks"] = [{
            "check_id": "T2-HC1", "criterion_refs": ["T2-C1"], "kind": "node",
            "command": ["node", "hidden_test.mjs"], "script_sha256": "6" * 64,
            "exit_code": 1,
            "stdout": {"path": "stdout.txt", "sha256": "7" * 64},
            "stderr": {"path": "stderr.txt", "sha256": "8" * 64},
            "passed": False,
        }]
        observation_path = self.root / "mapped-observation.json"
        write_json(observation_path, observation)
        judgment = self.judgment(observation_path, "T2")
        judgment["criterion_results"][1]["verdict"] = "satisfied"
        judgment_path = self.root / "mapped-judgment.json"
        write_json(judgment_path, judgment)
        result = runners.finalize_oracle(
            observation_path=observation_path, judgment_path=judgment_path,
            output=self.root / "mapped-oracle.json",
        )
        self.assertEqual(
            [item["verdict"] for item in result["criterion_results"]],
            ["violated", "satisfied"],
        )
        self.assertFalse(result["goal_satisfied"])

    def test_review_seal_requires_all_four_pairs_before_decode(self) -> None:
        with self.assertRaisesRegex(runners.RunnerError, "all four exact"):
            runners.seal_reviews(
                experiment_dir=EXPERIMENTS, execution_root=self.root / "execution",
                input_root=self.root, pair_bindings=[], output=self.root / "seal.json",
            )

    def test_review_seal_binds_receipt_to_exact_evidence_manifest(self) -> None:
        pair_ids = tuple(runners.REVIEW_PAIRS)
        execution_root = self.root / "execution"
        input_root = self.root / "inputs"
        input_root.mkdir()
        (execution_root / "grant.json").parent.mkdir(parents=True)
        write_json(execution_root / "grant.json", {
            "role": "reviewer", "experiment_id": "pilot-test",
        })
        (execution_root / "ledger-anchor.json").write_text("{}\n", encoding="utf-8")
        (execution_root / "spend-summary.json").write_text("{}\n", encoding="utf-8")
        bindings = []
        for pair_id in pair_ids:
            pair_root = input_root / pair_id
            pair_root.mkdir()
            blind = pair_root / "blind.json"
            result = pair_root / "result.json"
            receipt = pair_root / "usage-receipt.json"
            write_json(blind, {"pair_id": pair_id})
            write_json(receipt, {
                "run_id": f"{pair_id}-review", "episode_id": "review",
                "attempt_id": f"attempt-{pair_id}", "role": "reviewer",
                "response_sha256": "a" * 64,
                "evidence_manifest_sha256": "0" * 64,
            })
            write_json(pair_root / "evidence-manifest.json", {"invalid": True})
            write_json(result, {
                "pair_id": pair_id,
                "blind_manifest_sha256": runners.sha256_file(blind),
                "review_response_sha256": "a" * 64,
                "reviewer": {"receipt_sha256": runners.sha256_file(receipt)},
            })
            bindings.append((pair_id, blind, result, receipt))
        with (
            mock.patch.object(runners.guard, "replay", return_value={
                "settled_call_ids": [f"{pair_id}-review:review" for pair_id in pair_ids],
                "in_doubt_attempt_ids": [],
            }),
            mock.patch.object(runners.guard, "load_grant", return_value={
                "role": "reviewer", "experiment_id": "pilot-test",
            }),
            mock.patch.object(runners, "_validate_schema"),
            mock.patch.object(runners, "_review_context_check"),
        ):
            with self.assertRaisesRegex(
                runners.RunnerError, "receipt hash drifted|receipt evidence hash drifted"
            ):
                runners.seal_reviews(
                    experiment_dir=EXPERIMENTS,
                    execution_root=execution_root,
                    input_root=input_root,
                    pair_bindings=bindings,
                    output=self.root / "seal.json",
                )

    def test_review_requires_os_isolation_before_loading_any_provider_authority(self) -> None:
        with self.assertRaisesRegex(runners.RunnerError, "requires WSL2 bubblewrap"):
            runners.run_review(
                experiment_dir=EXPERIMENTS,
                authorization=self.root / "missing-grant.json",
                authority_freeze=self.root / "missing-final-freeze.json",
                execution_root=self.root / "missing-execution",
                input_root=self.root,
                blind_manifest=self.root / "missing-blind.json",
                output_root=self.root / "output",
                codex_executable="codex",
            )

    def test_calibration_requires_stable_authority_root_before_loading_runtime(self) -> None:
        execution_root = self.root / "authority" / "calibration-execution"
        with mock.patch.object(
            runners, "_run_codex_call", side_effect=AssertionError("runtime loaded")
        ) as call:
            with self.assertRaisesRegex(runners.RunnerError, "stable authority root"):
                runners.run_calibration(
                    experiment_dir=EXPERIMENTS,
                    authorization=execution_root / "grant.json",
                    authority_freeze=self.root / "authority" / "pre-freeze.json",
                    execution_root=execution_root,
                    output_root=self.root / "copied-output",
                    codex_executable="codex",
                )
        call.assert_not_called()

    def test_calibration_rejects_pre_freeze_outside_stable_root_before_runtime(self) -> None:
        authority_root = self.root / "authority"
        execution_root = authority_root / "calibration-execution"
        with mock.patch.object(
            runners, "_run_codex_call", side_effect=AssertionError("runtime loaded")
        ) as call:
            with self.assertRaisesRegex(runners.RunnerError, "pre-freeze must remain"):
                runners.run_calibration(
                    experiment_dir=EXPERIMENTS,
                    authorization=execution_root / "grant.json",
                    authority_freeze=self.root / "outside" / "pre-freeze.json",
                    execution_root=execution_root,
                    output_root=authority_root,
                    codex_executable="codex",
                )
        call.assert_not_called()

    def test_runtime_authority_failure_precedes_harness_credentials_ledger_and_launch(self) -> None:
        cases = (
            ("calibration", "pre-freeze.json"),
            ("reviewer", "final-freeze.json"),
        )
        for role, freeze_name in cases:
            with self.subTest(role=role):
                execution_root = self.root / role / "execution"
                authorization = execution_root / "grant.json"
                authority_freeze = self.root / role / freeze_name
                with (
                    mock.patch.object(
                        runners.pilot_freeze,
                        "validate_grant_authority",
                        side_effect=runners.pilot_freeze.PilotFreezeError("invalid freeze"),
                    ) as validate_authority,
                    mock.patch.object(
                        runners.pilot_harness,
                        "load_and_validate",
                        side_effect=AssertionError("harness read before authority"),
                    ) as load_harness,
                    mock.patch.object(
                        runners.adapter,
                        "_clean_environment",
                        side_effect=AssertionError("CODEX_HOME read before authority"),
                    ) as clean_environment,
                    mock.patch.object(
                        runners.guard,
                        "initialize",
                        side_effect=AssertionError("ledger initialized before authority"),
                    ) as initialize,
                    mock.patch.object(
                        runners.guard,
                        "reserve",
                        side_effect=AssertionError("budget reserved before authority"),
                    ) as reserve,
                    mock.patch.object(
                        runners.adapter,
                        "_run_codex",
                        side_effect=AssertionError("provider launched before authority"),
                    ) as launch_codex,
                    mock.patch.object(
                        runners.review_isolation,
                        "launch_reviewer",
                        side_effect=AssertionError("reviewer launched before authority"),
                    ) as launch_reviewer,
                ):
                    with self.assertRaisesRegex(
                        runners.RunnerError, f"{role} authority freeze validation failed"
                    ):
                        runners._run_codex_call(
                            experiment_dir=EXPERIMENTS,
                            authorization=authorization,
                            authority_freeze=authority_freeze,
                            execution_root=execution_root,
                            output_root=self.root / role / "output",
                            run_id=(
                                "pilot-calibration"
                                if role == "calibration"
                                else "PL-T2-P01-review"
                            ),
                            episode_id="calibration" if role == "calibration" else "review",
                            role=role,
                            prompt="offline authority test\n",
                            output_schema=(
                                EXPERIMENTS / "completion-claim.schema.json"
                                if role == "calibration"
                                else EXPERIMENTS / "pilot-review-claim.schema.json"
                            ),
                            codex_executable="codex",
                            review_boundary={} if role == "reviewer" else None,
                        )
                validate_authority.assert_called_once_with(
                    authorization,
                    authority_freeze,
                    expected_role=role,
                    experiment_dir=EXPERIMENTS,
                )
                load_harness.assert_not_called()
                clean_environment.assert_not_called()
                initialize.assert_not_called()
                reserve.assert_not_called()
                launch_codex.assert_not_called()
                launch_reviewer.assert_not_called()

    def test_runtime_rejects_noncanonical_execution_root_before_harness_read(self) -> None:
        authorization = self.root / "authority" / "execution" / "grant.json"
        with (
            mock.patch.object(
                runners.pilot_freeze,
                "validate_grant_authority",
                return_value={},
            ) as validate_authority,
            mock.patch.object(
                runners.pilot_harness,
                "load_and_validate",
                side_effect=AssertionError("harness read before execution-root binding"),
            ) as load_harness,
        ):
            with self.assertRaisesRegex(
                runners.RunnerError, "not the canonical execution-root grant"
            ):
                runners._load_runtime(
                    EXPERIMENTS,
                    authorization,
                    self.root / "authority" / "pre-freeze.json",
                    self.root / "different-execution-root",
                    "calibration",
                )
        validate_authority.assert_called_once()

    def test_reviewer_timestamp_starts_after_isolation_preparation(self) -> None:
        run_id = "PL-T2-P01-review"
        episode_id = "review"
        output_root = self.root / "review-output"
        execution_root = self.root / "review-execution"
        grant = {
            "authorized_calls": [{"run_id": run_id, "episode_id": episode_id}],
            "limits": {"per_call": {"max_total_tokens": 100, "max_wall_seconds": 60}},
            "model": "gpt-5.6-sol",
            "reasoning_effort": "ultra",
            "cli_identity": {"sha256": "1" * 64},
        }
        environment = {
            "_CLI_IDENTITY": json.dumps({}),
            "_CLI_IDENTITY_PATH": "unused.json",
        }
        validated_boundary = {"fixture": "validated"}
        order: list[str] = []
        timestamps = iter((
            "2026-08-05T00:00:00.000000Z",
            "2026-08-05T00:00:03.000000Z",
        ))
        monotonic_values = iter((0.0, 3.0))

        def materialize(*, root, **_):
            workspace = root / "workspace"
            workspace.mkdir()
            seal = root / "workspace-population-seal.json"
            write_json(seal, {})
            return workspace, seal

        def prepare(**_):
            order.append("prepare")
            return object()

        def now_text(*_):
            order.append("timestamp")
            return next(timestamps)

        def monotonic():
            order.append("monotonic")
            return next(monotonic_values)

        def launch(**kwargs):
            order.append("launch")
            kwargs["raw_path"].write_text("{}\n", encoding="utf-8")
            kwargs["stderr_path"].write_bytes(b"")
            return 0, False, False, 0.25

        review_boundary = {
            "codex_package_wsl": "/package",
            "source_codex_home": "/codex-home",
            "distribution": "Ubuntu",
            "wsl_executable": "wsl.exe",
            "hidden_sentinel_wsl": "/hidden",
        }
        with (
            mock.patch.object(
                runners,
                "_load_runtime",
                return_value=(
                    {}, {}, grant, {}, "unused-profile", environment,
                    validated_boundary,
                ),
            ),
            mock.patch.object(
                runners.guard,
                "initialize",
                return_value={"settled_call_ids": [], "in_doubt_attempt_ids": []},
            ),
            mock.patch.object(runners.guard, "reserve"),
            mock.patch.object(runners, "_materialize_workspace", side_effect=materialize),
            mock.patch.object(runners, "_validate_schema"),
            mock.patch.object(runners, "_now_text", side_effect=now_text),
            mock.patch.object(runners.time, "monotonic", side_effect=monotonic),
            mock.patch.object(
                runners.review_isolation, "prepare_isolation", side_effect=prepare
            ),
            mock.patch.object(
                runners.review_isolation, "launch_reviewer", side_effect=launch
            ), mock.patch.object(
                runners.execution_boundary, "launch_prefix", return_value=["wrapper"]
            ),
        ):
            with self.assertRaisesRegex(
                runners.adapter.AdapterError, "unambiguous explicit usage record"
            ):
                runners._run_codex_call(
                    experiment_dir=EXPERIMENTS,
                    authorization=execution_root / "grant.json",
                    authority_freeze=self.root / "final-freeze.json",
                    execution_root=execution_root,
                    output_root=output_root,
                    run_id=run_id,
                    episode_id=episode_id,
                    role="reviewer",
                    prompt="review\n",
                    output_schema=EXPERIMENTS / "pilot-review-claim.schema.json",
                    codex_executable="codex",
                    review_boundary=review_boundary,
                )
        self.assertEqual(
            order,
            ["prepare", "timestamp", "monotonic", "launch", "monotonic", "timestamp"],
        )
        provider_return = json.loads(
            (output_root / run_id / "provider-return.json").read_text(encoding="utf-8")
        )
        self.assertEqual(provider_return["wall_seconds"], 3.0)
        self.assertEqual(provider_return["started_at"], "2026-08-05T00:00:00.000000Z")
        self.assertEqual(provider_return["ended_at"], "2026-08-05T00:00:03.000000Z")

    def test_cli_requires_explicit_authority_freeze_for_provider_commands(self) -> None:
        for command, extra in (
            (
                "calibrate",
                ["--output-root", str(self.root / "output")],
            ),
            (
                "review",
                [
                    "--input-root", str(self.root),
                    "--blind-manifest", str(self.root / "blind.json"),
                    "--output-root", str(self.root / "output"),
                    "--reviewer-codex-package-wsl", "/opt/codex/codex",
                    "--reviewer-codex-home", str(self.root / "codex-home"),
                    "--reviewer-hidden-sentinel-wsl", "/tmp/hidden",
                ],
            ),
        ):
            with (
                self.subTest(command=command),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as raised,
            ):
                runners.parser().parse_args(
                    [
                        command,
                        "--authorization", str(self.root / "grant.json"),
                        "--execution-root", str(self.root / "execution"),
                        *extra,
                    ]
                )
            self.assertEqual(raised.exception.code, 2)

    def test_hidden_check_layout_matches_evaluator_relative_workspace_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            staging = Path(temporary)
            script = EXPERIMENTS / "pilot-evaluator/T2/hidden_test.mjs"
            command, target = runners._prepare_hidden_check(
                check={"kind": "node"}, script=script, staging=staging,
            )
            self.assertEqual(command[0], "node")
            self.assertEqual(target.relative_to(staging).as_posix(), "pilot-evaluator/T2/hidden_test.mjs")
            self.assertEqual(
                (target.parents[2] / "workspace").resolve(),
                (staging / "workspace").resolve(),
            )


if __name__ == "__main__":
    unittest.main()
