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
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from project_loop import project  # noqa: E402
from render_resume import write_atomic  # noqa: E402
from schema_runtime import load_json, validate  # noqa: E402
from test_v2_protocol import LoopFixture, claim, json_bytes, record  # noqa: E402
from validate_loop_dir import validate_loop_dir  # noqa: E402


class DateTimeValidationTests(unittest.TestCase):
    def test_rfc3339_requires_full_time_seconds_and_timezone(self):
        schema = {"type": "string", "format": "date-time"}
        for value in (
            "2026-07-31T00:00:00Z",
            "2026-07-31T00:00:00.123+08:00",
            "2026-07-31T00:00:00-05:30",
        ):
            with self.subTest(value=value):
                self.assertEqual(validate(value, schema), [])

        for value in (
            "2026-07-31",
            "2026-07-31 00:00:00Z",
            "2026-07-31T00:00Z",
            "2026-07-31T00:00:00",
            "2026-07-31T00:00:00+00",
            "2025-02-29T00:00:00Z",
            "2026-07-31T24:00:00Z",
            "2026-07-31T00:00:00+24:00",
        ):
            with self.subTest(value=value):
                self.assertTrue(validate(value, schema))


class ValidatorHardeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.fixture = LoopFixture(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def reset_fixture(self, *, modules: list[str] | None = None) -> None:
        shutil.rmtree(self.fixture.root, ignore_errors=True)
        self.fixture = LoopFixture(Path(self.temp.name), modules=modules)

    def write_claim(self, filename: str, value: dict) -> None:
        claim_dir = self.fixture.root / "claims"
        claim_dir.mkdir(exist_ok=True)
        (claim_dir / filename).write_bytes(json_bytes(value))

    def write_artifact_index(self, artifacts: object) -> None:
        (self.fixture.root / "artifact-index.json").write_bytes(
            json_bytes({"schema_version": "2.0", "artifacts": artifacts})
        )

    @staticmethod
    def bind_artifact(evidence: dict, artifact: dict) -> None:
        evidence["payload"]["artifact_ref"] = artifact["artifact_id"]
        evidence["payload"]["artifact_binding"] = {
            "path": artifact["path"],
            "sha256": artifact["sha256"],
        }

    def activate_plan(self, plan: dict, *, seq: int) -> None:
        evidence_ref = f"replan-cause-{plan['plan_version']}"
        decision_ref = f"replan-decision-{plan['plan_version']}"
        prior_plan_path = self.fixture.root / "plans" / f"plan-v{plan['plan_version'] - 1}.json"
        plan_path = self.fixture.root / "plans" / f"plan-v{plan['plan_version']}.json"
        plan_path.write_bytes(json_bytes(plan))
        plan_hash = hashlib.sha256(plan_path.read_bytes()).hexdigest()
        causal_evidence = self.fixture.evidence(seq, record_id=evidence_ref)
        causal_evidence["payload"]["check_ref"] = None
        causal_evidence["payload"].pop("check_binding", None)
        decision = record(
            seq + 1,
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
        causal_evidence["plan_version"] = plan["plan_version"] - 1
        decision["plan_version"] = plan["plan_version"] - 1
        self.fixture.records.extend([causal_evidence, decision])
        activation = record(
            seq + 2,
            "plan_activated",
            {
                "plan_ref": f"plans/plan-v{plan['plan_version']}.json",
                "plan_sha256": plan_hash,
                "previous_version": plan["plan_version"] - 1,
                "reason": "The optional risk ended; durable recovery remains.",
                "evidence_refs": [evidence_ref],
                "decision_ref": decision_ref,
            },
        )
        activation["plan_version"] = plan["plan_version"]
        self.fixture.records.append(activation)

    def test_malformed_optional_artifacts_report_schema_errors_without_raising(self):
        cases = (
            ("claim-scope", "concurrency", lambda: self.write_claim(
                "N1.json", claim(node_id="N1", token="token", scope_paths=[1])
            ), "SCHEMA-CLAIM"),
            ("claim-time", "concurrency", lambda: self.write_claim(
                "N1.json", claim(node_id="N1", token="token", scope_paths=["src"]) | {"acquired_at": 1}
            ), "SCHEMA-CLAIM"),
            ("claim-token", "concurrency", lambda: self.write_claim(
                "N1.json", claim(node_id="N1", token="token", scope_paths=["src"]) | {"token": []}
            ), "SCHEMA-CLAIM"),
            ("artifact-items", "artifacts", lambda: self.write_artifact_index([1]), "SCHEMA-ARTIFACT"),
            ("artifact-list", "artifacts", lambda: self.write_artifact_index(1), "SCHEMA-ARTIFACT"),
        )
        for label, module, writer, needle in cases:
            with self.subTest(label=label):
                self.reset_fixture(modules=[module])
                writer()
                self.fixture.save(render=False)
                errors = validate_loop_dir(self.fixture.root)
                self.assertTrue(any(needle in item for item in errors), errors)

    def test_lightweight_modules_are_rejected(self):
        self.fixture.plan["control"]["mode"] = "lightweight"
        self.fixture.plan["control"]["modules"] = ["effects"]
        self.fixture.rewrite_plan()
        self.assertTrue(any("SCHEMA-PLAN" in item for item in validate_loop_dir(self.fixture.root)))

    def test_persistent_modules_are_rejected(self):
        self.fixture.plan["control"]["mode"] = "persistent"
        self.fixture.plan["control"]["modules"] = ["effects"]
        self.fixture.rewrite_plan()
        errors = validate_loop_dir(self.fixture.root)
        self.assertTrue(any("SCHEMA-PLAN" in item or "JOURNAL-MODE" in item for item in errors), errors)

    def test_lightweight_rejects_conditional_files(self):
        self.fixture.plan["control"]["mode"] = "lightweight"
        self.fixture.plan["control"]["modules"] = []
        self.fixture.rewrite_plan()
        self.write_claim("N1.json", claim(node_id="N1", token="token", scope_paths=["src"]))
        self.write_artifact_index([self.artifact("A1", "x", 1, "active", None)])
        errors = validate_loop_dir(self.fixture.root)
        self.assertTrue(any("CLAIM-MODULE" in item for item in errors), errors)
        self.assertTrue(any("ARTIFACT-MODULE" in item for item in errors), errors)

    def test_v2_rejects_mixed_v1_core_artifacts(self):
        self.fixture.save(render=False)
        (self.fixture.root / "loop.plan.yaml").write_text("schema_version: '1.0'\n", encoding="utf-8")
        errors = validate_loop_dir(self.fixture.root)
        self.assertTrue(any("GRAPH-PROTOCOL" in item for item in errors), errors)

    def test_expired_claim_does_not_reserve_token_node_or_scope(self):
        self.reset_fixture(modules=["concurrency"])
        expired = claim(node_id="N1", token="reused", scope_paths=["src"])
        expired.update({
            "acquired_at": "2000-01-01T00:00:00Z",
            "heartbeat_at": "2000-01-01T00:01:00Z",
            "expires_at": "2000-01-01T00:02:00Z",
        })
        self.write_claim("expired.json", expired)
        self.write_claim("N1.json", claim(node_id="N1", token="reused", scope_paths=["src/a"]))
        self.fixture.save(render=False)
        errors = validate_loop_dir(self.fixture.root)
        self.assertTrue(any("CLAIM-EXPIRED" in item for item in errors), errors)
        self.assertFalse(any("CLAIM-TOKEN" in item for item in errors), errors)
        self.assertFalse(any("CLAIM-NODE" in item for item in errors), errors)
        self.assertFalse(any("CLAIM-OVERLAP" in item for item in errors), errors)

    def test_active_duplicate_claim_token_is_rejected(self):
        self.reset_fixture(modules=["concurrency"])
        second = copy.deepcopy(self.fixture.plan["nodes"][0])
        second["id"] = "N2"
        second["checks"][0]["id"] = "check-N2"
        self.fixture.plan["nodes"].append(second)
        self.fixture.rewrite_plan()
        self.write_claim("N1.json", claim(node_id="N1", token="same", scope_paths=["src/a"]))
        self.write_claim("N2.json", claim(node_id="N2", token="same", scope_paths=["src/b"]))
        self.fixture.save(render=False)
        self.assertTrue(any("CLAIM-TOKEN" in item for item in validate_loop_dir(self.fixture.root)))

    def test_claim_paths_reject_windows_aliases_and_preserve_unicode_distinctions(self):
        self.reset_fixture(modules=["concurrency"])
        for path in ("src/a.", "src/a "):
            with self.subTest(path=path):
                self.write_claim("N1.json", claim(node_id="N1", token="token", scope_paths=[path]))
                self.fixture.save(render=False)
                self.assertTrue(any("CLAIM-PATH" in item for item in validate_loop_dir(self.fixture.root)))
                (self.fixture.root / "claims" / "N1.json").unlink()

        second = copy.deepcopy(self.fixture.plan["nodes"][0])
        second["id"] = "N2"
        second["checks"][0]["id"] = "check-N2"
        self.fixture.plan["nodes"].append(second)
        self.fixture.rewrite_plan()
        self.write_claim("N1.json", claim(node_id="N1", token="one", scope_paths=["src/straße"]))
        self.write_claim("N2.json", claim(node_id="N2", token="two", scope_paths=["src/strasse"], owner_id="agent-b"))
        self.fixture.save()
        self.assertEqual(validate_loop_dir(self.fixture.root), [])

    def test_child_contract_refs_paths_and_outputs_are_checked_before_materialization(self):
        cases = (
            ({"loop_id": "L900.01", "return_deliverables": ["../escape"], "return_criteria_refs": ["SC1"]}, "CHILD-PATH"),
            ({"loop_id": "L900.01", "return_deliverables": ["CON.txt"], "return_criteria_refs": ["SC1"]}, "CHILD-PATH"),
            ({"loop_id": "L900.01", "return_deliverables": ["result.txt"], "return_criteria_refs": ["missing"]}, "CHILD-CRITERION"),
            ({"loop_id": "L900.01", "return_deliverables": ["result.txt"], "return_criteria_refs": ["SC1"]}, "CHILD-OUTPUT"),
        )
        for child, needle in cases:
            with self.subTest(needle=needle):
                self.reset_fixture(modules=["children"])
                self.fixture.plan["nodes"][0]["child_loop"] = child
                self.fixture.rewrite_plan()
                self.fixture.save(render=False)
                self.assertTrue(any(needle in item for item in validate_loop_dir(self.fixture.root)))

    def test_child_contract_duplicate_arrays_are_schema_errors(self):
        self.fixture.plan["control"]["mode"] = "governed"
        self.fixture.plan["control"]["modules"] = ["children"]
        self.fixture.plan["nodes"][0]["outputs"] = [{"path": "result.txt", "purpose": "return"}]
        self.fixture.plan["nodes"][0]["child_loop"] = {
            "loop_id": "L900.01",
            "return_deliverables": ["result.txt", "result.txt"],
            "return_criteria_refs": ["SC1", "SC1"],
        }
        self.fixture.rewrite_plan()
        self.fixture.save(render=False)
        self.assertTrue(any("SCHEMA-PLAN" in item for item in validate_loop_dir(self.fixture.root)))

    def test_parent_rejects_child_that_fails_its_whole_loop_gate(self):
        self.fixture.plan["control"]["mode"] = "governed"
        self.fixture.plan["control"]["modules"] = ["children"]
        self.fixture.plan["nodes"][0]["outputs"] = [{"path": "result.txt", "purpose": "return"}]
        self.fixture.plan["nodes"][0]["child_loop"] = {
            "loop_id": "L900.01", "return_deliverables": ["result.txt"], "return_criteria_refs": ["SC1"]
        }
        self.fixture.rewrite_plan()
        child_dir = self.make_child_without_render("L900.01-child")
        child_plan_path = child_dir / "plans" / "plan-v1.json"
        child_plan = load_json(child_plan_path)
        child_plan["control"]["mode"] = "governed"
        child_plan["control"]["modules"] = ["artifacts"]
        child_plan_path.write_bytes(json_bytes(child_plan))
        child_records = [json.loads(line) for line in (child_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()]
        child_records[0]["payload"]["plan_sha256"] = hashlib.sha256(child_plan_path.read_bytes()).hexdigest()
        with (child_dir / "journal.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for item in child_records:
                handle.write(json.dumps(item, separators=(",", ":")) + "\n")
        write_atomic(child_dir / "resume.json", project(child_dir, generated_at="2026-07-31T01:00:00Z"))
        self.fixture.save()
        errors = validate_loop_dir(self.fixture.root)
        self.assertTrue(any("CHILD-RETURN" in item and "ARTIFACT-MODULE" in item for item in errors), errors)

    def make_child_without_render(self, directory_name: str) -> Path:
        root = self.fixture.root / "_loops" / directory_name
        (root / "plans").mkdir(parents=True)
        goal = copy.deepcopy(self.fixture.goal)
        goal["loop_id"] = "L900.01"
        goal["origin"] = {"parent_loop_id": "L900", "parent_node_id": "N1"}
        (root / "goal.json").write_bytes(json_bytes(goal))
        plan = copy.deepcopy(self.fixture.plan)
        plan["plan_id"] = "plan-L900.01-v1"
        plan["goal_sha256"] = hashlib.sha256((root / "goal.json").read_bytes()).hexdigest()
        plan["control"]["modules"] = []
        plan["nodes"][0].pop("child_loop", None)
        plan["nodes"][0]["outputs"] = [{"path": "result.txt", "purpose": "Child return"}]
        (root / "result.txt").write_text("child result\n", encoding="utf-8")
        (root / "plans" / "plan-v1.json").write_bytes(json_bytes(plan))
        plan_hash = hashlib.sha256((root / "plans" / "plan-v1.json").read_bytes()).hexdigest()
        records = [
            record(1, "plan_activated", {"plan_ref": "plans/plan-v1.json", "plan_sha256": plan_hash, "previous_version": None, "reason": "Initial", "evidence_refs": [], "decision_ref": None}),
            record(2, "evidence", {"subject_refs": ["criterion:SC1"], "check_ref": None, "source_class": "direct_test", "origin_ref": "tool:test", "artifact_ref": None, "observed_result": "pass", "summary": "Child result verified.", "limits": "Child scope only.", "valid_until": None, "recheck_when": "Child output changes.", "review_context": None}, record_id="child-evidence"),
            record(3, "completion", {"deliverables": [{"path": "result.txt"}], "criterion_evidence": {"SC1": ["child-evidence"]}, "deterministic_check_refs": [], "system_review_ref": None, "counterexample_review_refs": [], "residual_risks": [], "unmet_scope": [], "authorization_decision_refs": []}, record_id="child-completion"),
        ]
        with (root / "journal.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for item in records:
                handle.write(json.dumps(item, separators=(",", ":")) + "\n")
        return root

    def test_artifact_index_requires_one_complete_active_chain(self):
        cases = (
            ([], "SCHEMA-ARTIFACT"),
            ([self.artifact("A1", "x", 1, "retired", None)], "ARTIFACT-ACTIVE"),
            ([self.artifact("A2", "x", 2, "active", None)], "ARTIFACT-CHAIN"),
            ([
                self.artifact("A1", "x", 1, "superseded", None),
                self.artifact("A1b", "x", 1, "active", None),
            ], "ARTIFACT-VERSION"),
            ([
                self.artifact("A1", "x", 1, "superseded", None),
                self.artifact("A3", "x", 3, "active", "A1"),
            ], "ARTIFACT-VERSION"),
            ([
                self.artifact("A1", "x", 1, "active", None),
                self.artifact("A2", "x", 2, "superseded", "A1"),
            ], "ARTIFACT-ACTIVE"),
            ([
                self.artifact("A1", "x", 1, "superseded", "A2"),
                self.artifact("A2", "x", 2, "active", "A1"),
            ], "ARTIFACT-CYCLE"),
        )
        for artifacts, needle in cases:
            with self.subTest(needle=needle):
                self.reset_fixture(modules=["artifacts"])
                (self.fixture.root / "x.txt").write_text("x", encoding="utf-8")
                self.write_artifact_index(artifacts)
                self.fixture.save(render=False)
                self.assertTrue(any(needle in item for item in validate_loop_dir(self.fixture.root)))

    def artifact(self, artifact_id: str, logical_name: str, version: int, status: str, predecessor: str | None) -> dict:
        relative = "x.txt" if version == 1 else f"x-v{version}.txt"
        path = self.fixture.root / relative
        if not path.exists():
            path.write_text("x", encoding="utf-8")
        return {
            "artifact_id": artifact_id,
            "logical_name": logical_name,
            "path": relative,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "version": version,
            "status": status,
            "supersedes_id": predecessor,
        }

    def test_artifact_chain_control_and_unknown_evidence_reference(self):
        self.reset_fixture(modules=["artifacts"])
        artifacts = [
            self.artifact("A1", "x", 1, "superseded", None),
            self.artifact("A2", "x", 2, "active", "A1"),
        ]
        self.write_artifact_index(artifacts)
        evidence = self.fixture.evidence(2)
        self.bind_artifact(evidence, artifacts[1])
        self.fixture.records.append(evidence)
        self.fixture.save()
        errors = validate_loop_dir(self.fixture.root)
        self.assertEqual(errors, [])

        self.fixture.records[-1]["payload"]["artifact_ref"] = "missing"
        self.fixture.save()
        self.assertTrue(any("ARTIFACT-EVIDENCE" in item for item in validate_loop_dir(self.fixture.root)))

    def test_artifact_paths_reject_cross_logical_identity_collisions(self):
        self.reset_fixture(modules=["artifacts"])
        artifact_x = self.artifact("A1", "x", 1, "active", None)
        artifact_y = self.artifact("B1", "y", 1, "active", None)
        artifact_y["path"] = "x.txt"
        self.write_artifact_index([artifact_x, artifact_y])
        self.fixture.save(render=False)
        errors = validate_loop_dir(self.fixture.root)
        self.assertTrue(any("ARTIFACT-PATH" in item and "collides" in item for item in errors), errors)

    def test_artifact_paths_require_canonical_names_and_preserve_unicode_distinctions(self):
        self.reset_fixture(modules=["artifacts"])
        for path in ("x.txt.", "x.txt ", "CON.txt"):
            with self.subTest(path=path):
                invalid = self.artifact("A1", "x", 1, "active", None)
                invalid["path"] = path
                self.write_artifact_index([invalid])
                self.fixture.save(render=False)
                self.assertTrue(any("ARTIFACT-PATH" in item for item in validate_loop_dir(self.fixture.root)))

        self.reset_fixture(modules=["artifacts"])
        first_path = self.fixture.root / "straße.txt"
        second_path = self.fixture.root / "strasse.txt"
        first_path.write_text("first", encoding="utf-8")
        second_path.write_text("second", encoding="utf-8")
        first = self.artifact("A1", "first", 1, "active", None)
        first.update({"path": "straße.txt", "sha256": hashlib.sha256(first_path.read_bytes()).hexdigest()})
        second = self.artifact("B1", "second", 1, "active", None)
        second.update({"path": "strasse.txt", "sha256": hashlib.sha256(second_path.read_bytes()).hexdigest()})
        self.write_artifact_index([first, second])
        self.fixture.save()
        self.assertEqual(validate_loop_dir(self.fixture.root), [])

    def test_superseded_artifact_remains_valid_for_historical_evidence(self):
        self.reset_fixture(modules=["artifacts"])
        artifact_v1 = self.artifact("A1", "x", 1, "active", None)
        self.write_artifact_index([artifact_v1])
        evidence = self.fixture.evidence(2, record_id="artifact-v1-pass")
        self.bind_artifact(evidence, artifact_v1)
        self.fixture.records.append(evidence)
        self.fixture.save()
        self.assertEqual(validate_loop_dir(self.fixture.root), [])

        artifact_v1["status"] = "superseded"
        artifact_v2 = self.artifact("A2", "x", 2, "active", "A1")
        self.write_artifact_index([artifact_v1, artifact_v2])
        self.fixture.save()
        self.assertEqual(validate_loop_dir(self.fixture.root), [])

        artifact_v1["sha256"] = "0" * 64
        self.write_artifact_index([artifact_v1, artifact_v2])
        self.fixture.save(render=False)
        self.assertTrue(any("ARTIFACT-HASH A1" in item for item in validate_loop_dir(self.fixture.root)))

    def test_completion_keeps_historical_superseded_artifact_evidence(self):
        self.reset_fixture(modules=["artifacts"])
        artifact_v1 = self.artifact("A1", "x", 1, "active", None)
        self.write_artifact_index([artifact_v1])
        evidence = self.fixture.evidence(2, record_id="artifact-v1-pass")
        self.bind_artifact(evidence, artifact_v1)
        self.fixture.records += [
            evidence,
            record(
                3,
                "completion",
                {
                    "deliverables": [],
                    "criterion_evidence": {"SC1": ["artifact-v1-pass"]},
                    "deterministic_check_refs": [],
                    "system_review_ref": None,
                    "counterexample_review_refs": [],
                    "residual_risks": [],
                    "unmet_scope": [],
                    "authorization_decision_refs": [],
                },
                record_id="completion-v1",
            ),
        ]
        self.fixture.save()
        self.assertEqual(validate_loop_dir(self.fixture.root), [])

        artifact_v1["status"] = "superseded"
        artifact_v2 = self.artifact("A2", "x", 2, "active", "A1")
        self.write_artifact_index([artifact_v1, artifact_v2])
        self.fixture.save()
        self.assertEqual(validate_loop_dir(self.fixture.root), [])
        self.assertEqual(project(self.fixture.root)["projection"]["loop_status"], "completed")

    def test_reopen_keeps_historical_superseded_artifact_evidence(self):
        self.reset_fixture(modules=["artifacts"])
        artifact_v1 = self.artifact("A1", "x", 1, "active", None)
        self.write_artifact_index([artifact_v1])
        support = self.fixture.evidence(2, record_id="artifact-v1-pass")
        self.bind_artifact(support, artifact_v1)
        counterevidence = self.fixture.evidence(4, result="fail", record_id="artifact-v1-fail")
        self.bind_artifact(counterevidence, artifact_v1)
        self.fixture.records += [
            support,
            record(
                3,
                "completion",
                {
                    "deliverables": [],
                    "criterion_evidence": {"SC1": ["artifact-v1-pass"]},
                    "deterministic_check_refs": [],
                    "system_review_ref": None,
                    "counterexample_review_refs": [],
                    "residual_risks": [],
                    "unmet_scope": [],
                    "authorization_decision_refs": [],
                },
                record_id="completion-v1",
            ),
            counterevidence,
            record(
                5,
                "evidence_relation",
                {
                    "source_evidence_ref": "artifact-v1-fail",
                    "target_evidence_ref": "artifact-v1-pass",
                    "relation": "invalidates",
                    "reason": "The original artifact failed revalidation.",
                },
                record_id="artifact-v1-invalidated",
            ),
            record(
                6,
                "reopen",
                {
                    "completion_ref": "completion-v1",
                    "counterevidence_refs": ["artifact-v1-fail"],
                    "affected_criterion_refs": ["SC1"],
                    "affected_node_ids": ["N1"],
                    "action": "Repair against the current artifact version.",
                    "reason": "Historical artifact evidence was invalidated.",
                },
                record_id="reopen-v1",
            ),
        ]
        self.fixture.save()
        self.assertEqual(validate_loop_dir(self.fixture.root), [])

        artifact_v1["status"] = "superseded"
        artifact_v2 = self.artifact("A2", "x", 2, "active", "A1")
        self.write_artifact_index([artifact_v1, artifact_v2])
        self.fixture.save()
        self.assertEqual(validate_loop_dir(self.fixture.root), [])
        self.assertEqual(project(self.fixture.root)["projection"]["loop_status"], "active")

    def test_evidence_artifact_ref_requires_artifacts_module(self):
        evidence = self.fixture.evidence(2)
        evidence["payload"]["artifact_ref"] = "A1"
        self.fixture.records.append(evidence)
        self.fixture.save(render=False)
        self.assertTrue(any("ARTIFACT-MODULE" in item for item in validate_loop_dir(self.fixture.root)))

    def test_historical_review_uses_the_plan_active_when_recorded(self):
        self.reset_fixture(modules=["independent_review"])
        manifest = self.fixture.root / "review.json"
        manifest.write_text("{}\n", encoding="utf-8")
        evidence = self.fixture.evidence(2, record_id="review-pass")
        evidence["payload"]["review_context"] = {
            "manifest_ref": "loop:review.json",
            "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "producer_conclusion_access": "withheld",
        }
        self.fixture.records.append(evidence)

        plan = copy.deepcopy(self.fixture.plan)
        plan.update({"plan_id": "plan-L900-v2", "plan_version": 2})
        plan["control"] = {
            "mode": "persistent",
            "modules": [],
            "admission_reason": "Durable recovery remains after review risk ended.",
        }
        self.activate_plan(plan, seq=3)
        self.fixture.save()
        self.assertEqual(validate_loop_dir(self.fixture.root), [])

    def test_review_rejects_when_its_active_plan_never_enabled_the_module(self):
        manifest = self.fixture.root / "review.json"
        manifest.write_text("{}\n", encoding="utf-8")
        evidence = self.fixture.evidence(2, record_id="review-pass")
        evidence["payload"]["review_context"] = {
            "manifest_ref": "loop:review.json",
            "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "producer_conclusion_access": "withheld",
        }
        self.fixture.records.append(evidence)
        self.fixture.save(render=False)
        self.assertTrue(any("EVIDENCE-REVIEW" in item for item in validate_loop_dir(self.fixture.root)))

    def test_historical_artifact_evidence_retains_an_independent_binding(self):
        self.reset_fixture(modules=["artifacts"])
        artifact = self.artifact("A1", "x", 1, "active", None)
        self.write_artifact_index([artifact])
        evidence = self.fixture.evidence(2, record_id="artifact-pass")
        self.bind_artifact(evidence, artifact)
        self.fixture.records.append(evidence)

        plan = copy.deepcopy(self.fixture.plan)
        plan.update({"plan_id": "plan-L900-v2", "plan_version": 2})
        plan["control"] = {
            "mode": "persistent",
            "modules": [],
            "admission_reason": "Durable recovery remains after artifact selection ended.",
        }
        self.activate_plan(plan, seq=3)
        self.fixture.save()
        errors = validate_loop_dir(self.fixture.root)
        self.assertTrue(any("ARTIFACT-MODULE artifact-index.json" in item for item in errors), errors)

        (self.fixture.root / "artifact-index.json").unlink()
        self.fixture.save()
        self.assertEqual(validate_loop_dir(self.fixture.root), [])

        (self.fixture.root / "x.txt").write_text("mutated", encoding="utf-8")
        errors = validate_loop_dir(self.fixture.root)
        self.assertTrue(any("ARTIFACT-EVIDENCE" in item for item in errors), errors)
        with self.assertRaisesRegex(Exception, "ARTIFACT-EVIDENCE"):
            project(self.fixture.root)
        rendered = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "render_resume.py"),
                str(self.fixture.root),
                "--check",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(rendered.returncode, 0)
        self.assertIn("ARTIFACT-EVIDENCE", rendered.stdout + rendered.stderr)

    def test_graph_rejects_noncanonical_and_duplicate_output_identity(self):
        self.fixture.plan["nodes"][0]["outputs"] = [
            {"path": "artifacts/./result.txt", "purpose": "noncanonical"}
        ]
        self.fixture.rewrite_plan()
        errors = validate_loop_dir(self.fixture.root)
        self.assertTrue(any("GRAPH-PATH" in error and "canonical form" in error for error in errors), errors)

        self.reset_fixture()
        self.fixture.plan["nodes"][0]["outputs"] = [
            {"path": "artifacts/result.txt", "purpose": "first"}
        ]
        second = copy.deepcopy(self.fixture.plan["nodes"][0])
        second.update({"id": "N2", "objective": "Duplicate output."})
        second["checks"][0]["id"] = "check-N2"
        self.fixture.plan["nodes"].append(second)
        self.fixture.rewrite_plan()
        errors = validate_loop_dir(self.fixture.root)
        self.assertTrue(any("GRAPH-UNIQUE duplicate output path" in error for error in errors), errors)

    def test_graph_rejects_unmaterializable_windows_output_paths(self):
        for index, path in enumerate(
            ("artifacts/result?.txt", "artifacts/result|copy.txt", "artifacts/control\x01.txt")
        ):
            with self.subTest(path=path):
                self.reset_fixture()
                self.fixture.plan["nodes"][0]["outputs"] = [
                    {"path": path, "purpose": "must be materializable on every host"}
                ]
                self.fixture.rewrite_plan()
                errors = validate_loop_dir(self.fixture.root)
                self.assertTrue(any("GRAPH-PATH" in error for error in errors), errors)

    @unittest.skipUnless(sys.platform == "win32", "Windows path identity only")
    def test_graph_preserves_windows_unicode_distinct_output_identities(self):
        for first_path, second_path in (
            ("artifacts/straße.txt", "artifacts/strasse.txt"),
            (f"artifacts/{chr(0x1F600)}.txt", f"artifacts/{chr(0x1F600)}.txu"),
        ):
            with self.subTest(first=first_path, second=second_path):
                self.reset_fixture()
                self.fixture.plan["nodes"][0]["outputs"] = [
                    {"path": first_path, "purpose": "first Unicode output"}
                ]
                second = copy.deepcopy(self.fixture.plan["nodes"][0])
                second.update({"id": "N2", "objective": "Produce a distinct Unicode output."})
                second["checks"][0]["id"] = "check-N2"
                second["outputs"] = [
                    {"path": second_path, "purpose": "second Unicode output"}
                ]
                self.fixture.plan["nodes"].append(second)
                self.fixture.rewrite_plan()
                self.fixture.save()
                self.assertEqual(validate_loop_dir(self.fixture.root), [])


if __name__ == "__main__":
    unittest.main()
