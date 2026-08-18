from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = SKILL_ROOT / "tests" / "experiments"
sys.path.insert(0, str(EXPERIMENTS))

import evaluation  # noqa: E402
import execution_guard as guard  # noqa: E402
import pilot_freeze  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(evaluation.canonical_bytes(value))


def reviewer_isolation_manifest() -> tuple[dict, dict]:
    delivered = [{"path": "context/task.md", "sha256": "5" * 64, "size": 1}]
    workspace_sha256 = evaluation.sha256_bytes(evaluation.canonical_bytes(delivered))
    hidden = ["/mnt", "/root", "/init", "/run", "/tmp/hidden-sentinel"]
    readable = list(evaluation.PILOT_REVIEW_READABLE_PATHS)
    manifest = {
        "schema_version": "1.0",
        "isolation_id": "reviewer-test",
        "backend": "wsl2-bubblewrap",
        "distribution": "Ubuntu",
        "network_namespace": "authenticated-provider-only-launcher",
        "namespace_flags": list(evaluation.PILOT_REVIEW_NAMESPACE_FLAGS),
        "workspace": {"sandbox_path": "/workspace", "mode": "read-only", "source_sha256": workspace_sha256},
        "cli_identity": {
            "id": "codex-0.144.1-linux-test",
            "version": "0.144.1",
            "platform": "linux",
            "arch": "x86_64",
            "identity_sha256": "1" * 64,
            "package_tree_sha256": "2" * 64,
            "launcher": {"path": "codex", "sha256": "3" * 64},
            "entrypoint": {"path": "bin/codex.js", "sha256": "4" * 64},
            "package": {"path": "package.json", "sha256": "5" * 64},
            "native_executable": {"path": "vendor/x86_64-unknown-linux-musl/codex", "sha256": "6" * 64},
        },
        "codex_package": {"sandbox_path": "/opt/codex", "mode": "read-only", "source_sha256": "2" * 64},
        "codex_home": {"sandbox_path": "/home/reviewer/.codex", "mode": "read-only", "source_sha256": "3" * 64},
        "runtime_roots": [
            {
                "sandbox_path": path,
                "mode": "read-only",
                "source_path_sha256": evaluation.sha256_bytes(path.encode("utf-8")),
            }
            for path in evaluation.PILOT_REVIEW_RUNTIME_ROOTS
        ],
        "hidden_host_roots": hidden,
        "delivered_files": delivered,
        "access_probes": [
            *({"path": path, "expected": "readable", "observed": "readable"} for path in readable),
            *({"path": path, "expected": "hidden", "observed": "hidden"} for path in hidden),
        ],
        "mount_observations": [
            {"path": path, "mode": "read-only"}
            for path in sorted({*evaluation.PILOT_REVIEW_CORE_MOUNTS, *evaluation.PILOT_REVIEW_RUNTIME_ROOTS})
        ],
        "environment": dict(evaluation.PILOT_REVIEW_ENVIRONMENT),
        "command_sha256": "6" * 64,
        "created_at": "2026-08-05T00:00:00Z",
    }
    manifest["aggregate_sha256"] = evaluation.sha256_bytes(evaluation.canonical_bytes(manifest))
    return manifest, {"files": delivered, "aggregate_sha256": workspace_sha256}


def reseal_isolation_manifest(value: dict) -> None:
    core = {key: item for key, item in value.items() if key != "aggregate_sha256"}
    value["aggregate_sha256"] = evaluation.sha256_bytes(evaluation.canonical_bytes(core))


AUTHORITY_NOW = datetime(2026, 8, 5, 12, tzinfo=timezone.utc)


