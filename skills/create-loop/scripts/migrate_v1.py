#!/usr/bin/env python3
"""Conservatively migrate a v1 Loop into a sibling v2 directory.

The source tree is only read. Ambiguous evidence becomes a warning; ambiguous
or unsafe effects fail closed. Legacy completed nodes become done state facts
but never a v2 loop completion.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    print("error: PyYAML is required for v1 migration", file=sys.stderr)
    raise SystemExit(2)

from render_resume import write_atomic
from schema_runtime import load_json, validate
from checks.checkpoint_projection import project_checkpoint
from checks.event_log import validate_event_log
from project_loop import canonical_output_path, output_path_identity, ProjectionError

STATUS = {
    "undiscovered": "pending", "discovered": "pending", "needs_clarification": "pending",
    "pending": "pending", "ready": "pending", "running": "active",
    "waiting_external": "waiting", "waiting_user": "waiting", "blocked": "waiting",
    "retry_pending": "waiting", "verifying": "verifying", "verification_failed": "waiting",
    "completed": "done", "cancelled": "closed", "deprecated": "closed",
}

EFFECT_KINDS = frozenset({"pre_effect", "post_effect"})
FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF


def output_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def journal_bytes(records: list[dict[str, Any]]) -> bytes:
    return b"".join(
        (
            json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        for record in records
    )


def _has_reparse_point(path: Path) -> bool:
    if os.name != "nt":
        return False
    try:
        get_attributes = ctypes.windll.kernel32.GetFileAttributesW
        get_attributes.argtypes = [ctypes.c_wchar_p]
        get_attributes.restype = ctypes.c_uint32
        attributes = get_attributes(str(path.absolute()))
    except (AttributeError, OSError) as exc:  # pragma: no cover - Windows API failure
        raise ValueError(f"cannot inspect source path attributes: {path}") from exc
    if attributes == INVALID_FILE_ATTRIBUTES:
        raise ValueError(f"cannot inspect source path attributes: {path}")
    return bool(attributes & FILE_ATTRIBUTE_REPARSE_POINT)


def _reject_link_or_reparse(path: Path, label: str) -> None:
    try:
        path.lstat()
    except OSError as exc:
        raise ValueError(f"cannot inspect {label}: {path}") from exc
    if path.is_symlink() or _has_reparse_point(path):
        raise ValueError(f"{label} must not be a symlink or reparse point: {path}")


def _source_files(source: Path) -> list[Path]:
    _reject_link_or_reparse(source, "source root")
    if not source.is_dir():
        raise ValueError(f"source root must be a real directory: {source}")
    files: list[Path] = []

    def visit(directory: Path) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            raise ValueError(f"cannot enumerate source directory: {directory}") from exc
        for entry in entries:
            path = Path(entry.path)
            _reject_link_or_reparse(path, "source member")
            try:
                if entry.is_dir(follow_symlinks=False):
                    visit(path)
                elif entry.is_file(follow_symlinks=False):
                    files.append(path)
                else:
                    raise ValueError(f"source member must be a regular file or directory: {path}")
            except OSError as exc:
                raise ValueError(f"cannot inspect source member: {path}") from exc

    visit(source)
    return files


def source_snapshot(source: Path) -> tuple[dict[str, bytes], dict[str, str]]:
    files: dict[str, bytes] = {}
    hashes: dict[str, str] = {}
    for path in _source_files(source):
        relative = path.relative_to(source).as_posix()
        raw = path.read_bytes()
        files[relative] = raw
        hashes[relative] = hashlib.sha256(raw).hexdigest()
    return files, hashes


def source_hashes(source: Path) -> dict[str, str]:
    return source_snapshot(source)[1]


def load_yaml_snapshot(snapshot: dict[str, bytes], relative: str, *, required: bool = False) -> Any:
    raw = snapshot.get(relative)
    if raw is None:
        if required:
            raise ValueError(f"required source file is missing: {relative}")
        return None
    try:
        return yaml.safe_load(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError(f"source file is not valid UTF-8: {relative}") from exc


def load_jsonl_snapshot(snapshot: dict[str, bytes], relative: str) -> list[dict[str, Any]]:
    raw = snapshot.get(relative)
    if raw is None:
        return []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"source file is not valid UTF-8: {relative}") from exc
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{relative} line {line_number} is not valid JSON") from exc
        if not isinstance(record, dict):
            raise ValueError(f"{relative} line {line_number} must contain an object")
        records.append(record)
    return records


def stable_id(value: str, prefix: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-.")
    if not cleaned or not cleaned[0].isalpha():
        cleaned = f"{prefix}-{cleaned}"
    return cleaned


def map_loop_id(source: Path, meta: dict[str, Any] | None) -> str:
    candidate = (meta or {}).get("loop_id")
    if isinstance(candidate, str) and re.fullmatch(r"L[0-9]{3}(?:\.[0-9]{2})*", candidate):
        return candidate
    match = re.search(r"L([0-9]{1,3})", source.name)
    return f"L{int(match.group(1)):03d}" if match else "L001"


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def flatten_nodes(
    nodes: Any,
    *,
    owner: str = "top-level plan",
    inherited_dependencies: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, list[str]], list[str]]:
    if not isinstance(nodes, list):
        raise ValueError(f"{owner} nodes must be a list")
    inherited_dependencies = inherited_dependencies or []
    flattened: list[dict[str, Any]] = []
    dependencies: dict[str, list[str]] = {}
    local_ids: list[str] = []
    for index, node in enumerate(nodes):
        label = f"{owner} node {index + 1}"
        if not isinstance(node, dict):
            raise ValueError(f"{label} must be an object")
        original_id = node.get("id")
        if not isinstance(original_id, str) or not original_id:
            raise ValueError(f"{label} has no usable id")
        local_ids.append(original_id)
        flattened.append(node)

    if len(local_ids) != len(set(local_ids)):
        raise ValueError(f"{owner} contains duplicate legacy node ids")
    local_id_set = set(local_ids)
    referenced: set[str] = set()
    for node in nodes:
        original_id = node["id"]
        requires = node.get("requires", [])
        if not isinstance(requires, list) or any(not isinstance(dep, str) for dep in requires):
            raise ValueError(f"legacy node {original_id!r} requires must be a string list")
        unknown = sorted(set(requires) - local_id_set)
        if unknown:
            raise ValueError(f"legacy node {original_id!r} has dependencies outside its plan fragment: {unknown}")
        referenced.update(requires)
        dependencies[original_id] = _dedupe(requires or inherited_dependencies)

    for node in nodes:
        original_id = node["id"]
        subgraph = node.get("subgraph")
        if subgraph is None:
            continue
        if not isinstance(subgraph, dict):
            raise ValueError(f"legacy subgraph under {original_id!r} must be an object")
        if subgraph.get("parent_ref") != original_id:
            raise ValueError(f"legacy subgraph under {original_id!r} has a mismatched parent_ref")
        nested_nodes, nested_dependencies, nested_leaves = flatten_nodes(
            subgraph.get("nodes"),
            owner=f"subgraph under {original_id!r}",
            inherited_dependencies=dependencies[original_id],
        )
        if not nested_nodes:
            raise ValueError(f"legacy subgraph under {original_id!r} has no materialized nodes")
        flattened.extend(nested_nodes)
        dependencies.update(nested_dependencies)
        dependencies[original_id] = _dedupe(dependencies[original_id] + nested_leaves)
    leaves = [node_id for node_id in local_ids if node_id not in referenced]
    return flattened, dependencies, leaves


def build_node_id_map(nodes: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    reverse: dict[str, str] = {}
    for node in nodes:
        original_id = node["id"]
        if original_id in mapping:
            raise ValueError(f"duplicate legacy node id: {original_id!r}")
        mapped_id = stable_id(original_id, "N")
        collision = reverse.get(mapped_id)
        if collision is not None:
            raise ValueError(
                f"legacy node ids {collision!r} and {original_id!r} both normalize to {mapped_id!r}"
            )
        mapping[original_id] = mapped_id
        reverse[mapped_id] = original_id
    return mapping


def map_node_reference(value: Any, node_ids: dict[str, str], *, label: str) -> str:
    if not isinstance(value, str) or value not in node_ids:
        raise ValueError(f"{label} references unknown legacy node id {value!r}")
    return node_ids[value]


def map_legacy_outputs(node: dict[str, Any], node_id: str) -> list[dict[str, str]]:
    produces = node.get("produces", [])
    if not isinstance(produces, list):
        raise ValueError(f"legacy node {node_id!r} produces must be a list")
    outputs: list[dict[str, str]] = []
    for index, value in enumerate(produces):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"legacy node {node_id!r} produces[{index}] must be a non-empty string"
            )
        try:
            canonical = canonical_output_path(value)
        except ProjectionError:
            raise ValueError(
                f"legacy node {node_id!r} produces[{index}] must be a relative path "
                "without a drive, '..' segment, or non-canonical file suffix"
            )
        outputs.append({"path": canonical, "purpose": f"Legacy output from {node_id}"})
    return outputs


def assign_legacy_outputs(
    nodes: list[dict[str, Any]],
    node_ids: dict[str, str],
    warnings: list[str],
) -> dict[str, list[dict[str, str]]]:
    mapped: dict[str, list[dict[str, str]]] = {}
    owners: dict[str, str] = {}
    for node in nodes:
        original_id = node["id"]
        retained: list[dict[str, str]] = []
        for output in map_legacy_outputs(node, original_id):
            identity = output_path_identity(output["path"])
            owner = owners.get(identity)
            if owner is None:
                owners[identity] = original_id
                retained.append(output)
                continue
            warnings.append(
                f"{original_id}: duplicate legacy output {output['path']!r} remains owned "
                f"by earlier producer {owner!r}; the later producer relationship is "
                "preserved in this migration warning instead of creating two v2 owners."
            )
        mapped[node_ids[original_id]] = retained
    return mapped


def _effect_identity(event: dict[str, Any], index: int) -> tuple[str, str] | None:
    effect_id = event.get("effect_id")
    attempt_id = event.get("attempt_id")
    if effect_id is None and attempt_id is None:
        return None
    if not (
        isinstance(effect_id, str)
        and effect_id
        and isinstance(attempt_id, str)
        and attempt_id
    ):
        raise ValueError(
            f"legacy event_log effect at index {index} must carry both effect_id "
            "and attempt_id as non-empty strings, or neither"
        )
    return effect_id, attempt_id


def _legacy_effect_pairings(events: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any] | None, str, str]]:
    open_exact: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {}
    open_legacy: dict[str, tuple[int, dict[str, Any]]] = {}
    seen_exact: set[tuple[str, str]] = set()
    pairs: list[tuple[dict[str, Any], dict[str, Any] | None, str, str]] = []
    for index, event in enumerate(events):
        if event.get("kind") not in EFFECT_KINDS:
            continue
        node_id = event.get("node_id")
        if not isinstance(node_id, str) or not node_id:
            raise ValueError(f"legacy event_log effect at index {index} has no usable node_id")
        identity = _effect_identity(event, index)
        if event["kind"] == "pre_effect":
            if identity is not None:
                if identity in seen_exact:
                    raise ValueError(f"duplicate legacy effect identity {identity!r}")
                seen_exact.add(identity)
                open_exact[identity] = (index, event)
            else:
                if node_id in open_legacy:
                    raise ValueError(
                        f"legacy effects for node {node_id!r} cannot be paired conservatively: "
                        "another pre_effect is already open"
                    )
                open_legacy[node_id] = (index, event)
            continue

        if identity is not None:
            prior = open_exact.pop(identity, None)
            if prior is None or prior[1].get("node_id") != node_id:
                raise ValueError(
                    f"legacy post_effect {identity!r} cannot be paired conservatively "
                    "with a unique prior pre_effect on the same node"
                )
            pairs.append((prior[1], event, identity[0], identity[1]))
            continue

        prior = open_legacy.pop(node_id, None)
        if prior is None:
            raise ValueError(
                f"legacy post_effect for node {node_id!r} cannot be paired conservatively"
            )
        pre_index, pre = prior
        idempotency_key = pre.get("idempotency_key")
        if not (
            pre_index == index - 1
            and isinstance(idempotency_key, str)
            and idempotency_key
            and event.get("idempotency_key") == idempotency_key
            and pre.get("to_status") == event.get("from_status")
        ):
            raise ValueError(
                f"legacy effects for node {node_id!r} cannot be paired conservatively: "
                "records must be adjacent with the same idempotency_key and a continuous status boundary"
            )
        effect_id = stable_id(f"legacy-effect-{node_id}-{pre.get('seq', pre_index)}", "effect")
        attempt_id = stable_id(f"legacy-attempt-{pre.get('seq', pre_index)}", "attempt")
        pairs.append((pre, event, effect_id, attempt_id))

    for identity, (_, pre) in open_exact.items():
        pairs.append((pre, None, identity[0], identity[1]))
    for node_id, (pre_index, pre) in open_legacy.items():
        effect_id = stable_id(f"legacy-effect-{node_id}-{pre.get('seq', pre_index)}", "effect")
        attempt_id = stable_id(f"legacy-attempt-{pre.get('seq', pre_index)}", "attempt")
        pairs.append((pre, None, effect_id, attempt_id))
    return pairs


def _effect_time(value: Any, fallback: str) -> str:
    if not isinstance(value, str) or not value:
        return fallback
    candidate = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"legacy effect timestamp is not RFC 3339: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"legacy effect timestamp lacks a timezone: {value!r}")
    return value


def _effect_outcome(value: Any) -> str:
    if value == "ok":
        return "succeeded"
    if value == "fail":
        return "failed"
    raise ValueError(f"legacy post_effect has unsupported outcome {value!r}")


def migrate_effects(
    events: list[dict[str, Any]],
    *,
    node_ids: dict[str, str],
    states: dict[str, str],
    warnings: list[str],
    start_seq: int,
    fallback_ts: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pairs = _legacy_effect_pairings(events)
    records: list[dict[str, Any]] = []
    closed_effects: list[dict[str, Any]] = []
    seq = start_seq
    for pre, post, effect_id, attempt_id in pairs:
        _effect_time(pre.get("ts"), fallback_ts)
        if post is not None:
            _effect_time(post.get("ts"), fallback_ts)
        mapped_node_id = map_node_reference(
            pre.get("node_id"), node_ids, label="legacy event_log effect"
        )
        idempotency_key = pre.get("idempotency_key")
        if idempotency_key is not None and (
            not isinstance(idempotency_key, str) or not idempotency_key
        ):
            raise ValueError(
                f"legacy effect {effect_id}:{attempt_id} has an invalid idempotency_key"
            )
        if post is not None:
            outcome = _effect_outcome(post.get("outcome"))
            result_ref = post.get("result_hash")
            if not isinstance(result_ref, str) or not result_ref:
                result_ref = f"legacy-event-log:seq-{post.get('seq', 'unknown')}"
            closed_effects.append({
                "effect_id": effect_id,
                "attempt_id": attempt_id,
                "node_id": mapped_node_id,
                "pre_seq": pre.get("seq"),
                "post_seq": post.get("seq"),
                "outcome": outcome,
                "idempotency_key": idempotency_key,
                "result_ref": result_ref,
            })
            continue
        if idempotency_key is None:
            raise ValueError(
                f"unmatched non-idempotent legacy effect {effect_id}:{attempt_id} "
                "cannot be migrated without a verified compensation reference"
            )
        if states[mapped_node_id] != "active":
            raise ValueError(
                f"in-doubt legacy effect {effect_id}:{attempt_id} belongs to node "
                f"{mapped_node_id!r} whose imported state is {states[mapped_node_id]!r}; "
                "migration will not fabricate the active state required by the v2 effect model"
            )
        operation = pre.get("intent")
        if not isinstance(operation, str) or not operation:
            operation = f"Imported legacy effect for {mapped_node_id}"
        target = pre.get("target")
        if not isinstance(target, str) or not target:
            target = f"legacy-node:{mapped_node_id}"
        expected = pre.get("expected_postcondition")
        if not isinstance(expected, str) or not expected:
            expected = f"Verify the real postcondition of imported legacy effect {effect_id}:{attempt_id}."
        records.append({
            "schema_version": "2.0", "seq": seq,
            "record_id": stable_id(f"legacy-effect-pre-{seq}-{effect_id}-{attempt_id}", "effect-pre"),
            "ts": fallback_ts, "kind": "effect_pre",
            "actor": {"type": "migrator", "id": "migrate_v1.py"},
            "plan_version": 1, "node_id": mapped_node_id,
            "payload": {
                "effect_id": effect_id, "attempt_id": attempt_id,
                "operation": operation, "target": target,
                "idempotency_key": idempotency_key,
                "authorization_decision_ref": None,
                "authorization_boundary_ref": None,
                "expected_postcondition": expected, "compensation_ref": None,
            },
        })
        seq += 1
        warnings.append(
            f"in-doubt legacy effect {effect_id}:{attempt_id} was preserved; "
            "check reality before retrying or completing the Loop."
        )
    return records, closed_effects


def convert(
    source: Path,
    destination: Path,
    *,
    dry_run: bool,
    snapshot: dict[str, bytes] | None = None,
    hashes: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    if (snapshot is None) != (hashes is None):
        raise ValueError("source snapshot bytes and hashes must be supplied together")
    if snapshot is None:
        snapshot, hashes = source_snapshot(source)
    plan_v1 = load_yaml_snapshot(snapshot, "loop.plan.yaml", required=True)
    if not isinstance(plan_v1, dict):
        raise ValueError("loop.plan.yaml must contain an object")
    required_authority = {
        "goal": str,
        "true_intent": str,
        "non_goals": list,
        "success_criteria": list,
        "failure_criteria": list,
        "constraints": list,
        "nodes": list,
    }
    for field, expected_type in required_authority.items():
        value = plan_v1.get(field)
        if not isinstance(value, expected_type):
            raise ValueError(
                f"legacy loop.plan.yaml authority field {field!r} must be "
                f"{expected_type.__name__}"
            )
    if not plan_v1["goal"].strip() or not plan_v1["true_intent"].strip():
        raise ValueError("legacy loop.plan.yaml goal and true_intent must be non-empty strings")
    for field in ("non_goals", "failure_criteria", "constraints"):
        if any(not isinstance(item, str) for item in plan_v1[field]):
            raise ValueError(f"legacy loop.plan.yaml authority field {field!r} must contain strings")
    if not plan_v1["success_criteria"]:
        raise ValueError("legacy loop.plan.yaml success_criteria must be non-empty")
    for index, item in enumerate(plan_v1["success_criteria"]):
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or not item["id"].strip()
            or not isinstance(item.get("statement"), str)
            or not item["statement"].strip()
        ):
            raise ValueError(
                "legacy loop.plan.yaml success_criteria"
                f"[{index}] must contain non-empty string id and statement"
            )
    meta = load_yaml_snapshot(snapshot, "loop.meta.yaml")
    checkpoint = load_yaml_snapshot(snapshot, "checkpoint.yaml") or {}
    ledger = load_yaml_snapshot(snapshot, "evidence.ledger.yaml") or {}
    if meta is not None and not isinstance(meta, dict):
        raise ValueError("loop.meta.yaml must contain an object")
    if not isinstance(checkpoint, dict):
        raise ValueError("checkpoint.yaml must contain an object")
    if not isinstance(ledger, dict):
        raise ValueError("evidence.ledger.yaml must contain an object")

    event_log_ref = checkpoint.get("event_log_ref")
    if not isinstance(event_log_ref, str) or not event_log_ref:
        raise ValueError("checkpoint event_log_ref must name the required v1 event log")
    normalized_event_ref = event_log_ref.replace("\\", "/")
    if normalized_event_ref.startswith("./"):
        normalized_event_ref = normalized_event_ref[2:]
    if normalized_event_ref != "event_log.jsonl":
        raise ValueError("checkpoint event_log_ref must resolve to event_log.jsonl for migration")
    if normalized_event_ref not in snapshot:
        raise ValueError("required source file is missing: event_log.jsonl")
    events = load_jsonl_snapshot(snapshot, normalized_event_ref)

    warnings: list[str] = []
    loop_id = map_loop_id(source, meta)
    criteria = [
        {
            "id": stable_id(item["id"], "SC"),
            "statement": item["statement"],
            "expected_evidence": "Direct evidence imported or re-collected under v2.",
        }
        for item in plan_v1["success_criteria"]
    ]
    constraints = [{"id": f"C{index}", "statement": str(value)} for index, value in enumerate(plan_v1.get("constraints", []), 1)]

    legacy_nodes, legacy_dependencies, _ = flatten_nodes(plan_v1.get("nodes"))
    node_ids = build_node_id_map(legacy_nodes)
    mapped_outputs = assign_legacy_outputs(legacy_nodes, node_ids, warnings)
    event_errors: list[str] = []
    validate_event_log(events, event_errors, node_ids=set(node_ids))
    if event_errors:
        raise ValueError("legacy event_log.jsonl is invalid: " + "; ".join(event_errors))
    checkpoint_states = checkpoint.get("node_states")
    if not isinstance(checkpoint_states, dict):
        raise ValueError("checkpoint node_states must be an object")
    unknown_states = sorted(str(value) for value in set(checkpoint_states) - set(node_ids))
    if unknown_states:
        raise ValueError(f"checkpoint references unmapped legacy node ids: {unknown_states}")
    invalid_statuses = {
        original_id: checkpoint_states[original_id]
        for original_id in node_ids
        if original_id in checkpoint_states
        and (
            not isinstance(checkpoint_states[original_id], str)
            or checkpoint_states[original_id] not in STATUS
        )
    }
    if invalid_statuses:
        details = ", ".join(
            f"{node_id!r}={status!r}"
            for node_id, status in sorted(invalid_statuses.items())
        )
        raise ValueError(f"checkpoint contains unknown legacy node status: {details}")
    source_projection = project_checkpoint(plan_v1, events, ledger)
    if source_projection.node_states != checkpoint_states:
        disagreements = {
            node_id: {
                "event_projection": source_projection.node_states.get(node_id),
                "checkpoint": checkpoint_states.get(node_id),
            }
            for node_id in sorted(set(source_projection.node_states) | set(checkpoint_states))
            if source_projection.node_states.get(node_id) != checkpoint_states.get(node_id)
        }
        raise ValueError(
            "legacy event-log projection disagrees with checkpoint node_states: "
            + json.dumps(disagreements, sort_keys=True)
        )
    if checkpoint.get("last_event_seq") != source_projection.last_event_seq:
        raise ValueError(
            "legacy event-log tail disagrees with checkpoint last_event_seq: "
            f"projected {source_projection.last_event_seq}, recorded {checkpoint.get('last_event_seq')!r}"
        )
    boundaries = []
    boundary_by_node: dict[str, str] = {}
    for old in legacy_nodes:
        gate = old.get("gate") or {}
        if not isinstance(gate, dict):
            raise ValueError(f"legacy node {old['id']!r} gate must be an object or null")
        if old.get("kind") == "approval" or gate.get("kind") == "human_approval":
            mapped_node_id = node_ids[old["id"]]
            boundary_id = stable_id(f"AUTH-{mapped_node_id}", "AUTH")
            boundaries.append({"id": boundary_id, "action": old.get("title", old["id"]), "authority": "user", "trigger": "Before executing the legacy approval-gated action."})
            boundary_by_node[old["id"]] = boundary_id

    created = str(plan_v1.get("created", "2026-01-01"))
    if "T" not in created:
        created += "T00:00:00Z"
    goal = {
        "schema_version": "2.0", "loop_id": loop_id, "goal": plan_v1["goal"],
        "intent": plan_v1["true_intent"],
        "scope": {"in": [plan_v1["goal"]], "out": list(plan_v1["non_goals"])},
        "success_criteria": criteria, "constraints": constraints, "authorization_boundaries": boundaries,
        "stop_conditions": [str(item) for item in plan_v1.get("failure_criteria", [])], "created_at": created,
    }
    goal_hash = hashlib.sha256(output_bytes(goal)).hexdigest()
    criterion_ids = [item["id"] for item in criteria]
    nodes = []
    for old in legacy_nodes:
        original_id = old["id"]
        node_id = node_ids[original_id]
        gate = old.get("gate") or {}
        check_id = stable_id(f"check-{node_id}", "check")
        nodes.append({
            "id": node_id, "objective": str(old.get("title", node_id)),
            "depends_on": [
                map_node_reference(dep, node_ids, label=f"legacy node {original_id!r}")
                for dep in legacy_dependencies[original_id]
            ],
            "success_criteria_refs": criterion_ids,
            "outputs": mapped_outputs[node_id],
            "checks": [{"id": check_id, "method": str(gate.get("kind", "model_judgment")), "instruction": str(gate.get("rubric") or old.get("postconditions") or "Re-verify the legacy node outcome."), "expected": "Fresh evidence supports this node's objective."}],
            "authorization_refs": [boundary_by_node[original_id]] if original_id in boundary_by_node else [],
        })
        if old.get("child_loops"):
            warnings.append(f"Legacy child loops under {node_id} require explicit v2 return contracts.")
    plan = {
        "schema_version": "2.0", "plan_id": stable_id(f"plan-{loop_id}-v1", "plan"), "plan_version": 1,
        "goal_sha256": goal_hash, "created_at": created,
        "control": {"mode": "persistent", "modules": [], "admission_reason": "Imported from a persisted v1 Loop; preservation of recovery context justifies persistent mode."},
        "nodes": nodes,
    }

    states_v1 = checkpoint_states
    states = {
        mapped_id: STATUS[states_v1.get(original_id, "pending")]
        for original_id, mapped_id in node_ids.items()
    }
    for original_id, node_id in node_ids.items():
        state = states[node_id]
        if state == "done":
            warnings.append(f"{node_id}: legacy completed mapped to done but remains legacy_completion_unverified and cannot authorize v2 completion.")
        if states_v1.get(original_id) == "verification_failed":
            warnings.append(f"{node_id}: verification_failed mapped to waiting and needs a new decision.")

    entries = ledger.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("evidence ledger entries must be a list")
    active_by_node: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("evidence ledger entries must be objects")
        original_id = entry.get("node_id")
        mapped_id = map_node_reference(original_id, node_ids, label="legacy evidence")
        if entry.get("status", "active") == "active":
            active_by_node.setdefault(mapped_id, []).append(entry)
    for node_id, active in active_by_node.items():
        if len(active) > 1 or len({entry.get("verdict") for entry in active}) > 1:
            warnings.append(f"{node_id}: multiple or conflicting active legacy evidence entries were not selected as current.")

    migration_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    effect_records, closed_effects = migrate_effects(
        events,
        node_ids=node_ids,
        states=states,
        warnings=warnings,
        start_seq=3,
        fallback_ts=migration_ts,
    )
    if effect_records:
        plan["control"]["mode"] = "governed"
        plan["control"]["modules"] = ["effects"]
    plan_hash = hashlib.sha256(output_bytes(plan)).hexdigest()
    for record in effect_records:
        record["ts"] = migration_ts
    legacy_source = {
        "event_log_ref": normalized_event_ref,
        "event_log_sha256": hashes[normalized_event_ref],
        "checkpoint_sha256": hashes["checkpoint.yaml"],
        "last_event_seq": source_projection.last_event_seq,
    }
    journal = [
        {"schema_version": "2.0", "seq": 1, "record_id": "legacy-import-0001", "ts": migration_ts, "kind": "legacy_import", "actor": {"type": "migrator", "id": "migrate_v1.py"}, "payload": {"source_hashes": hashes, "source": legacy_source, "node_states": states, "closed_effects": closed_effects, "warnings": warnings}},
        {"schema_version": "2.0", "seq": 2, "record_id": "plan-activated-0001", "ts": migration_ts, "kind": "plan_activated", "actor": {"type": "migrator", "id": "migrate_v1.py"}, "plan_version": 1, "payload": {"plan_ref": "plans/plan-v1.json", "plan_sha256": plan_hash, "previous_version": None, "reason": "Conservative v1 import", "evidence_refs": [], "decision_ref": None}},
        *effect_records,
    ]
    report = {"schema_version": "2.0", "source": str(source.resolve()), "destination": str(destination.resolve()), "dry_run": dry_run, "source_hashes": hashes, "journal_last_seq": journal[-1]["seq"], "journal_sha256": hashlib.sha256(journal_bytes(journal)).hexdigest(), "mapped_files": ["goal.json", "plans/plan-v1.json", "journal.jsonl", "resume.json", "migration-report.json"], "warnings": warnings}
    return goal, plan, journal, report


def validate_staging(
    staging: Path,
    goal: dict[str, Any],
    plan: dict[str, Any],
    journal: list[dict[str, Any]],
    report: dict[str, Any],
) -> None:
    (staging / "plans").mkdir()
    write_atomic(staging / "goal.json", goal)
    write_atomic(staging / "plans" / "plan-v1.json", plan)
    with (staging / "journal.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for record in journal:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    if hashlib.sha256((staging / "journal.jsonl").read_bytes()).hexdigest() != report["journal_sha256"]:
        raise ValueError("migration report journal hash does not match journal.jsonl")
    write_atomic(staging / "migration-report.json", report)
    from project_loop import project
    write_atomic(staging / "resume.json", project(staging))
    from validate_loop_dir import validate_loop_dir
    errors = validate_loop_dir(staging)
    report_errors = validate(report, load_json(Path(__file__).resolve().parent.parent / "schemas" / "migration-report.schema.json"))
    if errors or report_errors:
        raise ValueError("; ".join(errors + report_errors))


def create_staging(source: Path, destination: Path, *, dry_run: bool) -> Path:
    if not dry_run:
        return Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.migrate-", dir=destination.parent)
        )

    staging = Path(tempfile.mkdtemp(prefix="create-loop-migrate-dry-"))
    try:
        resolved_staging = staging.resolve(strict=True)
        resolved_source = source.resolve(strict=True)
        loop_roots = [resolved_source]
        loop_roots.extend(
            ancestor
            for ancestor in resolved_source.parents
            if (ancestor / "loop.plan.yaml").is_file()
        )
        if any(resolved_staging.is_relative_to(root) for root in loop_roots):
            raise ValueError(
                "dry-run temporary staging must be outside the source Loop ancestry"
            )
        return staging
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def migrate(
    source: Path,
    destination: Path,
    *,
    dry_run: bool,
) -> dict[str, Any]:
    snapshot, hashes = source_snapshot(source)
    goal, plan, journal, report = convert(
        source, destination, dry_run=dry_run, snapshot=snapshot, hashes=hashes
    )
    staging = create_staging(source, destination, dry_run=dry_run)
    published = False
    try:
        validate_staging(staging, goal, plan, journal, report)
        if source_hashes(source) != hashes:
            raise ValueError("source changed during migration")
        if not dry_run:
            staging.rename(destination)
            published = True
        return report
    finally:
        if not published:
            shutil.rmtree(staging, ignore_errors=True)


def bounded_error(exc: Exception, *, limit: int = 500) -> str:
    message = " ".join(str(exc).splitlines()).strip() or type(exc).__name__
    return message if len(message) <= limit else message[: limit - 3] + "..."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path, nargs="?")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    source_input = args.source.absolute()
    try:
        _reject_link_or_reparse(source_input, "source root")
        source = source_input.resolve(strict=True)
    except (OSError, ValueError) as exc:
        print(f"error: migration failed: {bounded_error(exc)}", file=sys.stderr)
        return 1
    destination_input = args.destination or source_input.with_name(source_input.name + "-v2")
    destination = destination_input.absolute().resolve(strict=False)
    if source == destination or source.parent != destination.parent:
        print("error: destination must be a distinct sibling of the source", file=sys.stderr)
        return 2
    if destination.exists():
        print(f"error: destination already exists: {destination}", file=sys.stderr)
        return 2
    try:
        report = migrate(source, destination, dry_run=args.dry_run)
    except Exception as exc:
        print(f"error: migration failed: {bounded_error(exc)}", file=sys.stderr)
        return 1
    if args.dry_run:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
