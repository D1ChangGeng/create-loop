from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from project_loop import canonical_output_path, ProjectionError, project, workspace_root  # noqa: E402


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2) + "\n").encode("utf-8")


def record(
    seq: int,
    kind: str,
    payload: dict,
    *,
    node_id: str | None = None,
    record_id: str | None = None,
) -> dict:
    value = {
        "schema_version": "2.0",
        "seq": seq,
        "record_id": record_id or f"rec-{seq}",
        "ts": f"2026-07-31T00:{seq:02d}:00Z",
        "kind": kind,
        "actor": {"type": "model", "id": "test"},
        "plan_version": 1,
        "payload": payload,
    }
    if node_id is not None:
        value["node_id"] = node_id
    return value


def transition(
    seq: int,
    before: str,
    after: str,
    *,
    evidence_refs: list[str] | None = None,
    decision_refs: list[str] | None = None,
    node_id: str = "N1",
) -> dict:
    return record(
        seq,
        "transition",
        {
            "from": before,
            "to": after,
            "reason_code": "test",
            "reason": "Test transition.",
            "evidence_refs": evidence_refs or [],
            "decision_refs": decision_refs or [],
        },
        node_id=node_id,
    )


def fixture_check_binding(
    check: dict | None = None, *, plan_version: int = 1, node_id: str = "N1"
) -> dict:
    check = check or {
        "id": "check-N1",
        "method": "test",
        "instruction": "Run it.",
        "expected": "Pass.",
    }
    return {
        "plan_version": plan_version,
        "node_id": node_id,
        "check_id": check["id"],
        "check_sha256": hashlib.sha256(
            (json.dumps(check, sort_keys=True, separators=(",", ":")) + "\n").encode()
        ).hexdigest(),
    }


def evidence_payload(
    *,
    result: str = "pass",
    check_ref: str | None = "check-N1",
    subjects: list[str] | None = None,
    valid_until: str | None = None,
    review_context: dict | None = None,
    check_binding: dict | None | bool = None,
) -> dict:
    if check_ref is not None and check_binding is None:
        check_binding = fixture_check_binding()
    return {
        "subject_refs": subjects or ["node:N1", "criterion:SC1"],
        "check_ref": check_ref,
        "source_class": "direct_test",
        "origin_ref": "tool:test",
        "artifact_ref": None,
        "observed_result": result,
        "summary": "Observed result.",
        "limits": "Fixture scope only.",
        "valid_until": valid_until,
        "recheck_when": "Inputs change.",
        "review_context": review_context,
        **({"check_binding": check_binding} if isinstance(check_binding, dict) else {}),
    }
def legacy_import(
    node_states: dict[str, str],
    *,
    seq: int = 1,
    actor_type: str = "migrator",
    record_id: str = "legacy-import",
) -> dict:
    event_hash = "a" * 64
    checkpoint_hash = "b" * 64
    value = record(
        seq,
        "legacy_import",
        {
            "source_hashes": {
                "event_log.jsonl": event_hash,
                "checkpoint.yaml": checkpoint_hash,
            },
            "source": {
                "event_log_ref": "event_log.jsonl",
                "event_log_sha256": event_hash,
                "checkpoint_sha256": checkpoint_hash,
                "last_event_seq": 0,
            },
            "node_states": node_states,
            "closed_effects": [],
            "warnings": [],
        },
        record_id=record_id,
    )
    value["actor"] = {"type": actor_type, "id": "test-migrator"}
    value.pop("plan_version", None)
    return value


def write_migration_report(root: Path, records: list[dict]) -> None:
    source_hashes = records[0]["payload"]["source_hashes"]
    journal_hash = hashlib.sha256(
        b"".join(
            (
                json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                + "\n"
            ).encode("utf-8")
            for item in records
        )
    ).hexdigest()
    (root / "migration-report.json").write_bytes(
        json_bytes(
            {
                "schema_version": "2.0",
                "source": "legacy-source",
                "destination": str(root),
                "dry_run": False,
                "source_hashes": source_hashes,
                "journal_last_seq": records[-1]["seq"],
                "journal_sha256": journal_hash,
                "mapped_files": ["goal.json", "plans/plan-v1.json", "journal.jsonl", "resume.json", "migration-report.json"],
                "warnings": [],
            }
        )
    )


def effect_pre_payload() -> dict:
    return {
        "effect_id": "deploy",
        "attempt_id": "attempt-1",
        "operation": "deploy",
        "target": "staging",
        "idempotency_key": "deploy-attempt-1",
        "authorization_decision_ref": None,
        "authorization_boundary_ref": None,
        "expected_postcondition": "Deployment is healthy.",
        "compensation_ref": None,
    }


