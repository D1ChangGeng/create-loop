#!/usr/bin/env python3
"""Hidden, evaluator-owned acceptance check for the T7 renderer repair."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable


NODE_VERSIONS = ("18.20.8", "24.13.0")
OFFICIAL_ARCHIVE_SHA256 = {
    "win32": {
        "18.20.8": "1a1e40260a6facba83636e4cd0ba01eb5bd1386896824b36645afba44857384a",
        "24.13.0": "ca2742695be8de44027d71b3f53a4bdb36009b95575fe1ae6f7f0b5ce091cb88",
    },
    "linux": {
        "18.20.8": "5467ee62d6af1411d46b6a10e3fb5cacc92734dbcef465fea14e7b90993001c9",
        "24.13.0": "e798599612f4bb71333a3397ab0d095fd62214e115aea45aa858a145fc72d67e",
    },
}
HOST_DIRS = (Path(".opencode/command"), Path(".claude/commands"))
RUNTIME_BUILTINS = frozenset({"fs", "path", "os", "crypto"})
IGNORED_DIRS = frozenset({".git"})


class CheckFailure(RuntimeError):
    pass


def fail(message: str) -> None:
    raise CheckFailure(message)


def strict_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda value: fail(
            f"non-standard JSON constant in {path}: {value}"
        ))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CheckFailure(f"cannot read strict JSON {path}: {exc}") from exc


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(root: Path) -> tuple[tuple[str, str, int], ...]:
    files: list[tuple[str, str, int]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root)
        if any(part in IGNORED_DIRS for part in relative.parts):
            continue
        if path.is_symlink():
            fail(f"workspace contains a symlink: {relative.as_posix()}")
        if path.is_file():
            files.append((relative.as_posix(), sha256(path), path.stat().st_size))
    return tuple(files)


def command_ids(root: Path) -> tuple[str, ...]:
    manifest = strict_json(root / "command/manifest.json")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("commands"), list):
        fail("command manifest has no commands array")
    ids: list[str] = []
    for command in manifest["commands"]:
        if not isinstance(command, dict) or not isinstance(command.get("id"), str):
            fail("command manifest contains an invalid command ID")
        ids.append(command["id"])
    if not ids or len(ids) != len(set(ids)):
        fail("command IDs must be non-empty and unique")
    return tuple(ids)


def rendered_snapshot(root: Path) -> tuple[tuple[str, str, int], ...]:
    files: list[tuple[str, str, int]] = []
    for host in HOST_DIRS:
        host_root = root / host
        if not host_root.is_dir():
            fail(f"renderer did not create {host.as_posix()}")
        for path in sorted(host_root.rglob("*"), key=lambda item: item.relative_to(host_root).as_posix()):
            if path.is_symlink() or not path.is_file():
                fail(f"render target contains a non-regular entry: {path}")
            relative = (host / path.relative_to(host_root)).as_posix()
            data = path.read_bytes()
            if b"\r" in data:
                fail(f"rendered command is not LF-normalized: {relative}")
            files.append((relative, hashlib.sha256(data).hexdigest(), len(data)))
    return tuple(files)


def assert_exact_set(root: Path, ids: Iterable[str]) -> None:
    expected = {f"{command_id}.md" for command_id in ids}
    for host in HOST_DIRS:
        entries = list((root / host).iterdir())
        if any(not item.is_file() or item.is_symlink() for item in entries):
            fail(f"render target {host.as_posix()} contains a non-regular entry")
        actual = {item.name for item in entries}
        if actual != expected:
            fail(
                f"render target {host.as_posix()} is not exact-set: "
                f"expected {sorted(expected)}, got {sorted(actual)}"
            )


def to_eol(root: Path, eol: bytes) -> None:
    for path in root.rglob("*"):
        if not path.is_file() or any(part in IGNORED_DIRS for part in path.relative_to(root).parts):
            continue
        data = path.read_bytes()
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        normalized = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        path.write_bytes(normalized.replace(b"\n", eol))


def runtime_dependency_check(root: Path) -> None:
    package = strict_json(root / "package.json")
    engines = package.get("engines") if isinstance(package, dict) else None
    if not isinstance(engines, dict) or engines.get("node") != ">=18":
        fail("package.json must retain engines.node >=18")
    forbidden = ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies", "bundledDependencies")
    if any(key in package for key in forbidden):
        fail("package.json contains a dependency field")
    source = (root / "bin/create-loop.js").read_text(encoding="utf-8")
    requires: list[str] = []
    marker = "require("
    for fragment in source.split(marker)[1:]:
        quote = fragment[:1]
        if quote not in {"'", '"'}:
            continue
        end = fragment.find(quote, 1)
        if end > 0:
            requires.append(fragment[1:end])
    externals = sorted(
        value for value in requires
        if not value.startswith((".", "/")) and value.removeprefix("node:") not in RUNTIME_BUILTINS
    )
    if externals:
        fail(f"installer imports non-builtin runtime modules: {externals}")


def node_cache_root() -> Path:
    configured = os.environ.get("CREATE_LOOP_NODE_MATRIX_CACHE")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".cache/create-loop/node-matrix").resolve()


def node_executable(version: str) -> Path:
    platform = "win32" if os.name == "nt" else "linux"
    suffix = "node.exe" if os.name == "nt" else "bin/node"
    archive_name = (
        f"node-v{version}-win-x64.zip" if os.name == "nt"
        else f"node-v{version}-linux-x64.tar.xz"
    )
    archive = node_cache_root() / "downloads" / archive_name
    if not archive.is_file() or archive.is_symlink():
        fail(f"official Node {version} archive is unavailable: {archive}")
    actual_archive_hash = sha256(archive)
    expected_archive_hash = OFFICIAL_ARCHIVE_SHA256[platform][version]
    if actual_archive_hash != expected_archive_hash:
        fail(
            f"official Node {version} archive hash mismatch: "
            f"expected {expected_archive_hash}, got {actual_archive_hash}"
        )
    executable = node_cache_root() / f"node-v{version}-{platform}-x64" / suffix
    if not executable.is_file() or executable.is_symlink():
        fail(f"frozen Node {version} executable is unavailable: {executable}")
    completed = subprocess.run(
        [str(executable), "--version"], text=True, capture_output=True, check=False, timeout=30
    )
    if completed.returncode != 0 or completed.stdout.strip() != f"v{version}":
        fail(f"frozen Node executable identity mismatch for {version}")
    return executable


def run_node(node: Path, root: Path, *arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [str(node), *arguments], cwd=root, text=True, capture_output=True, check=False, timeout=120
    )
    if completed.returncode != expected:
        fail(
            f"Node {node.name} {' '.join(arguments)} exited {completed.returncode}, expected {expected}: "
            f"{completed.stderr.strip()}"
        )
    return completed


def exercise_variant(source: Path, node: Path, eol: bytes, label: str) -> tuple[tuple[str, str, int], ...]:
    with tempfile.TemporaryDirectory(prefix=f"t7-{label}-") as temporary:
        root = Path(temporary) / "workspace"
        shutil.copytree(source, root)
        to_eol(root, eol)
        for host in HOST_DIRS:
            host_root = root / host
            host_root.mkdir(parents=True, exist_ok=True)
            (host_root / "stale-command.md").write_text("stale\n", encoding="utf-8", newline="\n")
        run_node(node, root, "bin/create-loop.js", "render")
        ids = command_ids(root)
        assert_exact_set(root, ids)
        rendered = rendered_snapshot(root)

        before_check = snapshot(root)
        run_node(node, root, "bin/create-loop.js", "render", "--check")
        if snapshot(root) != before_check:
            fail(f"render --check modified the {label} workspace")

        target = root / HOST_DIRS[0] / f"{ids[0]}.md"
        target.write_bytes(target.read_bytes() + b"drift\n")
        before_drift_check = snapshot(root)
        run_node(node, root, "bin/create-loop.js", "render", "--check", expected=1)
        if snapshot(root) != before_drift_check:
            fail(f"failing render --check modified the {label} workspace")
        return rendered


def main() -> int:
    workspace = Path(__file__).resolve().parents[2] / "workspace"
    if not workspace.is_dir():
        fail(f"T7 workspace is missing: {workspace}")
    original = snapshot(workspace)
    runtime_dependency_check(workspace)
    reference: tuple[tuple[str, str, int], ...] | None = None
    for version in NODE_VERSIONS:
        node = node_executable(version)
        lf = exercise_variant(workspace, node, b"\n", f"node-{version}-lf")
        crlf = exercise_variant(workspace, node, b"\r\n", f"node-{version}-crlf")
        if lf != crlf:
            fail(f"Node {version} renders different command bytes for LF and CRLF inputs")
        if reference is None:
            reference = lf
        elif lf != reference:
            fail(f"Node {version} renderer output differs from Node {NODE_VERSIONS[0]}")
    if snapshot(workspace) != original:
        fail("hidden check modified the evaluator workspace")
    print(
        json.dumps(
            {
                "ok": True,
                "node_versions": list(NODE_VERSIONS),
                "eol_variants": ["LF", "CRLF"],
                "exact_set": True,
                "render_check_read_only": True,
                "zero_runtime_dependencies": True,
                "workspace_unchanged": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CheckFailure, OSError, subprocess.SubprocessError) as exc:
        print(f"T7 hidden check failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
