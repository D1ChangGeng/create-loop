from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = SKILL_ROOT / "tests" / "experiments"
import sys

sys.path.insert(0, str(EXPERIMENTS))

import codex_exec_adapter as adapter  # noqa: E402
import execution_guard as guard  # noqa: E402
import network_execution_boundary as execution_boundary  # noqa: E402
import pilot_freeze as freeze  # noqa: E402
import workspace_builder as workspaces  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(adapter.canonical_bytes(value))


FAKE_CODEX = r'''#!/usr/bin/env python3
import json, os, pathlib, sys, time

args = sys.argv[1:]
workspace = pathlib.Path(args[args.index("--cd") + 1])
output = pathlib.Path(args[args.index("--output-last-message") + 1])
mode = os.environ.get("FAKE_CODEX_MODE", "success")
if mode == "nonzero":
    print("fake failure", file=sys.stderr)
    raise SystemExit(7)
if mode == "timeout":
    time.sleep(30)
if mode == "s1":
    reality = workspace / "reality" / "account.json"
    data = json.loads(reality.read_text())
    data["applied_count"] += 1
    data["operation_ids"].append("pilot-credit-001")
    reality.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n")
    (workspace / "reality" / "effect-applied-before-post.json").write_text(json.dumps({
        "operation_id":"pilot-credit-001","post_recorded":False
    }, sort_keys=True, separators=(",", ":")) + "\n")
    print(json.dumps({"type":"item.started","provider_request_id":"provider-s1"}), flush=True)
    time.sleep(30)
if mode == "s1-post-race":
    reality = workspace / "reality" / "account.json"
    data = json.loads(reality.read_text())
    data["applied_count"] += 1
    data["operation_ids"].append("pilot-credit-001")
    reality.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n")
    (workspace / "reality" / "effect-applied-before-post.json").write_text(json.dumps({
        "operation_id":"pilot-credit-001","post_recorded":False
    }, sort_keys=True, separators=(",", ":")) + "\n")
    (workspace / "reality" / "effect-post.json").write_text('{"operation_id":"pilot-credit-001","outcome":"ok"}\n')
    time.sleep(30)
if mode == "s1-recover":
    reality = json.loads((workspace / "reality" / "account.json").read_text())
    if reality != {"applied_count":1,"operation_ids":["pilot-credit-001"]}:
        raise SystemExit(9)
    (workspace / "recovery-decision.md").write_text("Reality queried first; operation already applied exactly once; no retry.\n")
request_id = None if mode == "missing-request" else "provider-1"
first = {"type":"response.started"}
if request_id is not None:
    first["provider_request_id"] = request_id
print(json.dumps(first), flush=True)
if mode == "ambiguous-request":
    print(json.dumps({"type":"response.completed","provider_request_id":"provider-2"}), flush=True)
usage = {
    "input_tokens": 20,
    "cached_input_tokens": 5,
    "output_tokens": 10,
    "reasoning_output_tokens": 4,
    "total_tokens": 30,
}
completed = {"type":"turn.completed","provider_request_id":request_id,"usage":usage}
if mode == "missing-usage":
    completed.pop("usage")
print(json.dumps(completed), flush=True)
output.write_text(json.dumps({
    "completion_claimed": True,
    "summary": "fake completed",
    "deliverables": [],
    "blockers": [],
    "risks": [],
}, sort_keys=True))
'''


class CodexAdapterEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.experiment = self.base / "experiment"
        shutil.copytree(EXPERIMENTS, self.experiment)
        self.plan = json.loads((self.experiment / "pilot-run-plan.json").read_text(encoding="utf-8"))
        cases = {
            item["case_id"]: item
            for item in json.loads(
                (self.experiment / "pilot-scenarios.json").read_text(encoding="utf-8")
            )["cases"]
        }
        pilot_preregistration = json.loads((self.experiment / "pilot-preregistration.json").read_text(encoding="utf-8"))
        for arm in self.plan["arms"]:
            manifest, _, _ = workspaces.build_pilot_manifest(
                pair_id=arm["pair_id"],
                case=cases[arm["case_id"]],
                protocol=arm["protocol"],
                workspace_seed=arm["workspace_seed"],
                source_binding=pilot_preregistration["baseline" if arm["protocol"] == "v1" else "candidate"],
                tool_profile_path=self.experiment / arm["tool_profile"]["path"],
                tool_profile_root=self.experiment,
            )
            arm["initial_workspace_manifest_sha256"] = adapter.sha256_bytes(
                workspaces.canonical_bytes(manifest)
            )
        evaluator_path = self.experiment / "pilot-evaluator-manifest.json"
        evaluator = json.loads(evaluator_path.read_text(encoding="utf-8"))
        evaluator["scenario_manifest"]["sha256"] = adapter.sha256_file(
            self.experiment / evaluator["scenario_manifest"]["path"]
        )
        for case in evaluator["cases"]:
            for check in case["hidden_checks"]:
                check["sha256"] = adapter.sha256_file(self.experiment / check["path"])
        for injection in evaluator["injections"]:
            for binding in injection["files"]:
                binding["sha256"] = adapter.sha256_file(self.experiment / binding["path"])
        write_json(evaluator_path, evaluator)
        self.install_execution_boundary()
        write_json(self.experiment / "pilot-run-plan.json", self.plan)
        self.plan_hash = adapter.sha256_bytes(adapter.canonical_bytes(self.plan))
        self.fake = self.base / "fake-codex.py"
        self.fake.write_text(FAKE_CODEX, encoding="utf-8", newline="\n")
        self.output = self.base / "output"
        self.output.mkdir()
        self.execution = self.base / "execution"
        self.authority_freeze = self.base / "final-freeze.json"
        self.authority_freeze.write_text("final\n", encoding="utf-8", newline="\n")
        self.spawn_commands: list[list[str]] = []

    def bind(self, path: Path, *, identity: str | None = None) -> dict[str, str]:
        value = {
            "path": path.relative_to(self.experiment).as_posix(),
            "sha256": adapter.sha256_file(path),
        }
        return {"id": identity, **value} if identity is not None else value

    def install_execution_boundary(self) -> None:
        reviewer_path = self.experiment / "cli-identities/codex-0.144.1-linux-x64.json"
        write_json(reviewer_path, {
            "schema_version": "1.0", "id": "codex-0.144.1-linux-x64",
            "product": "codex-cli", "version": "0.144.1", "platform": "linux",
            "arch": "x86_64", "package_tree_sha256": "5" * 64,
            "launcher": {"path": "codex", "sha256": "6" * 64},
            "entrypoint": {"path": "bin/codex.js", "sha256": "7" * 64},
            "package": {"path": "package.json", "sha256": "8" * 64},
            "native_executable": {"path": "vendor/bin/codex", "sha256": "9" * 64},
        })
        backend = self.experiment / "network/backend.json"
        launch_adapter = self.experiment / "network/adapter.py"
        launcher = Path(sys.executable).resolve()
        policy = self.experiment / "network/policy.json"
        provider_probe = self.experiment / "network/provider-probe.json"
        denied_probe = self.experiment / "network/denied-probe.json"
        for path, value in (
            (backend, {"backend": "fixture-firewall", "version": "1"}),
            (policy, {"default": "deny", "allow": ["api.payapionline.top:443"]}),
            (provider_probe, {"endpoint": "api.payapionline.top:443", "result": "allowed"}),
            (denied_probe, {"endpoint": "example.com:443", "result": "denied"}),
        ):
            write_json(path, value)
        launch_adapter.write_text(
            "import subprocess,sys\n"
            "args=sys.argv[1:]\n"
            "if len(args) < 6 or args[0] != '--session' or args[2] != '--role' or args[4] != '--':\n"
            "    raise SystemExit(91)\n"
            "raise SystemExit(subprocess.run(args[5:]).returncode)\n",
            encoding="utf-8",
            newline="\n",
        )
        provider_path = self.experiment / "provider-profiles/custom-zeo-responses.json"
        boundary_path = self.experiment / "network/boundary.json"
        write_json(boundary_path, {
            "schema_version": "1.0", "id": "fake-provider-only-boundary",
            "policy": "provider-api-only",
            "roles": ["calibration", "producer", "reviewer"],
            "provider_profile_sha256": adapter.sha256_file(provider_path),
            "allowed_endpoint": {
                "scheme": "https", "host": "api.payapionline.top", "port": 443,
                "path_prefix": "/v1",
            },
            "enforcement": {
                "backend": "test-provider-boundary-v1", "backend_identity": self.bind(backend),
                "launcher": {
                    "path": str(launcher), "sha256": adapter.sha256_file(launcher),
                },
                "adapter": self.bind(launch_adapter),
                "launch_arguments": [
                    "{adapter}", "--session", "{session_id}", "--role", "{role}",
                    "--", "{command}",
                ],
                "session_id": "adapter-fixture-session",
                "default_action": "deny", "applies_to_process_tree": True,
                "dns_fail_closed": True,
            },
            "verification": {
                "policy_export": self.bind(policy), "provider_probe": self.bind(provider_probe),
                "denied_probe": self.bind(denied_probe), "provider_probe_result": "allowed",
                "denied_probe_result": "denied", "session_id": "adapter-fixture-session",
                "launcher_sha256": adapter.sha256_file(launcher),
                "adapter_sha256": adapter.sha256_file(launch_adapter),
                "verified_at": "2026-08-04T00:00:00Z",
                "valid_until": "2099-08-06T00:00:00Z",
            },
        })
        preregistration_path = self.experiment / "pilot-preregistration.json"
        preregistration = json.loads(preregistration_path.read_text(encoding="utf-8"))
        preregistration["cli_identities"]["reviewer"] = {
            "status": "frozen", "platform": "linux", "arch": "x86_64",
            "version": "0.144.1", "binding": self.bind(
                reviewer_path, identity="codex-0.144.1-linux-x64"
            ), "reason": None,
        }
        preregistration["execution"]["network_boundary"] = {
            "status": "frozen", "binding": self.bind(
                boundary_path, identity="fake-provider-only-boundary"
            ), "reason": None,
        }
        write_json(preregistration_path, preregistration)
        self.network_launcher = launcher
        self.network_launch_adapter = launch_adapter
        self.network_adapter_sha256 = adapter.sha256_file(launch_adapter)
        with mock.patch.object(
            execution_boundary,
            "TRUSTED_LAUNCH_BACKENDS",
            {"test-provider-boundary-v1": self.network_adapter_sha256},
        ):
            self.assertEqual(
                execution_boundary.inspect_execution_blockers(
                    preregistration, self.experiment, required_role="producer"
                ), []
            )

    def arm_episode(self, run_id: str) -> tuple[dict, dict]:
        return adapter._select_episode(self.plan, run_id, run_id.rsplit("-", 1)[-1])

    @contextmanager
    def fresh_case(self):
        old_execution, old_output = self.execution, self.output
        with tempfile.TemporaryDirectory(dir=self.base) as temporary:
            root = Path(temporary)
            self.execution = root / "execution"
            self.output = root / "output"
            self.output.mkdir()
            try:
                yield self.execution, self.output
            finally:
                self.execution, self.output = old_execution, old_output

    def grant(self, run_id: str) -> Path:
        arm, episode = self.arm_episode(run_id)
        root_hash = guard._root_path_sha256(self.execution)
        value = {
            "schema_version": "2.0",
            "authorization_id": "authorization-pilot",
            "execution_id": "execution-pilot",
            "execution_root_sha256": root_hash,
            "experiment_id": self.plan["campaign_id"],
            "preregistration_sha256": self.plan["preregistration_sha256"],
            "run_plan_sha256": self.plan_hash,
            "role": "producer",
            "adapter": adapter.adapter_binding(),
            "cli_identity": {
                "id": "codex-0.144.1-windows",
                "path": "cli-identities/codex-0.144.1-windows.json",
                "sha256": adapter.sha256_file(self.experiment / "cli-identities/codex-0.144.1-windows.json"),
            },
            "provider_profile": {
                "id": "custom-zeo-responses-ultra",
                "path": "provider-profiles/custom-zeo-responses.json",
                "sha256": adapter.sha256_file(self.experiment / "provider-profiles/custom-zeo-responses.json"),
            },
            "model": "gpt-5.6-sol",
            "reasoning_effort": "ultra",
            "tool_profile": arm["tool_profile"],
            "authorized_calls": [{"run_id": run_id, "episode_id": episode["episode_id"]}],
            "limits": {
                "per_call": {"max_total_tokens": 100, "max_wall_seconds": 3},
                "total": {"max_calls": 1, "max_total_tokens": 100, "max_wall_seconds": 3},
            },
            "authorized_by": "unit-test",
            "authorized_at": "2026-01-01T00:00:00Z",
            "expires_at": "2030-01-01T00:00:00Z",
            "authority_evidence_sha256": "a" * 64,
        }
        path = self.execution / "grant.json"
        write_json(path, value)
        return path

    def args(self, run_id: str) -> argparse.Namespace:
        arm, episode = self.arm_episode(run_id)
        return argparse.Namespace(
            experiment_dir=self.experiment,
            run_plan=self.experiment / "pilot-run-plan.json",
            output_dir=self.output,
            run_id=run_id,
            episode_id=episode["episode_id"],
            authorization=self.grant(run_id),
            authority_freeze=self.authority_freeze,
            execution_root=self.execution,
            model="gpt-5.6-sol",
            reasoning_effort="ultra",
            tool_profile=self.experiment / arm["tool_profile"]["path"],
            codex_executable=str(self.fake),
            preregistration_sha256=self.plan["preregistration_sha256"],
            run_plan_sha256=self.plan_hash,
            baseline_source_sha256="b" * 64,
            candidate_source_sha256="c" * 64,
            instrument_manifest_sha256="d" * 64,
            max_total_tokens_per_call=100,
            max_seconds_per_call=3,
            preflight=False,
        )

    def execute(self, run_id: str, mode: str = "success") -> dict:
        original_clean = adapter._clean_environment
        original_popen = adapter.subprocess.Popen

        def clean(profile: dict) -> dict[str, str]:
            value = original_clean(profile)
            value["FAKE_CODEX_MODE"] = mode
            return value

        def popen(command, *args, **kwargs):
            self.spawn_commands.append(list(command))
            kwargs["creationflags"] = 0
            return original_popen([sys.executable, str(self.fake), *command[1:]], *args, **kwargs)

        with mock.patch.object(
            freeze,
            "validate_grant_authority",
            side_effect=lambda grant_path, authority_path, **_: guard.load_grant(grant_path),
        ), mock.patch.object(
            execution_boundary,
            "TRUSTED_LAUNCH_BACKENDS",
            {"test-provider-boundary-v1": self.network_adapter_sha256},
        ), mock.patch.object(
            execution_boundary, "prove_live_boundary"
        ), mock.patch.object(adapter, "_verify_frozen_cli_identity"), mock.patch.object(
            adapter, "_clean_environment", side_effect=clean
        ), mock.patch.object(adapter.subprocess, "Popen", side_effect=popen):
            return adapter.execute(self.args(run_id))

    def test_authority_failure_precedes_profile_environment_ledger_reserve_and_launch(self) -> None:
        args = self.args("PL-N0-P01-v1-E01")
        with (
            mock.patch.object(
                freeze,
                "validate_grant_authority",
                side_effect=freeze.PilotFreezeError("freeze drifted"),
            ) as authority,
            mock.patch.object(adapter, "load_json", side_effect=AssertionError("run plan read")),
            mock.patch.object(adapter, "_load_bound_profile", side_effect=AssertionError("profile read")),
            mock.patch.object(adapter, "_clean_environment", side_effect=AssertionError("CODEX_HOME read")),
            mock.patch.object(adapter.guard, "initialize", side_effect=AssertionError("ledger initialized")) as initialize,
            mock.patch.object(adapter.guard, "reserve", side_effect=AssertionError("reserved")) as reserve,
            mock.patch.object(adapter.subprocess, "Popen", side_effect=AssertionError("launched")) as launch,
        ):
            with self.assertRaisesRegex(adapter.AdapterError, "producer grant authority is invalid"):
                adapter.execute(args)
        authority.assert_called_once_with(
            args.authorization.resolve(),
            args.authority_freeze.resolve(),
            expected_role="producer",
            experiment_dir=args.experiment_dir.resolve(),
        )
        initialize.assert_not_called()
        reserve.assert_not_called()
        launch.assert_not_called()

    def test_normal_call_settles_from_raw_usage_and_request_identity(self) -> None:
        result = self.execute("PL-N0-P01-v1-E01")
        self.assertEqual(result["status"], "settled")
        summary = guard.replay(self.execution)
        self.assertEqual(summary["settled"]["total_tokens"], 30)
        self.assertEqual(summary["in_doubt_attempt_ids"], [])
        receipt = json.loads((self.output / "runs/PL-N0-P01-v1-E01/usage-receipt.json").read_text())
        self.assertEqual(receipt["provider_request_ids"], ["provider-1"])

    def test_trace_binds_the_exact_frozen_presented_deliverable_set(self) -> None:
        run_id = "PL-N0-P01-v1-E01"
        self.execute(run_id)
        root = self.output / "runs" / run_id
        trace = json.loads((root / "trace.json").read_text(encoding="utf-8"))
        trace_source = json.loads((root / "trace-source.json").read_text(encoding="utf-8"))
        case = workspaces.load_pilot_case("N0", self.experiment / "pilot-scenarios.json")
        expected = workspaces.presented_artifact_aggregate(
            self.output / "arms/PL-N0-P01-v1/workspace", case["presented_paths"]
        )
        source_events = trace_source["events"]
        self.assertEqual(trace["events"][: len(source_events)], source_events)
        self.assertEqual(
            [event["seq"] for event in trace["events"]],
            list(range(1, len(trace["events"]) + 1)),
        )
        deliverables = [
            event["payload_sha256"]
            for event in source_events
            if event["kind"] == "deliverable"
        ]
        self.assertEqual(deliverables, [expected])

    def test_missing_frozen_presented_deliverable_does_not_forge_an_event(self) -> None:
        original_run = adapter._run_codex

        def remove_deliverable(*args, **kwargs):
            result = original_run(*args, **kwargs)
            (args[1] / "src/routine.ts").unlink()
            return result

        run_id = "PL-N0-P01-v1-E01"
        with mock.patch.object(adapter, "_run_codex", side_effect=remove_deliverable):
            self.assertEqual(self.execute(run_id)["status"], "settled")
        root = self.output / "runs" / run_id
        for name in ("trace-source.json", "trace.json"):
            document = json.loads((root / name).read_text(encoding="utf-8"))
            self.assertFalse(any(event["kind"] == "deliverable" for event in document["events"]))
        self.assertEqual(guard.replay(self.execution)["settled"]["calls"], 1)

    def test_producer_spawn_is_wrapped_with_launcher_adapter_session_and_role(self) -> None:
        self.execute("PL-N0-P01-v1-E01")
        command = self.spawn_commands[-1]
        self.assertEqual(
            command[:7],
            [
                str(self.network_launcher), str(self.network_launch_adapter),
                "--session", "adapter-fixture-session", "--role", "producer", "--",
            ],
        )
        self.assertEqual(command[7], str(self.fake))
        self.assertEqual(command[8:11], ["--ask-for-approval", "never", "--model"])

    def test_codex_runner_rejects_an_empty_wrapper_before_popen(self) -> None:
        with mock.patch.object(
            adapter.subprocess, "Popen", side_effect=AssertionError("bare Popen")
        ) as launch:
            with self.assertRaisesRegex(
                adapter.AdapterError, "requires a verified network wrapper"
            ):
                adapter._run_codex(
                    str(self.fake), self.base, self.base / "prompt.txt",
                    self.base / "response.json", self.base / "events.jsonl",
                    self.base / "stderr.log", {}, "gpt-5.6-sol", "ultra",
                    {
                        "provider_key": "custom", "display_name": "Zeo",
                        "base_url": "https://example.invalid/v1",
                        "wire_api": "responses", "requires_openai_auth": True,
                    },
                    self.experiment / "completion-claim.schema.json", 3,
                    launch_prefix=[],
                )
        launch.assert_not_called()

    def test_receipt_timestamps_exclude_postflight_validation(self) -> None:
        clock = {"value": None, "run_finished": False, "postflight_delayed": False}
        original_now = adapter._now_text
        original_run = adapter._run_codex
        original_validate = adapter.workspaces.validate_protocol_bundle
        original_settle = guard.settle

        def now_text(value=None):
            if value is not None:
                return original_now(value)
            if clock["value"] is None:
                clock["value"] = datetime.now().astimezone()
            return original_now(clock["value"])

        def timed_run(*args, **kwargs):
            result = original_run(*args, **kwargs)
            clock["value"] += timedelta(seconds=result[3])
            clock["run_finished"] = True
            return result

        def delayed_validation(*args, **kwargs):
            result = original_validate(*args, **kwargs)
            if clock["run_finished"] and not clock["postflight_delayed"]:
                clock["value"] += timedelta(seconds=2)
                clock["postflight_delayed"] = True
            return result

        with (
            mock.patch.object(adapter, "_now_text", side_effect=now_text),
            mock.patch.object(adapter, "_run_codex", side_effect=timed_run),
            mock.patch.object(
                adapter.workspaces,
                "validate_protocol_bundle",
                side_effect=delayed_validation,
            ),
            mock.patch.object(
                adapter.guard,
                "settle",
                side_effect=lambda root, receipt, evidence: original_settle(
                    root,
                    receipt,
                    evidence,
                    now=clock["value"] + timedelta(seconds=1),
                ),
            ),
        ):
            result = self.execute("PL-N0-P01-v1-E01")
        self.assertEqual(result["status"], "settled")
        receipt = json.loads(
            (self.output / "runs/PL-N0-P01-v1-E01/usage-receipt.json").read_text()
        )
        started = datetime.fromisoformat(receipt["started_at"].replace("Z", "+00:00"))
        ended = datetime.fromisoformat(receipt["ended_at"].replace("Z", "+00:00"))
        self.assertAlmostEqual(
            (ended - started).total_seconds(), receipt["usage"]["wall_seconds"], places=5
        )

    def test_missing_or_ambiguous_request_and_usage_remain_in_doubt(self) -> None:
        for mode, error in (
            ("missing-request", "provider request ID"),
            ("ambiguous-request", "provider request ID"),
            ("missing-usage", "usage record"),
        ):
            with self.subTest(mode=mode):
                with self.fresh_case() as (execution, output):
                    with self.assertRaisesRegex(adapter.AdapterError, error):
                        self.execute("PL-N0-P01-v1-E01", mode)
                    self.assertEqual(len(guard.replay(execution)["in_doubt_attempt_ids"]), 1)
                    self.assertFalse((output / "runs/PL-N0-P01-v1-E01/usage-receipt.json").exists())

    def test_timeout_and_nonzero_exit_never_become_controller_interruptions(self) -> None:
        for mode, error in (("timeout", "exceeded"), ("nonzero", "exited 7")):
            with self.subTest(mode=mode):
                with self.fresh_case() as (execution, _):
                    with self.assertRaisesRegex(adapter.AdapterError, error):
                        self.execute("PL-N0-P01-v1-E01", mode)
                    summary = guard.replay(execution)
                    self.assertEqual(len(summary["in_doubt_attempt_ids"]), 1)
                    self.assertEqual(summary["interrupted_attempt_ids"], [])

    def test_s1_controller_kill_writes_manifest_without_receipt_or_trace(self) -> None:
        result = self.execute("PL-S1-P01-v1-E01", "s1")
        self.assertEqual(result["status"], "interrupted")
        root = self.output / "runs/PL-S1-P01-v1-E01"
        self.assertTrue((root / "controller-interruption.json").is_file())
        self.assertTrue((root / "evidence-manifest.json").is_file())
        self.assertFalse((root / "usage-receipt.json").exists())
        self.assertFalse((root / "trace.json").exists())
        manifest = json.loads((root / "controller-interruption.json").read_text())
        evidence = json.loads((root / "evidence-manifest.json").read_text())
        self.assertEqual(manifest["reason"], guard.INTERRUPTION_REASON)
        self.assertNotIn("structured_claim", evidence)
        self.assertEqual(
            {item["role"] for item in evidence["files"]},
            {
                "request", "provider_events", "stderr", "initial_workspace",
                "final_workspace", "workspace_population_seal", "protocol_bundle",
                "controller_interruption",
                "reality_observation", "post_absence_observation",
                "termination_fact",
            },
        )
        self.assertTrue(manifest["wall_seconds_upper_bound"]["seconds"] > 0)
        absence = json.loads((root / "post-absence-observation.json").read_text())
        self.assertTrue(absence["all_absent_after_termination"])
        summary = guard.replay(self.execution)
        self.assertEqual(summary["settled"], {"calls": 0, "total_tokens": 0, "wall_seconds": 0})
        self.assertEqual(summary["charged"], {"calls": 1, "total_tokens": 100, "wall_seconds": 3})
        self.assertEqual(summary["interrupted_call_ids"], ["PL-S1-P01-v1-E01:E01"])

    def test_s1_post_race_does_not_claim_before_post_interruption(self) -> None:
        with self.assertRaisesRegex(
            adapter.AdapterError,
            "exceeded|exited before|did not preserve the reality-before-post boundary",
        ):
            self.execute("PL-S1-P01-v1-E01", "s1-post-race")
        summary = guard.replay(self.execution)
        self.assertEqual(summary["interrupted_attempt_ids"], [])
        self.assertEqual(len(summary["in_doubt_attempt_ids"]), 1)

    def test_guard_rejects_underreported_or_over_limit_interruption_wall_time(self) -> None:
        self.execute("PL-S1-P01-v1-E01", "s1")
        root = self.output / "runs/PL-S1-P01-v1-E01"
        manifest = json.loads((root / "controller-interruption.json").read_text())
        self.assertLessEqual(manifest["wall_seconds_upper_bound"]["seconds"], 3)
        manifest["wall_seconds_upper_bound"]["seconds"] = 4
        write_json(root / "tampered-interruption.json", manifest)
        evidence = json.loads((root / "evidence-manifest.json").read_text())
        for item in evidence["files"]:
            if item["role"] == "controller_interruption":
                item["path"] = "tampered-interruption.json"
                item["sha256"] = guard.sha256_file(root / "tampered-interruption.json")
        evidence["controller_interruption"] = {
            "path": "tampered-interruption.json",
            "sha256": guard.sha256_file(root / "tampered-interruption.json"),
        }
        evidence["files"] = list(evidence["files"])
        evidence["aggregate_sha256"] = guard.sha256_bytes(
            guard.canonical_bytes(evidence["files"])
        )
        write_json(root / "tampered-evidence.json", evidence)
        other_execution = self.base / "other-execution"
        self.execution = other_execution
        # A fresh guard reservation with the same identity rejects the measured over-limit fact.
        grant_path = self.grant("PL-S1-P01-v1-E01")
        guard.initialize(other_execution, grant_path)
        guard.reserve(other_execution, "PL-S1-P01-v1-E01", manifest["attempt_id"], "E01")
        with self.assertRaisesRegex(guard.GuardError, "wall upper bound exceeds"):
            guard.interrupt(
                other_execution,
                root / "tampered-interruption.json",
                root / "tampered-evidence.json",
            )

    def test_evidence_written_before_settlement_can_be_recovered(self) -> None:
        with mock.patch.object(adapter.guard, "settle", side_effect=guard.GuardError("simulated settle interruption")):
            with self.assertRaisesRegex(guard.GuardError, "simulated settle interruption"):
                self.execute("PL-N0-P01-v1-E01")
        root = self.output / "runs/PL-N0-P01-v1-E01"
        self.assertTrue((root / "evidence-manifest.json").is_file())
        self.assertTrue((root / "usage-receipt.json").is_file())
        self.assertFalse((root / "trace.json").exists())
        self.assertEqual(len(guard.replay(self.execution)["in_doubt_attempt_ids"]), 1)
        recovered = guard.settle(
            self.execution, root / "usage-receipt.json", root / "evidence-manifest.json"
        )
        self.assertEqual(recovered["settled_call_ids"], ["PL-N0-P01-v1-E01:E01"])

    def test_settled_workspace_and_protocol_drift_fail_closed(self) -> None:
        self.execute("PL-N0-P01-v1-E01")
        workspace = self.output / "arms/PL-N0-P01-v1/workspace"
        (workspace / "src/routine.ts").write_text("drift\n")
        with self.assertRaisesRegex(adapter.AdapterError, "workspace drifted"):
            self.execute("PL-N0-P01-v1-E01")

        with self.fresh_case():
            self.execute("PL-N0-P01-v1-E01")
            bundle = self.output / "arms/PL-N0-P01-v1/protocol-bundle/SKILL.md"
            bundle.chmod(bundle.stat().st_mode | 0o200)
            bundle.write_text(bundle.read_text(encoding="utf-8") + "\ndrift\n", encoding="utf-8")
            with self.assertRaisesRegex(workspaces.WorkspaceError, "protocol bundle drifted"):
                self.execute("PL-N0-P01-v1-E01")

    def test_staged_injections_run_in_fresh_episode_processes(self) -> None:
        for first, second, injected in (
            ("PL-T3-P01-v1-E01", "PL-T3-P01-v1-E02", "test/cache-integration.test.mjs"),
            ("PL-T5-P01-v2-E01", "PL-T5-P01-v2-E02", "src/payments/resume.ts"),
        ):
            with self.subTest(second=second), self.fresh_case() as (execution, output):
                self.execute(first)
                self.execution = execution.parent / "execution-e2"
                result = self.execute(second)
                self.assertEqual(result["status"], "settled")
                self.assertTrue((output / "runs" / second / "injection-receipt.json").is_file())
                arm_id = second.rsplit("-", 1)[0]
                self.assertTrue((output / "arms" / arm_id / "workspace" / injected).is_file())
                first_command, second_command = self.spawn_commands[-2:]
                for command in (first_command, second_command):
                    codex_tail = command[command.index(str(self.fake)) :]
                    self.assertEqual(codex_tail.count("--ephemeral"), 1)
                    self.assertFalse(
                        {"resume", "--resume", "--session", "--thread", "--conversation-id"}
                        .intersection(codex_tail)
                    )
                second_request = (output / "runs" / second / "request.txt").read_text(encoding="utf-8")
                self.assertNotIn("fake completed", second_request)

    def test_s1_e02_recovers_interrupted_e01_without_duplicate_effect(self) -> None:
        self.execute("PL-S1-P01-v2-E01", "s1")
        self.execution = self.base / "execution-s1-e2"
        result = self.execute("PL-S1-P01-v2-E02", "s1-recover")
        self.assertEqual(result["status"], "settled")
        workspace = self.output / "arms/PL-S1-P01-v2/workspace"
        reality = json.loads((workspace / "reality/account.json").read_text())
        self.assertEqual(reality, {"applied_count": 1, "operation_ids": ["pilot-credit-001"]})
        self.assertIn("no retry", (workspace / "recovery-decision.md").read_text())


if __name__ == "__main__":
    unittest.main()
