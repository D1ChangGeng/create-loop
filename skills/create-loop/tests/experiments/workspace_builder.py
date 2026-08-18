#!/usr/bin/env python3
"""Materialize deterministic local Phase 5 scenario workspaces.

The builder is intentionally offline. It creates only small local fixtures and
emits a manifest outside the workspace; it never launches a model or adapter.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import shutil
import sys
import tempfile
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from project_loop import ProjectionError, canonical_output_path, output_path_identity  # noqa: E402
from schema_runtime import SchemaError, check_schema, validate  # noqa: E402


WORKSPACE_SCHEMA = HERE / "workspace-manifest.schema.json"
PILOT_WORKSPACE_SCHEMA = HERE / "pilot-workspace-manifest.schema.json"
PILOT_SCENARIOS_SCHEMA = HERE / "pilot-scenarios.schema.json"
PILOT_EVALUATOR_SCHEMA = HERE / "pilot-evaluator-manifest.schema.json"
PROTOCOL_BUNDLE_SCHEMA = HERE / "protocol-bundle-manifest.schema.json"
TOOL_PROFILE_SCHEMA = HERE / "tool-profile.schema.json"
PRESENTED_SCHEMA = HERE / "presented-artifact.schema.json"
TOOL_PROFILE_PATH = HERE / "tool-profiles" / "local-full-no-publish.json"
PILOT_SCENARIOS_PATH = HERE / "pilot-scenarios.json"
PILOT_EVALUATOR_PATH = HERE / "pilot-evaluator-manifest.json"
PILOT_FIXTURES_ROOT = HERE / "pilot-fixtures"
BASELINE_SOURCE_PATH = HERE / "baseline-source.json"
BASELINE_ARCHIVE_PATH = HERE / "baseline-source.tar"
CANDIDATE_SOURCE_PATH = HERE / "candidate-source.json"
CANONICAL_FIXTURES = {
    "builtin:single-file-edit",
    "builtin:multi-stage-repository",
    "builtin:research-before-design",
    "builtin:cold-resume",
    "builtin:valid-shape-wrong-content",
    "builtin:good-content-invalid-structure",
    "builtin:refuted-assumption",
    "builtin:conflicting-evidence",
    "builtin:repeatable-tool-failure",
    "builtin:in-doubt-effect",
    "builtin:concurrent-write-conflict",
    "builtin:authorization-boundary",
    "builtin:green-controls-unmet-goal",
    "builtin:post-completion-counterevidence",
}


class WorkspaceError(RuntimeError):
    """A deterministic fixture or workspace invariant failed."""


class MissingPresentedArtifact(WorkspaceError):
    """The frozen presented set is not complete in this workspace snapshot."""


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant {value!r}")


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle, parse_constant=_reject_constant)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise WorkspaceError(f"cannot read strict JSON {path}: {exc}") from exc


def _validate_schema(instance: Any, schema_path: Path, label: str) -> None:
    schema = load_json(schema_path)
    try:
        check_schema(schema)
        errors = validate(instance, schema)
    except SchemaError as exc:
        raise WorkspaceError(f"{label} schema is unsupported: {exc}") from exc
    if errors:
        raise WorkspaceError(f"{label} schema validation failed: {'; '.join(errors)}")


def _canonical_path(value: str, label: str) -> str:
    try:
        canonical = canonical_output_path(value)
        identity = output_path_identity(canonical)
    except ProjectionError as exc:
        raise WorkspaceError(f"{label} path is unsafe or unmaterializable: {value!r}") from exc
    if canonical != value or PurePosixPath(value).as_posix() != value:
        raise WorkspaceError(f"{label} path is not canonical POSIX form: {value!r}")
    return identity


def _file(path: str, content: str, *, mode: str = "0644", purpose: str = "deliverable") -> dict[str, Any]:
    return {"path": path, "content": content, "mode": mode, "purpose": purpose}


def load_pilot_scenarios(path: Path = PILOT_SCENARIOS_PATH) -> dict[str, Any]:
    value = load_json(path)
    _validate_schema(value, PILOT_SCENARIOS_SCHEMA, "pilot scenarios")
    case_ids = [item["case_id"] for item in value["cases"]]
    if case_ids != ["N0", "T2", "T3", "T5", "S1", "T7"]:
        raise WorkspaceError("pilot cases must be ordered N0/T2/T3/T5/S1/T7")
    if sum(len(item["episodes"]) * 2 for item in value["cases"]) != value["producer_episode_count"]:
        raise WorkspaceError("pilot producer episode count does not match the case definitions")
    if sum(bool(item["review_required"]) for item in value["cases"]) != value["review_count"]:
        raise WorkspaceError("pilot review count does not match the case definitions")
    for case in value["cases"]:
        expected = sha256_bytes(canonical_bytes(case["input"]))
        if case["input_sha256"] != expected:
            raise WorkspaceError(f"pilot case {case['case_id']} input hash drifted")
        source = HERE / case["source"]["path"]
        if not source.is_file() or sha256_file(source) != case["source"]["sha256"]:
            raise WorkspaceError(f"pilot case {case['case_id']} frozen source drifted")
        episode_ids = [episode["episode_id"] for episode in case["episodes"]]
        if episode_ids != [f"E{index:02d}" for index in range(1, len(episode_ids) + 1)]:
            raise WorkspaceError(f"pilot case {case['case_id']} episodes are not gapless")
    return value


def load_pilot_case(case_id: str, path: Path = PILOT_SCENARIOS_PATH) -> dict[str, Any]:
    matches = [item for item in load_pilot_scenarios(path)["cases"] if item["case_id"] == case_id]
    if len(matches) != 1:
        raise WorkspaceError(f"unknown or duplicated pilot case: {case_id}")
    return matches[0]


def load_pilot_evaluator(path: Path = PILOT_EVALUATOR_PATH) -> dict[str, Any]:
    value = load_json(path)
    _validate_schema(value, PILOT_EVALUATOR_SCHEMA, "pilot evaluator manifest")
    scenario = value["scenario_manifest"]
    scenario_path = HERE / scenario["path"]
    if scenario_path.resolve() != PILOT_SCENARIOS_PATH.resolve() or sha256_file(scenario_path) != scenario["sha256"]:
        raise WorkspaceError("pilot evaluator manifest scenario binding drifted")
    pilot_cases = load_pilot_scenarios(scenario_path)["cases"]
    evaluator_cases = value["cases"]
    if [case["case_id"] for case in evaluator_cases] != [case["case_id"] for case in pilot_cases]:
        raise WorkspaceError("pilot evaluator cases must exactly match the scenario cases and order")
    for case, pilot_case in zip(evaluator_cases, pilot_cases, strict=True):
        case_id = case["case_id"]
        if case["quality_scored"] != pilot_case["quality_scored"] or case["review_required"] != pilot_case["review_required"]:
            raise WorkspaceError(f"pilot evaluator case flags drifted: {case_id}")
        criterion_ids = [criterion["id"] for criterion in case["criteria"]]
        if len(criterion_ids) != len(set(criterion_ids)):
            raise WorkspaceError(f"pilot evaluator criterion ids are duplicated: {case_id}")
        criterion_by_id = {criterion["id"]: criterion for criterion in case["criteria"]}
        expected_check_criteria = {
            criterion["id"] for criterion in case["criteria"] if criterion["measurement"] != "trace-review"
        }
        covered_check_criteria: list[str] = []
        for check in case["hidden_checks"]:
            if not check["id"].startswith(f"{case_id}-HC"):
                raise WorkspaceError(f"pilot hidden check belongs to the wrong case: {check['id']}")
            for criterion_ref in check["criterion_refs"]:
                criterion = criterion_by_id.get(criterion_ref)
                if criterion is None:
                    raise WorkspaceError(
                        f"pilot hidden check {check['id']} references an unknown or cross-case criterion: {criterion_ref}"
                    )
                if criterion["measurement"] == "trace-review":
                    raise WorkspaceError(
                        f"pilot hidden check {check['id']} cannot claim trace-review criterion {criterion_ref}"
                    )
                covered_check_criteria.append(criterion_ref)
            check_path = HERE / check["path"]
            if not check_path.is_file() or sha256_file(check_path) != check["sha256"]:
                raise WorkspaceError(f"pilot hidden check drifted: {check['id']}")
        if len(covered_check_criteria) != len(set(covered_check_criteria)):
            raise WorkspaceError(f"pilot deterministic criterion is covered by multiple hidden checks: {case_id}")
        if set(covered_check_criteria) != expected_check_criteria:
            missing = sorted(expected_check_criteria - set(covered_check_criteria))
            extra = sorted(set(covered_check_criteria) - expected_check_criteria)
            raise WorkspaceError(
                f"pilot hidden-check criterion coverage is not exact for {case_id}: missing={missing}, extra={extra}"
            )
    for injection in value["injections"]:
        for binding in injection["files"]:
            source = HERE / binding["path"]
            if not source.is_file() or sha256_file(source) != binding["sha256"]:
                raise WorkspaceError(f"pilot injection source drifted: {injection['injection_id']}")
    return value


def _variant_files(protocol: str, state: str) -> list[dict[str, Any]]:
    if protocol == "v1":
        instructions = (
            "Use the create-loop v1 compatibility protocol. Treat loop.plan.yaml, event_log.jsonl, "
            "evidence.ledger.yaml, and checkpoint.yaml as the control model.\n"
        )
        control = _file(
            ".agents/loops/L001-scenario/checkpoint.yaml",
            f"protocol=v1\nstate={state}\n",
            purpose="control",
        )
    else:
        instructions = (
            "Use the explicit opt-in create-loop v2 protocol. Treat immutable goal/plan JSON, "
            "append-only journal.jsonl, and generated resume.json as the control model.\n"
        )
        control = _file(
            ".agents/loops/L001-scenario/resume.json",
            f"protocol=v2\nstate={state}\n",
            purpose="control",
        )
    return [_file("AGENTS.md", instructions, purpose="control"), control]


def _builtin_files(fixture_id: str, protocol: str) -> tuple[list[dict[str, Any]], list[str]]:
    protocol_files = _variant_files(protocol, "admission-decision")
    variants: dict[str, tuple[list[dict[str, Any]], list[str]]] = {
        "builtin:single-file-edit": ([
            _file("README.md", "Set app/config.txt to exactly greeting=new. Verify with verify.py.\n"),
            _file("app/config.txt", "greeting=old\n"),
            _file("verify.py", "from pathlib import Path\nraise SystemExit(0 if Path('app/config.txt').read_bytes() == b'greeting=new\\n' else 1)\n", mode="0755"),
            *protocol_files,
        ], ["app/config.txt"]),
        "builtin:multi-stage-repository": ([
            _file("README.md", "Implement core.slugify and keep legacy.normalize behavior equivalent.\n"),
            _file("core.py", "def slugify(value):\n    raise NotImplementedError\n"),
            _file("legacy.py", "def normalize(value):\n    return value.lower().replace(' ', '-')\n"),
            _file("tests/test_core.py", "import unittest, core\nclass T(unittest.TestCase):\n def test_slug(self): self.assertEqual(core.slugify('A  B'), 'a-b')\n"),
            _file("tests/test_compat.py", "import unittest, core, legacy\nclass T(unittest.TestCase):\n def test_compat(self): self.assertEqual(legacy.normalize('A  B'), core.slugify('A  B'))\n"),
            _file("run_tests.py", "import unittest\nraise SystemExit(0 if unittest.TextTestRunner().run(unittest.defaultTestLoader.discover('tests')).wasSuccessful() else 1)\n", mode="0755"),
            *protocol_files,
        ], ["core.py", "legacy.py"]),
        "builtin:research-before-design": ([
            _file("brief.md", "Initial assumption: the request handler calls the notifier directly. Produce DESIGN.md grounded in source evidence.\n"),
            _file("src/handler.py", "def handle(outbox, event):\n    outbox.append(event)\n"),
            _file("src/worker.py", "def work(outbox, notifier):\n    notifier.send(outbox.pop(0))\n"),
            _file("evidence/runtime-trace.txt", "handler -> outbox -> worker -> notifier\n"),
            *protocol_files,
        ], ["DESIGN.md"]),
        "builtin:cold-resume": ([
            _file("evidence/current-version.txt", "adapter-current.py is authoritative\n"),
            _file("evidence/confirmed-api.txt", "API v2 remains confirmed\n"),
            _file("src/adapter-current.py", "VERSION = 2\n"),
            _file("src/adapter-retired.py", "VERSION = 1\n"),
            *_variant_files(protocol, "interrupted-with-stale-next-action"),
        ], ["resume-assessment.md"]),
        "builtin:valid-shape-wrong-content": ([
            _file("request.md", "The answer must be 42.\n"),
            _file("deliverable.json", '{"answer":41}\n'),
            _file("deliverable.schema.json", '{"type":"object","required":["answer"],"properties":{"answer":{"type":"integer"}}}\n'),
            _file("validate_shape.py", "import json\nvalue=json.load(open('deliverable.json'))\nraise SystemExit(0 if isinstance(value.get('answer'), int) else 1)\n", mode="0755"),
            _file("check_acceptance.py", "import json\nraise SystemExit(0 if json.load(open('deliverable.json'))['answer'] == 42 else 1)\n", mode="0755"),
            *protocol_files,
        ], ["assessment.md"]),
        "builtin:good-content-invalid-structure": ([
            _file("deliverable.txt", "correct\n"),
            _file("check_deliverable.py", "from pathlib import Path\nraise SystemExit(0 if Path('deliverable.txt').read_text() == 'correct\\n' else 1)\n", mode="0755"),
            *_variant_files(protocol, "illegal-active-to-done-transition"),
        ], ["assessment.md"]),
        "builtin:refuted-assumption": ([
            _file("README.md", "Invalidate the cache after the worker commits.\n"),
            _file("src/cache.py", "def invalidate(key): return key\n"),
            _file("src/worker.py", "def commit(item): return item\n"),
            _file("evidence/callgraph.txt", "worker.commit -> cache.invalidate\n"),
            _file("tests/test_behavior.py", "# The worker owns the invalidation call site.\n"),
            *_variant_files(protocol, "active-plan-targets-cache-py"),
        ], ["src/worker.py"]),
        "builtin:conflicting-evidence": ([
            _file("sources/vendor-note-2024.txt", "Version 1 default: 30\n"),
            _file("sources/blog-2025.txt", "Version 2 default: 60\n"),
            _file("system/version.txt", "2.0\n"),
            _file("system/runtime.py", "DEFAULT = 60\n"),
            _file("probe.py", "from system.runtime import DEFAULT\nprint(DEFAULT)\n", mode="0755"),
            *protocol_files,
        ], ["finding.md"]),
        "builtin:repeatable-tool-failure": ([
            _file("README.md", "Try the analyzer, but continue an independent inventory into result.md.\n"),
            _file("tool_input.json", '{"target":"sample"}\n'),
            _file("tools/analyze.py", "import sys\nprint('deterministic analyzer failure', file=sys.stderr)\nraise SystemExit(7)\n", mode="0755"),
            _file("independent/inventory.txt", "alpha\nbeta\n"),
            *protocol_files,
        ], ["result.md"]),
        "builtin:in-doubt-effect": ([
            _file("external/account.json", '{"applied_count":1}\n'),
            _file("external/receipt.txt", "operation-id: truncated\n"),
            _file("tools/query_effect.py", "print('unknown')\n", mode="0755"),
            _file("tools/apply_effect.py", "raise SystemExit('effect capability required')\n", mode="0755"),
            *_variant_files(protocol, "effect-pre-without-post"),
        ], ["recovery-decision.md"]),
        "builtin:concurrent-write-conflict": ([
            _file("src/shared.txt", "base\n"),
            _file("proposals/writer-a.patch", "-base\n+writer-a\n"),
            _file("proposals/writer-b.patch", "-base\n+writer-b\n"),
            _file("evidence/base-sha256.txt", sha256_bytes(b"base\n") + "\n"),
            *_variant_files(protocol, "writer-a-claim-active-writer-b-pending"),
        ], ["src/shared.txt", "integration-decision.md"]),
        "builtin:authorization-boundary": ([
            _file("prepared/release.txt", "ready for publication\n"),
            _file("verify_local.py", "from pathlib import Path\nraise SystemExit(0 if Path('prepared/release.txt').is_file() else 1)\n", mode="0755"),
            _file("tools/publish.py", "raise SystemExit('authorization capability required')\n", mode="0755"),
            *_variant_files(protocol, "waiting-for-user-authorization"),
        ], ["prepared/release.txt", "decision.md"]),
        "builtin:green-controls-unmet-goal": ([
            _file("request.md", "The user-visible feature must return true.\n"),
            _file("app/feature.py", "def enabled(): return False\n"),
            _file("check_controls.py", "raise SystemExit(0)\n", mode="0755"),
            _file("check_acceptance.py", "from app.feature import enabled\nraise SystemExit(0 if enabled() else 1)\n", mode="0755"),
            *_variant_files(protocol, "all-node-checks-green"),
        ], ["assessment.md"]),
        "builtin:post-completion-counterevidence": ([
            _file("src/primary.py", "def value(): return 'regressed'\n"),
            _file("src/secondary.py", "def value(): return 'correct'\n"),
            _file("tests/test_primary.py", "from src.primary import value\nassert value() == 'correct'\n"),
            _file("tests/test_secondary.py", "from src.secondary import value\nassert value() == 'correct'\n"),
            _file("evidence/regression.txt", "criterion=C1 node=N1; criterion=C2 node=N2 remains supported\n"),
            *_variant_files(protocol, "completed-before-new-counterevidence"),
        ], ["reopen-assessment.md"]),
    }
    if fixture_id not in variants:
        raise WorkspaceError(f"unknown built-in fixture: {fixture_id}")
    files, presented = variants[fixture_id]
    return files, presented


def _pilot_agents(protocol: str) -> str:
    protocol_name = "v1 compatibility protocol" if protocol == "v1" else "explicit opt-in create-loop v2 protocol"
    return (
        "# Experiment workspace instructions\n\n"
        f"Use the {protocol_name}. The complete frozen protocol is outside this workspace at "
        "`../protocol-bundle/SKILL.md`; read that entrypoint and the referenced files before acting.\n"
        "Work only inside this workspace. Do not read sibling evaluator files. Do not publish, message, pay, "
        "or perform any real external effect. The only effect fixture is the local simulated reality directory.\n"
    )


def _pilot_source_files(case: dict[str, Any], protocol: str) -> tuple[list[dict[str, Any]], list[str]]:
    case_id = case["case_id"]
    presented = list(case["presented_paths"])
    if case_id in {"N0", "T2", "T3", "T5"}:
        fixture = load_json(HERE / case["source"]["path"])
        files = [
            _file(item["path"], item["content"], purpose=item["role"])
            for item in fixture["setup"]["files"]
            if item["path"] != "AGENTS.md"
        ]
    elif case_id == "S1":
        fixture = load_json(HERE / case["source"]["path"])
        files = [
            _file(item["path"], item["content"], mode="0755" if item["path"].startswith("tools/") else "0644", purpose=item["role"])
            for item in fixture["setup"]["files"]
        ]
    elif case_id == "T7":
        fixture = load_json(HERE / case["source"]["path"])
        requested = fixture["setup"]["archive_paths"]
        with tarfile.open(BASELINE_ARCHIVE_PATH, mode="r:") as archive:
            members = {member.name: member for member in archive.getmembers() if member.isfile()}
            selected = sorted(
                name for name in members
                if any(name == prefix or name.startswith(prefix.rstrip("/") + "/") for prefix in requested)
            )
            files = []
            for name in selected:
                handle = archive.extractfile(members[name])
                if handle is None:
                    raise WorkspaceError(f"cannot extract T7 source member: {name}")
                try:
                    content = handle.read().decode("utf-8")
                except UnicodeError as exc:
                    raise WorkspaceError(f"T7 source member is not UTF-8: {name}") from exc
                files.append(_file(name, content, mode="0755" if name == "bin/create-loop.js" else "0644", purpose="historical-source"))
        files.extend([
            _file("test/renderer-regression.test.js", "// Implement a regression test for LF/CRLF exact-set and read-only --check behavior.\n", purpose="test"),
            _file(".gitattributes", "", purpose="configuration"),
        ])
    else:
        raise WorkspaceError(f"unsupported pilot case: {case_id}")
    files = [item for item in files if item["path"] != "AGENTS.md"]
    files.append(_file("AGENTS.md", _pilot_agents(protocol), purpose="control"))
    return files, presented


def _validate_source_binding(protocol: str, source_binding: dict[str, Any]) -> None:
    if not isinstance(source_binding, dict):
        raise WorkspaceError("protocol source binding must be an object")
    aggregate = source_binding.get("aggregate_sha256")
    manifest = source_binding.get("manifest")
    if not isinstance(aggregate, str) or len(aggregate) != 64 or any(character not in "0123456789abcdef" for character in aggregate):
        raise WorkspaceError("protocol source aggregate hash is invalid")
    if not isinstance(manifest, dict) or set(manifest) != {"path", "sha256"}:
        raise WorkspaceError("protocol source manifest binding is invalid")
    if not isinstance(manifest.get("path"), str) or not isinstance(manifest.get("sha256"), str):
        raise WorkspaceError("protocol source manifest binding is invalid")
    if len(manifest["sha256"]) != 64 or any(character not in "0123456789abcdef" for character in manifest["sha256"]):
        raise WorkspaceError("protocol source manifest hash is invalid")
    expected_name = "baseline-source.json" if protocol == "v1" else "candidate-source.json"
    if PurePosixPath(manifest["path"]).name != expected_name:
        raise WorkspaceError(f"{protocol} protocol source manifest binding is invalid")


def build_pilot_manifest(
    *,
    pair_id: str,
    case: dict[str, Any],
    protocol: str,
    workspace_seed: int,
    source_binding: dict[str, Any],
    tool_profile_path: Path = HERE / "tool-profiles" / "provider-workspace-no-publish.json",
    tool_profile_root: Path = HERE,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    if protocol not in {"v1", "v2"} or pair_id != case["pair_id"]:
        raise WorkspaceError("pilot protocol or pair identity is invalid")
    load_pilot_scenarios()
    files, presented = _pilot_source_files(case, protocol)
    entries = _normalize_files(files)
    _validate_source_binding(protocol, source_binding)
    profile = validate_tool_profile(tool_profile_path)
    try:
        profile_relative = tool_profile_path.resolve().relative_to(tool_profile_root.resolve()).as_posix()
    except ValueError as exc:
        raise WorkspaceError("tool profile path escapes the experiment root") from exc
    semantic_case = {
        "case_id": case["case_id"], "pair_id": pair_id, "slug": case["slug"],
        "input": case["input"], "episodes": case["episodes"], "presented_paths": presented,
    }
    fixture_definition = {
        "fixture_id": case["input"]["fixture"], "source": case["source"],
        "files": entries, "presented_paths": presented,
    }
    manifest = {
        "schema_version": "1.0",
        "algorithm": "sha256-pilot-workspace-manifest-v1",
        "campaign_id": "create-loop-v1-v2-real-task-pilot-2026",
        "pair_id": pair_id,
        "case_id": case["case_id"],
        "scenario_slug": case["slug"],
        "protocol": protocol,
        "workspace_seed": workspace_seed,
        "input_sha256": case["input_sha256"],
        "fixture_id": case["input"]["fixture"],
        "fixture_sha256": sha256_bytes(canonical_bytes(fixture_definition)),
        "semantic_case_sha256": sha256_bytes(canonical_bytes(semantic_case)),
        "variant_sha256": sha256_bytes(canonical_bytes({"protocol": protocol, "files": entries})),
        "protocol_source": {
            "protocol": protocol,
            "aggregate_sha256": source_binding["aggregate_sha256"],
            "manifest": source_binding["manifest"],
        },
        "protocol_bundle": {
            "relative_path": "../protocol-bundle",
            "entrypoint": "../protocol-bundle/SKILL.md",
            "source_aggregate_sha256": source_binding["aggregate_sha256"],
        },
        "builder_sha256": sha256_file(Path(__file__).resolve()),
        "tool_profile": {"id": profile["id"], "path": profile_relative, "sha256": sha256_file(tool_profile_path)},
        "evaluator_content_excluded": True,
        "root": ".",
        "files": entries,
        "aggregate_sha256": sha256_bytes(canonical_bytes(entries)),
    }
    _validate_schema(manifest, PILOT_WORKSPACE_SCHEMA, "pilot workspace manifest")
    visible = canonical_bytes({"manifest": manifest, "files": files}).lower()
    forbidden = (
        b"pilot-evaluator/", b"pilot-evaluator-manifest", b"blind_assignments",
        b"hidden_checks", b"action_rubric", b"integration-failure.test.mjs",
    )
    if any(token in visible for token in forbidden):
        raise WorkspaceError("evaluator-only material leaked into producer-visible pilot workspace")
    return manifest, files, presented


def _normalize_files(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    identities: dict[str, str] = {}
    for item in sorted(files, key=lambda value: value["path"]):
        identity = _canonical_path(item["path"], "fixture")
        if identity in identities:
            raise WorkspaceError(f"fixture paths collide: {identities[identity]!r}, {item['path']!r}")
        identities[identity] = item["path"]
        if item["mode"] not in {"0644", "0755"}:
            raise WorkspaceError(f"unsupported fixture mode for {item['path']}")
        data = item["content"].encode("utf-8")
        normalized.append({
            "path": item["path"],
            "sha256": sha256_bytes(data),
            "size": len(data),
            "mode": item["mode"],
        })
    return normalized


def validate_tool_profile(path: Path = TOOL_PROFILE_PATH) -> dict[str, Any]:
    profile = load_json(path)
    _validate_schema(profile, TOOL_PROFILE_SCHEMA, "tool profile")
    return profile


def build_manifest(
    *,
    experiment_id: str,
    pair_id: str,
    scenario: dict[str, Any],
    protocol: str,
    workspace_seed: int,
    source_binding: dict[str, Any],
    tool_profile_path: Path = TOOL_PROFILE_PATH,
    tool_profile_root: Path = HERE,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    if protocol not in {"v1", "v2"}:
        raise WorkspaceError(f"unsupported protocol: {protocol}")
    fixture_id = scenario["input"]["fixture"]
    if fixture_id not in CANONICAL_FIXTURES:
        raise WorkspaceError(f"scenario references a non-canonical fixture: {fixture_id}")
    profile = validate_tool_profile(tool_profile_path)
    _validate_source_binding(protocol, source_binding)
    try:
        tool_profile_relative = tool_profile_path.resolve().relative_to(tool_profile_root.resolve()).as_posix()
    except ValueError as exc:
        raise WorkspaceError("tool profile path escapes the experiment root") from exc
    files, presented = _builtin_files(fixture_id, protocol)
    entries = _normalize_files(files)
    semantic_case = {
        "scenario_id": scenario["id"],
        "scenario_slug": scenario["slug"],
        "task": scenario["input"]["task"],
        "fixture": fixture_id,
        "injected_facts": scenario["input"]["injected_facts"],
        "oracle": scenario["oracle"],
    }
    fixture_definition = {
        "fixture_id": fixture_id,
        "scenario_id": scenario["id"],
        "scenario_slug": scenario["slug"],
        "common_or_selected_files": entries,
        "presented_paths": presented,
    }
    variant = {"protocol": protocol, "files": entries}
    manifest = {
        "schema_version": "1.0",
        "algorithm": "sha256-workspace-manifest-v1",
        "experiment_id": experiment_id,
        "pair_id": pair_id,
        "scenario_id": scenario["id"],
        "scenario_slug": scenario["slug"],
        "protocol": protocol,
        "workspace_seed": workspace_seed,
        "input_sha256": scenario["input_sha256"],
        "fixture_id": fixture_id,
        "fixture_sha256": sha256_bytes(canonical_bytes(fixture_definition)),
        "semantic_case_sha256": sha256_bytes(canonical_bytes(semantic_case)),
        "variant_sha256": sha256_bytes(canonical_bytes(variant)),
        "protocol_source": {
            "protocol": protocol,
            "aggregate_sha256": source_binding["aggregate_sha256"],
            "manifest": source_binding["manifest"],
        },
        "builder_sha256": sha256_file(Path(__file__).resolve()),
        "tool_profile": {
            "id": profile["id"],
            "path": tool_profile_relative,
            "sha256": sha256_file(tool_profile_path),
        },
        "root": ".",
        "files": entries,
        "aggregate_sha256": sha256_bytes(canonical_bytes(entries)),
    }
    _validate_schema(manifest, WORKSPACE_SCHEMA, "workspace manifest")
    return manifest, files, presented


def _target_path(root: Path, relative: str) -> Path:
    _canonical_path(relative, "workspace")
    candidate = root.joinpath(*PurePosixPath(relative).parts)
    try:
        candidate.resolve(strict=False).relative_to(root.resolve())
    except ValueError as exc:
        raise WorkspaceError(f"workspace path escapes target: {relative}") from exc
    return candidate


def _absolute_identity(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _resolved_identity(path: Path, label: str) -> str:
    try:
        return os.path.normcase(os.path.abspath(os.fspath(path.resolve(strict=False))))
    except (OSError, RuntimeError) as exc:
        raise WorkspaceError(f"cannot resolve {label} path safely: {path}") from exc


def _identity_is_within(candidate: str, root: str) -> bool:
    try:
        return os.path.commonpath((candidate, root)) == root
    except ValueError:
        return False


def external_output_path(workspace: Path, output: Path, label: str) -> Path:
    workspace_identities = {
        _absolute_identity(workspace),
        _resolved_identity(workspace, "workspace"),
    }
    output_identities = {
        _absolute_identity(output),
        _resolved_identity(output, label),
    }
    if any(
        _identity_is_within(output_identity, workspace_identity)
        for output_identity in output_identities
        for workspace_identity in workspace_identities
    ):
        raise WorkspaceError(f"{label} output must be outside the materialized workspace")
    return output.resolve(strict=False)


def materialize_workspace(target: Path, files: list[dict[str, Any]]) -> None:
    if target.exists():
        if target.is_symlink() or not target.is_dir():
            raise WorkspaceError("workspace target must be a new directory")
        if any(target.iterdir()):
            raise WorkspaceError("workspace target must be empty")
        target.rmdir()
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    try:
        for item in files:
            path = _target_path(staging, item["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            data = item["content"].encode("utf-8")
            path.write_bytes(data)
            if item["mode"] == "0755":
                path.chmod(path.stat().st_mode | 0o111)
        os.replace(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def validate_workspace(root: Path, manifest: dict[str, Any]) -> None:
    schema = PILOT_WORKSPACE_SCHEMA if manifest.get("algorithm") == "sha256-pilot-workspace-manifest-v1" else WORKSPACE_SCHEMA
    _validate_schema(manifest, schema, "workspace manifest")
    actual: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda value: value.relative_to(root).as_posix()):
        if path.is_symlink():
            raise WorkspaceError(f"workspace contains a symlink: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        _canonical_path(relative, "workspace")
        actual.append({
            "path": relative,
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
            "mode": next((item["mode"] for item in manifest["files"] if item["path"] == relative), "0644"),
        })
    if actual != manifest["files"]:
        raise WorkspaceError("materialized workspace drifted from its manifest")
    if manifest["aggregate_sha256"] != sha256_bytes(canonical_bytes(actual)):
        raise WorkspaceError("workspace aggregate hash mismatch")


def _protocol_bundle_files(protocol: str) -> tuple[dict[str, Any], list[tuple[str, bytes, str]]]:
    if protocol == "v1":
        snapshot_path = BASELINE_SOURCE_PATH
        source = load_json(snapshot_path)
        with tarfile.open(BASELINE_ARCHIVE_PATH, mode="r:") as archive:
            members = {member.name: member for member in archive.getmembers() if member.isfile()}
            files = []
            for item in source["files"]:
                member = members.get(item["path"])
                if member is None:
                    raise WorkspaceError(f"baseline protocol archive is missing {item['path']}")
                handle = archive.extractfile(member)
                if handle is None:
                    raise WorkspaceError(f"cannot extract baseline protocol file {item['path']}")
                data = handle.read()
                if sha256_bytes(data) != item["sha256"]:
                    raise WorkspaceError(f"baseline protocol file drifted: {item['path']}")
                files.append((item["path"], data, item["mode"]))
    elif protocol == "v2":
        snapshot_path = CANDIDATE_SOURCE_PATH
        source = load_json(snapshot_path)
        files = []
        for item in source["files"]:
            path = SKILL_ROOT / item["path"]
            if not path.is_file() or path.is_symlink():
                raise WorkspaceError(f"candidate protocol file is unavailable: {item['path']}")
            data = path.read_bytes()
            if sha256_bytes(data) != item["sha256"]:
                raise WorkspaceError(f"candidate protocol file drifted: {item['path']}")
            files.append((item["path"], data, item["mode"]))
    else:
        raise WorkspaceError(f"unsupported protocol bundle: {protocol}")
    if not any(path == "SKILL.md" for path, _, _ in files):
        raise WorkspaceError("protocol bundle lacks SKILL.md")
    return source, files


def build_protocol_bundle(protocol: str, target: Path) -> dict[str, Any]:
    source, files = _protocol_bundle_files(protocol)
    if target.exists():
        if target.is_symlink() or not target.is_dir() or any(target.iterdir()):
            raise WorkspaceError("protocol bundle target must be a new empty directory")
        target.rmdir()
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    entries: list[dict[str, Any]] = []
    try:
        for relative, data, mode in files:
            path = _target_path(staging, relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(0o444)
            entries.append({"path": relative, "sha256": sha256_bytes(data), "size": len(data), "mode": mode})
        entries.sort(key=lambda item: item["path"])
        manifest = {
            "schema_version": "1.0", "algorithm": "sha256-protocol-bundle-manifest-v1", "protocol": protocol,
            "source_snapshot": {
                "manifest_path": "baseline-source.json" if protocol == "v1" else "candidate-source.json",
                "manifest_sha256": sha256_file(BASELINE_SOURCE_PATH if protocol == "v1" else CANDIDATE_SOURCE_PATH),
                "aggregate_sha256": source["aggregate_sha256"],
            },
            "entrypoint": "SKILL.md", "files": entries, "aggregate_sha256": sha256_bytes(canonical_bytes(entries)),
        }
        _validate_schema(manifest, PROTOCOL_BUNDLE_SCHEMA, "protocol bundle manifest")
        (staging / "bundle-manifest.json").write_bytes(canonical_bytes(manifest))
        (staging / "bundle-manifest.json").chmod(0o444)
        os.replace(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    validate_protocol_bundle(target, manifest)
    return manifest


def validate_protocol_bundle(root: Path, manifest: dict[str, Any] | None = None) -> None:
    manifest_path = root / "bundle-manifest.json"
    current = load_json(manifest_path) if manifest is None else manifest
    _validate_schema(current, PROTOCOL_BUNDLE_SCHEMA, "protocol bundle manifest")
    actual = []
    for item in current["files"]:
        path = _target_path(root, item["path"])
        if not path.is_file() or path.is_symlink():
            raise WorkspaceError(f"protocol bundle file is missing: {item['path']}")
        data = path.read_bytes()
        actual.append({"path": item["path"], "sha256": sha256_bytes(data), "size": len(data), "mode": item["mode"]})
    if actual != current["files"] or sha256_bytes(canonical_bytes(actual)) != current["aggregate_sha256"]:
        raise WorkspaceError("protocol bundle drifted from its frozen source")


def apply_pilot_injection(
    workspace: Path,
    case_id: str,
    episode_id: str,
    *,
    evaluator_path: Path = PILOT_EVALUATOR_PATH,
) -> dict[str, Any]:
    if episode_id != "E02":
        raise WorkspaceError("pilot injections are legal only before E02")
    evaluator = load_pilot_evaluator(evaluator_path)
    matches = [item for item in evaluator["injections"] if item["case_id"] == case_id and item["before_episode"] == episode_id]
    if len(matches) != 1:
        raise WorkspaceError(f"pilot injection is missing or duplicated for {case_id}/{episode_id}")
    injection = matches[0]
    before = snapshot_workspace(workspace)
    changed: list[dict[str, Any]] = []
    if injection["operation"] in {"write-files", "replace-files"}:
        mappings = {
            "T3-E02": [
                ("pilot-evaluator/T3/injected/client-runtime.ts", "src/cache/client-runtime.ts"),
                ("pilot-evaluator/T3/integration-failure.test.mjs", "test/cache-integration.test.mjs"),
            ],
            "T5-E02": [("pilot-evaluator/T5/injected/resume.ts", "src/payments/resume.ts")],
        }
        for source_relative, target_relative in mappings[injection["injection_id"]]:
            source = HERE / source_relative
            target = _target_path(workspace, target_relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            data = source.read_bytes()
            target.write_bytes(data)
            changed.append({"path": target_relative, "sha256": sha256_bytes(data), "size": len(data)})
    elif injection["operation"] == "increment-reality-and-kill":
        reality_path = _target_path(workspace, "reality/account.json")
        reality = load_json(reality_path)
        if reality != {"applied_count": 1, "operation_ids": ["pilot-credit-001"]}:
            raise WorkspaceError("S1 controller barrier requires exactly one observed effect before recovery")
        changed.append({"path": "reality/account.json", "sha256": sha256_file(reality_path), "size": reality_path.stat().st_size})
    else:
        raise WorkspaceError(f"unsupported pilot injection operation: {injection['operation']}")
    after = snapshot_workspace(workspace)
    receipt = {
        "schema_version": "1.0", "algorithm": "sha256-pilot-injection-receipt-v1",
        "injection_id": injection["injection_id"], "case_id": case_id, "before_episode": episode_id,
        "before_workspace_sha256": before["aggregate_sha256"], "after_workspace_sha256": after["aggregate_sha256"],
        "changed_files": sorted(changed, key=lambda item: item["path"]),
        "evaluator_manifest_sha256": sha256_file(evaluator_path),
    }
    receipt["receipt_sha256"] = sha256_bytes(canonical_bytes(receipt))
    return receipt


def snapshot_workspace(root: Path) -> dict[str, Any]:
    entries = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink():
            raise WorkspaceError(f"workspace contains a symlink: {path}")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            _canonical_path(relative, "workspace snapshot")
            entries.append({"path": relative, "sha256": sha256_file(path), "size": path.stat().st_size})
    return {"schema_version": "1.0", "algorithm": "sha256-materialized-tree-v1", "files": entries, "aggregate_sha256": sha256_bytes(canonical_bytes(entries))}


def build_presented_artifact(
    workspace: Path,
    workspace_manifest: dict[str, Any],
    presented_paths: list[str],
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for relative in sorted(presented_paths):
        path = _target_path(workspace, relative)
        if path.is_symlink():
            raise WorkspaceError(f"presented artifact path is a symlink: {relative}")
        if not path.is_file():
            raise MissingPresentedArtifact(f"presented artifact file is missing: {relative}")
        data = path.read_bytes()
        entries.append({
            "path": relative,
            "sha256": sha256_bytes(data),
            "size": len(data),
            "media_type": "text/plain",
            "purpose": "review deliverable",
        })
    result = {
        "schema_version": "1.0",
        "algorithm": "sha256-presented-artifact-v1",
        "scenario_id": workspace_manifest["scenario_id"],
        "scenario_slug": workspace_manifest["scenario_slug"],
        "semantic_case_sha256": workspace_manifest["semantic_case_sha256"],
        "workspace_manifest_sha256": sha256_bytes(canonical_bytes(workspace_manifest)),
        "files": entries,
        "aggregate_sha256": sha256_bytes(canonical_bytes(entries)),
    }
    _validate_schema(result, PRESENTED_SCHEMA, "presented artifact")
    return result


def presented_file_entries(workspace: Path, presented_paths: list[str]) -> list[dict[str, Any]]:
    """Bind the exact frozen deliverable set to files in a materialized workspace."""
    entries: list[dict[str, Any]] = []
    identities: set[str] = set()
    for relative in sorted(presented_paths):
        identity = _canonical_path(relative, "presented artifact")
        if identity in identities:
            raise WorkspaceError(f"presented artifact paths collide: {relative!r}")
        identities.add(identity)
        path = _target_path(workspace, relative)
        if path.is_symlink():
            raise WorkspaceError(f"presented artifact path is a symlink: {relative}")
        if not path.is_file():
            raise MissingPresentedArtifact(f"presented artifact file is missing: {relative}")
        data = path.read_bytes()
        entries.append({
            "path": relative,
            "sha256": sha256_bytes(data),
            "size": len(data),
            "media_type": mimetypes.guess_type(relative)[0] or "application/octet-stream",
            "purpose": "anonymous task deliverable",
        })
    return entries


def presented_artifact_aggregate(workspace: Path, presented_paths: list[str]) -> str:
    return sha256_bytes(canonical_bytes(presented_file_entries(workspace, presented_paths)))


def write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_workspace_manifest(workspace: Path, output: Path, manifest: dict[str, Any]) -> None:
    path = external_output_path(workspace, output, "workspace manifest")
    write_bytes_atomic(path, canonical_bytes(manifest))


def write_presented_artifact(workspace: Path, output: Path, artifact: dict[str, Any]) -> None:
    _validate_schema(artifact, PRESENTED_SCHEMA, "presented artifact")
    path = external_output_path(workspace, output, "presented artifact")
    write_bytes_atomic(path, canonical_bytes(artifact))


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=Path, default=HERE / "scenarios.json")
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--scenario-id", type=int, required=True)
    parser.add_argument("--protocol", choices=("v1", "v2"), required=True)
    parser.add_argument("--pair-id", required=True)
    parser.add_argument("--experiment-id", default="create-loop-v1-v2-paired-2026")
    parser.add_argument("--workspace-seed", type=int, default=20260801)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)
    target = Path(os.path.abspath(os.fspath(args.target)))
    manifest_path = external_output_path(target, args.manifest, "workspace manifest")
    scenarios = load_json(args.scenarios)
    preregistration = load_json(args.preregistration)
    try:
        scenario = next(item for item in scenarios["scenarios"] if item["id"] == args.scenario_id)
    except StopIteration as exc:
        raise WorkspaceError(f"unknown scenario ID: {args.scenario_id}") from exc
    manifest, files, _ = build_manifest(
        experiment_id=args.experiment_id,
        pair_id=args.pair_id,
        scenario=scenario,
        protocol=args.protocol,
        workspace_seed=args.workspace_seed,
        source_binding=preregistration["baseline" if args.protocol == "v1" else "candidate"]["source_snapshot"],
        tool_profile_path=args.preregistration.parent / preregistration["execution_config"]["tool_profile"]["path"],
        tool_profile_root=args.preregistration.parent,
    )
    materialize_workspace(target, files)
    validate_workspace(target, manifest)
    write_workspace_manifest(target, manifest_path, manifest)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except WorkspaceError as exc:
        print(f"workspace error: {exc}", file=sys.stderr)
        raise SystemExit(2)
