from __future__ import annotations

import json
import multiprocessing
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = SKILL_ROOT / "tests" / "experiments"
sys.path.insert(0, str(EXPERIMENTS))

import execution_guard as guard  # noqa: E402


NOW = datetime(2026, 8, 5, 12, tzinfo=timezone.utc)
SETTLED = NOW + timedelta(seconds=20)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(guard.canonical_bytes(value))


def reserve_worker(
    root: str, run_id: str, attempt_id: str, episode_id: str, queue: multiprocessing.Queue
) -> None:
    try:
        guard.reserve(Path(root), run_id, attempt_id, episode_id, now=NOW)
        queue.put(("ok", attempt_id))
    except Exception as exc:  # pragma: no cover - asserted in parent
        queue.put(("error", type(exc).__name__, str(exc)))


class ExperimentExecutionGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "execution"
        self.grant_path = self.base / "grant-input.json"
        self.grant = self.make_grant()
        write_json(self.grant_path, self.grant)

    def make_grant(self, **total_overrides: object) -> dict:
        total = {"max_calls": 3, "max_total_tokens": 300, "max_wall_seconds": 180}
        total.update(total_overrides)
        return {
            "schema_version": "2.0",
            "authorization_id": "authorization-producer-1",
            "execution_id": "execution-producer-1",
            "execution_root_sha256": guard._root_path_sha256(self.root),
            "experiment_id": "experiment-1",
            "preregistration_sha256": "a" * 64,
            "run_plan_sha256": "b" * 64,
            "role": "producer",
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
            "authorized_calls": [
                {"run_id": "run-1", "episode_id": "E01"},
                {"run_id": "run-1", "episode_id": "E02"},
                {"run_id": "run-2", "episode_id": "E01"},
            ],
            "limits": {
                "per_call": {"max_total_tokens": 100, "max_wall_seconds": 60},
                "total": total,
            },
            "authorized_by": "unit-test",
            "authorized_at": "2026-08-05T00:00:00Z",
            "expires_at": "2026-08-06T00:00:00Z",
            "authority_evidence_sha256": "1" * 64,
        }

    def initialize(self) -> dict:
        return guard.initialize(self.root, self.grant_path, now=NOW)

    def receipt_and_evidence(
        self,
        run_id: str,
        attempt_id: str,
        episode_id: str = "E01",
        *,
        input_tokens: int = 20,
        cached_input_tokens: int = 5,
        output_tokens: int = 20,
        reasoning_output_tokens: int = 10,
        seconds: float = 10,
        request_id: str | None = None,
    ) -> tuple[Path, Path]:
        attempt = self.base / attempt_id
        attempt.mkdir(exist_ok=True)
        files = {
            "request.txt": b"request\n",
            "events.jsonl": b'{"type":"turn.completed"}\n',
            "stderr.log": b"",
            "claim.json": b'{"completion_claimed":false,"summary":"incomplete","deliverables":[],"blockers":[],"risks":[]}\n',
            "workspace-initial.json": b'{"initial":true}\n',
            "workspace-final.json": b'{"final":true}\n',
            "workspace-population-seal.json": b'{"sealed":true}\n',
            "trace-source.json": b'{"source":true}\n',
        }
        for name, data in files.items():
            (attempt / name).write_bytes(data)
        evidence_files = [
            {"role": role, "path": name, "sha256": guard.sha256_file(attempt / name)}
            for role, name in (
                ("request", "request.txt"),
                ("provider_events", "events.jsonl"),
                ("stderr", "stderr.log"),
                ("structured_claim", "claim.json"),
                ("initial_workspace", "workspace-initial.json"),
                ("final_workspace", "workspace-final.json"),
                ("workspace_population_seal", "workspace-population-seal.json"),
                ("trace_source", "trace-source.json"),
            )
        ]
        evidence = {
            "schema_version": "1.0",
            "run_id": run_id,
            "episode_id": episode_id,
            "attempt_id": attempt_id,
            "role": self.grant["role"],
            "initial_workspace_manifest": {
                "path": "workspace-initial.json",
                "sha256": guard.sha256_file(attempt / "workspace-initial.json"),
            },
            "final_workspace_manifest": {
                "path": "workspace-final.json",
                "sha256": guard.sha256_file(attempt / "workspace-final.json"),
            },
            "workspace_population_seal": {
                "path": "workspace-population-seal.json",
                "sha256": guard.sha256_file(attempt / "workspace-population-seal.json"),
            },
            "structured_claim": {
                "path": "claim.json",
                "sha256": guard.sha256_file(attempt / "claim.json"),
            },
            "files": evidence_files,
            "aggregate_sha256": guard.sha256_bytes(guard.canonical_bytes(evidence_files)),
        }
        evidence_path = attempt / "evidence-manifest.json"
        write_json(evidence_path, evidence)
        ended = NOW + timedelta(seconds=seconds)
        usage = {
            "input_tokens": input_tokens,
            "cached_input_tokens": cached_input_tokens,
            "output_tokens": output_tokens,
            "reasoning_output_tokens": reasoning_output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "wall_seconds": seconds,
        }
        receipt = {
            "schema_version": "2.0",
            "receipt_id": f"receipt-{attempt_id}",
            "authorization_id": self.grant["authorization_id"],
            "execution_id": self.grant["execution_id"],
            "run_id": run_id,
            "episode_id": episode_id,
            "attempt_id": attempt_id,
            "role": self.grant["role"],
            "adapter": self.grant["adapter"],
            "cli_identity": self.grant["cli_identity"],
            "provider_profile": self.grant["provider_profile"],
            "model": self.grant["model"],
            "reasoning_effort": self.grant["reasoning_effort"],
            "tool_profile": self.grant["tool_profile"],
            "source_class": "provider-response",
            "provider_request_ids": [request_id or f"request-{attempt_id}"],
            "request_sha256": "2" * 64,
            "response_sha256": "3" * 64,
            "usage": usage,
            "started_at": NOW.isoformat().replace("+00:00", "Z"),
            "ended_at": ended.isoformat().replace("+00:00", "Z"),
            "raw_evidence_sha256": "4" * 64,
            "evidence_manifest_sha256": guard.sha256_file(evidence_path),
        }
        receipt_path = attempt / "usage-receipt.json"
        write_json(receipt_path, receipt)
        return receipt_path, evidence_path

    def settle(self, run_id: str, attempt_id: str, episode_id: str = "E01", **usage: object) -> dict:
        receipt, evidence = self.receipt_and_evidence(run_id, attempt_id, episode_id, **usage)
        receipt_value = json.loads(receipt.read_text())
        settled_at = datetime.fromisoformat(receipt_value["ended_at"].replace("Z", "+00:00")) + timedelta(seconds=1)
        return guard.settle(self.root, receipt, evidence, now=settled_at)

    def interruption(self, run_id: str, attempt_id: str) -> tuple[Path, Path]:
        attempt = self.base / f"interrupted-{attempt_id}"
        attempt.mkdir(exist_ok=True)
        files = {
            "request.txt": b"request\n",
            "events.jsonl": b'{"type":"item.started"}\n',
            "stderr.log": b"",
            "workspace-initial.json": b'{"initial":true}\n',
            "workspace-final.json": b'{"final":true}\n',
            "workspace-population-seal.json": b'{"sealed":true}\n',
            "protocol-bundle.json": b'{"protocol":true}\n',
            "reality-observation.json": b'{"applied_count":1,"operation_ids":["pilot-credit-001"]}\n',
            "post-absence-observation.json": b'{"all_absent_after_termination":true}\n',
            "termination-fact.json": b'{"terminated":true}\n',
        }
        for name, data in files.items():
            (attempt / name).write_bytes(data)
        ordered = []
        bindings = {}
        for field, name in (
            ("partial_provider_events", "events.jsonl"),
            ("stderr", "stderr.log"),
            ("initial_workspace_manifest", "workspace-initial.json"),
            ("final_workspace_manifest", "workspace-final.json"),
            ("reality_observation", "reality-observation.json"),
            ("post_absence_observation", "post-absence-observation.json"),
            ("termination_fact", "termination-fact.json"),
        ):
            binding = {"path": name, "sha256": guard.sha256_file(attempt / name)}
            bindings[field] = binding
            ordered.append({"role": field, **binding})
        manifest = {
            "schema_version": "1.0",
            "authorization_id": self.grant["authorization_id"],
            "execution_id": self.grant["execution_id"],
            "experiment_id": self.grant["experiment_id"],
            "run_id": run_id,
            "episode_id": "E01",
            "attempt_id": attempt_id,
            "role": "producer",
            "case_id": "S1",
            "termination": guard.INTERRUPTION_TERMINATION,
            "reason": guard.INTERRUPTION_REASON,
            "interrupted_at": NOW.isoformat().replace("+00:00", "Z"),
            "controller": {
                "id": "create-loop-codex-exec-adapter",
                "observed_at": NOW.isoformat().replace("+00:00", "Z"),
                "termination_method": "graceful-then-force",
            },
            "wall_seconds_upper_bound": {"seconds": 10, "source": "controller-measured"},
            **bindings,
            "controller_evidence_sha256": guard.sha256_bytes(guard.canonical_bytes(ordered)),
        }
        path = attempt / "controller-interruption.json"
        write_json(path, manifest)
        evidence_files = [
            {"role": role, "path": name, "sha256": guard.sha256_file(attempt / name)}
            for role, name in (
                ("request", "request.txt"),
                ("provider_events", "events.jsonl"),
                ("stderr", "stderr.log"),
                ("initial_workspace", "workspace-initial.json"),
                ("final_workspace", "workspace-final.json"),
                ("workspace_population_seal", "workspace-population-seal.json"),
                ("protocol_bundle", "protocol-bundle.json"),
                ("controller_interruption", "controller-interruption.json"),
                ("reality_observation", "reality-observation.json"),
                ("post_absence_observation", "post-absence-observation.json"),
                ("termination_fact", "termination-fact.json"),
            )
        ]
        by_role = {item["role"]: item for item in evidence_files}
        evidence = {
            "schema_version": "1.0",
            "run_id": run_id,
            "episode_id": "E01",
            "attempt_id": attempt_id,
            "role": "producer",
            "initial_workspace_manifest": {
                "path": by_role["initial_workspace"]["path"],
                "sha256": by_role["initial_workspace"]["sha256"],
            },
            "final_workspace_manifest": {
                "path": by_role["final_workspace"]["path"],
                "sha256": by_role["final_workspace"]["sha256"],
            },
            "workspace_population_seal": {
                "path": by_role["workspace_population_seal"]["path"],
                "sha256": by_role["workspace_population_seal"]["sha256"],
            },
            "controller_interruption": {
                "path": by_role["controller_interruption"]["path"],
                "sha256": by_role["controller_interruption"]["sha256"],
            },
            "controller_evidence_sha256": manifest["controller_evidence_sha256"],
            "files": evidence_files,
            "aggregate_sha256": guard.sha256_bytes(guard.canonical_bytes(evidence_files)),
        }
        evidence_path = attempt / "evidence-manifest.json"
        write_json(evidence_path, evidence)
        return path, evidence_path

    def test_schemas_supported_and_legacy_cost_fields_rejected(self):
        from schema_runtime import check_schema

        for schema in guard.SCHEMAS.values():
            check_schema(json.loads(schema.read_text(encoding="utf-8")))
        broken = json.loads(json.dumps(self.grant))
        broken["pricing"] = {"currency": "USD"}
        write_json(self.grant_path, broken)
        with self.assertRaisesRegex(guard.GuardError, "unexpected property 'pricing'"):
            guard.load_grant(self.grant_path)

    def test_schema_file_cache_rechecks_changed_bytes(self):
        from schema_runtime import SchemaError, validate_schema_file

        schema = self.base / "schema.json"
        write_json(schema, {"type": "object", "additionalProperties": False})
        self.assertEqual(validate_schema_file({}, schema), [])
        write_json(schema, {"type": "object", "unsupportedKeyword": True})
        with self.assertRaisesRegex(SchemaError, "unsupported schema keyword"):
            validate_schema_file({}, schema)

    def test_replay_cache_rechecks_old_ledger_and_stored_evidence_bytes(self):
        self.initialize()
        guard.reserve(self.root, "run-1", "attempt-1", "E01", now=NOW)
        receipt, evidence = self.receipt_and_evidence("run-1", "attempt-1")
        guard.settle(self.root, receipt, evidence, now=SETTLED)
        guard.replay(self.root, now=SETTLED)

        first_record = sorted((self.root / "ledger").glob("*.json"))[0]
        original_record = first_record.read_bytes()
        first_record.write_bytes(original_record + b" ")
        with self.assertRaisesRegex(guard.GuardError, "ledger tail|hash chain"):
            guard.replay(self.root, now=SETTLED)
        first_record.write_bytes(original_record)

        settlement = json.loads(
            sorted((self.root / "ledger").glob("*.json"))[-1].read_text()
        )
        stored_evidence = self.root / "evidence" / settlement["payload"]["evidence_path"]
        original_evidence = stored_evidence.read_bytes()
        stored_evidence.write_bytes(original_evidence + b" ")
        with self.assertRaisesRegex(
            guard.GuardError, "evidence root contains a non-canonical manifest|evidence hash drifted"
        ):
            guard.replay(self.root, now=SETTLED)

    def test_replay_cache_is_scoped_to_root_and_authority(self):
        self.initialize()
        cached = guard.replay(self.root, now=NOW)
        other = self.base / "other-root"
        other_grant = json.loads(json.dumps(self.grant))
        other_grant["authorization_id"] = "authorization-other"
        other_grant["execution_id"] = "execution-other"
        other_grant["execution_root_sha256"] = guard._root_path_sha256(other)
        other_path = self.base / "other-grant.json"
        write_json(other_path, other_grant)
        other_summary = guard.initialize(other, other_path, now=NOW)
        self.assertEqual(cached["root_path_sha256"], guard._root_path_sha256(self.root))
        self.assertEqual(other_summary["root_path_sha256"], guard._root_path_sha256(other))
        self.assertNotEqual(cached["authorization_id"], other_summary["authorization_id"])

    def test_cold_replay_revalidates_copied_evidence_files(self):
        self.initialize()
        guard.reserve(self.root, "run-1", "attempt-1", "E01", now=NOW)
        receipt, evidence = self.receipt_and_evidence("run-1", "attempt-1")
        guard.settle(self.root, receipt, evidence, now=SETTLED)
        record = json.loads(
            sorted((self.root / "ledger").glob("*.json"))[-1].read_text()
        )
        copied = (
            self.root
            / "evidence"
            / Path(record["payload"]["evidence_path"]).stem
            / "workspace-final.json"
        )
        guard._REPLAY_CACHE.clear()
        guard._STRICT_JSON_CACHE.clear()
        guard._VALIDATED_JSON_CACHE.clear()
        copied.write_bytes(b"changed\n")
        with self.assertRaisesRegex(guard.GuardError, "evidence file hash drifted"):
            guard.replay(self.root, now=SETTLED)

    def test_fresh_process_can_replay_settled_copied_evidence(self):
        self.initialize()
        guard.reserve(self.root, "run-1", "attempt-1", "E01", now=NOW)
        receipt, evidence = self.receipt_and_evidence("run-1", "attempt-1")
        guard.settle(self.root, receipt, evidence, now=SETTLED)
        script = self.base / "cold-replay.py"
        script.write_text(
            "import sys\n"
            "from pathlib import Path\n"
            f"sys.path.insert(0, {str(EXPERIMENTS)!r})\n"
            "import execution_guard\n"
            "print(execution_guard.replay(Path(sys.argv[1]))['status'])\n",
            encoding="utf-8",
        )
        completed = subprocess.run(
            [sys.executable, str(script), str(self.root)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "active")

    def test_replay_cache_returns_isolated_summary_objects(self):
        self.initialize()
        first = guard.replay(self.root, now=NOW)
        first["charged"]["calls"] = 999
        second = guard.replay(self.root, now=NOW)
        self.assertEqual(second["charged"]["calls"], 0)

    def test_replay_snapshot_binds_exact_authority_bytes_and_is_isolated(self):
        self.initialize()
        first = guard.replay_snapshot(self.root, now=NOW)
        first_summary = guard.summary_from_snapshot(self.root, first)
        first_summary["charged"]["calls"] = 999
        self.assertEqual(
            guard.summary_from_snapshot(self.root, first)["charged"]["calls"], 0
        )

        unreferenced = self.root / "evidence" / "unreferenced"
        unreferenced.mkdir()
        (unreferenced / "extra.json").write_text("{}\n", encoding="utf-8")
        second = guard.replay_snapshot(self.root, now=NOW)
        self.assertFalse(guard.same_replay_authority(first, second))

        with self.assertRaisesRegex(guard.GuardError, "invalid execution replay snapshot"):
            guard.summary_from_snapshot(self.root, object())

    def test_replay_snapshot_rejects_constructed_token_forgery(self):
        self.initialize()
        snapshot = guard.replay_snapshot(self.root, now=NOW)
        forged = object.__new__(guard.ReplaySnapshot)
        with self.assertRaisesRegex(guard.GuardError, "invalid execution replay snapshot"):
            guard.summary_from_snapshot(self.root, forged)
        with self.assertRaisesRegex(guard.GuardError, "invalid execution replay snapshot"):
            guard.same_replay_authority(snapshot, forged)

    def test_same_replay_authority_compares_replayed_summary_bytes(self):
        self.initialize()
        first = guard.replay_snapshot(self.root, now=NOW)
        second = guard.replay_snapshot(self.root, now=NOW)
        root_path, fingerprint, summary_bytes = guard._REPLAY_SNAPSHOT_RECORDS[second]
        summary = json.loads(summary_bytes.decode("utf-8"))
        summary["status"] = "closed"
        guard._REPLAY_SNAPSHOT_RECORDS[second] = (
            root_path,
            fingerprint,
            guard.canonical_bytes(summary),
        )

        self.assertFalse(guard.same_replay_authority(first, second))

    def test_multi_root_snapshot_holds_all_execution_locks(self):
        self.initialize()
        second_root = self.base / "execution-second"
        second_grant_path = self.base / "grant-second.json"
        second_grant = self.make_grant()
        second_grant["authorization_id"] = "authorization-producer-2"
        second_grant["execution_id"] = "execution-producer-2"
        second_grant["execution_root_sha256"] = guard._root_path_sha256(second_root)
        write_json(second_grant_path, second_grant)
        guard.initialize(second_root, second_grant_path, now=NOW)

        original = guard._replay_locked
        mutation_errors: list[BaseException] = []
        replay_count = 0

        def mutate_first_after_its_replay(root: Path, **kwargs):
            nonlocal replay_count
            summary = original(root, **kwargs)
            replay_count += 1
            if replay_count == 1:
                try:
                    guard.close(self.root, "must remain locked", now=NOW)
                except BaseException as exc:
                    mutation_errors.append(exc)
            return summary

        with mock.patch.object(
            guard, "_replay_locked", side_effect=mutate_first_after_its_replay
        ):
            snapshots = guard.replay_snapshots([self.root, second_root], now=NOW)

        self.assertEqual(len(snapshots), 2)
        self.assertEqual(len(mutation_errors), 1)
        self.assertIsInstance(mutation_errors[0], guard.GuardError)
        self.assertIn("locked", str(mutation_errors[0]))

    def test_replay_snapshot_rejects_authority_drift_during_replay(self):
        self.initialize()
        original = guard._replay_locked

        def mutate_after_replay(root: Path, **kwargs):
            summary = original(root, **kwargs)
            grant_path = root / "grant.json"
            grant_path.write_bytes(grant_path.read_bytes() + b" ")
            return summary

        with (
            mock.patch.object(guard, "_replay_locked", side_effect=mutate_after_replay),
            self.assertRaisesRegex(
                guard.GuardError, "execution authority changed while taking replay snapshot"
            ),
        ):
            guard.replay_snapshot(self.root, now=NOW)

    def test_replay_timestamp_cannot_precede_ledger_tail(self):
        self.initialize()
        before_tail = NOW - timedelta(microseconds=1)

        for replay_call in (
            lambda: guard.replay(self.root, now=before_tail),
            lambda: guard.replay_snapshot(self.root, now=before_tail),
        ):
            with self.subTest(api=replay_call):
                with self.assertRaisesRegex(
                    guard.GuardError, "generated_at.*ledger tail|replay time.*ledger tail"
                ):
                    replay_call()

    def test_replay_timestamp_cannot_be_unreasonably_far_in_the_future(self):
        self.initialize()
        future = datetime.now(timezone.utc) + timedelta(
            seconds=guard.MAX_REPLAY_CLOCK_SKEW_SECONDS + 60
        )

        for replay_call in (
            lambda: guard.replay(self.root, now=future),
            lambda: guard.replay_snapshot(self.root, now=future),
        ):
            with self.subTest(api=replay_call):
                with self.assertRaisesRegex(
                    guard.GuardError, "replay time is unreasonably far in the future"
                ):
                    replay_call()

    def test_replay_timestamp_allows_only_bounded_clock_skew(self):
        current = datetime.now(timezone.utc)
        self.grant["authorized_at"] = guard._now_text(current - timedelta(minutes=1))
        self.grant["expires_at"] = guard._now_text(current + timedelta(minutes=1))
        write_json(self.grant_path, self.grant)
        guard.initialize(self.root, self.grant_path, now=current)

        replayed = guard.replay(
            self.root,
            now=datetime.now(timezone.utc)
            + timedelta(seconds=guard.MAX_REPLAY_CLOCK_SKEW_SECONDS - 1),
        )
        self.assertEqual(replayed["ledger_last_seq"], 1)

    def test_write_summary_cannot_race_a_reservation_append(self):
        self.initialize()
        fingerprint_ready = threading.Event()
        allow_replay = threading.Event()
        original = guard._replay_fingerprint

        def paused(root: Path):
            value = original(root)
            fingerprint_ready.set()
            allow_replay.wait(5)
            return value

        errors: list[BaseException] = []

        def writer() -> None:
            try:
                guard.replay(self.root, write_summary=True, now=NOW)
            except BaseException as exc:  # pragma: no cover - assertion reports it
                errors.append(exc)

        def reserve_writer() -> None:
            try:
                guard.reserve(self.root, "run-1", "attempt-1", "E01", now=NOW)
            except BaseException as exc:  # pragma: no cover - assertion reports it
                errors.append(exc)

        with mock.patch.object(guard, "_replay_fingerprint", side_effect=paused):
            thread = threading.Thread(target=writer)
            thread.start()
            self.assertTrue(fingerprint_ready.wait(5))
            reserve_thread = threading.Thread(target=reserve_writer)
            reserve_thread.start()
            allow_replay.set()
            thread.join(10)
            reserve_thread.join(10)
        self.assertFalse(errors)
        fresh = guard.replay(self.root, now=NOW)
        disk = json.loads((self.root / "spend-summary.json").read_text())
        self.assertEqual(disk, fresh)
        self.assertEqual(disk["ledger_last_seq"], 2)

    def test_initialize_and_replay_are_deterministic(self):
        summary = self.initialize()
        self.assertEqual(summary["charged"], {"calls": 0, "total_tokens": 0, "wall_seconds": 0})
        (self.root / "spend-summary.json").unlink()
        replayed = guard.replay(self.root, write_summary=True, now=NOW)
        self.assertEqual(replayed, json.loads((self.root / "spend-summary.json").read_text()))

    def test_reservation_is_per_episode_and_conservative(self):
        self.initialize()
        first = guard.reserve(self.root, "run-1", "attempt-1", "E01", now=NOW)
        self.assertEqual(first["charged"], {"calls": 1, "total_tokens": 100, "wall_seconds": 60})
        second = guard.reserve(self.root, "run-1", "attempt-2", "E02", now=NOW)
        self.assertEqual(second["charged"]["calls"], 2)
        with self.assertRaisesRegex(guard.GuardError, "cannot be reserved more than once"):
            guard.reserve(self.root, "run-1", "attempt-3", "E01", now=NOW)

    def test_default_episode_id_preserves_api_compatibility(self):
        self.grant["authorized_calls"][0]["episode_id"] = guard.DEFAULT_EPISODE_ID
        write_json(self.grant_path, self.grant)
        self.initialize()
        summary = guard.reserve(self.root, "run-1", "attempt-1", now=NOW)
        self.assertEqual(summary["in_doubt_attempt_ids"], ["attempt-1"])

    def test_two_processes_cannot_consume_one_episode_twice(self):
        self.initialize()
        context = multiprocessing.get_context("spawn")
        queue = context.Queue()
        processes = [
            context.Process(
                target=reserve_worker,
                args=(str(self.root), "run-1", f"attempt-{index}", "E01", queue),
            )
            for index in (1, 2)
        ]
        for process in processes:
            process.start()
        results = [queue.get(timeout=10) for _ in processes]
        for process in processes:
            process.join(10)
            self.assertEqual(process.exitcode, 0)
        self.assertEqual(sum(item[0] == "ok" for item in results), 1)

    def test_evidence_is_required_and_stored_before_settlement_record(self):
        self.initialize()
        guard.reserve(self.root, "run-1", "attempt-1", "E01", now=NOW)
        receipt, evidence = self.receipt_and_evidence("run-1", "attempt-1")
        with self.assertRaisesRegex(guard.GuardError, "requires a pre-existing evidence"):
            guard.settle(self.root, receipt, evidence.with_name("missing.json"), now=SETTLED)
        summary = guard.settle(self.root, receipt, evidence, now=SETTLED)
        self.assertEqual(summary["settled_call_ids"], ["run-1:E01"])
        record = json.loads(sorted((self.root / "ledger").glob("*.json"))[-1].read_text())
        self.assertEqual(record["kind"], "call_settled")
        self.assertTrue((self.root / "evidence" / record["payload"]["evidence_path"]).is_file())

    def test_evidence_hash_and_referenced_file_drift_fail_closed(self):
        self.initialize()
        guard.reserve(self.root, "run-1", "attempt-1", "E01", now=NOW)
        receipt, evidence = self.receipt_and_evidence("run-1", "attempt-1")
        (evidence.parent / "workspace-final.json").write_bytes(b"changed\n")
        with self.assertRaisesRegex(guard.GuardError, "evidence file hash drifted"):
            guard.settle(self.root, receipt, evidence, now=SETTLED)
        self.assertEqual(list((self.root / "receipts").iterdir()), [])

    def test_full_cli_usage_is_required_and_total_tokens_is_consistent(self):
        self.initialize()
        guard.reserve(self.root, "run-1", "attempt-1", "E01", now=NOW)
        receipt, evidence = self.receipt_and_evidence("run-1", "attempt-1")
        value = json.loads(receipt.read_text())
        value["usage"].pop("reasoning_output_tokens")
        write_json(receipt, value)
        with self.assertRaisesRegex(guard.GuardError, "reasoning_output_tokens"):
            guard.settle(self.root, receipt, evidence, now=SETTLED)
        value["usage"]["reasoning_output_tokens"] = 10
        value["usage"]["total_tokens"] = 999
        write_json(receipt, value)
        with self.assertRaisesRegex(guard.GuardError, "total_tokens disagrees"):
            guard.settle(self.root, receipt, evidence, now=SETTLED)

    def test_settlement_never_releases_reserved_budget(self):
        self.initialize()
        guard.reserve(self.root, "run-1", "attempt-1", "E01", now=NOW)
        summary = self.settle("run-1", "attempt-1", input_tokens=20, output_tokens=20)
        self.assertEqual(summary["settled"], {"calls": 1, "total_tokens": 40, "wall_seconds": 10})
        self.assertEqual(summary["charged"], {"calls": 1, "total_tokens": 100, "wall_seconds": 60})
        self.assertEqual(summary["remaining"], {"calls": 2, "total_tokens": 200, "wall_seconds": 120})

    def test_overspend_is_recorded_as_breach(self):
        self.initialize()
        guard.reserve(self.root, "run-1", "attempt-1", "E01", now=NOW)
        summary = self.settle(
            "run-1", "attempt-1", input_tokens=101, output_tokens=11, seconds=61
        )
        self.assertEqual(summary["status"], "breached")
        self.assertEqual(summary["breaches"], ["attempt-1"])

    def test_provider_request_id_is_unique_across_receipts(self):
        self.initialize()
        guard.reserve(self.root, "run-1", "attempt-1", "E01", now=NOW)
        guard.reserve(self.root, "run-1", "attempt-2", "E02", now=NOW)
        first, first_evidence = self.receipt_and_evidence(
            "run-1", "attempt-1", "E01", request_id="same-request"
        )
        guard.settle(self.root, first, first_evidence, now=SETTLED)
        second, second_evidence = self.receipt_and_evidence(
            "run-1", "attempt-2", "E02", request_id="same-request"
        )
        with self.assertRaisesRegex(guard.GuardError, "provider request IDs"):
            guard.settle(self.root, second, second_evidence, now=SETTLED)

    def test_preregistered_interruption_charges_reservation_without_settlement(self):
        self.grant["experiment_id"] = "create-loop-v1-v2-real-task-pilot-2026"
        self.grant["authorized_calls"] = [
            {"run_id": "PL-S1-P01-v1-E01", "episode_id": "E01"}
        ]
        self.grant["limits"]["total"]["max_calls"] = 1
        write_json(self.grant_path, self.grant)
        self.initialize()
        guard.reserve(self.root, "PL-S1-P01-v1-E01", "attempt-s1", "E01", now=NOW)
        summary = guard.interrupt(
            self.root, *self.interruption("PL-S1-P01-v1-E01", "attempt-s1"), now=NOW
        )
        self.assertEqual(summary["settled"], {"calls": 0, "total_tokens": 0, "wall_seconds": 0})
        self.assertEqual(summary["charged"], {"calls": 1, "total_tokens": 100, "wall_seconds": 60})
        self.assertEqual(summary["in_doubt_attempt_ids"], [])
        self.assertEqual(summary["interrupted_attempt_ids"], ["attempt-s1"])
        record = json.loads(sorted((self.root / "ledger").glob("*.json"))[-1].read_text())
        self.assertEqual(record["kind"], "call_interrupted")
        self.assertEqual(record["payload"]["reason"], guard.INTERRUPTION_REASON)

    def test_interruption_cannot_close_timeout_or_non_s1_reservations(self):
        self.grant["experiment_id"] = "create-loop-v1-v2-real-task-pilot-2026"
        write_json(self.grant_path, self.grant)
        self.initialize()
        guard.reserve(self.root, "run-1", "attempt-1", "E01", now=NOW)
        path, evidence = self.interruption("PL-S1-P01-v1-E01", "attempt-1")
        with self.assertRaisesRegex(guard.GuardError, "does not match its reservation"):
            guard.interrupt(self.root, path, evidence, now=NOW)
        self.assertEqual(guard.replay(self.root, now=NOW)["in_doubt_attempt_ids"], ["attempt-1"])

    def test_interruption_evidence_drift_fails_closed(self):
        self.grant["experiment_id"] = "create-loop-v1-v2-real-task-pilot-2026"
        self.grant["authorized_calls"] = [
            {"run_id": "PL-S1-P01-v2-E01", "episode_id": "E01"}
        ]
        self.grant["limits"]["total"]["max_calls"] = 1
        write_json(self.grant_path, self.grant)
        self.initialize()
        guard.reserve(self.root, "PL-S1-P01-v2-E01", "attempt-s1", "E01", now=NOW)
        path, evidence = self.interruption("PL-S1-P01-v2-E01", "attempt-s1")
        (path.parent / "termination-fact.json").write_bytes(b"changed\n")
        with self.assertRaisesRegex(guard.GuardError, "interruption file hash drifted"):
            guard.interrupt(self.root, path, evidence, now=NOW)

    def test_replay_rejects_interruption_evidence_ledger_hash_drift(self):
        self.grant["experiment_id"] = "create-loop-v1-v2-real-task-pilot-2026"
        self.grant["authorized_calls"] = [
            {"run_id": "PL-S1-P01-v1-E01", "episode_id": "E01"}
        ]
        self.grant["limits"]["total"]["max_calls"] = 1
        write_json(self.grant_path, self.grant)
        self.initialize()
        guard.reserve(self.root, "PL-S1-P01-v1-E01", "attempt-s1", "E01", now=NOW)
        interruption, evidence = self.interruption(
            "PL-S1-P01-v1-E01", "attempt-s1"
        )
        guard.interrupt(self.root, interruption, evidence, now=NOW)
        record_path = sorted((self.root / "ledger").glob("*.json"))[-1]
        record = json.loads(record_path.read_text())
        stored = self.root / "evidence" / record["payload"]["interruption_evidence_path"]
        evidence_value = json.loads(stored.read_text())
        self.assertEqual(
            next(
                item["path"]
                for item in evidence_value["files"]
                if item["role"] == "controller_interruption"
            ),
            "controller-interruption.json",
        )
        record["payload"]["interruption_evidence_sha256"] = "0" * 64
        record_path.write_bytes(guard.canonical_bytes(record))
        with self.assertRaisesRegex(
            guard.GuardError,
            "ledger tail drifted|interruption evidence manifest hash drifted",
        ):
            guard.replay(self.root, now=NOW)

    def test_grant_and_receipt_bind_role_cli_provider_and_model(self):
        self.initialize()
        guard.reserve(self.root, "run-1", "attempt-1", "E01", now=NOW)
        receipt, evidence = self.receipt_and_evidence("run-1", "attempt-1")
        original = json.loads(receipt.read_text())
        for field, replacement in (
            ("role", "reviewer"),
            ("model", "other-model"),
            ("cli_identity", {**self.grant["cli_identity"], "sha256": "9" * 64}),
            ("provider_profile", {**self.grant["provider_profile"], "sha256": "8" * 64}),
        ):
            mutated = json.loads(json.dumps(original))
            mutated[field] = replacement
            write_json(receipt, mutated)
            expected = "evidence role drifted|receipt role drifted" if field == "role" else f"receipt {field} drifted"
            with self.assertRaisesRegex(guard.GuardError, expected):
                guard.settle(self.root, receipt, evidence, now=SETTLED)
        self.assertEqual(list((self.root / "receipts").iterdir()), [])

    def test_hash_chain_and_durable_anchor_fail_closed(self):
        self.initialize()
        guard.reserve(self.root, "run-1", "attempt-1", "E01", now=NOW)
        record = sorted((self.root / "ledger").glob("*.json"))[-1]
        value = json.loads(record.read_text())
        value["previous_record_sha256"] = "9" * 64
        write_json(record, value)
        with self.assertRaisesRegex(guard.GuardError, "hash chain|durable anchor"):
            guard.replay(self.root, now=NOW)

    def test_revocation_and_close_preserve_in_doubt_safety(self):
        self.initialize()
        guard.reserve(self.root, "run-1", "attempt-1", "E01", now=NOW)
        summary = guard.revoke(self.root, "stop", now=NOW)
        self.assertEqual(summary["status"], "revoked")
        with self.assertRaisesRegex(guard.GuardError, "in-doubt"):
            guard.close(self.root, "cannot close", now=NOW)
        self.settle("run-1", "attempt-1")
        closed = guard.close(self.root, "accounting complete", now=SETTLED)
        self.assertEqual(closed["status"], "closed")

    def test_execution_root_binding_and_expiry_fail_closed(self):
        other = self.base / "other"
        with self.assertRaisesRegex(guard.GuardError, "different execution root"):
            guard.initialize(other, self.grant_path, now=NOW)
        self.initialize()
        with self.assertRaisesRegex(guard.GuardError, "not valid"):
            guard.reserve(
                self.root,
                "run-1",
                "attempt-1",
                "E01",
                now=datetime(2026, 8, 7, tzinfo=timezone.utc),
            )

    @unittest.skipUnless(os.name == "nt", "Windows junction semantics")
    def test_receipt_store_junction_is_rejected(self):
        self.initialize()
        receipts = self.root / "receipts"
        receipts.rmdir()
        outside = self.base / "outside"
        outside.mkdir()
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(receipts), str(outside)],
            check=True,
            capture_output=True,
        )
        try:
            with self.assertRaisesRegex(guard.GuardError, "receipt root"):
                guard.replay(self.root, now=NOW)
        finally:
            subprocess.run(["cmd", "/c", "rmdir", str(receipts)], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
