from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from checks.checkpoint_projection import check_checkpoint_projection, project_checkpoint
from checks.event_log import validate_event_log
from checks.provenance import (
    check_evidence_identity,
    check_ledger_verifier_independence,
    check_missing_dissent,
    current_evidence_by_node,
)
from check_loop_integrity import check_loop_dir
from validate_checkpoint import validate_checkpoint_schema
from validate_loop_plan import validate_evidence_ledger


class EventSafetyTests(unittest.TestCase):
    def test_exact_effect_pair_and_reopen_control(self) -> None:
        events = [
            {"seq": 0, "node_id": "n", "ts": "2026-07-31T00:00:00Z", "kind": "pre_effect", "from_status": "ready", "to_status": "running", "effect_id": "deploy", "attempt_id": "a1"},
            {"seq": 1, "node_id": "n", "ts": "2026-07-31T00:01:00Z", "kind": "post_effect", "from_status": "running", "to_status": "verifying", "effect_id": "deploy", "attempt_id": "a1", "outcome": "ok"},
            {"seq": 2, "node_id": "n", "ts": "2026-07-31T00:02:00Z", "kind": "reopen", "from_status": "completed", "to_status": "verifying", "evidence_refs": ["ev-counter"]},
        ]
        errors: list[str] = []
        validate_event_log(events, errors, node_ids={"n"})
        self.assertEqual([], errors)

    def test_only_effect_and_reopen_records_may_carry_transitions(self) -> None:
        for kind, extra in (
            ("note", {}),
            (
                "mutation",
                {
                    "mutation_type": "add_subgraph",
                    "reason": "A prior observation exposed a gap.",
                    "evidence_refs": ["ev-1"],
                },
            ),
            (
                "dissent",
                {
                    "reason": "Proceed under an explicit override.",
                    "failed_entry_id": "failed",
                    "overriding_entry_id": "override",
                },
            ),
        ):
            with self.subTest(kind=kind):
                event = {
                    "seq": 0,
                    "node_id": "n",
                    "ts": "2026-07-31T00:00:00Z",
                    "kind": kind,
                    **extra,
                }
                errors: list[str] = []
                validate_event_log([event], errors, node_ids={"n"})
                self.assertEqual([], errors)

                errors = []
                validate_event_log(
                    [event | {"from_status": "running", "to_status": "waiting_user"}],
                    errors,
                    node_ids={"n"},
                )
                self.assertTrue(any("ILLEGAL-TRANSITION" in error for error in errors))

    def test_rejects_direct_completion_unknown_node_and_cross_attempt_post(self) -> None:
        events = [
            {"seq": 0, "node_id": "missing", "ts": "2026-07-31T00:00:00Z", "kind": "pre_effect", "from_status": "ready", "to_status": "running", "effect_id": "deploy", "attempt_id": "a1"},
            {"seq": 1, "node_id": "missing", "ts": "2026-07-31T00:01:00Z", "kind": "post_effect", "from_status": "running", "to_status": "completed", "effect_id": "deploy", "attempt_id": "a2", "outcome": "ok"},
        ]
        errors: list[str] = []
        validate_event_log(events, errors, node_ids={"n"})
        joined = "\n".join(errors)
        self.assertIn("EVENT-NODE-UNKNOWN", joined)
        self.assertIn("ILLEGAL-TRANSITION", joined)
        self.assertIn("EFFECT-PAIR", joined)

    def test_rejects_reopen_without_counterevidence(self) -> None:
        errors: list[str] = []
        validate_event_log([
            {"seq": 0, "node_id": "n", "ts": "2026-07-31T00:00:00Z", "kind": "reopen", "from_status": "completed", "to_status": "verifying", "evidence_refs": []},
        ], errors, node_ids={"n"})
        self.assertTrue(any("ILLEGAL-REOPEN" in error for error in errors))

    def test_post_effect_requires_outcome_and_failure_cannot_verify(self) -> None:
        pre = {
            "seq": 0,
            "node_id": "n",
            "ts": "2026-07-31T00:00:00Z",
            "kind": "pre_effect",
            "from_status": "ready",
            "to_status": "running",
            "effect_id": "deploy",
            "attempt_id": "a1",
        }
        for post in (
            {
                "seq": 1,
                "node_id": "n",
                "ts": "2026-07-31T00:01:00Z",
                "kind": "post_effect",
                "from_status": "running",
                "to_status": "verifying",
                "effect_id": "deploy",
                "attempt_id": "a1",
            },
            {
                "seq": 1,
                "node_id": "n",
                "ts": "2026-07-31T00:01:00Z",
                "kind": "post_effect",
                "from_status": "running",
                "to_status": "verifying",
                "effect_id": "deploy",
                "attempt_id": "a1",
                "outcome": "fail",
            },
        ):
            with self.subTest(post=post):
                errors: list[str] = []
                validate_event_log([pre, post], errors, node_ids={"n"})
                self.assertTrue(any("EFFECT-OUTCOME" in error for error in errors))

        errors = []
        validate_event_log(
            [
                pre,
                {
                    "seq": 1,
                    "node_id": "n",
                    "ts": "2026-07-31T00:01:00Z",
                    "kind": "post_effect",
                    "from_status": "running",
                    "to_status": "blocked",
                    "effect_id": "deploy",
                    "attempt_id": "a1",
                    "outcome": "fail",
                },
            ],
            errors,
            node_ids={"n"},
        )
        self.assertEqual([], errors)

    def test_rejects_reopen_with_unknown_counterevidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = ROOT / "examples" / "example_child_loop_tree" / "L001-example-delivery"
            target = Path(temp) / "loop"
            shutil.copytree(source, target)
            with (target / "event_log.jsonl").open("a", encoding="utf-8") as log:
                log.write(json.dumps({"seq": 2, "node_id": "charter", "ts": "2026-07-01T10:00:00Z", "kind": "reopen", "from_status": "completed", "to_status": "verifying", "evidence_refs": ["missing"]}) + "\n")
            checkpoint_path = target / "checkpoint.yaml"
            checkpoint = yaml.safe_load(checkpoint_path.read_text(encoding="utf-8"))
            checkpoint["last_event_seq"] = 2
            checkpoint_path.write_text(yaml.safe_dump(checkpoint, sort_keys=False), encoding="utf-8")
            problems, _checks = check_loop_dir(target)
            self.assertTrue(any("counterevidence references must resolve" in problem for problem in problems))

    def test_mutation_evidence_refs_must_resolve_in_whole_loop(self) -> None:
        source = ROOT / "examples" / "example_child_loop_tree" / "L001-example-delivery"
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "loop"
            shutil.copytree(source, target)
            event_path = target / "event_log.jsonl"
            checkpoint_path = target / "checkpoint.yaml"

            mutation = {
                "seq": 2,
                "node_id": "build",
                "ts": "2026-07-01T13:20:00Z",
                "kind": "mutation",
                "mutation_type": "add_subgraph",
                "reason": "The child result exposed a new verification branch.",
                "evidence_refs": ["missing"],
            }
            with event_path.open("a", encoding="utf-8") as log:
                log.write(json.dumps(mutation) + "\n")
            checkpoint = yaml.safe_load(checkpoint_path.read_text(encoding="utf-8"))
            checkpoint["last_event_seq"] = 2
            checkpoint_path.write_text(yaml.safe_dump(checkpoint, sort_keys=False), encoding="utf-8")

            problems, _checks = check_loop_dir(target)
            self.assertTrue(any("MUTATION-EVIDENCE" in problem for problem in problems))

            mutation["node_id"] = "charter"
            mutation["evidence_refs"] = ["ev-0001"]
            event_path.write_text(
                "\n".join(
                    [
                        *source.joinpath("event_log.jsonl").read_text(encoding="utf-8").splitlines(),
                        json.dumps(mutation),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            problems, _checks = check_loop_dir(target)
            self.assertFalse(any("MUTATION-EVIDENCE" in problem for problem in problems))

            mutation["node_id"] = "build"
            event_path.write_text(
                "\n".join(
                    [
                        *source.joinpath("event_log.jsonl").read_text(encoding="utf-8").splitlines(),
                        json.dumps(mutation),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            problems, _checks = check_loop_dir(target)
            self.assertTrue(any("MUTATION-EVIDENCE" in problem for problem in problems))

    def test_mutation_evidence_must_strictly_predate_the_event(self) -> None:
        source = ROOT / "examples" / "example_child_loop_tree" / "L001-example-delivery"
        for name, recorded, should_reject in (
            ("control", "2026-07-01T13:19:59Z", False),
            ("equal", "2026-07-01T13:20:00Z", True),
            ("future", "2026-07-02T00:00:00Z", True),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                target = Path(temp) / "loop"
                shutil.copytree(source, target)
                event_path = target / "event_log.jsonl"
                mutation = {
                    "seq": 2,
                    "node_id": "build",
                    "ts": "2026-07-01T13:20:00Z",
                    "kind": "mutation",
                    "mutation_type": "add_subgraph",
                    "reason": "A prior observation exposed a verification gap.",
                    "evidence_refs": ["mutation-evidence"],
                }
                with event_path.open("a", encoding="utf-8") as log:
                    log.write(json.dumps(mutation) + "\n")

                ledger_path = target / "evidence.ledger.yaml"
                ledger = yaml.safe_load(ledger_path.read_text(encoding="utf-8"))
                ledger["entries"].append(
                    ledger["entries"][0]
                    | {
                        "entry_id": "mutation-evidence",
                        "node_id": "build",
                        "gate_kind": "test",
                        "verdict": "fail",
                        "recorded": recorded,
                        "verifier": "script",
                        "rationale": "Observed a verification gap.",
                    }
                )
                ledger_path.write_text(
                    yaml.safe_dump(ledger, sort_keys=False), encoding="utf-8"
                )

                checkpoint_path = target / "checkpoint.yaml"
                checkpoint = yaml.safe_load(checkpoint_path.read_text(encoding="utf-8"))
                checkpoint["last_event_seq"] = 2
                checkpoint_path.write_text(
                    yaml.safe_dump(checkpoint, sort_keys=False), encoding="utf-8"
                )

                problems, _checks = check_loop_dir(target)
                causality_errors = [
                    problem
                    for problem in problems
                    if "must be recorded strictly before the mutation event" in problem
                ]
                self.assertEqual(should_reject, bool(causality_errors))

    def test_reopen_requires_current_same_node_prior_negative_evidence(self) -> None:
        source = ROOT / "examples" / "example_child_loop_tree" / "L001-example-delivery"
        cases = (
            ("cross-node", "build", "fail", "2026-07-01T09:05:00Z", None),
            ("passing", "charter", "pass", "2026-07-01T09:05:00Z", None),
            ("late", "charter", "fail", "2026-07-01T10:05:00Z", None),
            ("displaced", "charter", "fail", "2026-07-01T09:05:00Z", "newer"),
        )
        for name, node_id, verdict, recorded, replacement in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                target = Path(temp) / "loop"
                shutil.copytree(source, target)
                ledger_path = target / "evidence.ledger.yaml"
                ledger = yaml.safe_load(ledger_path.read_text(encoding="utf-8"))
                counter = {
                    "entry_id": "counter",
                    "node_id": node_id,
                    "gate_kind": "test",
                    "verdict": verdict,
                    "score": None,
                    "artifact_path": "evidence/charter.md",
                    "rationale": "counterexample",
                    "recorded": recorded,
                    "verifier": "script",
                    "assurance": "external",
                }
                ledger["entries"].append(counter)
                if replacement:
                    ledger["entries"].append(
                        counter
                        | {
                            "entry_id": replacement,
                            "verdict": "pass",
                            "recorded": "2026-07-01T09:06:00Z",
                            "rationale": "fresh control",
                        }
                    )
                    ledger["relations"] = [
                        {
                            "relation_id": "rel-newer",
                            "source_entry_id": replacement,
                            "target_entry_id": "counter",
                            "relation": "supersedes",
                            "reason": "fresh control",
                        },
                        {
                            "relation_id": "rel-old-pass",
                            "source_entry_id": replacement,
                            "target_entry_id": "ev-0001",
                            "relation": "supersedes",
                            "reason": "fresh control",
                        },
                    ]
                elif node_id == "charter":
                    ledger["relations"] = [
                        {
                            "relation_id": "rel-counter",
                            "source_entry_id": "counter",
                            "target_entry_id": "ev-0001",
                            "relation": "supersedes",
                            "reason": "new counterevidence",
                        }
                    ]
                ledger_path.write_text(yaml.safe_dump(ledger, sort_keys=False), encoding="utf-8")
                event_path = target / "event_log.jsonl"
                with event_path.open("a", encoding="utf-8") as log:
                    log.write(
                        json.dumps(
                            {
                                "seq": 2,
                                "node_id": "charter",
                                "ts": "2026-07-01T10:00:00Z",
                                "kind": "reopen",
                                "from_status": "completed",
                                "to_status": "verifying",
                                "evidence_refs": ["counter"],
                            }
                        )
                        + "\n"
                    )
                checkpoint_path = target / "checkpoint.yaml"
                checkpoint = yaml.safe_load(checkpoint_path.read_text(encoding="utf-8"))
                checkpoint["last_event_seq"] = 2
                checkpoint_path.write_text(
                    yaml.safe_dump(checkpoint, sort_keys=False), encoding="utf-8"
                )
                problems, _checks = check_loop_dir(target)
                self.assertTrue(any("ILLEGAL-REOPEN" in problem for problem in problems))

        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "loop"
            shutil.copytree(source, target)
            ledger_path = target / "evidence.ledger.yaml"
            ledger = yaml.safe_load(ledger_path.read_text(encoding="utf-8"))
            ledger["entries"].append(
                {
                    "entry_id": "counter",
                    "node_id": "charter",
                    "gate_kind": "test",
                    "verdict": "fail",
                    "score": None,
                    "artifact_path": "evidence/charter.md",
                    "rationale": "counterexample",
                    "recorded": "2026-07-01T09:30:00Z",
                    "verifier": "script",
                    "assurance": "external",
                }
            )
            ledger["relations"] = [
                {
                    "relation_id": "rel-counter",
                    "source_entry_id": "counter",
                    "target_entry_id": "ev-0001",
                    "relation": "supersedes",
                    "reason": "new counterevidence",
                }
            ]
            ledger_path.write_text(yaml.safe_dump(ledger, sort_keys=False), encoding="utf-8")
            event_path = target / "event_log.jsonl"
            with event_path.open("a", encoding="utf-8") as log:
                log.write(
                    json.dumps(
                        {
                            "seq": 2,
                            "node_id": "charter",
                            "ts": "2026-07-01T10:00:00Z",
                            "kind": "reopen",
                            "from_status": "completed",
                            "to_status": "verifying",
                            "evidence_refs": ["counter"],
                        }
                    )
                    + "\n"
                )
            checkpoint_path = target / "checkpoint.yaml"
            checkpoint = yaml.safe_load(checkpoint_path.read_text(encoding="utf-8"))
            checkpoint["node_states"]["charter"] = "verification_failed"
            checkpoint["last_completed"] = []
            checkpoint["last_event_seq"] = 2
            checkpoint_path.write_text(
                yaml.safe_dump(checkpoint, sort_keys=False), encoding="utf-8"
            )
            problems, _checks = check_loop_dir(target)
            self.assertFalse(any("ILLEGAL-REOPEN" in problem for problem in problems))

    def test_reopen_requires_new_pass_before_recompletion(self) -> None:
        plan = {"nodes": [{"id": "n", "status": "completed", "requires": []}]}
        events = [
            {
                "seq": 0,
                "node_id": "n",
                "ts": "2026-01-02T00:00:00Z",
                "kind": "reopen",
                "from_status": "completed",
                "to_status": "verifying",
                "evidence_refs": ["counter"],
            }
        ]
        ledger = {
            "entries": [
                {
                    "entry_id": "old-pass",
                    "node_id": "n",
                    "verdict": "pass",
                    "assurance": "external",
                    "recorded": "2026-01-01T00:00:00Z",
                }
            ]
        }
        self.assertEqual("verifying", project_checkpoint(plan, events, ledger).node_states["n"])
        ledger["entries"][0]["recorded"] = "2026-01-03T00:00:00Z"
        self.assertEqual("completed", project_checkpoint(plan, events, ledger).node_states["n"])

    def test_conservative_legacy_pairing(self) -> None:
        control = [
            {"seq": 0, "node_id": "n", "ts": "2026-07-31T00:00:00Z", "kind": "pre_effect", "from_status": "ready", "to_status": "running", "idempotency_key": "k"},
            {"seq": 1, "node_id": "n", "ts": "2026-07-31T00:01:00Z", "kind": "post_effect", "from_status": "running", "to_status": "verifying", "idempotency_key": "k", "outcome": "ok"},
        ]
        errors: list[str] = []
        validate_event_log(control, errors, node_ids={"n"})
        self.assertEqual([], errors)
        reject = [
            control[0],
            {"seq": 1, "node_id": "n", "ts": "2026-07-31T00:00:30Z", "kind": "note"},
            control[1] | {"seq": 2},
        ]
        errors = []
        validate_event_log(reject, errors, node_ids={"n"})
        self.assertTrue(any("LEGACY-EFFECT-AMBIGUOUS" in error for error in errors))

    def test_unmatched_exact_effect_requires_idempotency_key(self) -> None:
        base = {
            "seq": 0,
            "node_id": "n",
            "ts": "2026-07-31T00:00:00Z",
            "kind": "pre_effect",
            "from_status": "ready",
            "to_status": "running",
            "effect_id": "publish",
            "attempt_id": "attempt-1",
        }
        errors: list[str] = []
        validate_event_log([base], errors, node_ids={"n"})
        self.assertTrue(any("IN-DOUBT-NONIDEMPOTENT" in error for error in errors))

        errors = []
        validate_event_log([base | {"idempotency_key": "publish#attempt-1"}], errors, node_ids={"n"})
        self.assertEqual([], errors)

    def test_mutation_requires_type_reason_and_evidence(self) -> None:
        errors: list[str] = []
        validate_event_log([
            {"seq": 0, "node_id": "n", "ts": "2026-07-31T00:00:00Z", "kind": "mutation", "mutation_type": "add_subgraph", "reason": "", "evidence_refs": []},
        ], errors, node_ids={"n"})
        joined = "\n".join(errors)
        self.assertIn("non-empty reason", joined)
        self.assertIn("non-empty evidence_refs", joined)

        errors = []
        validate_event_log([
            {"seq": 0, "node_id": "n", "ts": "2026-07-31T00:00:00Z", "kind": "mutation", "mutation_type": "add_subgraph", "reason": "New evidence invalidated the flat plan.", "evidence_refs": ["ev-1"]},
        ], errors, node_ids={"n"})
        self.assertEqual([], errors)

    def test_event_shape_and_timezone_validation_are_mandatory(self) -> None:
        control = {
            "seq": 0,
            "node_id": "n",
            "ts": "2026-07-31T08:00:00+08:00",
            "kind": "note",
            "reason": "control annotation",
        }
        errors: list[str] = []
        validate_event_log([control], errors, node_ids={"n"})
        self.assertEqual([], errors)

        for event, expected in (
            (control | {"bogus": True}, "unexpected field"),
            (control | {"ts": "not-a-time"}, "valid RFC 3339"),
            (control | {"ts": "2026-07-31T08:00:00"}, "valid RFC 3339"),
        ):
            with self.subTest(event=event):
                errors = []
                validate_event_log([event], errors, node_ids={"n"})
                self.assertTrue(any(expected in error for error in errors))

    def test_sequence_rejects_negative_values_but_allows_gaps(self) -> None:
        errors: list[str] = []
        validate_event_log([
            {"seq": -1, "node_id": "n", "ts": "2026-07-31T00:00:00Z", "kind": "note"},
        ], errors, node_ids={"n"})
        self.assertTrue(any("non-negative integer" in error for error in errors))

        errors = []
        validate_event_log([
            {"seq": 4, "node_id": "n", "ts": "2026-07-31T00:00:00Z", "kind": "note"},
            {"seq": 9, "node_id": "n", "ts": "2026-07-31T00:01:00Z", "kind": "note"},
        ], errors, node_ids={"n"})
        self.assertEqual([], errors)


class EvidenceSafetyTests(unittest.TestCase):
    @staticmethod
    def valid_ledger() -> dict:
        return {
            "schema_version": "1.0.0",
            "entries": [
                {
                    "entry_id": "ev-1",
                    "node_id": "n",
                    "gate_kind": "test",
                    "verdict": "pass",
                    "score": None,
                    "artifact_path": "evidence/result.txt",
                    "rationale": "The declared check passed.",
                    "recorded": "2026-01-01T00:00:00Z",
                    "verifier": "script",
                    "assurance": "external",
                    "status": "active",
                    "superseded_by": None,
                }
            ],
            "relations": [],
        }

    def test_handwritten_ledger_shape_matches_completion_relevant_schema(self) -> None:
        cases = (
            ("root-extra", lambda ledger: ledger.update({"unexpected": True}), "unexpected field"),
            ("entry-extra", lambda ledger: ledger["entries"][0].update({"unexpected": True}), "unexpected field"),
            ("entry-id", lambda ledger: ledger["entries"][0].update({"entry_id": 7}), "entry_id must be a non-empty string"),
            ("artifact-null", lambda ledger: ledger["entries"][0].update({"artifact_path": None}), "artifact_path must be a non-empty string"),
            ("rationale-list", lambda ledger: ledger["entries"][0].update({"rationale": []}), "rationale must be a string"),
            ("recorded-object", lambda ledger: ledger["entries"][0].update({"recorded": {}}), "recorded must be a valid RFC 3339"),
            ("recorded-naive", lambda ledger: ledger["entries"][0].update({"recorded": "2026-01-01T00:00:00"}), "recorded must be a valid RFC 3339"),
            ("score-range", lambda ledger: ledger["entries"][0].update({"score": 2}), "score must be null or a number from 0 to 1"),
            ("score-bool", lambda ledger: ledger["entries"][0].update({"score": True}), "score must be null or a number from 0 to 1"),
            ("score-nan", lambda ledger: ledger["entries"][0].update({"score": float("nan")}), "score must be null or a number from 0 to 1"),
            ("score-infinity", lambda ledger: ledger["entries"][0].update({"score": float("inf")}), "score must be null or a number from 0 to 1"),
            ("gate-kind-list", lambda ledger: ledger["entries"][0].update({"gate_kind": []}), "BAD GATE KIND"),
            ("assurance-list", lambda ledger: ledger["entries"][0].update({"assurance": []}), "MISSING-ASSURANCE"),
            ("status-list", lambda ledger: ledger["entries"][0].update({"status": []}), "status [] is not one of"),
            ("superseded-by-list", lambda ledger: ledger["entries"][0].update({"superseded_by": []}), "superseded_by must be a string or null"),
            ("relation-extra", lambda ledger: ledger["relations"].append({"relation_id": "r", "source_entry_id": "ev-1", "target_entry_id": "ev-1", "relation": "confirms", "reason": "x", "unexpected": True}), "unexpected field"),
            ("relation-reason", lambda ledger: ledger["relations"].append({"relation_id": "r", "source_entry_id": "ev-1", "target_entry_id": "ev-1", "relation": "confirms", "reason": 7}), "reason must be a non-empty string"),
            ("relation-source-list", lambda ledger: ledger["relations"].append({"relation_id": "r", "source_entry_id": [], "target_entry_id": "ev-1", "relation": "supersedes", "reason": "x"}), "source_entry_id must be a non-empty string"),
            ("relation-kind-list", lambda ledger: ledger["relations"].append({"relation_id": "r", "source_entry_id": "ev-1", "target_entry_id": "ev-1", "relation": [], "reason": "x"}), "relation must be a non-empty string"),
        )
        for name, mutate, expected in cases:
            with self.subTest(name=name):
                ledger = self.valid_ledger()
                mutate(ledger)
                errors: list[str] = []
                validate_evidence_ledger(ledger, errors)
                self.assertTrue(any(expected in error for error in errors), errors)

        errors = []
        validate_evidence_ledger(self.valid_ledger(), errors)
        self.assertEqual([], errors)

    def test_mixed_mapping_keys_and_bad_plan_refs_fail_without_traceback(self) -> None:
        source = ROOT / "examples" / "example_child_loop_tree" / "L001-example-delivery"
        plan_path = source / "loop.plan.yaml"
        source_ledger = yaml.safe_load(
            (source / "evidence.ledger.yaml").read_text(encoding="utf-8")
        )
        cases = (
            (
                "root-mixed-key",
                lambda ledger: ledger.update({1: "bad", "unexpected": True}),
                "mapping keys must be strings",
            ),
            (
                "entry-mixed-key",
                lambda ledger: ledger["entries"][0].update({1: "bad", "unexpected": True}),
                "mapping keys must be strings",
            ),
            (
                "review-mixed-key",
                lambda ledger: ledger["entries"][0].update({
                    "review_context": {
                        "review_id": "review-1",
                        "delivered_context_sha256": "0" * 64,
                        "producer_claim_access": "withheld",
                        1: "bad",
                        "unexpected": True,
                    }
                }),
                "mapping keys must be strings",
            ),
            (
                "relation-mixed-key",
                lambda ledger: ledger.update({
                    "relations": [{
                        "relation_id": "rel-1",
                        "source_entry_id": "ev-0001",
                        "target_entry_id": "ev-0001",
                        "relation": "confirms",
                        "reason": "shape rejection control",
                        1: "bad",
                        "unexpected": True,
                    }]
                }),
                "mapping keys must be strings",
            ),
            (
                "bad-plan-ref-type",
                lambda ledger: ledger["entries"][0].update({"success_criteria_id": []}),
                "success_criteria_id must be a string",
            ),
        )
        with tempfile.TemporaryDirectory() as temp:
            ledger_path = Path(temp) / "evidence.ledger.yaml"
            command = [
                sys.executable,
                str(ROOT / "scripts" / "validate_loop_plan.py"),
                "--kind",
                "evidence_ledger",
                str(ledger_path),
                "--plan",
                str(plan_path),
            ]
            for name, mutate, expected in cases:
                with self.subTest(name=name):
                    ledger = yaml.safe_load(yaml.safe_dump(source_ledger, sort_keys=False))
                    mutate(ledger)
                    ledger_path.write_text(
                        yaml.safe_dump(ledger, sort_keys=False), encoding="utf-8"
                    )
                    result = subprocess.run(command, capture_output=True, text=True)
                    output = result.stdout + result.stderr
                    self.assertEqual(1, result.returncode, output)
                    self.assertIn(expected, output)
                    self.assertNotIn("Traceback", output)

    def test_whole_loop_rejects_forged_ledger_without_jsonschema(self) -> None:
        source = ROOT / "examples" / "example_child_loop_tree" / "L001-example-delivery"
        blocker = (
            "import builtins\n"
            "_original_import = builtins.__import__\n"
            "def _blocked(name, *args, **kwargs):\n"
            "    if name == 'jsonschema' or name.startswith('jsonschema.'):\n"
            "        raise ImportError('blocked by test')\n"
            "    return _original_import(name, *args, **kwargs)\n"
            "builtins.__import__ = _blocked\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            loop_path = temp_path / "loop"
            shutil.copytree(source, loop_path)
            (temp_path / "sitecustomize.py").write_text(blocker, encoding="utf-8")
            ledger_path = loop_path / "evidence.ledger.yaml"
            ledger = yaml.safe_load(ledger_path.read_text(encoding="utf-8"))
            ledger["entries"][0] = {
                "entry_id": 7,
                "node_id": "charter",
                "gate_kind": "human_approval",
                "verdict": "pass",
                "score": None,
                "artifact_path": None,
                "rationale": [],
                "recorded": {},
                "verifier": "user",
                "assurance": "external",
            }
            ledger["relations"] = [
                {
                    "relation_id": "forged",
                    "source_entry_id": [],
                    "target_entry_id": "ev-0001",
                    "relation": "supersedes",
                    "reason": "malformed relation must not crash downstream checks",
                }
            ]
            ledger_path.write_text(
                yaml.safe_dump(ledger, sort_keys=False), encoding="utf-8"
            )
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(temp_path)
            command = [
                sys.executable,
                str(ROOT / "scripts" / "check_loop_integrity.py"),
                str(loop_path),
            ]
            rejected = subprocess.run(
                command, capture_output=True, text=True, env=environment
            )
            self.assertEqual(1, rejected.returncode, rejected.stdout + rejected.stderr)
            self.assertIn("ledger invalid", rejected.stdout + rejected.stderr)

            shutil.rmtree(loop_path)
            shutil.copytree(source, loop_path)
            control = subprocess.run(
                command, capture_output=True, text=True, env=environment
            )
            self.assertEqual(0, control.returncode, control.stdout + control.stderr)

    def test_whole_loop_rejects_non_finite_score_without_jsonschema(self) -> None:
        source = ROOT / "examples" / "example_child_loop_tree" / "L001-example-delivery"
        blocker = (
            "import builtins\n"
            "_original_import = builtins.__import__\n"
            "def _blocked(name, *args, **kwargs):\n"
            "    if name == 'jsonschema' or name.startswith('jsonschema.'):\n"
            "        raise ImportError('blocked by test')\n"
            "    return _original_import(name, *args, **kwargs)\n"
            "builtins.__import__ = _blocked\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            loop_path = temp_path / "loop"
            (temp_path / "sitecustomize.py").write_text(blocker, encoding="utf-8")
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(temp_path)
            command = [
                sys.executable,
                str(ROOT / "scripts" / "check_loop_integrity.py"),
                str(loop_path),
            ]
            for score, expected_rc in ((float("nan"), 1), (None, 0), (0, 0), (1, 0)):
                with self.subTest(score=score):
                    if loop_path.exists():
                        shutil.rmtree(loop_path)
                    shutil.copytree(source, loop_path)
                    ledger_path = loop_path / "evidence.ledger.yaml"
                    ledger = yaml.safe_load(ledger_path.read_text(encoding="utf-8"))
                    ledger["entries"][0]["score"] = score
                    ledger_path.write_text(
                        yaml.safe_dump(ledger, sort_keys=False), encoding="utf-8"
                    )
                    result = subprocess.run(
                        command, capture_output=True, text=True, env=environment
                    )
                    output = result.stdout + result.stderr
                    self.assertEqual(expected_rc, result.returncode, output)
                    self.assertNotIn("Traceback", output)
                    if expected_rc:
                        self.assertIn(
                            "score must be null or a number from 0 to 1", output
                        )

    def test_newer_fail_is_current_not_old_pass(self) -> None:
        ledger = {"entries": [
            {"entry_id": "old", "node_id": "n", "verdict": "pass", "assurance": "external", "recorded": "2026-01-01T00:00:00Z"},
            {"entry_id": "new", "node_id": "n", "verdict": "fail", "assurance": "external", "recorded": "2026-01-02T00:00:00Z"},
        ], "relations": [
            {"relation_id": "r-new", "source_entry_id": "new", "target_entry_id": "old", "relation": "supersedes", "reason": "newer test result"},
        ]}
        self.assertEqual("fail", current_evidence_by_node(ledger)["n"]["verdict"])

    def test_append_order_without_relation_does_not_choose_a_latest_head(self) -> None:
        ledger = {"entries": [
            {"entry_id": "old", "node_id": "n", "verdict": "pass", "assurance": "external", "recorded": "2026-01-01T00:00:00Z"},
            {"entry_id": "new", "node_id": "n", "verdict": "fail", "assurance": "external", "recorded": "2026-01-02T00:00:00Z"},
        ]}
        errors: list[str] = []
        self.assertEqual({}, current_evidence_by_node(ledger, errors))
        self.assertTrue(any("EVIDENCE-HEAD" in error for error in errors))

    def test_older_relation_source_cannot_displace_newer_evidence(self) -> None:
        ledger = {"entries": [
            {"entry_id": "old", "node_id": "n", "verdict": "pass", "assurance": "external", "recorded": "2026-01-01T00:00:00Z"},
            {"entry_id": "new", "node_id": "n", "verdict": "fail", "assurance": "external", "recorded": "2026-01-02T00:00:00Z"},
        ], "relations": [
            {"relation_id": "r-old", "source_entry_id": "old", "target_entry_id": "new", "relation": "supersedes", "reason": "forged reverse relation"},
        ]}
        errors: list[str] = []
        check_evidence_identity(ledger, errors)
        joined = "\n".join(errors)
        self.assertIn("must appear after target entry", joined)
        self.assertIn("recorded must be strictly later", joined)

        ledger["entries"].reverse()
        ledger["entries"][0]["recorded"] = "2026-01-01T00:00:00Z"
        ledger["entries"][1]["recorded"] = "2026-01-02T00:00:00Z"
        errors = []
        check_evidence_identity(ledger, errors)
        self.assertEqual([], errors)
        self.assertEqual("pass", current_evidence_by_node(ledger, errors)["n"]["verdict"])

    def test_relation_with_missing_or_invalid_time_cannot_change_current_evidence(self) -> None:
        for source_time in (None, "not-a-time"):
            with self.subTest(source_time=source_time):
                source = {
                    "entry_id": "new", "node_id": "n", "verdict": "fail",
                    "assurance": "external",
                }
                if source_time is not None:
                    source["recorded"] = source_time
                ledger = {"entries": [
                    {"entry_id": "old", "node_id": "n", "verdict": "pass", "assurance": "external", "recorded": "2026-01-01T00:00:00Z"},
                    source,
                ], "relations": [
                    {"relation_id": "r-new", "source_entry_id": "new", "target_entry_id": "old", "relation": "supersedes", "reason": "newer test result"},
                ]}
                errors: list[str] = []
                check_evidence_identity(ledger, errors)
                self.assertTrue(any("requires valid RFC 3339" in error for error in errors))
                self.assertEqual({}, current_evidence_by_node(ledger, errors))
                self.assertTrue(any("EVIDENCE-HEAD" in error for error in errors))

    def test_invalidly_ordered_challenge_and_confirmation_do_not_change_currentness(self) -> None:
        ledger = {"entries": [
            {"entry_id": "pass", "node_id": "n", "verdict": "pass", "assurance": "external", "recorded": "2026-01-03T00:00:00Z"},
            {"entry_id": "challenge", "node_id": "n", "verdict": "fail", "assurance": "blind", "recorded": "2026-01-01T00:00:00Z"},
            {"entry_id": "confirm", "node_id": "n", "verdict": "pass", "assurance": "external", "recorded": "2026-01-02T00:00:00Z"},
        ], "relations": [
            {"relation_id": "r1", "source_entry_id": "challenge", "target_entry_id": "pass", "relation": "challenges", "reason": "counterexample"},
            {"relation_id": "r2", "source_entry_id": "confirm", "target_entry_id": "challenge", "relation": "confirms", "reason": "recheck"},
        ]}
        errors: list[str] = []
        check_evidence_identity(ledger, errors)
        self.assertTrue(any("recorded must be strictly later" in error for error in errors))
        self.assertEqual({}, current_evidence_by_node(ledger, errors))
        self.assertTrue(any("EVIDENCE-HEAD" in error for error in errors))

    def test_older_legacy_link_cannot_displace_newer_evidence(self) -> None:
        ledger = {"entries": [
            {"entry_id": "old", "node_id": "n", "verdict": "pass", "assurance": "external", "recorded": "2026-01-01T00:00:00Z", "supersedes": "new"},
            {"entry_id": "new", "node_id": "n", "verdict": "fail", "assurance": "external", "recorded": "2026-01-02T00:00:00Z"},
        ]}
        errors: list[str] = []
        check_evidence_identity(ledger, errors)
        self.assertTrue(any("must appear after target entry" in error for error in errors))
        self.assertEqual({}, current_evidence_by_node(ledger, errors))
        self.assertTrue(any("EVIDENCE-HEAD" in error for error in errors))

    def test_duplicate_ids_and_relation_cycle_rejected(self) -> None:
        ledger = {"entries": [
            {"entry_id": "a", "node_id": "n"},
            {"entry_id": "a", "node_id": "n"},
            {"entry_id": "b", "node_id": "n"},
        ], "relations": [
            {"relation_id": "r1", "source_entry_id": "a", "target_entry_id": "b", "relation": "supersedes", "reason": "x"},
            {"relation_id": "r2", "source_entry_id": "b", "target_entry_id": "a", "relation": "supersedes", "reason": "x"},
        ]}
        errors: list[str] = []
        check_evidence_identity(ledger, errors)
        joined = "\n".join(errors)
        self.assertIn("duplicate entry_id", joined)
        self.assertIn("cycle", joined)

    def test_challenged_evidence_cannot_authorize(self) -> None:
        ledger = {"entries": [{"entry_id": "pass", "node_id": "n", "verdict": "pass", "assurance": "external", "recorded": "2026-01-01T00:00:00Z"}, {"entry_id": "challenge", "node_id": "n", "verdict": "fail", "assurance": "external", "status": "retired", "recorded": "2026-01-02T00:00:00Z"}], "relations": [{"relation_id": "r", "source_entry_id": "challenge", "target_entry_id": "pass", "relation": "challenges", "reason": "counterexample"}]}
        self.assertNotIn("n", current_evidence_by_node(ledger))

    def test_new_blind_failure_cannot_hide_itself_with_retired_status(self) -> None:
        ledger = {"entries": [
            {"entry_id": "old-pass", "node_id": "n", "verdict": "pass", "assurance": "external", "recorded": "2026-01-01T00:00:00Z"},
            {"entry_id": "new-fail", "node_id": "n", "verdict": "fail", "assurance": "blind", "status": "retired", "recorded": "2026-01-02T00:00:00Z"},
        ]}
        errors: list[str] = []
        check_evidence_identity(ledger, errors)
        self.assertTrue(any("EVIDENCE-LIFECYCLE" in error for error in errors))
        self.assertEqual({}, current_evidence_by_node(ledger, errors))
        self.assertTrue(any("cannot be hidden" in error for error in errors))

        ledger["entries"][1].pop("status")
        ledger["relations"] = [{
            "relation_id": "rel-new-fail", "source_entry_id": "new-fail",
            "target_entry_id": "old-pass", "relation": "supersedes",
            "reason": "fresh blind review failed",
        }]
        errors = []
        check_evidence_identity(ledger, errors)
        self.assertEqual([], errors)
        self.assertEqual("new-fail", current_evidence_by_node(ledger, errors)["n"]["entry_id"])

    def test_blind_assurance_requires_withheld_producer_claim(self) -> None:
        base_context = {
            "review_id": "review-1",
            "delivered_context_sha256": "a" * 64,
        }
        ledger = {"entries": [{
            "entry_id": "blind", "node_id": "n", "assurance": "blind",
            "review_context": base_context | {"producer_claim_access": "available"},
        }]}
        for access in ("available", "unknown"):
            with self.subTest(access=access):
                ledger["entries"][0]["review_context"]["producer_claim_access"] = access
                errors: list[str] = []
                check_ledger_verifier_independence(ledger, {}, errors)
                self.assertTrue(any("producer_claim_access: withheld" in error for error in errors))

        ledger["entries"][0]["review_context"]["producer_claim_access"] = "withheld"
        errors = []
        check_ledger_verifier_independence(ledger, {}, errors)
        self.assertEqual([], errors)

    def test_legacy_challenged_status_cannot_authorize(self) -> None:
        ledger = {"entries": [{
            "entry_id": "pass", "node_id": "n", "verdict": "pass",
            "assurance": "external", "status": "challenged",
        }]}
        self.assertNotIn("n", current_evidence_by_node(ledger))

    def test_only_active_exact_confirmation_resolves_a_challenge(self) -> None:
        ledger = {
            "entries": [
                {"entry_id": "pass", "node_id": "n", "verdict": "pass", "assurance": "external", "recorded": "2026-01-01T00:00:00Z"},
                {"entry_id": "challenge", "node_id": "n", "verdict": "fail", "assurance": "blind", "recorded": "2026-01-02T00:00:00Z"},
                {"entry_id": "confirm", "node_id": "n", "verdict": "pass", "assurance": "external", "status": "retired", "recorded": "2026-01-03T00:00:00Z"},
            ],
            "relations": [
                {"relation_id": "r1", "source_entry_id": "challenge", "target_entry_id": "pass", "relation": "challenges", "reason": "counterexample"},
                {"relation_id": "r2", "source_entry_id": "confirm", "target_entry_id": "pass", "relation": "confirms", "reason": "unrelated"},
            ],
        }
        errors: list[str] = []
        check_evidence_identity(ledger, errors)
        self.assertTrue(any("exact prior challenge evidence" in error for error in errors))
        self.assertEqual("fail", current_evidence_by_node(ledger, errors)["n"]["verdict"])

        ledger["relations"][1]["target_entry_id"] = "challenge"
        ledger["entries"][2].pop("status")
        ledger["relations"] += [
            {"relation_id": "r3", "source_entry_id": "confirm", "target_entry_id": "challenge", "relation": "supersedes", "reason": "resolved"},
            {"relation_id": "r4", "source_entry_id": "confirm", "target_entry_id": "pass", "relation": "supersedes", "reason": "fresh result"},
        ]
        errors = []
        check_evidence_identity(ledger, errors)
        self.assertEqual([], errors)
        self.assertEqual("pass", current_evidence_by_node(ledger, errors)["n"]["verdict"])

    def test_relations_require_counterevidence_and_passing_confirmation(self) -> None:
        ledger = {
            "entries": [
                {"entry_id": "pass", "node_id": "n", "verdict": "pass", "recorded": "2026-01-01T00:00:00Z"},
                {"entry_id": "bad-challenge", "node_id": "n", "verdict": "pass", "recorded": "2026-01-02T00:00:00Z"},
                {"entry_id": "bad-confirm", "node_id": "n", "verdict": "fail", "recorded": "2026-01-03T00:00:00Z"},
            ],
            "relations": [
                {"relation_id": "r1", "source_entry_id": "bad-challenge", "target_entry_id": "pass", "relation": "challenges", "reason": "not counterevidence"},
                {"relation_id": "r2", "source_entry_id": "bad-confirm", "target_entry_id": "bad-challenge", "relation": "confirms", "reason": "not a passing confirmation"},
            ],
        }
        errors: list[str] = []
        check_evidence_identity(ledger, errors)
        joined = "\n".join(errors)
        self.assertIn("challenges source must have verdict fail or inconclusive", joined)
        self.assertIn("confirms source must have verdict pass", joined)

        ledger["entries"][1]["verdict"] = "inconclusive"
        ledger["entries"][2]["verdict"] = "pass"
        errors = []
        check_evidence_identity(ledger, errors)
        self.assertEqual([], errors)

        ledger["relations"] = [{
            "relation_id": "r3", "source_entry_id": "pass", "target_entry_id": "bad-challenge",
            "relation": "invalidates", "reason": "not counterevidence",
        }]
        errors = []
        check_evidence_identity(ledger, errors)
        self.assertTrue(any("invalidates source must have verdict fail or inconclusive" in error for error in errors))

    def test_multiple_current_heads_are_rejected(self) -> None:
        errors: list[str] = []
        self.assertEqual({}, current_evidence_by_node({"entries": [{"entry_id": "a", "node_id": "n"}, {"entry_id": "b", "node_id": "n"}]}, errors))
        self.assertTrue(any("EVIDENCE-HEAD" in error for error in errors))

    def test_inactive_dissent_override_is_rejected(self) -> None:
        ledger = {"entries": [
            {"entry_id": "fail", "node_id": "n", "verdict": "fail", "assurance": "blind", "status": "active", "recorded": "2026-01-01T01:00:00Z"},
            {"entry_id": "override", "node_id": "n", "verdict": "pass", "assurance": "external", "status": "stale", "overrides_entry_id": "fail", "recorded": "2026-01-01T01:00:00Z"},
        ]}
        events = [{"kind": "dissent", "node_id": "n", "failed_entry_id": "fail", "overriding_entry_id": "override", "reason": "proceed", "ts": "2026-01-01T02:00:00Z"}]
        errors: list[str] = []
        check_missing_dissent(ledger, {"node_states": {"n": "completed"}}, events, errors)
        self.assertTrue(any("MISSING-DISSENT" in error for error in errors))

    def test_repaired_blind_failure_does_not_require_dissent(self) -> None:
        ledger = {
            "entries": [
                {
                    "entry_id": "fail",
                    "node_id": "n",
                    "verdict": "fail",
                    "assurance": "blind",
                    "recorded": "2026-01-01T01:00:00Z",
                },
                {
                    "entry_id": "fixed-pass",
                    "node_id": "n",
                    "verdict": "pass",
                    "assurance": "external",
                    "recorded": "2026-01-01T02:00:00Z",
                },
            ],
            "relations": [
                {
                    "relation_id": "rel-fixed",
                    "source_entry_id": "fixed-pass",
                    "target_entry_id": "fail",
                    "relation": "supersedes",
                    "reason": "the defect was fixed and the check reran",
                }
            ],
        }
        errors: list[str] = []
        check_missing_dissent(ledger, {"node_states": {"n": "completed"}}, [], errors)
        self.assertEqual([], errors)

    def test_explicit_current_override_still_requires_exact_dissent(self) -> None:
        ledger = {
            "entries": [
                {
                    "entry_id": "fail",
                    "node_id": "n",
                    "verdict": "fail",
                    "assurance": "blind",
                    "recorded": "2026-01-01T01:00:00Z",
                },
                {
                    "entry_id": "override",
                    "node_id": "n",
                    "verdict": "pass",
                    "assurance": "external",
                    "overrides_entry_id": "fail",
                    "recorded": "2026-01-01T02:00:00Z",
                },
            ]
        }
        checkpoint = {"node_states": {"n": "completed"}}
        errors: list[str] = []
        check_missing_dissent(ledger, checkpoint, [], errors)
        self.assertTrue(any("MISSING-DISSENT" in error for error in errors))

        events = [
            {
                "kind": "dissent",
                "node_id": "n",
                "failed_entry_id": "fail",
                "overriding_entry_id": "override",
                "reason": "authorized risk acceptance",
                "ts": "2026-01-01T03:00:00Z",
            }
        ]
        errors = []
        check_missing_dissent(ledger, checkpoint, events, errors)
        self.assertEqual([], errors)

    def test_dissent_time_is_timezone_aware_and_rejects_invalid_values(self) -> None:
        ledger = {"entries": [
            {"entry_id": "fail", "node_id": "n", "verdict": "fail", "assurance": "blind", "status": "active", "recorded": "2026-01-01T01:00:00Z"},
            {"entry_id": "override", "node_id": "n", "verdict": "pass", "assurance": "external", "status": "active", "overrides_entry_id": "fail", "recorded": "2026-01-01T10:00:00+08:00"},
        ]}
        event = {"kind": "dissent", "node_id": "n", "failed_entry_id": "fail", "overriding_entry_id": "override", "reason": "proceed", "ts": "2026-01-01T02:30:00Z"}
        errors: list[str] = []
        check_missing_dissent(ledger, {"node_states": {"n": "completed"}}, [event], errors)
        self.assertEqual([], errors)

        event["ts"] = "not-a-time"
        errors = []
        check_missing_dissent(ledger, {"node_states": {"n": "completed"}}, [event], errors)
        joined = "\n".join(errors)
        self.assertIn("INVALID-TIME", joined)
        self.assertIn("MISSING-DISSENT", joined)

        event["ts"] = "2026-01-01T02:30:00"
        errors = []
        check_missing_dissent(ledger, {"node_states": {"n": "completed"}}, [event], errors)
        self.assertTrue(any("must include a timezone" in error for error in errors))


class CheckpointSafetyTests(unittest.TestCase):
    def test_whole_loop_validates_present_loop_meta(self) -> None:
        source = (
            ROOT
            / "examples"
            / "example_child_loop_tree"
            / "L001-example-delivery"
            / "_loops"
            / "L001.01-fix-effectiveness-bug"
        )
        problems, checks = check_loop_dir(source)
        self.assertFalse(any("loop.meta.yaml invalid" in problem for problem in problems))
        self.assertIn("optional loop metadata validation", checks)

        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "loop"
            shutil.copytree(source, target)
            (target / "loop.meta.yaml").write_text(
                "loop_id: L001.01\n", encoding="utf-8"
            )
            problems, checks = check_loop_dir(target)
            self.assertTrue(any("loop.meta.yaml invalid" in problem for problem in problems))
            self.assertIn("optional loop metadata validation", checks)

    def test_whole_loop_rejects_invalid_runtime_event_shape(self) -> None:
        source = ROOT / "examples" / "example_child_loop_tree" / "L001-example-delivery"
        for name, patch, expected in (
            ("unknown-field", {"bogus": True}, "unexpected field"),
            ("invalid-time", {"ts": "not-a-time"}, "valid RFC 3339"),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                target = Path(temp) / "loop"
                shutil.copytree(source, target)
                event_path = target / "event_log.jsonl"
                with event_path.open("a", encoding="utf-8") as log:
                    log.write(
                        json.dumps(
                            {
                                "seq": 2,
                                "node_id": "build",
                                "ts": "2026-07-01T13:20:00Z",
                                "kind": "note",
                                "reason": "control annotation",
                                **patch,
                            }
                        )
                        + "\n"
                    )
                checkpoint_path = target / "checkpoint.yaml"
                checkpoint = yaml.safe_load(checkpoint_path.read_text(encoding="utf-8"))
                checkpoint["last_event_seq"] = 2
                checkpoint_path.write_text(
                    yaml.safe_dump(checkpoint, sort_keys=False), encoding="utf-8"
                )

                problems, _checks = check_loop_dir(target)
                self.assertTrue(any(expected in problem for problem in problems))

        problems, _checks = check_loop_dir(source)
        self.assertFalse(any("EVENTLOG-FIELD" in problem for problem in problems))

    def test_whole_loop_rejects_external_control_and_evidence_paths(self) -> None:
        source = ROOT / "examples" / "example_product_delivery"
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "loop"
            shutil.copytree(source, target)
            outside = Path(temp) / "outside.jsonl"
            outside.write_text("{}\n", encoding="utf-8")
            checkpoint_path = target / "checkpoint.yaml"
            checkpoint = yaml.safe_load(checkpoint_path.read_text(encoding="utf-8"))
            checkpoint["event_log_ref"] = "..\\outside.jsonl"
            checkpoint_path.write_text(yaml.safe_dump(checkpoint, sort_keys=False), encoding="utf-8")
            ledger_path = target / "evidence.ledger.yaml"
            ledger = yaml.safe_load(ledger_path.read_text(encoding="utf-8"))
            ledger["entries"][0]["artifact_path"] = str(outside.resolve())
            ledger_path.write_text(yaml.safe_dump(ledger, sort_keys=False), encoding="utf-8")

            problems, _ = check_loop_dir(target)
            joined = "\n".join(problems)
            self.assertIn("checkpoint.event_log_ref must be relative", joined)
            self.assertIn("artifact_path must be relative", joined)

    def test_last_event_seq_is_required(self) -> None:
        errors: list[str] = []
        validate_checkpoint_schema({}, errors)
        self.assertTrue(any("last_event_seq" in error for error in errors))

    def test_event_log_ref_must_be_a_non_empty_path_string(self) -> None:
        source = ROOT / "examples" / "example_product_delivery"
        for value in ("", None, 7):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as temp:
                target = Path(temp) / "loop"
                shutil.copytree(source, target)
                checkpoint_path = target / "checkpoint.yaml"
                checkpoint = yaml.safe_load(checkpoint_path.read_text(encoding="utf-8"))
                checkpoint.update({
                    "event_log_ref": value,
                    "last_event_seq": 0,
                    "last_completed": [],
                    "phase": 0,
                })
                checkpoint_path.write_text(
                    yaml.safe_dump(checkpoint, sort_keys=False), encoding="utf-8"
                )

                problems, checks = check_loop_dir(target)
                self.assertTrue(
                    any("event_log_ref must be a non-empty path string" in item for item in problems)
                )
                self.assertIn(
                    "declared event-log existence and line-by-line JSONL parsing", checks
                )

        problems, _checks = check_loop_dir(source)
        self.assertFalse(any("event_log_ref" in item for item in problems))

    def test_projection_compares_secondary_fields(self) -> None:
        plan = {"nodes": [{"id": "n", "status": "pending", "requires": []}]}
        checkpoint = {"node_states": {"n": "pending"}, "ready_set": [], "last_completed": [], "phase": 1, "last_event_seq": 4}
        errors: list[str] = []
        check_checkpoint_projection(plan, [], {"entries": []}, checkpoint, errors)
        joined = "\n".join(errors)
        self.assertIn("ready_set", joined)
        self.assertIn("phase", joined)
        self.assertIn("last_event_seq", joined)

    def test_reopen_projection_returns_to_verifying(self) -> None:
        plan = {"nodes": [{"id": "n", "status": "completed", "requires": []}]}
        events = [{"seq": 0, "node_id": "n", "kind": "reopen", "from_status": "completed", "to_status": "verifying", "evidence_refs": ["counter"]}]
        projection = project_checkpoint(plan, events, {"entries": [{"entry_id": "counter", "node_id": "n", "verdict": "fail", "assurance": "external"}]})
        self.assertEqual("verification_failed", projection.node_states["n"])

    def test_nested_completed_node_requires_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = ROOT / "examples" / "example_product_delivery"
            target = Path(temp) / "loop"
            import shutil
            shutil.copytree(source, target)
            ledger_path = target / "evidence.ledger.yaml"
            import yaml
            ledger = yaml.safe_load(ledger_path.read_text(encoding="utf-8"))
            ledger["entries"] = [entry for entry in ledger["entries"] if entry.get("node_id") != "impl_auth"]
            ledger_path.write_text(yaml.safe_dump(ledger, sort_keys=False), encoding="utf-8")
            problems, _checks = check_loop_dir(target)
            self.assertTrue(any("impl_auth" in problem and "R43" in problem for problem in problems))

    def test_whole_loop_rejects_unknown_evidence_node_and_allows_nested_node(self) -> None:
        source = ROOT / "examples" / "example_product_delivery"
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "loop"
            shutil.copytree(source, target)
            ledger_path = target / "evidence.ledger.yaml"
            ledger = yaml.safe_load(ledger_path.read_text(encoding="utf-8"))
            template = ledger["entries"][0]
            ledger["entries"].append(
                template
                | {
                    "entry_id": "ghost-evidence",
                    "node_id": "ghost",
                    "recorded": "2026-07-20T00:00:00Z",
                }
            )
            ledger_path.write_text(yaml.safe_dump(ledger, sort_keys=False), encoding="utf-8")
            problems, _checks = check_loop_dir(target)
            self.assertTrue(
                any("evidence-node" in problem and "ghost" in problem for problem in problems)
            )

            ledger["entries"][-1]["node_id"] = "impl_auth"
            ledger_path.write_text(yaml.safe_dump(ledger, sort_keys=False), encoding="utf-8")
            problems, _checks = check_loop_dir(target)
            self.assertFalse(any("evidence-node" in problem for problem in problems))

    def test_canonical_nodes_directory_is_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = ROOT / "examples" / "example_child_loop_tree" / "L001-example-delivery"
            target = Path(temp) / "loop"
            import shutil
            shutil.copytree(source, target)
            node_dir = target / "nodes" / "charter"
            node_dir.mkdir(parents=True)
            (node_dir / "node.contract.yaml").write_text("node_id: charter\n", encoding="utf-8")
            problems, checks = check_loop_dir(target)
            self.assertTrue(any("node-contract" in problem for problem in problems))
            self.assertIn("optional canonical node-contract validation", checks)


if __name__ == "__main__":
    unittest.main()
