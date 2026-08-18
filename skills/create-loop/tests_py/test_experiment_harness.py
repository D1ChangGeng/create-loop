from __future__ import annotations

import json
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = SKILL_ROOT / "tests" / "experiments"
sys.path.insert(0, str(EXPERIMENTS))

import experiment_harness as harness  # noqa: E402
import execution_guard as guard  # noqa: E402
import snapshot_tools as snapshots  # noqa: E402
import workspace_builder as builder  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


class ExperimentHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "experiments"
        shutil.copytree(EXPERIMENTS, self.root)
        self.refresh_candidate_and_instrument()

    def load(self, name: str) -> dict:
        return json.loads((self.root / name).read_text(encoding="utf-8"))

    def prereg_hash(self) -> str:
        return harness.sha256_bytes(harness.canonical_bytes(self.load("preregistration.json")))

    def refresh_candidate_and_instrument(self) -> None:
        preregistration = self.load("preregistration.json")
        preregistration["authorization"] = {
            "required_file": "authorization-grant.json",
            "schema_file": "authorization-grant.schema.json",
        }
        candidate = snapshots.build_worktree_snapshot(
            SKILL_ROOT,
            repo_root=SKILL_ROOT.parents[1],
            snapshot_id="v2-candidate-worktree",
            protocol="v2",
            base_git_commit=preregistration["candidate"]["source_snapshot"]["origin_commit"],
        )
        write_json(self.root / "candidate-source.json", candidate)
        preregistration["candidate"]["source_snapshot"]["manifest"]["sha256"] = harness.sha256_file(self.root / "candidate-source.json")
        preregistration["candidate"]["source_snapshot"]["aggregate_sha256"] = candidate["aggregate_sha256"]
        preregistration["scenario_manifest"]["sha256"] = harness.sha256_file(self.root / "scenarios.json")
        preregistration["review"]["manifest_schema"]["sha256"] = harness.sha256_file(self.root / "blind-review-manifest.schema.json")
        tool_binding = preregistration["execution_config"]["tool_profile"]
        tool_binding["sha256"] = harness.sha256_file(self.root / tool_binding["path"])
        instrument = self.build_instrument(preregistration)
        write_json(self.root / "instrument-manifest.json", instrument)
        preregistration["instrument_manifest"]["sha256"] = snapshots.instrument_manifest_sha256(instrument)
        write_json(self.root / "preregistration.json", preregistration)

    def run_plan(self) -> dict:
        scenarios, preregistration = harness.load_and_validate(self.root)
        return harness.build_run_plan(scenarios, preregistration, experiment_dir=self.root)

    def make_fake_adapter(self) -> tuple[Path, Path]:
        marker = Path(self.temp.name) / "adapter-ran.txt"
        adapter = Path(self.temp.name) / "fake_adapter.py"
        adapter.write_text(
            "from pathlib import Path\n"
            "import sys\n"
            f"Path({str(marker)!r}).write_text('ran', encoding='utf-8')\n"
            "print('fake adapter ran')\n",
            encoding="utf-8",
            newline="\n",
        )
        adapter.chmod(adapter.stat().st_mode | stat.S_IXUSR)
        return adapter, marker

    def authorize_fixture(
        self,
        adapter: Path,
        run_plan_path: Path,
        *,
        total_tokens: int = 8400,
        freeze_preregistration: bool = True,
    ) -> tuple[Path, Path]:
        preregistration = self.load("preregistration.json")
        if freeze_preregistration:
            preregistration["status"] = "frozen"
            preregistration["execution_config"].update({
                "model": "fake-model",
                "max_tokens_per_run": 100,
                "max_seconds_per_run": 60,
            })
            write_json(self.root / "preregistration.json", preregistration)
            self.refresh_instrument_only()
            preregistration = self.load("preregistration.json")
        run_plan = harness.build_run_plan(
            self.load("scenarios.json"), preregistration, experiment_dir=self.root
        )
        write_json(run_plan_path, run_plan)
        execution_root = Path(self.temp.name) / f"execution-{run_plan_path.stem}"
        cli_path = self.root / "cli-identities" / "fake-cli.json"
        provider_path = self.root / "provider-profiles" / "fake-provider.json"
        write_json(cli_path, {"id": "fake-cli", "version": "1"})
        write_json(provider_path, {"id": "fake-provider", "wire_api": "responses"})
        cli_identity = {
            "id": "fake-cli",
            "path": cli_path.relative_to(self.root).as_posix(),
            "sha256": harness.sha256_file(cli_path),
        }
        provider_profile = {
            "id": "fake-provider",
            "path": provider_path.relative_to(self.root).as_posix(),
            "sha256": harness.sha256_file(provider_path),
        }
        authorization = {
            "schema_version": "2.0",
            "authorization_id": f"authorization-{run_plan_path.stem}",
            "execution_id": f"execution-{run_plan_path.stem}",
            "execution_root_sha256": guard._root_path_sha256(execution_root),
            "experiment_id": preregistration["experiment_id"],
            "preregistration_sha256": harness.sha256_bytes(harness.canonical_bytes(preregistration)),
            "run_plan_sha256": harness.sha256_bytes(harness.canonical_bytes(run_plan)),
            "role": "producer",
            "adapter": {"id": "fake", "version": "1", "sha256": harness.sha256_file(adapter)},
            "cli_identity": cli_identity,
            "provider_profile": provider_profile,
            "model": preregistration["execution_config"]["model"],
            "reasoning_effort": preregistration["execution_config"]["reasoning_effort"],
            "tool_profile": preregistration["execution_config"]["tool_profile"],
            "authorized_calls": [
                {"run_id": run["run_id"], "episode_id": "E01"}
                for run in run_plan["runs"]
            ],
            "limits": {
                "per_call": {"max_total_tokens": 100, "max_wall_seconds": 60},
                "total": {"max_calls": 84, "max_total_tokens": total_tokens, "max_wall_seconds": 5040},
            },
            "authorized_by": "unit-test",
            "authorized_at": "2026-08-01T00:00:00Z",
            "expires_at": "2026-08-02T00:00:00Z",
            "authority_evidence_sha256": "8" * 64,
        }
        path = Path(self.temp.name) / f"authorization-{run_plan_path.stem}.json"
        write_json(path, authorization)
        guard.initialize(execution_root, path, now=datetime(2026, 8, 1, tzinfo=timezone.utc))
        return execution_root / "grant.json", execution_root

    def refresh_instrument_only(self) -> None:
        preregistration = self.load("preregistration.json")
        instrument = self.build_instrument(preregistration)
        write_json(self.root / "instrument-manifest.json", instrument)
        preregistration["instrument_manifest"]["sha256"] = snapshots.instrument_manifest_sha256(instrument)
        write_json(self.root / "preregistration.json", preregistration)

    def build_instrument(self, preregistration: dict) -> dict:
        return snapshots.build_instrument_manifest(
            self.root,
            snapshots.EXPERIMENT_INSTRUMENT_INPUTS,
            source_snapshots=(
                preregistration["baseline"]["source_snapshot"]["aggregate_sha256"],
                preregistration["candidate"]["source_snapshot"]["aggregate_sha256"],
            ),
        )

    def test_frozen_inputs_validate_and_contain_exactly_fourteen_scenarios(self):
        scenarios, preregistration = harness.load_and_validate(self.root)
        self.assertEqual([item["id"] for item in scenarios["scenarios"]], list(range(1, 15)))
        self.assertEqual([item["slug"] for item in scenarios["scenarios"]], harness.CANONICAL_SCENARIO_SLUGS)
        self.assertEqual(preregistration["pairing"]["pair_count"], 42)
        self.assertEqual(preregistration["pairing"]["run_count"], 84)
        harness.validate_baseline_binding(preregistration)

    def test_live_repository_validate_and_plan_inputs_are_in_sync(self):
        scenarios, preregistration = harness.load_and_validate(EXPERIMENTS)
        plan = harness.build_run_plan(scenarios, preregistration, experiment_dir=EXPERIMENTS)
        harness.validate_run_plan(plan, scenarios, preregistration, experiment_dir=EXPERIMENTS)

    def test_instrument_manifest_has_no_preregistration_self_binding(self):
        preregistration = self.load("preregistration.json")
        instrument = self.load("instrument-manifest.json")
        paths = {entry["path"] for entry in instrument["files"]}
        roles = {entry["role"] for entry in instrument["files"]}
        self.assertNotIn("preregistration.json", paths)
        self.assertIn("report.schema.json", paths)
        self.assertIn("evaluation", roles)
        self.assertEqual(
            preregistration["instrument_manifest"]["sha256"],
            snapshots.instrument_manifest_sha256(instrument),
        )

    def test_every_experiment_schema_uses_only_supported_runtime_keywords(self):
        harness.validate_schema_documents(self.root)

    def test_unused_schema_definition_with_unknown_keyword_is_rejected(self):
        schema_path = self.root / "trace.schema.json"
        schema = self.load("trace.schema.json")
        schema["$defs"]["unused_bad_schema"] = {
            "type": "object",
            "unevaluatedProperties": False,
        }
        write_json(schema_path, schema)
        with self.assertRaisesRegex(harness.ExperimentError, "schema is unsupported"):
            harness.validate_schema_documents(self.root)

    def test_non_standard_json_numbers_are_rejected(self):
        path = Path(self.temp.name) / "invalid.json"
        for constant in ("NaN", "Infinity", "-Infinity"):
            path.write_text(f'{{"value": {constant}}}\n', encoding="utf-8", newline="\n")
            with self.assertRaisesRegex(harness.ExperimentError, "non-standard JSON constant"):
                harness.load_json(path)

    def test_scenario_metrics_must_be_declared_by_preregistration(self):
        preregistration = self.load("preregistration.json")
        for group in preregistration["metrics"].values():
            if "goal_quality" in group:
                group.remove("goal_quality")
        write_json(self.root / "preregistration.json", preregistration)
        with self.assertRaisesRegex(harness.ExperimentError, "preregistered metric set drifted"):
            harness.load_and_validate(self.root)

    def test_plan_is_deterministic_unique_and_balanced(self):
        first = self.run_plan()
        second = self.run_plan()
        self.assertEqual(harness.canonical_bytes(first), harness.canonical_bytes(second))
        self.assertEqual(len(first["runs"]), 84)
        self.assertEqual(len({item["run_id"] for item in first["runs"]}), 84)
        self.assertEqual(len({item["pair_id"] for item in first["runs"]}), 42)
        by_scenario = {scenario_id: [] for scenario_id in range(1, 15)}
        for item in first["runs"]:
            by_scenario[item["scenario_id"]].append(item)
        for runs in by_scenario.values():
            self.assertEqual(len(runs), 6)
            self.assertEqual({item["repetition"] for item in runs}, {1, 2, 3})
            self.assertEqual(sum(item["protocol"] == "v1" for item in runs), 3)
            self.assertEqual(sum(item["protocol"] == "v2" for item in runs), 3)
        for index in range(0, len(first["runs"]), 2):
            pair = first["runs"][index:index + 2]
            self.assertEqual(pair[0]["pair_id"], pair[1]["pair_id"])
            self.assertEqual({item["protocol"] for item in pair}, {"v1", "v2"})
            self.assertEqual(len({item["pair_seed"] for item in pair}), 1)
            self.assertEqual(len({item["semantic_case_sha256"] for item in pair}), 1)
            self.assertEqual(pair[0]["tool_profile"], self.load("preregistration.json")["execution_config"]["tool_profile"])
            self.assertNotEqual(pair[0]["workspace_variant_sha256"], pair[1]["workspace_variant_sha256"])

    def test_copied_root_tool_profile_is_the_only_run_plan_authority(self):
        preregistration = self.load("preregistration.json")
        binding = preregistration["execution_config"]["tool_profile"]
        profile_path = self.root / binding["path"]
        profile = self.load(binding["path"])
        profile["id"] = "copied-root-tool-profile"
        write_json(profile_path, profile)
        binding["id"] = profile["id"]
        binding["sha256"] = harness.sha256_file(profile_path)
        write_json(self.root / "preregistration.json", preregistration)

        plan = harness.build_run_plan(
            self.load("scenarios.json"), preregistration, experiment_dir=self.root
        )
        self.assertEqual({run["tool_profile"]["id"] for run in plan["runs"]}, {profile["id"]})
        self.assertEqual({run["tool_profile"]["sha256"] for run in plan["runs"]}, {binding["sha256"]})
        self.assertNotEqual(binding["sha256"], harness.sha256_file(EXPERIMENTS / binding["path"]))
        harness.validate_run_plan(
            plan,
            self.load("scenarios.json"),
            preregistration,
            experiment_dir=self.root,
        )

        with self.assertRaisesRegex(harness.ExperimentError, "run plan does not match"):
            harness.validate_run_plan(
                plan,
                self.load("scenarios.json"),
                preregistration,
                experiment_dir=EXPERIMENTS,
            )

    def test_plan_command_does_not_launch_subprocess(self):
        output = Path(self.temp.name) / "run-plan.json"
        with mock.patch.object(
            harness.subprocess,
            "run",
            wraps=subprocess.run,
        ) as run_mock:
            self.assertEqual(harness.main(["--experiment-dir", str(self.root), "plan", "--output", str(output)]), 0)
        self.assertTrue(all(call.args[0][0] == "git" for call in run_mock.call_args_list))
        self.assertTrue(output.is_file())
        self.assertEqual(self.load_from(output)["run_count"], 84)

    def load_from(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def valid_trace(self, run_plan: dict, run: dict) -> dict:
        cached = getattr(self, "valid_traces", {}).get(run["run_id"])
        if cached is not None:
            return json.loads(json.dumps(cached))
        preregistration = self.load("preregistration.json")
        scenario = next(item for item in self.load("scenarios.json")["scenarios"] if item["id"] == run["scenario_id"])
        workspace_manifest, files, presented_paths = builder.build_manifest(
            experiment_id=run_plan["experiment_id"],
            pair_id=run["pair_id"],
            scenario=scenario,
            protocol=run["protocol"],
            workspace_seed=run["pair_seed"],
            source_binding=preregistration[
                "baseline" if run["protocol"] == "v1" else "candidate"
            ]["source_snapshot"],
            tool_profile_path=self.root / preregistration["execution_config"]["tool_profile"]["path"],
            tool_profile_root=self.root,
        )
        workspace_root = Path(self.temp.name) / f"{run['run_id']}-workspace"
        if not workspace_root.exists():
            builder.materialize_workspace(workspace_root, files)
        workspace_manifest_path = Path(self.temp.name) / f"{run['run_id']}-workspace-manifest.json"
        workspace_manifest_path.write_bytes(builder.canonical_bytes(workspace_manifest))
        self.workspace_manifests = getattr(self, "workspace_manifests", {})
        self.workspace_roots = getattr(self, "workspace_roots", {})
        self.presented_paths = getattr(self, "presented_paths", {})
        self.workspace_manifests[run["run_id"]] = (workspace_manifest_path, workspace_manifest)
        self.workspace_roots[run["run_id"]] = workspace_root
        self.presented_paths[run["run_id"]] = presented_paths
        adapter = Path(self.temp.name) / "trace-adapter.py"
        if not adapter.exists():
            adapter.write_text("# trace adapter\n", encoding="utf-8", newline="\n")
        authorization = getattr(self, "trace_authorization", None)
        if authorization is None:
            plan_path = Path(self.temp.name) / "trace-run-plan.json"
            authorization, execution_root = self.authorize_fixture(
                adapter,
                plan_path,
                freeze_preregistration=False,
            )
            self.trace_authorization = authorization
            self.trace_execution_root = execution_root
        authorization_value = self.load_from(authorization)
        attempt_id = f"attempt-{run['run_id']}"
        call_index = len(getattr(self, "valid_traces", {}))
        started = datetime(2026, 8, 1, tzinfo=timezone.utc) + timedelta(seconds=call_index * 2)
        ended = started + timedelta(seconds=1)
        started_text = started.isoformat().replace("+00:00", "Z")
        ended_text = ended.isoformat().replace("+00:00", "Z")
        evidence_root = Path(self.temp.name) / f"evidence-{run['run_id']}"
        evidence_root.mkdir(exist_ok=True)
        initial_workspace_path = evidence_root / "workspace-initial.json"
        initial_workspace_path.write_bytes(workspace_manifest_path.read_bytes())
        final_files = [
            {"path": item["path"], "sha256": item["sha256"], "size": item["size"]}
            for item in workspace_manifest["files"]
        ]
        final_workspace = {
            "schema_version": "1.0",
            "algorithm": "sha256-final-workspace-manifest-v1",
            "initial_manifest_sha256": harness.sha256_file(initial_workspace_path),
            "root": ".",
            "files": final_files,
            "changes": {"added": [], "modified": [], "deleted": []},
            "aggregate_sha256": harness.sha256_bytes(harness.canonical_bytes(final_files)),
        }
        final_workspace_path = evidence_root / "workspace-final.json"
        write_json(final_workspace_path, final_workspace)
        claim = {
            "completion_claimed": False,
            "summary": "Fixture remains incomplete.",
            "deliverables": [],
            "blockers": [],
            "risks": [],
        }
        claim_path = evidence_root / "claim.json"
        write_json(claim_path, claim)
        request_path = evidence_root / "request.txt"
        request_path.write_text("request\n", encoding="utf-8", newline="\n")
        response_path = evidence_root / "response.txt"
        response_path.write_text("response\n", encoding="utf-8", newline="\n")
        events_path = evidence_root / "provider-events.jsonl"
        events_path.write_text('{"type":"turn.completed"}\n', encoding="utf-8", newline="\n")
        stderr_path = evidence_root / "stderr.log"
        stderr_path.write_text("", encoding="utf-8", newline="\n")
        trace_source = {
            "schema_version": "1.0",
            "run_id": run["run_id"],
            "episode_id": "E01",
            "attempt_id": attempt_id,
            "started_at": started_text,
            "ended_at": ended_text,
            "events": [{"kind": "fixture"}],
            "completion_claim": claim,
            "not_measured_metrics": sorted(scenario["metrics"]),
        }
        trace_source_path = evidence_root / "trace-source.json"
        write_json(trace_source_path, trace_source)
        population_seal = {
            "schema_version": "1.0",
            "algorithm": "sha256-workspace-population-seal-v1",
            "run_id": run["run_id"],
            "episode_id": "E01",
            "role": authorization_value["role"],
            "prompt_sha256": "0" * 64,
            "output_schema_sha256": "1" * 64,
            "workspace_snapshot_sha256": harness.sha256_file(initial_workspace_path),
            "workspace_aggregate_sha256": workspace_manifest["aggregate_sha256"],
            "file_count": len(workspace_manifest["files"]),
            "protocol_bundle_sha256": harness.sha256_bytes(
                f"fixture-protocol-bundle:{run['protocol']}".encode("utf-8")
            ),
            "protocol_entrypoint_sha256": harness.sha256_bytes(
                f"fixture-protocol-entrypoint:{run['protocol']}".encode("utf-8")
            ),
            "protocol_access": {
                "entrypoint": "../protocol-bundle/SKILL.md",
                "access_available": True,
                "understanding_claimed": False,
            },
            "injection_receipt_sha256": None,
        }
        population_seal_path = evidence_root / "workspace-population-seal.json"
        write_json(population_seal_path, population_seal)
        evidence_files = [
            {"role": role, "path": path.name, "sha256": harness.sha256_file(path)}
            for role, path in (
                ("request", request_path),
                ("provider_events", events_path),
                ("provider_response", response_path),
                ("stderr", stderr_path),
                ("structured_claim", claim_path),
                ("initial_workspace", initial_workspace_path),
                ("final_workspace", final_workspace_path),
                ("workspace_population_seal", population_seal_path),
                ("trace_source", trace_source_path),
            )
        ]
        evidence_manifest = {
            "schema_version": "1.0",
            "run_id": run["run_id"],
            "episode_id": "E01",
            "attempt_id": attempt_id,
            "role": authorization_value["role"],
            "initial_workspace_manifest": {
                "path": initial_workspace_path.name,
                "sha256": harness.sha256_file(initial_workspace_path),
            },
            "final_workspace_manifest": {
                "path": final_workspace_path.name,
                "sha256": harness.sha256_file(final_workspace_path),
            },
            "workspace_population_seal": {
                "path": population_seal_path.name,
                "sha256": harness.sha256_file(population_seal_path),
            },
            "structured_claim": {
                "path": claim_path.name,
                "sha256": harness.sha256_file(claim_path),
            },
            "files": evidence_files,
            "aggregate_sha256": harness.sha256_bytes(harness.canonical_bytes(evidence_files)),
        }
        evidence_path = evidence_root / "evidence-manifest.json"
        evidence_path.write_bytes(guard.canonical_bytes(evidence_manifest))
        receipt = {
            "schema_version": "2.0",
            "receipt_id": f"receipt-{run['run_id']}",
            "authorization_id": authorization_value["authorization_id"],
            "execution_id": authorization_value["execution_id"],
            "run_id": run["run_id"],
            "episode_id": "E01",
            "attempt_id": attempt_id,
            "role": authorization_value["role"],
            "adapter": authorization_value["adapter"],
            "cli_identity": authorization_value["cli_identity"],
            "provider_profile": authorization_value["provider_profile"],
            "model": authorization_value["model"],
            "reasoning_effort": authorization_value["reasoning_effort"],
            "tool_profile": authorization_value["tool_profile"],
            "source_class": "provider-response",
            "provider_request_ids": [f"request-{run['run_id']}"],
            "request_sha256": harness.sha256_file(request_path),
            "response_sha256": harness.sha256_file(response_path),
            "usage": {
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "reasoning_output_tokens": 0,
                "total_tokens": 0,
                "wall_seconds": 1,
            },
            "started_at": started_text,
            "ended_at": ended_text,
            "raw_evidence_sha256": harness.sha256_file(events_path),
            "evidence_manifest_sha256": harness.sha256_file(evidence_path),
        }
        receipt_input = Path(self.temp.name) / f"receipt-{run['run_id']}.json"
        receipt_input.write_bytes(guard.canonical_bytes(receipt))
        guard.reserve(
            self.trace_execution_root,
            run["run_id"],
            attempt_id,
            "E01",
            now=started,
        )
        summary = guard.settle(
            self.trace_execution_root,
            receipt_input,
            evidence_path,
            now=ended,
        )
        stored_receipt = self.trace_execution_root / "receipts" / f"receipt-{guard.sha256_bytes(guard.canonical_bytes(receipt))}.json"
        receipt_binding = Path(self.temp.name) / f"bound-receipt-{run['run_id']}.json"
        receipt_binding.write_bytes(stored_receipt.read_bytes())
        self.trace_receipts = getattr(self, "trace_receipts", {})
        self.trace_receipts[run["run_id"]] = receipt_binding
        self.trace_adapter = adapter
        trace = {
            "schema_version": "2.0",
            "experiment_id": run_plan["experiment_id"],
            "preregistration_sha256": run_plan["preregistration_sha256"],
            "run_plan_sha256": harness.sha256_bytes(harness.canonical_bytes(run_plan)),
            "pair_id": run["pair_id"],
            "run_id": run["run_id"],
            "episode_id": "E01",
            "scenario_id": run["scenario_id"],
            "scenario_slug": run["scenario_slug"],
            "protocol": run["protocol"],
            "repetition": run["repetition"],
            "pair_position": run["pair_position"],
            "pair_seed": run["pair_seed"],
            "role": authorization_value["role"],
            "model": preregistration["execution_config"]["model"],
            "reasoning_effort": preregistration["execution_config"]["reasoning_effort"],
            "tool_profile": run["tool_profile"],
            "provider_profile": authorization_value["provider_profile"],
            "cli_identity": authorization_value["cli_identity"],
            "workspace_seed": run["pair_seed"],
            "input_sha256": run["input_sha256"],
            "baseline_source_sha256": preregistration["baseline"]["source_snapshot"]["aggregate_sha256"],
            "candidate_source_sha256": preregistration["candidate"]["source_snapshot"]["aggregate_sha256"],
            "instrument_manifest_sha256": preregistration["instrument_manifest"]["sha256"],
            "semantic_case_sha256": run["semantic_case_sha256"],
            "workspace_manifest": {
                "path": workspace_manifest_path.name,
                "sha256": harness.sha256_file(workspace_manifest_path),
            },
            "final_workspace_manifest": {
                "path": final_workspace_path.relative_to(Path(self.temp.name)).as_posix(),
                "sha256": harness.sha256_file(final_workspace_path),
            },
            "initial_workspace_manifest_sha256": harness.sha256_file(workspace_manifest_path),
            "final_workspace_manifest_sha256": harness.sha256_file(final_workspace_path),
            "evidence_manifest": {
                "path": evidence_path.relative_to(Path(self.temp.name)).as_posix(),
                "sha256": harness.sha256_file(evidence_path),
            },
            "evidence_manifest_sha256": harness.sha256_file(evidence_path),
            "usage_receipt": {"path": receipt_binding.name, "sha256": harness.sha256_file(receipt_binding)},
            "execution_authority": {
                "grant_sha256": harness.sha256_file(authorization),
                "ledger_last_seq": summary["ledger_last_seq"],
                "ledger_tail_sha256": summary["ledger_tail_sha256"],
            },
            "adapter": {"id": "fake", "version": "1", "sha256": harness.sha256_file(adapter)},
            "trace_source": {
                "path": trace_source_path.relative_to(Path(self.temp.name)).as_posix(),
                "sha256": harness.sha256_file(trace_source_path),
            },
            "started_at": started_text,
            "ended_at": ended_text,
            "budget": {
                "total_tokens_limit": authorization_value["limits"]["per_call"]["max_total_tokens"],
                "seconds_limit": authorization_value["limits"]["per_call"]["max_wall_seconds"],
                "total_tokens_used": 0,
                "elapsed_seconds": 1,
            },
            "events": [
                {"seq": 1, "ts": started_text, "kind": "adapter_started", "summary": "Started.", "payload_sha256": None},
                {"seq": 2, "ts": started_text, "kind": "model_request", "summary": "Requested.", "payload_sha256": receipt["request_sha256"]},
                {"seq": 3, "ts": ended_text, "kind": "model_response", "summary": "Responded.", "payload_sha256": receipt["response_sha256"]},
                {"seq": 4, "ts": ended_text, "kind": "adapter_finished", "summary": "Finished.", "payload_sha256": None},
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
                "metric_observations": {metric: "not-measured" for metric in scenario["metrics"]},
            },
            "goal_satisfied": None,
        }
        self.valid_traces = getattr(self, "valid_traces", {})
        self.valid_traces[run["run_id"]] = trace
        return json.loads(json.dumps(trace))

    def test_scenario_content_drift_is_rejected(self):
        scenarios = self.load("scenarios.json")
        scenarios["scenarios"][0]["input"]["task"] += " Drift."
        write_json(self.root / "scenarios.json", scenarios)
        preregistration = self.load("preregistration.json")
        preregistration["scenario_manifest"]["sha256"] = harness.sha256_file(self.root / "scenarios.json")
        write_json(self.root / "preregistration.json", preregistration)
        with self.assertRaisesRegex(harness.ExperimentError, "input_sha256 mismatch"):
            harness.load_and_validate(self.root)

    def test_preregistration_hash_drift_is_rejected(self):
        preregistration = self.load("preregistration.json")
        preregistration["scenario_manifest"]["sha256"] = "f" * 64
        write_json(self.root / "preregistration.json", preregistration)
        with self.assertRaisesRegex(harness.ExperimentError, "scenario manifest hash"):
            harness.load_and_validate(self.root)

    def test_baseline_artifact_drift_is_rejected(self):
        preregistration = self.load("preregistration.json")
        preregistration["baseline"]["audit_record_sha256"] = "f" * 64
        with self.assertRaisesRegex(harness.ExperimentError, "baseline commit artifact hash"):
            harness.validate_baseline_binding(preregistration)

    def test_candidate_source_drift_is_rejected(self):
        manifest = self.load("candidate-source.json")
        manifest["files"][0]["sha256"] = "f" * 64
        write_json(self.root / "candidate-source.json", manifest)
        preregistration = self.load("preregistration.json")
        preregistration["candidate"]["source_snapshot"]["manifest"]["sha256"] = harness.sha256_file(self.root / "candidate-source.json")
        write_json(self.root / "preregistration.json", preregistration)
        with self.assertRaisesRegex(harness.ExperimentError, "v2 source snapshot invalid"):
            harness.load_and_validate(self.root)

    def test_trace_drift_is_rejected(self):
        run_plan = self.run_plan()
        run = run_plan["runs"][0]
        trace = self.valid_trace(run_plan, run)
        trace["protocol"] = "v1" if run["protocol"] == "v2" else "v2"
        path = Path(self.temp.name) / "trace.json"
        write_json(path, trace)
        with self.assertRaisesRegex(harness.ExperimentError, "protocol drifted"):
                harness.validate_trace(
                    self.root,
                    path,
                    run_plan,
                    self.load("preregistration.json"),
                    adapter_path=self.trace_adapter,
                    authorization_path=self.trace_authorization,
                    execution_root=self.trace_execution_root,
                )

    def test_trace_resolves_workspace_manifest_and_rejects_reality_drift(self):
        run_plan = self.run_plan()
        run = run_plan["runs"][0]
        trace = self.valid_trace(run_plan, run)
        path = Path(self.temp.name) / "workspace-trace.json"
        write_json(path, trace)
        harness.validate_trace(
            self.root,
            path,
            run_plan,
            self.load("preregistration.json"),
            adapter_path=self.trace_adapter,
            authorization_path=self.trace_authorization,
            execution_root=self.trace_execution_root,
            workspace_root=self.workspace_roots[run["run_id"]],
        )
        workspace_manifest_path, workspace_manifest = self.workspace_manifests[run["run_id"]]
        workspace_manifest["semantic_case_sha256"] = "f" * 64
        write_json(workspace_manifest_path, workspace_manifest)
        trace["workspace_manifest"]["sha256"] = harness.sha256_file(workspace_manifest_path)
        write_json(path, trace)
        with self.assertRaisesRegex(harness.ExperimentError, "semantic_case_sha256 drifted"):
            harness.validate_trace(
                self.root,
                path,
                run_plan,
                self.load("preregistration.json"),
                adapter_path=self.trace_adapter,
                authorization_path=self.trace_authorization,
                execution_root=self.trace_execution_root,
            )

    def test_trace_snapshot_is_private_and_public_validation_replays_current_authority(self):
        run_plan = self.run_plan()
        run = run_plan["runs"][0]
        trace = self.valid_trace(run_plan, run)
        path = Path(self.temp.name) / "summary-trace.json"
        write_json(path, trace)
        preregistration = self.load("preregistration.json")
        snapshot = guard.replay_snapshot(self.trace_execution_root)

        with mock.patch.object(guard, "replay", wraps=guard.replay) as replay:
            harness._validate_trace_with_execution_snapshot(
                self.root,
                path,
                run_plan,
                preregistration,
                adapter_path=self.trace_adapter,
                authorization_path=self.trace_authorization,
                execution_root=self.trace_execution_root,
                execution_snapshot=snapshot,
                workspace_root=self.workspace_roots[run["run_id"]],
            )
        replay.assert_not_called()

        with self.assertRaisesRegex(
            harness.ExperimentError,
            "invalid execution replay snapshot",
        ):
            harness._validate_trace_with_execution_snapshot(
                self.root,
                path,
                run_plan,
                preregistration,
                adapter_path=self.trace_adapter,
                authorization_path=self.trace_authorization,
                execution_root=self.trace_execution_root,
                execution_snapshot=object(),
                workspace_root=self.workspace_roots[run["run_id"]],
            )

        (self.trace_execution_root / "receipts" / "unexpected.txt").write_text(
            "authority drift\n", encoding="utf-8", newline="\n"
        )
        with self.assertRaisesRegex(
            harness.ExperimentError,
            "execution_snapshot is private",
        ):
            harness.validate_trace(
                self.root,
                path,
                run_plan,
                preregistration,
                adapter_path=self.trace_adapter,
                authorization_path=self.trace_authorization,
                execution_root=self.trace_execution_root,
                execution_snapshot=snapshot,
                workspace_root=self.workspace_roots[run["run_id"]],
            )

        with mock.patch.object(guard, "replay", wraps=guard.replay) as replay:
            with self.assertRaisesRegex(
                harness.ExperimentError,
                "receipt root contains unexpected entries",
            ):
                harness.validate_trace(
                    self.root,
                    path,
                    run_plan,
                    preregistration,
                    adapter_path=self.trace_adapter,
                    authorization_path=self.trace_authorization,
                    execution_root=self.trace_execution_root,
                    workspace_root=self.workspace_roots[run["run_id"]],
                )
        replay.assert_called_once()

    def test_complete_trace_set_rejects_missing_runs(self):
        run_plan = self.run_plan()
        with self.assertRaisesRegex(harness.ExperimentError, "trace set is incomplete"):
            adapter, _ = self.make_fake_adapter()
            authorization, execution_root = self.authorize_fixture(adapter, Path(self.temp.name) / "empty-plan.json")
            harness.validate_trace_set(
                self.root,
                [],
                run_plan,
                self.load("preregistration.json"),
                adapter_path=adapter,
                authorization_path=authorization,
                execution_root=execution_root,
            )

    def test_trace_rejects_timing_metrics_and_outcome_incoherence(self):
        run_plan = self.run_plan()
        run = run_plan["runs"][0]
        cases = []
        trace = self.valid_trace(run_plan, run)
        trace["events"][1]["ts"] = "2025-07-31T23:59:59Z"
        cases.append((trace, "timestamps must be monotonic|outside the run interval"))
        trace = self.valid_trace(run_plan, run)
        trace["outcome"]["metric_observations"]["fabricated"] = 1
        cases.append((trace, "metric_observations|metric observations"))
        trace = self.valid_trace(run_plan, run)
        trace["outcome"]["goal_satisfied"] = True
        cases.append((trace, "goal_satisfied"))
        for index, (case, message) in enumerate(cases):
            path = Path(self.temp.name) / f"bad-trace-{index}.json"
            write_json(path, case)
            with self.assertRaisesRegex(harness.ExperimentError, message):
                harness.validate_trace(
                    self.root,
                    path,
                    run_plan,
                    self.load("preregistration.json"),
                    adapter_path=self.trace_adapter,
                    authorization_path=self.trace_authorization,
                    execution_root=self.trace_execution_root,
                )

    def test_blind_manifest_rejects_duplicate_label_and_path_escape(self):
        run_plan = self.run_plan()
        pair = run_plan["runs"][:2]
        trace_paths = []
        for run in pair:
            path = Path(self.temp.name) / f"{run['run_id']}.json"
            write_json(path, self.valid_trace(run_plan, run))
            trace_paths.append(path)
        review_root = Path(self.temp.name) / "review"
        review_root.mkdir()
        context = review_root / "context.txt"
        context.write_text("context", encoding="utf-8", newline="\n")
        assignment = harness.blind_assignment(pair[0]["pair_id"], self.load("preregistration.json")["pairing"]["order_seed"])
        protocol_runs = {run["protocol"]: run for run in pair}
        presented = []
        for label in ("A", "B"):
            run = protocol_runs[assignment[label]]
            workspace_root = self.workspace_roots[run["run_id"]]
            workspace_manifest = self.workspace_manifests[run["run_id"]][1]
            for relative in self.presented_paths[run["run_id"]]:
                target = workspace_root / relative
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(f"presented {label}\n", encoding="utf-8", newline="\n")
            artifact = builder.build_presented_artifact(
                workspace_root,
                workspace_manifest,
                self.presented_paths[run["run_id"]],
            )
            artifact_path = review_root / label / "presented.json"
            artifact_path.parent.mkdir()
            write_json(artifact_path, artifact)
            for entry in artifact["files"]:
                source = workspace_root / entry["path"]
                target = artifact_path.parent / entry["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            trace_path = next(path for path in trace_paths if path.stem == run["run_id"])
            presented.append({
                "label": label,
                "presented_artifact": {
                    "path": artifact_path.relative_to(review_root).as_posix(),
                    "sha256": harness.sha256_file(artifact_path),
                },
                "trace_sha256": harness.sha256_file(trace_path),
            })
        manifest = {
            "schema_version": "1.0",
            "experiment_id": run_plan["experiment_id"],
            "preregistration_sha256": run_plan["preregistration_sha256"],
            "review_id": "review-1",
            "pair_id": pair[0]["pair_id"],
            "scenario_id": pair[0]["scenario_id"],
            "reviewer": {
                "id": "reviewer",
                "kind": "model",
                "model": "review-model",
                "reasoning_effort": "ultra",
                "context_isolation": "fresh-session",
            },
            "producer_protocols_withheld": True,
            "assignment_seed": self.load("preregistration.json")["pairing"]["order_seed"],
            "presented": [presented[0], {**presented[1], "label": "A"}],
            "delivered_context": [{"path": "context.txt", "sha256": harness.sha256_file(context), "purpose": "review"}],
            "created_at": "2026-08-01T00:00:00Z",
        }
        path = Path(self.temp.name) / "blind.json"
        write_json(path, manifest)
        with self.assertRaisesRegex(harness.ExperimentError, "labels must be exactly"):
            harness.validate_blind_review_manifest(
                self.root,
                path,
                run_plan,
                self.load("preregistration.json"),
                trace_paths,
                review_root,
                adapter_path=self.trace_adapter,
                authorization_path=self.trace_authorization,
                execution_root=self.trace_execution_root,
            )
        manifest["presented"][1]["label"] = "B"
        manifest["delivered_context"][0]["path"] = "../outside"
        write_json(path, manifest)
        with self.assertRaisesRegex(harness.ExperimentError, "schema validation failed|path must remain"):
            harness.validate_blind_review_manifest(
                self.root,
                path,
                run_plan,
                self.load("preregistration.json"),
                trace_paths,
                review_root,
                adapter_path=self.trace_adapter,
                authorization_path=self.trace_authorization,
                execution_root=self.trace_execution_root,
            )

    def test_blind_manifest_rejects_presented_artifact_drift(self):
        run_plan = self.run_plan()
        pair = run_plan["runs"][:2]
        trace_paths = []
        for run in pair:
            path = Path(self.temp.name) / f"{run['run_id']}.json"
            write_json(path, self.valid_trace(run_plan, run))
            trace_paths.append(path)
        review_root = Path(self.temp.name) / "review-artifact"
        review_root.mkdir()
        context = review_root / "context.txt"
        context.write_text("context", encoding="utf-8", newline="\n")
        assignment_seed = self.load("preregistration.json")["pairing"]["order_seed"]
        assignment = harness.blind_assignment(pair[0]["pair_id"], assignment_seed)
        by_protocol = {run["protocol"]: run for run in pair}
        presented = []
        for label in ("A", "B"):
            run = by_protocol[assignment[label]]
            root = self.workspace_roots[run["run_id"]]
            manifest = self.workspace_manifests[run["run_id"]][1]
            for relative in self.presented_paths[run["run_id"]]:
                target = root / relative
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(f"{label}\n", encoding="utf-8", newline="\n")
            artifact = builder.build_presented_artifact(root, manifest, self.presented_paths[run["run_id"]])
            if label == "A":
                artifact["semantic_case_sha256"] = "f" * 64
            artifact_path = review_root / label / "presented.json"
            artifact_path.parent.mkdir()
            write_json(artifact_path, artifact)
            for entry in artifact["files"]:
                source = root / entry["path"]
                target = artifact_path.parent / entry["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            trace_path = next(path for path in trace_paths if path.stem == run["run_id"])
            presented.append({
                "label": label,
                "presented_artifact": {
                    "path": artifact_path.relative_to(review_root).as_posix(),
                    "sha256": harness.sha256_file(artifact_path),
                },
                "trace_sha256": harness.sha256_file(trace_path),
            })
        blind = {
            "schema_version": "1.0",
            "experiment_id": run_plan["experiment_id"],
            "preregistration_sha256": run_plan["preregistration_sha256"],
            "review_id": "review-artifact",
            "pair_id": pair[0]["pair_id"],
            "scenario_id": pair[0]["scenario_id"],
            "reviewer": {
                "id": "reviewer",
                "kind": "model",
                "model": "review-model",
                "reasoning_effort": "ultra",
                "context_isolation": "fresh-session",
            },
            "producer_protocols_withheld": True,
            "assignment_seed": assignment_seed,
            "presented": presented,
            "delivered_context": [{"path": "context.txt", "sha256": harness.sha256_file(context), "purpose": "review"}],
            "created_at": "2026-08-01T00:00:00Z",
        }
        blind_path = Path(self.temp.name) / "blind-artifact.json"
        write_json(blind_path, blind)
        with self.assertRaisesRegex(harness.ExperimentError, "semantic_case_sha256 drifted"):
            harness.validate_blind_review_manifest(
                self.root,
                blind_path,
                run_plan,
                self.load("preregistration.json"),
                trace_paths,
                review_root,
                adapter_path=self.trace_adapter,
                authorization_path=self.trace_authorization,
                execution_root=self.trace_execution_root,
            )

    def test_report_rejects_fabricated_eligibility(self):
        run_plan = self.run_plan()
        preregistration = self.load("preregistration.json")
        report = {
            "schema_version": "1.0",
            "experiment_id": run_plan["experiment_id"],
            "preregistration_sha256": run_plan["preregistration_sha256"],
            "run_plan_sha256": harness.sha256_bytes(harness.canonical_bytes(run_plan)),
            "generated_at": "2026-08-01T00:00:00Z",
            "run_summary": {"planned": 84, "valid": 84, "failed": 0, "missing": 0, "excluded_with_reason": 0},
            "metrics": {
                metric: {"v1": 1, "v2": 1, "comparison": 1, "unit": "fabricated", "sample_count": 84}
                for metric in sorted(harness.EXPECTED_METRICS)
            },
            "gate_results": [
                {
                    "gate": gate,
                    "status": "pass",
                    "observed": 1,
                    "threshold": preregistration["gates"][gate],
                    "evidence_refs": [f"fabricated:{gate}"],
                }
                for gate in sorted(harness.EXPECTED_GATES)
            ],
            "decision": {"recommendation": "eligible-for-v2-default-review", "rationale": "fake", "semantic_reviewer": "fake"},
            "limitations": ["none"],
        }
        path = Path(self.temp.name) / "report.json"
        write_json(path, report)
        with self.assertRaisesRegex(harness.ExperimentError, "legacy report cannot claim eligibility"):
            harness.validate_report(self.root, path, run_plan, preregistration)

    def test_aggregator_requires_exact_inputs_and_cannot_claim_eligibility(self):
        run_plan = self.run_plan()
        preregistration = self.load("preregistration.json")
        with self.assertRaisesRegex(harness.ExperimentError, "exact 84-run and 42-pair"):
            harness.aggregate_results(
                preregistration,
                run_plan,
                validated_trace_ids=set(),
                validated_review_pair_ids=set(),
            )
        report = harness.aggregate_results(
            preregistration,
            run_plan,
            validated_trace_ids={run["run_id"] for run in run_plan["runs"]},
            validated_review_pair_ids={run["pair_id"] for run in run_plan["runs"]},
        )
        self.assertEqual(set(report["metrics"]), harness.EXPECTED_METRICS)
        self.assertEqual({item["gate"] for item in report["gate_results"]}, harness.EXPECTED_GATES)
        self.assertEqual(report["decision"]["recommendation"], "extend-experiment")
        path = Path(self.temp.name) / "aggregate-report.json"
        write_json(path, report)
        harness.validate_report(self.root, path, run_plan, preregistration)

    def test_execute_without_flag_never_launches_adapter(self):
        adapter, marker = self.make_fake_adapter()
        run_plan_path = Path(self.temp.name) / "run-plan.json"
        authorization_path = Path(self.temp.name) / "authorization.json"
        write_json(run_plan_path, self.run_plan())
        write_json(authorization_path, {})
        with mock.patch.object(harness.subprocess, "run", side_effect=AssertionError("subprocess launched")):
            with self.assertRaisesRegex(harness.ExperimentError, "explicit --execute"):
                harness.execute_adapter(
                    self.root, run_plan_path, adapter, authorization_path,
                    Path(self.temp.name) / "execution", Path(self.temp.name) / "output", execute=False,
                    run_id="S01-P01-v1", episode_id="E01",
                )
        self.assertFalse(marker.exists())

    def test_missing_adapter_never_reaches_authorization_or_subprocess(self):
        missing_adapter = Path(self.temp.name) / "missing.py"
        run_plan_path = Path(self.temp.name) / "run-plan.json"
        authorization_path = Path(self.temp.name) / "authorization.json"
        write_json(run_plan_path, self.run_plan())
        write_json(authorization_path, {})
        with mock.patch.object(harness.subprocess, "run", side_effect=AssertionError("subprocess launched")):
            with self.assertRaisesRegex(harness.ExperimentError, "existing regular file"):
                harness.execute_adapter(
                    self.root, run_plan_path, missing_adapter, authorization_path,
                    Path(self.temp.name) / "execution", Path(self.temp.name) / "output", execute=True,
                    run_id="S01-P01-v1", episode_id="E01",
                )

    def test_repository_preregistration_cannot_execute_paid_adapter(self):
        adapter, marker = self.make_fake_adapter()
        run_plan_path = Path(self.temp.name) / "run-plan.json"
        write_json(run_plan_path, self.run_plan())
        authorization_path = Path(self.temp.name) / "authorization.json"
        write_json(authorization_path, {})
        with mock.patch.object(harness.subprocess, "run", wraps=subprocess.run) as run_mock:
            with self.assertRaisesRegex(harness.ExperimentError, "preregistration must be frozen|authorization grant is invalid"):
                harness.execute_adapter(
                    self.root, run_plan_path, adapter, authorization_path,
                    Path(self.temp.name) / "execution", Path(self.temp.name) / "output", execute=True,
                    run_id="S01-P01-v1", episode_id="E01",
                    now=datetime(2026, 8, 1, 12, tzinfo=timezone.utc),
                )
        self.assertTrue(all(call.args[0][0] == "git" for call in run_mock.call_args_list))
        self.assertFalse(marker.exists())

    def test_mismatched_authorization_hash_never_launches_adapter(self):
        adapter, marker = self.make_fake_adapter()
        run_plan_path = Path(self.temp.name) / "run-plan.json"
        authorization_path, execution_root = self.authorize_fixture(adapter, run_plan_path)
        tampered_adapter = Path(self.temp.name) / "other-adapter.py"
        tampered_adapter.write_text("# different\n", encoding="utf-8", newline="\n")
        with mock.patch.object(harness.subprocess, "run", wraps=subprocess.run) as run_mock:
            with self.assertRaisesRegex(harness.ExperimentError, "adapter hash mismatch"):
                harness.execute_adapter(
                    self.root, run_plan_path, tampered_adapter, authorization_path,
                    execution_root, Path(self.temp.name) / "output", execute=True,
                    run_id="S01-P01-v1", episode_id="E01",
                    now=datetime(2026, 8, 1, 12, tzinfo=timezone.utc),
                )
        self.assertTrue(all(call.args[0][0] == "git" for call in run_mock.call_args_list))
        self.assertFalse(marker.exists())

    def test_authorized_total_token_budget_cannot_undercut_reserved_calls(self):
        adapter, marker = self.make_fake_adapter()
        run_plan_path = Path(self.temp.name) / "run-plan.json"
        with self.assertRaisesRegex(guard.GuardError, "per-call|max_total_tokens|total authorization"):
            self.authorize_fixture(adapter, run_plan_path, total_tokens=99)
        self.assertFalse(marker.exists())

    def test_static_execution_kill_switch_remains_available(self):
        adapter, marker = self.make_fake_adapter()
        run_plan_path = Path(self.temp.name) / "run-plan.json"
        authorization_path, execution_root = self.authorize_fixture(adapter, run_plan_path)
        expected_capabilities = {
            "concrete workspace, oracle, reviewer, and deterministic input schemas are implemented",
            "offline metric and gate formulas are implemented",
        }
        expected_blockers = {"maintenance freeze"}
        stale_false_blockers = {
            "fixture oracles, review results, and metric or gate formulas are not implemented",
            "the adapter trust boundary cannot yet enforce per-run token, time, and cost limits",
            "authorization consumption and durable spend receipts are not implemented",
        }
        self.assertEqual(harness.IMPLEMENTED_OFFLINE_CAPABILITIES, expected_capabilities)
        self.assertEqual(harness.EXECUTION_BLOCKERS, set())
        with mock.patch.object(harness, "EXECUTION_BLOCKERS", expected_blockers), mock.patch.object(harness.subprocess, "run", wraps=subprocess.run) as run_mock:
            with self.assertRaisesRegex(harness.ExperimentError, "formal execution remains disabled") as caught:
                harness.execute_adapter(
                    self.root, run_plan_path, adapter, authorization_path,
                    execution_root, Path(self.temp.name) / "output", execute=True,
                    run_id="S01-P01-v1", episode_id="E01",
                    now=datetime(2026, 8, 1, 12, tzinfo=timezone.utc),
                )
        for blocker in expected_blockers:
            self.assertIn(blocker, str(caught.exception))
        for stale in stale_false_blockers:
            self.assertNotIn(stale, str(caught.exception))
        self.assertTrue(all(call.args[0][0] == "git" for call in run_mock.call_args_list))
        self.assertFalse(marker.exists())

    def test_cli_execute_without_explicit_flag_does_not_launch(self):
        adapter, marker = self.make_fake_adapter()
        run_plan_path = Path(self.temp.name) / "run-plan.json"
        write_json(run_plan_path, self.run_plan())
        authorization_path = Path(self.temp.name) / "authorization.json"
        write_json(authorization_path, {})
        command = [
            sys.executable, str(EXPERIMENTS / "experiment_harness.py"),
            "--experiment-dir", str(self.root), "execute",
            "--run-plan", str(run_plan_path), "--adapter", str(adapter),
            "--authorization", str(authorization_path), "--execution-root", str(Path(self.temp.name) / "execution"),
            "--output-dir", str(Path(self.temp.name) / "out"),
            "--run-id", "S01-P01-v1", "--episode-id", "E01",
        ]
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("explicit --execute", result.stderr)
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
