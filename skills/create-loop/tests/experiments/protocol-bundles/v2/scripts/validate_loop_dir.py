#!/usr/bin/env python3
"""Validate a complete create-loop v2 directory without runtime dependencies."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_loop import canonical_output_path, output_path_identity, ProjectionError, confined_file, file_sha256, load_journal, project, workspace_root
from schema_runtime import SchemaError, load_json, validate

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "schemas"
V1_CORE_ARTIFACTS = (
    "loop.plan.yaml",
    "loop.meta.yaml",
    "loop.state.yaml",
    "checkpoint.yaml",
    "evidence.ledger.yaml",
    "event_log.jsonl",
)


def _schema_errors(value: Any, name: str) -> list[str]:
    return [f"SCHEMA-{name.upper()} {message}" for message in validate(value, load_json(SCHEMAS / f"{name}.schema.json"))]


def _unique(items: list[dict[str, Any]], key: str, label: str, errors: list[str]) -> None:
    values = [item.get(key) for item in items]
    if len(values) != len(set(values)):
        errors.append(f"GRAPH-UNIQUE duplicate {label}")


def _parse_rfc3339(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_graph(goal: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    criteria = {item["id"] for item in goal.get("success_criteria", []) if isinstance(item, dict) and "id" in item}
    boundaries = {item["id"] for item in goal.get("authorization_boundaries", []) if isinstance(item, dict) and "id" in item}
    nodes = plan.get("nodes", []) if isinstance(plan.get("nodes"), list) else []
    _unique(goal.get("success_criteria", []), "id", "success criterion id", errors)
    _unique(goal.get("constraints", []), "id", "constraint id", errors)
    _unique(goal.get("authorization_boundaries", []), "id", "authorization boundary id", errors)
    _unique(nodes, "id", "node id", errors)
    node_ids = {node.get("id") for node in nodes if isinstance(node, dict)}
    children = 0
    output_owners: dict[str, str] = {}
    for node in nodes:
        node_id = node.get("id", "<unknown>")
        checks = node.get("checks", []) if isinstance(node.get("checks"), list) else []
        _unique(checks, "id", f"check id in {node_id}", errors)
        for dep in node.get("depends_on", []):
            if dep not in node_ids:
                errors.append(f"GRAPH-DANGLING {node_id}: unknown dependency {dep!r}")
            if dep == node_id:
                errors.append(f"GRAPH-CYCLE {node_id}: self dependency")
        for ref in node.get("success_criteria_refs", []):
            if ref not in criteria:
                errors.append(f"GRAPH-CRITERION {node_id}: unknown criterion {ref!r}")
        for ref in node.get("authorization_refs", []):
            if ref not in boundaries:
                errors.append(f"GRAPH-AUTH {node_id}: unknown authorization boundary {ref!r}")
        for output in node.get("outputs", []):
            path = output.get("path") if isinstance(output, dict) else None
            try:
                canonical = canonical_output_path(path)
            except (ProjectionError, TypeError):
                errors.append(f"GRAPH-PATH {node_id}: output path must stay relative to the workspace")
                continue
            if path != canonical:
                errors.append(f"GRAPH-PATH {node_id}: output path must use canonical form {canonical!r}")
                continue
            identity = output_path_identity(canonical)
            owner = output_owners.get(identity)
            if owner is not None:
                errors.append(f"GRAPH-UNIQUE duplicate output path {path!r} in {owner} and {node_id}")
            else:
                output_owners[identity] = node_id
        if "child_loop" in node:
            children += 1
            child = node.get("child_loop")
            if not isinstance(child, dict):
                continue
            return_criteria = child.get("return_criteria_refs", [])
            for ref in return_criteria if isinstance(return_criteria, list) else []:
                if ref not in criteria:
                    errors.append(f"CHILD-CRITERION {node_id}: unknown return criterion {ref!r}")
                if ref not in node.get("success_criteria_refs", []):
                    errors.append(f"CHILD-CRITERION {node_id}: return criterion {ref!r} is not assigned to the parent node")
            output_paths: set[str] = set()
            for output in node.get("outputs", []):
                output_path = output.get("path") if isinstance(output, dict) else None
                if not isinstance(output_path, str):
                    continue
                try:
                    canonical_output = canonical_output_path(output_path)
                except ProjectionError:
                    continue
                if output_path == canonical_output:
                    output_paths.add(output_path_identity(canonical_output))
            return_deliverables = child.get("return_deliverables", [])
            for return_path in return_deliverables if isinstance(return_deliverables, list) else []:
                if not isinstance(return_path, str):
                    errors.append(f"CHILD-PATH {node_id}: return deliverable path must stay relative to the workspace")
                else:
                    try:
                        canonical_return = canonical_output_path(return_path)
                    except ProjectionError:
                        errors.append(f"CHILD-PATH {node_id}: return deliverable path must stay relative to the workspace")
                        continue
                    if return_path != canonical_return:
                        errors.append(f"CHILD-PATH {node_id}: return deliverable must use canonical form {canonical_return!r}")
                    elif output_path_identity(canonical_return) not in output_paths:
                        errors.append(f"CHILD-OUTPUT {node_id}: return deliverable {return_path!r} is not declared in node outputs")
    modules = set(plan.get("control", {}).get("modules", []))
    if modules and plan.get("control", {}).get("mode") != "governed":
        errors.append("JOURNAL-MODE optional modules require governed mode")
    if children and "children" not in modules:
        errors.append("CHILD-MODULE child_loop requires the children module")
    if "children" in modules and not children:
        errors.append("CHILD-MODULE children module is enabled but no child_loop is declared")

    visiting: set[str] = set()
    visited: set[str] = set()
    deps = {node["id"]: node.get("depends_on", []) for node in nodes if isinstance(node, dict) and "id" in node}

    def walk(node_id: str) -> None:
        if node_id in visiting:
            errors.append(f"GRAPH-CYCLE dependency cycle includes {node_id}")
            return
        if node_id in visited:
            return
        visiting.add(node_id)
        for dep in deps.get(node_id, []):
            if dep in deps:
                walk(dep)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in deps:
        walk(node_id)
    return errors


def validate_journal_payloads(records: list[dict[str, Any]], plans: dict[int, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    evidence_ids: set[str] = set()
    record_ids: set[str] = set()
    relation_edges: dict[str, set[str]] = {}
    active_plan: dict[str, Any] | None = None
    lightweight_upgrade_evidence: str | None = None
    lightweight_upgrade_decision: str | None = None
    for record in records:
        kind = record.get("kind")
        payload = record.get("payload")
        if not isinstance(kind, str) or not isinstance(payload, dict):
            continue
        if kind == "plan_activated":
            previous_mode = (active_plan or {}).get("control", {}).get("mode")
            if previous_mode == "lightweight":
                if (
                    plans.get(record.get("plan_version"), {}).get("control", {}).get("mode")
                    not in {"persistent", "governed"}
                    or payload.get("evidence_refs") != [lightweight_upgrade_evidence]
                    or payload.get("decision_ref") != lightweight_upgrade_decision
                    or next(
                        (
                            prior.get("payload", {}).get("outcome")
                            for prior in records
                            if prior.get("record_id") == lightweight_upgrade_decision
                        ),
                        None,
                    )
                    != plans.get(record.get("plan_version"), {}).get("control", {}).get("mode")
                ):
                    errors.append(
                        f"JOURNAL-MODE {record.get('record_id')}: lightweight upgrade must consume "
                        "the immediately preceding upgrade evidence and decision"
                    )
            active_plan = plans.get(record.get("plan_version"))
            lightweight_upgrade_evidence = None
            lightweight_upgrade_decision = None
        modules = set((active_plan or {}).get("control", {}).get("modules", []))
        if active_plan is not None and active_plan.get("control", {}).get("mode") == "lightweight" and kind != "plan_activated":
            if kind == "evidence":
                if (
                    lightweight_upgrade_evidence is not None
                    or lightweight_upgrade_decision is not None
                    or record.get("node_id") is not None
                    or payload.get("subject_refs") != ["loop:control_mode"]
                    or payload.get("source_class") != "control_trigger"
                    or payload.get("check_ref") is not None
                    or payload.get("artifact_ref") is not None
                    or payload.get("review_context") is not None
                    or payload.get("observed_result") != "observation"
                ):
                    errors.append(
                        f"JOURNAL-MODE {record.get('record_id')}: lightweight upgrade prefix "
                        "requires one control-only observation"
                    )
                else:
                    lightweight_upgrade_evidence = record.get("record_id")
            elif kind == "decision":
                if (
                    lightweight_upgrade_evidence is None
                    or lightweight_upgrade_decision is not None
                    or record.get("node_id") is not None
                    or payload.get("question") != "control_mode_upgrade"
                    or payload.get("outcome") not in {"persistent", "governed"}
                    or payload.get("evidence_refs") != [lightweight_upgrade_evidence]
                    or payload.get("authorization_boundary_ref") is not None
                    or payload.get("overrides_evidence_ref") is not None
                    or "plan_change" not in payload
                    or payload["plan_change"] is not None
                ):
                    errors.append(
                        f"JOURNAL-MODE {record.get('record_id')}: lightweight upgrade decision "
                        "must immediately cite the upgrade observation"
                    )
                else:
                    lightweight_upgrade_decision = record.get("record_id")
            else:
                errors.append(
                    f"JOURNAL-MODE {record.get('record_id')}: lightweight history permits only "
                    "the bounded upgrade prefix before plan activation"
                )
        if kind == "evidence":
            evidence_ids.add(record["record_id"])
            if payload.get("observed_result") not in {"pass", "fail", "inconclusive", "observation"}:
                errors.append(f"EVIDENCE-RESULT {record['record_id']}: invalid observed_result")
            if not isinstance(payload.get("subject_refs"), list) or not payload.get("subject_refs"):
                errors.append(f"EVIDENCE-SUBJECT {record['record_id']}: subject_refs must be non-empty")
            if payload.get("review_context") is not None:
                review = payload["review_context"]
                required = {"manifest_ref", "manifest_sha256", "producer_conclusion_access"}
                if not isinstance(review, dict) or not required.issubset(review):
                    errors.append(f"EVIDENCE-REVIEW {record['record_id']}: incomplete review context manifest")
                if "independent_review" not in modules:
                    errors.append(f"EVIDENCE-REVIEW {record['record_id']}: review context requires the independent_review module")
            if payload.get("artifact_ref") is not None and "artifacts" not in modules:
                errors.append(f"ARTIFACT-MODULE {record['record_id']}: evidence artifact_ref requires the artifacts module")
        elif kind == "evidence_relation":
            if payload.get("relation") not in {"supersedes", "invalidates", "challenges", "confirms"}:
                errors.append(f"EVIDENCE-RELATION {record['record_id']}: invalid relation")
            relation_edges.setdefault(payload.get("source_evidence_ref"), set()).add(payload.get("target_evidence_ref"))
        elif kind in {"effect_pre", "effect_post"} and "effects" not in modules:
            errors.append(f"EFFECT-MODULE {record['record_id']}: effect records require the effects module")
        elif kind == "reopen":
            if not payload.get("affected_node_ids") or not payload.get("counterevidence_refs"):
                errors.append(f"JOURNAL-REOPEN {record['record_id']}: affected nodes and counterevidence are required")
        elif kind == "decision" and payload.get("overrides_evidence_ref"):
            if payload["overrides_evidence_ref"] not in evidence_ids:
                errors.append(f"EVIDENCE-OVERRIDE {record['record_id']}: override must reference prior evidence")
        elif kind == "decision" and payload.get("plan_change") is not None:
            change = payload["plan_change"]
            required = {
                "from_plan_version", "from_plan_sha256", "to_plan_version", "to_plan_sha256"
            }
            if payload.get("question") != "plan_replacement" or not isinstance(change, dict) or set(change) != required:
                errors.append(
                    f"JOURNAL-PLAN {record['record_id']}: plan_change requires a plan_replacement decision "
                    "with exact old/new plan version and hash fields"
                )
        record_ids.add(record.get("record_id"))

    for record in records:
        kind = record.get("kind")
        payload = record.get("payload", {})
        if kind == "plan_activated" and payload.get("previous_version") is not None:
            if not payload.get("evidence_refs") or payload.get("decision_ref") is None:
                errors.append(
                    f"JOURNAL-PLAN {record.get('record_id')}: non-initial activation "
                    "requires causal evidence and a prior decision"
                )
        if kind == "evidence_relation":
            for field in ("source_evidence_ref", "target_evidence_ref"):
                if payload.get(field) not in evidence_ids:
                    errors.append(f"EVIDENCE-REF {record.get('record_id')}: {field} references unknown evidence")
        if kind == "transition":
            for ref in payload.get("evidence_refs", []):
                if ref not in evidence_ids:
                    errors.append(f"EVIDENCE-REF {record.get('record_id')}: transition references unknown evidence")
            for ref in payload.get("decision_refs", []):
                if ref not in record_ids:
                    errors.append(f"JOURNAL-REF {record.get('record_id')}: transition references unknown decision")

    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(item: str) -> None:
        if item in visiting:
            errors.append(f"EVIDENCE-CYCLE relation cycle includes {item}")
            return
        if item in visited:
            return
        visiting.add(item)
        for target in relation_edges.get(item, set()):
            walk(target)
        visiting.remove(item)
        visited.add(item)

    for item in relation_edges:
        walk(item)
    return errors


def validate_claims(loop_dir: Path, goal: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    modules = set(plan.get("control", {}).get("modules", []))
    claim_dir = loop_dir / "claims"
    claims = list(claim_dir.glob("*.json")) if claim_dir.exists() else []
    if claims and "concurrency" not in modules:
        errors.append("CLAIM-MODULE claim files require the concurrency module")
    nodes = {node["id"] for node in plan.get("nodes", [])}
    active_claims: list[tuple[Path, dict[str, Any], set[str]]] = []
    active_nodes: set[str] = set()
    active_tokens: set[str] = set()
    now = datetime.now(timezone.utc)
    for path in claims:
        try:
            relative = path.relative_to(loop_dir).as_posix()
            claim_path = confined_file(loop_dir, relative, "CLAIM-PATH")
        except (OSError, ProjectionError, ValueError) as exc:
            errors.append(f"CLAIM-PATH {path.name}: {exc}")
            continue
        value = load_json(claim_path)
        schema_errors = validate(value, load_json(SCHEMAS / "claim-v2.schema.json"))
        errors.extend(f"SCHEMA-CLAIM {item}" for item in schema_errors)
        if schema_errors:
            continue
        node_id = value.get("node_id")
        if path.name != f"{node_id}.json":
            errors.append(f"CLAIM-FILENAME {path.name}: expected {node_id}.json")
        if value.get("loop_id") != goal.get("loop_id") or node_id not in nodes or value.get("plan_version") != plan.get("plan_version"):
            errors.append(f"CLAIM-IDENTITY {path.name}: loop, node, or plan does not match")
        try:
            acquired = _parse_rfc3339(value["acquired_at"])
            heartbeat = _parse_rfc3339(value["heartbeat_at"])
            expires = _parse_rfc3339(value["expires_at"])
            if not acquired <= heartbeat < expires:
                errors.append(f"CLAIM-TIME {path.name}: require acquired_at <= heartbeat_at < expires_at")
            if expires <= now:
                errors.append(f"CLAIM-EXPIRED {path.name}: claim is expired")
            else:
                normalized_scope: set[str] = set()
                for item in value.get("scope_paths", []):
                    if not isinstance(item, str):
                        continue
                    try:
                        canonical = canonical_output_path(item)
                    except ProjectionError:
                        continue
                    normalized_scope.add(output_path_identity(canonical))
                active_claims.append((path, value, normalized_scope))
                if node_id in active_nodes:
                    errors.append(f"CLAIM-NODE {path.name}: node {node_id!r} already has an active claim")
                elif isinstance(node_id, str):
                    active_nodes.add(node_id)
                token = value["token"]
                if token in active_tokens:
                    errors.append(f"CLAIM-TOKEN {path.name}: duplicate active claim token {token!r}")
                else:
                    active_tokens.add(token)
        except (KeyError, ValueError):
            pass
        for scope_path in value.get("scope_paths", []):
            if not isinstance(scope_path, str):
                continue
            try:
                canonical = canonical_output_path(scope_path)
            except ProjectionError:
                errors.append(f"CLAIM-PATH {path.name}: scope path must be a materializable workspace-relative path")
                continue
            normalized = scope_path.replace("\\", "/").rstrip("/")
            if normalized != canonical:
                errors.append(f"CLAIM-PATH {path.name}: scope path must use canonical form {canonical!r}")
    for index, (left_path, _left, left_scope) in enumerate(active_claims):
        for right_path, _right, right_scope in active_claims[index + 1:]:
            conflicts = sorted(
                left
                for left in left_scope
                for right in right_scope
                if left == right or left.startswith(right.rstrip("/") + "/") or right.startswith(left.rstrip("/") + "/")
            )
            if conflicts:
                errors.append(
                    f"CLAIM-OVERLAP {left_path.name}/{right_path.name}: active scope paths overlap {conflicts}"
                )
    return errors


def validate_artifacts(
    loop_dir: Path, plan: dict[str, Any]
) -> tuple[list[str], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    errors: list[str] = []
    active_artifacts: dict[str, dict[str, Any]] = {}
    index_path = loop_dir / "artifact-index.json"
    modules = set(plan.get("control", {}).get("modules", []))
    if index_path.exists() and "artifacts" not in modules:
        errors.append("ARTIFACT-MODULE artifact-index.json requires the artifacts module")
    if "artifacts" in modules and not index_path.exists():
        errors.append("ARTIFACT-MODULE artifacts module requires artifact-index.json")
        return errors, {}, active_artifacts
    if not index_path.exists():
        return errors, {}, active_artifacts
    index = load_json(index_path)
    schema_errors = validate(index, load_json(SCHEMAS / "artifact-index-v2.schema.json"))
    errors.extend(f"SCHEMA-ARTIFACT {item}" for item in schema_errors)
    if schema_errors:
        return errors, {}, active_artifacts
    ids: set[str] = set()
    path_owners: dict[str, tuple[str, str]] = {}
    items_by_id: dict[str, dict[str, Any]] = {}
    items_by_name: dict[str, list[dict[str, Any]]] = {}
    for item in index.get("artifacts", []):
        artifact_id = item.get("artifact_id")
        if artifact_id in ids:
            errors.append(f"ARTIFACT-ID duplicate artifact_id {artifact_id!r}")
        ids.add(artifact_id)
        items_by_id[artifact_id] = item
        items_by_name.setdefault(item["logical_name"], []).append(item)
        if item.get("status") == "active":
            if item.get("logical_name") in active_artifacts:
                errors.append(f"ARTIFACT-ACTIVE multiple active versions for {item.get('logical_name')!r}")
            active_artifacts[item["logical_name"]] = item
        relative = item.get("path")
        try:
            canonical = canonical_output_path(relative)
        except (ProjectionError, TypeError):
            errors.append(f"ARTIFACT-PATH {artifact_id}: path must be a materializable workspace-relative path")
            continue
        if relative != canonical:
            errors.append(f"ARTIFACT-PATH {artifact_id}: path must use canonical form {canonical!r}")
            continue
        identity = output_path_identity(canonical)
        owner = path_owners.get(identity)
        if owner is not None:
            errors.append(f"ARTIFACT-PATH {artifact_id}: path collides with artifact {owner[1]!r}")
        else:
            path_owners[identity] = (item["logical_name"], artifact_id)
        path = workspace_root(loop_dir) / Path(canonical)
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(workspace_root(loop_dir))
        except (OSError, ValueError):
            errors.append(f"ARTIFACT-PATH {artifact_id}: resolved path escapes workspace")
            continue
        if not resolved.is_file() or file_sha256(resolved) != item.get("sha256"):
            errors.append(f"ARTIFACT-HASH {artifact_id}: file missing or hash mismatch")
    for logical_name, items in items_by_name.items():
        versions = [item["version"] for item in items]
        if len(versions) != len(set(versions)):
            errors.append(f"ARTIFACT-VERSION {logical_name!r} has duplicate versions")
        if sorted(set(versions)) != list(range(1, max(versions) + 1)):
            errors.append(f"ARTIFACT-VERSION {logical_name!r} versions must be contiguous from 1")
        active = [item for item in items if item["status"] == "active"]
        if len(active) != 1:
            errors.append(f"ARTIFACT-ACTIVE {logical_name!r} must have exactly one active version")
        elif active[0]["version"] != max(versions):
            errors.append(f"ARTIFACT-ACTIVE {logical_name!r} active artifact must be the highest version")

    edges: dict[str, str] = {}
    for artifact_id, item in items_by_id.items():
        predecessor_id = item.get("supersedes_id")
        if item["version"] == 1 and predecessor_id is not None:
            errors.append(f"ARTIFACT-CHAIN {artifact_id}: version 1 must not supersede another artifact")
        elif item["version"] > 1 and predecessor_id is None:
            errors.append(f"ARTIFACT-CHAIN {artifact_id}: version {item['version']} requires a predecessor")
        if predecessor_id is None:
            continue
        edges[artifact_id] = predecessor_id
        predecessor = items_by_id.get(predecessor_id)
        if predecessor is None:
            errors.append(f"ARTIFACT-REF {artifact_id}: unknown supersedes_id {predecessor_id!r}")
        elif predecessor.get("logical_name") != item.get("logical_name") or predecessor.get("version") != item.get("version") - 1:
            errors.append(f"ARTIFACT-CHAIN {artifact_id}: predecessor must share logical_name and be exactly version {item['version'] - 1}")

    for artifact_id in edges:
        seen: set[str] = set()
        current = artifact_id
        while current in edges:
            if current in seen:
                errors.append(f"ARTIFACT-CYCLE supersedes chain includes {current!r}")
                break
            seen.add(current)
            current = edges[current]
    active_by_id = {item["artifact_id"]: item for item in active_artifacts.values()}
    return errors, items_by_id, active_by_id


def validate_evidence_artifacts(
    loop_dir: Path,
    records: list[dict[str, Any]],
    registered_artifacts: dict[str, dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    for record in records:
        if record.get("kind") != "evidence" or not isinstance(record.get("payload"), dict):
            continue
        artifact_ref = record["payload"].get("artifact_ref")
        if artifact_ref is None:
            continue
        binding = record["payload"].get("artifact_binding")
        registered = registered_artifacts.get(artifact_ref)
        if registered is None and (loop_dir / "artifact-index.json").exists():
            errors.append(
                f"ARTIFACT-EVIDENCE {record.get('record_id')}: artifact_ref must "
                "name a registry artifact while the index is present"
            )
        elif registered is not None and binding != {
            "path": registered.get("path"),
            "sha256": registered.get("sha256"),
        }:
            errors.append(
                f"ARTIFACT-EVIDENCE {record.get('record_id')}: artifact_binding "
                "does not match the registry artifact"
            )
        if not isinstance(binding, dict):
            continue
        try:
            canonical = canonical_output_path(binding.get("path"))
            if binding.get("path") != canonical:
                raise ProjectionError("non-canonical artifact binding path")
            path = workspace_root(loop_dir) / Path(canonical)
            resolved = path.resolve(strict=True)
            resolved.relative_to(workspace_root(loop_dir))
            if not resolved.is_file() or file_sha256(resolved) != binding.get("sha256"):
                raise ProjectionError("file missing or hash mismatch")
        except (OSError, ProjectionError, TypeError, ValueError):
            errors.append(
                f"ARTIFACT-EVIDENCE {record.get('record_id')}: bound artifact "
                "file is missing or hash mismatched"
            )
    return errors


def _child_candidates(parent: Path, loop_id: str) -> list[Path]:
    candidates: list[Path] = []
    child_root = parent / "_loops"
    if not child_root.exists():
        return candidates
    try:
        parent_root = parent.resolve(strict=True)
        child_root_resolved = child_root.resolve(strict=True)
        child_root_resolved.relative_to(parent_root)
    except (OSError, ValueError) as exc:
        raise ProjectionError("CHILD-PATH _loops directory escapes the parent Loop") from exc
    if not child_root_resolved.is_dir():
        raise ProjectionError("CHILD-PATH _loops must be a directory")
    for child_dir in child_root.iterdir():
        if not child_dir.is_dir():
            continue
        try:
            child_dir.resolve(strict=True).relative_to(child_root_resolved)
        except (OSError, ValueError) as exc:
            raise ProjectionError(f"CHILD-PATH child directory escapes _loops: {child_dir.name!r}") from exc
        goal_path = child_dir / "goal.json"
        if not goal_path.is_file():
            continue
        try:
            goal = load_json(confined_file(child_dir, "goal.json", "CHILD-PATH"))
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise ProjectionError(
                f"CHILD-PATH cannot read materialized child goal {child_dir.name!r}"
            ) from exc
        if not isinstance(goal, dict):
            raise ProjectionError(
                f"CHILD-PATH materialized child goal must be an object: {child_dir.name!r}"
            )
        if goal.get("loop_id") == loop_id:
            candidates.append(child_dir)
    return candidates


def validate_module_contracts(
    loop_dir: Path,
    goal: dict[str, Any],
    plan: dict[str, Any],
    projection: dict[str, Any] | None,
    visited: set[Path],
) -> list[str]:
    errors: list[str] = []
    modules = set(plan.get("control", {}).get("modules", []))
    if "children" in modules:
        projected = projection.get("projection", {}) if projection is not None else {}
        node_states = projected.get("node_states", {})
        parent_completed = projected.get("loop_status") == "completed"
        for node in plan.get("nodes", []):
            child = node.get("child_loop")
            if not child:
                continue
            return_required = parent_completed or node_states.get(node["id"]) == "done"
            try:
                candidates = _child_candidates(loop_dir, child["loop_id"])
            except ProjectionError as exc:
                errors.append(f"CHILD-RETURN {node['id']}: {exc}")
                continue
            if not candidates:
                if return_required:
                    errors.append(f"CHILD-RETURN {node['id']}: child loop {child['loop_id']} has not returned")
                continue
            if len(candidates) > 1:
                errors.append(f"CHILD-RETURN {node['id']}: child loop {child['loop_id']} must resolve to exactly one directory under _loops by goal.loop_id")
                continue
            child_dir = candidates[0]
            child_resolved = child_dir.resolve()
            if child_resolved in visited:
                errors.append(f"CHILD-RETURN {node['id']}: child validation cycle detected")
                continue
            completion = child_dir / "journal.jsonl"
            if not completion.is_file():
                if return_required:
                    errors.append(f"CHILD-RETURN {node['id']}: child loop {child['loop_id']} has no completion journal")
                continue
            try:
                child_errors = validate_loop_dir(child_dir, _visited=visited)
                if child_errors:
                    detail = "; ".join(child_errors[:3])
                    errors.append(f"CHILD-RETURN {node['id']}: child whole-loop validation failed ({detail})")
                    continue
                child_goal = load_json(child_dir / "goal.json")
                child_records = load_journal(completion)
                child_projection = project(child_dir)
            except (OSError, json.JSONDecodeError, ProjectionError, SchemaError, AttributeError, TypeError, ValueError) as exc:
                errors.append(f"CHILD-RETURN {node['id']}: cannot read child loop ({exc})")
                continue
            origin = child_goal.get("origin", {})
            if origin.get("parent_loop_id") != goal.get("loop_id") or origin.get("parent_node_id") != node["id"]:
                errors.append(f"CHILD-RETURN {node['id']}: child origin does not point back to the parent contract")
            child_completed = child_projection["projection"]["loop_status"] == "completed"
            if not child_completed:
                if return_required:
                    errors.append(f"CHILD-RETURN {node['id']}: child is not currently completed")
                continue
            completion_records = [record for record in child_records if record.get("kind") == "completion"]
            completion_payload = completion_records[-1]["payload"]
            expected_criteria = set(child.get("return_criteria_refs", []))
            if not expected_criteria.issubset(set(completion_payload.get("criterion_evidence", {}))):
                errors.append(f"CHILD-RETURN {node['id']}: child completion does not cover the return criteria")
            returned: set[str] = set()
            for item in completion_payload.get("deliverables", []):
                if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                    continue
                try:
                    returned.add(output_path_identity(item["path"]))
                except ProjectionError:
                    continue
            expected_returns = {output_path_identity(path) for path in child.get("return_deliverables", [])}
            if not expected_returns.issubset(returned):
                errors.append(f"CHILD-RETURN {node['id']}: child completion does not return the declared deliverables")
    return errors


def validate_loop_dir(loop_dir: Path, *, _visited: set[Path] | None = None) -> list[str]:
    errors: list[str] = []
    visited = set() if _visited is None else set(_visited)
    try:
        resolved_loop_dir = loop_dir.resolve(strict=True)
        if resolved_loop_dir in visited:
            return ["CHILD-RETURN child validation cycle detected"]
        visited.add(resolved_loop_dir)
        mixed = [name for name in V1_CORE_ARTIFACTS if (loop_dir / name).exists()]
        if mixed:
            return [f"GRAPH-PROTOCOL v2 loop contains legacy v1 core artifacts: {', '.join(mixed)}"]
        goal_path = confined_file(loop_dir, "goal.json", "GRAPH-GOAL")
        goal = load_json(goal_path)
        errors.extend(_schema_errors(goal, "goal"))
        goal_hash = file_sha256(goal_path)
        journal_path = loop_dir / "journal.jsonl"
        if not journal_path.exists():
            plans = sorted((loop_dir / "plans").glob("plan-v*.json"))
            if len(plans) != 1 or plans[0].name != "plan-v1.json":
                return errors + ["GRAPH-PLAN lightweight loops require exactly plans/plan-v1.json"]
            path = confined_file(loop_dir, "plans/plan-v1.json", "GRAPH-PLAN")
            value = load_json(path)
            errors.extend(_schema_errors(value, "plan"))
            errors.extend(validate_graph(goal, value))
            if value.get("plan_version") != 1:
                errors.append("GRAPH-PLAN plan-v1.json: filename/version mismatch")
            if value.get("goal_sha256") != goal_hash:
                errors.append("GRAPH-GOAL plan-v1.json: goal_sha256 does not match goal.json")
            if value.get("control", {}).get("mode") != "lightweight":
                errors.append("JOURNAL-MISSING persistent/governed loops require journal.jsonl")
            if (loop_dir / "resume.json").exists():
                errors.append("JOURNAL-MODE lightweight loops must not have resume.json")
            if value.get("control", {}).get("modules"):
                errors.append("JOURNAL-MODE lightweight loops must not enable optional modules")
            errors.extend(validate_claims(loop_dir, goal, value))
            artifact_errors, _, _ = validate_artifacts(loop_dir, value)
            errors.extend(artifact_errors)
            return errors
        if not journal_path.is_file():
            return errors + ["JOURNAL-MISSING journal.jsonl is not a file"]
        journal_path = confined_file(loop_dir, "journal.jsonl", "JOURNAL")
        records = load_journal(journal_path)
        journal_schema = load_json(SCHEMAS / "journal-record.schema.json")
        for record in records:
            errors.extend(f"SCHEMA-JOURNAL {item}" for item in validate(record, journal_schema))
        activation_records = [record for record in records if record.get("kind") == "plan_activated"]
        if not activation_records:
            return errors + ["JOURNAL-PLAN no plan_activated record"]
        activated_paths: list[Path] = []
        for record in activation_records:
            payload = record.get("payload")
            ref = payload.get("plan_ref") if isinstance(payload, dict) else None
            if not isinstance(ref, str):
                continue
            try:
                path = confined_file(loop_dir, ref, "JOURNAL-PLAN")
            except ProjectionError as exc:
                errors.append(str(exc))
                continue
            if path not in activated_paths:
                activated_paths.append(path)
        if not activated_paths:
            return errors + ["JOURNAL-PLAN no readable activated plan file"]
        plan_values: list[tuple[Path, dict[str, Any]]] = []
        for path in activated_paths:
            match = re.fullmatch(r"plan-v([1-9][0-9]*)\.json", path.name)
            if match is None:
                errors.append(f"GRAPH-PLAN invalid plan filename {path.name!r}")
            value = load_json(path)
            plan_values.append((path, value))
            errors.extend(_schema_errors(value, "plan"))
            errors.extend(validate_graph(goal, value))
            if match is not None and value.get("plan_version") != int(match.group(1)):
                errors.append(f"GRAPH-PLAN {path.name}: filename/version mismatch")
            if value.get("goal_sha256") != goal_hash:
                errors.append(f"GRAPH-GOAL {path.name}: goal_sha256 does not match goal.json")
        versions = [value.get("plan_version") for _, value in plan_values]
        if len(versions) != len(set(versions)):
            errors.append("GRAPH-PLAN duplicate plan_version")
        latest_path, latest_plan = max(plan_values, key=lambda item: item[1].get("plan_version", 0))
        activation_versions = [record.get("plan_version") for record in activation_records]
        active_version = activation_versions[-1] if activation_versions else None
        active_matches = [(path, value) for path, value in plan_values if value.get("plan_version") == active_version]
        if len(active_matches) != 1:
            errors.append("JOURNAL-PLAN latest activation does not select exactly one immutable plan")
            current_plan = latest_plan
        else:
            _, current_plan = active_matches[0]
        plans_by_version = {value.get("plan_version"): value for _, value in plan_values}
        errors.extend(validate_journal_payloads(records, plans_by_version))
        projected: dict[str, Any] | None = None
        if not errors:
            try:
                projected = project(loop_dir)
            except (OSError, ProjectionError, AttributeError, KeyError, TypeError, ValueError) as exc:
                errors.append(f"JOURNAL-PROJECTION {exc}")
        if projected is not None:
            errors.extend(_schema_errors(projected, "resume"))
            resume_path = loop_dir / "resume.json"
            if not resume_path.is_file():
                errors.append("JOURNAL-RESUME resume.json is missing")
            else:
                resume = load_json(confined_file(loop_dir, "resume.json", "JOURNAL-RESUME"))
                errors.extend(_schema_errors(resume, "resume"))
                resume["generated_at"] = projected["generated_at"]
                if resume != projected:
                    errors.append("JOURNAL-FRESHNESS resume.json does not match the canonical projection")
        errors.extend(validate_claims(loop_dir, goal, current_plan))
        artifact_errors, registered_artifacts, _ = validate_artifacts(loop_dir, current_plan)
        errors.extend(artifact_errors)
        errors.extend(validate_evidence_artifacts(loop_dir, records, registered_artifacts))
        errors.extend(validate_module_contracts(loop_dir, goal, current_plan, projected, visited))
    except (OSError, json.JSONDecodeError, SchemaError, ProjectionError, AttributeError, KeyError, TypeError, ValueError) as exc:
        errors.append(f"SCHEMA-LOAD {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("loop_dir", type=Path)
    args = parser.parse_args()
    errors = validate_loop_dir(args.loop_dir)
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
