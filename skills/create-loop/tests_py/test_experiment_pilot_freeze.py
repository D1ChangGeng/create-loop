from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = ROOT / "skills" / "create-loop"
EXPERIMENTS = SKILL_ROOT / "tests" / "experiments"
sys.path.insert(0, str(EXPERIMENTS))

import pilot_freeze as freeze  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(freeze.canonical_bytes(value))


class PilotFreezeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    @staticmethod
    def records(
        *,
        request_id: str | None = "request-1",
        second_request_id: str | None = None,
        usage: dict[str, int] | None = None,
        second_usage: dict[str, int] | None = None,
    ) -> list[dict]:
        first: dict = {"type": "response.started"}
        if request_id is not None:
            first["provider_request_id"] = request_id
        value = usage or {
            "input_tokens": 20,
            "cached_input_tokens": 5,
            "output_tokens": 10,
            "reasoning_output_tokens": 4,
            "total_tokens": 30,
        }
        result = [first, {"type": "turn.completed", "provider_request_id": request_id, "usage": value}]
        if second_request_id is not None:
            result.append({"type": "response.completed", "provider_request_id": second_request_id})
        if second_usage is not None:
            result.append({"type": "usage", "usage": second_usage})
        return result

    @staticmethod
    def write_jsonl(path: Path, records: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n" for item in records),
            encoding="utf-8",
            newline="\n",
        )

    def static_fixture(self) -> tuple[Path, dict, dict, list[dict]]:
        experiment = self.root / "experiment"
        experiment.mkdir()
        for relative in freeze.PILOT_STATIC_INPUTS:
            path = experiment / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(relative + "\n", encoding="utf-8", newline="\n")
        for protocol in ("v1", "v2"):
            bundle = experiment / "protocol-bundles" / protocol / "bundle-manifest.json"
            bundle.parent.mkdir(parents=True)
            bundle.write_text(protocol + "\n", encoding="utf-8", newline="\n")
        producer_path = experiment / "cli-identities/codex-0.144.1-windows.json"
        write_json(producer_path, {
            "schema_version": "1.0", "id": "codex-0.144.1-windows", "product": "codex-cli",
            "version": "0.144.1", "launcher_sha256": "1" * 64,
            "entrypoint_sha256": "2" * 64, "package_sha256": "3" * 64,
            "native_executable_sha256": "4" * 64,
        })
        producer_binding = {
            "id": "codex-0.144.1-windows",
            "path": "cli-identities/codex-0.144.1-windows.json",
            "sha256": freeze.sha256_file(producer_path),
        }
        reviewer_path = experiment / "cli-identities/codex-0.144.1-linux-x64.json"
        write_json(reviewer_path, {
            "schema_version": "1.0", "id": "codex-0.144.1-linux-x64", "product": "codex-cli",
            "version": "0.144.1", "platform": "linux", "arch": "x86_64",
            "package_tree_sha256": "5" * 64,
            "launcher": {"path": "codex", "sha256": "6" * 64},
            "entrypoint": {"path": "bin/codex.js", "sha256": "7" * 64},
            "package": {"path": "package.json", "sha256": "8" * 64},
            "native_executable": {"path": "vendor/bin/codex", "sha256": "9" * 64},
        })
        reviewer_binding = {
            "id": "codex-0.144.1-linux-x64",
            "path": "cli-identities/codex-0.144.1-linux-x64.json",
            "sha256": freeze.sha256_file(reviewer_path),
        }
        preregistration = {
            "campaign_id": "create-loop-v1-v2-real-task-pilot-2026",
            "baseline": {"aggregate_sha256": "1" * 64},
            "candidate": {"aggregate_sha256": "2" * 64},
            "instrument_manifest": {"path": "instrument-manifest.json"},
            "scenario_manifest": {"path": "pilot-scenarios.json"},
            "evaluator_manifest": {"path": "pilot-evaluator-manifest.json"},
            "execution": {
                "adapter": {"path": "codex_exec_adapter.py"},
                "tool_profile": {"path": "tool-profiles/provider-workspace-no-publish.json"},
            },
            "provider": {"path": "provider-profiles/custom-zeo-responses.json"},
            "cli_identities": {
                "calibration_reuses": "producer",
                "producer": {
                    "status": "frozen", "platform": "windows", "arch": "x86_64",
                    "version": "0.144.1", "binding": producer_binding, "reason": None,
                },
                "reviewer": {
                    "status": "frozen", "platform": "linux", "arch": "x86_64",
                    "version": "0.144.1", "binding": reviewer_binding, "reason": None,
                },
            },
        }
        plan = {"campaign_id": preregistration["campaign_id"]}
        entries = freeze._static_entries(experiment, preregistration)
        return experiment, preregistration, plan, entries

    def test_role_cli_bindings_and_unresolved_reviewer_fail_closed(self) -> None:
        experiment, preregistration, _, _ = self.static_fixture()
        producer = preregistration["cli_identities"]["producer"]["binding"]
        reviewer = preregistration["cli_identities"]["reviewer"]["binding"]
        identities = {
            producer["path"]: {
                "schema_version": "1.0", "id": producer["id"], "product": "codex-cli",
                "version": "0.144.1", "launcher_sha256": "1" * 64,
                "entrypoint_sha256": "2" * 64, "package_sha256": "3" * 64,
                "native_executable_sha256": "4" * 64,
            },
            reviewer["path"]: {
                "schema_version": "1.0", "id": reviewer["id"], "product": "codex-cli",
                "version": "0.144.1", "platform": "linux", "arch": "x86_64",
                "package_tree_sha256": "5" * 64,
                "launcher": {"path": "codex", "sha256": "6" * 64},
                "entrypoint": {"path": "bin/codex.js", "sha256": "7" * 64},
                "package": {"path": "package.json", "sha256": "8" * 64},
                "native_executable": {"path": "vendor/bin/codex", "sha256": "9" * 64},
            },
        }
        for relative, value in identities.items():
            path = experiment / relative
            write_json(path, value)
            role = "producer" if "windows" in relative else "reviewer"
            preregistration["cli_identities"][role]["binding"]["sha256"] = freeze.sha256_file(path)
        bindings = freeze._validate_cli_identities(experiment, preregistration)
        self.assertEqual(bindings["producer_cli"], {key: producer[key] for key in ("path", "sha256")})
        self.assertEqual(bindings["reviewer_cli"], {key: reviewer[key] for key in ("path", "sha256")})
        blocked = copy.deepcopy(preregistration)
        blocked["cli_identities"]["reviewer"] = {
            "status": "unresolved", "platform": "linux", "arch": "x86_64",
            "version": "0.144.1", "binding": None, "reason": "payload unavailable",
        }
        with self.assertRaisesRegex(freeze.PilotFreezeError, "reviewer CLI identity is unresolved"):
            freeze._validate_cli_identities(experiment, blocked)

    def pre_freeze(self, experiment: Path, preregistration: dict, entries: list[dict]) -> dict:
        bindings = freeze._expected_bindings(experiment, preregistration)
        return {
            "schema_version": "1.0",
            "kind": "pilot-authority-freeze",
            "experiment_id": preregistration["campaign_id"],
            "phase": "pre-calibration",
            "algorithm": "sha256-pilot-authority-freeze-v1",
            "created_at": "2026-08-05T00:00:00Z",
            "source_snapshots": ["1" * 64, "2" * 64],
            "bindings": bindings,
            "files": entries,
            "aggregate_sha256": freeze._aggregate(entries),
        }

    def grant(self, role: str, authority_sha256: str) -> dict:
        calls = (
            [freeze.CALIBRATION_CALL]
            if role == "calibration"
            else [{"run_id": "PL-T2-P01-v2-E01" if role == "producer" else "PL-T2-P01-review", "episode_id": "E01" if role == "producer" else "review"}]
        )
        limits = freeze.CALIBRATION_LIMITS if role == "calibration" else {
            "per_call": {"max_total_tokens": 60_000, "max_wall_seconds": 900},
            "total": {"max_calls": 1, "max_total_tokens": 60_000, "max_wall_seconds": 900},
        }
        return {
            "schema_version": "2.0",
            "authorization_id": f"authorization-{role}",
            "execution_id": f"execution-{role}",
            "execution_root_sha256": "3" * 64,
            "experiment_id": "create-loop-v1-v2-real-task-pilot-2026",
            "preregistration_sha256": "4" * 64,
            "run_plan_sha256": "5" * 64,
            "role": role,
            "adapter": {"id": "codex-exec", "version": "2.0", "sha256": "6" * 64},
            "cli_identity": {"id": "codex", "path": "cli.json", "sha256": "7" * 64},
            "provider_profile": {"id": "provider", "path": "provider.json", "sha256": "8" * 64},
            "model": "gpt-5.6-sol",
            "reasoning_effort": "ultra",
            "tool_profile": {"id": "tool", "path": "tool.json", "sha256": "9" * 64},
            "authorized_calls": calls,
            "limits": limits,
            "authorized_by": "user",
            "authorized_at": "2026-08-05T00:00:00Z",
            "expires_at": "2026-08-06T00:00:00Z",
            "authority_evidence_sha256": authority_sha256,
        }

    def calibration_fixture(self) -> dict[str, Path | dict]:
        output = self.root / "output"
        output.mkdir()
        pre_path = output / "pre-freeze.json"
        pre_path.write_text("pre\n", encoding="utf-8", newline="\n")
        execution_root = output / "execution"
        execution_root.mkdir()
        grant_path = execution_root / "grant.json"
        raw_path = output / "call" / "codex-events.jsonl"
        receipt_path = output / "call" / "usage-receipt.json"
        evidence_path = output / "call" / "evidence-manifest.json"
        response_path = output / "call" / "final-response.json"
        request_path = output / "call" / "request.txt"
        claim_path = output / "call" / "structured-claim.json"
        initial_path = output / "call" / "workspace-initial-manifest.json"
        final_path = output / "call" / "workspace-final-manifest.json"
        request_path.parent.mkdir(parents=True)
        request_path.write_text("calibrate\n", encoding="utf-8", newline="\n")
        response = {"completion_claimed": True, "summary": "ok", "deliverables": [], "blockers": [], "risks": []}
        for path in (response_path, claim_path):
            write_json(path, response)
        write_json(initial_path, {"fixture": "initial"})
        write_json(final_path, {"fixture": "final"})
        records = self.records()
        self.write_jsonl(raw_path, records)
        grant = self.grant("calibration", freeze.sha256_file(pre_path))
        grant["execution_root_sha256"] = freeze.guard._root_path_sha256(execution_root)
        write_json(grant_path, grant)
        files = []
        for role, path in (
            ("request", request_path),
            ("provider_events", raw_path),
            ("provider_response", response_path),
            ("structured_claim", claim_path),
            ("initial_workspace", initial_path),
            ("final_workspace", final_path),
        ):
            files.append({"role": role, "path": path.relative_to(evidence_path.parent).as_posix(), "sha256": freeze.sha256_file(path)})
        evidence = {
            "schema_version": "1.0", "run_id": "pilot-calibration", "episode_id": "calibration",
            "attempt_id": "attempt-1", "role": "calibration",
            "initial_workspace_manifest": {"path": initial_path.name, "sha256": freeze.sha256_file(initial_path)},
            "final_workspace_manifest": {"path": final_path.name, "sha256": freeze.sha256_file(final_path)},
            "structured_claim": {"path": claim_path.name, "sha256": freeze.sha256_file(claim_path)},
            "files": files, "aggregate_sha256": freeze._aggregate(files),
        }
        write_json(evidence_path, evidence)
        usage = records[1]["usage"]
        receipt = {
            "schema_version": "2.0", "receipt_id": "receipt-1",
            "authorization_id": grant["authorization_id"], "execution_id": grant["execution_id"],
            "run_id": "pilot-calibration", "episode_id": "calibration", "attempt_id": "attempt-1", "role": "calibration",
            "adapter": grant["adapter"], "cli_identity": grant["cli_identity"], "provider_profile": grant["provider_profile"],
            "model": grant["model"], "reasoning_effort": grant["reasoning_effort"], "tool_profile": grant["tool_profile"],
            "source_class": "provider-response", "provider_request_ids": ["request-1"],
            "request_sha256": freeze.sha256_file(request_path), "response_sha256": freeze.sha256_file(response_path),
            "usage": {**usage, "wall_seconds": 1.0},
            "started_at": "2026-08-05T00:00:00Z", "ended_at": "2026-08-05T00:00:01Z",
            "raw_evidence_sha256": freeze.sha256_file(raw_path), "evidence_manifest_sha256": freeze.sha256_file(evidence_path),
        }
        write_json(receipt_path, receipt)
        return {
            "output": output, "execution": execution_root, "pre": pre_path,
            "grant": grant_path, "raw": raw_path,
            "receipt": receipt_path, "evidence": evidence_path, "response": response_path,
            "grant_value": grant, "usage": usage,
        }

    def test_pre_freeze_exact_set_and_drift_detection_are_read_only(self) -> None:
        experiment, preregistration, plan, entries = self.static_fixture()
        expected = self.pre_freeze(experiment, preregistration, entries)
        freeze_path = self.root / "authority" / "pre.json"
        write_json(freeze_path, expected)
        before = {path: path.read_bytes() for path in experiment.rglob("*") if path.is_file()}
        with (
            mock.patch.object(
                freeze, "_validate_static_authority",
                return_value=(preregistration, plan, entries),
            ),
            mock.patch.object(
                freeze.execution_boundary, "require_execution_ready",
                return_value={"fixture": "ready"},
            ) as readiness,
        ):
            self.assertEqual(
                freeze.validate_pre_calibration_freeze(freeze_path, experiment_dir=experiment),
                expected,
            )
            (experiment / "pilot_runners.py").write_text("drift\n", encoding="utf-8", newline="\n")
            drifted = freeze._static_entries(experiment, preregistration)
            with mock.patch.object(
                freeze, "_validate_static_authority",
                return_value=(preregistration, plan, drifted),
            ):
                with self.assertRaisesRegex(freeze.PilotFreezeError, "exact static input set"):
                    freeze.validate_pre_calibration_freeze(freeze_path, experiment_dir=experiment)
        self.assertEqual(readiness.call_count, 2)
        self.assertTrue(
            all("required_role" not in item.kwargs for item in readiness.call_args_list)
        )
        for path, data in before.items():
            if path.name != "pilot_runners.py":
                self.assertEqual(path.read_bytes(), data)

    def test_static_inputs_extend_the_canonical_instrument_set(self) -> None:
        for path, role in freeze.snapshots.EXPERIMENT_INSTRUMENT_INPUTS.items():
            self.assertEqual(freeze.PILOT_STATIC_INPUTS[path], role)
        for path in (
            "evaluation.py", "pilot_campaign.py", "reviewer_isolation.py",
            "reviewer-isolation-manifest.schema.json",
        ):
            self.assertIn(path, freeze.PILOT_STATIC_INPUTS)
        self.assertEqual(
            set(freeze.PILOT_STATIC_INPUTS) - set(freeze.snapshots.EXPERIMENT_INSTRUMENT_INPUTS),
            set(freeze.PILOT_FREEZE_DOCUMENTS),
        )

    def test_repository_preregistration_describes_but_cannot_freeze_unresolved_reviewer(self) -> None:
        preregistration = json.loads(
            (EXPERIMENTS / "pilot-preregistration.json").read_text(encoding="utf-8")
        )
        reviewer = preregistration["cli_identities"]["reviewer"]
        self.assertEqual(reviewer["status"], "unresolved")
        self.assertIsNone(reviewer["binding"])
        with self.assertRaisesRegex(freeze.PilotFreezeError, "reviewer CLI identity is unresolved"):
            freeze._validate_cli_identities(EXPERIMENTS, preregistration)

    def test_raw_replay_fixes_request_and_usage_event_json_pointers(self) -> None:
        raw = self.root / "events.jsonl"
        self.write_jsonl(raw, self.records())
        records, usage, request_id = freeze._usage_from_raw(raw)
        self.assertEqual(request_id, "request-1")
        self.assertEqual(freeze._usage_observation(records, usage), {"event_type": "turn.completed", "json_pointer": "/1/usage"})
        self.assertEqual(
            freeze._provider_observations(records, request_id),
            [
                {"event_type": "response.started", "json_pointer": "/0/provider_request_id", "field": "provider_request_id"},
                {"event_type": "turn.completed", "json_pointer": "/1/provider_request_id", "field": "provider_request_id"},
            ],
        )

    def test_raw_replay_rejects_missing_or_ambiguous_identity_and_usage(self) -> None:
        cases = {
            "missing-request": self.records(request_id=None),
            "ambiguous-request": self.records(second_request_id="request-2"),
            "missing-usage": [{"type": "response.started", "provider_request_id": "request-1"}],
            "ambiguous-usage": self.records(second_usage={
                "input_tokens": 21, "cached_input_tokens": 5, "output_tokens": 10,
                "reasoning_output_tokens": 4, "total_tokens": 31,
            }),
        }
        for name, records in cases.items():
            with self.subTest(name=name):
                raw = self.root / f"{name}.jsonl"
                self.write_jsonl(raw, records)
                with self.assertRaisesRegex(freeze.PilotFreezeError, "raw JSONL"):
                    freeze._usage_from_raw(raw)

    def test_calibration_result_builder_is_raw_derived(self) -> None:
        fixture = self.calibration_fixture()
        result = freeze.build_calibration_result(
            experiment_id="create-loop-v1-v2-real-task-pilot-2026",
            pre_freeze_path=fixture["pre"], execution_root=fixture["execution"],
            raw_provider_events_path=fixture["raw"], usage_receipt_path=fixture["receipt"],
            evidence_manifest_path=fixture["evidence"], response_path=fixture["response"],
            authority_root=fixture["output"], generated_at="2026-08-05T00:00:02Z",
        )
        self.assertEqual(result["usage"]["value"], fixture["usage"])
        self.assertEqual(result["usage"]["observation"]["json_pointer"], "/1/usage")
        self.assertEqual(result["provider_request_ids"], ["request-1"])
        self.assertNotIn("grant_sha256", result)

    def test_calibration_result_reconciliation_rejects_receipt_or_pre_freeze_drift(self) -> None:
        fixture = self.calibration_fixture()
        result = freeze.build_calibration_result(
            experiment_id="create-loop-v1-v2-real-task-pilot-2026",
            pre_freeze_path=fixture["pre"], execution_root=fixture["execution"],
            raw_provider_events_path=fixture["raw"], usage_receipt_path=fixture["receipt"],
            evidence_manifest_path=fixture["evidence"], response_path=fixture["response"],
            authority_root=fixture["output"], generated_at="2026-08-05T00:00:02Z",
        )
        result_path = fixture["output"] / "pilot-calibration-result.json"
        write_json(result_path, result)
        with mock.patch.object(freeze, "validate_pre_calibration_freeze", return_value={"experiment_id": result["experiment_id"]}):
            self.assertEqual(
                freeze.validate_calibration_result(
                    result_path, pre_freeze_path=fixture["pre"],
                    authority_root=fixture["output"], experiment_dir=self.root,
                ),
                result,
            )
            receipt = json.loads(fixture["receipt"].read_text(encoding="utf-8"))
            receipt["usage"]["input_tokens"] += 1
            write_json(fixture["receipt"], receipt)
            result["usage_receipt"]["sha256"] = freeze.sha256_file(fixture["receipt"])
            write_json(result_path, result)
            with self.assertRaisesRegex(freeze.PilotFreezeError, "receipt disagrees"):
                freeze.validate_calibration_result(
                    result_path, pre_freeze_path=fixture["pre"],
                    authority_root=fixture["output"], experiment_dir=self.root,
                )

    def test_calibration_result_requires_execution_root_canonical_grant(self) -> None:
        fixture = self.calibration_fixture()
        copied_grant = fixture["output"] / "copied-grant.json"
        shutil.copyfile(fixture["grant"], copied_grant)
        with self.assertRaises(TypeError):
            freeze.build_calibration_result(
                experiment_id="create-loop-v1-v2-real-task-pilot-2026",
                pre_freeze_path=fixture["pre"], grant_path=copied_grant,
                raw_provider_events_path=fixture["raw"], usage_receipt_path=fixture["receipt"],
                evidence_manifest_path=fixture["evidence"], response_path=fixture["response"],
                authority_root=fixture["output"], generated_at="2026-08-05T00:00:02Z",
            )
        result = freeze.build_calibration_result(
            experiment_id="create-loop-v1-v2-real-task-pilot-2026",
            pre_freeze_path=fixture["pre"], execution_root=fixture["execution"],
            raw_provider_events_path=fixture["raw"], usage_receipt_path=fixture["receipt"],
            evidence_manifest_path=fixture["evidence"], response_path=fixture["response"],
            authority_root=fixture["output"], generated_at="2026-08-05T00:00:02Z",
        )
        self.assertEqual(result["grant"]["path"], "execution/grant.json")
        result["grant"] = freeze._binding(copied_grant, fixture["output"])
        result_path = fixture["output"] / "pilot-calibration-result.json"
        write_json(result_path, result)
        with mock.patch.object(
            freeze, "validate_pre_calibration_freeze",
            return_value={"experiment_id": result["experiment_id"]},
        ):
            with self.assertRaisesRegex(freeze.PilotFreezeError, "canonical grant.json"):
                freeze.validate_calibration_result(
                    result_path, pre_freeze_path=fixture["pre"],
                    authority_root=fixture["output"], experiment_dir=self.root,
                )

    def test_final_freeze_uses_its_directory_as_stable_authority_root(self) -> None:
        authority = self.root / "authority"
        authority.mkdir()
        pre = authority / "pre.json"
        calibration = authority / "results" / "pilot-calibration-result.json"
        calibration.parent.mkdir()
        write_json(pre, {"fixture": "pre"})
        write_json(calibration, {"fixture": "calibration"})
        value = {
            "binding_root": "experiment-authority-root",
            "pre_calibration_freeze": freeze._binding(pre, authority),
            "calibration_result": freeze._binding(calibration, authority),
        }
        self.assertEqual(value["pre_calibration_freeze"]["path"], "pre.json")
        self.assertEqual(
            value["calibration_result"]["path"],
            "results/pilot-calibration-result.json",
        )
        moved_result = authority / "other" / calibration.name
        moved_result.parent.mkdir()
        shutil.copyfile(calibration, moved_result)
        calibration.unlink()
        with self.assertRaisesRegex(freeze.PilotFreezeError, "must be a regular"):
            freeze._load_binding(
                authority, value["calibration_result"], "final freeze calibration result"
            )

    def test_final_freeze_binds_calibration_and_detects_static_drift(self) -> None:
        experiment, preregistration, plan, entries = self.static_fixture()
        pre = self.pre_freeze(experiment, preregistration, entries)
        authority = self.root / "authority"
        authority.mkdir()
        pre_path = authority / "pre.json"
        calibration_path = authority / "pilot-calibration-result.json"
        write_json(pre_path, pre)
        write_json(calibration_path, {"fixture": "calibration"})
        artifact = authority / "artifact.json"
        write_json(artifact, {"fixture": "artifact"})
        artifacts = {
            role: artifact if role != "calibration_result" else calibration_path
            for role in ("calibration_result", "grant", "raw_provider_events", "usage_receipt", "evidence_manifest", "response")
        }
        with (
            mock.patch.object(freeze, "validate_pre_calibration_freeze", return_value=pre),
            mock.patch.object(freeze, "validate_calibration_result", return_value={"fixture": "calibration"}),
            mock.patch.object(freeze, "_validate_static_authority", return_value=(preregistration, plan, entries)),
            mock.patch.object(freeze, "_calibration_artifact_paths", return_value=artifacts),
            mock.patch.object(
                freeze.execution_boundary, "require_execution_ready",
                return_value={"fixture": "ready"},
            ) as readiness,
        ):
            final = freeze.build_final_freeze(
                experiment_dir=experiment, authority_root=authority,
                pre_freeze_path=pre_path,
                calibration_result_path=calibration_path, created_at="2026-08-05T00:00:03Z",
            )
        self.assertEqual(final["pre_calibration_freeze"]["sha256"], freeze.sha256_file(pre_path))
        self.assertEqual(final["calibration_result"]["sha256"], freeze.sha256_file(calibration_path))
        self.assertEqual({item["role"] for item in final["calibration_artifacts"]}, set(artifacts))
        readiness.assert_called_once()
        self.assertNotIn("required_role", readiness.call_args.kwargs)

    def test_grant_roles_bind_only_their_authorized_freeze_phase(self) -> None:
        # The production grant gate reads the preregistration only after the
        # canonical grant/root/freeze checks.  This fixture does not exercise
        # preregistration semantics, but still supplies a regular JSON file so
        # the readiness boundary remains an explicit, separately patched seam.
        write_json(self.root / "pilot-preregistration.json", {})
        pre = self.root / "pre.json"
        final = self.root / "final.json"
        pre.write_text("pre\n", encoding="utf-8", newline="\n")
        final.write_text("final\n", encoding="utf-8", newline="\n")
        grant_paths: dict[str, Path] = {}
        for role, authority in (
            ("calibration", pre), ("producer", final), ("reviewer", final),
        ):
            execution_root = self.root / role
            grant = self.grant(role, freeze.sha256_file(authority))
            grant["execution_root_sha256"] = freeze.guard._root_path_sha256(execution_root)
            grant_paths[role] = execution_root / "grant.json"
            write_json(grant_paths[role], grant)
        calibration = grant_paths["calibration"]
        producer = grant_paths["producer"]
        reviewer = grant_paths["reviewer"]
        with (
            mock.patch.object(freeze, "validate_pre_calibration_freeze", return_value={"phase": "pre-calibration"}),
            mock.patch.object(freeze, "validate_final_freeze", return_value={"phase": "final-pilot"}),
            mock.patch.object(
                freeze.execution_boundary, "require_execution_ready",
                return_value={"fixture": "ready"},
            ) as readiness,
        ):
            freeze.validate_grant_authority(calibration, pre, expected_role="calibration", experiment_dir=self.root)
            freeze.validate_grant_authority(producer, final, expected_role="producer", experiment_dir=self.root)
            freeze.validate_grant_authority(reviewer, final, expected_role="reviewer", experiment_dir=self.root)
            with self.assertRaisesRegex(freeze.PilotFreezeError, "hash drifted"):
                freeze.validate_grant_authority(calibration, final, expected_role="calibration", experiment_dir=self.root)
            with self.assertRaisesRegex(freeze.PilotFreezeError, "hash drifted"):
                freeze.validate_grant_authority(producer, pre, expected_role="producer", experiment_dir=self.root)
            self.assertEqual(readiness.call_count, 3)
            self.assertTrue(
                all("required_role" not in item.kwargs for item in readiness.call_args_list)
            )

        copied = self.root / "copied-producer-grant.json"
        copied.write_bytes(producer.read_bytes())
        with self.assertRaisesRegex(freeze.PilotFreezeError, "canonical execution-root grant.json"):
            freeze.validate_grant_authority(
                copied, final, expected_role="producer", experiment_dir=self.root,
            )
        wrong_root = self.root / "wrong-root" / "grant.json"
        wrong_root.parent.mkdir()
        wrong_root.write_bytes(producer.read_bytes())
        with self.assertRaisesRegex(freeze.PilotFreezeError, "another execution root"):
            freeze.validate_grant_authority(
                wrong_root, final, expected_role="producer", experiment_dir=self.root,
            )


if __name__ == "__main__":
    unittest.main()
