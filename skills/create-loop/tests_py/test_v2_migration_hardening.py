from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path, PurePosixPath
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import migrate_v1  # noqa: E402


def legacy_node(
    node_id: str,
    *,
    requires: list[str] | None = None,
    kind: str = "milestone",
    gate_kind: str = "test",
    subgraph: dict | None = None,
) -> dict:
    return {
        "id": node_id,
        "kind": kind,
        "title": f"Work for {node_id}",
        "requires": requires or [],
        "produces": [],
        "postconditions": [f"{node_id} is verified."],
        "gate": {"kind": gate_kind, "rubric": None},
        "subgraph": subgraph,
        "child_loops": [],
    }


def write_source(
    root: Path,
    nodes: list[dict],
    *,
    states: dict[str, str] | None = None,
    entries: list[dict] | None = None,
    events: list[dict] | None = None,
) -> None:
    root.mkdir()
    node_states = states or {}

    def apply_statuses(items: list[dict]) -> None:
        for node in items:
            node.setdefault("status", node_states.get(node["id"], "pending"))
            subgraph = node.get("subgraph")
            if isinstance(subgraph, dict):
                apply_statuses(subgraph.get("nodes", []))

    apply_statuses(nodes)
    plan = {
        "schema_version": "1.0.0",
        "plan_id": "legacy-plan",
        "plan_version": 1,
        "created": "2026-07-31T00:00:00Z",
        "goal": "Migrate the legacy Loop safely.",
        "true_intent": "Preserve the legacy graph and recovery facts.",
        "success_criteria": [
            {"id": "SC1", "statement": "The migrated Loop is recoverable.", "measurable": True}
        ],
        "failure_criteria": ["Migration loses a mapped node."],
        "non_goals": [],
        "constraints": [],
        "nodes": nodes,
    }
    (root / "loop.plan.yaml").write_text(
        yaml.safe_dump(plan, sort_keys=False), encoding="utf-8", newline="\n"
    )
    (root / "loop.meta.yaml").write_text(
        yaml.safe_dump({"loop_id": "L901"}, sort_keys=False), encoding="utf-8", newline="\n"
    )
    (root / "checkpoint.yaml").write_text(
        yaml.safe_dump(
            {
                "node_states": node_states,
                "event_log_ref": "./event_log.jsonl",
                "last_event_seq": events[-1]["seq"] if events else 0,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
        newline="\n",
    )
    (root / "evidence.ledger.yaml").write_text(
        yaml.safe_dump({"entries": entries or []}, sort_keys=False),
        encoding="utf-8",
        newline="\n",
    )
    with (root / "event_log.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for event in events or []:
            handle.write(json.dumps(event, sort_keys=True) + "\n")


def run_cli(source: Path, destination: Path, *, dry_run: bool) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPTS / "migrate_v1.py"), str(source), str(destination)]
    if dry_run:
        command.append("--dry-run")
    return subprocess.run(command, text=True, capture_output=True, check=False)


def staging_paths(destination: Path) -> list[Path]:
    return list(destination.parent.glob(f".{destination.name}.migrate-*"))


class MigrationHardeningTests(unittest.TestCase):
    def test_source_snapshot_accepts_ordinary_files_and_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            write_source(source, [legacy_node("Node One")], states={"Node One": "pending"})
            nested = source / "artifacts" / "nested"
            nested.mkdir(parents=True)
            (nested / "result.txt").write_text("ok\n", encoding="utf-8", newline="\n")

            snapshot, hashes = migrate_v1.source_snapshot(source)

            self.assertEqual(set(snapshot), set(hashes))
            self.assertEqual(snapshot["artifacts/nested/result.txt"], b"ok\n")
            self.assertEqual(hashes["artifacts/nested/result.txt"], hashlib.sha256(b"ok\n").hexdigest())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support is unavailable")
    def test_source_root_symlink_is_rejected_before_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            real_source = parent / "real-source"
            source_link = parent / "source-link"
            destination = parent / "migrated"
            write_source(real_source, [legacy_node("Node One")], states={"Node One": "pending"})
            try:
                source_link.symlink_to(real_source, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlink creation is unavailable: {exc}")

            result = run_cli(source_link, destination, dry_run=True)

            self.assertEqual(result.returncode, 1)
            self.assertIn("source root must not be a symlink or reparse point", result.stderr)
            self.assertFalse(destination.exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support is unavailable")
    def test_source_file_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            source = parent / "source"
            outside = parent / "outside.txt"
            destination = parent / "migrated"
            write_source(source, [legacy_node("Node One")], states={"Node One": "pending"})
            outside.write_text("outside\n", encoding="utf-8", newline="\n")
            try:
                (source / "linked.txt").symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"file symlink creation is unavailable: {exc}")

            result = run_cli(source, destination, dry_run=True)

            self.assertEqual(result.returncode, 1)
            self.assertIn("source member must not be a symlink or reparse point", result.stderr)
            self.assertFalse(destination.exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support is unavailable")
    def test_source_directory_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            source = parent / "source"
            outside = parent / "outside"
            destination = parent / "migrated"
            write_source(source, [legacy_node("Node One")], states={"Node One": "pending"})
            outside.mkdir()
            try:
                (source / "linked-dir").symlink_to(outside, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlink creation is unavailable: {exc}")

            result = run_cli(source, destination, dry_run=True)

            self.assertEqual(result.returncode, 1)
            self.assertIn("source member must not be a symlink or reparse point", result.stderr)
            self.assertFalse(destination.exists())

    @unittest.skipUnless(os.name == "nt", "Windows junction coverage")
    def test_source_root_junction_is_rejected_before_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            real_source = parent / "real-source"
            source_junction = parent / "source-junction"
            destination = parent / "migrated"
            write_source(real_source, [legacy_node("Node One")], states={"Node One": "pending"})
            created = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(source_junction), str(real_source)],
                check=False,
                capture_output=True,
                text=True,
            )
            if created.returncode != 0:
                self.skipTest(f"junction creation is unavailable: {created.stderr}")
            try:
                result = run_cli(source_junction, destination, dry_run=True)
                self.assertEqual(result.returncode, 1)
                self.assertIn("source root must not be a symlink or reparse point", result.stderr)
                self.assertFalse(destination.exists())
            finally:
                subprocess.run(["cmd", "/c", "rmdir", str(source_junction)], check=True, capture_output=True, text=True)

    @unittest.skipUnless(os.name == "nt", "Windows junction coverage")
    def test_source_directory_junction_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            source = parent / "source"
            outside = parent / "outside"
            junction = source / "linked-junction"
            destination = parent / "migrated"
            write_source(source, [legacy_node("Node One")], states={"Node One": "pending"})
            outside.mkdir()
            created = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
                check=False,
                capture_output=True,
                text=True,
            )
            if created.returncode != 0:
                self.skipTest(f"junction creation is unavailable: {created.stderr}")
            try:
                result = run_cli(source, destination, dry_run=True)
                self.assertEqual(result.returncode, 1)
                self.assertIn("source member must not be a symlink or reparse point", result.stderr)
                self.assertFalse(destination.exists())
            finally:
                subprocess.run(["cmd", "/c", "rmdir", str(junction)], check=True, capture_output=True, text=True)

    def test_malformed_goal_authority_fields_fail_closed(self) -> None:
        cases = (
            ("missing-goal", lambda plan: plan.pop("goal"), "authority field 'goal'"),
            ("object-intent", lambda plan: plan.__setitem__("true_intent", {"bad": "shape"}), "authority field 'true_intent'"),
            ("string-non-goals", lambda plan: plan.__setitem__("non_goals", "abc"), "authority field 'non_goals'"),
            ("string-constraints", lambda plan: plan.__setitem__("constraints", "not-list"), "authority field 'constraints'"),
            ("empty-criteria", lambda plan: plan.__setitem__("success_criteria", []), "success_criteria must be non-empty"),
            ("bad-criterion", lambda plan: plan.__setitem__("success_criteria", [{"id": "SC1"}]), "must contain non-empty string id and statement"),
        )
        for label, mutate, error in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp:
                parent = Path(temp)
                source = parent / "source"
                destination = parent / "migrated"
                write_source(source, [legacy_node("Node One")], states={"Node One": "pending"})
                plan_path = source / "loop.plan.yaml"
                plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
                mutate(plan)
                plan_path.write_text(
                    yaml.safe_dump(plan, sort_keys=False), encoding="utf-8", newline="\n"
                )

                result = run_cli(source, destination, dry_run=True)

                self.assertEqual(result.returncode, 1)
                self.assertIn(error, result.stderr)
                self.assertFalse(destination.exists())

    def test_missing_declared_event_log_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            source = parent / "source"
            destination = parent / "migrated"
            write_source(source, [legacy_node("Node One")], states={"Node One": "running"})
            (source / "event_log.jsonl").unlink()

            result = run_cli(source, destination, dry_run=True)

            self.assertEqual(result.returncode, 1)
            self.assertIn("required source file is missing: event_log.jsonl", result.stderr)
            self.assertFalse(destination.exists())

    def test_event_projection_must_match_checkpoint_tail(self) -> None:
        events = [
            {
                "seq": 0,
                "node_id": "Node One",
                "ts": "2026-07-31T00:01:00Z",
                "kind": "pre_effect",
                "from_status": "ready",
                "to_status": "running",
                "effect_id": "deploy",
                "attempt_id": "attempt-1",
                "idempotency_key": "deploy-attempt-1",
            },
            {
                "seq": 1,
                "node_id": "Node One",
                "ts": "2026-07-31T00:02:00Z",
                "kind": "post_effect",
                "from_status": "running",
                "to_status": "verifying",
                "effect_id": "deploy",
                "attempt_id": "attempt-1",
                "outcome": "ok",
            },
        ]
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            source = parent / "source"
            destination = parent / "migrated"
            write_source(
                source,
                [{**legacy_node("Node One"), "status": "running"}],
                states={"Node One": "running"},
                events=events,
            )

            result = run_cli(source, destination, dry_run=True)

            self.assertEqual(result.returncode, 1)
            self.assertIn("event-log projection disagrees with checkpoint", result.stderr)
            self.assertFalse(destination.exists())

    def test_exact_legacy_effect_pair_is_preserved_as_closed_audit_fact(self) -> None:
        events = [
            {
                "seq": 0,
                "node_id": "Node One",
                "ts": "2026-07-31T00:01:00Z",
                "kind": "pre_effect",
                "from_status": "ready",
                "to_status": "running",
                "intent": "Deploy the legacy artifact.",
                "idempotency_key": "deploy-attempt-1",
                "effect_id": "deploy",
                "attempt_id": "attempt-1",
            },
            {
                "seq": 1,
                "node_id": "Node One",
                "ts": "2026-07-31T00:02:00Z",
                "kind": "post_effect",
                "from_status": "running",
                "to_status": "verifying",
                "effect_id": "deploy",
                "attempt_id": "attempt-1",
                "outcome": "ok",
                "result_hash": "sha256:legacy-deploy-result",
            },
        ]
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            source = parent / "source"
            destination = parent / "migrated"
            write_source(
                source,
                [legacy_node("Node One")],
                states={"Node One": "verifying"},
                events=events,
            )

            result = run_cli(source, destination, dry_run=False)

            self.assertEqual(result.returncode, 0, result.stderr)
            plan = json.loads((destination / "plans" / "plan-v1.json").read_text(encoding="utf-8"))
            records = [
                json.loads(line)
                for line in (destination / "journal.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            resume = json.loads((destination / "resume.json").read_text(encoding="utf-8"))
            closed = records[0]["payload"]["closed_effects"]

            self.assertEqual(plan["control"]["modules"], [])
            self.assertEqual(len(closed), 1)
            self.assertEqual(closed[0]["effect_id"], "deploy")
            self.assertEqual(closed[0]["attempt_id"], "attempt-1")
            self.assertEqual(closed[0]["node_id"], "Node-One")
            self.assertEqual(closed[0]["outcome"], "succeeded")
            self.assertEqual(resume["projection"]["in_doubt_effect_ids"], [])

    def test_unmatched_idempotent_legacy_effect_is_preserved_in_doubt(self) -> None:
        events = [
            {
                "seq": 0,
                "node_id": "Node One",
                "ts": "2026-07-31T00:01:00Z",
                "kind": "pre_effect",
                "from_status": "ready",
                "to_status": "running",
                "intent": "Deploy the legacy artifact.",
                "idempotency_key": "deploy-attempt-1",
                "effect_id": "deploy",
                "attempt_id": "attempt-1",
            }
        ]
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            source = parent / "source"
            destination = parent / "migrated"
            write_source(
                source,
                [legacy_node("Node One")],
                states={"Node One": "running"},
                events=events,
            )

            result = run_cli(source, destination, dry_run=False)

            self.assertEqual(result.returncode, 0, result.stderr)
            resume = json.loads((destination / "resume.json").read_text(encoding="utf-8"))
            report = json.loads((destination / "migration-report.json").read_text(encoding="utf-8"))
            self.assertEqual(resume["projection"]["in_doubt_effect_ids"], ["deploy:attempt-1"])
            self.assertTrue(any("in-doubt legacy effect deploy:attempt-1" in item for item in report["warnings"]))
            records = [
                json.loads(line)
                for line in (destination / "journal.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual([record["ts"] for record in records], sorted(record["ts"] for record in records))

            from project_loop import project

            records.append(
                {
                    "schema_version": "2.0",
                    "seq": records[-1]["seq"] + 1,
                    "record_id": "effect-post-after-import",
                    "ts": records[-1]["ts"],
                    "kind": "effect_post",
                    "actor": {"type": "tool", "id": "recovery-check"},
                    "plan_version": 1,
                    "node_id": "Node-One",
                    "payload": {
                        "effect_id": "deploy",
                        "attempt_id": "attempt-1",
                        "outcome": "succeeded",
                        "observed_postcondition": "The imported deployment is present.",
                        "result_ref": "tool:recovery-check",
                    },
                }
            )
            with (destination / "journal.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
                for record in records:
                    handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
            self.assertEqual(project(destination)["projection"]["in_doubt_effect_ids"], [])

    def test_ambiguous_or_non_idempotent_legacy_effect_fails_closed(self) -> None:
        cases = (
            (
                "ambiguous",
                [
                    {
                        "seq": 0,
                        "node_id": "Node One",
                        "ts": "2026-07-31T00:01:00Z",
                        "kind": "pre_effect",
                        "from_status": "ready",
                        "to_status": "running",
                        "intent": "First legacy effect.",
                        "idempotency_key": "first",
                    },
                    {
                        "seq": 1,
                        "node_id": "Node One",
                        "ts": "2026-07-31T00:02:00Z",
                        "kind": "note",
                    },
                    {
                        "seq": 2,
                        "node_id": "Node One",
                        "ts": "2026-07-31T00:03:00Z",
                        "kind": "post_effect",
                        "from_status": "running",
                        "to_status": "verifying",
                        "idempotency_key": "first",
                        "outcome": "ok",
                    },
                ],
                "LEGACY-EFFECT-AMBIGUOUS",
            ),
            (
                "orphan-post",
                [
                    {
                        "seq": 0,
                        "node_id": "Node One",
                        "ts": "2026-07-31T00:01:00Z",
                        "kind": "post_effect",
                        "from_status": "running",
                        "to_status": "verifying",
                        "effect_id": "deploy",
                        "attempt_id": "attempt-1",
                        "outcome": "ok",
                    }
                ],
                "EFFECT-PAIR",
            ),
            (
                "non-idempotent",
                [
                    {
                        "seq": 0,
                        "node_id": "Node One",
                        "ts": "2026-07-31T00:01:00Z",
                        "kind": "pre_effect",
                        "from_status": "ready",
                        "to_status": "running",
                        "intent": "Charge an external account.",
                        "effect_id": "charge",
                        "attempt_id": "attempt-1",
                    }
                ],
                "IN-DOUBT-NONIDEMPOTENT",
            ),
            (
                "state-incompatible",
                [
                    {
                        "seq": 0,
                        "node_id": "Node One",
                        "ts": "2026-07-31T00:01:00Z",
                        "kind": "pre_effect",
                        "from_status": "ready",
                        "to_status": "running",
                        "intent": "Deploy the legacy artifact.",
                        "idempotency_key": "deploy-attempt-1",
                        "effect_id": "deploy",
                        "attempt_id": "attempt-1",
                    }
                ],
                "event-log projection disagrees with checkpoint",
            ),
        )
        for case_name, events, error in cases:
            with self.subTest(case=case_name), tempfile.TemporaryDirectory() as temp:
                parent = Path(temp)
                source = parent / "source"
                write_source(
                    source,
                    [legacy_node("Node One")],
                    states={"Node One": "completed" if case_name == "state-incompatible" else "running"},
                    events=events,
                )

                for dry_run, name in ((True, "dry"), (False, "real")):
                    destination = parent / name
                    result = run_cli(source, destination, dry_run=dry_run)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn(error, result.stderr)
                    self.assertFalse(destination.exists())
                    self.assertEqual(staging_paths(destination), [])

    def test_invalid_legacy_event_chain_fails_before_effect_import(self) -> None:
        events = [
            {
                "seq": 1,
                "node_id": "Node One",
                "ts": "2026-07-31T00:01:00Z",
                "kind": "pre_effect",
                "from_status": "ready",
                "to_status": "running",
                "intent": "First attempt.",
                "idempotency_key": "attempt-1",
                "effect_id": "deploy",
                "attempt_id": "attempt-1",
            },
            {
                "seq": 1,
                "node_id": "Node One",
                "ts": "2026-07-31T00:02:00Z",
                "kind": "post_effect",
                "from_status": "running",
                "to_status": "verifying",
                "effect_id": "deploy",
                "attempt_id": "attempt-1",
                "outcome": "ok",
            },
        ]
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            source = parent / "source"
            destination = parent / "migrated"
            write_source(
                source,
                [legacy_node("Node One")],
                states={"Node One": "verifying"},
                events=events,
            )

            result = run_cli(source, destination, dry_run=True)

            self.assertEqual(result.returncode, 1)
            self.assertIn("legacy event_log.jsonl is invalid", result.stderr)
            self.assertIn("EVENTLOG-SEQ", result.stderr)
            self.assertFalse(destination.exists())

    def test_unmatched_effect_timestamp_must_be_rfc3339(self) -> None:
        events = [
            {
                "seq": 0,
                "node_id": "Node One",
                "ts": "not-a-time",
                "kind": "pre_effect",
                "from_status": "ready",
                "to_status": "running",
                "intent": "Deploy the legacy artifact.",
                "idempotency_key": "deploy-attempt-1",
                "effect_id": "deploy",
                "attempt_id": "attempt-1",
            }
        ]
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            source = parent / "source"
            destination = parent / "migrated"
            write_source(
                source,
                [legacy_node("Node One")],
                states={"Node One": "running"},
                events=events,
            )

            result = run_cli(source, destination, dry_run=True)

            self.assertEqual(result.returncode, 1)
            self.assertRegex(result.stderr, r"(?:timestamp is not|must be a valid) RFC 3339")
            self.assertFalse(destination.exists())

    def test_legal_posix_and_windows_relative_outputs_are_preserved(self) -> None:
        outputs = [
            "artifacts/result.txt",
            r"reports\summary.txt",
            "C-folder/output.txt",
            ".hidden/output.txt",
        ]
        node = legacy_node("Node One")
        node["produces"] = outputs
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            source = parent / "source"
            destination = parent / "migrated"
            write_source(source, [node], states={"Node One": "pending"})

            result = run_cli(source, destination, dry_run=False)

            self.assertEqual(result.returncode, 0, result.stderr)
            plan = json.loads(
                (destination / "plans" / "plan-v1.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                [item["path"] for item in plan["nodes"][0]["outputs"]],
                [PurePosixPath(item.replace("\\", "/")).as_posix() for item in outputs],
            )

    def test_windows_reserved_device_outputs_are_rejected(self) -> None:
        for output in ("CON", "reports/CON.txt", "aux.md", "COM1.log", "lpt9"):
            with self.subTest(output=output), tempfile.TemporaryDirectory() as temp:
                node = legacy_node("Node One")
                node["produces"] = [output]
                parent = Path(temp)
                source = parent / "source"
                destination = parent / "migrated"
                write_source(source, [node], states={"Node One": "pending"})

                result = run_cli(source, destination, dry_run=True)

                self.assertEqual(result.returncode, 1)
                self.assertIn("produces[0] must be a relative path", result.stderr)
                self.assertFalse(destination.exists())

    def test_windows_unicode_distinct_outputs_keep_distinct_owners(self) -> None:
        pairs = (
            ("artifacts/straße.txt", "artifacts/strasse.txt"),
            (f"artifacts/{chr(0x1F600)}.txt", f"artifacts/{chr(0x1F600)}.txu"),
        )
        for first_path, second_path in pairs:
            with self.subTest(first=first_path, second=second_path), tempfile.TemporaryDirectory() as temp:
                first = legacy_node("Producer One")
                second = legacy_node("Producer Two")
                first["produces"] = [first_path]
                second["produces"] = [second_path]
                parent = Path(temp)
                source = parent / "source"
                destination = parent / "migrated"
                write_source(
                    source,
                    [first, second],
                    states={"Producer One": "pending", "Producer Two": "pending"},
                )

                result = run_cli(source, destination, dry_run=False)

                self.assertEqual(result.returncode, 0, result.stderr)
                plan = json.loads((destination / "plans" / "plan-v1.json").read_text(encoding="utf-8"))
                self.assertEqual(
                    [[item["path"] for item in node["outputs"]] for node in plan["nodes"]],
                    [[first_path], [second_path]],
                )

    def test_duplicate_legacy_output_keeps_one_owner_and_records_later_producer(self) -> None:
        first = legacy_node("Producer One")
        second = legacy_node("Producer Two")
        first["produces"] = ["artifacts/result.txt"]
        second["produces"] = ["artifacts/result.txt"]
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            source = parent / "source"
            destination = parent / "migrated"
            write_source(
                source,
                [first, second],
                states={"Producer One": "pending", "Producer Two": "pending"},
            )

            result = run_cli(source, destination, dry_run=False)

            self.assertEqual(result.returncode, 0, result.stderr)
            plan = json.loads((destination / "plans" / "plan-v1.json").read_text(encoding="utf-8"))
            report = json.loads((destination / "migration-report.json").read_text(encoding="utf-8"))
            self.assertEqual([item["path"] for item in plan["nodes"][0]["outputs"]], ["artifacts/result.txt"])
            self.assertEqual(plan["nodes"][1]["outputs"], [])
            self.assertTrue(
                any(
                    "Producer Two: duplicate legacy output 'artifacts/result.txt' remains owned by earlier producer 'Producer One'"
                    in warning
                    for warning in report["warnings"]
                )
            )

    def test_lexically_equivalent_legacy_outputs_keep_one_canonical_owner(self) -> None:
        variants = (
            "artifacts/result.txt",
            "artifacts/./result.txt",
            "artifacts//result.txt",
            r"artifacts\result.txt",
        )
        nodes = []
        states = {}
        for index, value in enumerate(variants, start=1):
            node = legacy_node(f"Producer {index}")
            node["produces"] = [value]
            nodes.append(node)
            states[node["id"]] = "pending"
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            source = parent / "source"
            destination = parent / "migrated"
            write_source(source, nodes, states=states)

            result = run_cli(source, destination, dry_run=False)

            self.assertEqual(result.returncode, 0, result.stderr)
            plan = json.loads((destination / "plans" / "plan-v1.json").read_text(encoding="utf-8"))
            report = json.loads((destination / "migration-report.json").read_text(encoding="utf-8"))
            self.assertEqual([item["path"] for item in plan["nodes"][0]["outputs"]], ["artifacts/result.txt"])
            self.assertTrue(all(node["outputs"] == [] for node in plan["nodes"][1:]))
            self.assertEqual(
                sum("duplicate legacy output" in warning for warning in report["warnings"]),
                3,
            )

    def test_malformed_or_unsafe_outputs_fail_closed_for_dry_and_real(self) -> None:
        cases = (
            ("not-list", "artifacts/result.txt", "produces must be a list"),
            ("non-string", [7], "must be a non-empty string"),
            ("empty", [""], "must be a non-empty string"),
            ("blank", ["   "], "must be a non-empty string"),
            ("posix-absolute", ["/tmp/result.txt"], "must be a relative path"),
            ("windows-absolute", [r"C:\tmp\result.txt"], "must be a relative path"),
            ("windows-drive-relative", [r"C:result.txt"], "must be a relative path"),
            ("windows-unc", [r"\\server\share\result.txt"], "must be a relative path"),
            ("posix-parent", ["../result.txt"], "must be a relative path"),
            ("windows-parent", [r"reports\..\result.txt"], "must be a relative path"),
            ("current-directory", ["."], "must be a relative path"),
            ("trailing-dot", ["artifacts/result.txt."], "must be a relative path"),
            ("trailing-space", ["artifacts/result.txt "], "must be a relative path"),
            ("windows-question", ["artifacts/result?.txt"], "must be a relative path"),
            ("windows-pipe", ["artifacts/result|copy.txt"], "must be a relative path"),
            ("windows-control", ["artifacts/control\x01.txt"], "must be a relative path"),
        )
        for case_name, produces, error in cases:
            with self.subTest(case=case_name), tempfile.TemporaryDirectory() as temp:
                parent = Path(temp)
                source = parent / "source"
                node = legacy_node("Node One")
                node["produces"] = produces
                write_source(source, [node], states={"Node One": "pending"})

                errors = []
                for dry_run, name in ((True, "dry"), (False, "real")):
                    destination = parent / name
                    result = run_cli(source, destination, dry_run=dry_run)
                    errors.append(result.stderr)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn(error, result.stderr)
                    self.assertFalse(destination.exists())
                    self.assertEqual(staging_paths(destination), [])
                self.assertEqual(errors[0], errors[1])

    def test_all_locked_legacy_statuses_map_without_fallback(self) -> None:
        nodes = [legacy_node(f"State {status}") for status in migrate_v1.STATUS]
        states = {f"State {status}": status for status in migrate_v1.STATUS}
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            source = parent / "source"
            destination = parent / "migrated"
            write_source(source, nodes, states=states)

            result = run_cli(source, destination, dry_run=False)

            self.assertEqual(result.returncode, 0, result.stderr)
            first_record = json.loads(
                (destination / "journal.jsonl").read_text(encoding="utf-8").splitlines()[0]
            )
            expected = {
                migrate_v1.stable_id(original_id, "node"): migrate_v1.STATUS[status]
                for original_id, status in states.items()
            }
            self.assertEqual(first_record["payload"]["node_states"], expected)

    def test_unknown_legacy_status_fails_closed_for_dry_and_real(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            source = parent / "source"
            write_source(
                source,
                [legacy_node("Node One")],
                states={"Node One": "future_unknown_status"},
            )

            errors = []
            for dry_run, name in ((True, "dry"), (False, "real")):
                destination = parent / name
                result = run_cli(source, destination, dry_run=dry_run)
                errors.append(result.stderr)
                self.assertEqual(result.returncode, 1)
                self.assertIn("unknown legacy node status", result.stderr)
                self.assertIn("future_unknown_status", result.stderr)
                self.assertFalse(destination.exists())
                self.assertEqual(staging_paths(destination), [])
            self.assertEqual(errors[0], errors[1])

    def test_normalized_ids_preserve_nested_graph_states_evidence_and_authorization(self) -> None:
        nested = {
            "parent_ref": "Parent Node",
            "schema_version": "1.0.0",
            "plan_version": 1,
            "nodes": [
                legacy_node("Nested One"),
                legacy_node("Nested Two", requires=["Nested One"]),
            ],
        }
        nodes = [
            legacy_node("A B"),
            legacy_node("Parent Node", requires=["A B"], subgraph=nested),
            legacy_node(
                "Approval Node",
                requires=["Parent Node"],
                kind="approval",
                gate_kind="human_approval",
            ),
        ]
        states = {
            "A B": "completed",
            "Parent Node": "running",
            "Nested One": "verifying",
            "Nested Two": "verification_failed",
            "Approval Node": "waiting_user",
        }
        entries = [
            {"entry_id": "ev-1", "node_id": "A B", "verdict": "pass", "status": "active"},
            {"entry_id": "ev-2", "node_id": "A B", "verdict": "fail", "status": "active"},
            {"entry_id": "ev-3", "node_id": "Nested One", "verdict": "pass", "status": "active"},
        ]
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            source = parent / "source"
            destination = parent / "migrated"
            write_source(source, nodes, states=states, entries=entries)

            result = run_cli(source, destination, dry_run=False)

            self.assertEqual(result.returncode, 0, result.stderr)
            plan = json.loads((destination / "plans" / "plan-v1.json").read_text(encoding="utf-8"))
            goal = json.loads((destination / "goal.json").read_text(encoding="utf-8"))
            resume = json.loads((destination / "resume.json").read_text(encoding="utf-8"))
            report = json.loads((destination / "migration-report.json").read_text(encoding="utf-8"))
            mapped = {node["id"]: node for node in plan["nodes"]}

            self.assertEqual(
                list(mapped),
                ["A-B", "Parent-Node", "Approval-Node", "Nested-One", "Nested-Two"],
            )
            self.assertEqual(mapped["Parent-Node"]["depends_on"], ["A-B", "Nested-Two"])
            self.assertEqual(mapped["Nested-One"]["depends_on"], ["A-B"])
            self.assertEqual(mapped["Nested-Two"]["depends_on"], ["Nested-One"])
            self.assertEqual(
                resume["projection"]["node_states"],
                {
                    "A-B": "done",
                    "Parent-Node": "active",
                    "Nested-One": "verifying",
                    "Nested-Two": "waiting",
                    "Approval-Node": "waiting",
                },
            )
            self.assertEqual(goal["authorization_boundaries"][0]["id"], "AUTH-Approval-Node")
            self.assertEqual(mapped["Approval-Node"]["authorization_refs"], ["AUTH-Approval-Node"])
            self.assertTrue(any(item.startswith("A-B: multiple or conflicting") for item in report["warnings"]))

    def test_node_id_normalization_collision_fails_closed_for_dry_and_real(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            source = parent / "source"
            write_source(
                source,
                [legacy_node("A B"), legacy_node("A-B")],
                states={"A B": "pending", "A-B": "pending"},
            )

            results = []
            for dry_run, name in ((True, "dry"), (False, "real")):
                destination = parent / name
                result = run_cli(source, destination, dry_run=dry_run)
                results.append(result)
                self.assertEqual(result.returncode, 1)
                self.assertIn("both normalize to 'A-B'", result.stderr)
                self.assertFalse(destination.exists())
                self.assertEqual(staging_paths(destination), [])
            self.assertEqual(results[0].stderr, results[1].stderr)

    def test_unmappable_nested_structure_and_orphan_references_fail_closed(self) -> None:
        cases = (
            (
                [
                    legacy_node(
                        "Parent",
                        subgraph={
                            "parent_ref": "Wrong Parent",
                            "schema_version": "1.0.0",
                            "plan_version": 1,
                            "nodes": [legacy_node("Nested")],
                        },
                    )
                ],
                {"Parent": "pending", "Nested": "pending"},
                [],
                "mismatched parent_ref",
            ),
            (
                [legacy_node("Only Node")],
                {"Only Node": "pending", "Orphan Node": "completed"},
                [],
                "unmapped legacy node ids",
            ),
            (
                [legacy_node("Only Node")],
                {"Only Node": "pending"},
                [{"entry_id": "ev-orphan", "node_id": "Orphan Node", "verdict": "pass"}],
                "unknown legacy node id",
            ),
        )
        for index, (nodes, states, entries, error) in enumerate(cases):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as temp:
                parent = Path(temp)
                source = parent / "source"
                destination = parent / f"dest-{index}"
                write_source(source, nodes, states=states, entries=entries)
                result = run_cli(source, destination, dry_run=True)
                self.assertEqual(result.returncode, 1)
                self.assertIn(error, result.stderr)
                self.assertFalse(destination.exists())
                self.assertEqual(staging_paths(destination), [])

    def test_dry_run_and_real_share_projector_validation_and_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            source = parent / "source"
            write_source(
                source,
                [legacy_node("Node A", requires=["Node B"]), legacy_node("Node B", requires=["Node A"])],
                states={"Node A": "pending", "Node B": "pending"},
            )
            source_before = {
                path.relative_to(source): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in source.rglob("*")
                if path.is_file()
            }

            errors = []
            for dry_run, name in ((True, "dry"), (False, "real")):
                destination = parent / name
                result = run_cli(source, destination, dry_run=dry_run)
                errors.append(result.stderr)
                self.assertEqual(result.returncode, 1)
                self.assertIn("GRAPH-CYCLE", result.stderr)
                self.assertFalse(destination.exists())
                self.assertEqual(staging_paths(destination), [])
            self.assertEqual(errors[0], errors[1])
            source_after = {
                path.relative_to(source): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in source.rglob("*")
                if path.is_file()
            }
            self.assertEqual(source_before, source_after)

    def test_conversion_reads_snapshot_bytes_and_source_change_blocks_publish(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            source = parent / "source"
            destination = parent / "migrated"
            write_source(source, [legacy_node("Node One")], states={"Node One": "pending"})
            snapshot, hashes = migrate_v1.source_snapshot(source)
            plan_path = source / "loop.plan.yaml"
            changed = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
            changed["goal"] = "A changed goal that was not in the snapshot."
            plan_path.write_text(
                yaml.safe_dump(changed, sort_keys=False), encoding="utf-8", newline="\n"
            )

            goal, _, _, report = migrate_v1.convert(
                source,
                destination,
                dry_run=False,
                snapshot=snapshot,
                hashes=hashes,
            )
            self.assertEqual(goal["goal"], "Migrate the legacy Loop safely.")
            self.assertEqual(report["source_hashes"], hashes)

            errors = []
            for dry_run, name in ((True, "dry"), (False, "real")):
                case_source = parent / f"source-{name}"
                case_destination = parent / f"destination-{name}"
                write_source(case_source, [legacy_node("Node One")], states={"Node One": "pending"})
                real_convert = migrate_v1.convert

                def convert_then_change(*args, **kwargs):
                    result = real_convert(*args, **kwargs)
                    case_plan = case_source / "loop.plan.yaml"
                    value = yaml.safe_load(case_plan.read_text(encoding="utf-8"))
                    value["goal"] = "Changed after the migration snapshot."
                    case_plan.write_text(
                        yaml.safe_dump(value, sort_keys=False), encoding="utf-8", newline="\n"
                    )
                    return result

                with (
                    mock.patch.object(migrate_v1, "convert", side_effect=convert_then_change),
                    self.assertRaisesRegex(ValueError, "source changed during migration") as raised,
                ):
                    migrate_v1.migrate(case_source, case_destination, dry_run=dry_run)
                errors.append(str(raised.exception))
                self.assertFalse(case_destination.exists())
                self.assertEqual(staging_paths(case_destination), [])
            self.assertEqual(errors[0], errors[1])

    def test_ordinary_exception_is_bounded_and_cleans_staging(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            source = parent / "source"
            destination = parent / "migrated"
            write_source(source, [legacy_node("Node One")], states={"Node One": "pending"})
            errors = []
            for dry_run, name in ((True, "dry"), (False, "real")):
                destination = parent / name
                stderr = io.StringIO()
                argv = ["migrate_v1.py", str(source), str(destination)]
                if dry_run:
                    argv.append("--dry-run")
                failure = RuntimeError("injected ordinary failure\n" + "x" * 800)
                real_validate_staging = migrate_v1.validate_staging

                def validate_then_fail(*args, **kwargs):
                    real_validate_staging(*args, **kwargs)
                    raise failure

                with (
                    mock.patch.object(sys, "argv", argv),
                    mock.patch.object(migrate_v1, "validate_staging", side_effect=validate_then_fail),
                    redirect_stderr(stderr),
                ):
                    result = migrate_v1.main()

                errors.append(stderr.getvalue())
                self.assertEqual(result, 1)
                self.assertEqual(len(stderr.getvalue().splitlines()), 1)
                self.assertLessEqual(len(stderr.getvalue()), 526)
                self.assertTrue(stderr.getvalue().endswith("...\n"))
                self.assertFalse(destination.exists())
                self.assertEqual(staging_paths(destination), [])
            self.assertEqual(errors[0], errors[1])

    def test_keyboard_interrupt_and_system_exit_are_not_swallowed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            source = parent / "source"
            write_source(source, [legacy_node("Node One")], states={"Node One": "pending"})
            for raised in (KeyboardInterrupt(), SystemExit(7)):
                destination = parent / type(raised).__name__
                argv = ["migrate_v1.py", str(source), str(destination)]
                with (
                    self.subTest(exception=type(raised).__name__),
                    mock.patch.object(sys, "argv", argv),
                    mock.patch.object(migrate_v1, "validate_staging", side_effect=raised),
                    self.assertRaises(type(raised)),
                ):
                    migrate_v1.main()
                self.assertFalse(destination.exists())
                self.assertEqual(staging_paths(destination), [])

    def test_nested_child_dry_run_does_not_touch_ancestor_loop_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp) / "parent"
            child = parent / "_loops" / "child"
            destination = child.with_name("child-v2")
            write_source(parent, [legacy_node("Parent")], states={"Parent": "pending"})
            child.parent.mkdir()
            write_source(child, [legacy_node("Child")], states={"Child": "pending"})
            source_before = migrate_v1.source_hashes(parent)
            real_validate_staging = migrate_v1.validate_staging
            observed_staging: list[Path] = []

            def validate_outside_parent(staging: Path, *args, **kwargs) -> None:
                observed_staging.append(staging.resolve())
                self.assertFalse(staging.resolve().is_relative_to(parent.resolve()))
                self.assertEqual(migrate_v1.source_hashes(parent), source_before)
                real_validate_staging(staging, *args, **kwargs)

            with mock.patch.object(
                migrate_v1, "validate_staging", side_effect=validate_outside_parent
            ):
                report = migrate_v1.migrate(child, destination, dry_run=True)

            self.assertTrue(report["dry_run"])
            self.assertEqual(Path(report["destination"]), destination.resolve())
            self.assertEqual(len(observed_staging), 1)
            self.assertFalse(observed_staging[0].exists())
            self.assertEqual(migrate_v1.source_hashes(parent), source_before)
            self.assertFalse(destination.exists())
            self.assertEqual(staging_paths(destination), [])

    def test_real_migration_stages_beside_destination_before_publish(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            source = parent / "source"
            destination = parent / "migrated"
            write_source(source, [legacy_node("Node One")], states={"Node One": "pending"})
            real_validate_staging = migrate_v1.validate_staging

            def validate_sibling(staging: Path, *args, **kwargs) -> None:
                self.assertEqual(staging.parent.resolve(), destination.parent.resolve())
                real_validate_staging(staging, *args, **kwargs)

            with mock.patch.object(
                migrate_v1, "validate_staging", side_effect=validate_sibling
            ):
                report = migrate_v1.migrate(source, destination, dry_run=False)

            self.assertFalse(report["dry_run"])
            self.assertTrue(destination.is_dir())
            self.assertEqual(staging_paths(destination), [])

    def test_dry_run_rejects_temporary_staging_inside_loop_ancestry(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp) / "parent"
            child = parent / "_loops" / "child"
            destination = child.with_name("child-v2")
            unsafe_staging = parent / ".forced-dry-run-staging"
            write_source(parent, [legacy_node("Parent")], states={"Parent": "pending"})
            child.parent.mkdir()
            write_source(child, [legacy_node("Child")], states={"Child": "pending"})

            def create_unsafe_staging(*args, **kwargs) -> str:
                unsafe_staging.mkdir()
                return str(unsafe_staging)

            with (
                mock.patch.object(
                    migrate_v1.tempfile, "mkdtemp", side_effect=create_unsafe_staging
                ),
                self.assertRaisesRegex(
                    ValueError,
                    "dry-run temporary staging must be outside the source Loop ancestry",
                ),
            ):
                migrate_v1.migrate(child, destination, dry_run=True)

            self.assertFalse(unsafe_staging.exists())
            self.assertFalse(destination.exists())
            self.assertEqual(staging_paths(destination), [])


if __name__ == "__main__":
    unittest.main()
