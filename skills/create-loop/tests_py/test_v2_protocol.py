from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SCHEMAS = ROOT / "schemas"
sys.path.insert(0, str(SCRIPTS))

from project_loop import ProjectionError, project  # noqa: E402
from render_resume import write_atomic  # noqa: E402
from schema_runtime import SchemaError, check_schema, load_json, validate  # noqa: E402
from validate_loop_dir import validate_loop_dir  # noqa: E402


class DocumentationRoutingTests(unittest.TestCase):
    def test_migration_runbook_is_readme_routed(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        protocol = (ROOT / "references" / "protocol_v2.md").read_text(encoding="utf-8")
        runbook = ROOT / "references" / "migration_v1_to_v2.md"

        self.assertTrue(runbook.is_file())
        self.assertNotIn("migrate_v1.py", skill)
        self.assertNotIn("legacy_import", skill)
        self.assertIn("references/migration_v1_to_v2.md", readme)
        self.assertIn("scripts/migrate_v1.py", readme)
        self.assertNotIn("python scripts/migrate_v1.py", protocol)
        self.assertIn("migration_v1_to_v2.md", protocol)


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def make_goal() -> dict:
    return {
        "schema_version": "2.0", "loop_id": "L900", "goal": "Deliver a tested result.",
        "intent": "Produce a directly verified result with resumable state.",
        "scope": {"in": ["Implementation and verification"], "out": ["Deployment"]},
        "success_criteria": [{"id": "SC1", "statement": "The direct check passes.", "expected_evidence": "Passing tool output."}],
        "constraints": [], "authorization_boundaries": [], "stop_conditions": [],
        "created_at": "2026-07-31T00:00:00Z",
    }


def make_plan(goal_hash: str, *, modules: list[str] | None = None, mode: str = "persistent", version: int = 1) -> dict:
    if modules and mode == "persistent":
        mode = "governed"
    return {
        "schema_version": "2.0", "plan_id": f"plan-L900-v{version}", "plan_version": version,
        "goal_sha256": goal_hash, "created_at": "2026-07-31T00:00:00Z",
        "control": {"mode": mode, "modules": modules or [], "admission_reason": "Cross-session verification needs durable recovery."},
        "nodes": [{"id": "N1", "objective": "Produce the result.", "depends_on": [], "success_criteria_refs": ["SC1"], "outputs": [], "checks": [{"id": "check-N1", "method": "test", "instruction": "Run the test.", "expected": "Pass."}], "authorization_refs": []}],
    }


def check_binding(plan: dict, *, node_id: str = "N1", check_id: str = "check-N1") -> dict:
    node = next(item for item in plan["nodes"] if item["id"] == node_id)
    check = next(item for item in node["checks"] if item["id"] == check_id)
    return {
        "plan_version": plan["plan_version"],
        "node_id": node_id,
        "check_id": check_id,
        "check_sha256": hashlib.sha256(
            (json.dumps(check, sort_keys=True, separators=(",", ":")) + "\n").encode()
        ).hexdigest(),
    }


def record(seq: int, kind: str, payload: dict, *, node_id: str | None = None, record_id: str | None = None) -> dict:
    value = {"schema_version": "2.0", "seq": seq, "record_id": record_id or f"rec-{seq}", "ts": f"2026-07-31T00:{seq:02d}:00Z", "kind": kind, "actor": {"type": "model", "id": "test"}, "plan_version": 1, "payload": payload}
    if node_id:
        value["node_id"] = node_id
    return value


def claim(*, node_id: str, token: str, scope_paths: list[str], owner_id: str = "agent-a", expires_at: str = "2099-01-01T00:00:00Z") -> dict:
    return {
        "schema_version": "2.0", "loop_id": "L900", "node_id": node_id,
        "token": token, "owner_id": owner_id, "scope_paths": scope_paths,
        "plan_version": 1, "acquired_at": "2026-07-31T00:00:00Z",
        "heartbeat_at": "2026-07-31T00:01:00Z", "expires_at": expires_at,
    }


def base_records(plan_hash: str) -> list[dict]:
    return [record(1, "plan_activated", {"plan_ref": "plans/plan-v1.json", "plan_sha256": plan_hash, "previous_version": None, "reason": "Initial", "evidence_refs": [], "decision_ref": None})]


class LoopFixture:
    def __init__(self, parent: Path, *, modules: list[str] | None = None):
        self.root = parent / "loop"
        (self.root / "plans").mkdir(parents=True)
        self.goal = make_goal()
        (self.root / "goal.json").write_bytes(json_bytes(self.goal))
        self.plan = make_plan(hashlib.sha256((self.root / "goal.json").read_bytes()).hexdigest(), modules=modules)
        (self.root / "plans" / "plan-v1.json").write_bytes(json_bytes(self.plan))
        self.records = base_records(hashlib.sha256((self.root / "plans" / "plan-v1.json").read_bytes()).hexdigest())

    def save(self, *, render: bool = True) -> None:
        with (self.root / "journal.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for item in self.records:
                handle.write(json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n")
        if render:
            write_atomic(self.root / "resume.json", project(self.root, generated_at="2026-07-31T01:00:00Z"))

    def evidence(self, seq: int = 3, *, result: str = "pass", record_id: str = "ev-pass") -> dict:
        return record(seq, "evidence", {"subject_refs": ["node:N1", "criterion:SC1"], "check_ref": "check-N1", "check_binding": check_binding(self.plan), "source_class": "direct_test", "origin_ref": "tool:test", "artifact_ref": None, "observed_result": result, "summary": "Observed result.", "limits": "Only this check.", "valid_until": None, "recheck_when": "Implementation changes.", "review_context": None}, node_id="N1", record_id=record_id)

    def activate_node(self, seq: int = 2) -> dict:
        return record(seq, "transition", {"from": "pending", "to": "active", "reason_code": "dispatch", "reason": "Ready", "evidence_refs": [], "decision_refs": []}, node_id="N1")

    def complete_node(self, *, start_seq: int = 2, evidence_id: str = "ev-pass") -> list[dict]:
        return [
            self.evidence(start_seq, record_id=evidence_id),
            record(start_seq + 1, "transition", {"from": "pending", "to": "active", "reason_code": "dispatch", "reason": "Ready", "evidence_refs": [], "decision_refs": []}, node_id="N1"),
            record(start_seq + 2, "transition", {"from": "active", "to": "verifying", "reason_code": "work_complete", "reason": "Verify", "evidence_refs": [evidence_id], "decision_refs": []}, node_id="N1"),
            record(start_seq + 3, "transition", {"from": "verifying", "to": "done", "reason_code": "checks_satisfied", "reason": "Pass", "evidence_refs": [evidence_id], "decision_refs": []}, node_id="N1"),
        ]

    def rewrite_plan(self) -> None:
        plan_path = self.root / "plans" / "plan-v1.json"
        plan_path.write_bytes(json_bytes(self.plan))
        self.records[0]["payload"]["plan_sha256"] = hashlib.sha256(plan_path.read_bytes()).hexdigest()


def make_completed_child(parent: Path, directory_name: str) -> Path:
    root = parent / "_loops" / directory_name
    (root / "plans").mkdir(parents=True)
    goal = make_goal()
    goal["loop_id"] = "L900.01"
    goal["origin"] = {"parent_loop_id": "L900", "parent_node_id": "N1"}
    (root / "goal.json").write_bytes(json_bytes(goal))
    plan = make_plan(hashlib.sha256((root / "goal.json").read_bytes()).hexdigest())
    plan["plan_id"] = "plan-L900.01-v1"
    plan["nodes"][0]["outputs"] = [{"path": "result.txt", "purpose": "Child return"}]
    (root / "result.txt").write_text("child result\n", encoding="utf-8")
    (root / "plans" / "plan-v1.json").write_bytes(json_bytes(plan))
    plan_hash = hashlib.sha256((root / "plans" / "plan-v1.json").read_bytes()).hexdigest()
    records = base_records(plan_hash) + [
        record(2, "evidence", {"subject_refs": ["criterion:SC1"], "check_ref": None, "source_class": "direct_test", "origin_ref": "tool:test", "artifact_ref": None, "observed_result": "pass", "summary": "Child result verified.", "limits": "Child scope only.", "valid_until": None, "recheck_when": "Child output changes.", "review_context": None}, record_id="child-evidence"),
        record(3, "completion", {"deliverables": [{"path": "result.txt"}], "criterion_evidence": {"SC1": ["child-evidence"]}, "deterministic_check_refs": [], "system_review_ref": None, "counterexample_review_refs": [], "residual_risks": [], "unmet_scope": [], "authorization_decision_refs": []}, record_id="child-completion"),
    ]
    with (root / "journal.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for item in records:
            handle.write(json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n")
    write_atomic(root / "resume.json", project(root, generated_at="2026-07-31T01:00:00Z"))
    return root


class SchemaRuntimeTests(unittest.TestCase):
    def test_all_v2_schemas_use_2020_12_and_runtime_accepts_examples(self):
        names = ["goal", "plan", "journal-record", "resume", "claim-v2", "artifact-index-v2", "migration-report"]
        for name in names:
            schema = load_json(SCHEMAS / f"{name}.schema.json")
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        for example in (ROOT / "examples" / "example_v2_lightweight", ROOT / "examples" / "example_v2_persistent"):
            self.assertEqual(validate_loop_dir(example), [])

    def test_unknown_keyword_fails_closed(self):
        with self.assertRaises(SchemaError):
            validate({}, {"type": "object", "unevaluatedProperties": False})

    def test_unknown_keyword_in_unused_definition_fails_closed(self):
        with self.assertRaises(SchemaError):
            check_schema({
                "type": "object",
                "$defs": {"unused": {"type": "string", "unevaluatedProperties": False}},
            })

    def test_non_standard_json_numbers_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "invalid.json"
            for constant in ("NaN", "Infinity", "-Infinity"):
                path.write_text(f'{{"value": {constant}}}\n', encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_json(path)
        self.assertTrue(validate(float("nan"), {"type": "number"}))
        self.assertTrue(validate(float("inf"), {"type": "number"}))

    def test_jsonschema_parity_when_available(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is not installed")
        goal = make_goal()
        schema = load_json(SCHEMAS / "goal.schema.json")
        self.assertEqual(validate(goal, schema), [])
        self.assertEqual(list(jsonschema.Draft202012Validator(schema).iter_errors(goal)), [])
        invalid = copy.deepcopy(goal)
        invalid["extra"] = True
        self.assertTrue(validate(invalid, schema))
        self.assertTrue(list(jsonschema.Draft202012Validator(schema).iter_errors(invalid)))

    def test_check_ref_requires_exact_binding_shape(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = LoopFixture(Path(temp))
            schema = load_json(SCHEMAS / "journal-record.schema.json")
            evidence = fixture.evidence(2)
            self.assertEqual(validate(evidence, schema), [])

            evidence["payload"].pop("check_binding")
            self.assertTrue(any("check_binding" in item for item in validate(evidence, schema)))

            criterion_only = fixture.evidence(2)
            criterion_only["payload"]["check_ref"] = None
            criterion_only["payload"].pop("check_binding")
            self.assertEqual(validate(criterion_only, schema), [])


class ProjectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.fixture = LoopFixture(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def test_control_projection(self):
        self.fixture.records += [
            record(2, "transition", {"from": "pending", "to": "active", "reason_code": "dispatch", "reason": "Ready", "evidence_refs": [], "decision_refs": []}, node_id="N1"),
            self.fixture.evidence(),
            record(4, "transition", {"from": "active", "to": "verifying", "reason_code": "work_complete", "reason": "Ready for verification", "evidence_refs": ["ev-pass"], "decision_refs": []}, node_id="N1"),
            record(5, "transition", {"from": "verifying", "to": "done", "reason_code": "checks_satisfied", "reason": "Direct check passed", "evidence_refs": ["ev-pass"], "decision_refs": []}, node_id="N1"),
        ]
        self.fixture.save()
        self.assertEqual(validate_loop_dir(self.fixture.root), [])
        self.assertEqual(project(self.fixture.root)["projection"]["node_states"], {"N1": "done"})

    def assertProjectionRejects(self, needle: str):
        self.fixture.save(render=False)
        with self.assertRaisesRegex(ProjectionError, needle):
            project(self.fixture.root)

    def reset_fixture(self, *, modules: list[str] | None = None) -> None:
        shutil.rmtree(self.fixture.root)
        self.fixture = LoopFixture(Path(self.temp.name), modules=modules)

    def make_lightweight_upgrade(self) -> None:
        self.fixture.plan["control"] = {
            "mode": "lightweight",
            "modules": [],
            "admission_reason": "A stable single-session dependency plan is enough initially.",
        }
        self.fixture.rewrite_plan()
        plan_v2 = copy.deepcopy(self.fixture.plan)
        plan_v2.update({"plan_id": "plan-L900-v2", "plan_version": 2})
        plan_v2["control"] = {
            "mode": "persistent",
            "modules": [],
            "admission_reason": "A cross-session handoff now requires durable recovery.",
        }
        plan_path = self.fixture.root / "plans" / "plan-v2.json"
        plan_path.write_bytes(json_bytes(plan_v2))
        upgrade_evidence = record(
            2,
            "evidence",
            {
                "subject_refs": ["loop:control_mode"],
                "check_ref": None,
                "source_class": "control_trigger",
                "origin_ref": "session-boundary",
                "artifact_ref": None,
                "observed_result": "observation",
                "summary": "The work now needs a cross-session handoff.",
                "limits": "This establishes only the control-mode trigger.",
                "valid_until": None,
                "recheck_when": "The handoff requirement changes.",
                "review_context": None,
            },
            record_id="ev-upgrade",
        )
        upgrade_decision = record(
            3,
            "decision",
            {
                "question": "control_mode_upgrade",
                "outcome": "persistent",
                "rationale": "The cited handoff observation crosses the lightweight boundary.",
                "authority": "model",
                "evidence_refs": ["ev-upgrade"],
                "authorization_boundary_ref": None,
                "reconsider_when": "The handoff requirement changes.",
                "overrides_evidence_ref": None,
                "plan_change": None,
            },
            record_id="decision-upgrade",
        )
        activation = record(
            4,
            "plan_activated",
            {
                "plan_ref": "plans/plan-v2.json",
                "plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                "previous_version": 1,
                "reason": "Upgrade before recording durable runtime facts.",
                "evidence_refs": ["ev-upgrade"],
                "decision_ref": "decision-upgrade",
            },
            record_id="activation-v2",
        )
        activation["plan_version"] = 2
        self.fixture.records += [upgrade_evidence, upgrade_decision, activation]

    def test_lightweight_upgrade_prefix_is_projectable(self):
        self.make_lightweight_upgrade()
        self.fixture.save()
        self.assertEqual(validate_loop_dir(self.fixture.root), [])
        projected = project(self.fixture.root)
        self.assertEqual(projected["source"]["plan_version"], 2)
        self.assertEqual(projected["projection"]["loop_status"], "active")

    def test_lightweight_upgrade_rejects_runtime_work_before_activation(self):
        self.make_lightweight_upgrade()
        self.fixture.records.insert(
            1,
            record(
                2,
                "transition",
                {
                    "from": "pending",
                    "to": "active",
                    "reason_code": "dispatch",
                    "reason": "Work started too early.",
                    "evidence_refs": [],
                    "decision_refs": [],
                },
                node_id="N1",
            ),
        )
        for seq, item in enumerate(self.fixture.records, start=1):
            item["seq"] = seq
            item["ts"] = f"2026-07-31T00:{seq:02d}:00Z"
        self.fixture.save(render=False)
        errors = validate_loop_dir(self.fixture.root)
        self.assertTrue(any("bounded upgrade prefix" in item for item in errors), errors)
        with self.assertRaisesRegex(ProjectionError, "bounded upgrade prefix"):
            project(self.fixture.root)

    def test_lightweight_upgrade_rejects_unconsumed_causal_pair(self):
        self.make_lightweight_upgrade()
        self.fixture.records[-1]["payload"]["evidence_refs"] = ["ev-other"]
        self.fixture.save(render=False)
        errors = validate_loop_dir(self.fixture.root)
        self.assertTrue(any("must consume" in item for item in errors), errors)
        with self.assertRaisesRegex(ProjectionError, "must consume"):
            project(self.fixture.root)

    def test_lightweight_upgrade_rejects_mode_decision_mismatch(self):
        self.make_lightweight_upgrade()
        self.fixture.records[-2]["payload"]["outcome"] = "governed"
        self.fixture.save(render=False)
        errors = validate_loop_dir(self.fixture.root)
        self.assertTrue(any("must consume" in item for item in errors), errors)
        with self.assertRaisesRegex(ProjectionError, "must consume"):
            project(self.fixture.root)

    def test_lightweight_upgrade_rejects_bundled_plan_semantic_changes(self):
        mutations = (
            lambda plan: plan["nodes"][0].update({"objective": "Changed objective."}),
            lambda plan: plan["nodes"][0]["checks"][0].update({"instruction": "Changed check."}),
            lambda plan: plan["nodes"][0].update(
                {"outputs": [{"path": "result.txt", "purpose": "Changed output."}]}
            ),
            lambda plan: plan["nodes"][0].update({"depends_on": ["N2"]}),
            lambda plan: plan["nodes"][0].update({"authorization_refs": ["AUTH1"]}),
            lambda plan: plan["nodes"][0].update(
                {
                    "child_loop": {
                        "loop_id": "L900.01",
                        "return_deliverables": ["result.txt"],
                        "return_criteria_refs": ["SC1"],
                    }
                }
            ),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                self.reset_fixture()
                self.make_lightweight_upgrade()
                plan_path = self.fixture.root / "plans" / "plan-v2.json"
                plan_v2 = json.loads(plan_path.read_text(encoding="utf-8"))
                mutate(plan_v2)
                plan_path.write_bytes(json_bytes(plan_v2))
                self.fixture.records[-1]["payload"]["plan_sha256"] = hashlib.sha256(
                    plan_path.read_bytes()
                ).hexdigest()
                self.fixture.save(render=False)
                errors = validate_loop_dir(self.fixture.root)
                self.assertTrue(errors)
                with self.assertRaisesRegex(
                    ProjectionError, "may change only|GRAPH-DANGLING|GRAPH-AUTH|CHILD-"
                ):
                    project(self.fixture.root)

    def test_lightweight_upgrade_rejects_plan_change_binding(self):
        self.make_lightweight_upgrade()
        self.fixture.records[-2]["payload"]["plan_change"] = {
            "from_plan_version": 1,
            "from_plan_sha256": self.fixture.records[0]["payload"]["plan_sha256"],
            "to_plan_version": 2,
            "to_plan_sha256": self.fixture.records[-1]["payload"]["plan_sha256"],
        }
        self.fixture.save(render=False)
        with self.assertRaisesRegex(ProjectionError, "must immediately cite|must consume"):
            project(self.fixture.root)

        self.reset_fixture()
        self.make_lightweight_upgrade()
        del self.fixture.records[-2]["payload"]["plan_change"]
        self.fixture.save(render=False)
        with self.assertRaisesRegex(ProjectionError, "must immediately cite"):
            project(self.fixture.root)

    def add_second_node(self) -> None:
        second = copy.deepcopy(self.fixture.plan["nodes"][0])
        second["id"] = "N2"
        second["objective"] = "Produce an independent result."
        second["checks"][0]["id"] = "check-N2"
        self.fixture.plan["nodes"].append(second)
        self.fixture.rewrite_plan()

    def write_claim(self, filename: str, value: dict) -> None:
        claim_dir = self.fixture.root / "claims"
        claim_dir.mkdir(exist_ok=True)
        (claim_dir / filename).write_bytes(json_bytes(value))

    def test_rejects_seq_gap(self):
        self.fixture.records.append(record(3, "context", {"item_id": "x", "item_type": "risk", "status": "open", "statement": "x", "evidence_refs": [], "resolution_condition": "y"}))
        self.assertProjectionRejects("JOURNAL-SEQ")

    def test_rejects_direct_done(self):
        self.fixture.records.append(record(2, "transition", {"from": "pending", "to": "done", "reason_code": "bypass", "reason": "bad", "evidence_refs": [], "decision_refs": []}, node_id="N1"))
        self.assertProjectionRejects("illegal")

    def test_rejects_chain_discontinuity(self):
        self.fixture.records.append(record(2, "transition", {"from": "active", "to": "verifying", "reason_code": "bad", "reason": "bad", "evidence_refs": [], "decision_refs": []}, node_id="N1"))
        self.assertProjectionRejects("JOURNAL-CHAIN")

    def test_rejects_unknown_node(self):
        self.fixture.records.append(record(2, "transition", {"from": "pending", "to": "active", "reason_code": "bad", "reason": "bad", "evidence_refs": [], "decision_refs": []}, node_id="N404"))
        self.assertProjectionRejects("GRAPH-NODE")

    def test_exact_effect_pairing(self):
        self.reset_fixture(modules=["effects"])
        self.fixture.records += [
            self.fixture.activate_node(),
            record(3, "effect_pre", {"effect_id": "deploy", "attempt_id": "a1", "operation": "deploy", "target": "staging", "idempotency_key": "deploy-a1", "authorization_decision_ref": None, "authorization_boundary_ref": None, "expected_postcondition": "healthy", "compensation_ref": None}, node_id="N1"),
            record(4, "effect_post", {"effect_id": "deploy", "attempt_id": "a2", "outcome": "succeeded", "observed_postcondition": "healthy", "result_ref": "tool:deploy"}, node_id="N1"),
        ]
        self.assertProjectionRejects("EFFECT-PAIR")

    def test_effect_succeeded_closes_attempt(self):
        self.reset_fixture(modules=["effects"])
        self.fixture.records += [
            self.fixture.activate_node(),
            record(3, "effect_pre", {"effect_id": "deploy", "attempt_id": "a1", "operation": "deploy", "target": "staging", "idempotency_key": "deploy-a1", "authorization_decision_ref": None, "authorization_boundary_ref": None, "expected_postcondition": "healthy", "compensation_ref": None}, node_id="N1"),
            record(4, "effect_post", {"effect_id": "deploy", "attempt_id": "a1", "outcome": "succeeded", "observed_postcondition": "healthy", "result_ref": "tool:deploy"}, node_id="N1"),
        ]
        self.fixture.save()
        self.assertEqual(validate_loop_dir(self.fixture.root), [])
        self.assertEqual(project(self.fixture.root)["projection"]["in_doubt_effect_ids"], [])

    def test_unmatched_effect_pre_remains_in_doubt_and_blocks_completion(self):
        self.reset_fixture(modules=["effects"])
        self.fixture.records += [
            self.fixture.activate_node(),
            record(3, "effect_pre", {"effect_id": "deploy", "attempt_id": "a1", "operation": "deploy", "target": "staging", "idempotency_key": "deploy-a1", "authorization_decision_ref": None, "authorization_boundary_ref": None, "expected_postcondition": "healthy", "compensation_ref": None}, node_id="N1"),
        ]
        self.fixture.save()
        self.assertEqual(project(self.fixture.root)["projection"]["in_doubt_effect_ids"], ["deploy:a1"])

        self.fixture.records += [
            self.fixture.evidence(4),
            record(5, "completion", {"deliverables": [], "criterion_evidence": {"SC1": ["ev-pass"]}, "deterministic_check_refs": [], "system_review_ref": None, "counterexample_review_refs": [], "residual_risks": [], "unmet_scope": [], "authorization_decision_refs": []}, record_id="completion-1"),
        ]
        self.assertProjectionRejects("in-doubt effects remain")

    def test_unknown_effect_observation_stays_in_doubt_until_conclusive_post(self):
        self.reset_fixture(modules=["effects"])
        self.fixture.records += [
            self.fixture.activate_node(),
            record(3, "effect_pre", {"effect_id": "deploy", "attempt_id": "a1", "operation": "deploy", "target": "staging", "idempotency_key": "deploy-a1", "authorization_decision_ref": None, "authorization_boundary_ref": None, "expected_postcondition": "healthy", "compensation_ref": None}, node_id="N1"),
            record(4, "effect_post", {"effect_id": "deploy", "attempt_id": "a1", "outcome": "unknown", "observed_postcondition": "Reality check was inconclusive.", "result_ref": "tool:deploy-check-1"}, node_id="N1"),
        ]
        self.fixture.save()
        self.assertEqual(validate_loop_dir(self.fixture.root), [])
        self.assertEqual(project(self.fixture.root)["projection"]["in_doubt_effect_ids"], ["deploy:a1"])

        self.fixture.records.append(
            record(5, "effect_post", {"effect_id": "deploy", "attempt_id": "a1", "outcome": "succeeded", "observed_postcondition": "Deployment is healthy.", "result_ref": "tool:deploy-check-2"}, node_id="N1")
        )
        self.fixture.save()
        self.assertEqual(validate_loop_dir(self.fixture.root), [])
        self.assertEqual(project(self.fixture.root)["projection"]["in_doubt_effect_ids"], [])

    def test_effect_identity_and_reality_fields_are_required(self):
        cases = [
            ({"effect_id": "", "attempt_id": "a1", "operation": "deploy", "target": "staging", "idempotency_key": "deploy-a1", "authorization_decision_ref": None, "authorization_boundary_ref": None, "expected_postcondition": "healthy", "compensation_ref": None}, "SCHEMA-JOURNAL.*effect_id"),
            ({"effect_id": "deploy", "attempt_id": "a1", "operation": "deploy", "target": "staging", "idempotency_key": None, "authorization_decision_ref": None, "authorization_boundary_ref": None, "expected_postcondition": "healthy", "compensation_ref": None}, "EFFECT-COMPENSATION"),
        ]
        for payload, needle in cases:
            with self.subTest(needle=needle):
                self.reset_fixture(modules=["effects"])
                self.fixture.records += [self.fixture.activate_node(), record(3, "effect_pre", payload, node_id="N1")]
                self.assertProjectionRejects(needle)

        post_cases = [
            ({"effect_id": "deploy", "attempt_id": "a1", "outcome": "invalid", "observed_postcondition": "healthy", "result_ref": "tool:deploy"}, "SCHEMA-JOURNAL.*outcome"),
            ({"effect_id": "deploy", "attempt_id": "a1", "outcome": "succeeded", "observed_postcondition": "", "result_ref": "tool:deploy"}, "SCHEMA-JOURNAL.*observed_postcondition"),
            ({"effect_id": "deploy", "attempt_id": "a1", "outcome": "succeeded", "observed_postcondition": "healthy", "result_ref": ""}, "SCHEMA-JOURNAL.*result_ref"),
        ]
        for payload, needle in post_cases:
            with self.subTest(needle=needle):
                self.reset_fixture(modules=["effects"])
                self.fixture.records += [
                    self.fixture.activate_node(),
                    record(3, "effect_pre", {"effect_id": "deploy", "attempt_id": "a1", "operation": "deploy", "target": "staging", "idempotency_key": "deploy-a1", "authorization_decision_ref": None, "authorization_boundary_ref": None, "expected_postcondition": "healthy", "compensation_ref": None}, node_id="N1"),
                    record(4, "effect_post", payload, node_id="N1"),
                ]
                self.assertProjectionRejects(needle)

    def test_conclusive_effect_post_is_unique(self):
        for second_outcome in ("failed", "unknown"):
            with self.subTest(second_outcome=second_outcome):
                self.reset_fixture(modules=["effects"])
                self.fixture.records += [
                    self.fixture.activate_node(),
                    record(3, "effect_pre", {"effect_id": "deploy", "attempt_id": "a1", "operation": "deploy", "target": "staging", "idempotency_key": "deploy-a1", "authorization_decision_ref": None, "authorization_boundary_ref": None, "expected_postcondition": "healthy", "compensation_ref": None}, node_id="N1"),
                    record(4, "effect_post", {"effect_id": "deploy", "attempt_id": "a1", "outcome": "succeeded", "observed_postcondition": "healthy", "result_ref": "tool:deploy-1"}, node_id="N1"),
                    record(5, "effect_post", {"effect_id": "deploy", "attempt_id": "a1", "outcome": second_outcome, "observed_postcondition": "second observation", "result_ref": "tool:deploy-2"}, node_id="N1"),
                ]
                self.assertProjectionRejects("EFFECT-PAIR")

    def test_failed_and_cancelled_effects_close_without_changing_node_state(self):
        for outcome in ("failed", "cancelled"):
            with self.subTest(outcome=outcome):
                self.reset_fixture(modules=["effects"])
                self.fixture.records += [
                    self.fixture.activate_node(),
                    record(3, "effect_pre", {"effect_id": "deploy", "attempt_id": "a1", "operation": "deploy", "target": "staging", "idempotency_key": "deploy-a1", "authorization_decision_ref": None, "authorization_boundary_ref": None, "expected_postcondition": "healthy", "compensation_ref": None}, node_id="N1"),
                    record(4, "effect_post", {"effect_id": "deploy", "attempt_id": "a1", "outcome": outcome, "observed_postcondition": f"Effect {outcome}.", "result_ref": "tool:deploy"}, node_id="N1"),
                ]
                self.fixture.save()
                projection = project(self.fixture.root)["projection"]
                self.assertEqual(projection["in_doubt_effect_ids"], [])
                self.assertEqual(projection["node_states"], {"N1": "active"})

    def test_active_done_node_reopens_via_counterevidence_transition(self):
        self.fixture.records += self.fixture.complete_node()
        self.fixture.records += [
            self.fixture.evidence(6, result="fail", record_id="ev-counter"),
            record(7, "evidence_relation", {"source_evidence_ref": "ev-counter", "target_evidence_ref": "ev-pass", "relation": "invalidates", "reason": "Regression."}, record_id="rel-1"),
            record(8, "transition", {"from": "done", "to": "active", "reason_code": "counterevidence", "reason": "Repair regression", "evidence_refs": ["ev-counter"], "decision_refs": []}, node_id="N1"),
        ]
        self.fixture.save()
        projection = project(self.fixture.root)["projection"]
        self.assertEqual(projection["loop_status"], "active")
        self.assertEqual(projection["node_states"], {"N1": "active"})

    def test_active_done_node_invalidation_requires_local_reopen(self):
        self.fixture.records += self.fixture.complete_node()
        self.fixture.records += [
            self.fixture.evidence(6, result="fail", record_id="ev-counter"),
            record(7, "evidence_relation", {"source_evidence_ref": "ev-counter", "target_evidence_ref": "ev-pass", "relation": "invalidates", "reason": "Regression."}, record_id="rel-1"),
        ]
        self.assertProjectionRejects("node-local reopen")

    def test_direct_same_check_failure_requires_local_reopen(self):
        self.fixture.records += self.fixture.complete_node()
        self.fixture.records.append(self.fixture.evidence(6, result="fail", record_id="ev-counter"))
        self.assertProjectionRejects("node-local reopen")

        self.fixture.records.append(
            record(7, "transition", {"from": "done", "to": "active", "reason_code": "counterevidence", "reason": "Repair regression", "evidence_refs": ["ev-counter"], "decision_refs": []}, node_id="N1")
        )
        self.fixture.save()
        self.assertEqual(project(self.fixture.root)["projection"]["node_states"], {"N1": "active"})

    def test_done_to_active_requires_exact_current_counterevidence(self):
        cases = [
            ([], "requires current counterevidence"),
            (["ev-pass"], "must cite counterevidence"),
        ]
        for refs, needle in cases:
            with self.subTest(refs=refs):
                self.reset_fixture()
                self.fixture.records += self.fixture.complete_node()
                if refs:
                    self.fixture.records.append(self.fixture.evidence(6, result="fail", record_id="ev-counter"))
                    seq = 7
                else:
                    seq = 6
                self.fixture.records.append(
                    record(seq, "transition", {"from": "done", "to": "active", "reason_code": "counterevidence", "reason": "Repair", "evidence_refs": refs, "decision_refs": []}, node_id="N1")
                )
                self.assertProjectionRejects(needle)

    def test_expired_done_evidence_requires_reverification(self):
        evidence = self.fixture.evidence(2, record_id="ev-pass")
        evidence["payload"]["valid_until"] = "2026-07-31T00:30:00Z"
        self.fixture.records += [
            evidence,
            record(3, "transition", {"from": "pending", "to": "active", "reason_code": "dispatch", "reason": "Ready", "evidence_refs": [], "decision_refs": []}, node_id="N1"),
            record(4, "transition", {"from": "active", "to": "verifying", "reason_code": "work_complete", "reason": "Verify", "evidence_refs": ["ev-pass"], "decision_refs": []}, node_id="N1"),
            record(5, "transition", {"from": "verifying", "to": "done", "reason_code": "checks_satisfied", "reason": "Pass", "evidence_refs": ["ev-pass"], "decision_refs": []}, node_id="N1"),
        ]
        self.fixture.save(render=False)
        with self.assertRaisesRegex(ProjectionError, "node-local reopen"):
            project(self.fixture.root, generated_at="2026-07-31T01:00:00Z")

    def test_resolved_challenge_keeps_done_valid(self):
        self.fixture.records += self.fixture.complete_node()
        self.fixture.records += [
            self.fixture.evidence(6, result="fail", record_id="ev-challenge"),
            record(7, "evidence_relation", {"source_evidence_ref": "ev-challenge", "target_evidence_ref": "ev-pass", "relation": "challenges", "reason": "Potential regression."}, record_id="rel-challenge"),
            self.fixture.evidence(8, record_id="ev-resolution"),
            record(9, "evidence_relation", {"source_evidence_ref": "ev-resolution", "target_evidence_ref": "ev-challenge", "relation": "supersedes", "reason": "Fresh direct test resolves the challenge."}, record_id="rel-resolution"),
        ]
        self.fixture.save()
        self.assertEqual(project(self.fixture.root)["projection"]["node_states"], {"N1": "done"})

    def test_reopened_dependency_removes_downstream_readiness(self):
        self.add_second_node()
        self.fixture.plan["nodes"][1]["depends_on"] = ["N1"]
        self.fixture.rewrite_plan()
        self.fixture.records += self.fixture.complete_node()
        self.fixture.save()
        self.assertEqual(project(self.fixture.root)["projection"]["ready_nodes"], ["N2"])

        self.fixture.records += [
            self.fixture.evidence(6, result="fail", record_id="ev-counter"),
            record(7, "transition", {"from": "done", "to": "active", "reason_code": "counterevidence", "reason": "Repair", "evidence_refs": ["ev-counter"], "decision_refs": []}, node_id="N1"),
        ]
        self.fixture.save()
        self.assertEqual(project(self.fixture.root)["projection"]["ready_nodes"], [])

    def test_single_active_claim_is_valid(self):
        self.reset_fixture(modules=["concurrency"])
        self.write_claim("N1.json", claim(node_id="N1", token="token-1", scope_paths=["src/a/"]))
        self.fixture.save()
        self.assertEqual(validate_loop_dir(self.fixture.root), [])

    def test_claim_requires_concurrency_module(self):
        self.write_claim("N1.json", claim(node_id="N1", token="token-1", scope_paths=["src/a"]))
        self.fixture.save()
        self.assertTrue(any("CLAIM-MODULE" in item for item in validate_loop_dir(self.fixture.root)))

    def test_claim_tokens_are_unique_across_loop(self):
        self.reset_fixture(modules=["concurrency"])
        self.add_second_node()
        self.write_claim("N1.json", claim(node_id="N1", token="same-token", scope_paths=["src/a"]))
        self.write_claim("N2.json", claim(node_id="N2", token="same-token", scope_paths=["src/b"], owner_id="agent-b"))
        self.fixture.save()
        self.assertTrue(any("CLAIM-TOKEN" in item for item in validate_loop_dir(self.fixture.root)))

    def test_each_node_has_at_most_one_active_claim_and_canonical_filename(self):
        self.reset_fixture(modules=["concurrency"])
        self.write_claim("N1.json", claim(node_id="N1", token="token-1", scope_paths=["src/a"]))
        self.write_claim("other.json", claim(node_id="N1", token="token-2", scope_paths=["src/b"], owner_id="agent-b"))
        self.fixture.save()
        errors = validate_loop_dir(self.fixture.root)
        self.assertTrue(any("CLAIM-FILENAME" in item for item in errors))
        self.assertTrue(any("CLAIM-NODE" in item for item in errors))

    def test_claim_scope_overlap_rejects_equal_ancestor_and_windows_aliases(self):
        cases = [
            (["src/a"], ["src/a"], "equal"),
            (["src"], ["src/a"], "ancestor"),
            (["Src\\A\\"], ["src/a"], "case-and-slash"),
            (["src/./a/"], ["SRC/a"], "dot-and-trailing-slash"),
        ]
        for left, right, label in cases:
            with self.subTest(label=label):
                self.reset_fixture(modules=["concurrency"])
                self.add_second_node()
                self.write_claim("N1.json", claim(node_id="N1", token="token-1", scope_paths=left))
                self.write_claim("N2.json", claim(node_id="N2", token="token-2", scope_paths=right, owner_id="agent-b"))
                self.fixture.save()
                self.assertTrue(any("CLAIM-OVERLAP" in item for item in validate_loop_dir(self.fixture.root)))

    def test_sibling_claim_scopes_are_valid(self):
        self.reset_fixture(modules=["concurrency"])
        self.add_second_node()
        self.write_claim("N1.json", claim(node_id="N1", token="token-1", scope_paths=["src/a/"]))
        self.write_claim("N2.json", claim(node_id="N2", token="token-2", scope_paths=["src/b/"], owner_id="agent-b"))
        self.fixture.save()
        self.assertEqual(validate_loop_dir(self.fixture.root), [])

    def test_overlapping_claims_reject_even_for_same_owner(self):
        self.reset_fixture(modules=["concurrency"])
        self.add_second_node()
        self.write_claim("N1.json", claim(node_id="N1", token="token-1", scope_paths=["src"]))
        self.write_claim("N2.json", claim(node_id="N2", token="token-2", scope_paths=["src/a"]))
        self.fixture.save()
        self.assertTrue(any("CLAIM-OVERLAP" in item for item in validate_loop_dir(self.fixture.root)))

    def test_expired_claim_fails_but_does_not_create_active_overlap(self):
        self.reset_fixture(modules=["concurrency"])
        self.add_second_node()
        expired = claim(node_id="N1", token="token-1", scope_paths=["src"], expires_at="2000-01-01T00:02:00Z")
        expired["acquired_at"] = "2000-01-01T00:00:00Z"
        expired["heartbeat_at"] = "2000-01-01T00:01:00Z"
        self.write_claim("N1.json", expired)
        self.write_claim("N2.json", claim(node_id="N2", token="token-2", scope_paths=["src/a"], owner_id="agent-b"))
        self.fixture.save()
        errors = validate_loop_dir(self.fixture.root)
        self.assertTrue(any("CLAIM-EXPIRED" in item for item in errors))
        self.assertFalse(any("CLAIM-OVERLAP" in item for item in errors))

    def test_claim_identity_and_paths_are_confined(self):
        cases = [
            ("bad-loop", claim(node_id="N1", token="token-1", scope_paths=["src/a"]) | {"loop_id": "L404"}, "CLAIM-IDENTITY"),
            ("bad-node", claim(node_id="N404", token="token-1", scope_paths=["src/a"]), "CLAIM-IDENTITY"),
            ("bad-plan", claim(node_id="N1", token="token-1", scope_paths=["src/a"]) | {"plan_version": 2}, "CLAIM-IDENTITY"),
            ("parent", claim(node_id="N1", token="token-1", scope_paths=["../outside"]), "CLAIM-PATH"),
            ("drive", claim(node_id="N1", token="token-1", scope_paths=["C:\\outside"]), "CLAIM-PATH"),
            ("unc", claim(node_id="N1", token="token-1", scope_paths=["\\\\server\\share"]), "CLAIM-PATH"),
            ("ads", claim(node_id="N1", token="token-1", scope_paths=["src/file.txt:stream"]), "CLAIM-PATH"),
            ("reserved-device", claim(node_id="N1", token="token-1", scope_paths=["src/CON.txt"]), "CLAIM-PATH"),
        ]
        for label, value, needle in cases:
            with self.subTest(label=label):
                self.reset_fixture(modules=["concurrency"])
                self.write_claim(f"{value['node_id']}.json", value)
                self.fixture.save()
                self.assertTrue(any(needle in item for item in validate_loop_dir(self.fixture.root)))

    def test_old_pass_new_fail_cannot_complete(self):
        self.fixture.records += [
            self.fixture.evidence(2, record_id="ev-old"),
            self.fixture.evidence(3, result="fail", record_id="ev-new-fail"),
            record(4, "evidence_relation", {"source_evidence_ref": "ev-new-fail", "target_evidence_ref": "ev-old", "relation": "invalidates", "reason": "New test failed."}, record_id="rel-1"),
            record(5, "completion", {"deliverables": [], "criterion_evidence": {"SC1": ["ev-old"]}, "deterministic_check_refs": [], "system_review_ref": None, "counterexample_review_refs": [], "residual_risks": [], "unmet_scope": [], "authorization_decision_refs": []}, record_id="completion-1"),
        ]
        self.assertProjectionRejects("active evidence")

    def test_challenged_evidence_cannot_complete(self):
        self.fixture.records += [
            self.fixture.evidence(2, record_id="ev-old"),
            self.fixture.evidence(3, result="fail", record_id="ev-challenge"),
            record(4, "evidence_relation", {"source_evidence_ref": "ev-challenge", "target_evidence_ref": "ev-old", "relation": "challenges", "reason": "Counterexample."}, record_id="rel-1"),
            record(5, "completion", {"deliverables": [], "criterion_evidence": {"SC1": ["ev-old"]}, "deterministic_check_refs": [], "system_review_ref": None, "counterexample_review_refs": [], "residual_risks": [], "unmet_scope": [], "authorization_decision_refs": []}, record_id="completion-1"),
        ]
        self.assertProjectionRejects("active evidence")

    def test_reopen_requires_counterevidence(self):
        self.fixture.records += [
            self.fixture.evidence(2),
            record(3, "completion", {"deliverables": [], "criterion_evidence": {"SC1": ["ev-pass"]}, "deterministic_check_refs": [], "system_review_ref": None, "counterexample_review_refs": [], "residual_risks": [], "unmet_scope": [], "authorization_decision_refs": []}, record_id="completion-1"),
            record(4, "reopen", {"completion_ref": "completion-1", "counterevidence_refs": [], "affected_criterion_refs": ["SC1"], "affected_node_ids": ["N1"], "action": "retest", "reason": "reported issue"}, record_id="reopen-1"),
        ]
        self.assertProjectionRejects("counterevidence")

    def test_plan_activation_cannot_reference_future_evidence(self):
        self.fixture.records[0]["payload"]["evidence_refs"] = ["ev-future"]
        self.fixture.records.append(self.fixture.evidence(2, record_id="ev-future"))
        self.assertProjectionRejects("non-prior")

    def test_tail_invalidation_requires_explicit_reopen(self):
        self.fixture.records += [
            self.fixture.evidence(2, record_id="ev-pass"),
            record(3, "completion", {"deliverables": [], "criterion_evidence": {"SC1": ["ev-pass"]}, "deterministic_check_refs": [], "system_review_ref": None, "counterexample_review_refs": [], "residual_risks": [], "unmet_scope": [], "authorization_decision_refs": []}, record_id="completion-1"),
            self.fixture.evidence(4, result="fail", record_id="ev-counter"),
            record(5, "evidence_relation", {"source_evidence_ref": "ev-counter", "target_evidence_ref": "ev-pass", "relation": "invalidates", "reason": "Regression."}, record_id="rel-1"),
        ]
        self.assertProjectionRejects("without an explicit reopen")

    def test_reopen_requires_failed_evidence_covering_affected_subjects(self):
        self.fixture.records += [
            self.fixture.evidence(2, record_id="ev-pass"),
            record(3, "completion", {"deliverables": [], "criterion_evidence": {"SC1": ["ev-pass"]}, "deterministic_check_refs": [], "system_review_ref": None, "counterexample_review_refs": [], "residual_risks": [], "unmet_scope": [], "authorization_decision_refs": []}, record_id="completion-1"),
            record(4, "evidence", {"subject_refs": ["criterion:SC1"], "check_ref": None, "source_class": "user_report", "origin_ref": "user", "artifact_ref": None, "observed_result": "fail", "summary": "Regression.", "limits": "Node is not identified.", "valid_until": None, "recheck_when": "After repair.", "review_context": None}, record_id="ev-counter"),
            record(5, "reopen", {"completion_ref": "completion-1", "counterevidence_refs": ["ev-counter"], "affected_criterion_refs": ["SC1"], "affected_node_ids": ["N1"], "action": "repair", "reason": "Regression."}, record_id="reopen-1"),
        ]
        self.assertProjectionRejects("does not cover")

    def test_reopen_control_accepts_failed_counterevidence_and_transition(self):
        self.fixture.records += [
            self.fixture.evidence(2, record_id="ev-pass"),
            record(3, "transition", {"from": "pending", "to": "active", "reason_code": "dispatch", "reason": "Ready", "evidence_refs": [], "decision_refs": []}, node_id="N1"),
            record(4, "transition", {"from": "active", "to": "verifying", "reason_code": "work_complete", "reason": "Verify", "evidence_refs": ["ev-pass"], "decision_refs": []}, node_id="N1"),
            record(5, "transition", {"from": "verifying", "to": "done", "reason_code": "checks_satisfied", "reason": "Pass", "evidence_refs": ["ev-pass"], "decision_refs": []}, node_id="N1"),
            record(6, "completion", {"deliverables": [], "criterion_evidence": {"SC1": ["ev-pass"]}, "deterministic_check_refs": [], "system_review_ref": None, "counterexample_review_refs": [], "residual_risks": [], "unmet_scope": [], "authorization_decision_refs": []}, record_id="completion-1"),
            self.fixture.evidence(7, result="fail", record_id="ev-counter"),
            record(8, "evidence_relation", {"source_evidence_ref": "ev-counter", "target_evidence_ref": "ev-pass", "relation": "invalidates", "reason": "Regression."}, record_id="rel-1"),
            record(9, "reopen", {"completion_ref": "completion-1", "counterevidence_refs": ["ev-counter"], "affected_criterion_refs": ["SC1"], "affected_node_ids": ["N1"], "action": "repair", "reason": "Regression."}, record_id="reopen-1"),
            record(10, "transition", {"from": "done", "to": "active", "reason_code": "counterevidence", "reason": "Repair", "evidence_refs": ["ev-counter"], "decision_refs": []}, node_id="N1"),
        ]
        self.fixture.save()
        self.assertEqual(validate_loop_dir(self.fixture.root), [])
        self.assertEqual(project(self.fixture.root)["projection"]["loop_status"], "active")

    def test_orphan_higher_persistent_plan_does_not_change_active_mode(self):
        orphan = make_plan(self.fixture.plan["goal_sha256"], mode="lightweight", version=2)
        (self.fixture.root / "plans" / "plan-v2.json").write_bytes(json_bytes(orphan))
        self.fixture.save()
        self.assertEqual(validate_loop_dir(self.fixture.root), [])
        self.assertEqual(project(self.fixture.root)["source"]["plan_version"], 1)

    def test_child_is_discovered_by_goal_id_under_parent_loops_directory(self):
        self.fixture.plan["control"]["mode"] = "governed"
        self.fixture.plan["control"]["modules"] = ["children"]
        self.fixture.plan["nodes"][0]["child_loop"] = {"loop_id": "L900.01", "return_deliverables": ["result.txt"], "return_criteria_refs": ["SC1"]}
        self.fixture.plan["nodes"][0]["outputs"] = [{"path": "result.txt", "purpose": "Child return deliverable."}]
        (self.fixture.root / "plans" / "plan-v1.json").write_bytes(json_bytes(self.fixture.plan))
        self.fixture.records[0]["payload"]["plan_sha256"] = hashlib.sha256((self.fixture.root / "plans" / "plan-v1.json").read_bytes()).hexdigest()
        make_completed_child(self.fixture.root, "L900.01-child-slug")
        self.fixture.save()
        self.assertEqual(validate_loop_dir(self.fixture.root), [])

    def test_ambiguous_child_goal_id_is_rejected(self):
        self.fixture.plan["control"]["mode"] = "governed"
        self.fixture.plan["control"]["modules"] = ["children"]
        self.fixture.plan["nodes"][0]["child_loop"] = {"loop_id": "L900.01", "return_deliverables": ["result.txt"], "return_criteria_refs": ["SC1"]}
        self.fixture.plan["nodes"][0]["outputs"] = [{"path": "result.txt", "purpose": "Child return deliverable."}]
        (self.fixture.root / "plans" / "plan-v1.json").write_bytes(json_bytes(self.fixture.plan))
        self.fixture.records[0]["payload"]["plan_sha256"] = hashlib.sha256((self.fixture.root / "plans" / "plan-v1.json").read_bytes()).hexdigest()
        make_completed_child(self.fixture.root, "L900.01-first")
        make_completed_child(self.fixture.root, "L900.01-second")
        self.fixture.save()
        self.assertTrue(any("exactly one directory under _loops" in item for item in validate_loop_dir(self.fixture.root)))

    def test_enabled_modules_do_not_require_live_claim_or_completed_review(self):
        self.fixture.plan["control"]["mode"] = "governed"
        self.fixture.plan["control"]["modules"] = ["concurrency", "independent_review"]
        (self.fixture.root / "plans" / "plan-v1.json").write_bytes(json_bytes(self.fixture.plan))
        self.fixture.records[0]["payload"]["plan_sha256"] = hashlib.sha256((self.fixture.root / "plans" / "plan-v1.json").read_bytes()).hexdigest()
        self.fixture.save()
        self.assertEqual(validate_loop_dir(self.fixture.root), [])

    def test_unmaterialized_child_is_valid_until_parent_consumes_return(self):
        self.fixture.plan["control"]["mode"] = "governed"
        self.fixture.plan["control"]["modules"] = ["children"]
        self.fixture.plan["nodes"][0]["child_loop"] = {"loop_id": "L900.01", "return_deliverables": ["result.txt"], "return_criteria_refs": ["SC1"]}
        self.fixture.plan["nodes"][0]["outputs"] = [{"path": "result.txt", "purpose": "Child return deliverable."}]
        (self.fixture.root / "plans" / "plan-v1.json").write_bytes(json_bytes(self.fixture.plan))
        self.fixture.records[0]["payload"]["plan_sha256"] = hashlib.sha256((self.fixture.root / "plans" / "plan-v1.json").read_bytes()).hexdigest()
        self.fixture.save()
        self.assertEqual(validate_loop_dir(self.fixture.root), [])

        broken = self.fixture.root / "_loops" / "L900.01-broken"
        broken.mkdir(parents=True)
        (broken / "goal.json").write_text("{not-json\n", encoding="utf-8")
        errors = validate_loop_dir(self.fixture.root)
        self.assertTrue(any("CHILD-PATH cannot read materialized child goal" in item for item in errors), errors)
        shutil.rmtree(broken)

        self.fixture.records += [
            record(2, "transition", {"from": "pending", "to": "active", "reason_code": "dispatch", "reason": "Ready", "evidence_refs": [], "decision_refs": []}, node_id="N1"),
            self.fixture.evidence(3),
            record(4, "transition", {"from": "active", "to": "verifying", "reason_code": "work_complete", "reason": "Verify", "evidence_refs": ["ev-pass"], "decision_refs": []}, node_id="N1"),
            record(5, "transition", {"from": "verifying", "to": "done", "reason_code": "checks_satisfied", "reason": "Return consumed", "evidence_refs": ["ev-pass"], "decision_refs": []}, node_id="N1"),
        ]
        self.fixture.save()
        self.assertTrue(any("has not returned" in item for item in validate_loop_dir(self.fixture.root)))

    def test_resume_freshness_rejects_stale_projection(self):
        self.fixture.save()
        resume = load_json(self.fixture.root / "resume.json")
        resume["source"]["journal_last_seq"] = 99
        write_atomic(self.fixture.root / "resume.json", resume)
        self.assertTrue(any("JOURNAL-FRESHNESS" in item for item in validate_loop_dir(self.fixture.root)))


class MigrationTests(unittest.TestCase):
    def test_dry_run_is_read_only_and_real_migration_is_sibling(self):
        source = ROOT / "examples" / "example_product_delivery"
        before = {path.relative_to(source): hashlib.sha256(path.read_bytes()).hexdigest() for path in source.rglob("*") if path.is_file()}
        with tempfile.TemporaryDirectory() as temp:
            copied_source = Path(temp) / "source"
            shutil.copytree(source, copied_source)
            destination = Path(temp) / "migrated"
            command = [sys.executable, str(SCRIPTS / "migrate_v1.py"), str(copied_source), str(destination), "--dry-run"]
            dry = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertFalse(destination.exists())
            report = json.loads(dry.stdout)
            self.assertTrue(any("legacy completed" in item for item in report["warnings"]))
            real = subprocess.run(command[:-1], text=True, capture_output=True, check=False)
            self.assertEqual(real.returncode, 0, real.stderr)
            self.assertEqual(validate_loop_dir(destination), [])
            self.assertNotEqual(load_json(destination / "resume.json")["projection"]["loop_status"], "completed")
        after = {path.relative_to(source): hashlib.sha256(path.read_bytes()).hexdigest() for path in source.rglob("*") if path.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