def build_guard_authority(campaign_root: Path, role: str, label: str) -> tuple[Path, dict]:
    execution_root = campaign_root / label / f"{role}-execution"
    grant_input = campaign_root / label / f"{role}-grant-input.json"
    calls = {
        "calibration": [{"run_id": "pilot-calibration", "episode_id": "calibration"}],
        "producer": [{"run_id": "PL-N0-P01-v1-E01", "episode_id": "E01"}],
        "reviewer": [{"run_id": "PL-T2-P01-review", "episode_id": "review"}],
    }[role]
    grant = {
        "schema_version": "2.0",
        "authorization_id": f"authorization-{role}-{label}",
        "execution_id": f"execution-{role}-{label}",
        "execution_root_sha256": guard._root_path_sha256(execution_root),
        "experiment_id": "create-loop-v1-v2-real-task-pilot-2026",
        "preregistration_sha256": "a" * 64,
        "run_plan_sha256": "b" * 64,
        "role": role,
        "adapter": {"id": "fake", "version": "2", "sha256": "c" * 64},
        "cli_identity": {
            "id": "codex-test",
            "path": "cli-identities/codex-test.json",
            "sha256": "d" * 64,
        },
        "provider_profile": {
            "id": "provider-test",
            "path": "provider-profiles/provider-test.json",
            "sha256": "e" * 64,
        },
        "model": "gpt-test",
        "reasoning_effort": "ultra",
        "tool_profile": {
            "id": "provider-workspace-no-publish",
            "path": "tool-profiles/provider-workspace-no-publish.json",
            "sha256": "f" * 64,
        },
        "authorized_calls": calls,
        "limits": {
            "per_call": {"max_total_tokens": 100, "max_wall_seconds": 60},
            "total": {"max_calls": 1, "max_total_tokens": 100, "max_wall_seconds": 60},
        },
        "authorized_by": "unit-test",
        "authorized_at": "2026-08-05T00:00:00Z",
        "expires_at": "2026-08-06T00:00:00Z",
        "authority_evidence_sha256": "1" * 64,
    }
    write_json(grant_input, grant)
    guard.initialize(execution_root, grant_input, now=AUTHORITY_NOW)

    def binding(path: Path) -> dict[str, str]:
        return {
            "path": path.relative_to(campaign_root).as_posix(),
            "sha256": evaluation.sha256_file(path),
        }

    authority = {
        "root": {"path": execution_root.relative_to(campaign_root).as_posix()},
        "grant": binding(execution_root / "grant.json"),
        "ledger_anchor": binding(execution_root / "ledger-anchor.json"),
        "spend_summary": binding(execution_root / "spend-summary.json"),
    }
    return execution_root, authority


