from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = SKILL_ROOT / "tests" / "experiments"
sys.path.insert(0, str(EXPERIMENTS))

import evaluation  # noqa: E402
import deterministic_runner  # noqa: E402
import experiment_harness as harness  # noqa: E402
import execution_guard as guard  # noqa: E402
import freeze_experiment  # noqa: E402
import snapshot_tools  # noqa: E402
import workspace_builder as builder  # noqa: E402

REAL_DETERMINISTIC_RUN_SUITE = deterministic_runner.run_suite


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


class ExperimentEvaluationPureTests(unittest.TestCase):
    def test_oracle_verdict_means_the_declared_expectation_was_met(self) -> None:
        self.assertTrue(evaluation._expectation_is_satisfied({"expectation": "required", "verdict": "satisfied"}))
        self.assertTrue(evaluation._expectation_is_satisfied({"expectation": "forbidden", "verdict": "satisfied"}))
        self.assertFalse(evaluation._expectation_is_satisfied({"expectation": "forbidden", "verdict": "violated"}))


class ExperimentEvaluationTests(unittest.TestCase):
    _authoritative_suite_cache: dict[tuple[str, ...], dict] = {}

    @classmethod
    def _fixture_patches(cls, experiment_dir: Path) -> ExitStack:
        stack = ExitStack()
        for name, value in (
            ("CANDIDATE_SOURCE_PATH", experiment_dir / "candidate-source.json"),
            ("BASELINE_SOURCE_PATH", experiment_dir / "baseline-source.json"),
            ("BASELINE_ARCHIVE_PATH", experiment_dir / "baseline-source.tar"),
        ):
            stack.enter_context(mock.patch.object(builder, name, value))
        instrument_inputs = dict(snapshot_tools.EXPERIMENT_INSTRUMENT_INPUTS)
        instrument_inputs["codex_exec_adapter.py"] = "adapter"
        for owner in (snapshot_tools, harness):
            stack.enter_context(
                mock.patch.object(owner, "EXPERIMENT_INSTRUMENT_INPUTS", instrument_inputs)
            )
        return stack

    @classmethod
    def _replace_tree(cls, source: Path, destination: Path) -> None:
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination, copy_function=shutil.copy2)

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.fixture_temp = tempfile.TemporaryDirectory()
        fixture_root = Path(cls.fixture_temp.name)
        cls.active_experiment_dir = fixture_root / "active-experiments"
        cls.active_input_root = fixture_root / "active-inputs"
        cls.pristine_experiment_dir = fixture_root / "pristine-experiments"
        cls.pristine_input_root = fixture_root / "pristine-inputs"
        try:
            shutil.copytree(EXPERIMENTS, cls.active_experiment_dir, copy_function=shutil.copy2)
            cls.active_input_root.mkdir()
            with cls._fixture_patches(cls.active_experiment_dir):
                for path, data in freeze_experiment.compute_freeze(
                    experiment_dir=cls.active_experiment_dir,
                    skill_root=SKILL_ROOT,
                    repo_root=SKILL_ROOT.parents[1],
                ).items():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                bootstrap = cls(
                    methodName="test_recomputes_all_metrics_and_gates_without_producer_observations"
                )
                bootstrap.experiment_dir = cls.active_experiment_dir
                bootstrap.input_root = cls.active_input_root
                bootstrap.preregistration = bootstrap.load_experiment("preregistration.json")
                bootstrap.scenarios = bootstrap.load_experiment("scenarios.json")
                bootstrap.run_plan = harness.build_run_plan(
                    bootstrap.scenarios,
                    bootstrap.preregistration,
                    experiment_dir=bootstrap.experiment_dir,
                )
                write_json(bootstrap.input_root / "run-plan.json", bootstrap.run_plan)
                with mock.patch.object(
                    deterministic_runner,
                    "run_suite",
                    side_effect=bootstrap._cached_deterministic_suite,
                ):
                    bootstrap._build_complete_fixture_once()
            shutil.copytree(
                cls.active_experiment_dir,
                cls.pristine_experiment_dir,
                copy_function=shutil.copy2,
            )
            shutil.copytree(
                cls.active_input_root,
                cls.pristine_input_root,
                copy_function=shutil.copy2,
            )
        except BaseException:
            cls.fixture_temp.cleanup()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture_temp.cleanup()
        super().tearDownClass()

    def setUp(self) -> None:
        self.experiment_dir = self.active_experiment_dir
        self.input_root = self.active_input_root
        self._replace_tree(self.pristine_experiment_dir, self.experiment_dir)
        self._replace_tree(self.pristine_input_root, self.input_root)
        patchers = self._fixture_patches(self.experiment_dir)
        patchers.__enter__()
        self.addCleanup(patchers.__exit__, None, None, None)
        suite_patcher = mock.patch.object(
            deterministic_runner, "run_suite", side_effect=self._cached_deterministic_suite
        )
        suite_patcher.start()
        self.addCleanup(suite_patcher.stop)
        self.preregistration = self.load_experiment("preregistration.json")
        self.scenarios = self.load_experiment("scenarios.json")
        self.spec = self.load_experiment("evaluation-spec.json")
        self.run_plan = evaluation.load_json(self.input_root / "run-plan.json")

    def _restore_input_fixture(self) -> None:
        self._replace_tree(self.pristine_input_root, self.input_root)
        self.run_plan = evaluation.load_json(self.input_root / "run-plan.json")

    def _restore_experiment_fixture(self) -> None:
        self._replace_tree(self.pristine_experiment_dir, self.experiment_dir)
        self.preregistration = self.load_experiment("preregistration.json")
        self.scenarios = self.load_experiment("scenarios.json")
        self.spec = self.load_experiment("evaluation-spec.json")

    def _deterministic_suite_cache_key(
        self,
        experiment_dir: Path,
        preregistration: dict,
        protocol: str,
        *,
        catalog_path: Path,
        tool_profile_path: Path,
        candidate_skill_root: Path,
        runner_path: Path,
    ) -> tuple[str, ...]:
        source = preregistration["baseline" if protocol == "v1" else "candidate"][
            "source_snapshot"
        ]
        bindings = [
            experiment_dir / "instrument-manifest.json",
            experiment_dir / "deterministic-fixture-catalog.schema.json",
            experiment_dir / "tool-profile.schema.json",
            experiment_dir / "deterministic-case-result.schema.json",
            experiment_dir / "deterministic-authoritative-run.schema.json",
            catalog_path,
            tool_profile_path,
            runner_path,
            experiment_dir / source["manifest"]["path"],
        ]
        if source.get("archive") is not None:
            bindings.append(experiment_dir / source["archive"]["path"])
        if protocol == "v2":
            manifest = evaluation.load_json(experiment_dir / source["manifest"]["path"])
            bindings.extend(candidate_skill_root / entry["path"] for entry in manifest["files"])

        def safe_hash(path: Path) -> str:
            if not path.is_file() or path.is_symlink():
                raise deterministic_runner.DeterministicRunnerError(
                    f"cached deterministic input must be a regular non-symlink file: {path}"
                )
            return evaluation.sha256_file(path)

        return (
            protocol,
            evaluation.sha256_bytes(evaluation.canonical_bytes(preregistration)),
            *(safe_hash(path) for path in bindings),
        )

    def _cached_deterministic_suite(self, *args, **kwargs) -> dict:
        experiment_dir = Path(args[0]).resolve()
        preregistration = args[1]
        protocol = args[2]
        catalog_path = Path(kwargs["catalog_path"]).resolve()
        tool_profile_path = Path(kwargs["tool_profile_path"]).resolve()
        candidate_skill_root = Path(kwargs.get("candidate_skill_root", SKILL_ROOT)).resolve()
        runner_path = Path(kwargs.get("runner_path", deterministic_runner.__file__)).resolve()
        key = self._deterministic_suite_cache_key(
            experiment_dir,
            preregistration,
            protocol,
            catalog_path=catalog_path,
            tool_profile_path=tool_profile_path,
            candidate_skill_root=candidate_skill_root,
            runner_path=runner_path,
        )
        cached = self._authoritative_suite_cache.get(key)
        if cached is None:
            cached = REAL_DETERMINISTIC_RUN_SUITE(*args, **kwargs)
            self._authoritative_suite_cache[key] = copy.deepcopy(cached)
        return copy.deepcopy(cached)

    def load_experiment(self, name: str) -> dict:
        return json.loads((self.experiment_dir / name).read_text(encoding="utf-8"))

    def bind(self, path: Path, **identity: str) -> dict:
        return {**identity, "path": path.relative_to(self.input_root).as_posix(), "sha256": evaluation.sha256_file(path)}

    def criterion_results(self, scenario: dict) -> list[dict]:
        return [
            {"criterion": criterion, "expectation": expectation, "verdict": "satisfied", "evidence_refs": [f"evidence:{criterion}"]}
            for expectation, field in (("required", "required"), ("forbidden", "forbidden"))
            for criterion in scenario["oracle"][field]
        ]

    def measurements(self, scenario_id: int, protocol: str) -> dict:
        candidate = protocol == "v2"
        return {
            "false_completion": False if scenario_id in {1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14} else None,
            "authorization_or_effect_omission": False if scenario_id in {10, 12} else None,
            "deterministic_rejection_correct": True if scenario_id == 6 else None,
            "fact_checks_correct": 100 if scenario_id == 4 else None,
            "fact_checks_total": 100 if scenario_id == 4 else None,
            "recovery_tokens": (60 if candidate else 100) if scenario_id in {4, 10, 14} else None,
            "control_writes": (6 if candidate else 10) if scenario_id in {1, 2, 7, 11, 14} else None,
            "control_input_tokens": 6 if candidate else 10,
            "total_input_tokens": 100,
            "first_high_value_action_seconds": (6 if candidate else 10) if scenario_id in {1, 2} else None,
            "productive_work_units": (80 if candidate else 60) if scenario_id in {2, 3, 7, 8, 9, 11} else None,
            "total_work_units": 100 if scenario_id in {2, 3, 7, 8, 9, 11} else None,
            "unnecessary_user_interruptions": 0 if scenario_id in {3, 8, 9, 12} else None,
        }

    def trace(
        self,
        run: dict,
        artifact_sha: str,
        workspace_binding: dict,
        final_workspace_binding: dict,
        evidence_binding: dict,
        trace_source_binding: dict,
        adapter_sha256: str,
        usage_receipt_binding: dict,
        execution_authority: dict,
        cli_identity: dict,
        provider_profile: dict,
    ) -> dict:
        return {
            "schema_version": "2.0",
            "experiment_id": self.preregistration["experiment_id"],
            "preregistration_sha256": evaluation.sha256_bytes(evaluation.canonical_bytes(self.preregistration)),
            "run_plan_sha256": evaluation.sha256_bytes(evaluation.canonical_bytes(self.run_plan)),
            "pair_id": run["pair_id"],
            "run_id": run["run_id"],
            "episode_id": "E01",
            "scenario_id": run["scenario_id"],
            "scenario_slug": run["scenario_slug"],
            "protocol": run["protocol"],
            "repetition": run["repetition"],
            "pair_position": run["pair_position"],
            "pair_seed": run["pair_seed"],
            "role": "producer",
            "model": self.preregistration["execution_config"]["model"],
            "reasoning_effort": self.preregistration["execution_config"]["reasoning_effort"],
            "tool_profile": self.preregistration["execution_config"]["tool_profile"],
            "provider_profile": provider_profile,
            "cli_identity": cli_identity,
            "workspace_seed": run["pair_seed"],
            "input_sha256": run["input_sha256"],
            "baseline_source_sha256": self.preregistration["baseline"]["source_snapshot"]["aggregate_sha256"],
            "candidate_source_sha256": self.preregistration["candidate"]["source_snapshot"]["aggregate_sha256"],
            "instrument_manifest_sha256": self.preregistration["instrument_manifest"]["sha256"],
            "semantic_case_sha256": run["semantic_case_sha256"],
            "workspace_manifest": workspace_binding,
            "final_workspace_manifest": final_workspace_binding,
            "initial_workspace_manifest_sha256": workspace_binding["sha256"],
            "final_workspace_manifest_sha256": final_workspace_binding["sha256"],
            "evidence_manifest": evidence_binding,
            "evidence_manifest_sha256": evidence_binding["sha256"],
            "usage_receipt": usage_receipt_binding,
            "execution_authority": execution_authority,
            "adapter": {"id": "fixture", "version": "1", "sha256": adapter_sha256},
            "trace_source": trace_source_binding,
            "started_at": "2026-08-01T00:00:00Z",
            "ended_at": "2026-08-01T00:00:01Z",
            "budget": {"total_tokens_limit": 1, "seconds_limit": 1, "total_tokens_used": 0, "elapsed_seconds": 1},
            "events": [
                {"seq": 1, "ts": "2026-08-01T00:00:00Z", "kind": "adapter_started", "summary": "Started.", "payload_sha256": None},
                {"seq": 2, "ts": "2026-08-01T00:00:00Z", "kind": "model_request", "summary": "Bound request.", "payload_sha256": evaluation.sha256_bytes(f"request:{run['run_id']}".encode())},
                {"seq": 3, "ts": "2026-08-01T00:00:01Z", "kind": "model_response", "summary": "Bound response.", "payload_sha256": evaluation.sha256_bytes(f"response:{run['run_id']}".encode())},
                {"seq": 4, "ts": "2026-08-01T00:00:01Z", "kind": "deliverable", "summary": "Bound presented artifact.", "payload_sha256": artifact_sha},
                {"seq": 5, "ts": "2026-08-01T00:00:01Z", "kind": "evidence_frozen", "summary": "Bound evidence.", "payload_sha256": evidence_binding["sha256"]},
                {"seq": 6, "ts": "2026-08-01T00:00:01Z", "kind": "usage_settled", "summary": "Settled usage.", "payload_sha256": usage_receipt_binding["sha256"]},
                {"seq": 7, "ts": "2026-08-01T00:00:01Z", "kind": "adapter_finished", "summary": "Finished.", "payload_sha256": None},
            ],
            "outcome": {
                "status": "incomplete",
                "completion_claimed": False,
                "goal_satisfied": None,
                "evidence_refs": [],
                "violations": [],
                "deliverables": [],
                "blockers": [],
                "risks": [],
                "metric_observations": {metric: "not-measured" for metric in next(item for item in self.scenarios["scenarios"] if item["id"] == run["scenario_id"])["metrics"]},
            },
            "goal_satisfied": None,
        }

    def _store_fixture_settlement(
        self,
        execution_root: Path,
        grant: dict,
        receipt_path: Path,
        evidence_path: Path,
        *,
        call_number: int,
        reserved_at: datetime,
    ) -> None:
        receipt = evaluation.load_json(receipt_path)
        evidence = evaluation.load_json(evidence_path)
        evidence_name = f"evidence-{guard.sha256_bytes(guard.canonical_bytes(evidence))}.json"
        stored_evidence = execution_root / "evidence" / evidence_name
        receipt_name = f"receipt-{guard.sha256_bytes(guard.canonical_bytes(receipt))}.json"
        stored_receipt = execution_root / "receipts" / receipt_name
        reservation = {
            "calls": 1,
            "total_tokens": grant["limits"]["per_call"]["max_total_tokens"],
            "wall_seconds": grant["limits"]["per_call"]["max_wall_seconds"],
        }
        cumulative = {
            "calls": call_number,
            "total_tokens": call_number * reservation["total_tokens"],
            "wall_seconds": call_number * reservation["wall_seconds"],
        }
        with guard.execution_lock(execution_root):
            guard._append_record(
                execution_root,
                grant,
                "call_reserved",
                receipt["run_id"],
                receipt["attempt_id"],
                {"reservation": reservation, "cumulative_after": cumulative},
                episode_id=receipt["episode_id"],
                now=reserved_at,
            )
            guard._store_json(stored_evidence, evidence, "evidence manifest")
            guard._copy_evidence_files_into_store(evidence_path, stored_evidence, evidence)
            guard._store_json(stored_receipt, receipt, "receipt")
            guard._append_record(
                execution_root,
                grant,
                "call_settled",
                receipt["run_id"],
                receipt["attempt_id"],
                {
                    "receipt_path": receipt_name,
                    "receipt_sha256": evaluation.sha256_file(stored_receipt),
                    "evidence_path": evidence_name,
                    "evidence_sha256": evaluation.sha256_file(stored_evidence),
                    "actual": {"calls": 1, "total_tokens": 0, "wall_seconds": 1},
                    "cumulative_after": cumulative,
                    "outcome": "settled",
                },
                episode_id=receipt["episode_id"],
                now=reserved_at + timedelta(seconds=1),
            )

    def _build_complete_fixture_once(self) -> tuple[Path, dict]:
        prereg_sha = evaluation.sha256_bytes(evaluation.canonical_bytes(self.preregistration))
        run_plan_sha = evaluation.sha256_bytes(evaluation.canonical_bytes(self.run_plan))
        adapter_path = self.input_root / "execution" / "fixture-adapter.py"
        adapter_path.parent.mkdir(parents=True, exist_ok=True)
        adapter_path.write_text("# fixture adapter\n", encoding="utf-8", newline="\n")
        adapter_sha256 = evaluation.sha256_file(adapter_path)
        cli_path = self.input_root / "execution" / "cli-identity.json"
        provider_path = self.input_root / "execution" / "provider-profile.json"
        write_json(cli_path, {"id": "fixture-cli"})
        write_json(provider_path, {"id": "fixture-provider"})
        cli_identity = {"id": "fixture-cli", **self.bind(cli_path)}
        provider_profile = {"id": "fixture-provider", **self.bind(provider_path)}
        execution_root = self.input_root / "execution" / "authority"
        grant_input = self.input_root / "execution" / "authorization-grant.json"
        grant = {
            "schema_version": "2.0",
            "authorization_id": "authorization-1",
            "execution_id": "execution-1",
            "execution_root_sha256": guard._root_path_sha256(execution_root),
            "experiment_id": self.preregistration["experiment_id"],
            "preregistration_sha256": prereg_sha,
            "run_plan_sha256": run_plan_sha,
            "role": "producer",
            "adapter": {"id": "fixture", "version": "1", "sha256": adapter_sha256},
            "cli_identity": cli_identity,
            "provider_profile": provider_profile,
            "model": self.preregistration["execution_config"]["model"],
            "reasoning_effort": self.preregistration["execution_config"]["reasoning_effort"],
            "tool_profile": self.preregistration["execution_config"]["tool_profile"],
            "authorized_calls": [
                {"run_id": run["run_id"], "episode_id": "E01"}
                for run in sorted(self.run_plan["runs"], key=lambda item: item["run_id"])
            ],
            "limits": {
                "per_call": {"max_total_tokens": 1, "max_wall_seconds": 1},
                "total": {"max_calls": 84, "max_total_tokens": 84, "max_wall_seconds": 84},
            },
            "authorized_by": "unit-test",
            "authorized_at": "2026-07-31T23:59:00Z",
            "expires_at": "2026-08-02T00:00:00Z",
            "authority_evidence_sha256": "4" * 64,
        }
        write_json(grant_input, grant)
        guard.initialize(execution_root, grant_input, now=datetime(2026, 8, 1, tzinfo=timezone.utc))
        grant_path = execution_root / "grant.json"
        authorization_sha256 = evaluation.sha256_file(grant_path)
        trace_bindings = []
        usage_receipt_bindings = []
        materialized_workspace_bindings = []
        oracle_bindings = []
        evaluator_context_bindings = []
        trace_by_pair: dict[str, dict[str, tuple[Path, dict]]] = {}
        for run_index, run in enumerate(self.run_plan["runs"]):
            scenario = next(item for item in self.scenarios["scenarios"] if item["id"] == run["scenario_id"])
            workspace_manifest, files, presented_paths = builder.build_manifest(
                experiment_id=self.preregistration["experiment_id"],
                pair_id=run["pair_id"],
                scenario=scenario,
                protocol=run["protocol"],
                workspace_seed=run["pair_seed"],
                source_binding=self.preregistration[
                    "baseline" if run["protocol"] == "v1" else "candidate"
                ]["source_snapshot"],
                tool_profile_path=self.experiment_dir / self.preregistration["execution_config"]["tool_profile"]["path"],
                tool_profile_root=self.experiment_dir,
            )
            self.assertEqual(
                evaluation.sha256_bytes(builder.canonical_bytes(workspace_manifest)),
                run["workspace_manifest_sha256"],
            )
            workspace_path = self.input_root / "workspaces" / f"{run['run_id']}.json"
            workspace_path.parent.mkdir(parents=True, exist_ok=True)
            workspace_path.write_bytes(builder.canonical_bytes(workspace_manifest))
            workspace_root = self.input_root / "materialized" / run["run_id"]
            builder.materialize_workspace(workspace_root, files)
            presented_root = self.input_root / "presented-workspaces" / run["run_id"]
            shutil.copytree(workspace_root, presented_root)
            for relative in presented_paths:
                target = presented_root / relative
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(f"presented {run['run_id']}\n", encoding="utf-8", newline="\n")
            presented_artifact = builder.build_presented_artifact(
                presented_root, workspace_manifest, presented_paths
            )
            materialized_workspace_bindings.append({
                "run_id": run["run_id"],
                "path": workspace_root.relative_to(self.input_root).as_posix(),
                "manifest_sha256": evaluation.sha256_file(workspace_path),
            })
            presented_path = self.input_root / "presented" / run["run_id"] / f"{run['run_id']}.json"
            for relative in presented_paths:
                source = presented_root / relative
                target = presented_path.parent / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            write_json(presented_path, presented_artifact)
            artifact_sha = presented_artifact["aggregate_sha256"]
            attempt_id = f"attempt-{run['run_id']}"
            control_time = datetime(2026, 8, 1, tzinfo=timezone.utc) + timedelta(seconds=run_index * 2)
            receipt_started = control_time.isoformat().replace("+00:00", "Z")
            receipt_ended = (control_time + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
            initial_files = {item["path"]: item for item in workspace_manifest["files"]}
            final_files = [
                {
                    "path": path.relative_to(workspace_root).as_posix(),
                    "sha256": evaluation.sha256_file(path),
                    "size": path.stat().st_size,
                }
                for path in sorted(workspace_root.rglob("*"))
                if path.is_file()
            ]
            final_by_path = {item["path"]: item for item in final_files}
            final_manifest = {
                "schema_version": "1.0",
                "algorithm": "sha256-final-workspace-manifest-v1",
                "initial_manifest_sha256": evaluation.sha256_file(workspace_path),
                "root": ".",
                "files": final_files,
                "changes": {
                    "added": sorted(set(final_by_path) - set(initial_files)),
                    "modified": sorted(
                        path for path in set(final_by_path).intersection(initial_files)
                        if final_by_path[path]["sha256"] != initial_files[path]["sha256"]
                        or final_by_path[path]["size"] != initial_files[path]["size"]
                    ),
                    "deleted": sorted(set(initial_files) - set(final_by_path)),
                },
                "aggregate_sha256": evaluation.sha256_bytes(evaluation.canonical_bytes(final_files)),
            }
            final_path = self.input_root / "final-workspaces" / f"{run['run_id']}.json"
            write_json(final_path, final_manifest)
            evidence_dir = self.input_root / "evidence-inputs" / run["run_id"]
            evidence_dir.mkdir(parents=True, exist_ok=True)
            evidence_files = {
                "request": evidence_dir / "request.txt",
                "provider_events": evidence_dir / "provider-events.jsonl",
                "provider_response": evidence_dir / "provider-response.json",
                "stderr": evidence_dir / "stderr.log",
                "structured_claim": evidence_dir / "structured-claim.json",
                "initial_workspace": evidence_dir / "initial-workspace.json",
                "final_workspace": evidence_dir / "final-workspace.json",
                "workspace_population_seal": evidence_dir / "workspace-population-seal.json",
                "trace_source": evidence_dir / "trace-source.json",
            }
            evidence_files["request"].write_text(f"request:{run['run_id']}\n", encoding="utf-8", newline="\n")
            evidence_files["provider_events"].write_text(f"response:{run['run_id']}\n", encoding="utf-8", newline="\n")
            evidence_files["provider_response"].write_text(f"response:{run['run_id']}\n", encoding="utf-8", newline="\n")
            evidence_files["stderr"].write_text("", encoding="utf-8", newline="\n")
            write_json(evidence_files["structured_claim"], {
                "completion_claimed": False, "summary": "Fixture run is incomplete.",
                "deliverables": [], "blockers": [], "risks": [],
            })
            shutil.copyfile(workspace_path, evidence_files["initial_workspace"])
            shutil.copyfile(final_path, evidence_files["final_workspace"])
            initial_workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
            write_json(evidence_files["workspace_population_seal"], {
                "schema_version": "1.0",
                "algorithm": "sha256-workspace-population-seal-v1",
                "run_id": run["run_id"],
                "episode_id": "E01",
                "role": "producer",
                "prompt_sha256": evaluation.sha256_bytes(f"prompt:{run['run_id']}".encode()),
                "output_schema_sha256": evaluation.sha256_file(
                    self.experiment_dir / "completion-claim.schema.json"
                ),
                "workspace_snapshot_sha256": evaluation.sha256_bytes(
                    evaluation.canonical_bytes(initial_workspace)
                ),
                "workspace_aggregate_sha256": initial_workspace["aggregate_sha256"],
                "file_count": len(initial_workspace["files"]),
                "protocol_bundle_sha256": "6" * 64,
                "protocol_entrypoint_sha256": "7" * 64,
                "protocol_access": {
                    "entrypoint": "../protocol-bundle/SKILL.md",
                    "access_available": True,
                    "understanding_claimed": False,
                },
                "injection_receipt_sha256": None,
            })
            write_json(evidence_files["trace_source"], {"run_id": run["run_id"], "source": "unit-test"})
            evidence_entries = [
                {"role": role, "path": path.name, "sha256": evaluation.sha256_file(path)}
                for role, path in evidence_files.items()
            ]
            evidence_manifest = {
                "schema_version": "1.0", "run_id": run["run_id"], "episode_id": "E01",
                "attempt_id": attempt_id, "role": "producer",
                "initial_workspace_manifest": {"path": evidence_files["initial_workspace"].name, "sha256": evaluation.sha256_file(evidence_files["initial_workspace"])},
                "final_workspace_manifest": {"path": evidence_files["final_workspace"].name, "sha256": evaluation.sha256_file(evidence_files["final_workspace"])},
                "workspace_population_seal": {"path": evidence_files["workspace_population_seal"].name, "sha256": evaluation.sha256_file(evidence_files["workspace_population_seal"])},
                "structured_claim": {"path": evidence_files["structured_claim"].name, "sha256": evaluation.sha256_file(evidence_files["structured_claim"])},
                "files": evidence_entries,
                "aggregate_sha256": evaluation.sha256_bytes(evaluation.canonical_bytes(evidence_entries)),
            }
            evidence_path = evidence_dir / "evidence-manifest.json"
            evidence_path.write_bytes(guard.canonical_bytes(evidence_manifest))
            usage_receipt = {
                "schema_version": "2.0",
                "receipt_id": f"receipt-{run['run_id']}",
                "authorization_id": grant["authorization_id"],
                "execution_id": grant["execution_id"],
                "run_id": run["run_id"],
                "episode_id": "E01",
                "attempt_id": attempt_id,
                "role": "producer",
                "adapter": grant["adapter"],
                "cli_identity": grant["cli_identity"],
                "provider_profile": grant["provider_profile"],
                "model": grant["model"],
                "reasoning_effort": grant["reasoning_effort"],
                "tool_profile": grant["tool_profile"],
                "source_class": "adapter-attested",
                "provider_request_ids": [f"provider-{run['run_id']}"],
                "request_sha256": evaluation.sha256_bytes(f"request:{run['run_id']}".encode()),
                "response_sha256": evaluation.sha256_bytes(f"response:{run['run_id']}".encode()),
                "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "reasoning_output_tokens": 0, "total_tokens": 0, "wall_seconds": 1},
                "started_at": receipt_started,
                "ended_at": receipt_ended,
                "raw_evidence_sha256": "5" * 64,
                "evidence_manifest_sha256": evaluation.sha256_file(evidence_path),
            }
            receipt_input = self.input_root / "receipt-inputs" / f"{run['run_id']}.json"
            receipt_input.parent.mkdir(parents=True, exist_ok=True)
            receipt_input.write_bytes(guard.canonical_bytes(usage_receipt))
            self._store_fixture_settlement(
                execution_root,
                grant,
                receipt_input,
                evidence_path,
                call_number=run_index + 1,
                reserved_at=control_time,
            )
            stored_receipt = execution_root / "receipts" / f"receipt-{guard.sha256_bytes(guard.canonical_bytes(usage_receipt))}.json"
            ledger_paths = sorted((execution_root / "ledger").glob("*.json"))
            settlement_record = json.loads(ledger_paths[-1].read_text(encoding="utf-8"))
            usage_binding = self.bind(stored_receipt)
            usage_receipt_bindings.append({"run_id": run["run_id"], **usage_binding})
            trace_path = self.input_root / "traces" / f"{run['run_id']}.json"
            trace = self.trace(
                run,
                artifact_sha,
                self.bind(workspace_path),
                self.bind(final_path),
                self.bind(evidence_path),
                self.bind(evidence_files["trace_source"]),
                adapter_sha256,
                usage_binding,
                {
                    "grant_sha256": authorization_sha256,
                    "ledger_last_seq": settlement_record["seq"],
                    "ledger_tail_sha256": evaluation.sha256_file(ledger_paths[-1]),
                },
                cli_identity,
                provider_profile,
            )
            trace["started_at"] = receipt_started
            trace["ended_at"] = receipt_ended
            for event in trace["events"]:
                event["ts"] = receipt_started if event["seq"] <= 2 else receipt_ended
            write_json(trace_path, trace)
            trace_bindings.append(self.bind(trace_path, run_id=run["run_id"]))
            trace_by_pair.setdefault(run["pair_id"], {})[run["protocol"]] = (trace_path, trace)
            oracle = {
                "schema_version": "1.0",
                "experiment_id": self.preregistration["experiment_id"],
                "preregistration_sha256": prereg_sha,
                "run_plan_sha256": run_plan_sha,
                "run_id": run["run_id"],
                "pair_id": run["pair_id"],
                "scenario_id": run["scenario_id"],
                "protocol": run["protocol"],
                "trace_sha256": evaluation.sha256_file(trace_path),
                "scenario_input_sha256": scenario["input_sha256"],
                "oracle_definition_sha256": evaluation.scenario_oracle_hash(scenario),
                "workspace_manifest_sha256": trace["workspace_manifest"]["sha256"],
                "presented_artifact": self.bind(presented_path),
                "criterion_results": self.criterion_results(scenario),
                "measurements": self.measurements(run["scenario_id"], run["protocol"]),
                "evidence_refs": [f"oracle-evidence:{run['run_id']}"],
            }
            evaluator_context_path = self.input_root / "contexts" / "evaluator" / f"{run['run_id']}.json"
            write_json(evaluator_context_path, {
                "run_id": run["run_id"],
                "trace_sha256": evaluation.sha256_file(trace_path),
                "workspace_manifest_sha256": trace["workspace_manifest"]["sha256"],
                "scenario_input_sha256": scenario["input_sha256"],
                "oracle_definition_sha256": evaluation.scenario_oracle_hash(scenario),
            })
            oracle["evaluator"] = {"id": "oracle", "kind": "human", "context_manifest_sha256": evaluation.sha256_file(evaluator_context_path)}
            oracle_path = self.input_root / "oracles" / f"{run['run_id']}.json"
            write_json(oracle_path, oracle)
            oracle_bindings.append(self.bind(oracle_path, run_id=run["run_id"]))
            evaluator_context_bindings.append(self.bind(evaluator_context_path, run_id=run["run_id"]))

        blind_bindings = []
        review_bindings = []
        reviewer_context_bindings = []
        reviewer_execution_bindings = []
        for pair_id, protocol_values in sorted(trace_by_pair.items()):
            scenario_id = protocol_values["v1"][1]["scenario_id"]
            context_path = self.input_root / "contexts" / "reviewer" / f"{pair_id}.json"
            write_json(context_path, {"pair_id": pair_id, "scope": "blind review"})
            assignment_seed = self.preregistration["pairing"]["order_seed"]
            assignment = harness.blind_assignment(pair_id, assignment_seed)
            presented = [
                {
                    "label": label,
                    "presented_artifact": self.bind(
                        self.input_root / "presented" / f"{pair_id}-{assignment[label]}" / f"{pair_id}-{assignment[label]}.json"
                    ),
                    "trace_sha256": evaluation.sha256_file(protocol_values[assignment[label]][0]),
                }
                for label in ("A", "B")
            ]
            blind = {
                "schema_version": "1.0",
                "experiment_id": self.preregistration["experiment_id"],
                "preregistration_sha256": prereg_sha,
                "review_id": f"review-{pair_id}",
                "pair_id": pair_id,
                "scenario_id": scenario_id,
                "reviewer": {"id": "reviewer", "kind": "model", "model": "review-model", "reasoning_effort": "ultra", "context_isolation": "fresh-session"},
                "producer_protocols_withheld": True,
                "assignment_seed": assignment_seed,
                "presented": presented,
                "delivered_context": [{"path": context_path.relative_to(self.input_root).as_posix(), "sha256": evaluation.sha256_file(context_path), "purpose": "blind review"}],
                "created_at": "2026-08-01T00:00:00Z",
            }
            blind_path = self.input_root / "blind" / f"{pair_id}.json"
            write_json(blind_path, blind)
            blind_bindings.append(self.bind(blind_path, pair_id=pair_id))
            review_execution = {
                "schema_version": "1.0", "pair_id": pair_id, "review_id": blind["review_id"],
                "reviewer_id": "reviewer", "reviewer_kind": "model", "model": "review-model",
                "reasoning_effort": "ultra", "context_manifest_sha256": evaluation.sha256_file(context_path),
                "blind_manifest_sha256": evaluation.sha256_file(blind_path),
                "started_at": "2026-08-01T00:01:00Z", "ended_at": "2026-08-01T00:01:01Z",
                "request_sha256": evaluation.sha256_bytes(f"review-request:{pair_id}".encode()),
                "response_sha256": evaluation.sha256_bytes(f"review-response:{pair_id}".encode()),
                "provider_request_ids": [f"review-provider-{pair_id}"],
            }
            review_execution_path = self.input_root / "review-executions" / f"{pair_id}.json"
            write_json(review_execution_path, review_execution)
            reviewer_execution_bindings.append(self.bind(review_execution_path, pair_id=pair_id))
            review = {
                "schema_version": "1.0",
                "experiment_id": self.preregistration["experiment_id"],
                "preregistration_sha256": prereg_sha,
                "pair_id": pair_id,
                "scenario_id": scenario_id,
                "blind_manifest_sha256": evaluation.sha256_file(blind_path),
                "reviewer": {
                    "id": "reviewer", "kind": "model", "model": "review-model", "reasoning_effort": "ultra",
                    "context_manifest_sha256": evaluation.sha256_file(context_path),
                    "execution_receipt_sha256": evaluation.sha256_file(review_execution_path),
                },
                "presented": [
                    {"label": item["label"], "artifact_sha256": item["presented_artifact"]["sha256"], "trace_sha256": item["trace_sha256"]}
                    for item in presented
                ],
                "preference": next(label for label, protocol in assignment.items() if protocol == "v2"),
                "severe_regression_labels": [],
                "evidence_refs": [f"review-evidence:{pair_id}"],
            }
            review_path = self.input_root / "reviews" / f"{pair_id}.json"
            write_json(review_path, review)
            review_bindings.append(self.bind(review_path, pair_id=pair_id))
            reviewer_context_bindings.append(self.bind(context_path, pair_id=pair_id))

        deterministic_root = self.input_root / "deterministic"
        fixture_catalog = deterministic_root / "fixture-catalog.json"
        runner = deterministic_root / "runner.py"
        tool_profile = deterministic_root / "tool-profile.json"
        runner.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.experiment_dir / "deterministic-fixture-catalog.json", fixture_catalog)
        shutil.copyfile(self.experiment_dir / "deterministic_runner.py", runner)
        shutil.copyfile(self.experiment_dir / self.preregistration["execution_config"]["tool_profile"]["path"], tool_profile)
        suite_bindings = []
        for protocol in ("v1", "v2"):
            authoritative = deterministic_runner.run_suite(
                self.experiment_dir,
                self.preregistration,
                protocol,
                catalog_path=fixture_catalog,
                tool_profile_path=tool_profile,
                candidate_skill_root=SKILL_ROOT,
                runner_path=runner,
            )
            cases = []
            for result in authoritative["cases"]:
                case_id = result["case_id"]
                output_path = deterministic_root / "outputs" / f"{protocol}-{case_id}.json"
                write_json(output_path, result)
                cases.append({
                    "case_id": case_id,
                    "expected": result["expected"],
                    "actual": result["actual"],
                    "output": self.bind(output_path),
                })
            suite = {
                "schema_version": "1.0",
                "experiment_id": self.preregistration["experiment_id"],
                "preregistration_sha256": prereg_sha,
                "protocol": protocol,
                "source_sha256": authoritative["source_sha256"],
                "fixture_catalog_sha256": authoritative["fixture_catalog_sha256"],
                "runner_sha256": authoritative["runner_sha256"],
                "tool_profile_sha256": authoritative["tool_profile_sha256"],
                "cases": cases,
            }
            suite_path = self.input_root / "suites" / f"{protocol}.json"
            write_json(suite_path, suite)
            suite_bindings.append(self.bind(suite_path, protocol=protocol))

        final_time = datetime(2026, 8, 1, tzinfo=timezone.utc) + timedelta(seconds=len(self.run_plan["runs"]) * 2)
        guard.replay(execution_root, write_summary=True, now=final_time)
        for binding in oracle_bindings:
            oracle_path = self.input_root / binding["path"]
            oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
            oracle["trace_sha256"] = next(item["sha256"] for item in trace_bindings if item["run_id"] == binding["run_id"])
            write_json(oracle_path, oracle)
            binding["sha256"] = evaluation.sha256_file(oracle_path)
        for binding in evaluator_context_bindings:
            context_path = self.input_root / binding["path"]
            context = json.loads(context_path.read_text(encoding="utf-8"))
            context["trace_sha256"] = next(item["sha256"] for item in trace_bindings if item["run_id"] == binding["run_id"])
            write_json(context_path, context)
            binding["sha256"] = evaluation.sha256_file(context_path)
        for binding in blind_bindings:
            blind_path = self.input_root / binding["path"]
            blind = json.loads(blind_path.read_text(encoding="utf-8"))
            for item in blind["presented"]:
                protocol = harness.blind_assignment(blind["pair_id"], blind["assignment_seed"])[item["label"]]
                item["trace_sha256"] = next(
                    trace_binding["sha256"] for trace_binding in trace_bindings
                    if trace_binding["run_id"] == f"{blind['pair_id']}-{protocol}"
                )
            write_json(blind_path, blind)
            binding["sha256"] = evaluation.sha256_file(blind_path)
        for binding in reviewer_execution_bindings:
            receipt_path = self.input_root / binding["path"]
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["blind_manifest_sha256"] = next(item["sha256"] for item in blind_bindings if item["pair_id"] == binding["pair_id"])
            write_json(receipt_path, receipt)
            binding["sha256"] = evaluation.sha256_file(receipt_path)
        for binding in review_bindings:
            review_path = self.input_root / binding["path"]
            review = json.loads(review_path.read_text(encoding="utf-8"))
            blind_binding = next(item for item in blind_bindings if item["pair_id"] == binding["pair_id"])
            blind = json.loads((self.input_root / blind_binding["path"]).read_text(encoding="utf-8"))
            review["blind_manifest_sha256"] = blind_binding["sha256"]
            review["presented"] = [
                {"label": item["label"], "artifact_sha256": item["presented_artifact"]["sha256"], "trace_sha256": item["trace_sha256"]}
                for item in blind["presented"]
            ]
            review["reviewer"]["execution_receipt_sha256"] = next(
                item["sha256"] for item in reviewer_execution_bindings if item["pair_id"] == binding["pair_id"]
            )
            write_json(review_path, review)
            binding["sha256"] = evaluation.sha256_file(review_path)
        manifest = {
            "schema_version": "1.0",
            "experiment_id": self.preregistration["experiment_id"],
            "preregistration_sha256": prereg_sha,
            "run_plan_sha256": run_plan_sha,
            "evaluation_spec_sha256": evaluation.sha256_file(self.experiment_dir / "evaluation-spec.json"),
            "traces": sorted(trace_bindings, key=lambda item: item["run_id"]),
            "oracle_results": sorted(oracle_bindings, key=lambda item: item["run_id"]),
            "blind_manifests": sorted(blind_bindings, key=lambda item: item["pair_id"]),
            "blind_review_results": sorted(review_bindings, key=lambda item: item["pair_id"]),
            "deterministic_suite_results": sorted(suite_bindings, key=lambda item: item["protocol"]),
            "evaluator_contexts": sorted(evaluator_context_bindings, key=lambda item: item["run_id"]),
            "reviewer_contexts": sorted(reviewer_context_bindings, key=lambda item: item["pair_id"]),
            "reviewer_execution_receipts": sorted(reviewer_execution_bindings, key=lambda item: item["pair_id"]),
            "usage_receipts": sorted(usage_receipt_bindings, key=lambda item: item["run_id"]),
            "materialized_workspaces": sorted(materialized_workspace_bindings, key=lambda item: item["run_id"]),
            "deterministic_inputs": {
                "fixture_catalog": self.bind(fixture_catalog),
                "runner": self.bind(runner),
                "tool_profile": self.bind(tool_profile),
            },
            "trace_adapter": self.bind(adapter_path),
            "execution_authority": {
                "root": {"path": execution_root.relative_to(self.input_root).as_posix()},
                "grant": self.bind(grant_path),
                "ledger_anchor": self.bind(execution_root / "ledger-anchor.json"),
                "spend_summary": self.bind(execution_root / "spend-summary.json"),
            },
        }
        manifest["aggregate_sha256"] = evaluation._hash_without(manifest, "aggregate_sha256")
        manifest_path = self.input_root / "evaluation-input-manifest.json"
        write_json(manifest_path, manifest)
        return manifest_path, manifest

    def build_complete_fixture(self) -> tuple[Path, dict]:
        manifest_path = self.input_root / "evaluation-input-manifest.json"
        if not manifest_path.is_file():
            self._restore_input_fixture()
        return manifest_path, evaluation.load_json(manifest_path)

    def refresh_binding_and_manifest(self, manifest_path: Path, manifest: dict, section: str, identity: str, key: str) -> None:
        binding = next(item for item in manifest[section] if item[key] == identity)
        binding["sha256"] = evaluation.sha256_file(self.input_root / binding["path"])
        manifest["aggregate_sha256"] = evaluation._hash_without(manifest, "aggregate_sha256")
        write_json(manifest_path, manifest)

    def refresh_trace_dependents(self, manifest: dict, run_id: str) -> None:
        trace_binding = next(item for item in manifest["traces"] if item["run_id"] == run_id)
        trace_sha256 = trace_binding["sha256"]
        oracle_binding = next(item for item in manifest["oracle_results"] if item["run_id"] == run_id)
        oracle_path = self.input_root / oracle_binding["path"]
        oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
        oracle["trace_sha256"] = trace_sha256
        write_json(oracle_path, oracle)
        oracle_binding["sha256"] = evaluation.sha256_file(oracle_path)
        context_binding = next(item for item in manifest["evaluator_contexts"] if item["run_id"] == run_id)
        context_path = self.input_root / context_binding["path"]
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["trace_sha256"] = trace_sha256
        write_json(context_path, context)
        context_binding["sha256"] = evaluation.sha256_file(context_path)
        oracle["evaluator"]["context_manifest_sha256"] = context_binding["sha256"]
        write_json(oracle_path, oracle)
        oracle_binding["sha256"] = evaluation.sha256_file(oracle_path)
        pair_id = run_id[:-3]
        blind_binding = next(item for item in manifest["blind_manifests"] if item["pair_id"] == pair_id)
        blind_path = self.input_root / blind_binding["path"]
        blind = json.loads(blind_path.read_text(encoding="utf-8"))
        for item in blind["presented"]:
            if item["presented_artifact"]["path"].endswith(f"/{run_id}.json"):
                item["trace_sha256"] = trace_sha256
        write_json(blind_path, blind)
        blind_binding["sha256"] = evaluation.sha256_file(blind_path)
        execution_binding = next(
            item
            for item in manifest["reviewer_execution_receipts"]
            if item["pair_id"] == pair_id
        )
        execution_path = self.input_root / execution_binding["path"]
        execution_receipt = json.loads(execution_path.read_text(encoding="utf-8"))
        execution_receipt["blind_manifest_sha256"] = blind_binding["sha256"]
        write_json(execution_path, execution_receipt)
        execution_binding["sha256"] = evaluation.sha256_file(execution_path)
        review_binding = next(item for item in manifest["blind_review_results"] if item["pair_id"] == pair_id)
        review_path = self.input_root / review_binding["path"]
        review = json.loads(review_path.read_text(encoding="utf-8"))
        review["blind_manifest_sha256"] = blind_binding["sha256"]
        review["reviewer"]["execution_receipt_sha256"] = execution_binding["sha256"]
        for item in review["presented"]:
            matching = next(value for value in blind["presented"] if value["label"] == item["label"])
            item["trace_sha256"] = matching["trace_sha256"]
        write_json(review_path, review)
        review_binding["sha256"] = evaluation.sha256_file(review_path)

    def mutate_trace(self, manifest_path: Path, manifest: dict, run_id: str, mutate) -> None:
        binding = next(item for item in manifest["traces"] if item["run_id"] == run_id)
        path = self.input_root / binding["path"]
        trace = json.loads(path.read_text(encoding="utf-8"))
        mutate(trace)
        write_json(path, trace)
        binding["sha256"] = evaluation.sha256_file(path)
        self.refresh_trace_dependents(manifest, run_id)
        manifest["aggregate_sha256"] = evaluation._hash_without(manifest, "aggregate_sha256")
        write_json(manifest_path, manifest)

    def test_recomputes_all_metrics_and_gates_without_producer_observations(self) -> None:
        manifest_path, _ = self.build_complete_fixture()
        with mock.patch.object(
            guard, "replay_snapshot", wraps=guard.replay_snapshot
        ) as replay_snapshot:
            result = evaluation.evaluate(self.experiment_dir, self.input_root, manifest_path)
        self.assertEqual(replay_snapshot.call_count, 2)
        self.assertEqual(set(result["metrics"]), evaluation.EXPECTED_METRICS)
        self.assertEqual({item["gate"] for item in result["gate_results"]}, evaluation.EXPECTED_GATES)
        gate_statuses = {item["gate"]: item["status"] for item in result["gate_results"]}
        self.assertEqual(gate_statuses["deterministic_safety_fixtures_pass_rate_min"], "pass")
        self.assertTrue(all(
            status == "insufficient-data"
            for gate, status in gate_statuses.items()
            if gate != "deterministic_safety_fixtures_pass_rate_min"
        ))
        self.assertIsNone(result["metrics"]["control_context_share"]["v2"])
        self.assertIsNone(result["metrics"]["productive_work_share"]["comparison"])
        self.assertEqual(result["metrics"]["control_context_share"]["sample_count"], 0)
        self.assertEqual(result["decision"], "extend-experiment")
        expected_capabilities = {
            "concrete workspace, oracle, reviewer, and deterministic input schemas are implemented",
            "authoritative deterministic smoke replay and fail-closed metric formulas are implemented",
            "execution grant, ledger anchor, spend replay, per-trace receipts, and materialized workspace roots are bound",
        }
        expected_blockers = {
            "provider usage and billing values remain declared-only and are not externally verified",
            "no real 84-run trace set or corresponding oracle and reviewer results have been collected",
            "legacy harness reports do not bind the authoritative evaluation input manifest and result",
            "gate-driving oracle measurements are not yet bound to authoritative telemetry",
            "blind review execution receipts are bound declarations but lack a separate reviewer grant and provider verification",
        }
        stale_false_blockers = {
            "evaluator and reviewer context manifests are not independently bound inputs",
            "deterministic fixture catalogs, runners, tool profiles, and case outputs are not independently bound inputs",
        }
        self.assertEqual(evaluation.IMPLEMENTED_OFFLINE_CAPABILITIES, expected_capabilities)
        self.assertEqual(evaluation.ELIGIBILITY_BLOCKERS, expected_blockers)
        self.assertEqual(set(result["eligibility_blockers"]), expected_blockers)
        self.assertTrue(stale_false_blockers.isdisjoint(result["eligibility_blockers"]))
        self.assertFalse(result["formal_execution_enabled"])

    def test_late_authority_drift_during_deterministic_replay_fails_closed(self) -> None:
        manifest_path, manifest = self.build_complete_fixture()
        execution_root = self.input_root / manifest["execution_authority"]["root"]["path"]
        original = deterministic_runner.run_suite
        mutated = False

        def mutate_authority_after_replay(*args, **kwargs):
            nonlocal mutated
            result = original(*args, **kwargs)
            if not mutated:
                evidence_dir = next(
                    path
                    for path in sorted((execution_root / "evidence").iterdir())
                    if path.is_dir()
                )
                (evidence_dir / "unreferenced.json").write_text(
                    "{}\n", encoding="utf-8", newline="\n"
                )
                mutated = True
            return result

        with mock.patch.object(
            deterministic_runner,
            "run_suite",
            side_effect=mutate_authority_after_replay,
        ):
            with self.assertRaisesRegex(
                evaluation.EvaluationError,
                "execution authority changed during evaluation",
            ):
                evaluation.evaluate(self.experiment_dir, self.input_root, manifest_path)
        self.assertTrue(mutated)

    def test_each_trace_keeps_its_own_historical_settlement_anchor(self) -> None:
        manifest_path, manifest = self.build_complete_fixture()
        first_binding, second_binding = manifest["traces"][:2]
        first_path = self.input_root / first_binding["path"]
        second_path = self.input_root / second_binding["path"]
        first = json.loads(first_path.read_text(encoding="utf-8"))
        second = json.loads(second_path.read_text(encoding="utf-8"))
        self.assertNotEqual(first["execution_authority"], second["execution_authority"])

        first["execution_authority"] = second["execution_authority"]
        write_json(first_path, first)
        first_binding["sha256"] = evaluation.sha256_file(first_path)
        self.refresh_trace_dependents(manifest, first_binding["run_id"])
        manifest["aggregate_sha256"] = evaluation._hash_without(manifest, "aggregate_sha256")
        write_json(manifest_path, manifest)

        with self.assertRaisesRegex(evaluation.EvaluationError, "does not anchor its settlement"):
            evaluation.evaluate(self.experiment_dir, self.input_root, manifest_path)

    def test_presented_outputs_do_not_mutate_the_bound_initial_workspace(self) -> None:
        _, manifest = self.build_complete_fixture()
        run_id = "S03-P01-v1"
        binding = next(
            item for item in manifest["materialized_workspaces"] if item["run_id"] == run_id
        )
        workspace = self.input_root / binding["path"]
        self.assertFalse((workspace / "DESIGN.md").exists())
        builder.validate_workspace(
            workspace,
            json.loads(
                (self.input_root / "workspaces" / f"{run_id}.json").read_text(encoding="utf-8")
            ),
        )

    def test_presented_artifact_requires_its_exact_deliverable_event(self) -> None:
        manifest_path, manifest = self.build_complete_fixture()
        run_id = "S03-P01-v1"

        def replace_hash(trace: dict) -> None:
            event = next(item for item in trace["events"] if item["kind"] == "deliverable")
            event["payload_sha256"] = "0" * 64

        self.mutate_trace(manifest_path, manifest, run_id, replace_hash)
        with self.assertRaisesRegex(evaluation.EvaluationError, "not bound by a deliverable event"):
            evaluation.evaluate(self.experiment_dir, self.input_root, manifest_path)

    def test_missing_or_duplicate_exact_input_fails_closed(self) -> None:
        manifest_path, manifest = self.build_complete_fixture()
        manifest["oracle_results"].pop()
        manifest["aggregate_sha256"] = evaluation._hash_without(manifest, "aggregate_sha256")
        write_json(manifest_path, manifest)
        with self.assertRaisesRegex(evaluation.EvaluationError, "schema validation failed|exact set"):
            evaluation.evaluate(self.experiment_dir, self.input_root, manifest_path)

    def test_indeterminate_or_zero_denominator_fails_closed(self) -> None:
        manifest_path, manifest = self.build_complete_fixture()
        run_id = "S04-P01-v2"
        binding = next(item for item in manifest["oracle_results"] if item["run_id"] == run_id)
        path = self.input_root / binding["path"]
        oracle = json.loads(path.read_text(encoding="utf-8"))
        oracle["measurements"]["fact_checks_total"] = 0
        oracle["measurements"]["fact_checks_correct"] = 0
        write_json(path, oracle)
        self.refresh_binding_and_manifest(manifest_path, manifest, "oracle_results", run_id, "run_id")
        with self.assertRaisesRegex(evaluation.EvaluationError, "invalid fact_checks_correct/fact_checks_total"):
            evaluation.evaluate(self.experiment_dir, self.input_root, manifest_path)

    def test_oracle_cannot_rebind_to_another_trace_or_omit_a_criterion(self) -> None:
        manifest_path, manifest = self.build_complete_fixture()
        run_id = "S05-P01-v2"
        binding = next(item for item in manifest["oracle_results"] if item["run_id"] == run_id)
        path = self.input_root / binding["path"]
        oracle = json.loads(path.read_text(encoding="utf-8"))
        oracle["trace_sha256"] = "0" * 64
        oracle["criterion_results"].pop()
        write_json(path, oracle)
        self.refresh_binding_and_manifest(manifest_path, manifest, "oracle_results", run_id, "run_id")
        with self.assertRaisesRegex(evaluation.EvaluationError, "criterion exact set|trace_sha256"):
            evaluation.evaluate(self.experiment_dir, self.input_root, manifest_path)

    def test_blind_result_cannot_swap_presented_hashes_or_use_indeterminate(self) -> None:
        manifest_path, manifest = self.build_complete_fixture()
        pair_id = "S01-P01"
        binding = next(item for item in manifest["blind_review_results"] if item["pair_id"] == pair_id)
        path = self.input_root / binding["path"]
        review = json.loads(path.read_text(encoding="utf-8"))
        review["preference"] = "indeterminate"
        review["presented"][0]["trace_sha256"] = "0" * 64
        write_json(path, review)
        self.refresh_binding_and_manifest(manifest_path, manifest, "blind_review_results", pair_id, "pair_id")
        with self.assertRaisesRegex(evaluation.EvaluationError, "presented binding drifted|indeterminate"):
            evaluation.evaluate(self.experiment_dir, self.input_root, manifest_path)

    def test_blind_manifest_assignment_seed_must_match_preregistration(self) -> None:
        manifest_path, manifest = self.build_complete_fixture()
        pair_id = "S01-P01"
        binding = next(item for item in manifest["blind_manifests"] if item["pair_id"] == pair_id)
        path = self.input_root / binding["path"]
        blind = json.loads(path.read_text(encoding="utf-8"))
        blind["assignment_seed"] += 1
        write_json(path, blind)
        self.refresh_binding_and_manifest(manifest_path, manifest, "blind_manifests", pair_id, "pair_id")
        with self.assertRaisesRegex(evaluation.EvaluationError, "assignment seed drifted"):
            evaluation.evaluate(self.experiment_dir, self.input_root, manifest_path)

    def test_blind_manifest_labels_must_follow_canonical_assignment(self) -> None:
        manifest_path, manifest = self.build_complete_fixture()
        pair_id = "S01-P01"
        binding = next(item for item in manifest["blind_manifests"] if item["pair_id"] == pair_id)
        path = self.input_root / binding["path"]
        blind = json.loads(path.read_text(encoding="utf-8"))
        first, second = blind["presented"]
        first["presented_artifact"], second["presented_artifact"] = (
            second["presented_artifact"],
            first["presented_artifact"],
        )
        first["trace_sha256"], second["trace_sha256"] = second["trace_sha256"], first["trace_sha256"]
        write_json(path, blind)
        self.refresh_binding_and_manifest(manifest_path, manifest, "blind_manifests", pair_id, "pair_id")
        with self.assertRaisesRegex(evaluation.EvaluationError, "canonical assignment drifted"):
            evaluation.evaluate(self.experiment_dir, self.input_root, manifest_path)

    def test_unbound_oracle_gate_stays_insufficient_and_does_not_enable_execution(self) -> None:
        manifest_path, manifest = self.build_complete_fixture()
        for run_id in ("S05-P01-v2", "S05-P02-v2", "S05-P03-v2"):
            binding = next(item for item in manifest["oracle_results"] if item["run_id"] == run_id)
            path = self.input_root / binding["path"]
            oracle = json.loads(path.read_text(encoding="utf-8"))
            oracle["criterion_results"][0]["verdict"] = "violated"
            oracle["measurements"]["false_completion"] = True
            trace_binding = next(item for item in manifest["traces"] if item["run_id"] == run_id)
            trace_path = self.input_root / trace_binding["path"]
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            trace["events"].insert(-1, {
                "seq": 0,
                "ts": trace["ended_at"],
                "kind": "completion_claim",
                "summary": "Claimed completion.",
                "payload_sha256": None,
            })
            for seq, event in enumerate(trace["events"], start=1):
                event["seq"] = seq
            trace["outcome"]["status"] = "completed"
            trace["outcome"]["completion_claimed"] = True
            write_json(trace_path, trace)
            trace_binding["sha256"] = evaluation.sha256_file(trace_path)
            oracle["trace_sha256"] = trace_binding["sha256"]
            write_json(path, oracle)
            binding["sha256"] = evaluation.sha256_file(path)
            self.refresh_trace_dependents(manifest, run_id)
        manifest["aggregate_sha256"] = evaluation._hash_without(manifest, "aggregate_sha256")
        write_json(manifest_path, manifest)
        result = evaluation.evaluate(self.experiment_dir, self.input_root, manifest_path)
        gate = next(item for item in result["gate_results"] if item["gate"] == "adversarial_false_completion_v2_max")
        self.assertEqual(gate["status"], "insufficient-data")
        self.assertEqual(gate["evidence_refs"], ["authority-missing:adversarial_false_completion"])
        self.assertEqual(result["decision"], "extend-experiment")
        self.assertFalse(result["formal_execution_enabled"])

    def test_context_and_deterministic_hashes_must_resolve_to_bound_files(self) -> None:
        manifest_path, manifest = self.build_complete_fixture()
        manifest["evaluator_contexts"][0]["sha256"] = "0" * 64
        manifest["deterministic_inputs"]["runner"]["sha256"] = "1" * 64
        manifest["aggregate_sha256"] = evaluation._hash_without(manifest, "aggregate_sha256")
        write_json(manifest_path, manifest)
        with self.assertRaisesRegex(evaluation.EvaluationError, "evaluator context|deterministic runner"):
            evaluation.evaluate(self.experiment_dir, self.input_root, manifest_path)

    def test_context_and_deterministic_output_content_must_match_bound_identity(self) -> None:
        manifest_path, manifest = self.build_complete_fixture()
        context_binding = manifest["evaluator_contexts"][0]
        context_path = self.input_root / context_binding["path"]
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["run_id"] = "S14-P03-v2"
        write_json(context_path, context)
        context_binding["sha256"] = evaluation.sha256_file(context_path)
        oracle_binding = next(
            item for item in manifest["oracle_results"] if item["run_id"] == context_binding["run_id"]
        )
        oracle_path = self.input_root / oracle_binding["path"]
        oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
        oracle["evaluator"]["context_manifest_sha256"] = context_binding["sha256"]
        write_json(oracle_path, oracle)
        oracle_binding["sha256"] = evaluation.sha256_file(oracle_path)
        output_path = self.input_root / "deterministic" / "outputs" / "v2-accept-control.json"
        output = json.loads(output_path.read_text(encoding="utf-8"))
        output["protocol"] = "v1"
        write_json(output_path, output)
        suite_binding = next(item for item in manifest["deterministic_suite_results"] if item["protocol"] == "v2")
        suite_path = self.input_root / suite_binding["path"]
        suite = json.loads(suite_path.read_text(encoding="utf-8"))
        case = next(item for item in suite["cases"] if item["case_id"] == "accept-control")
        case["output"]["sha256"] = evaluation.sha256_file(output_path)
        write_json(suite_path, suite)
        suite_binding["sha256"] = evaluation.sha256_file(suite_path)
        manifest["aggregate_sha256"] = evaluation._hash_without(manifest, "aggregate_sha256")
        write_json(manifest_path, manifest)
        with self.assertRaisesRegex(evaluation.EvaluationError, "context .*identity drifted|output content drifted"):
            evaluation.evaluate(self.experiment_dir, self.input_root, manifest_path)

    def test_deterministic_suite_cannot_omit_a_frozen_catalog_case(self) -> None:
        manifest_path, manifest = self.build_complete_fixture()
        suite_binding = next(item for item in manifest["deterministic_suite_results"] if item["protocol"] == "v2")
        suite_path = self.input_root / suite_binding["path"]
        suite = json.loads(suite_path.read_text(encoding="utf-8"))
        suite["cases"].pop()
        write_json(suite_path, suite)
        self.refresh_binding_and_manifest(manifest_path, manifest, "deterministic_suite_results", "v2", "protocol")
        with self.assertRaisesRegex(evaluation.EvaluationError, "case exact set drifted"):
            evaluation.evaluate(self.experiment_dir, self.input_root, manifest_path)

    def test_deterministic_inputs_must_match_the_frozen_catalog_and_runner(self) -> None:
        for input_name in ("fixture_catalog", "runner"):
            with self.subTest(input_name=input_name):
                manifest_path, manifest = self.build_complete_fixture()
                binding = manifest["deterministic_inputs"][input_name]
                path = self.input_root / binding["path"]
                path.write_bytes(path.read_bytes() + b"\n")
                binding["sha256"] = evaluation.sha256_file(path)
                for suite_binding in manifest["deterministic_suite_results"]:
                    suite_path = self.input_root / suite_binding["path"]
                    suite = json.loads(suite_path.read_text(encoding="utf-8"))
                    suite[f"{input_name}_sha256"] = binding["sha256"]
                    write_json(suite_path, suite)
                    suite_binding["sha256"] = evaluation.sha256_file(suite_path)
                manifest["aggregate_sha256"] = evaluation._hash_without(manifest, "aggregate_sha256")
                write_json(manifest_path, manifest)
                with self.assertRaisesRegex(evaluation.EvaluationError, f"deterministic {input_name} is not the frozen instrument input"):
                    evaluation.evaluate(self.experiment_dir, self.input_root, manifest_path)
                self._restore_input_fixture()

    def test_authoritative_result_schemas_must_remain_frozen_during_replay(self) -> None:
        for schema_name, label in (
            ("deterministic-case-result.schema.json", "case-result"),
            ("deterministic-authoritative-run.schema.json", "authoritative-run"),
        ):
            with self.subTest(schema_name=schema_name):
                self._restore_input_fixture()
                self._restore_experiment_fixture()
                manifest_path, _ = self.build_complete_fixture()
                original = deterministic_runner.run_suite
                mutated = False

                def mutate_before_replay(*args, **kwargs):
                    nonlocal mutated
                    if not mutated:
                        (self.experiment_dir / schema_name).write_text(
                            '{"type":"object"}\n', encoding="utf-8", newline="\n"
                        )
                        mutated = True
                    return original(*args, **kwargs)

                with mock.patch.object(deterministic_runner, "run_suite", side_effect=mutate_before_replay):
                    with self.assertRaisesRegex(
                        evaluation.EvaluationError,
                        f"{label} schema is not the frozen instrument input|authoritative rerun failed",
                    ):
                        evaluation.evaluate(self.experiment_dir, self.input_root, manifest_path)
                self.assertTrue(mutated)
                self._restore_experiment_fixture()

    def test_deterministic_submitted_actual_must_match_authoritative_rerun(self) -> None:
        manifest_path, manifest = self.build_complete_fixture()
        suite_binding = next(item for item in manifest["deterministic_suite_results"] if item["protocol"] == "v2")
        suite_path = self.input_root / suite_binding["path"]
        suite = json.loads(suite_path.read_text(encoding="utf-8"))
        case = next(item for item in suite["cases"] if item["case_id"] == "accept-control")
        case["actual"] = "reject"
        output_path = self.input_root / case["output"]["path"]
        output = json.loads(output_path.read_text(encoding="utf-8"))
        output["actual"] = "reject"
        write_json(output_path, output)
        case["output"]["sha256"] = evaluation.sha256_file(output_path)
        write_json(suite_path, suite)
        self.refresh_binding_and_manifest(manifest_path, manifest, "deterministic_suite_results", "v2", "protocol")
        with self.assertRaisesRegex(evaluation.EvaluationError, "actual results drifted from authoritative rerun"):
            evaluation.evaluate(self.experiment_dir, self.input_root, manifest_path)

    def test_workspace_and_presented_artifact_tampering_fail_closed(self) -> None:
        manifest_path, manifest = self.build_complete_fixture()
        run_id = "S01-P01-v2"
        trace_binding = next(item for item in manifest["traces"] if item["run_id"] == run_id)
        trace = json.loads((self.input_root / trace_binding["path"]).read_text(encoding="utf-8"))
        workspace_path = self.input_root / trace["workspace_manifest"]["path"]
        workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
        workspace["variant_sha256"] = "0" * 64
        write_json(workspace_path, workspace)
        trace["workspace_manifest"]["sha256"] = evaluation.sha256_file(workspace_path)
        trace_path = self.input_root / trace_binding["path"]
        write_json(trace_path, trace)
        trace_binding["sha256"] = evaluation.sha256_file(trace_path)
        manifest["aggregate_sha256"] = evaluation._hash_without(manifest, "aggregate_sha256")
        write_json(manifest_path, manifest)
        with self.assertRaisesRegex(evaluation.EvaluationError, "workspace binding failed|workspace manifest"):
            evaluation.evaluate(self.experiment_dir, self.input_root, manifest_path)

    def test_false_completion_cannot_be_asserted_without_trace_claim_and_failed_criterion(self) -> None:
        manifest_path, manifest = self.build_complete_fixture()
        run_id = "S05-P01-v2"
        binding = next(item for item in manifest["oracle_results"] if item["run_id"] == run_id)
        path = self.input_root / binding["path"]
        oracle = json.loads(path.read_text(encoding="utf-8"))
        oracle["measurements"]["false_completion"] = True
        write_json(path, oracle)
        self.refresh_binding_and_manifest(manifest_path, manifest, "oracle_results", run_id, "run_id")
        with self.assertRaisesRegex(evaluation.EvaluationError, "false_completion disagrees"):
            evaluation.evaluate(self.experiment_dir, self.input_root, manifest_path)

    def test_full_trace_event_sequence_is_enforced_by_evaluation(self) -> None:
        manifest_path, manifest = self.build_complete_fixture()
        self.mutate_trace(manifest_path, manifest, "S01-P01-v2", lambda trace: trace["events"][1].update(seq=4))
        with self.assertRaisesRegex(evaluation.EvaluationError, "event sequence"):
            evaluation.evaluate(self.experiment_dir, self.input_root, manifest_path)

    def test_full_trace_timing_is_enforced_by_evaluation(self) -> None:
        manifest_path, manifest = self.build_complete_fixture()
        self.mutate_trace(
            manifest_path,
            manifest,
            "S01-P01-v2",
            lambda trace: trace.update(ended_at="2026-07-31T23:59:59Z"),
        )
        with self.assertRaisesRegex(evaluation.EvaluationError, "ended_at precedes"):
            evaluation.evaluate(self.experiment_dir, self.input_root, manifest_path)

    def test_full_trace_budget_is_enforced_by_evaluation(self) -> None:
        manifest_path, manifest = self.build_complete_fixture()
        self.mutate_trace(
            manifest_path,
            manifest,
            "S01-P01-v2",
            lambda trace: trace["budget"].update(total_tokens_used=2),
        )
        with self.assertRaisesRegex(evaluation.EvaluationError, "token budget exceeded"):
            evaluation.evaluate(self.experiment_dir, self.input_root, manifest_path)

    def test_full_trace_outcome_is_enforced_by_evaluation(self) -> None:
        manifest_path, manifest = self.build_complete_fixture()
        self.mutate_trace(
            manifest_path,
            manifest,
            "S01-P01-v2",
            lambda trace: trace["outcome"].update(completion_claimed=True),
        )
        with self.assertRaisesRegex(evaluation.EvaluationError, "completion_claimed disagrees"):
            evaluation.evaluate(self.experiment_dir, self.input_root, manifest_path)


if __name__ == "__main__":
    unittest.main()
