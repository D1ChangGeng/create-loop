#!/usr/bin/env python3
"""Project a create-loop v2 journal into a deterministic resume document."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from schema_runtime import SchemaError, load_json as load_schema_json, validate as validate_schema

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "schemas"
WINDOWS_DEVICE_NAME = re.compile(
    r"^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$", re.IGNORECASE
)

NODE_STATES = {"pending", "active", "waiting", "verifying", "done", "closed"}
LOOP_STATES = {"active", "waiting", "completed", "closed"}
JOURNAL_KINDS = {
    "plan_activated", "transition", "evidence", "evidence_relation", "decision",
    "context", "effect_pre", "effect_post", "completion", "reopen",
    "loop_lifecycle", "legacy_import",
}
TRANSITIONS = {
    "pending": {"active", "waiting", "closed"},
    "active": {"verifying", "waiting", "closed"},
    "waiting": {"pending", "active", "closed"},
    "verifying": {"done", "active", "waiting", "closed"},
    "done": {"active", "closed"},
    "closed": set(),
}

if os.name == "nt":
    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _LCMAP_STRING_EX = _KERNEL32.LCMapStringEx
    _LCMAP_STRING_EX.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint,
        ctypes.c_wchar_p,
        ctypes.c_int,
        ctypes.c_wchar_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_ssize_t,
    ]
    _LCMAP_STRING_EX.restype = ctypes.c_int
else:
    _LCMAP_STRING_EX = None


class ProjectionError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def check_sha256(check: dict[str, Any]) -> str:
    return sha256_json(check)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_legacy_report(loop_dir: Path, records: list[dict[str, Any]]) -> None:
    report_path = confined_file(loop_dir, "migration-report.json", "JOURNAL-LEGACY")
    if not report_path.exists():
        raise ProjectionError("JOURNAL-LEGACY migration-report.json is required")
    report = load_json(report_path)
    _validate_shape(report, "migration-report", "MIGRATION-REPORT")
    payload = _payload(records[0])
    if report["source_hashes"] != payload["source_hashes"]:
        raise ProjectionError("JOURNAL-LEGACY migration report source hashes do not match legacy_import")
    bound_seq = report["journal_last_seq"]
    if bound_seq > len(records):
        raise ProjectionError("JOURNAL-LEGACY migration report extends beyond the journal tail")
    bound_records = records[:bound_seq]
    if not bound_records or bound_records[-1].get("seq") != bound_seq:
        raise ProjectionError("JOURNAL-LEGACY migration report journal prefix is not contiguous")
    journal_hash = hashlib.sha256(
        b"".join(
            (
                json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                + "\n"
            ).encode("utf-8")
            for record in bound_records
        )
    ).hexdigest()
    if report["journal_sha256"] != journal_hash:
        raise ProjectionError("JOURNAL-LEGACY migration report does not bind this journal")


def safe_relative_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(value)
    return (
        bool(posix.parts)
        and not posix.is_absolute()
        and not windows.is_absolute()
        and not windows.drive
        and ".." not in posix.parts
        and all(":" not in part for part in posix.parts)
    )


def canonical_output_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ProjectionError(f"invalid output path: {value!r}")
    normalized = value.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(value)
    if (
        not posix.parts
        or posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or ".." in posix.parts
        or any(
            any(ord(char) < 32 or char in '<>:"|?*' for char in part)
            or part.endswith((" ", "."))
            or WINDOWS_DEVICE_NAME.fullmatch(part) is not None
            for part in posix.parts
        )
    ):
        raise ProjectionError(f"invalid output path: {value!r}")
    return posix.as_posix()


def output_path_identity(value: str) -> str:
    canonical = canonical_output_path(value)
    if _LCMAP_STRING_EX is None:
        return canonical
    uppercase = 0x00000200
    source_units = len(canonical.encode("utf-16-le")) // 2
    needed = _LCMAP_STRING_EX(
        None, uppercase, canonical, source_units, None, 0, None, None, 0
    )
    if needed <= 0:
        raise ProjectionError(f"cannot compute Windows output path identity: {value!r}")
    buffer = ctypes.create_unicode_buffer(needed)
    written = _LCMAP_STRING_EX(
        None, uppercase, canonical, source_units, buffer, needed, None, None, 0
    )
    if written != needed:
        raise ProjectionError(f"cannot compute Windows output path identity: {value!r}")
    return buffer[:written]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_hashed_json(path: Path) -> tuple[Any, str]:
    raw = path.read_bytes()
    try:
        return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProjectionError(f"SCHEMA-LOAD {path}: invalid UTF-8 JSON") from exc


def confined_file(root: Path, relative: str, label: str) -> Path:
    if not safe_relative_path(relative):
        raise ProjectionError(f"{label}: path must stay within the loop directory")
    candidate = root / Path(relative)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ProjectionError(f"{label}: referenced file is missing") from exc
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ProjectionError(f"{label}: resolved path escapes the loop directory") from exc
    if not resolved.is_file():
        raise ProjectionError(f"{label}: referenced path is not a file")
    return resolved


def load_journal(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ProjectionError(f"JOURNAL-PARSE line {line_number}: {exc.msg}") from exc
            if not isinstance(value, dict):
                raise ProjectionError(f"JOURNAL-PARSE line {line_number}: record is not an object")
            records.append(value)
    if not records:
        raise ProjectionError("JOURNAL-EMPTY: persistent loops require at least one record")
    return records


def _validate_shape(value: Any, schema_name: str, label: str) -> None:
    try:
        errors = validate_schema(value, load_schema_json(SCHEMAS / f"{schema_name}.schema.json"))
    except SchemaError as exc:
        raise ProjectionError(f"SCHEMA-{label} {exc}") from exc
    if errors:
        raise ProjectionError(f"SCHEMA-{label} {'; '.join(errors)}")


def _payload(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("payload")
    if not isinstance(payload, dict):
        raise ProjectionError(f"JOURNAL-PAYLOAD {record.get('record_id')}: payload must be an object")
    return payload


def _parse_time(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ProjectionError(f"JOURNAL-TIME {label}: invalid RFC 3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise ProjectionError(f"JOURNAL-TIME {label}: timestamp must include a timezone")
    return parsed


def _base_active_evidence_ids(
    evidence: dict[str, dict[str, Any]], at: datetime
) -> set[str]:
    active: set[str] = set()
    for evidence_id, payload in evidence.items():
        valid_until = payload.get("valid_until")
        if valid_until is not None and _parse_time(valid_until, evidence_id) <= at:
            continue
        active.add(evidence_id)
    return active


def _current_evidence_by_subject(
    evidence: dict[str, dict[str, Any]], active: set[str], challenged: set[str]
) -> dict[str, list[str]]:
    by_subject: dict[str, list[str]] = defaultdict(list)
    for evidence_id in active:
        if evidence_id in challenged:
            continue
        for subject in evidence[evidence_id]["subject_refs"]:
            by_subject[subject].append(evidence_id)
    return {key: sorted(value) for key, value in sorted(by_subject.items())}


def _current_evidence_state(
    evidence: dict[str, dict[str, Any]],
    evidence_seq: dict[str, int],
    relations: list[tuple[str, str, str]],
    at: datetime,
    nodes: dict[str, dict[str, Any]],
    active_plan_version: int | None,
    evidence_plan_versions: dict[str, int],
    evidence_check_bindings: dict[str, dict[str, Any]],
    evidence_cross_plan_reusable: set[str],
    *,
    filter_stale_check_evidence: bool = True,
) -> tuple[set[str], set[str]]:
    active = _base_active_evidence_ids(evidence, at)
    challenged: set[str] = set()
    relations_by_source: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for source, target, relation in relations:
        relations_by_source[source].append((target, relation))

    for source in sorted(active, key=evidence_seq.__getitem__, reverse=True):
        if source in challenged or source not in active:
            continue
        source_matches_active_plan = (
            active_plan_version is None
            or _evidence_matches_active_check_definition(
                source,
                evidence[source],
                nodes,
                active_plan_version,
                evidence_plan_versions,
                evidence_check_bindings,
                evidence_cross_plan_reusable,
            )
        )
        if not source_matches_active_plan:
            if filter_stale_check_evidence:
                continue
            active.discard(source)
            challenged.discard(source)
            continue
        for target, relation in relations_by_source.get(source, []):
            if target not in active:
                continue
            if relation == "challenges":
                challenged.add(target)
            else:
                active.discard(target)
                challenged.discard(target)
    return active, challenged


def _same_evidence_identity(
    source: str,
    target: str,
    evidence: dict[str, dict[str, Any]],
    evidence_check_bindings: dict[str, dict[str, Any]],
) -> bool:
    source_check = evidence[source].get("check_ref")
    target_check = evidence[target].get("check_ref")
    if source_check is None or target_check is None:
        return source_check is None and target_check is None
    source_binding = evidence_check_bindings.get(source)
    target_binding = evidence_check_bindings.get(target)
    if source_binding is None or target_binding is None:
        return False
    return all(
        source_binding[key] == target_binding[key]
        for key in ("node_id", "check_id", "check_sha256")
    )


def _node_reopen_requirements(
    node_id: str,
    done_refs: set[str],
    evidence: dict[str, dict[str, Any]],
    active_evidence: set[str],
    challenged_evidence: set[str],
    node: dict[str, Any],
    active_plan_version: int,
    evidence_plan_versions: dict[str, int],
    evidence_check_bindings: dict[str, dict[str, Any]],
    evidence_cross_plan_reusable: set[str],
) -> tuple[bool, set[str]]:
    done_checks = {
        evidence[ref].get("check_ref")
        for ref in done_refs
        if ref in evidence and evidence[ref].get("check_ref") is not None
    }
    invalid_support = any(ref not in active_evidence or ref in challenged_evidence for ref in done_refs)
    counterevidence = {
        ref
        for ref in active_evidence
        if ref not in challenged_evidence
        and evidence[ref].get("observed_result") in {"fail", "inconclusive"}
        and f"node:{node_id}" in evidence[ref].get("subject_refs", [])
        and (
            evidence[ref].get("check_ref") is None
            or (
                evidence[ref].get("check_ref") in done_checks
                and _evidence_matches_active_check_definition(
                    ref,
                    evidence[ref],
                    {node_id: node},
                    active_plan_version,
                    evidence_plan_versions,
                    evidence_check_bindings,
                    evidence_cross_plan_reusable,
                )
            )
        )
    }
    return invalid_support or bool(counterevidence), counterevidence


def _check_binding_matches(
    binding: dict[str, Any] | None, node_id: str, check: dict[str, Any]
) -> bool:
    return (
        isinstance(binding, dict)
        and binding.get("node_id") == node_id
        and binding.get("check_id") == check["id"]
        and binding.get("check_sha256") == check_sha256(check)
    )


def _check_evidence_matches_active_plan(
    evidence_id: str,
    node_id: str,
    check: dict[str, Any],
    active_plan_version: int,
    evidence_plan_versions: dict[str, int],
    evidence_check_bindings: dict[str, dict[str, Any]],
    evidence_cross_plan_reusable: set[str],
) -> bool:
    return (
        evidence_plan_versions.get(evidence_id) == active_plan_version
        or (
            evidence_id in evidence_cross_plan_reusable
            and _check_binding_matches(
                evidence_check_bindings.get(evidence_id), node_id, check
            )
        )
    )


def _evidence_matches_active_check_definition(
    evidence_id: str,
    payload: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    active_plan_version: int,
    evidence_plan_versions: dict[str, int],
    evidence_check_bindings: dict[str, dict[str, Any]],
    evidence_cross_plan_reusable: set[str],
) -> bool:
    check_ref = payload.get("check_ref")
    if check_ref is None:
        return True
    binding = evidence_check_bindings.get(evidence_id)
    node_id = binding.get("node_id") if isinstance(binding, dict) else None
    if node_id is None and evidence_plan_versions.get(evidence_id) == active_plan_version:
        subjects = payload.get("subject_refs", [])
        node_subjects = [item[5:] for item in subjects if item.startswith("node:")]
        if len(node_subjects) == 1:
            node_id = node_subjects[0]
    node = nodes.get(node_id)
    if node is None:
        return False
    check = next((item for item in node["checks"] if item["id"] == check_ref), None)
    return check is not None and _check_evidence_matches_active_plan(
        evidence_id,
        node_id,
        check,
        active_plan_version,
        evidence_plan_versions,
        evidence_check_bindings,
        evidence_cross_plan_reusable,
    )


def _authority_matches(boundary: dict[str, Any], record: dict[str, Any], payload: dict[str, Any]) -> bool:
    authority = str(boundary["authority"])
    return (
        payload.get("authority") == authority
        and record["actor"].get("type") == authority
    )


def workspace_root(loop_dir: Path) -> Path:
    resolved = loop_dir.resolve()
    for ancestor in (resolved, *resolved.parents):
        if ancestor.name != ".agents":
            continue
        try:
            relative = resolved.relative_to(ancestor)
        except ValueError:
            continue
        if relative.parts and relative.parts[0] == "loops":
            return ancestor.parent
    return resolved


def validate_artifact_binding(
    loop_dir: Path, record_id: str, binding: dict[str, Any]
) -> None:
    try:
        canonical = canonical_output_path(binding.get("path"))
        if binding.get("path") != canonical:
            raise ProjectionError("non-canonical artifact binding path")
        root = workspace_root(loop_dir).resolve()
        resolved = (root / Path(canonical)).resolve(strict=True)
        resolved.relative_to(root)
        if not resolved.is_file() or file_sha256(resolved) != binding.get("sha256"):
            raise ProjectionError("file missing or hash mismatch")
    except (OSError, TypeError, ValueError) as exc:
        raise ProjectionError(
            f"ARTIFACT-EVIDENCE {record_id}: bound artifact file is missing or hash mismatched"
        ) from exc


def _require_unique(values: list[Any], label: str) -> None:
    if len(values) != len(set(values)):
        raise ProjectionError(f"GRAPH-UNIQUE duplicate {label}")


def _validate_plan_semantics(goal: dict[str, Any], plan: dict[str, Any]) -> None:
    criteria_items = goal.get("success_criteria", [])
    constraint_items = goal.get("constraints", [])
    boundary_items = goal.get("authorization_boundaries", [])
    nodes = plan.get("nodes", [])
    criteria = {item["id"] for item in criteria_items}
    boundaries = {item["id"] for item in boundary_items}
    _require_unique([item["id"] for item in criteria_items], "success criterion id")
    _require_unique([item["id"] for item in constraint_items], "constraint id")
    _require_unique([item["id"] for item in boundary_items], "authorization boundary id")
    _require_unique([node["id"] for node in nodes], "node id")
    node_ids = {node["id"] for node in nodes}
    child_ids: list[str] = []
    child_count = 0
    dependencies: dict[str, list[str]] = {}
    check_ids: list[str] = []
    output_paths: list[str] = []

    for node in nodes:
        node_id = node["id"]
        checks = node["checks"]
        if not checks:
            raise ProjectionError(f"GRAPH-CHECK {node_id}: at least one deterministic check is required")
        check_ids.extend(check["id"] for check in checks)
        dependencies[node_id] = node["depends_on"]
        for dependency in node["depends_on"]:
            if dependency not in node_ids:
                raise ProjectionError(f"GRAPH-DANGLING {node_id}: unknown dependency {dependency!r}")
            if dependency == node_id:
                raise ProjectionError(f"GRAPH-CYCLE {node_id}: self dependency")
        for ref in node["success_criteria_refs"]:
            if ref not in criteria:
                raise ProjectionError(f"GRAPH-CRITERION {node_id}: unknown criterion {ref!r}")
        for ref in node["authorization_refs"]:
            if ref not in boundaries:
                raise ProjectionError(f"GRAPH-AUTH {node_id}: unknown authorization boundary {ref!r}")
        for output in node["outputs"]:
            try:
                canonical_output = canonical_output_path(output["path"])
            except ProjectionError:
                raise ProjectionError(f"GRAPH-PATH {node_id}: output path must stay relative to the workspace")
            if output["path"] != canonical_output:
                raise ProjectionError(
                    f"GRAPH-PATH {node_id}: output path must use canonical form {canonical_output!r}"
                )
            output_paths.append(output_path_identity(canonical_output))
        child = node.get("child_loop")
        if child is not None:
            child_count += 1
            child_ids.append(child["loop_id"])
            _require_unique(
                child["return_criteria_refs"], f"child return criterion in {node_id}"
            )
            _require_unique(
                child["return_deliverables"], f"child return deliverable in {node_id}"
            )
            for ref in child["return_criteria_refs"]:
                if ref not in criteria:
                    raise ProjectionError(f"CHILD-CRITERION {node_id}: unknown return criterion {ref!r}")
            output_identities = {
                output_path_identity(output["path"]) for output in node["outputs"]
            }
            for path in child["return_deliverables"]:
                try:
                    canonical_return = canonical_output_path(path)
                except ProjectionError:
                    raise ProjectionError(f"CHILD-PATH {node_id}: return deliverable must stay relative to the workspace")
                if path != canonical_return:
                    raise ProjectionError(
                        f"CHILD-PATH {node_id}: return deliverable must use canonical form {canonical_return!r}"
                    )
                if output_path_identity(canonical_return) not in output_identities:
                    raise ProjectionError(
                        f"CHILD-OUTPUT {node_id}: return deliverable {path!r} is not declared in node outputs"
                    )

    _require_unique(check_ids, "check id")
    _require_unique(output_paths, "output path")
    _require_unique(child_ids, "child loop id")
    modules = set(plan["control"]["modules"])
    if modules and plan["control"]["mode"] != "governed":
        raise ProjectionError("JOURNAL-MODE optional modules require governed mode")
    if child_count and "children" not in modules:
        raise ProjectionError("CHILD-MODULE child_loop requires the children module")
    if "children" in modules and not child_count:
        raise ProjectionError("CHILD-MODULE children module is enabled but no child_loop is declared")

    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(node_id: str) -> None:
        if node_id in visiting:
            raise ProjectionError(f"GRAPH-CYCLE dependency cycle includes {node_id}")
        if node_id in visited:
            return
        visiting.add(node_id)
        for dependency in dependencies[node_id]:
            walk(dependency)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in dependencies:
        walk(node_id)


def _review_manifest_path(loop_dir: Path, manifest_ref: str, record_id: str) -> Path:
    roots = {
        "loop:": loop_dir,
        "workspace:": workspace_root(loop_dir),
    }
    for prefix, root in roots.items():
        if manifest_ref.startswith(prefix):
            relative = manifest_ref[len(prefix):]
            return confined_file(root, relative, f"EVIDENCE-REVIEW {record_id}")
    raise ProjectionError(
        f"EVIDENCE-REVIEW {record_id}: manifest_ref must use the loop: or workspace: safe root"
    )


def _completion_evidence_refs(payload: dict[str, Any]) -> set[str]:
    refs = {
        ref
        for values in payload["criterion_evidence"].values()
        for ref in values
    }
    refs.update(payload.get("deterministic_check_refs", []))
    refs.update(payload.get("counterexample_review_refs", []))
    if payload.get("system_review_ref") is not None:
        refs.add(payload["system_review_ref"])
    return refs


def _completion_affected_refs(
    payload: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
) -> tuple[set[str], set[str]]:
    criterion_refs = set(payload["criterion_evidence"])
    node_refs = {
        subject[5:]
        for ref in _completion_evidence_refs(payload)
        if ref in evidence
        for subject in evidence[ref].get("subject_refs", [])
        if subject.startswith("node:")
    }
    return criterion_refs, node_refs


def _current_completion_counterevidence(
    payload: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
    active_evidence: set[str],
    challenged_evidence: set[str],
    nodes: dict[str, dict[str, Any]],
    active_plan_version: int,
    evidence_plan_versions: dict[str, int],
    evidence_check_bindings: dict[str, dict[str, Any]],
    evidence_cross_plan_reusable: set[str],
) -> set[str]:
    support_refs = _completion_evidence_refs(payload)
    support_subjects = {
        subject
        for ref in support_refs
        if ref in evidence
        for subject in evidence[ref].get("subject_refs", [])
    }
    support_checks = {
        evidence[ref].get("check_ref")
        for ref in support_refs
        if ref in evidence and evidence[ref].get("check_ref") is not None
    }
    return {
        ref
        for ref in active_evidence
        if ref not in challenged_evidence
        and evidence[ref].get("observed_result") in {"fail", "inconclusive"}
        and _evidence_matches_active_check_definition(
            ref,
            evidence[ref],
            nodes,
            active_plan_version,
            evidence_plan_versions,
            evidence_check_bindings,
            evidence_cross_plan_reusable,
        )
        and (
            bool(set(evidence[ref].get("subject_refs", [])) & support_subjects)
            or (
                evidence[ref].get("check_ref") is not None
                and evidence[ref].get("check_ref") in support_checks
            )
        )
    }


def _active_failed_reviews(
    node_id: str,
    node: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
    active_evidence: set[str],
    challenged_evidence: set[str],
) -> set[str]:
    check_ids = {check["id"] for check in node["checks"]}
    return {
        ref
        for ref in active_evidence
        if ref not in challenged_evidence
        and evidence[ref].get("review_context") is not None
        and evidence[ref].get("observed_result") in {"fail", "inconclusive"}
        and (
            f"node:{node_id}" in evidence[ref].get("subject_refs", [])
            or evidence[ref].get("check_ref") in check_ids
        )
    }


def _would_cycle(edges: dict[str, set[str]], source: str, target: str) -> bool:
    stack = [target]
    seen: set[str] = set()
    while stack:
        current = stack.pop()
        if current == source:
            return True
        if current in seen:
            continue
        seen.add(current)
        stack.extend(edges.get(current, ()))
    return False


def project(loop_dir: Path, *, generated_at: str | None = None) -> dict[str, Any]:
    goal, goal_hash = load_hashed_json(confined_file(loop_dir, "goal.json", "GRAPH-GOAL"))
    _validate_shape(goal, "goal", "GOAL")
    records = load_journal(loop_dir / "journal.jsonl")
    for record in records:
        _validate_shape(record, "journal-record", "JOURNAL")
    record_ids: set[str] = set()
    expected_seq = 1
    previous_record_time: datetime | None = None
    for record in records:
        if record.get("seq") != expected_seq:
            raise ProjectionError(f"JOURNAL-SEQ expected {expected_seq}, found {record.get('seq')!r}")
        expected_seq += 1
        record_id = record.get("record_id")
        if not isinstance(record_id, str) or record_id in record_ids:
            raise ProjectionError(f"JOURNAL-ID duplicate or invalid record_id {record_id!r}")
        record_ids.add(record_id)
        if record.get("kind") not in JOURNAL_KINDS:
            raise ProjectionError(f"JOURNAL-KIND {record_id}: unknown record kind {record.get('kind')!r}")
        record_time = _parse_time(record.get("ts"), record_id)
        if previous_record_time is not None and record_time < previous_record_time:
            raise ProjectionError(
                f"JOURNAL-TIME {record_id}: timestamp precedes the prior journal record"
            )
        previous_record_time = record_time
    if not any(record.get("kind") == "plan_activated" for record in records):
        raise ProjectionError("JOURNAL-PLAN no plan_activated record")
    legacy_imports = [record for record in records if record.get("kind") == "legacy_import"]
    if legacy_imports:
        legacy_import = legacy_imports[0]
        if len(legacy_imports) != 1:
            raise ProjectionError("JOURNAL-LEGACY exactly one legacy_import record is allowed")
        if legacy_import.get("seq") != 1 or records[0].get("kind") != "legacy_import":
            raise ProjectionError("JOURNAL-LEGACY legacy_import must be the seq=1 first record")
        if legacy_import.get("actor", {}).get("type") != "migrator":
            raise ProjectionError("JOURNAL-LEGACY legacy_import actor must be a migrator")
        if len(records) < 2 or records[1].get("kind") != "plan_activated":
            raise ProjectionError(
                "JOURNAL-LEGACY legacy_import must be followed immediately by the initial plan_activated"
            )
        _validate_legacy_report(loop_dir, records)
    nodes: dict[str, dict[str, Any]] = {}
    states: dict[str, str] = {}
    seen_node_ids: set[str] = set()
    plan: dict[str, Any] | None = None
    plan_path: Path | None = None
    plan_hash: str | None = None
    previous_plan_version: int | None = None
    lightweight_upgrade_evidence: str | None = None
    lightweight_upgrade_decision: str | None = None
    legacy_states: dict[str, str] = {}
    legacy_unverified_done: set[str] = set()
    legacy_reverification_active: dict[str, int] = {}
    reopen_nodes: set[str] = set()
    locally_reopened_nodes: set[str] = set()
    loop_status = "active"
    contexts: dict[str, str] = {}
    decisions: dict[str, dict[str, Any]] = {}
    decision_plan_versions: dict[str, int | None] = {}
    authorized: set[str] = set()
    effect_pre: dict[tuple[str, str], tuple[str, str | None]] = {}
    conclusive_effect_post: set[tuple[str, str]] = set()
    done_evidence_by_node: dict[str, set[str]] = {}
    completion_records: dict[str, dict[str, Any]] = {}
    active_completion: str | None = None
    latest_next_action: str | None = None
    evidence: dict[str, dict[str, Any]] = {}
    evidence_seq: dict[str, int] = {}
    evidence_plan_versions: dict[str, int] = {}
    evidence_check_bindings: dict[str, dict[str, Any]] = {}
    evidence_cross_plan_reusable: set[str] = set()
    challenge_sources: dict[str, set[str]] = defaultdict(set)
    evidence_relations: list[tuple[str, str, str]] = []
    relation_edges: dict[str, set[str]] = defaultdict(set)
    seen_record_ids: set[str] = set()
    criteria = {criterion["id"] for criterion in goal["success_criteria"]}
    boundaries = {boundary["id"]: boundary for boundary in goal.get("authorization_boundaries", [])}
    projection_time = _parse_time(
        generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "projection",
    )
    for record in records:
        kind = record["kind"]
        node_id = record.get("node_id")
        record_time = _parse_time(record.get("ts"), record["record_id"])
        active_evidence_ids, challenged_evidence = _current_evidence_state(
            evidence,
            evidence_seq,
            evidence_relations,
            record_time,
            nodes,
            plan["plan_version"] if plan is not None else None,
            evidence_plan_versions,
            evidence_check_bindings,
            evidence_cross_plan_reusable,
        )
        if kind == "plan_activated":
            activation = _payload(record)
            previous_mode = plan.get("control", {}).get("mode") if plan is not None else None
            expected_ref = f"plans/plan-v{record.get('plan_version')}.json"
            if activation["plan_ref"].replace("\\", "/") != expected_ref:
                raise ProjectionError(f"JOURNAL-PLAN plan_ref must be {expected_ref!r}")
            candidate_path = confined_file(loop_dir, activation["plan_ref"], "JOURNAL-PLAN")
            candidate, candidate_hash = load_hashed_json(candidate_path)
            _validate_shape(candidate, "plan", "PLAN")
            _validate_plan_semantics(goal, candidate)
            if candidate_hash != activation["plan_sha256"]:
                raise ProjectionError("JOURNAL-PLAN activated plan hash does not match the file")
            if candidate.get("goal_sha256") != goal_hash:
                raise ProjectionError("GRAPH-GOAL plan goal_sha256 does not match goal.json")
            if candidate.get("plan_version") != record.get("plan_version"):
                raise ProjectionError("JOURNAL-PLAN activation plan_version does not match plan")
            if activation["previous_version"] != previous_plan_version:
                raise ProjectionError("JOURNAL-PLAN previous_version does not match the active plan")
            if previous_plan_version is not None and candidate.get("plan_version") != previous_plan_version + 1:
                raise ProjectionError("JOURNAL-PLAN plan versions must advance by exactly one")
            if previous_plan_version is None and candidate.get("plan_version") != 1:
                raise ProjectionError("JOURNAL-PLAN initial plan version must be 1")
            if loop_status == "completed":
                raise ProjectionError(f"JOURNAL-PLAN {record['record_id']}: completed loops must reopen before replanning")
            if loop_status == "waiting":
                raise ProjectionError(
                    f"JOURNAL-LIFECYCLE {record['record_id']}: waiting loops must resume before replanning"
                )
            if previous_plan_version is not None:
                in_doubt_effects = sorted(
                    f"{effect_id}:{attempt_id}"
                    for effect_id, attempt_id in effect_pre.keys() - conclusive_effect_post
                )
                if in_doubt_effects:
                    raise ProjectionError(
                        f"EFFECT-REPLAN {record['record_id']}: resolve in-doubt effects "
                        f"before replanning: {in_doubt_effects}"
                    )
            evidence_refs = activation.get("evidence_refs", [])
            decision_ref = activation.get("decision_ref")
            if previous_plan_version is not None and (not evidence_refs or decision_ref is None):
                raise ProjectionError(
                    f"JOURNAL-PLAN {record['record_id']}: non-initial activation requires "
                    "causal evidence and a prior decision"
                )
            if previous_mode == "lightweight":
                if (
                    candidate.get("control", {}).get("mode") not in {"persistent", "governed"}
                    or evidence_refs != [lightweight_upgrade_evidence]
                    or decision_ref != lightweight_upgrade_decision
                    or decisions.get(decision_ref, {}).get("outcome")
                    != candidate.get("control", {}).get("mode")
                    or decisions.get(decision_ref, {}).get("plan_change") is not None
                ):
                    raise ProjectionError(
                        f"JOURNAL-MODE {record['record_id']}: lightweight upgrade must consume "
                        "the immediately preceding upgrade evidence and decision"
                    )
                stable_keys = set(plan) - {"plan_id", "plan_version", "created_at", "control"}
                if stable_keys != set(candidate) - {"plan_id", "plan_version", "created_at", "control"} or any(
                    plan[key] != candidate[key] for key in stable_keys
                ):
                    raise ProjectionError(
                        f"JOURNAL-MODE {record['record_id']}: lightweight upgrade may change only "
                        "plan identity, version, creation time, and control metadata"
                    )
            if any(ref not in active_evidence_ids or ref in challenged_evidence for ref in evidence_refs):
                raise ProjectionError(f"JOURNAL-PLAN {record['record_id']}: activation references non-prior or inactive evidence")
            if decision_ref is not None and decision_ref not in decisions:
                raise ProjectionError(f"JOURNAL-PLAN {record['record_id']}: activation references an unknown prior decision")
            if decision_ref is not None and evidence_refs != decisions[decision_ref]["evidence_refs"]:
                raise ProjectionError(
                    f"JOURNAL-PLAN {record['record_id']}: activation decision must "
                    "cite exactly the activation's causal evidence references"
                )
            if previous_plan_version is not None and previous_mode != "lightweight":
                decision = decisions[decision_ref]
                expected_change = {
                    "from_plan_version": previous_plan_version,
                    "from_plan_sha256": plan_hash,
                    "to_plan_version": candidate["plan_version"],
                    "to_plan_sha256": candidate_hash,
                }
                if decision.get("question") != "plan_replacement" or decision.get("plan_change") != expected_change:
                    raise ProjectionError(
                        f"JOURNAL-PLAN {record['record_id']}: replacement decision must bind "
                        "the exact active and candidate plan versions and hashes"
                    )
                if decision_plan_versions.get(decision_ref) != previous_plan_version:
                    raise ProjectionError(
                        f"JOURNAL-PLAN {record['record_id']}: replacement decision must be recorded under the prior plan"
                    )
                if any(evidence[ref].get("source_class") == "control_trigger" for ref in evidence_refs):
                    raise ProjectionError(
                        f"JOURNAL-PLAN {record['record_id']}: ordinary replans cannot use a control-only upgrade trigger"
                    )
            next_nodes = {item["id"]: item for item in candidate["nodes"]}
            if previous_plan_version is None and legacy_imports:
                imported_payload = _payload(legacy_imports[0])
                source = imported_payload["source"]
                if imported_payload["source_hashes"].get(source["event_log_ref"]) != source["event_log_sha256"]:
                    raise ProjectionError(
                        "JOURNAL-LEGACY event_log source hash does not match source_hashes"
                    )
                if imported_payload["source_hashes"].get("checkpoint.yaml") != source["checkpoint_sha256"]:
                    raise ProjectionError(
                        "JOURNAL-LEGACY checkpoint source hash does not match source_hashes"
                    )
                unknown_closed_nodes = sorted(
                    {
                        effect["node_id"]
                        for effect in imported_payload.get("closed_effects", [])
                    }
                    - set(next_nodes)
                )
                if unknown_closed_nodes:
                    raise ProjectionError(
                        "JOURNAL-LEGACY closed legacy effects reference unknown nodes: "
                        f"{unknown_closed_nodes}"
                    )
            removed = set(nodes) - set(next_nodes)
            removed_legacy_done = sorted(removed & legacy_unverified_done)
            if removed_legacy_done:
                raise ProjectionError(
                    f"JOURNAL-LEGACY {record['record_id']}: replan cannot remove or rename "
                    f"unverified legacy done nodes: {removed_legacy_done}"
                )
            unsafe = sorted(item for item in removed if states.get(item) not in {"done", "closed"})
            if unsafe:
                raise ProjectionError(f"JOURNAL-PLAN active nodes removed without closure: {unsafe}")
            reintroduced = sorted((set(next_nodes) - set(nodes)) & seen_node_ids)
            if reintroduced:
                raise ProjectionError(
                    f"JOURNAL-PLAN {record['record_id']}: node ids are globally unique and "
                    f"cannot be reintroduced after removal: {reintroduced}"
                )
            changed_live = sorted(
                item
                for item in set(nodes) & set(next_nodes)
                if nodes[item] != next_nodes[item] and states.get(item) != "pending"
            )
            if changed_live:
                raise ProjectionError(f"JOURNAL-PLAN non-pending nodes changed in place: {changed_live}")
            for item in next_nodes:
                states.setdefault(item, legacy_states.get(item, "pending"))
            if previous_plan_version is None:
                legacy_unverified_done.update(
                    item for item in next_nodes if legacy_states.get(item) == "done"
                )
            unknown_legacy = set(legacy_states) - set(next_nodes)
            if previous_plan_version is None and unknown_legacy:
                raise ProjectionError(f"JOURNAL-LEGACY unknown imported nodes: {sorted(unknown_legacy)}")
            invalid_legacy = {item: states[item] for item in next_nodes if states[item] not in NODE_STATES}
            if invalid_legacy:
                raise ProjectionError(f"JOURNAL-LEGACY invalid imported node states: {invalid_legacy}")
            nodes = next_nodes
            seen_node_ids.update(next_nodes)
            plan, plan_path, plan_hash = candidate, candidate_path, candidate_hash
            previous_plan_version = candidate["plan_version"]
            lightweight_upgrade_evidence = None
            lightweight_upgrade_decision = None
            seen_record_ids.add(record["record_id"])
            continue
        if kind == "legacy_import":
            if plan is not None:
                raise ProjectionError(f"JOURNAL-LEGACY {record['record_id']}: legacy import must precede plan activation")
            payload = _payload(record)
            if not isinstance(payload["node_states"], dict):
                raise ProjectionError(f"JOURNAL-LEGACY {record['record_id']}: node_states must be an object")
            closed_effects = payload.get("closed_effects", [])
            closed_effect_keys: set[tuple[str, str]] = set()
            closed_effect_seqs: set[int] = set()
            for effect in closed_effects:
                key = (effect["effect_id"], effect["attempt_id"])
                if key in closed_effect_keys:
                    raise ProjectionError(
                        f"JOURNAL-LEGACY {record['record_id']}: duplicate closed legacy effect {key!r}"
                    )
                if effect["post_seq"] <= effect["pre_seq"]:
                    raise ProjectionError(
                        f"JOURNAL-LEGACY {record['record_id']}: closed legacy effect {key!r} "
                        "must have post_seq after pre_seq"
                    )
                if effect["post_seq"] > payload["source"]["last_event_seq"]:
                    raise ProjectionError(
                        f"JOURNAL-LEGACY {record['record_id']}: closed legacy effect {key!r} "
                        "references a sequence beyond the bound event-log tail"
                    )
                for source_seq in (effect["pre_seq"], effect["post_seq"]):
                    if source_seq in closed_effect_seqs:
                        raise ProjectionError(
                            f"JOURNAL-LEGACY {record['record_id']}: source event seq "
                            f"{source_seq} is reused by multiple closed legacy effects"
                        )
                    closed_effect_seqs.add(source_seq)
                closed_effect_keys.add(key)
            legacy_states.update(payload["node_states"])
            seen_record_ids.add(record["record_id"])
            continue
        if plan is None:
            raise ProjectionError(f"JOURNAL-PLAN {record['record_id']}: no plan is active")
        if plan.get("control", {}).get("mode") == "lightweight":
            if kind == "evidence":
                payload = _payload(record)
                if (
                    lightweight_upgrade_evidence is not None
                    or lightweight_upgrade_decision is not None
                    or node_id is not None
                    or payload.get("subject_refs") != ["loop:control_mode"]
                    or payload.get("source_class") != "control_trigger"
                    or payload.get("check_ref") is not None
                    or payload.get("artifact_ref") is not None
                    or payload.get("review_context") is not None
                    or payload.get("observed_result") != "observation"
                ):
                    raise ProjectionError(
                        f"JOURNAL-MODE {record['record_id']}: lightweight upgrade prefix "
                        "requires one control-only observation"
                    )
                lightweight_upgrade_evidence = record["record_id"]
            elif kind == "decision":
                payload = _payload(record)
                if (
                    lightweight_upgrade_evidence is None
                    or lightweight_upgrade_decision is not None
                    or node_id is not None
                    or payload.get("question") != "control_mode_upgrade"
                    or payload.get("outcome") not in {"persistent", "governed"}
                    or payload.get("evidence_refs") != [lightweight_upgrade_evidence]
                    or payload.get("authorization_boundary_ref") is not None
                    or payload.get("overrides_evidence_ref") is not None
                    or "plan_change" not in payload
                    or payload["plan_change"] is not None
                ):
                    raise ProjectionError(
                        f"JOURNAL-MODE {record['record_id']}: lightweight upgrade decision "
                        "must immediately cite the upgrade observation"
                    )
                lightweight_upgrade_decision = record["record_id"]
            else:
                raise ProjectionError(
                    f"JOURNAL-MODE {record['record_id']}: lightweight history permits only "
                    "the bounded upgrade prefix before plan activation"
                )
        if loop_status == "closed":
            raise ProjectionError(f"JOURNAL-LIFECYCLE {record['record_id']}: closed loops are terminal")
        if record.get("plan_version") is not None and record.get("plan_version") != plan["plan_version"]:
            raise ProjectionError(f"JOURNAL-PLAN {record['record_id']}: record plan_version is not active")
        if loop_status == "completed" and kind not in {"evidence", "evidence_relation", "reopen", "loop_lifecycle"}:
            raise ProjectionError(f"JOURNAL-COMPLETION {record['record_id']}: completed loops must reopen before further work")
        if node_id is not None and node_id not in nodes:
            raise ProjectionError(f"GRAPH-NODE {record['record_id']}: node_id is not in the active plan: {node_id!r}")
        if kind == "evidence":
            payload = _payload(record)
            if payload["observed_result"] not in {"pass", "fail", "inconclusive", "observation"}:
                raise ProjectionError(f"EVIDENCE-RESULT {record['record_id']}: invalid observed result")
            if payload.get("valid_until") is not None and _parse_time(payload["valid_until"], record["record_id"]) <= record_time:
                raise ProjectionError(f"EVIDENCE-EXPIRY {record['record_id']}: evidence is already expired when recorded")
            for subject in payload["subject_refs"]:
                if subject.startswith("node:") and subject[5:] not in nodes:
                    raise ProjectionError(f"EVIDENCE-SUBJECT {record['record_id']}: unknown node subject {subject!r}")
                if subject.startswith("criterion:") and subject[10:] not in criteria:
                    raise ProjectionError(f"EVIDENCE-SUBJECT {record['record_id']}: unknown criterion subject {subject!r}")
            check_ref = payload.get("check_ref")
            check_binding = payload.get("check_binding")
            if check_ref is not None:
                if node_id is None or f"node:{node_id}" not in payload["subject_refs"]:
                    raise ProjectionError(f"EVIDENCE-CHECK {record['record_id']}: check evidence needs its node_id and node subject")
                declared_checks = {check["id"]: check for check in nodes[node_id]["checks"]}
                if check_ref not in declared_checks:
                    raise ProjectionError(f"EVIDENCE-CHECK {record['record_id']}: check is not declared by the active node")
                expected_binding = {
                    "plan_version": plan["plan_version"],
                    "node_id": node_id,
                    "check_id": check_ref,
                    "check_sha256": check_sha256(declared_checks[check_ref]),
                }
                if check_binding != expected_binding:
                    raise ProjectionError(
                        f"EVIDENCE-CHECK {record['record_id']}: check_binding does not match "
                        "the active canonical check definition"
                    )
            elif check_binding is not None:
                raise ProjectionError(
                    f"EVIDENCE-CHECK {record['record_id']}: check_binding requires check_ref"
                )
            artifact_ref = payload.get("artifact_ref")
            artifact_binding = payload.get("artifact_binding")
            if artifact_ref is not None:
                if "artifacts" not in set(plan["control"]["modules"]):
                    raise ProjectionError(
                        f"ARTIFACT-MODULE {record['record_id']}: artifact evidence "
                        "requires the artifacts module"
                    )
                if not isinstance(artifact_binding, dict):
                    raise ProjectionError(
                        f"ARTIFACT-EVIDENCE {record['record_id']}: artifact_ref requires "
                        "an immutable artifact_binding"
                    )
                validate_artifact_binding(loop_dir, record["record_id"], artifact_binding)
            elif artifact_binding is not None:
                raise ProjectionError(
                    f"ARTIFACT-EVIDENCE {record['record_id']}: artifact_binding requires artifact_ref"
                )
            if payload.get("review_context") is not None and "independent_review" not in set(plan["control"]["modules"]):
                raise ProjectionError(f"EVIDENCE-REVIEW {record['record_id']}: active plan has no independent_review module")
            review_context = payload.get("review_context")
            if review_context is not None:
                manifest_path = _review_manifest_path(
                    loop_dir, review_context["manifest_ref"], record["record_id"]
                )
                if file_sha256(manifest_path) != review_context["manifest_sha256"]:
                    raise ProjectionError(
                        f"EVIDENCE-REVIEW {record['record_id']}: manifest hash does not match"
                    )
            evidence[record["record_id"]] = payload
            evidence_seq[record["record_id"]] = record["seq"]
            evidence_plan_versions[record["record_id"]] = plan["plan_version"]
            if check_ref is not None:
                evidence_check_bindings[record["record_id"]] = check_binding
                if review_context is None:
                    evidence_cross_plan_reusable.add(record["record_id"])
        elif kind == "evidence_relation":
            payload = _payload(record)
            source = payload["source_evidence_ref"]
            target = payload["target_evidence_ref"]
            if source == target or source not in active_evidence_ids or target not in evidence:
                raise ProjectionError(f"EVIDENCE-REF {record['record_id']}: relation needs distinct prior evidence and an active source")
            if evidence_seq[source] <= evidence_seq[target]:
                raise ProjectionError(
                    f"EVIDENCE-ORDER {record['record_id']}: relation source evidence "
                    "must be newer than target evidence"
                )
            if source in challenged_evidence:
                raise ProjectionError(
                    f"EVIDENCE-CURRENT {record['record_id']}: relation source evidence "
                    "must not be challenged"
                )
            if not _evidence_matches_active_check_definition(
                source,
                evidence[source],
                nodes,
                plan["plan_version"],
                evidence_plan_versions,
                evidence_check_bindings,
                evidence_cross_plan_reusable,
            ):
                raise ProjectionError(
                    f"EVIDENCE-CURRENT {record['record_id']}: relation source evidence "
                    "does not match the active check definition"
                )
            relation = payload["relation"]
            source_subjects = set(evidence[source]["subject_refs"])
            target_subjects = set(evidence[target]["subject_refs"])
            if not target_subjects <= source_subjects:
                raise ProjectionError(
                    f"EVIDENCE-RELATION {record['record_id']}: relation source must cover "
                    "every target subject"
                )
            if not _same_evidence_identity(
                source, target, evidence, evidence_check_bindings
            ):
                raise ProjectionError(
                    f"EVIDENCE-RELATION {record['record_id']}: related evidence must share "
                    "the same exact check identity"
                )
            if relation in {"invalidates", "challenges"} and evidence[source].get("observed_result") not in {"fail", "inconclusive"}:
                raise ProjectionError(f"EVIDENCE-RELATION {record['record_id']}: counterevidence must fail or be inconclusive")
            if relation == "confirms" and evidence[source].get("observed_result") != "pass":
                raise ProjectionError(f"EVIDENCE-RELATION {record['record_id']}: confirming evidence must pass")
            if relation == "supersedes" and evidence[source].get("observed_result") not in {"pass", "fail", "inconclusive"}:
                raise ProjectionError(
                    f"EVIDENCE-RELATION {record['record_id']}: superseding evidence must be conclusive"
                )
            if _would_cycle(relation_edges, source, target):
                raise ProjectionError(f"EVIDENCE-CYCLE {record['record_id']}: relation creates a cycle")
            if relation == "challenges":
                challenge_sources[target].add(source)
            elif relation == "confirms":
                if evidence[target].get("observed_result") not in {"fail", "inconclusive"}:
                    raise ProjectionError(
                        f"EVIDENCE-RELATION {record['record_id']}: confirms must target exact challenge evidence"
                    )
                if not any(target in sources for sources in challenge_sources.values()):
                    raise ProjectionError(
                        f"EVIDENCE-RELATION {record['record_id']}: confirms target is not an active challenge source"
                    )
            relation_edges[source].add(target)
            evidence_relations.append((source, target, relation))
        elif kind == "decision":
            payload = _payload(record)
            if any(ref not in active_evidence_ids for ref in payload["evidence_refs"]):
                raise ProjectionError(f"JOURNAL-REF {record['record_id']}: decision references non-prior or inactive evidence")
            if payload.get("plan_change") is not None and any(
                ref in challenged_evidence for ref in payload["evidence_refs"]
            ):
                raise ProjectionError(
                    f"JOURNAL-PLAN {record['record_id']}: replacement decision cannot cite challenged evidence"
                )
            override_ref = payload.get("overrides_evidence_ref")
            if override_ref is not None:
                if override_ref not in active_evidence_ids or evidence[override_ref].get("observed_result") not in {"fail", "inconclusive"}:
                    raise ProjectionError(f"EVIDENCE-OVERRIDE {record['record_id']}: override requires active prior failed evidence")
            boundary = payload.get("authorization_boundary_ref")
            if boundary is not None:
                if boundary not in boundaries:
                    raise ProjectionError(f"EFFECT-AUTH {record['record_id']}: unknown authorization boundary")
                if not _authority_matches(boundaries[boundary], record, payload):
                    raise ProjectionError(f"EFFECT-AUTH {record['record_id']}: decision actor lacks the declared authority")
            decisions[record["record_id"]] = payload
            decision_plan_versions[record["record_id"]] = record.get("plan_version")
            if boundary:
                if payload["outcome"] in {"approved", "authorized", "allow"}:
                    authorized.add(boundary)
                else:
                    authorized.discard(boundary)
            if payload.get("question") == "next_action":
                latest_next_action = record["record_id"]
        elif kind == "context":
            payload = _payload(record)
            if any(ref not in active_evidence_ids for ref in payload["evidence_refs"]):
                raise ProjectionError(f"JOURNAL-REF {record['record_id']}: context references non-prior or inactive evidence")
            contexts[payload["item_id"]] = payload["status"]
        elif kind == "reopen":
            payload = _payload(record)
            if loop_status != "completed" or payload["completion_ref"] != active_completion:
                raise ProjectionError(f"JOURNAL-REOPEN {record['record_id']}: reopen must name the active prior completion")
            counter_refs = payload["counterevidence_refs"]
            if not counter_refs or any(
                ref not in active_evidence_ids
                or ref in challenged_evidence
                or evidence[ref].get("observed_result") not in {"fail", "inconclusive"}
                or not _evidence_matches_active_check_definition(
                    ref,
                    evidence[ref],
                    nodes,
                    plan["plan_version"],
                    evidence_plan_versions,
                    evidence_check_bindings,
                    evidence_cross_plan_reusable,
                )
                for ref in counter_refs
            ):
                raise ProjectionError(f"JOURNAL-REOPEN {record['record_id']}: active prior fail/inconclusive counterevidence is required")
            if not payload["affected_criterion_refs"] or any(ref not in criteria for ref in payload["affected_criterion_refs"]):
                raise ProjectionError(f"JOURNAL-REOPEN {record['record_id']}: affected criteria must be known and non-empty")
            if any(item not in nodes for item in payload["affected_node_ids"]):
                raise ProjectionError(f"JOURNAL-REOPEN {record['record_id']}: affected nodes must exist in the active plan")
            subjects = {subject for ref in counter_refs for subject in evidence[ref]["subject_refs"]}
            required_subjects = {f"criterion:{item}" for item in payload["affected_criterion_refs"]}
            required_subjects.update(f"node:{item}" for item in payload["affected_node_ids"])
            if required_subjects - subjects:
                raise ProjectionError(f"JOURNAL-REOPEN {record['record_id']}: counterevidence does not cover {sorted(required_subjects - subjects)}")
            completion_criteria, completion_nodes = _completion_affected_refs(
                completion_records[active_completion], evidence
            )
            if not set(payload["affected_criterion_refs"]).issubset(completion_criteria):
                raise ProjectionError(
                    f"JOURNAL-REOPEN {record['record_id']}: affected criteria are not part of the completion"
                )
            if completion_nodes and not set(payload["affected_node_ids"]).issubset(completion_nodes):
                raise ProjectionError(
                    f"JOURNAL-REOPEN {record['record_id']}: affected nodes are not supported by completion evidence"
                )
            reopen_nodes.update(item for item in payload["affected_node_ids"] if states[item] == "done")
            loop_status = "active"
            active_completion = None
        elif kind == "transition":
            payload = _payload(record)
            if node_id is None:
                raise ProjectionError(f"JOURNAL-TRANSITION {record['record_id']}: node_id is required")
            before, after = payload["from"], payload["to"]
            if before not in NODE_STATES or after not in NODE_STATES or after not in TRANSITIONS[before]:
                raise ProjectionError(f"JOURNAL-TRANSITION {record['record_id']}: illegal {before!r}->{after!r}")
            if states[node_id] != before:
                raise ProjectionError(f"JOURNAL-CHAIN {record['record_id']}: expected from {states[node_id]!r}, found {before!r}")
            if loop_status == "completed":
                raise ProjectionError(f"JOURNAL-TRANSITION {record['record_id']}: completed loops must reopen first")
            if loop_status == "waiting":
                raise ProjectionError(
                    f"JOURNAL-LIFECYCLE {record['record_id']}: waiting loops must resume before node transitions"
                )
            if node_id in legacy_unverified_done and after == "closed":
                raise ProjectionError(
                    f"JOURNAL-LEGACY {record['record_id']}: unverified legacy done nodes "
                    "cannot close before fresh reverification"
                )
            required_authorizations = set(nodes[node_id]["authorization_refs"])
            if after in {"active", "verifying", "done"} and required_authorizations - authorized:
                raise ProjectionError(f"EFFECT-AUTH {record['record_id']}: node lacks active authorization {sorted(required_authorizations - authorized)}")
            refs = payload["evidence_refs"]
            decision_refs = payload["decision_refs"]
            if any(ref not in active_evidence_ids for ref in refs):
                raise ProjectionError(f"JOURNAL-REF {record['record_id']}: transition references non-prior or inactive evidence")
            if any(ref not in decisions for ref in decision_refs):
                raise ProjectionError(f"JOURNAL-REF {record['record_id']}: transition references a non-prior decision")
            failed_reviews = _active_failed_reviews(
                node_id, nodes[node_id], evidence, active_evidence_ids, challenged_evidence
            )
            checks_by_id = {check["id"]: check for check in nodes[node_id]["checks"]}
            failed_reviews = {
                ref
                for ref in failed_reviews
                if evidence[ref].get("check_ref") is None
                or (
                    evidence[ref].get("check_ref") in checks_by_id
                    and _check_evidence_matches_active_plan(
                        ref,
                        node_id,
                        checks_by_id[evidence[ref]["check_ref"]],
                        plan["plan_version"],
                        evidence_plan_versions,
                        evidence_check_bindings,
                        evidence_cross_plan_reusable,
                    )
                )
            }
            overridden_failures: set[str] = {
                decisions[ref]["overrides_evidence_ref"]
                for ref in decision_refs
                if decisions[ref].get("overrides_evidence_ref") is not None
            }
            if after in {"verifying", "done"} and failed_reviews:
                cited_override_decisions = {
                    ref
                    for ref in decision_refs
                    if decisions[ref].get("overrides_evidence_ref") is not None
                }
                if failed_reviews - overridden_failures:
                    raise ProjectionError(
                        f"EVIDENCE-OVERRIDE {record['record_id']}: transition must cite decisions "
                        f"overriding failed review evidence {sorted(failed_reviews - overridden_failures)}"
                    )
            if before == "done" and after == "active":
                if node_id in legacy_unverified_done:
                    if payload.get("reason_code") != "legacy_reverification":
                        raise ProjectionError(
                            f"JOURNAL-LEGACY {record['record_id']}: legacy done->active requires "
                            "reason_code 'legacy_reverification'"
                        )
                    if refs:
                        raise ProjectionError(
                            f"JOURNAL-LEGACY {record['record_id']}: legacy reverification starts "
                            "without treating legacy evidence as current"
                        )
                    legacy_reverification_active[node_id] = record["seq"]
                else:
                    needs_reopen, required_counterevidence = _node_reopen_requirements(
                        node_id,
                        done_evidence_by_node.get(node_id, set()),
                        evidence,
                        active_evidence_ids,
                        challenged_evidence,
                        nodes[node_id],
                        plan["plan_version"],
                        evidence_plan_versions,
                        evidence_check_bindings,
                        evidence_cross_plan_reusable,
                    )
                    if not needs_reopen:
                        raise ProjectionError(
                            f"JOURNAL-REOPEN {record['record_id']}: done->active requires current counterevidence"
                        )
                    if not required_counterevidence:
                        raise ProjectionError(
                            f"JOURNAL-REOPEN {record['record_id']}: append active node/check fail or inconclusive evidence first"
                        )
                    if not required_counterevidence.issubset(set(refs)):
                        raise ProjectionError(
                            f"JOURNAL-REOPEN {record['record_id']}: done->active must cite "
                            f"counterevidence {sorted(required_counterevidence)}"
                        )
                    reopen_nodes.discard(node_id)
                    locally_reopened_nodes.add(node_id)
            if after == "done":
                if before != "verifying":
                    raise ProjectionError(f"JOURNAL-TRANSITION {record['record_id']}: done is reachable only from verifying")
                node_definition = nodes[node_id]
                checks_by_id = {
                    check["id"]: check for check in node_definition["checks"]
                }
                check_ids = set(checks_by_id)
                if not refs or any(ref in challenged_evidence for ref in refs):
                    raise ProjectionError(f"EVIDENCE-DONE {record['record_id']}: active evidence is required")
                covered = {
                    evidence[ref].get("check_ref")
                    for ref in refs
                    if evidence[ref].get("observed_result") == "pass"
                    and f"node:{node_id}" in evidence[ref].get("subject_refs", [])
                    and evidence[ref].get("check_ref") in checks_by_id
                    and _check_evidence_matches_active_plan(
                        ref,
                        node_id,
                        checks_by_id[evidence[ref]["check_ref"]],
                        plan["plan_version"],
                        evidence_plan_versions,
                        evidence_check_bindings,
                        evidence_cross_plan_reusable,
                    )
                }
                if check_ids - covered:
                    raise ProjectionError(f"EVIDENCE-DONE {record['record_id']}: missing check evidence {sorted(check_ids - covered)}")
                active_failures = {
                    item
                    for item in active_evidence_ids
                    if evidence[item].get("observed_result") in {"fail", "inconclusive"}
                    and f"node:{node_id}" in evidence[item].get("subject_refs", [])
                    and evidence[item].get("check_ref") in check_ids
                    and _check_evidence_matches_active_plan(
                        item,
                        node_id,
                        checks_by_id[evidence[item]["check_ref"]],
                        plan["plan_version"],
                        evidence_plan_versions,
                        evidence_check_bindings,
                        evidence_cross_plan_reusable,
                    )
                    and item not in overridden_failures
                }
                if active_failures:
                    raise ProjectionError(f"EVIDENCE-DONE {record['record_id']}: unresolved failing evidence {sorted(active_failures)}")
                if node_id in legacy_reverification_active:
                    reopen_seq = legacy_reverification_active[node_id]
                    stale_refs = sorted(ref for ref in refs if evidence_seq.get(ref, 0) <= reopen_seq)
                    if stale_refs:
                        raise ProjectionError(
                            f"JOURNAL-LEGACY {record['record_id']}: legacy reverification requires "
                            f"fresh evidence recorded after done->active: {stale_refs}"
                        )
                done_evidence_by_node[node_id] = set(refs)
                if node_id in legacy_reverification_active:
                    legacy_reverification_active.pop(node_id)
                    legacy_unverified_done.discard(node_id)
            elif before == "done" and after == "active":
                done_evidence_by_node.pop(node_id, None)
            states[node_id] = after
        elif kind == "effect_pre":
            payload = _payload(record)
            key = (payload["effect_id"], payload["attempt_id"])
            if not all(isinstance(item, str) and item for item in key):
                raise ProjectionError(f"EFFECT-IDENTITY {record['record_id']}: effect_id and attempt_id must be non-empty")
            if "effects" not in set(plan["control"]["modules"]):
                raise ProjectionError(f"EFFECT-MODULE {record['record_id']}: active plan has no effects module")
            if node_id is None:
                raise ProjectionError(f"EFFECT-NODE {record['record_id']}: effect_pre requires an active-plan node_id")
            if states[node_id] != "active" or loop_status != "active":
                raise ProjectionError(
                    f"EFFECT-STATE {record['record_id']}: effect_pre requires an active node in an active loop"
                )
            if key in effect_pre:
                raise ProjectionError(f"EFFECT-DUPLICATE {record['record_id']}: duplicate effect attempt")
            boundary_ref = payload.get("authorization_boundary_ref")
            decision_ref = payload.get("authorization_decision_ref")
            node_authorizations = set(nodes[node_id]["authorization_refs"])
            if node_authorizations and boundary_ref is None:
                raise ProjectionError(f"EFFECT-AUTH {record['record_id']}: effect omits the node authorization boundary")
            if boundary_ref:
                decision = decisions.get(decision_ref)
                if boundary_ref not in node_authorizations:
                    raise ProjectionError(f"EFFECT-AUTH {record['record_id']}: boundary is not declared by the node")
                if (
                    boundary_ref not in authorized
                    or decision is None
                    or decision.get("authorization_boundary_ref") != boundary_ref
                    or decision.get("outcome") not in {"approved", "authorized", "allow"}
                ):
                    raise ProjectionError(f"EFFECT-AUTH {record['record_id']}: authorization is not active")
            elif decision_ref is not None and decision_ref not in decisions:
                raise ProjectionError(f"EFFECT-AUTH {record['record_id']}: authorization decision is not prior")
            compensation_ref = payload.get("compensation_ref")
            if compensation_ref is not None and compensation_ref not in nodes:
                raise ProjectionError(f"EFFECT-COMPENSATION {record['record_id']}: compensation_ref is not an active-plan node")
            idempotency_key = payload.get("idempotency_key")
            if idempotency_key is not None and (not isinstance(idempotency_key, str) or not idempotency_key):
                raise ProjectionError(f"EFFECT-IDENTITY {record['record_id']}: idempotency_key must be null or non-empty")
            if idempotency_key is None and compensation_ref is None:
                raise ProjectionError(f"EFFECT-COMPENSATION {record['record_id']}: non-idempotent effects require compensation_ref")
            effect_pre[key] = (record["record_id"], node_id)
        elif kind == "effect_post":
            payload = _payload(record)
            key = (payload["effect_id"], payload["attempt_id"])
            if not all(isinstance(item, str) and item for item in key):
                raise ProjectionError(f"EFFECT-IDENTITY {record['record_id']}: effect_id and attempt_id must be non-empty")
            if "effects" not in set(plan["control"]["modules"]):
                raise ProjectionError(f"EFFECT-MODULE {record['record_id']}: active plan has no effects module")
            if key not in effect_pre or key in conclusive_effect_post or effect_pre.get(key, (None, None))[1] != node_id:
                raise ProjectionError(f"EFFECT-PAIR {record['record_id']}: no unique prior effect_pre")
            if payload.get("outcome") not in {"succeeded", "failed", "cancelled", "unknown"}:
                raise ProjectionError(f"EFFECT-OUTCOME {record['record_id']}: invalid effect outcome")
            if not isinstance(payload.get("observed_postcondition"), str) or not payload["observed_postcondition"]:
                raise ProjectionError(f"EFFECT-POSTCONDITION {record['record_id']}: observed postcondition is required")
            if not isinstance(payload.get("result_ref"), str) or not payload["result_ref"]:
                raise ProjectionError(f"EFFECT-RESULT {record['record_id']}: reality result_ref is required")
            if payload["outcome"] != "unknown":
                conclusive_effect_post.add(key)
        elif kind == "loop_lifecycle":
            payload = _payload(record)
            if (
                payload["from"] != loop_status
                or payload["to"] not in {"active", "waiting", "closed"}
                or loop_status == "closed"
                or (loop_status == "completed" and payload["to"] != "closed")
            ):
                raise ProjectionError(f"JOURNAL-LIFECYCLE {record['record_id']}: illegal lifecycle chain")
            if any(ref not in seen_record_ids for ref in payload["refs"]):
                raise ProjectionError(f"JOURNAL-REF {record['record_id']}: lifecycle refs must be prior records")
            if payload["to"] == "closed":
                in_doubt_effects = sorted(
                    f"{effect_id}:{attempt_id}"
                    for effect_id, attempt_id in effect_pre.keys() - conclusive_effect_post
                )
                if in_doubt_effects:
                    raise ProjectionError(
                        f"EFFECT-LIFECYCLE {record['record_id']}: resolve in-doubt effects "
                        f"before closing the loop: {in_doubt_effects}"
                    )
            loop_status = payload["to"]
        elif kind == "completion":
            payload = _payload(record)
            if loop_status in {"closed", "completed"}:
                raise ProjectionError(f"JOURNAL-COMPLETION {record['record_id']}: loop must be active or waiting")
            if legacy_unverified_done:
                raise ProjectionError(
                    f"JOURNAL-LEGACY {record['record_id']}: legacy done nodes require fresh "
                    f"reverification before completion: {sorted(legacy_unverified_done)}"
                )
            mapped = set(payload["criterion_evidence"])
            if criteria != mapped:
                raise ProjectionError(f"JOURNAL-COMPLETION {record['record_id']}: every criterion must be mapped exactly")
            refs = [ref for values in payload["criterion_evidence"].values() for ref in values]
            if not refs or any(
                ref not in active_evidence_ids
                or ref in challenged_evidence
                or evidence[ref].get("observed_result") != "pass"
                or not _evidence_matches_active_check_definition(
                    ref,
                    evidence[ref],
                    nodes,
                    plan["plan_version"],
                    evidence_plan_versions,
                    evidence_check_bindings,
                    evidence_cross_plan_reusable,
                )
                for ref in refs
            ):
                raise ProjectionError(f"JOURNAL-COMPLETION {record['record_id']}: active evidence is required")
            for criterion_id, criterion_refs in payload["criterion_evidence"].items():
                if not criterion_refs or any(f"criterion:{criterion_id}" not in evidence[ref].get("subject_refs", []) for ref in criterion_refs):
                    raise ProjectionError(f"JOURNAL-COMPLETION {record['record_id']}: criterion evidence is not tied to {criterion_id}")
                conflicts = {
                    ref
                    for ref in active_evidence_ids
                    if f"criterion:{criterion_id}" in evidence[ref].get("subject_refs", [])
                    and evidence[ref].get("observed_result") in {"fail", "inconclusive"}
                    and _evidence_matches_active_check_definition(
                        ref,
                        evidence[ref],
                        nodes,
                        plan["plan_version"],
                        evidence_plan_versions,
                        evidence_check_bindings,
                        evidence_cross_plan_reusable,
                    )
                }
                if conflicts:
                    raise ProjectionError(f"JOURNAL-COMPLETION {record['record_id']}: unresolved criterion evidence {sorted(conflicts)}")
            review_refs = list(payload.get("counterexample_review_refs", []))
            if payload.get("system_review_ref") is not None:
                review_refs.append(payload["system_review_ref"])
            deterministic_refs = payload.get("deterministic_check_refs", [])
            if any(
                ref not in active_evidence_ids
                or evidence[ref].get("observed_result") != "pass"
                or not _evidence_matches_active_check_definition(
                    ref,
                    evidence[ref],
                    nodes,
                    plan["plan_version"],
                    evidence_plan_versions,
                    evidence_check_bindings,
                    evidence_cross_plan_reusable,
                )
                for ref in deterministic_refs + review_refs
            ):
                raise ProjectionError(f"JOURNAL-COMPLETION {record['record_id']}: check/review refs need active prior passing evidence")
            if "independent_review" in set(plan["control"]["modules"]):
                if not review_refs or any(evidence[ref].get("review_context") is None for ref in review_refs):
                    raise ProjectionError(f"EVIDENCE-REVIEW {record['record_id']}: completion lacks declared independent review evidence")
            declared_outputs = {
                output["path"]
                for node in nodes.values()
                for output in node["outputs"]
            }
            delivered_paths: set[str] = set()
            for item in payload["deliverables"]:
                if not isinstance(item, dict) or set(item) - {"path", "sha256"} or "path" not in item:
                    raise ProjectionError(f"JOURNAL-COMPLETION {record['record_id']}: deliverables need path and optional sha256")
                path_value = item["path"]
                if path_value not in declared_outputs or path_value in delivered_paths:
                    raise ProjectionError(f"JOURNAL-COMPLETION {record['record_id']}: deliverable is duplicate or not declared: {path_value!r}")
                delivered_paths.add(path_value)
                if not safe_relative_path(path_value):
                    raise ProjectionError(f"JOURNAL-COMPLETION {record['record_id']}: unsafe deliverable path")
                workspace = workspace_root(loop_dir).resolve()
                workspace_path = workspace / Path(path_value)
                try:
                    resolved_deliverable = workspace_path.resolve(strict=True)
                except OSError:
                    raise ProjectionError(f"JOURNAL-COMPLETION {record['record_id']}: deliverable is missing: {path_value!r}")
                try:
                    resolved_deliverable.relative_to(workspace)
                except ValueError as exc:
                    raise ProjectionError(
                        f"JOURNAL-COMPLETION {record['record_id']}: deliverable resolved path escapes the workspace: {path_value!r}"
                    ) from exc
                if not (resolved_deliverable.is_file() or resolved_deliverable.is_dir()):
                    raise ProjectionError(f"JOURNAL-COMPLETION {record['record_id']}: deliverable is missing: {path_value!r}")
                if item.get("sha256") is not None and (
                    not resolved_deliverable.is_file()
                    or file_sha256(resolved_deliverable) != item["sha256"]
                ):
                    raise ProjectionError(f"JOURNAL-COMPLETION {record['record_id']}: deliverable hash mismatch: {path_value!r}")
            if declared_outputs - delivered_paths:
                raise ProjectionError(f"JOURNAL-COMPLETION {record['record_id']}: declared deliverables missing {sorted(declared_outputs - delivered_paths)}")
            decision_refs = payload.get("authorization_decision_refs", [])
            if any(ref not in decisions for ref in decision_refs):
                raise ProjectionError(f"JOURNAL-COMPLETION {record['record_id']}: unknown authorization decision")
            for boundary in goal.get("authorization_boundaries", []):
                boundary_id = boundary["id"]
                if boundary_id in authorized and not any(
                    decisions[ref].get("authorization_boundary_ref") == boundary_id
                    and decisions[ref].get("outcome") in {"approved", "authorized", "allow"}
                    for ref in decision_refs
                ):
                    raise ProjectionError(f"JOURNAL-COMPLETION {record['record_id']}: active authorization {boundary_id} is not cited")
            if effect_pre.keys() - conclusive_effect_post:
                raise ProjectionError(f"JOURNAL-COMPLETION {record['record_id']}: in-doubt effects remain")
            pending_auth = {
                ref
                for current_node_id, node in nodes.items()
                if states[current_node_id] not in {"done", "closed"}
                for ref in node["authorization_refs"]
                if ref not in authorized
            }
            if pending_auth:
                raise ProjectionError(f"JOURNAL-COMPLETION {record['record_id']}: pending authorization remains {sorted(pending_auth)}")
            completion_records[record["record_id"]] = payload
            active_completion = record["record_id"]
            loop_status = "completed"
        seen_record_ids.add(record["record_id"])

    if plan is None or plan_path is None or plan_hash is None:
        raise ProjectionError("JOURNAL-PLAN no active plan at journal tail")
    if plan.get("control", {}).get("mode") not in {"persistent", "governed"}:
        raise ProjectionError("JOURNAL-MODE active journal plan must be persistent or governed")
    tail = records[-1]
    tail_record_time = _parse_time(tail["ts"], tail["record_id"])
    if projection_time < tail_record_time:
        raise ProjectionError("JOURNAL-TIME generated_at cannot precede the journal tail")
    tail_time = projection_time
    final_active_evidence, final_challenged_evidence = _current_evidence_state(
        evidence,
        evidence_seq,
        evidence_relations,
        tail_time,
        nodes,
        plan["plan_version"],
        evidence_plan_versions,
        evidence_check_bindings,
        evidence_cross_plan_reusable,
    )
    if active_completion is not None:
        completion_payload = completion_records[active_completion]
        cited = _completion_evidence_refs(completion_payload)
        current_counterevidence = _current_completion_counterevidence(
            completion_payload,
            evidence,
            final_active_evidence,
            final_challenged_evidence,
            nodes,
            plan["plan_version"],
            evidence_plan_versions,
            evidence_check_bindings,
            evidence_cross_plan_reusable,
        )
        if (
            current_counterevidence
            or any(
                ref not in final_active_evidence or ref in final_challenged_evidence
                for ref in cited
            )
        ):
            raise ProjectionError("JOURNAL-REOPEN active completion was invalidated, challenged, or expired without an explicit reopen")
    if reopen_nodes:
        raise ProjectionError(f"JOURNAL-REOPEN affected done nodes were not reopened: {sorted(reopen_nodes)}")
    stale_done_nodes = sorted(
        node_id
        for node_id, refs in done_evidence_by_node.items()
        if states.get(node_id) == "done"
        and _node_reopen_requirements(
            node_id,
            refs,
            evidence,
            final_active_evidence,
            final_challenged_evidence,
            nodes[node_id],
            plan["plan_version"],
            evidence_plan_versions,
            evidence_check_bindings,
            evidence_cross_plan_reusable,
        )[0]
    )
    if stale_done_nodes:
        raise ProjectionError(
            "JOURNAL-REOPEN done-node evidence is stale or contradicted without "
            f"a node-local reopen: {stale_done_nodes}"
        )
    stale_reopened_nodes = sorted(
        node_id
        for node_id in locally_reopened_nodes
        if states.get(node_id) == "done"
        and _node_reopen_requirements(
            node_id,
            done_evidence_by_node.get(node_id, set()),
            evidence,
            final_active_evidence,
            final_challenged_evidence,
            nodes[node_id],
            plan["plan_version"],
            evidence_plan_versions,
            evidence_check_bindings,
            evidence_cross_plan_reusable,
        )[0]
    )
    if stale_reopened_nodes:
        raise ProjectionError(
            "JOURNAL-REOPEN reopened nodes returned to done while counterevidence remains current: "
            f"{stale_reopened_nodes}"
        )
    states = {node_id: states[node_id] for node_id in nodes}
    ready = sorted(node_id for node_id, node in nodes.items() if states[node_id] == "pending" and all(states.get(dep) == "done" for dep in node["depends_on"]))
    pending_auth = sorted({ref for node_id, node in nodes.items() if states[node_id] not in {"done", "closed"} for ref in node["authorization_refs"] if ref not in authorized})
    in_doubt = sorted(f"{effect_id}:{attempt_id}" for effect_id, attempt_id in effect_pre.keys() - conclusive_effect_post)
    projected_active_evidence = {
        ref
        for ref in final_active_evidence
        if _evidence_matches_active_check_definition(
            ref,
            evidence[ref],
            nodes,
            plan["plan_version"],
            evidence_plan_versions,
            evidence_check_bindings,
            evidence_cross_plan_reusable,
        )
    }
    projected_challenged_evidence = final_challenged_evidence & projected_active_evidence
    current_evidence = _current_evidence_by_subject(
        evidence, projected_active_evidence, projected_challenged_evidence
    )
    confirmed_evidence = sorted(
        ref
        for ref in projected_active_evidence
        if ref not in projected_challenged_evidence
        and evidence[ref].get("observed_result") == "pass"
    )
    return {
        "schema_version": "2.0",
        "loop_id": goal["loop_id"],
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": {"goal_sha256": goal_hash, "plan_version": plan["plan_version"], "plan_sha256": plan_hash, "journal_last_seq": tail["seq"], "journal_tail_id": tail["record_id"]},
        "projection": {
            "loop_status": loop_status, "node_states": states, "ready_nodes": ready,
            "active_nodes": sorted(key for key, value in states.items() if value in {"active", "verifying"}),
            "waiting_nodes": sorted(key for key, value in states.items() if value == "waiting"),
            "current_evidence_refs": current_evidence,
            "open_context_ids": sorted(key for key, value in contexts.items() if value == "open"),
            "pending_authorization_refs": pending_auth, "in_doubt_effect_ids": in_doubt,
        },
        "recovery_refs": {"confirmed_evidence": confirmed_evidence, "recent_records": [item["record_id"] for item in records[-10:]], "latest_next_action_decision": latest_next_action},
    }