class LoopFixture:
    def __init__(self, parent: Path, *, modules: list[str] | None = None):
        self.root = parent / "loop"
        (self.root / "plans").mkdir(parents=True)
        self.goal = {
            "schema_version": "2.0",
            "loop_id": "L900",
            "goal": "Deliver a verified result.",
            "intent": "Retain only directly verified state.",
            "scope": {"in": ["Implementation"], "out": []},
            "success_criteria": [
                {"id": "SC1", "statement": "The result passes.", "expected_evidence": "Direct output."}
            ],
            "constraints": [],
            "authorization_boundaries": [],
            "stop_conditions": [],
            "created_at": "2026-07-31T00:00:00Z",
        }
        (self.root / "goal.json").write_bytes(json_bytes(self.goal))
        self.plan = {
            "schema_version": "2.0",
            "plan_id": "plan-L900-v1",
            "plan_version": 1,
            "goal_sha256": hashlib.sha256((self.root / "goal.json").read_bytes()).hexdigest(),
            "created_at": "2026-07-31T00:00:00Z",
            "control": {
                "mode": "governed" if modules else "persistent",
                "modules": modules or [],
                "admission_reason": "Durable verification is required.",
            },
            "nodes": [
                {
                    "id": "N1",
                    "objective": "Produce the result.",
                    "depends_on": [],
                    "success_criteria_refs": ["SC1"],
                    "outputs": [],
                    "checks": [
                        {"id": "check-N1", "method": "test", "instruction": "Run it.", "expected": "Pass."}
                    ],
                    "authorization_refs": [],
                }
            ],
        }
        self.records: list[dict] = []
        self.rewrite_plan()

    def rewrite_plan(self) -> None:
        plan_path = self.root / "plans" / "plan-v1.json"
        plan_path.write_bytes(json_bytes(self.plan))
        activation = record(
            1,
            "plan_activated",
            {
                "plan_ref": "plans/plan-v1.json",
                "plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                "previous_version": None,
                "reason": "Initial plan.",
                "evidence_refs": [],
                "decision_ref": None,
            },
        )
        if self.records:
            self.records[0] = activation
        else:
            self.records.append(activation)

    def save(self) -> None:
        with (self.root / "journal.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for item in self.records:
                handle.write(json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n")
        if self.records and self.records[0].get("kind") == "legacy_import":
            write_migration_report(self.root, self.records)

    def assert_rejects(self, testcase: unittest.TestCase, pattern: str) -> None:
        self.save()
        with testcase.assertRaisesRegex(ProjectionError, pattern):
            project(self.root, generated_at="2026-07-31T01:00:00Z")

    def complete_node(self) -> None:
        self.records += [
            record(2, "evidence", evidence_payload(), node_id="N1", record_id="ev-pass"),
            transition(3, "pending", "active"),
            transition(4, "active", "verifying", evidence_refs=["ev-pass"]),
            transition(5, "verifying", "done", evidence_refs=["ev-pass"]),
        ]

    def require_authorization(self, authority: str) -> None:
        self.goal["authorization_boundaries"] = [{
            "id": "AUTH1",
            "action": "Start protected work.",
            "authority": authority,
            "trigger": "Before N1 becomes active.",
        }]
        goal_path = self.root / "goal.json"
        goal_path.write_bytes(json_bytes(self.goal))
        self.plan["goal_sha256"] = hashlib.sha256(goal_path.read_bytes()).hexdigest()
        self.plan["nodes"][0]["authorization_refs"] = ["AUTH1"]
        self.rewrite_plan()


class ProjectorHardeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.fixture = LoopFixture(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def activate_replan(
        self,
        plan: dict,
        *,
        seq: int,
        evidence_ref: str | None = None,
        decision_ref: str | None = None,
    ) -> None:
        evidence_ref = evidence_ref or f"replan-cause-{plan['plan_version']}"
        decision_ref = decision_ref or f"replan-decision-{plan['plan_version']}"
        prior_plan_path = self.fixture.root / "plans" / f"plan-v{plan['plan_version'] - 1}.json"
        plan_path = self.fixture.root / "plans" / f"plan-v{plan['plan_version']}.json"
        plan_path.write_bytes(json_bytes(plan))
        plan_hash = hashlib.sha256(plan_path.read_bytes()).hexdigest()
        existing = {item["record_id"] for item in self.fixture.records}
        next_seq = seq
        if evidence_ref not in existing:
            causal_evidence = record(
                next_seq,
                "evidence",
                evidence_payload(check_ref=None, subjects=["criterion:SC1"]),
                record_id=evidence_ref,
            )
            causal_evidence["plan_version"] = plan["plan_version"] - 1
            self.fixture.records.append(causal_evidence)
            next_seq += 1
        if decision_ref not in existing:
            decision = record(
                next_seq,
                "decision",
                {
                    "question": "plan_replacement",
                    "outcome": f"Activate plan v{plan['plan_version']}.",
                    "rationale": "The cited evidence changes the executable plan.",
                    "authority": "model",
                    "evidence_refs": [evidence_ref],
                    "authorization_boundary_ref": None,
                    "reconsider_when": "The causal evidence changes.",
                    "overrides_evidence_ref": None,
                    "plan_change": {
                        "from_plan_version": plan["plan_version"] - 1,
                        "from_plan_sha256": hashlib.sha256(prior_plan_path.read_bytes()).hexdigest(),
                        "to_plan_version": plan["plan_version"],
                        "to_plan_sha256": plan_hash,
                    },
                },
                record_id=decision_ref,
            )
            decision["plan_version"] = plan["plan_version"] - 1
            self.fixture.records.append(decision)
            next_seq += 1
        activation = record(
            next_seq,
            "plan_activated",
            {
                "plan_ref": f"plans/plan-v{plan['plan_version']}.json",
                "plan_sha256": plan_hash,
                "previous_version": plan["plan_version"] - 1,
                "reason": "Replan check semantics.",
                "evidence_refs": [evidence_ref],
                "decision_ref": decision_ref,
            },
        )
        activation["plan_version"] = plan["plan_version"]
        self.fixture.records.append(activation)

    @staticmethod
    def renumber(records: list[dict], start: int = 1) -> None:
        for seq, item in enumerate(records, start=start):
            item["seq"] = seq
            item["ts"] = f"2026-07-31T00:{seq:02d}:00Z"
            if item.get("record_id", "").startswith("rec-"):
                item["record_id"] = f"rec-{seq}"

    def test_noninitial_replan_requires_causal_evidence_and_decision(self):
        plan_v2 = copy.deepcopy(self.fixture.plan)
        plan_v2.update({"plan_id": "plan-L900-v2", "plan_version": 2})
        plan_path = self.fixture.root / "plans" / "plan-v2.json"
        plan_path.write_bytes(json_bytes(plan_v2))
        activation = record(
            2,
            "plan_activated",
            {
                "plan_ref": "plans/plan-v2.json",
                "plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                "previous_version": 1,
                "reason": "Uncaused replan.",
                "evidence_refs": [],
                "decision_ref": None,
            },
            record_id="activation-v2",
        )
        activation["plan_version"] = 2
        self.fixture.records.append(activation)
        self.fixture.assert_rejects(
            self, "expected at least 1 item|requires causal evidence and a prior decision"
        )

    def test_replan_decision_binds_exact_old_and_new_plans(self):
        plan_v2 = copy.deepcopy(self.fixture.plan)
        plan_v2.update({"plan_id": "plan-L900-v2", "plan_version": 2})
        self.activate_replan(plan_v2, seq=2)
        decision = self.fixture.records[-2]["payload"]
        mutations = (
            lambda change: change.update({"from_plan_version": 2}),
            lambda change: change.update({"to_plan_version": 3}),
            lambda change: change.update({"from_plan_sha256": "0" * 64}),
            lambda change: change.update({"to_plan_sha256": "0" * 64}),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                original = copy.deepcopy(decision["plan_change"])
                mutate(decision["plan_change"])
                self.fixture.assert_rejects(self, "must bind the exact active and candidate")
                decision["plan_change"] = original

        decision["question"] = "Which plan should replace the active plan?"
        self.fixture.assert_rejects(self, "must bind the exact active and candidate")

    def test_old_plan_check_failure_can_cause_changed_check_replan(self):
        old_failure = record(
            2,
            "evidence",
            evidence_payload(result="fail"),
            node_id="N1",
            record_id="old-check-fail",
        )
        self.fixture.records.append(old_failure)
        plan_v2 = copy.deepcopy(self.fixture.plan)
        plan_v2.update({"plan_id": "plan-L900-v2", "plan_version": 2})
        plan_v2["nodes"][0]["checks"][0]["instruction"] = "Run the corrected check."
        self.activate_replan(plan_v2, seq=3, evidence_ref="old-check-fail")
        self.fixture.save()
        projection = project(self.fixture.root)
        self.assertEqual(projection["source"]["plan_version"], 2)

    def test_ordinary_replan_rejects_control_only_trigger(self):
        plan_v2 = copy.deepcopy(self.fixture.plan)
        plan_v2.update({"plan_id": "plan-L900-v2", "plan_version": 2})
        self.activate_replan(plan_v2, seq=2)
        self.fixture.records[-3]["payload"]["source_class"] = "control_trigger"
        self.fixture.assert_rejects(self, "cannot use a control-only upgrade trigger")

    def test_ordinary_replan_rejects_challenged_causal_evidence(self):
        plan_v2 = copy.deepcopy(self.fixture.plan)
        plan_v2.update({"plan_id": "plan-L900-v2", "plan_version": 2})
        self.activate_replan(plan_v2, seq=2)
        cause = self.fixture.records[-3]
        challenge = record(
            3,
            "evidence",
            evidence_payload(result="fail", check_ref=None, subjects=["criterion:SC1"]),
            record_id="replan-challenge",
        )
        relation = record(
            4,
            "evidence_relation",
            {
                "source_evidence_ref": "replan-challenge",
                "target_evidence_ref": cause["record_id"],
                "relation": "challenges",
                "reason": "The alleged cause is disputed.",
            },
            record_id="challenge-replan-cause",
        )
        decision = self.fixture.records[-2]
        activation = self.fixture.records[-1]
        decision["seq"], decision["ts"] = 5, "2026-07-31T00:05:00Z"
        activation["seq"], activation["ts"] = 6, "2026-07-31T00:06:00Z"
        self.fixture.records = [self.fixture.records[0], cause, challenge, relation, decision, activation]
        self.fixture.assert_rejects(self, "cannot cite challenged evidence")

    def test_replan_decision_must_be_recorded_under_prior_plan(self):
        plan_v2 = copy.deepcopy(self.fixture.plan)
        plan_v2.update({"plan_id": "plan-L900-v2", "plan_version": 2})
        self.activate_replan(plan_v2, seq=2)
        self.fixture.records[-2]["plan_version"] = 2
        self.fixture.assert_rejects(self, "record plan_version is not active|recorded under the prior plan")

    def test_replan_rejects_old_decision_reuse_and_evidence_mismatch(self):
        plan_v2 = copy.deepcopy(self.fixture.plan)
        plan_v2.update({"plan_id": "plan-L900-v2", "plan_version": 2})
        self.activate_replan(plan_v2, seq=2)
        plan_v3 = copy.deepcopy(plan_v2)
        plan_v3.update({"plan_id": "plan-L900-v3", "plan_version": 3})
        self.activate_replan(
            plan_v3,
            seq=5,
            evidence_ref="replan-cause-2",
            decision_ref="replan-decision-2",
        )
        self.fixture.assert_rejects(self, "must bind the exact active and candidate")

        self.fixture.records = self.fixture.records[:4]
        different = copy.deepcopy(self.fixture.records[1])
        different["seq"] = 4
        different["record_id"] = "different-evidence"
        different["ts"] = "2026-07-31T00:04:00Z"
        self.fixture.records.insert(3, different)
        self.fixture.records[-1]["seq"] = 5
        self.fixture.records[-1]["ts"] = "2026-07-31T00:05:00Z"
        self.fixture.records[-1]["payload"]["evidence_refs"] = ["different-evidence"]
        self.fixture.assert_rejects(self, "cite exactly")

    def test_removed_node_id_cannot_be_reintroduced(self):
        self.fixture.complete_node()

        plan_v2 = copy.deepcopy(self.fixture.plan)
        plan_v2.update({"plan_id": "plan-L900-v2", "plan_version": 2})
        plan_v2["nodes"] = [{
            "id": "N2",
            "objective": "Temporary replacement.",
            "depends_on": [],
            "success_criteria_refs": ["SC1"],
            "outputs": [],
            "checks": [{"id": "check-N2", "method": "test", "instruction": "Run N2.", "expected": "Pass."}],
            "authorization_refs": [],
        }]
        self.activate_replan(plan_v2, seq=6)

        plan_v3 = copy.deepcopy(plan_v2)
        plan_v3.update({"plan_id": "plan-L900-v3", "plan_version": 3})
        plan_v3["nodes"].append({
            "id": "N1",
            "objective": "A different objective must not inherit old state.",
            "depends_on": [],
            "success_criteria_refs": ["SC1"],
            "outputs": [],
            "checks": [{"id": "check-N1", "method": "test", "instruction": "Run new N1.", "expected": "Pass."}],
            "authorization_refs": [],
        })
        self.activate_replan(plan_v3, seq=9)
        self.fixture.assert_rejects(self, "cannot be reintroduced after removal")

    def test_windows_device_basename_detection_is_narrow(self):
        for path in ("CON", "reports/aux.md", "COM1.log", "nested/lpt9"):
            with self.subTest(path=path), self.assertRaises(ProjectionError):
                canonical_output_path(path)

        for path in ("console.txt", "com10.log", "lpt0", "auxiliary.md", "conduit/result.txt"):
            with self.subTest(path=path):
                self.assertEqual(canonical_output_path(path), path)

    def test_authorization_rejects_actor_id_spoofing(self):
        for authority in ("user", "tool", "reviewer"):
            with self.subTest(authority=authority):
                fixture = LoopFixture(Path(self.temp.name) / f"spoof-{authority}")
                fixture.require_authorization(authority)
                decision = record(
                    2,
                    "decision",
                    {
                        "question": "May protected work start?",
                        "outcome": "approved",
                        "rationale": "Spoof attempt.",
                        "authority": authority,
                        "evidence_refs": [],
                        "authorization_boundary_ref": "AUTH1",
                        "reconsider_when": None,
                        "overrides_evidence_ref": None,
                    },
                    record_id="authorize-N1",
                )
                decision["actor"] = {"type": "model", "id": authority}
                fixture.records.append(decision)
                fixture.assert_rejects(self, "decision actor lacks the declared authority")

    def test_authorization_requires_payload_authority_match(self):
        self.fixture.require_authorization("user")
        decision = record(
            2,
            "decision",
            {
                "question": "May protected work start?",
                "outcome": "approved",
                "rationale": "The payload declares the wrong authority.",
                "authority": "model",
                "evidence_refs": [],
                "authorization_boundary_ref": "AUTH1",
                "reconsider_when": None,
                "overrides_evidence_ref": None,
            },
            record_id="authorize-N1",
        )
        decision["actor"] = {"type": "user", "id": "principal"}
        self.fixture.records.append(decision)
        self.fixture.assert_rejects(self, "decision actor lacks the declared authority")

    def test_authorization_accepts_exact_actor_types(self):
        for authority in ("user", "model", "tool", "reviewer"):
            with self.subTest(authority=authority):
                fixture = LoopFixture(Path(self.temp.name) / f"control-{authority}")
                fixture.require_authorization(authority)
                decision = record(
                    2,
                    "decision",
                    {
                        "question": "May protected work start?",
                        "outcome": "approved",
                        "rationale": "The declared authority approved it.",
                        "authority": authority,
                        "evidence_refs": [],
                        "authorization_boundary_ref": "AUTH1",
                        "reconsider_when": None,
                        "overrides_evidence_ref": None,
                    },
                    record_id="authorize-N1",
                )
                decision["actor"] = {"type": authority, "id": "principal"}
                fixture.records += [decision, transition(3, "pending", "active")]
                fixture.save()
                self.assertEqual(
                    project(fixture.root, generated_at="2026-07-31T01:00:00Z")
                    ["projection"]["node_states"],
                    {"N1": "active"},
                )

    def test_evidence_relation_rejects_older_source_for_newer_target(self):
        self.fixture.records += [
            record(2, "evidence", evidence_payload(), node_id="N1", record_id="old-pass"),
            record(3, "evidence", evidence_payload(result="fail"), node_id="N1", record_id="new-fail"),
            record(
                4,
                "evidence_relation",
                {
                    "source_evidence_ref": "old-pass",
                    "target_evidence_ref": "new-fail",
                    "relation": "supersedes",
                    "reason": "An old pass cannot retire a newer failure.",
                },
                record_id="inverted-relation",
            ),
        ]
        self.fixture.assert_rejects(self, "EVIDENCE-ORDER.*source evidence must be newer")

    def test_evidence_relation_accepts_newer_source_for_older_target(self):
        self.fixture.records += [
            record(2, "evidence", evidence_payload(result="fail"), node_id="N1", record_id="old-fail"),
            record(3, "evidence", evidence_payload(), node_id="N1", record_id="new-pass"),
            record(
                4,
                "evidence_relation",
                {
                    "source_evidence_ref": "new-pass",
                    "target_evidence_ref": "old-fail",
                    "relation": "supersedes",
                    "reason": "A fresh pass replaces the older failed observation.",
                },
                record_id="forward-relation",
            ),
        ]
        self.fixture.save()
        projection = project(self.fixture.root, generated_at="2026-07-31T01:00:00Z")
        self.assertIn("new-pass", projection["recovery_refs"]["confirmed_evidence"])
        self.assertNotIn("old-fail", projection["recovery_refs"]["confirmed_evidence"])

    def test_evidence_relation_rejects_partial_subject_supersession_false_completion(self):
        self.fixture.records += [
            record(2, "evidence", evidence_payload(result="fail", check_ref=None), record_id="criterion-fail"),
            record(
                3,
                "evidence",
                evidence_payload(check_ref=None, subjects=["node:N1"]),
                node_id="N1",
                record_id="node-only-pass",
            ),
            record(
                4,
                "evidence_relation",
                {
                    "source_evidence_ref": "node-only-pass",
                    "target_evidence_ref": "criterion-fail",
                    "relation": "supersedes",
                    "reason": "Node-only evidence cannot retire the criterion conclusion.",
                },
                record_id="partial-supersession",
            ),
            record(
                5,
                "evidence",
                evidence_payload(check_ref=None, subjects=["criterion:SC1"]),
                record_id="criterion-pass",
            ),
            record(
                6,
                "completion",
                {
                    "deliverables": [],
                    "criterion_evidence": {"SC1": ["criterion-pass"]},
                    "deterministic_check_refs": [],
                    "system_review_ref": None,
                    "counterexample_review_refs": [],
                    "residual_risks": [],
                    "unmet_scope": [],
                    "authorization_decision_refs": [],
                },
                record_id="false-completion",
            ),
        ]
        self.fixture.assert_rejects(self, "relation source must cover every target subject")

    def test_evidence_relation_rejects_partial_subject_invalidation_false_completion(self):
        self.fixture.records += [
            record(2, "evidence", evidence_payload(result="fail", check_ref=None), record_id="criterion-fail"),
            record(
                3,
                "evidence",
                evidence_payload(result="fail", check_ref=None, subjects=["node:N1"]),
                node_id="N1",
                record_id="node-only-fail",
            ),
            record(
                4,
                "evidence_relation",
                {
                    "source_evidence_ref": "node-only-fail",
                    "target_evidence_ref": "criterion-fail",
                    "relation": "invalidates",
                    "reason": "Node-only counterevidence cannot invalidate the criterion conclusion.",
                },
                record_id="partial-invalidation",
            ),
            record(
                5,
                "evidence",
                evidence_payload(check_ref=None, subjects=["criterion:SC1"]),
                record_id="criterion-pass",
            ),
            record(
                6,
                "completion",
                {
                    "deliverables": [],
                    "criterion_evidence": {"SC1": ["criterion-pass"]},
                    "deterministic_check_refs": [],
                    "system_review_ref": None,
                    "counterexample_review_refs": [],
                    "residual_risks": [],
                    "unmet_scope": [],
                    "authorization_decision_refs": [],
                },
                record_id="false-completion",
            ),
        ]
        self.fixture.assert_rejects(self, "relation source must cover every target subject")

    def test_evidence_relation_accepts_source_covering_all_target_subjects(self):
        subjects = ["node:N1", "criterion:SC1", "artifact:result"]
        self.fixture.records += [
            record(
                2,
                "evidence",
                evidence_payload(result="fail", check_ref=None, subjects=subjects[:2]),
                record_id="old-fail",
            ),
            record(
                3,
                "evidence",
                evidence_payload(check_ref=None, subjects=subjects),
                record_id="new-pass",
            ),
            record(
                4,
                "evidence_relation",
                {
                    "source_evidence_ref": "new-pass",
                    "target_evidence_ref": "old-fail",
                    "relation": "supersedes",
                    "reason": "Fresh evidence covers all prior subjects and one additional artifact.",
                },
                record_id="complete-supersession",
            ),
        ]
        self.fixture.save()
        projection = project(self.fixture.root, generated_at="2026-07-31T01:00:00Z")
        self.assertIn("new-pass", projection["recovery_refs"]["confirmed_evidence"])
        self.assertNotIn("old-fail", projection["recovery_refs"]["confirmed_evidence"])

    def test_evidence_relation_rejects_challenged_source_false_completion(self):
        shared = ["artifact:shared"]
        self.fixture.records += [
            record(
                2,
                "evidence",
                evidence_payload(
                    result="fail",
                    check_ref=None,
                    subjects=["criterion:SC1", *shared],
                ),
                record_id="criterion-fail",
            ),
            record(
                3,
                "evidence",
                evidence_payload(result="fail", check_ref=None, subjects=["criterion:SC1", *shared]),
                record_id="challenged-source",
            ),
            record(
                4,
                "evidence",
                evidence_payload(result="fail", check_ref=None, subjects=["criterion:SC1", *shared]),
                record_id="challenge",
            ),
            record(
                5,
                "evidence_relation",
                {
                    "source_evidence_ref": "challenge",
                    "target_evidence_ref": "challenged-source",
                    "relation": "challenges",
                    "reason": "The proposed counterevidence is itself disputed.",
                },
                record_id="challenge-source",
            ),
            record(
                6,
                "evidence_relation",
                {
                    "source_evidence_ref": "challenged-source",
                    "target_evidence_ref": "criterion-fail",
                    "relation": "invalidates",
                    "reason": "A challenged source must not hide criterion failure.",
                },
                record_id="challenged-invalidation",
            ),
            record(
                7,
                "evidence",
                evidence_payload(check_ref=None, subjects=["criterion:SC1"]),
                record_id="criterion-pass",
            ),
            record(
                8,
                "completion",
                {
                    "deliverables": [],
                    "criterion_evidence": {"SC1": ["criterion-pass"]},
                    "deterministic_check_refs": [],
                    "system_review_ref": None,
                    "counterexample_review_refs": [],
                    "residual_risks": [],
                    "unmet_scope": [],
                    "authorization_decision_refs": [],
                },
                record_id="false-completion",
            ),
        ]
        self.fixture.assert_rejects(self, "EVIDENCE-CURRENT.*must not be challenged")

    def test_resolved_challenge_restores_relation_source_currentness(self):
        shared = ["artifact:shared"]
        self.fixture.records += [
            record(
                2,
                "evidence",
                evidence_payload(
                    result="fail",
                    check_ref=None,
                    subjects=["criterion:SC1", *shared],
                ),
                record_id="criterion-fail",
            ),
            record(
                3,
                "evidence",
                evidence_payload(check_ref=None, subjects=["criterion:SC1", *shared]),
                record_id="restored-source",
            ),
            record(
                4,
                "evidence",
                evidence_payload(result="fail", check_ref=None, subjects=["criterion:SC1", *shared]),
                record_id="challenge",
            ),
            record(
                5,
                "evidence_relation",
                {
                    "source_evidence_ref": "challenge",
                    "target_evidence_ref": "restored-source",
                    "relation": "challenges",
                    "reason": "The source needs independent confirmation.",
                },
                record_id="challenge-source",
            ),
            record(
                6,
                "evidence",
                evidence_payload(check_ref=None, subjects=["criterion:SC1", *shared]),
                record_id="challenge-resolution",
            ),
            record(
                7,
                "evidence_relation",
                {
                    "source_evidence_ref": "challenge-resolution",
                    "target_evidence_ref": "challenge",
                    "relation": "confirms",
                    "reason": "A newer direct pass resolves the exact challenge.",
                },
                record_id="resolve-challenge",
            ),
            record(
                8,
                "evidence_relation",
                {
                    "source_evidence_ref": "restored-source",
                    "target_evidence_ref": "criterion-fail",
                    "relation": "supersedes",
                    "reason": "The resolved current source may now affect older evidence.",
                },
                record_id="current-invalidation",
            ),
            record(
                9,
                "evidence",
                evidence_payload(check_ref=None, subjects=["criterion:SC1"]),
                record_id="criterion-pass",
            ),
            record(
                10,
                "completion",
                {
                    "deliverables": [],
                    "criterion_evidence": {"SC1": ["criterion-pass"]},
                    "deterministic_check_refs": [],
                    "system_review_ref": None,
                    "counterexample_review_refs": [],
                    "residual_risks": [],
                    "unmet_scope": [],
                    "authorization_decision_refs": [],
                },
                record_id="completion-1",
            ),
        ]
        self.fixture.save()
        projection = project(self.fixture.root, generated_at="2026-07-31T01:00:00Z")
        self.assertEqual(projection["projection"]["loop_status"], "completed")

    def test_later_challenge_retracts_prior_invalidation(self):
        shared = ["artifact:shared"]
        self.fixture.records += [
            record(
                2,
                "evidence",
                evidence_payload(
                    result="fail",
                    check_ref=None,
                    subjects=["criterion:SC1", *shared],
                ),
                record_id="criterion-fail",
            ),
            record(
                3,
                "evidence",
                evidence_payload(result="fail", check_ref=None, subjects=["criterion:SC1", *shared]),
                record_id="invalidation-source",
            ),
            record(
                4,
                "evidence_relation",
                {
                    "source_evidence_ref": "invalidation-source",
                    "target_evidence_ref": "criterion-fail",
                    "relation": "invalidates",
                    "reason": "The source initially disputes the criterion failure.",
                },
                record_id="initial-invalidation",
            ),
            record(
                5,
                "evidence",
                evidence_payload(result="fail", check_ref=None, subjects=["criterion:SC1", *shared]),
                record_id="later-challenge",
            ),
            record(
                6,
                "evidence_relation",
                {
                    "source_evidence_ref": "later-challenge",
                    "target_evidence_ref": "invalidation-source",
                    "relation": "challenges",
                    "reason": "The invalidation source is no longer trustworthy.",
                },
                record_id="challenge-invalidation-source",
            ),
            record(
                7,
                "evidence",
                evidence_payload(check_ref=None, subjects=["criterion:SC1"]),
                record_id="criterion-pass",
            ),
            record(
                8,
                "completion",
                {
                    "deliverables": [],
                    "criterion_evidence": {"SC1": ["criterion-pass"]},
                    "deterministic_check_refs": [],
                    "system_review_ref": None,
                    "counterexample_review_refs": [],
                    "residual_risks": [],
                    "unmet_scope": [],
                    "authorization_decision_refs": [],
                },
                record_id="false-completion",
            ),
        ]
        self.fixture.assert_rejects(self, "unresolved criterion evidence.*criterion-fail")

    def test_confirming_later_challenge_reactivates_prior_supersession(self):
        shared = ["artifact:shared"]
        self.fixture.records += [
            record(
                2,
                "evidence",
                evidence_payload(
                    result="fail",
                    check_ref=None,
                    subjects=["criterion:SC1", *shared],
                ),
                record_id="criterion-fail",
            ),
            record(
                3,
                "evidence",
                evidence_payload(check_ref=None, subjects=["criterion:SC1", *shared]),
                record_id="supersession-source",
            ),
            record(
                4,
                "evidence_relation",
                {
                    "source_evidence_ref": "supersession-source",
                    "target_evidence_ref": "criterion-fail",
                    "relation": "supersedes",
                    "reason": "The source initially replaces the criterion failure.",
                },
                record_id="initial-supersession",
            ),
            record(
                5,
                "evidence",
                evidence_payload(result="fail", check_ref=None, subjects=["criterion:SC1", *shared]),
                record_id="later-challenge",
            ),
            record(
                6,
                "evidence_relation",
                {
                    "source_evidence_ref": "later-challenge",
                    "target_evidence_ref": "supersession-source",
                    "relation": "challenges",
                    "reason": "The superseding source needs confirmation.",
                },
                record_id="challenge-supersession-source",
            ),
            record(
                7,
                "evidence",
                evidence_payload(check_ref=None, subjects=["criterion:SC1", *shared]),
                record_id="challenge-resolution",
            ),
            record(
                8,
                "evidence_relation",
                {
                    "source_evidence_ref": "challenge-resolution",
                    "target_evidence_ref": "later-challenge",
                    "relation": "confirms",
                    "reason": "The later challenge is resolved by direct evidence.",
                },
                record_id="resolve-later-challenge",
            ),
            record(
                9,
                "evidence",
                evidence_payload(check_ref=None, subjects=["criterion:SC1"]),
                record_id="criterion-pass",
            ),
            record(
                10,
                "completion",
                {
                    "deliverables": [],
                    "criterion_evidence": {"SC1": ["criterion-pass"]},
                    "deterministic_check_refs": [],
                    "system_review_ref": None,
                    "counterexample_review_refs": [],
                    "residual_risks": [],
                    "unmet_scope": [],
                    "authorization_decision_refs": [],
                },
                record_id="completion-1",
            ),
        ]
        self.fixture.save()
        projection = project(self.fixture.root, generated_at="2026-07-31T01:00:00Z")
        self.assertEqual(projection["projection"]["loop_status"], "completed")

    def test_challenging_confirmation_retracts_cascading_relation_effects(self):
        shared = ["artifact:shared"]
        self.fixture.records += [
            record(
                2,
                "evidence",
                evidence_payload(
                    result="fail",
                    check_ref=None,
                    subjects=["criterion:SC1", *shared],
                ),
                record_id="criterion-fail",
            ),
            record(
                3,
                "evidence",
                evidence_payload(result="fail", check_ref=None, subjects=["criterion:SC1", *shared]),
                record_id="invalidation-source",
            ),
            record(
                4,
                "evidence_relation",
                {
                    "source_evidence_ref": "invalidation-source",
                    "target_evidence_ref": "criterion-fail",
                    "relation": "invalidates",
                    "reason": "The source initially disputes the criterion failure.",
                },
                record_id="initial-invalidation",
            ),
            record(
                5,
                "evidence",
                evidence_payload(result="fail", check_ref=None, subjects=["criterion:SC1", *shared]),
                record_id="later-challenge",
            ),
            record(
                6,
                "evidence_relation",
                {
                    "source_evidence_ref": "later-challenge",
                    "target_evidence_ref": "invalidation-source",
                    "relation": "challenges",
                    "reason": "The invalidation source needs confirmation.",
                },
                record_id="challenge-invalidation-source",
            ),
            record(
                7,
                "evidence",
                evidence_payload(check_ref=None, subjects=["criterion:SC1", *shared]),
                record_id="challenge-resolution",
            ),
            record(
                8,
                "evidence_relation",
                {
                    "source_evidence_ref": "challenge-resolution",
                    "target_evidence_ref": "later-challenge",
                    "relation": "confirms",
                    "reason": "The later challenge is initially resolved.",
                },
                record_id="resolve-later-challenge",
            ),
            record(
                9,
                "evidence",
                evidence_payload(result="fail", check_ref=None, subjects=["criterion:SC1", *shared]),
                record_id="resolution-challenge",
            ),
            record(
                10,
                "evidence_relation",
                {
                    "source_evidence_ref": "resolution-challenge",
                    "target_evidence_ref": "challenge-resolution",
                    "relation": "challenges",
                    "reason": "The purported resolution is itself disputed.",
                },
                record_id="challenge-resolution-source",
            ),
            record(
                11,
                "evidence",
                evidence_payload(check_ref=None, subjects=["criterion:SC1"]),
                record_id="criterion-pass",
            ),
            record(
                12,
                "completion",
                {
                    "deliverables": [],
                    "criterion_evidence": {"SC1": ["criterion-pass"]},
                    "deterministic_check_refs": [],
                    "system_review_ref": None,
                    "counterexample_review_refs": [],
                    "residual_risks": [],
                    "unmet_scope": [],
                    "authorization_decision_refs": [],
                },
                record_id="false-completion",
            ),
        ]
        self.fixture.assert_rejects(self, "unresolved criterion evidence.*criterion-fail")

    def test_expired_relation_source_reactivates_target(self):
        self.fixture.records += [
            record(
                2,
                "evidence",
                evidence_payload(
                    result="fail",
                    check_ref=None,
                    subjects=["criterion:SC1"],
                ),
                record_id="criterion-fail",
            ),
            record(
                3,
                "evidence",
                evidence_payload(
                    check_ref=None,
                    subjects=["criterion:SC1"],
                    valid_until="2026-07-31T00:30:00Z",
                ),
                record_id="temporary-pass",
            ),
            record(
                4,
                "evidence_relation",
                {
                    "source_evidence_ref": "temporary-pass",
                    "target_evidence_ref": "criterion-fail",
                    "relation": "supersedes",
                    "reason": "The temporary observation initially replaces the failure.",
                },
                record_id="temporary-supersession",
            ),
            record(
                5,
                "completion",
                {
                    "deliverables": [],
                    "criterion_evidence": {"SC1": ["temporary-pass"]},
                    "deterministic_check_refs": [],
                    "system_review_ref": None,
                    "counterexample_review_refs": [],
                    "residual_risks": [],
                    "unmet_scope": [],
                    "authorization_decision_refs": [],
                },
                record_id="completion-1",
            ),
        ]
        self.fixture.assert_rejects(self, "active completion was invalidated, challenged, or expired")

    def test_confirmed_post_completion_challenge_does_not_require_reopen(self):
        subjects = ["criterion:SC1"]
        self.fixture.records += [
            record(
                2,
                "evidence",
                evidence_payload(check_ref=None, subjects=subjects),
                record_id="criterion-pass",
            ),
            record(
                3,
                "completion",
                {
                    "deliverables": [],
                    "criterion_evidence": {"SC1": ["criterion-pass"]},
                    "deterministic_check_refs": [],
                    "system_review_ref": None,
                    "counterexample_review_refs": [],
                    "residual_risks": [],
                    "unmet_scope": [],
                    "authorization_decision_refs": [],
                },
                record_id="completion-1",
            ),
            record(
                4,
                "evidence",
                evidence_payload(result="fail", check_ref=None, subjects=subjects),
                record_id="challenge",
            ),
            record(
                5,
                "evidence_relation",
                {
                    "source_evidence_ref": "challenge",
                    "target_evidence_ref": "criterion-pass",
                    "relation": "challenges",
                    "reason": "A reported regression challenges the completion evidence.",
                },
                record_id="challenge-completion",
            ),
            record(
                6,
                "evidence",
                evidence_payload(check_ref=None, subjects=subjects),
                record_id="challenge-resolution",
            ),
            record(
                7,
                "evidence_relation",
                {
                    "source_evidence_ref": "challenge-resolution",
                    "target_evidence_ref": "challenge",
                    "relation": "confirms",
                    "reason": "A direct retest resolves the exact challenge.",
                },
                record_id="resolve-challenge",
            ),
        ]
        self.fixture.save()
        projection = project(self.fixture.root, generated_at="2026-07-31T01:00:00Z")
        self.assertEqual(projection["projection"]["loop_status"], "completed")

    def test_generated_at_cannot_precede_journal_tail(self):
        self.fixture.records.append(
            record(2, "evidence", evidence_payload(), node_id="N1", record_id="ev-pass")
        )
        self.fixture.save()
        with self.assertRaisesRegex(ProjectionError, "generated_at cannot precede the journal tail"):
            project(self.fixture.root, generated_at="2026-07-31T00:01:00Z")

    def test_replan_changed_check_retracts_prior_relation_effect(self):
        check_binding = fixture_check_binding()
        self.fixture.records += [
            record(
                2,
                "evidence",
                evidence_payload(
                    result="fail",
                    subjects=["node:N1", "criterion:SC1", "artifact:failure"],
                    check_binding=check_binding,
                ),
                node_id="N1",
                record_id="criterion-fail",
            ),
            record(
                3,
                "evidence",
                evidence_payload(
                    subjects=["node:N1", "criterion:SC1", "artifact:failure"]
                ),
                node_id="N1",
                record_id="old-check-source",
            ),
            record(
                4,
                "evidence_relation",
                {
                    "source_evidence_ref": "old-check-source",
                    "target_evidence_ref": "criterion-fail",
                    "relation": "supersedes",
                    "reason": "The old check initially replaces the failure.",
                },
                record_id="old-check-supersession",
            ),
        ]
        plan_v2 = copy.deepcopy(self.fixture.plan)
        plan_v2.update({"plan_id": "plan-L900-v2", "plan_version": 2})
        plan_v2["nodes"][0]["checks"][0]["instruction"] = "Run the replacement check."
        self.activate_replan(plan_v2, seq=5)
        criterion_pass = record(
            6,
            "evidence",
            evidence_payload(check_ref=None, subjects=["criterion:SC1"]),
            record_id="criterion-pass-v2",
        )
        criterion_pass["plan_version"] = 2
        completion = record(
            7,
            "completion",
            {
                "deliverables": [],
                "criterion_evidence": {"SC1": ["criterion-pass-v2"]},
                "deterministic_check_refs": [],
                "system_review_ref": None,
                "counterexample_review_refs": [],
                "residual_risks": [],
                "unmet_scope": [],
                "authorization_decision_refs": [],
            },
            record_id="false-completion",
        )
        completion["plan_version"] = 2
        self.fixture.records += [criterion_pass, completion]
        self.renumber(self.fixture.records)
        self.fixture.save()
        projection = project(self.fixture.root, generated_at="2026-07-31T01:00:00Z")
        self.assertEqual(projection["projection"]["loop_status"], "completed")
        self.assertNotIn(
            "old-check-source", projection["recovery_refs"]["confirmed_evidence"]
        )

    def test_evidence_relation_rejects_stale_check_source_after_replan(self):
        self.fixture.records += [
            record(
                2,
                "evidence",
                evidence_payload(result="fail", check_ref=None),
                record_id="older-target",
            ),
            record(
                3,
                "evidence",
                evidence_payload(),
                node_id="N1",
                record_id="stale-check-source",
            ),
        ]
        plan_v2 = copy.deepcopy(self.fixture.plan)
        plan_v2.update({"plan_id": "plan-L900-v2", "plan_version": 2})
        plan_v2["nodes"][0]["checks"][0]["instruction"] = "Run the replacement check."
        self.activate_replan(plan_v2, seq=4)
        relation = record(
            5,
            "evidence_relation",
            {
                "source_evidence_ref": "stale-check-source",
                "target_evidence_ref": "older-target",
                "relation": "supersedes",
                "reason": "Changed check evidence is not current in plan v2.",
            },
            record_id="stale-source-relation",
        )
        relation["plan_version"] = 2
        self.fixture.records.append(relation)
        self.renumber(self.fixture.records)
        self.fixture.assert_rejects(
            self, "EVIDENCE-CURRENT.*does not match the active check definition"
        )

    def test_replan_rejects_stale_same_id_check_evidence(self):
        check = self.fixture.plan["nodes"][0]["checks"][0]
        binding = {
            "plan_version": 1,
            "node_id": "N1",
            "check_id": check["id"],
            "check_sha256": hashlib.sha256(
                (json.dumps(check, sort_keys=True, separators=(",", ":")) + "\n").encode()
            ).hexdigest(),
        }
        self.fixture.records.append(
            record(
                2,
                "evidence",
                evidence_payload(check_binding=binding),
                node_id="N1",
                record_id="old-pass",
            )
        )
        plan_v2 = copy.deepcopy(self.fixture.plan)
        plan_v2.update({"plan_id": "plan-L900-v2", "plan_version": 2})
        plan_v2["nodes"][0]["checks"][0]["instruction"] = "Run the stricter replacement."
        self.activate_replan(plan_v2, seq=3)
        for item in (
            transition(4, "pending", "active"),
            transition(5, "active", "verifying", evidence_refs=["old-pass"]),
            transition(6, "verifying", "done", evidence_refs=["old-pass"]),
        ):
            item["plan_version"] = 2
            self.fixture.records.append(item)
        self.renumber(self.fixture.records)
        self.fixture.assert_rejects(self, "missing check evidence")

    def test_replan_accepts_bound_evidence_for_unchanged_exact_check(self):
        check = self.fixture.plan["nodes"][0]["checks"][0]
        binding = {
            "plan_version": 1,
            "node_id": "N1",
            "check_id": check["id"],
            "check_sha256": hashlib.sha256(
                (json.dumps(check, sort_keys=True, separators=(",", ":")) + "\n").encode()
            ).hexdigest(),
        }
        self.fixture.records.append(
            record(
                2,
                "evidence",
                evidence_payload(check_binding=binding),
                node_id="N1",
                record_id="old-pass",
            )
        )
        plan_v2 = copy.deepcopy(self.fixture.plan)
        plan_v2.update({"plan_id": "plan-L900-v2", "plan_version": 2})
        self.activate_replan(plan_v2, seq=3)
        for item in (
            transition(4, "pending", "active"),
            transition(5, "active", "verifying", evidence_refs=["old-pass"]),
            transition(6, "verifying", "done", evidence_refs=["old-pass"]),
        ):
            item["plan_version"] = 2
            self.fixture.records.append(item)
        self.renumber(self.fixture.records)
        self.fixture.save()
        projection = project(self.fixture.root, generated_at="2026-07-31T01:00:00Z")
        self.assertEqual(projection["projection"]["node_states"]["N1"], "done")

    def test_replan_rejects_stale_check_in_completion_refs(self):
        check = self.fixture.plan["nodes"][0]["checks"][0]
        self.fixture.records.append(
            record(
                2,
                "evidence",
                evidence_payload(check_binding=fixture_check_binding(check)),
                node_id="N1",
                record_id="old-pass",
            )
        )
        plan_v2 = copy.deepcopy(self.fixture.plan)
        plan_v2.update({"plan_id": "plan-L900-v2", "plan_version": 2})
        plan_v2["nodes"][0]["checks"][0]["expected"] = "The stricter result passes."
        self.activate_replan(plan_v2, seq=3)
        completion = record(
            4,
            "completion",
            {
                "deliverables": [],
                "criterion_evidence": {"SC1": ["old-pass"]},
                "deterministic_check_refs": ["old-pass"],
                "system_review_ref": None,
                "counterexample_review_refs": [],
                "residual_risks": [],
                "unmet_scope": [],
                "authorization_decision_refs": [],
            },
            record_id="completion-stale",
        )
        completion["plan_version"] = 2
        self.fixture.records.append(completion)
        self.renumber(self.fixture.records)
        self.fixture.assert_rejects(self, "active evidence is required")

    def test_replan_ignores_stale_check_specific_failure_and_review(self):
        check = self.fixture.plan["nodes"][0]["checks"][0]
        old_binding = fixture_check_binding(check)
        review_dir = self.fixture.root / "reviews"
        review_dir.mkdir()
        manifest = review_dir / "old.json"
        manifest.write_bytes(b"{}\n")
        review_context = {
            "manifest_ref": "loop:reviews/old.json",
            "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "producer_conclusion_access": "withheld",
        }
        self.fixture.plan["control"] = {
            "mode": "governed",
            "modules": ["independent_review"],
            "admission_reason": "Independent review was required for plan v1.",
        }
        self.fixture.rewrite_plan()
        self.fixture.records += [
            record(
                2,
                "evidence",
                evidence_payload(result="fail", check_binding=old_binding),
                node_id="N1",
                record_id="old-fail",
            ),
            record(
                3,
                "evidence",
                evidence_payload(
                    result="fail",
                    check_binding=old_binding,
                    review_context=review_context,
                ),
                node_id="N1",
                record_id="old-review-fail",
            ),
        ]
        plan_v2 = copy.deepcopy(self.fixture.plan)
        plan_v2.update({"plan_id": "plan-L900-v2", "plan_version": 2})
        plan_v2["control"] = {
            "mode": "persistent",
            "modules": [],
            "admission_reason": "The independent-review risk ended.",
        }
        plan_v2["nodes"][0]["checks"][0]["instruction"] = "Run the replacement check."
        self.activate_replan(plan_v2, seq=4)
        new_check = plan_v2["nodes"][0]["checks"][0]
        fresh_binding = fixture_check_binding(new_check, plan_version=2)
        fresh = record(
            5,
            "evidence",
            evidence_payload(check_binding=fresh_binding),
            node_id="N1",
            record_id="fresh-pass",
        )
        fresh["plan_version"] = 2
        self.fixture.records.append(fresh)
        for item in (
            transition(6, "pending", "active"),
            transition(7, "active", "verifying", evidence_refs=["fresh-pass"]),
            transition(8, "verifying", "done", evidence_refs=["fresh-pass"]),
        ):
            item["plan_version"] = 2
            self.fixture.records.append(item)
        self.renumber(self.fixture.records)
        self.fixture.save()
        projection = project(self.fixture.root, generated_at="2026-07-31T01:00:00Z")
        self.assertEqual(projection["projection"]["node_states"]["N1"], "done")

    def test_replan_requires_fresh_review_even_when_check_is_unchanged(self):
        review_dir = self.fixture.root / "reviews"
        review_dir.mkdir()
        manifest = review_dir / "old.json"
        manifest.write_bytes(b"{}\n")
        context = {
            "manifest_ref": "loop:reviews/old.json",
            "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "producer_conclusion_access": "withheld",
        }
        self.fixture.plan["control"] = {
            "mode": "governed",
            "modules": ["independent_review"],
            "admission_reason": "Independent review is required.",
        }
        self.fixture.rewrite_plan()
        check = self.fixture.plan["nodes"][0]["checks"][0]
        self.fixture.records.append(
            record(
                2,
                "evidence",
                evidence_payload(
                    review_context=context,
                    check_binding=fixture_check_binding(check),
                ),
                node_id="N1",
                record_id="old-review-pass",
            )
        )
        plan_v2 = copy.deepcopy(self.fixture.plan)
        plan_v2.update({"plan_id": "plan-L900-v2", "plan_version": 2})
        self.activate_replan(plan_v2, seq=3)
        completion = record(
            4,
            "completion",
            {
                "deliverables": [],
                "criterion_evidence": {"SC1": ["old-review-pass"]},
                "deterministic_check_refs": [],
                "system_review_ref": "old-review-pass",
                "counterexample_review_refs": [],
                "residual_risks": [],
                "unmet_scope": [],
                "authorization_decision_refs": [],
            },
            record_id="completion-stale-review",
        )
        completion["plan_version"] = 2
        self.fixture.records.append(completion)
        self.renumber(self.fixture.records)
        self.fixture.assert_rejects(self, "active evidence is required")

    def test_reopen_rejects_stale_check_counterevidence_after_replan(self):
        self.fixture.records += [
            record(
                2,
                "evidence",
                evidence_payload(result="inconclusive", subjects=["node:N1"]),
                node_id="N1",
                record_id="stale-check-fail",
            ),
            record(
                3,
                "evidence",
                evidence_payload(check_ref=None, subjects=["criterion:SC1"]),
                record_id="criterion-pass",
            ),
            record(
                4,
                "completion",
                {
                    "deliverables": [],
                    "criterion_evidence": {"SC1": ["criterion-pass"]},
                    "deterministic_check_refs": [],
                    "system_review_ref": None,
                    "counterexample_review_refs": [],
                    "residual_risks": [],
                    "unmet_scope": [],
                    "authorization_decision_refs": [],
                },
                record_id="completion-1",
            ),
            record(
                5,
                "evidence",
                evidence_payload(result="fail", check_ref=None, subjects=["criterion:SC1"]),
                record_id="criterion-fail",
            ),
            record(
                6,
                "reopen",
                {
                    "completion_ref": "completion-1",
                    "counterevidence_refs": ["criterion-fail", "stale-check-fail"],
                    "affected_criterion_refs": ["SC1"],
                    "affected_node_ids": ["N1"],
                    "action": "Replan the check.",
                    "reason": "New criterion evidence invalidated the prior completion.",
                },
                record_id="reopen-for-replan",
            ),
        ]
        replan_decision = record(
            7,
            "decision",
            {
                "question": "Which plan should repair the reopened criterion?",
                "outcome": "Activate plan v2.",
                "rationale": "The criterion failure invalidated the active plan.",
                "authority": "model",
                "evidence_refs": ["criterion-fail"],
                "authorization_boundary_ref": None,
                "reconsider_when": "The criterion failure is resolved.",
                "overrides_evidence_ref": None,
            },
            record_id="replan-after-reopen",
        )
        self.fixture.records.append(replan_decision)

        plan_v2 = copy.deepcopy(self.fixture.plan)
        plan_v2.update({"plan_id": "plan-L900-v2", "plan_version": 2})
        plan_v2["nodes"][0]["checks"][0]["instruction"] = "Run the replacement check."
        plan_path = self.fixture.root / "plans" / "plan-v2.json"
        plan_path.write_bytes(json_bytes(plan_v2))
        replan_decision["payload"]["question"] = "plan_replacement"
        replan_decision["payload"]["plan_change"] = {
            "from_plan_version": 1,
            "from_plan_sha256": hashlib.sha256(
                (self.fixture.root / "plans" / "plan-v1.json").read_bytes()
            ).hexdigest(),
            "to_plan_version": 2,
            "to_plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        }
        self.activate_replan(
            plan_v2,
            seq=8,
            evidence_ref="criterion-fail",
            decision_ref="replan-after-reopen",
        )
        fresh_criterion_pass = record(
            8,
            "evidence",
            evidence_payload(check_ref=None, subjects=["criterion:SC1"]),
            record_id="criterion-pass-v2",
        )
        fresh_criterion_pass["plan_version"] = 2
        self.fixture.records.append(fresh_criterion_pass)
        resolve_criterion = record(
            9,
            "evidence_relation",
            {
                "source_evidence_ref": "criterion-pass-v2",
                "target_evidence_ref": "criterion-fail",
                "relation": "supersedes",
                "reason": "The criterion-level regression was resolved before recompletion.",
            },
            record_id="resolve-criterion-fail",
        )
        resolve_criterion["plan_version"] = 2
        self.fixture.records.append(resolve_criterion)
        completion = record(
            10,
            "completion",
            {
                "deliverables": [],
                "criterion_evidence": {"SC1": ["criterion-pass-v2"]},
                "deterministic_check_refs": [],
                "system_review_ref": None,
                "counterexample_review_refs": [],
                "residual_risks": [],
                "unmet_scope": [],
                "authorization_decision_refs": [],
            },
            record_id="completion-2",
        )
        completion["plan_version"] = 2
        self.fixture.records.append(completion)
        fresh_check_fail = record(
            11,
            "evidence",
            evidence_payload(
                result="fail",
                check_binding=fixture_check_binding(
                    plan_v2["nodes"][0]["checks"][0], plan_version=2
                ),
            ),
            node_id="N1",
            record_id="fresh-check-fail",
        )
        fresh_check_fail["plan_version"] = 2
        self.fixture.records.append(fresh_check_fail)
        reopen = record(
            12,
            "reopen",
            {
                "completion_ref": "completion-2",
                "counterevidence_refs": ["fresh-check-fail", "stale-check-fail"],
                "affected_criterion_refs": ["SC1"],
                "affected_node_ids": ["N1"],
                "action": "Reopen on the changed check.",
                "reason": "The old check failed.",
            },
            record_id="reopen-stale",
        )
        reopen["plan_version"] = 2
        self.fixture.records.append(reopen)
        self.renumber(self.fixture.records)
        self.fixture.assert_rejects(self, "active prior fail/inconclusive counterevidence")

        self.fixture.records[-1]["payload"]["counterevidence_refs"] = ["fresh-check-fail"]
        self.fixture.records[-1]["payload"]["affected_node_ids"] = ["N1"]
        self.fixture.save()
        self.assertEqual(project(self.fixture.root)["projection"]["loop_status"], "active")

    def test_projection_filters_stale_check_and_review_evidence_after_replan(self):
        review_dir = self.fixture.root / "reviews"
        review_dir.mkdir()
        manifest = review_dir / "old.json"
        manifest.write_bytes(b"{}\n")
        review_context = {
            "manifest_ref": "loop:reviews/old.json",
            "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "producer_conclusion_access": "withheld",
        }
        self.fixture.plan["control"] = {
            "mode": "governed",
            "modules": ["independent_review"],
            "admission_reason": "Independent review is required.",
        }
        self.fixture.rewrite_plan()
        check = self.fixture.plan["nodes"][0]["checks"][0]
        self.fixture.records += [
            record(2, "evidence", evidence_payload(), node_id="N1", record_id="old-pass"),
            record(
                3,
                "evidence",
                evidence_payload(review_context=review_context),
                node_id="N1",
                record_id="old-review-pass",
            ),
            record(
                4,
                "evidence",
                evidence_payload(check_ref=None, subjects=["criterion:SC1"]),
                record_id="criterion-pass",
            ),
        ]
        plan_v2 = copy.deepcopy(self.fixture.plan)
        plan_v2.update({"plan_id": "plan-L900-v2", "plan_version": 2})
        self.activate_replan(plan_v2, seq=5)
        self.renumber(self.fixture.records)
        self.fixture.save()

        projection = project(self.fixture.root, generated_at="2026-07-31T01:00:00Z")
        current = projection["projection"]["current_evidence_refs"]
        self.assertIn("old-pass", current["node:N1"])
        self.assertNotIn("old-review-pass", current["node:N1"])
        self.assertIn("criterion-pass", current["criterion:SC1"])
        self.assertEqual(
            projection["recovery_refs"]["confirmed_evidence"],
            ["criterion-pass", "old-pass", "replan-cause-2"],
        )

        plan_v2["nodes"][0]["checks"][0]["expected"] = "The changed result passes."
        plan_path = self.fixture.root / "plans" / "plan-v2.json"
        plan_path.write_bytes(json_bytes(plan_v2))
        self.fixture.records[-1]["payload"]["plan_sha256"] = hashlib.sha256(
            plan_path.read_bytes()
        ).hexdigest()
        self.fixture.records[-2]["payload"]["plan_change"]["to_plan_sha256"] = (
            self.fixture.records[-1]["payload"]["plan_sha256"]
        )
        self.fixture.save()
        projection = project(self.fixture.root, generated_at="2026-07-31T01:00:00Z")
        current = projection["projection"]["current_evidence_refs"]
        self.assertNotIn("node:N1", current)
        self.assertEqual(current["criterion:SC1"], ["criterion-pass", "replan-cause-2"])
        self.assertEqual(
            projection["recovery_refs"]["confirmed_evidence"],
            ["criterion-pass", "replan-cause-2"],
        )

    def test_project_rejects_plan_graph_semantic_failures(self):
        mutations = [
            (lambda plan: plan["nodes"].append(copy.deepcopy(plan["nodes"][0])), "GRAPH-UNIQUE"),
            (lambda plan: plan["nodes"][0].update({"depends_on": ["missing"]}), "GRAPH-DANGLING"),
            (lambda plan: plan["nodes"][0].update({"depends_on": ["N1"]}), "GRAPH-CYCLE"),
            (lambda plan: plan["nodes"][0].update({"success_criteria_refs": ["missing"]}), "GRAPH-CRITERION"),
            (lambda plan: plan["nodes"][0].update({"authorization_refs": ["missing"]}), "GRAPH-AUTH"),
            (lambda plan: plan["nodes"][0].update({"outputs": [{"path": "../escape", "purpose": "bad"}]}), "GRAPH-PATH"),
            (lambda plan: plan["nodes"][0].update({"outputs": [{"path": "artifacts/./result.txt", "purpose": "bad"}]}), "GRAPH-PATH"),
            (lambda plan: plan["nodes"][0].update({"outputs": [{"path": "artifacts/result?.txt", "purpose": "bad"}]}), "GRAPH-PATH"),
            (lambda plan: plan["nodes"][0].update({"outputs": [{"path": "artifacts/control\x01.txt", "purpose": "bad"}]}), "GRAPH-PATH"),
            (lambda plan: plan["nodes"][0].update({"outputs": [{"path": "artifacts/CON.txt", "purpose": "bad"}]}), "GRAPH-PATH"),
            (lambda plan: plan["nodes"].append({
                "id": "N2", "objective": "Duplicate the output.", "depends_on": [],
                "success_criteria_refs": ["SC1"],
                "outputs": [{"path": "artifacts/result.txt", "purpose": "duplicate"}],
                "checks": [{"id": "check-N2", "method": "test", "instruction": "Run it.", "expected": "Pass."}],
                "authorization_refs": [],
            }) or plan["nodes"][0].update({"outputs": [{"path": "artifacts/result.txt", "purpose": "result"}]}), "GRAPH-UNIQUE"),
            (lambda plan: plan["nodes"][0].update({"checks": []}), "GRAPH-CHECK"),
            (lambda plan: plan["control"].update({"mode": "governed", "modules": ["children"]}), "CHILD-MODULE"),
        ]
        for index, (mutate, pattern) in enumerate(mutations):
            with self.subTest(pattern=pattern, index=index):
                self.fixture = LoopFixture(Path(self.temp.name) / f"{pattern}-{index}")
                mutate(self.fixture.plan)
                self.fixture.rewrite_plan()
                self.fixture.assert_rejects(self, pattern)

    def test_legacy_import_is_unique_first_migrator_record_followed_by_activation(self):
        activation = self.fixture.records[0]
        activation["seq"] = 2
        activation["record_id"] = "activation"
        activation["ts"] = "2026-07-31T00:02:00Z"
        self.fixture.records = [legacy_import({"N1": "pending"}), activation]
        self.fixture.save()
        self.assertEqual(project(self.fixture.root)["projection"]["node_states"], {"N1": "pending"})

        cases = (
            (lambda records: records.append(legacy_import({}, seq=3, record_id="legacy-import-2")), "exactly one"),
            (lambda records: records.reverse(), "seq=1 first record"),
            (lambda records: records[0].update({"actor": {"type": "model", "id": "forged"}}), "migrator"),
            (
                lambda records: records.insert(
                    1,
                    record(
                        2,
                        "context",
                        {
                            "item_id": "gap",
                            "item_type": "risk",
                            "status": "open",
                            "statement": "Unexpected record before activation.",
                            "evidence_refs": [],
                            "resolution_condition": "Remove it.",
                        },
                        record_id="gap",
                    ),
                ),
                "followed immediately",
            ),
        )
        for mutate, pattern in cases:
            with self.subTest(pattern=pattern):
                fixture = LoopFixture(Path(self.temp.name) / pattern.replace(" ", "-"))
                activation = fixture.records[0]
                activation["seq"] = 2
                activation["record_id"] = "activation"
                activation["ts"] = "2026-07-31T00:02:00Z"
                fixture.records = [legacy_import({"N1": "pending"}), activation]
                mutate(fixture.records)
                for index, item in enumerate(fixture.records, 1):
                    item["seq"] = index
                    item["ts"] = f"2026-07-31T00:{index:02d}:00Z"
                fixture.assert_rejects(self, pattern)

    def test_legacy_import_closed_effect_audit_is_ordered_and_unique(self):
        activation = self.fixture.records[0]
        activation["seq"] = 2
        activation["record_id"] = "activation"
        activation["ts"] = "2026-07-31T00:02:00Z"
        imported = legacy_import({"N1": "pending"})
        imported["payload"]["source"]["last_event_seq"] = 5
        imported["payload"]["closed_effects"] = [
            {
                "effect_id": "deploy",
                "attempt_id": "attempt-1",
                "node_id": "N1",
                "pre_seq": 4,
                "post_seq": 5,
                "outcome": "succeeded",
                "idempotency_key": "deploy-attempt-1",
                "result_ref": "sha256:legacy-result",
            }
        ]
        self.fixture.records = [imported, activation]
        self.fixture.save()
        self.assertEqual(project(self.fixture.root)["projection"]["in_doubt_effect_ids"], [])

        imported["payload"]["closed_effects"][0]["post_seq"] = 4
        self.fixture.save()
        self.fixture.assert_rejects(self, "post_seq after pre_seq")

        imported["payload"]["closed_effects"][0]["post_seq"] = 5
        imported["payload"]["closed_effects"].append(
            dict(imported["payload"]["closed_effects"][0])
        )
        self.fixture.save()
        self.fixture.assert_rejects(self, "duplicate closed legacy effect")

    def test_legacy_import_closed_effects_are_bound_to_source_and_active_plan(self):
        activation = self.fixture.records[0]
        activation["seq"] = 2
        activation["record_id"] = "activation"
        activation["ts"] = "2026-07-31T00:02:00Z"
        imported = legacy_import({"N1": "pending"})
        imported["payload"]["source"]["last_event_seq"] = 5
        imported["payload"]["closed_effects"] = [
            {
                "effect_id": "deploy",
                "attempt_id": "attempt-1",
                "node_id": "UNKNOWN",
                "pre_seq": 4,
                "post_seq": 5,
                "outcome": "succeeded",
                "idempotency_key": None,
                "result_ref": "legacy-result",
            }
        ]
        self.fixture.records = [imported, activation]
        self.fixture.assert_rejects(self, "closed legacy effects reference unknown nodes")

        imported["payload"]["closed_effects"][0]["node_id"] = "N1"
        imported["payload"]["source"]["event_log_sha256"] = "c" * 64
        self.fixture.assert_rejects(self, "event_log source hash does not match")

    def test_journal_timestamps_must_not_move_backwards(self):
        self.fixture.records += [
            record(
                2,
                "context",
                {
                    "item_id": "risk-1",
                    "item_type": "risk",
                    "status": "open",
                    "statement": "Track a risk.",
                    "evidence_refs": [],
                    "resolution_condition": "Resolve it.",
                },
            )
        ]
        self.fixture.records[1]["ts"] = "2026-07-30T23:59:00Z"
        self.fixture.assert_rejects(self, "timestamp precedes the prior journal record")

    def test_legacy_done_requires_explicit_fresh_reverification_before_completion(self):
        activation = self.fixture.records[0]
        activation["seq"] = 2
        activation["record_id"] = "activation"
        activation["ts"] = "2026-07-31T00:02:00Z"
        self.fixture.records = [legacy_import({"N1": "done"}), activation]
        self.fixture.records += [
            record(3, "evidence", evidence_payload(check_ref=None, subjects=["criterion:SC1"]), record_id="criterion-pass"),
            record(4, "completion", {"deliverables": [], "criterion_evidence": {"SC1": ["criterion-pass"]}, "deterministic_check_refs": [], "system_review_ref": None, "counterexample_review_refs": [], "residual_risks": [], "unmet_scope": [], "authorization_decision_refs": []}, record_id="completion-1"),
        ]
        self.fixture.assert_rejects(self, "legacy done nodes require fresh reverification")

        self.fixture.records = self.fixture.records[:2] + [
            transition(3, "done", "active"),
        ]
        self.fixture.assert_rejects(self, "legacy_reverification")

        self.fixture.records[-1]["payload"]["reason_code"] = "legacy_reverification"
        self.fixture.records += [
            record(4, "evidence", evidence_payload(), node_id="N1", record_id="fresh-pass"),
            transition(5, "active", "verifying", evidence_refs=["fresh-pass"]),
            transition(6, "verifying", "done", evidence_refs=["fresh-pass"]),
            record(7, "completion", {"deliverables": [], "criterion_evidence": {"SC1": ["fresh-pass"]}, "deterministic_check_refs": [], "system_review_ref": None, "counterexample_review_refs": [], "residual_risks": [], "unmet_scope": [], "authorization_decision_refs": []}, record_id="completion-1"),
        ]
        self.fixture.save()
        projection = project(self.fixture.root)
        self.assertEqual(projection["projection"]["node_states"], {"N1": "done"})
        self.assertEqual(projection["projection"]["loop_status"], "completed")

    def test_legacy_reverification_rejects_pre_reopen_check_evidence(self):
        activation = self.fixture.records[0]
        activation["seq"] = 2
        activation["record_id"] = "activation"
        activation["ts"] = "2026-07-31T00:02:00Z"
        self.fixture.records = [
            legacy_import({"N1": "done"}),
            activation,
            record(3, "evidence", evidence_payload(), node_id="N1", record_id="old-pass"),
            transition(4, "done", "active"),
            transition(5, "active", "verifying", evidence_refs=["old-pass"]),
            transition(6, "verifying", "done", evidence_refs=["old-pass"]),
        ]
        self.fixture.records[3]["payload"]["reason_code"] = "legacy_reverification"
        self.fixture.assert_rejects(self, "fresh evidence recorded after done->active")

    def test_unverified_legacy_done_cannot_be_replanned_away_or_closed(self):
        activation = self.fixture.records[0]
        activation["seq"] = 2
        activation["record_id"] = "activation"
        activation["ts"] = "2026-07-31T00:02:00Z"
        self.fixture.records = [legacy_import({"N1": "done"}), activation]

        renamed_plan = copy.deepcopy(self.fixture.plan)
        renamed_plan["plan_id"] = "plan-L900-v2"
        renamed_plan["plan_version"] = 2
        renamed_plan["nodes"][0]["id"] = "N2"
        renamed_plan["nodes"][0]["checks"][0]["id"] = "check-N2"
        plan_path = self.fixture.root / "plans" / "plan-v2.json"
        plan_path.write_bytes(json_bytes(renamed_plan))
        replan = record(
            3,
            "plan_activated",
            {
                "plan_ref": "plans/plan-v2.json",
                "plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                "previous_version": 1,
                "reason": "Rename the imported node.",
                "evidence_refs": [],
                "decision_ref": None,
            },
            record_id="activation-v2",
        )
        replan["plan_version"] = 2
        causal = record(
            3,
            "evidence",
            evidence_payload(check_ref=None, subjects=["criterion:SC1"]),
            record_id="legacy-replan-cause",
        )
        decision = record(
            4,
            "decision",
            {
                "question": "plan_replacement",
                "outcome": "Replace it in plan v2.",
                "rationale": "Fixture exercises the legacy-node safety gate.",
                "authority": "model",
                "evidence_refs": ["legacy-replan-cause"],
                "authorization_boundary_ref": None,
                "reconsider_when": None,
                "overrides_evidence_ref": None,
                "plan_change": {
                    "from_plan_version": 1,
                    "from_plan_sha256": hashlib.sha256(
                        (self.fixture.root / "plans" / "plan-v1.json").read_bytes()
                    ).hexdigest(),
                    "to_plan_version": 2,
                    "to_plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                },
            },
            record_id="legacy-replan-decision",
        )
        replan["seq"] = 5
        replan["ts"] = "2026-07-31T00:05:00Z"
        replan["payload"]["evidence_refs"] = ["legacy-replan-cause"]
        replan["payload"]["decision_ref"] = "legacy-replan-decision"
        self.fixture.records.extend([causal, decision, replan])
        self.fixture.assert_rejects(self, "replan cannot remove or rename")

        self.fixture.records = self.fixture.records[:2] + [transition(3, "done", "closed")]
        self.fixture.assert_rejects(self, "cannot close before fresh reverification")

    def test_legacy_done_to_active_cannot_complete_before_fresh_done(self):
        activation = self.fixture.records[0]
        activation["seq"] = 2
        activation["record_id"] = "activation"
        activation["ts"] = "2026-07-31T00:02:00Z"
        reopen = transition(3, "done", "active")
        reopen["payload"]["reason_code"] = "legacy_reverification"
        self.fixture.records = [
            legacy_import({"N1": "done"}),
            activation,
            reopen,
            record(
                4,
                "evidence",
                evidence_payload(check_ref=None, subjects=["criterion:SC1"]),
                record_id="criterion-pass",
            ),
            record(
                5,
                "completion",
                {
                    "deliverables": [],
                    "criterion_evidence": {"SC1": ["criterion-pass"]},
                    "deterministic_check_refs": [],
                    "system_review_ref": None,
                    "counterexample_review_refs": [],
                    "residual_risks": [],
                    "unmet_scope": [],
                    "authorization_decision_refs": [],
                },
                record_id="completion-1",
            ),
        ]
        self.fixture.assert_rejects(self, "legacy done nodes require fresh reverification")

    def test_nested_child_workspace_root_and_completion_deliverable(self):
        project_root = Path(self.temp.name) / "workspace"
        child_root = project_root / ".agents" / "loops" / "L001-parent" / "_loops" / "L001.01-child-slug"
        child_root.parent.mkdir(parents=True)
        self.assertEqual(workspace_root(child_root), project_root)

        fixture = LoopFixture(child_root.parent)
        fixture.root.rename(child_root)
        fixture.root = child_root
        fixture.goal["loop_id"] = "L900.01"
        (fixture.root / "goal.json").write_bytes(json_bytes(fixture.goal))
        fixture.plan["goal_sha256"] = hashlib.sha256((fixture.root / "goal.json").read_bytes()).hexdigest()
        fixture.plan["nodes"][0]["outputs"] = [{"path": "result.txt", "purpose": "Return"}]
        fixture.rewrite_plan()
        (project_root / "result.txt").write_text("ok\n", encoding="utf-8")
        fixture.records += [
            record(2, "evidence", evidence_payload(), node_id="N1", record_id="ev-pass"),
            record(
                3,
                "completion",
                {
                    "deliverables": [{"path": "result.txt"}],
                    "criterion_evidence": {"SC1": ["ev-pass"]},
                    "deterministic_check_refs": [],
                    "system_review_ref": None,
                    "counterexample_review_refs": [],
                    "residual_risks": [],
                    "unmet_scope": [],
                    "authorization_decision_refs": [],
                },
                record_id="completion-1",
            ),
        ]
        fixture.save()
        self.assertEqual(project(child_root)["projection"]["loop_status"], "completed")

    def test_completion_accepts_declared_directory_deliverable_without_file_hash(self):
        project_root = Path(self.temp.name) / "workspace"
        fixture = LoopFixture(project_root / ".agents" / "loops")
        fixture.plan["nodes"][0]["outputs"] = [
            {"path": "artifacts", "purpose": "Legacy directory output"}
        ]
        fixture.rewrite_plan()
        (project_root / "artifacts").mkdir()
        (project_root / "artifacts" / "result.txt").write_text("ok\n", encoding="utf-8")
        fixture.records += [
            record(
                2,
                "evidence",
                evidence_payload(check_ref=None, subjects=["criterion:SC1"]),
                record_id="criterion-pass",
            ),
            record(
                3,
                "completion",
                {
                    "deliverables": [{"path": "artifacts"}],
                    "criterion_evidence": {"SC1": ["criterion-pass"]},
                    "deterministic_check_refs": [],
                    "system_review_ref": None,
                    "counterexample_review_refs": [],
                    "residual_risks": [],
                    "unmet_scope": [],
                    "authorization_decision_refs": [],
                },
                record_id="completion-directory",
            ),
        ]
        fixture.save()
        self.assertEqual(project(fixture.root)["projection"]["loop_status"], "completed")

        fixture.records[-1]["payload"]["deliverables"][0]["sha256"] = "0" * 64
        fixture.save()
        fixture.assert_rejects(self, "deliverable hash mismatch")

    def test_completion_deliverable_resolved_path_must_stay_in_workspace(self):
        project_root = Path(self.temp.name) / "workspace"
        loop_parent = project_root / ".agents" / "loops"
        fixture = LoopFixture(loop_parent)
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        external_file = outside / "result.txt"
        external_file.write_text("outside\n", encoding="utf-8")
        link = project_root / "escape"
        created_symlink = False
        created_link = False
        try:
            os.symlink(outside, link, target_is_directory=True)
            created_symlink = True
            created_link = True
        except OSError:
            if os.name != "nt":
                self.skipTest("directory symlink creation is unavailable")
            try:
                subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                created_link = True
            except subprocess.CalledProcessError:
                self.skipTest("directory junction creation is unavailable")

        try:
            fixture.plan["nodes"][0]["outputs"] = [
                {"path": "escape/result.txt", "purpose": "Must remain in the workspace"}
            ]
            fixture.rewrite_plan()
            fixture.records += [
                record(
                    2,
                    "evidence",
                    evidence_payload(check_ref=None, subjects=["criterion:SC1"]),
                    record_id="criterion-pass",
                ),
                record(
                    3,
                    "completion",
                    {
                        "deliverables": [
                            {
                                "path": "escape/result.txt",
                                "sha256": hashlib.sha256(external_file.read_bytes()).hexdigest(),
                            }
                        ],
                        "criterion_evidence": {"SC1": ["criterion-pass"]},
                        "deterministic_check_refs": [],
                        "system_review_ref": None,
                        "counterexample_review_refs": [],
                        "residual_risks": [],
                        "unmet_scope": [],
                        "authorization_decision_refs": [],
                    },
                    record_id="completion-escape",
                ),
            ]
            fixture.assert_rejects(self, "resolved path escapes the workspace")
        finally:
            if created_link:
                if created_symlink:
                    link.unlink()
                else:
                    link.rmdir()

        (project_root / "escape").mkdir()
        fixture.assert_rejects(self, "deliverable is missing")

        local_file = project_root / "escape" / "result.txt"
        local_file.write_text("inside\n", encoding="utf-8")
        fixture.assert_rejects(self, "deliverable hash mismatch")

        fixture.records[-1]["payload"]["deliverables"][0]["sha256"] = hashlib.sha256(
            local_file.read_bytes()
        ).hexdigest()
        fixture.save()
        self.assertEqual(project(fixture.root)["projection"]["loop_status"], "completed")

    def test_effect_pre_requires_active_node(self):
        self.fixture = LoopFixture(Path(self.temp.name) / "effect", modules=["effects"])
        self.fixture.records.append(
            record(2, "effect_pre", effect_pre_payload(), node_id="N1")
        )
        self.fixture.assert_rejects(self, "EFFECT-STATE")

        self.fixture.records.insert(1, transition(2, "pending", "active"))
        self.fixture.records[-1]["seq"] = 3
        self.fixture.records[-1]["record_id"] = "rec-3"
        self.fixture.records[-1]["ts"] = "2026-07-31T00:03:00Z"
        self.fixture.save()
        self.assertEqual(project(self.fixture.root)["projection"]["in_doubt_effect_ids"], ["deploy:attempt-1"])

    def test_replan_requires_conclusive_effect_recovery(self):
        self.fixture = LoopFixture(Path(self.temp.name) / "effect-replan", modules=["effects"])
        self.fixture.records += [
            transition(2, "pending", "active"),
            record(3, "effect_pre", effect_pre_payload(), node_id="N1"),
            transition(4, "active", "closed"),
            record(
                5,
                "evidence",
                evidence_payload(check_ref=None, subjects=["criterion:SC1"]),
                record_id="effect-replan-cause",
            ),
            record(
                6,
                "decision",
                {
                    "question": "plan_replacement",
                    "outcome": "Activate plan v2 after effect recovery.",
                    "rationale": "The external operation no longer needs governance.",
                    "authority": "model",
                    "evidence_refs": ["effect-replan-cause"],
                    "authorization_boundary_ref": None,
                    "reconsider_when": "The effect becomes in doubt again.",
                    "overrides_evidence_ref": None,
                },
                record_id="effect-replan-decision",
            ),
        ]
        plan_v2 = copy.deepcopy(self.fixture.plan)
        plan_v2.update({"plan_id": "plan-L900-v2", "plan_version": 2})
        plan_v2["control"] = {
            "mode": "persistent",
            "modules": [],
            "admission_reason": "The external effect is resolved before governance is reduced.",
        }
        plan_path = self.fixture.root / "plans" / "plan-v2.json"
        plan_path.write_bytes(json_bytes(plan_v2))
        self.fixture.records[-1]["payload"]["plan_change"] = {
            "from_plan_version": 1,
            "from_plan_sha256": hashlib.sha256(
                (self.fixture.root / "plans" / "plan-v1.json").read_bytes()
            ).hexdigest(),
            "to_plan_version": 2,
            "to_plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        }
        activation = record(
            7,
            "plan_activated",
            {
                "plan_ref": "plans/plan-v2.json",
                "plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                "previous_version": 1,
                "reason": "Retire the effects module.",
                "evidence_refs": ["effect-replan-cause"],
                "decision_ref": "effect-replan-decision",
            },
            record_id="activation-v2",
        )
        activation["plan_version"] = 2
        self.fixture.records.append(activation)
        self.fixture.assert_rejects(self, "resolve in-doubt effects before replanning")

        effect_post = record(
            4,
            "effect_post",
            {
                "effect_id": "deploy",
                "attempt_id": "attempt-1",
                "outcome": "succeeded",
                "observed_postcondition": "Deployment is healthy.",
                "result_ref": "tool:deploy-check",
            },
            node_id="N1",
        )
        self.fixture.records.insert(3, effect_post)
        self.renumber(self.fixture.records)
        self.fixture.save()
        projection = project(self.fixture.root)
        self.assertEqual(projection["projection"]["in_doubt_effect_ids"], [])
        self.assertEqual(projection["source"]["plan_version"], 2)

    def test_loop_close_requires_conclusive_effect_recovery(self):
        self.fixture = LoopFixture(Path(self.temp.name) / "effect-close", modules=["effects"])
        self.fixture.records += [
            transition(2, "pending", "active"),
            record(3, "effect_pre", effect_pre_payload(), node_id="N1"),
            record(
                4,
                "loop_lifecycle",
                {
                    "from": "active",
                    "to": "closed",
                    "reason_code": "abandoned",
                    "reason": "Stop the Loop.",
                    "refs": [],
                },
                record_id="close-loop",
            ),
        ]
        self.fixture.assert_rejects(self, "resolve in-doubt effects before closing the loop")

        self.fixture.records.insert(
            3,
            record(
                4,
                "effect_post",
                {
                    "effect_id": "deploy",
                    "attempt_id": "attempt-1",
                    "outcome": "cancelled",
                    "observed_postcondition": "Reality check confirms no deployment remains active.",
                    "result_ref": "tool:deploy-check",
                },
                node_id="N1",
            ),
        )
        self.fixture.records[4]["seq"] = 5
        self.fixture.records[4]["ts"] = "2026-07-31T00:05:00Z"
        self.fixture.save()
        projection = project(self.fixture.root)
        self.assertEqual(projection["projection"]["in_doubt_effect_ids"], [])
        self.assertEqual(projection["projection"]["loop_status"], "closed")

    def test_waiting_loop_must_resume_before_node_transition(self):
        self.fixture.records += [
            record(2, "loop_lifecycle", {"from": "active", "to": "waiting", "reason_code": "external", "reason": "Wait.", "refs": []}),
            transition(3, "pending", "active"),
        ]
        self.fixture.assert_rejects(self, "must resume")
        self.fixture.records.insert(
            2,
            record(3, "loop_lifecycle", {"from": "waiting", "to": "active", "reason_code": "ready", "reason": "Resume.", "refs": []}),
        )
        self.fixture.records[-1]["seq"] = 4
        self.fixture.records[-1]["record_id"] = "rec-4"
        self.fixture.records[-1]["ts"] = "2026-07-31T00:04:00Z"
        self.fixture.save()
        self.assertEqual(project(self.fixture.root)["projection"]["node_states"], {"N1": "active"})

    def test_review_manifest_is_confined_present_and_hash_bound(self):
        self.fixture = LoopFixture(Path(self.temp.name) / "review", modules=["independent_review"])
        manifest = self.fixture.root / "review-manifest.json"
        manifest.write_text('{"visible":["artifact"]}\n', encoding="utf-8")
        context = {
            "manifest_ref": "loop:review-manifest.json",
            "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "producer_conclusion_access": "withheld",
        }
        self.fixture.records.append(
            record(2, "evidence", evidence_payload(review_context=context), node_id="N1", record_id="review-pass")
        )
        self.fixture.save()
        self.assertIn("review-pass", project(self.fixture.root)["recovery_refs"]["confirmed_evidence"])

        self.fixture.records[-1]["payload"]["review_context"]["manifest_sha256"] = "0" * 64
        self.fixture.assert_rejects(self, "manifest hash")
        self.fixture.records[-1]["payload"]["review_context"]["manifest_ref"] = "../outside.json"
        self.fixture.assert_rejects(self, "safe root")

    def test_confirms_resolves_only_exact_challenge_source(self):
        self.fixture.complete_node()
        self.fixture.records += [
            record(6, "evidence", evidence_payload(result="fail"), node_id="N1", record_id="challenge-1"),
            record(7, "evidence_relation", {"source_evidence_ref": "challenge-1", "target_evidence_ref": "ev-pass", "relation": "challenges", "reason": "Regression."}, record_id="rel-challenge"),
            record(8, "evidence", evidence_payload(), node_id="N1", record_id="unrelated-pass"),
            record(9, "evidence_relation", {"source_evidence_ref": "unrelated-pass", "target_evidence_ref": "ev-pass", "relation": "confirms", "reason": "Unrelated."}, record_id="rel-bypass"),
        ]
        self.fixture.assert_rejects(self, "exact challenge evidence")

        self.fixture.records[-1]["payload"]["target_evidence_ref"] = "challenge-1"
        self.fixture.save()
        self.assertEqual(project(self.fixture.root)["projection"]["node_states"], {"N1": "done"})

    def test_failed_review_requires_exact_override_decision_on_transition(self):
        self.fixture = LoopFixture(Path(self.temp.name) / "override", modules=["independent_review"])
        manifest = self.fixture.root / "review.json"
        manifest.write_text("{}\n", encoding="utf-8")
        context = {
            "manifest_ref": "loop:review.json",
            "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "producer_conclusion_access": "withheld",
        }
        self.fixture.records += [
            transition(2, "pending", "active"),
            record(3, "evidence", evidence_payload(result="fail", review_context=context), node_id="N1", record_id="review-fail"),
            record(
                4,
                "decision",
                {
                    "question": "Proceed despite review?",
                    "outcome": "Proceed with bounded verification.",
                    "rationale": "A separate direct check will decide.",
                    "authority": "model",
                    "evidence_refs": ["review-fail"],
                    "authorization_boundary_ref": None,
                    "reconsider_when": "Direct verification fails.",
                    "overrides_evidence_ref": "review-fail",
                },
                record_id="override-review",
            ),
            transition(5, "active", "verifying", evidence_refs=["review-fail"]),
        ]
        self.fixture.assert_rejects(self, "must cite decisions")
        self.fixture.records[-1]["payload"]["decision_refs"] = ["override-review"]
        self.fixture.save()
        self.assertEqual(project(self.fixture.root)["projection"]["node_states"], {"N1": "verifying"})

    def test_completion_tail_tracks_all_check_and_review_refs(self):
        self.fixture.records += [
            record(2, "evidence", evidence_payload(check_ref=None, subjects=["criterion:SC1"]), record_id="criterion-pass"),
            record(3, "evidence", evidence_payload(check_ref=None, subjects=["artifact:det"]), record_id="det-pass"),
            record(4, "completion", {"deliverables": [], "criterion_evidence": {"SC1": ["criterion-pass"]}, "deterministic_check_refs": ["det-pass"], "system_review_ref": None, "counterexample_review_refs": [], "residual_risks": [], "unmet_scope": [], "authorization_decision_refs": []}, record_id="completion-1"),
            record(5, "evidence", evidence_payload(result="fail", check_ref=None, subjects=["artifact:det"]), record_id="det-fail"),
            record(6, "evidence_relation", {"source_evidence_ref": "det-fail", "target_evidence_ref": "det-pass", "relation": "invalidates", "reason": "Fresh check failed."}, record_id="rel-det"),
        ]
        self.fixture.assert_rejects(self, "without an explicit reopen")

    def test_done_remains_invalid_until_counterevidence_is_resolved(self):
        self.fixture.complete_node()
        self.fixture.records += [
            record(6, "evidence", evidence_payload(result="fail"), node_id="N1", record_id="counter"),
            transition(7, "done", "active", evidence_refs=["counter"]),
            transition(8, "active", "verifying", evidence_refs=["counter"]),
            record(9, "evidence", evidence_payload(), node_id="N1", record_id="fresh-pass"),
            transition(10, "verifying", "done", evidence_refs=["fresh-pass"]),
        ]
        self.fixture.assert_rejects(self, "unresolved failing evidence")

        self.fixture.records.insert(
            -1,
            record(10, "evidence_relation", {"source_evidence_ref": "fresh-pass", "target_evidence_ref": "counter", "relation": "supersedes", "reason": "Fresh direct check resolves the failure."}, record_id="resolve-counter"),
        )
        self.fixture.records[-1]["seq"] = 11
        self.fixture.records[-1]["record_id"] = "rec-11"
        self.fixture.records[-1]["ts"] = "2026-07-31T00:11:00Z"
        self.fixture.save()
        self.assertEqual(project(self.fixture.root)["projection"]["node_states"], {"N1": "done"})


if __name__ == "__main__":
    unittest.main()
