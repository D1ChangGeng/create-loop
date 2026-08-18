"""artifacts/INDEX.yaml registry checks (R41). Ensures exactly one authoritative
version per logical path and a resolvable supersedes chain, so an agent never
consumes a stale artifact version while a newer one exists.
"""
from __future__ import annotations

from typing import Any

_ACTIVE = {"draft", "candidate", "accepted", "verified", "published"}
_VALID = _ACTIVE | {"superseded", "deprecated", "retired"}


def validate_artifact_index(doc: Any, errors: list[str]) -> None:
    if not isinstance(doc, dict):
        errors.append("[R41 ARTIFACT-AUTHORITY] artifact.index: document is not a mapping")
        return
    artifacts = doc.get("artifacts")
    if not isinstance(artifacts, list):
        errors.append("[R41 ARTIFACT-AUTHORITY] artifact.index: 'artifacts' must be a list")
        return

    ids = {a.get("artifact_id") for a in artifacts if isinstance(a, dict)}
    active_by_path: dict[str, list[str]] = {}

    for idx, a in enumerate(artifacts):
        scope = f"artifact.index[{idx}]"
        if not isinstance(a, dict):
            errors.append(f"[R41 ARTIFACT-AUTHORITY] {scope}: not a mapping")
            continue
        for field in ("artifact_id", "path", "status"):
            if field not in a:
                errors.append(f"[R41 ARTIFACT-AUTHORITY] {scope}: missing {field!r}")
        status = a.get("status")
        if status is not None and status not in _VALID:
            errors.append(
                f"[R41 ARTIFACT-AUTHORITY] {scope}: status {status!r} not one of {sorted(_VALID)}"
            )
        for sid in a.get("supersedes", []) or []:
            if sid not in ids:
                errors.append(
                    f"[R41 ARTIFACT-AUTHORITY] {scope}: supersedes {sid!r} references no "
                    f"existing artifact_id"
                )
        if status in _ACTIVE and isinstance(a.get("path"), str):
            active_by_path.setdefault(a["path"], []).append(a.get("artifact_id", "?"))

    for path, holders in active_by_path.items():
        if len(holders) > 1:
            errors.append(
                f"[R41 ARTIFACT-AUTHORITY] path {path!r} has {len(holders)} active "
                f"versions {holders} — exactly one may be authoritative; supersede the "
                f"older ones."
            )