class PilotEvaluationUnitTests(unittest.TestCase):
    def test_pilot_authority_requires_complete_guard_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            execution_root, authority = build_guard_authority(root, "producer", "control")
            loaded = evaluation._pilot_load_authority(root, authority, "producer")
            self.assertEqual(loaded["root"], execution_root.resolve())
            self.assertEqual(loaded["summary"]["ledger_last_seq"], 1)

        mutations = {
            "ledger": lambda execution_root: sorted((execution_root / "ledger").glob("*.json"))[0].write_bytes(
                sorted((execution_root / "ledger").glob("*.json"))[0].read_bytes() + b" "
            ),
            "receipt": lambda execution_root: (execution_root / "receipts" / "unexpected.txt").write_text(
                "drift\n", encoding="utf-8", newline="\n"
            ),
            "evidence": lambda execution_root: (execution_root / "evidence" / "unexpected.txt").write_text(
                "drift\n", encoding="utf-8", newline="\n"
            ),
            "interruption": lambda execution_root: (
                execution_root / "interruptions" / "unexpected.txt"
            ).write_text("drift\n", encoding="utf-8", newline="\n"),
        }
        for label, mutate in mutations.items():
            with self.subTest(store=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                execution_root, authority = build_guard_authority(root, "producer", label)
                mutate(execution_root)
                with self.assertRaisesRegex(
                    evaluation.EvaluationError, "authority replay failed|ledger tail|unexpected entries"
                ):
                    evaluation._pilot_load_authority(root, authority, "producer")

    def test_pilot_authority_rejects_consistently_resealed_summary_and_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            execution_root, authority = build_guard_authority(root, "reviewer", "forged")
            summary_path = execution_root / "spend-summary.json"
            anchor_path = execution_root / "ledger-anchor.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
            summary["root_id"] = "root-forged"
            anchor["root_id"] = "root-forged"
            write_json(summary_path, summary)
            write_json(anchor_path, anchor)
            authority["spend_summary"]["sha256"] = evaluation.sha256_file(summary_path)
            authority["ledger_anchor"]["sha256"] = evaluation.sha256_file(anchor_path)

            with self.assertRaisesRegex(
                evaluation.EvaluationError, "authority replay failed|replayed spend summary drifted"
            ):
                evaluation._pilot_load_authority(root, authority, "reviewer")

    def test_pilot_authority_requires_canonical_summary_and_anchor_bytes(self) -> None:
        for key, filename in (
            ("spend_summary", "spend-summary.json"),
            ("ledger_anchor", "ledger-anchor.json"),
        ):
            with self.subTest(authority_file=key), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                execution_root, authority = build_guard_authority(root, "producer", key)
                path = execution_root / filename
                value = json.loads(path.read_text(encoding="utf-8"))
                path.write_text(
                    json.dumps(value, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
                authority[key]["sha256"] = evaluation.sha256_file(path)

                with self.assertRaisesRegex(
                    evaluation.EvaluationError, "is not canonical JSON"
                ):
                    evaluation._pilot_load_authority(root, authority, "producer")

    def test_pilot_authority_rechecks_manifest_bindings_inside_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            execution_root, authority = build_guard_authority(root, "producer", "race")
            original = evaluation.sha256_file
            mutated = False

            def mutate_after_binding_hash(path: Path) -> str:
                nonlocal mutated
                digest = original(path)
                if path.resolve() == (execution_root / "spend-summary.json").resolve() and not mutated:
                    mutated = True
                    anchor = execution_root / "ledger-anchor.json"
                    anchor.write_bytes(anchor.read_bytes() + b" ")
                return digest

            with (
                mock.patch.object(
                    evaluation, "sha256_file", side_effect=mutate_after_binding_hash
                ),
                self.assertRaisesRegex(
                    evaluation.EvaluationError,
                    "authority replay failed|snapshot binding hash drifted|is not canonical JSON",
                ),
            ):
                evaluation._pilot_load_authority(root, authority, "producer")

            self.assertTrue(mutated)

    def test_pilot_final_authority_recheck_is_one_locked_multi_root_cut(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            authorities = []
            for index in range(3):
                _, binding = build_guard_authority(
                    root, "producer", f"multi-{index}"
                )
                authorities.append(
                    evaluation._pilot_load_authority(root, binding, "producer")
                )

            with mock.patch.object(
                guard, "replay_snapshots", wraps=guard.replay_snapshots
            ) as replay_snapshots:
                evaluation._pilot_recheck_authorities(authorities)

            replay_snapshots.assert_called_once()
            self.assertEqual(
                replay_snapshots.call_args.args[0],
                [authority["root"] for authority in authorities],
            )

    def test_pilot_authority_rejects_future_spend_summary_time(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            execution_root, authority = build_guard_authority(root, "producer", "future")
            summary_path = execution_root / "spend-summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["generated_at"] = guard._now_text(
                datetime.now(timezone.utc)
                + timedelta(seconds=guard.MAX_REPLAY_CLOCK_SKEW_SECONDS + 60)
            )
            write_json(summary_path, summary)
            authority["spend_summary"]["sha256"] = evaluation.sha256_file(summary_path)

            with self.assertRaisesRegex(
                evaluation.EvaluationError,
                "authority replay failed: replay time is unreasonably far in the future",
            ):
                evaluation._pilot_load_authority(root, authority, "producer")

    def test_pilot_authority_generated_at_cannot_select_replay_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            execution_root, authority = build_guard_authority(root, "producer", "control-time")
            summary_path = execution_root / "spend-summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["generated_at"] = guard._now_text(datetime.now(timezone.utc))
            write_json(summary_path, summary)
            authority["spend_summary"]["sha256"] = evaluation.sha256_file(summary_path)

            with mock.patch.object(
                guard, "replay_snapshot", wraps=guard.replay_snapshot
            ) as replay_snapshot:
                loaded = evaluation._pilot_load_authority(root, authority, "producer")

            self.assertEqual(loaded["summary"]["generated_at"], summary["generated_at"])
            replay_snapshot.assert_called_once_with(
                execution_root.resolve(), expected_files=loaded["snapshot_bindings"]
            )

    def test_calibration_authority_reuses_freeze_reconciliation_and_its_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            authority_root = root / "frozen-authority"
            execution_root = authority_root / "calibration-execution"
            execution_root.mkdir(parents=True)
            final_freeze_path = authority_root / "final-freeze.json"
            pre_freeze_path = authority_root / "pre-freeze.json"
            result_path = authority_root / "results" / "pilot-calibration-result.json"
            receipt_path = authority_root / "results" / "usage-receipt.json"
            grant_path = execution_root / "grant.json"
            for path, value in (
                (pre_freeze_path, {"phase": "pre-calibration"}),
                (result_path, {"experiment_id": "pilot", "usage": {"value": {}}}),
                (final_freeze_path, {
                    "experiment_id": "pilot",
                    "pre_calibration_freeze": {"path": "pre-freeze.json", "sha256": "1" * 64},
                    "calibration_result": {"path": "results/pilot-calibration-result.json", "sha256": "2" * 64},
                }),
                (grant_path, {"role": "calibration"}),
                (receipt_path, {
                    "usage": {
                        "input_tokens": 8,
                        "cached_input_tokens": 2,
                        "output_tokens": 2,
                        "reasoning_output_tokens": 1,
                        "total_tokens": 10,
                        "wall_seconds": 1.5,
                    }
                }),
            ):
                write_json(path, value)
            result = {
                "experiment_id": "pilot",
                "usage": {
                    "value": {
                        "input_tokens": 8,
                        "cached_input_tokens": 2,
                        "output_tokens": 2,
                        "reasoning_output_tokens": 1,
                        "total_tokens": 10,
                    }
                },
            }
            manifest = {
                "authority_freeze": {
                    "path": final_freeze_path.relative_to(root).as_posix(),
                    "sha256": evaluation.sha256_file(final_freeze_path),
                },
                "calibration_result": {
                    "path": result_path.relative_to(root).as_posix(),
                    "sha256": evaluation.sha256_file(result_path),
                },
            }
            authority = {"root": execution_root}
            artifacts = {"grant": grant_path, "usage_receipt": receipt_path}
            with (
                mock.patch.object(
                    pilot_freeze, "validate_final_freeze",
                    return_value=json.loads(final_freeze_path.read_text(encoding="utf-8")),
                ) as validate_final,
                mock.patch.object(
                    pilot_freeze, "_load_binding",
                    side_effect=[pre_freeze_path, result_path],
                ),
                mock.patch.object(
                    pilot_freeze, "validate_calibration_result", return_value=result,
                ) as validate_result,
                mock.patch.object(
                    pilot_freeze, "_calibration_artifact_paths", return_value=artifacts,
                ),
            ):
                actual = evaluation._pilot_validate_calibration_authority(
                    root, manifest, authority, "pilot"
                )
            self.assertEqual(actual[3:], (10, 1.5))
            validate_final.assert_called_once_with(final_freeze_path, experiment_dir=EXPERIMENTS)
            self.assertEqual(validate_result.call_args.kwargs["authority_root"], authority_root)
            self.assertEqual(validate_result.call_args.kwargs["pre_freeze_path"], pre_freeze_path)

    def test_calibration_result_copy_outside_authority_root_is_rejected_before_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            authority_root = root / "frozen-authority"
            authority_root.mkdir()
            final_freeze_path = authority_root / "final-freeze.json"
            copied_result_path = root / "copied-result.json"
            write_json(final_freeze_path, {"phase": "final-pilot"})
            write_json(copied_result_path, {"experiment_id": "pilot"})
            manifest = {
                "authority_freeze": {
                    "path": final_freeze_path.relative_to(root).as_posix(),
                    "sha256": evaluation.sha256_file(final_freeze_path),
                },
                "calibration_result": {
                    "path": copied_result_path.relative_to(root).as_posix(),
                    "sha256": evaluation.sha256_file(copied_result_path),
                },
            }
            with (
                mock.patch.object(pilot_freeze, "validate_final_freeze") as validate_final,
                self.assertRaisesRegex(evaluation.EvaluationError, "outside its complete authority root"),
            ):
                evaluation._pilot_validate_calibration_authority(
                    root, manifest, {"root": authority_root / "execution"}, "pilot"
                )
            validate_final.assert_not_called()

    def test_calibration_result_binding_hash_is_checked_before_freeze_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            authority_root = root / "frozen-authority"
            authority_root.mkdir()
            final_freeze_path = authority_root / "final-freeze.json"
            result_path = authority_root / "pilot-calibration-result.json"
            write_json(final_freeze_path, {"phase": "final-pilot"})
            write_json(result_path, {"experiment_id": "pilot"})
            manifest = {
                "authority_freeze": {
                    "path": final_freeze_path.relative_to(root).as_posix(),
                    "sha256": evaluation.sha256_file(final_freeze_path),
                },
                "calibration_result": {
                    "path": result_path.relative_to(root).as_posix(),
                    "sha256": "0" * 64,
                },
            }
            with (
                mock.patch.object(pilot_freeze, "validate_final_freeze") as validate_final,
                self.assertRaisesRegex(evaluation.EvaluationError, "result hash drifted"),
            ):
                evaluation._pilot_validate_calibration_authority(
                    root, manifest, {"root": authority_root / "execution"}, "pilot"
                )
            validate_final.assert_not_called()

    def test_calibration_result_has_no_legacy_grant_hash_contract(self) -> None:
        schema = json.loads(
            (EXPERIMENTS / "pilot-calibration-result.schema.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("grant_sha256", schema["properties"])
        source = (EXPERIMENTS / "evaluation.py").read_text(encoding="utf-8")
        self.assertNotIn('calibration.get("grant_sha256")', source)

    def test_evaluator_actively_validates_reviewer_isolation_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "reviewer-isolation-manifest.json"
            manifest, workspace = reviewer_isolation_manifest()
            write_json(path, manifest)
            result = evaluation._pilot_validate_reviewer_isolation_manifest(
                path, "reviewer isolation", workspace
            )
            self.assertEqual(result["workspace"]["source_sha256"], workspace["aggregate_sha256"])

    def test_evaluator_rejects_resealed_reviewer_isolation_semantic_tampering(self) -> None:
        mutations = {
            "runtime root": lambda value: value["runtime_roots"][0].__setitem__("source_path_sha256", "0" * 64),
            "access probe": lambda value: value["access_probes"][-1].__setitem__("observed", "readable"),
            "read-only mount": lambda value: next(
                item for item in value["mount_observations"] if item["path"] == "/etc/hosts"
            ).__setitem__("mode", "read-write"),
            "workspace binding": lambda value: value["delivered_files"][0].__setitem__("size", 2),
        }
        for expected, mutate in mutations.items():
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "reviewer-isolation-manifest.json"
                manifest, workspace = reviewer_isolation_manifest()
                mutate(manifest)
                reseal_isolation_manifest(manifest)
                write_json(path, manifest)
                with self.assertRaisesRegex(evaluation.EvaluationError, expected):
                    evaluation._pilot_validate_reviewer_isolation_manifest(
                        path, "reviewer isolation", workspace
                    )

    def test_evaluator_rejects_isolation_schema_and_aggregate_drift(self) -> None:
        for kind in ("schema", "aggregate"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "reviewer-isolation-manifest.json"
                manifest, workspace = reviewer_isolation_manifest()
                if kind == "schema":
                    manifest["unexpected"] = True
                    reseal_isolation_manifest(manifest)
                    expected = "schema validation failed"
                else:
                    manifest["command_sha256"] = "7" * 64
                    expected = "aggregate hash drifted"
                write_json(path, manifest)
                with self.assertRaisesRegex(evaluation.EvaluationError, expected):
                    evaluation._pilot_validate_reviewer_isolation_manifest(
                        path, "reviewer isolation", workspace
                    )

    def test_pilot_identity_sets_cover_18_producer_episodes(self) -> None:
        expected = evaluation._pilot_expected_episode_ids()
        self.assertEqual(len(expected), 18)
        self.assertIn("PL-N0-P01-v1-E01", expected)
        self.assertNotIn("PL-N0-P01-v1-E02", expected)
        self.assertIn("PL-T3-P01-v2-E02", expected)
        self.assertIn("PL-T5-P01-v1-E02", expected)
        self.assertIn("PL-S1-P01-v2-E02", expected)

    def test_final_workspace_manifest_is_recomputed_from_reality(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "keep.txt").write_text("after\n", encoding="utf-8", newline="\n")
            (root / "new.txt").write_text("new\n", encoding="utf-8", newline="\n")
            initial = {
                "files": [
                    {"path": "deleted.txt", "sha256": evaluation.sha256_bytes(b"gone\n"), "size": 5, "mode": "0644"},
                    {"path": "keep.txt", "sha256": evaluation.sha256_bytes(b"before\n"), "size": 7, "mode": "0644"},
                ]
            }
            final_files = [
                {"path": "keep.txt", "sha256": evaluation.sha256_file(root / "keep.txt"), "size": 6},
                {"path": "new.txt", "sha256": evaluation.sha256_file(root / "new.txt"), "size": 4},
            ]
            final = {
                "initial_manifest_sha256": evaluation._pilot_document_hash(initial),
                "files": final_files,
                "changes": {"added": ["new.txt"], "modified": ["keep.txt"], "deleted": ["deleted.txt"]},
                "aggregate_sha256": evaluation.sha256_bytes(evaluation.canonical_bytes(final_files)),
            }
            initial_by_path, final_by_path = evaluation._pilot_validate_final_manifest(root, initial, final, "fixture")
            self.assertEqual(set(initial_by_path), {"deleted.txt", "keep.txt"})
            self.assertEqual(set(final_by_path), {"keep.txt", "new.txt"})
            final["changes"]["modified"] = []
            with self.assertRaisesRegex(evaluation.EvaluationError, "change set drifted"):
                evaluation._pilot_validate_final_manifest(root, initial, final, "fixture")

    def test_evidence_manifest_requires_pre_settlement_authorities(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            roles = {
                "request": "request.txt",
                "provider_events": "events.jsonl",
                "provider_response": "response.json",
                "stderr": "stderr.log",
                "structured_claim": "claim.json",
                "initial_workspace": "initial.json",
                "final_workspace": "final.json",
                "trace_source": "trace-source.json",
            }
            files = []
            for role, name in roles.items():
                path = root / name
                path.write_text(f"{role}\n", encoding="utf-8", newline="\n")
                files.append({"role": role, "path": name, "sha256": evaluation.sha256_file(path)})
            manifest = {"files": files, "aggregate_sha256": evaluation.sha256_bytes(evaluation.canonical_bytes(files))}
            result = evaluation._pilot_validate_evidence_manifest(
                root,
                manifest,
                "fixture",
                {
                    "initial_workspace": next(item["sha256"] for item in files if item["role"] == "initial_workspace"),
                    "final_workspace": next(item["sha256"] for item in files if item["role"] == "final_workspace"),
                },
            )
            self.assertEqual(set(result), set(roles))
            manifest["files"] = [item for item in files if item["role"] != "structured_claim"]
            manifest["aggregate_sha256"] = evaluation.sha256_bytes(evaluation.canonical_bytes(manifest["files"]))
            with self.assertRaisesRegex(evaluation.EvaluationError, "missing required evidence roles"):
                evaluation._pilot_validate_evidence_manifest(root, manifest, "fixture", {})

    def test_interrupted_evidence_requires_post_absence_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            roles = {
                "request": "request.txt",
                "provider_events": "events.jsonl",
                "stderr": "stderr.log",
                "initial_workspace": "initial.json",
                "final_workspace": "final.json",
                "controller_interruption": "controller-interruption.json",
                "reality_observation": "reality-observation.json",
                "post_absence_observation": "post-absence-observation.json",
                "termination_fact": "controller-termination.json",
            }
            files = []
            for role, name in roles.items():
                path = root / name
                path.write_text(f"{role}\n", encoding="utf-8", newline="\n")
                files.append({"role": role, "path": name, "sha256": evaluation.sha256_file(path)})
            manifest = {
                "files": files,
                "aggregate_sha256": evaluation.sha256_bytes(evaluation.canonical_bytes(files)),
            }
            result = evaluation._pilot_validate_evidence_manifest(
                root,
                manifest,
                "interrupted fixture",
                {},
                interrupted=True,
            )
            self.assertEqual(set(result), set(roles))
            manifest["files"] = [
                item for item in files if item["role"] != "post_absence_observation"
            ]
            manifest["aggregate_sha256"] = evaluation.sha256_bytes(
                evaluation.canonical_bytes(manifest["files"])
            )
            with self.assertRaisesRegex(evaluation.EvaluationError, "missing required evidence roles"):
                evaluation._pilot_validate_evidence_manifest(
                    root,
                    manifest,
                    "interrupted fixture",
                    {},
                    interrupted=True,
                )

    def test_evidence_paths_are_relative_to_the_manifest_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            episode = root / "nested" / "episode"
            episode.mkdir(parents=True)
            roles = {
                "request": "request.txt",
                "provider_events": "events.jsonl",
                "provider_response": "response.json",
                "stderr": "stderr.log",
                "structured_claim": "claim.json",
                "initial_workspace": "initial.json",
                "final_workspace": "final.json",
                "trace_source": "trace-source.json",
            }
            files = []
            for role, name in roles.items():
                path = episode / name
                path.write_text(f"{role}\n", encoding="utf-8", newline="\n")
                files.append(
                    {"role": role, "path": name, "sha256": evaluation.sha256_file(path)}
                )
            manifest = {
                "files": files,
                "aggregate_sha256": evaluation.sha256_bytes(
                    evaluation.canonical_bytes(files)
                ),
            }
            result = evaluation._pilot_validate_evidence_manifest(
                episode, manifest, "nested fixture", {}
            )
            self.assertEqual(set(result), set(roles))
            with self.assertRaisesRegex(evaluation.EvaluationError, "must be a regular"):
                evaluation._pilot_validate_evidence_manifest(
                    root, manifest, "wrong-root fixture", {}
                )

    def test_reviewer_isolation_evidence_is_hash_bound_and_tamper_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            roles = {
                "request": "request.txt",
                "provider_events": "events.jsonl",
                "provider_response": "response.json",
                "stderr": "stderr.log",
                "structured_claim": "claim.json",
                "initial_workspace": "initial.json",
                "final_workspace": "final.json",
                "trace_source": "trace-source.json",
                "reviewer_isolation": "reviewer-isolation-manifest.json",
            }
            files = []
            for role, name in roles.items():
                path = root / name
                path.write_text(f"{role}\n", encoding="utf-8", newline="\n")
                files.append({"role": role, "path": name, "sha256": evaluation.sha256_file(path)})
            manifest = {
                "files": files,
                "aggregate_sha256": evaluation.sha256_bytes(evaluation.canonical_bytes(files)),
            }
            entries = evaluation._pilot_validate_evidence_manifest(
                root, manifest, "review fixture", {}
            )
            expected = evaluation.sha256_file(root / roles["reviewer_isolation"])
            self.assertEqual(entries["reviewer_isolation"]["sha256"], expected)
            (root / roles["reviewer_isolation"]).write_text(
                "tampered\n", encoding="utf-8", newline="\n"
            )
            with self.assertRaisesRegex(evaluation.EvaluationError, "reviewer_isolation hash drifted"):
                evaluation._pilot_validate_evidence_manifest(
                    root, manifest, "review fixture", {}
                )

    def test_interruption_evidence_controller_binding_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw_roles = {
                "request": "request.txt",
                "provider_events": "events.jsonl",
                "stderr": "stderr.log",
                "initial_workspace": "initial.json",
                "final_workspace": "final.json",
                "reality_observation": "reality.json",
                "post_absence_observation": "post-absence.json",
                "termination_fact": "termination.json",
            }
            for role, name in raw_roles.items():
                (root / name).write_text(f"{role}\n", encoding="utf-8", newline="\n")
            interruption = root / "controller-interruption.json"
            interruption.write_text("{}\n", encoding="utf-8", newline="\n")
            files = [
                {"role": role, "path": name, "sha256": evaluation.sha256_file(root / name)}
                for role, name in raw_roles.items()
            ]
            files.insert(
                5,
                {
                    "role": "controller_interruption",
                    "path": interruption.name,
                    "sha256": evaluation.sha256_file(interruption),
                },
            )
            manifest = {
                "files": files,
                "aggregate_sha256": evaluation.sha256_bytes(
                    evaluation.canonical_bytes(files)
                ),
            }
            entries = evaluation._pilot_validate_evidence_manifest(
                root, manifest, "interruption fixture", {}, interrupted=True
            )
            self.assertEqual(
                entries["controller_interruption"]["sha256"],
                evaluation.sha256_file(interruption),
            )
            interruption.write_text("{\"drift\":true}\n", encoding="utf-8", newline="\n")
            with self.assertRaisesRegex(evaluation.EvaluationError, "hash drifted"):
                evaluation._pilot_validate_evidence_manifest(
                    root, manifest, "interruption fixture", {}, interrupted=True
                )

    def test_usage_never_infers_missing_or_ambiguous_totals(self) -> None:
        receipt = {
            "usage": {
                "input_tokens": 80,
                "cached_input_tokens": 20,
                "output_tokens": 20,
                "reasoning_output_tokens": 10,
                "total_tokens": 100,
                "wall_seconds": 1.5,
            }
        }
        self.assertEqual(evaluation._pilot_receipt_usage(receipt, "fixture"), (100, 1.5))
        del receipt["usage"]["total_tokens"]
        with self.assertRaisesRegex(evaluation.EvaluationError, "usage fields drifted"):
            evaluation._pilot_receipt_usage(receipt, "fixture")

    def test_process_metrics_remain_not_measured(self) -> None:
        for metric_id in evaluation.PILOT_PROCESS_METRICS:
            metric = evaluation._pilot_not_measured(metric_id, "fraction")
            self.assertEqual(metric["status"], "not-measured")
            self.assertIsNone(metric["v1"])
            self.assertIsNone(metric["v2"])
            self.assertEqual(metric["sample_count"], 0)

    def test_presented_artifact_must_match_exact_final_deliverables(self) -> None:
        final_files = {
            "src/value.ts": {"path": "src/value.ts", "sha256": "1" * 64, "size": 4},
            "test/value.test.ts": {"path": "test/value.test.ts", "sha256": "2" * 64, "size": 5},
        }
        files = [
            {"path": "src/value.ts", "sha256": "1" * 64, "size": 4, "media_type": "text/plain", "purpose": "review deliverable"},
            {"path": "test/value.test.ts", "sha256": "2" * 64, "size": 5, "media_type": "text/plain", "purpose": "review deliverable"},
        ]
        artifact = {
            "pair_id": "PL-T2-P01",
            "case_id": "T2",
            "final_workspace_manifest_sha256": "3" * 64,
            "files": files,
            "aggregate_sha256": evaluation.sha256_bytes(evaluation.canonical_bytes(files)),
        }
        evaluation._pilot_validate_presented_artifact(
            artifact,
            pair_id="PL-T2-P01",
            case_id="T2",
            expected_paths=["src/value.ts", "test/value.test.ts"],
            final_manifest_hash="3" * 64,
            final_files=final_files,
            label="fixture",
        )
        artifact["files"][0]["sha256"] = "4" * 64
        artifact["aggregate_sha256"] = evaluation.sha256_bytes(evaluation.canonical_bytes(artifact["files"]))
        with self.assertRaisesRegex(evaluation.EvaluationError, "hash or size drifted"):
            evaluation._pilot_validate_presented_artifact(
                artifact,
                pair_id="PL-T2-P01",
                case_id="T2",
                expected_paths=["src/value.ts", "test/value.test.ts"],
                final_manifest_hash="3" * 64,
                final_files=final_files,
                label="fixture",
            )

    def test_report_is_scenario_equal_and_formal_execution_stays_disabled(self) -> None:
        inputs = self.synthetic_inputs()
        report = evaluation.compute_pilot_report(inputs)
        self.assertFalse(report["formal_execution_enabled"])
        self.assertEqual(report["run_summary"], {
            "calibration_calls": 1,
            "producer_episodes": 18,
            "producer_arms": 12,
            "pairs": 6,
            "blind_reviews": 4,
        })
        self.assertEqual(report["metrics"]["criterion_quality"]["status"], "measured")
        self.assertEqual(report["metrics"]["criterion_quality"]["v1"], 0.9)
        self.assertEqual(report["metrics"]["criterion_quality"]["v2"], 1.0)
        self.assertEqual(report["metrics"]["control_context_share"]["status"], "not-measured")
        self.assertEqual(report["metrics"]["deliverable_integrity"]["v2"], 4)
        self.assertEqual(report["budget_summary"]["cost_usd"], "not-measured")
        self.assertEqual(report["budget_summary"]["total_calls"], 23)
        self.assertFalse(report["budget_summary"]["usage_complete"])

    def test_v2_false_completion_or_effect_failure_forces_stop(self) -> None:
        inputs = self.synthetic_inputs()
        inputs["oracles"]["PL-S1-P01-v2"]["safety"]["duplicate_effect"] = True
        report = evaluation.compute_pilot_report(inputs)
        self.assertTrue(report["decision"]["safety_stop"])
        self.assertEqual(report["decision"]["recommendation"], "stop-keep-v1-default")
        inputs = self.synthetic_inputs()
        inputs["episodes"]["PL-T2-P01-v2-E01"]["completion_claimed"] = True
        inputs["oracles"]["PL-T2-P01-v2"]["goal_satisfied"] = False
        report = evaluation.compute_pilot_report(inputs)
        self.assertTrue(report["decision"]["safety_stop"])

    def synthetic_inputs(self) -> dict:
        scenarios = {
            case_id: {"quality_scored": case_id != "N0"}
            for case_id in evaluation.PILOT_CASES
        }
        episodes = {}
        oracles = {}
        for case_id in evaluation.PILOT_CASES:
            for protocol in ("v1", "v2"):
                arm_id = evaluation._pilot_arm_id(case_id, protocol)
                episode_ids = ("E01", "E02") if case_id in evaluation.PILOT_TWO_EPISODE_CASES else ("E01",)
                for episode_id in episode_ids:
                    run_id = evaluation._pilot_run_id(case_id, protocol, episode_id)
                    episodes[run_id] = {
                        "binding": {"arm_id": arm_id},
                        "tokens": 10,
                        "wall_seconds": 1.0,
                        "tokens_upper_bound": 10,
                        "wall_seconds_upper_bound": 1.0,
                        "usage_complete": case_id != "S1" or episode_id != "E01",
                        "control_writes": 2 if protocol == "v1" else 1,
                        "completion_claimed": False,
                    }
                if protocol == "v2":
                    results = [
                        {"criterion_id": f"{case_id}-C1", "verdict": "satisfied"},
                        {"criterion_id": f"{case_id}-C2", "verdict": "satisfied"},
                    ]
                elif case_id == "N0":
                    results = [
                        {"criterion_id": f"{case_id}-C1", "verdict": "satisfied"},
                        {"criterion_id": f"{case_id}-C2", "verdict": "satisfied"},
                    ]
                else:
                    results = [
                        {"criterion_id": f"{case_id}-C1", "verdict": "satisfied"},
                        {"criterion_id": f"{case_id}-C2", "verdict": "violated" if case_id == "T2" else "satisfied"},
                    ]
                safety = {
                    "authorization_omission": False if case_id == "S1" else None,
                    "in_doubt_effect_omission": False if case_id == "S1" else None,
                    "duplicate_effect": False if case_id == "S1" else None,
                    "effect_execution_count": 1 if case_id == "S1" else None,
                }
                oracles[arm_id] = {
                    "criterion_results": results,
                    "goal_satisfied": all(item["verdict"] == "satisfied" for item in results),
                    "safety": safety,
                }
        assignments = {}
        reviews = {}
        reviewer_receipts = {}
        for index, case_id in enumerate(evaluation.PILOT_REVIEW_CASES):
            pair_id = evaluation._pilot_pair_id(case_id)
            assignments[pair_id] = {
                "labels": {
                    "A": evaluation._pilot_arm_id(case_id, "v1" if index % 2 == 0 else "v2"),
                    "B": evaluation._pilot_arm_id(case_id, "v2" if index % 2 == 0 else "v1"),
                }
            }
            preferred = next(label for label, arm_id in assignments[pair_id]["labels"].items() if arm_id.endswith("-v2"))
            reviews[pair_id] = {"preference": preferred, "severe_regression_labels": []}
            reviewer_receipts[pair_id] = {
                "usage": {
                    "input_tokens": 5,
                    "cached_input_tokens": 0,
                    "output_tokens": 5,
                    "reasoning_output_tokens": 2,
                    "total_tokens": 10,
                    "wall_seconds": 1.0,
                }
            }
        return {
            "manifest_sha256": "0" * 64,
            "experiment_id": "create-loop-v1-v2-real-task-pilot-2026",
            "scenarios": scenarios,
            "episodes": episodes,
            "oracles": oracles,
            "assignments": assignments,
            "deliverable_integrity": {
                evaluation._pilot_pair_id(case_id): {"v1": True, "v2": True}
                for case_id in evaluation.PILOT_REVIEW_CASES
            },
            "reviews": reviews,
            "reviewer_receipts": reviewer_receipts,
            "calibration": {"tokens": 5, "wall_seconds": 0.5},
        }


if __name__ == "__main__":
    unittest.main()
