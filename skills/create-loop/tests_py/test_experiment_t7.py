from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
CHECK_PATH = SKILL_ROOT / "tests/experiments/pilot-evaluator/T7/hidden_check.py"
SPEC = importlib.util.spec_from_file_location("t7_hidden_check", CHECK_PATH)
assert SPEC is not None and SPEC.loader is not None
t7 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(t7)


FAKE_NODE = r'''#!/usr/bin/env python3
import json, os, pathlib, sys

if sys.argv[1:] == ["--version"]:
    version = os.environ.get("FAKE_NODE_VERSION", "18.20.8")
    print("v" + version)
    raise SystemExit(0)

root = pathlib.Path.cwd()
args = sys.argv[1:]
if args != ["bin/create-loop.js", "render"] and args != ["bin/create-loop.js", "render", "--check"]:
    raise SystemExit(64)
manifest = json.loads((root / "command/manifest.json").read_text())
ids = [item["id"] for item in manifest["commands"]]
expected = {}
for host, header in ((pathlib.Path(".opencode/command"), "opencode"), (pathlib.Path(".claude/commands"), "claude")):
    expected[host] = {command_id + ".md": (header + ":" + command_id + "\n").encode() for command_id in ids}

drift = False
for host, files in expected.items():
    target = root / host
    actual = {}
    if target.is_dir():
        actual = {item.name: item.read_bytes() for item in target.iterdir() if item.is_file()}
    if actual != files:
        drift = True
    if args[-1:] != ["--check"]:
        target.mkdir(parents=True, exist_ok=True)
        for item in list(target.iterdir()):
            if item.is_file() and item.name not in files:
                item.unlink()
        for name, data in files.items():
            (target / name).write_bytes(data)
raise SystemExit(1 if args[-1:] == ["--check"] and drift else 0)
'''


class T7HiddenCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        (self.workspace / "bin").mkdir()
        (self.workspace / "command").mkdir()
        (self.workspace / "bin/create-loop.js").write_text(
            "const fs = require('fs');\nconst path = require('path');\n"
            "const os = require('os');\nconst crypto = require('crypto');\n",
            encoding="utf-8", newline="\n",
        )
        (self.workspace / "package.json").write_text(
            json.dumps({"engines": {"node": ">=18"}}) + "\n", encoding="utf-8", newline="\n"
        )
        (self.workspace / "command/manifest.json").write_text(
            json.dumps({"commands": [{"id": "loop-run"}, {"id": "loop-status"}]}) + "\n",
            encoding="utf-8", newline="\n",
        )
        (self.workspace / "command/manifest.schema.json").write_text("{}\n", encoding="utf-8", newline="\n")
        (self.workspace / "command/loop-run.md").write_text("Run.\n", encoding="utf-8", newline="\n")
        (self.workspace / "command/loop-status.md").write_text("Status.\n", encoding="utf-8", newline="\n")
        self.cache = self.root / "node-cache"
        self.fake_node = self.root / "fake-node.py"
        self.fake_node.write_text(FAKE_NODE, encoding="utf-8", newline="\n")
        self.fake_node.chmod(0o755)
        for version in t7.NODE_VERSIONS:
            archive = self.cache / "downloads" / (
                f"node-v{version}-win-x64.zip" if os.name == "nt" else f"node-v{version}-linux-x64.tar.xz"
            )
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive.write_bytes(f"archive-{version}\n".encode())
            executable = self.cache / f"node-v{version}-{'win32' if os.name == 'nt' else 'linux'}-x64" / (
                "node.exe" if os.name == "nt" else "bin/node"
            )
            executable.parent.mkdir(parents=True, exist_ok=True)
            executable.write_bytes(b"fake executable identity\n")
        self.archive_hashes = {
            "win32" if os.name == "nt" else "linux": {
                version: t7.sha256(self.cache / "downloads" / (
                    f"node-v{version}-win-x64.zip" if os.name == "nt" else f"node-v{version}-linux-x64.tar.xz"
                ))
                for version in t7.NODE_VERSIONS
            }
        }

    def run_check(self) -> subprocess.CompletedProcess[str]:
        staging = self.root / "staging"
        evaluator = staging / "pilot-evaluator/T7/hidden_check.py"
        evaluator.parent.mkdir(parents=True)
        shutil.copyfile(CHECK_PATH, evaluator)
        shutil.copytree(self.workspace, staging / "workspace")
        environment = os.environ.copy()
        environment["CREATE_LOOP_NODE_MATRIX_CACHE"] = str(self.cache)
        runner = self.root / "run-hidden.py"
        instrumented = staging / "pilot-evaluator/T7/instrumented-hidden.py"
        source = evaluator.read_text(encoding="utf-8")
        start = source.index("OFFICIAL_ARCHIVE_SHA256 = {")
        end = source.index("\n}\n", start) + 3
        source = source[:start] + f"OFFICIAL_ARCHIVE_SHA256 = {self.archive_hashes!r}\n" + source[end:]
        instrumented.write_text(source, encoding="utf-8", newline="\n")
        runner.write_text(
            "import runpy, subprocess, sys\n"
            "real_run = subprocess.run\n"
            f"fake = {str(self.fake_node)!r}\n"
            "def patched(command, *args, **kwargs):\n"
            "    if isinstance(command, list) and command and ('node-v18.20.8-' in command[0] or 'node-v24.13.0-' in command[0]):\n"
            "        version = command[0].split('node-v', 1)[1].split('-', 1)[0]\n"
            "        env = dict(kwargs.get('env') or __import__('os').environ)\n"
            "        env['FAKE_NODE_VERSION'] = version\n"
            "        kwargs['env'] = env\n"
            "        command = [sys.executable, fake, *command[1:]]\n"
            "    return real_run(command, *args, **kwargs)\n"
            "subprocess.run = patched\n"
            f"module = runpy.run_path({str(instrumented)!r})\n"
            "try:\n"
            "    raise SystemExit(module['main']())\n"
            "except module['CheckFailure'] as exc:\n"
            "    print(f'T7 hidden check failed: {exc}', file=sys.stderr)\n"
            "    raise SystemExit(1)\n",
            encoding="utf-8", newline="\n",
        )
        return subprocess.run([os.sys.executable, str(runner)], cwd=staging, env=environment, text=True, capture_output=True, check=False)

    def test_full_matrix_accepts_and_leaves_source_workspace_unchanged(self) -> None:
        before = t7.snapshot(self.workspace)
        completed = self.run_check()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["node_versions"], ["18.20.8", "24.13.0"])
        self.assertTrue(result["exact_set"])
        self.assertTrue(result["render_check_read_only"])
        self.assertTrue(result["workspace_unchanged"])
        self.assertEqual(t7.snapshot(self.workspace), before)

    def test_rejects_runtime_dependency_fields_and_imports(self) -> None:
        package = json.loads((self.workspace / "package.json").read_text())
        package["dependencies"] = {}
        (self.workspace / "package.json").write_text(json.dumps(package) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(t7.CheckFailure, "dependency field"):
            t7.runtime_dependency_check(self.workspace)
        package.pop("dependencies")
        (self.workspace / "package.json").write_text(json.dumps(package) + "\n", encoding="utf-8")
        with (self.workspace / "bin/create-loop.js").open("a", encoding="utf-8") as handle:
            handle.write("const unsafe = require('left-pad');\n")
        with self.assertRaisesRegex(t7.CheckFailure, "non-builtin"):
            t7.runtime_dependency_check(self.workspace)

    def test_exercise_rejects_crlf_output_or_stale_survivor_or_check_mutation(self) -> None:
        node = self.fake_node

        def fake_baseline(_node: Path, root: Path, *args: str, expected: int = 0):
            return subprocess.run(
                [os.sys.executable, str(self.fake_node), *args], cwd=root,
                text=True, capture_output=True, check=False,
            )

        def corrupt(kind: str):
            def run(fake_node: Path, root: Path, *args: str, expected: int = 0):
                result = fake_baseline(fake_node, root, *args, expected=expected)
                self.assertEqual(result.returncode, expected, result.stderr)
                if args == ("bin/create-loop.js", "render"):
                    target = root / ".opencode/command"
                    if kind == "crlf":
                        first = next(target.iterdir())
                        first.write_bytes(first.read_bytes().replace(b"\n", b"\r\n"))
                    elif kind == "stale":
                        (target / "stale-command.md").write_text("stale\n", encoding="utf-8")
                elif args == ("bin/create-loop.js", "render", "--check") and expected == 0 and kind == "check-mutation":
                    (root / "check-mutated.txt").write_text("changed\n", encoding="utf-8")
                return result
            return run

        for kind, message in (("crlf", "LF-normalized"), ("stale", "exact-set"), ("check-mutation", "modified")):
            with self.subTest(kind=kind), mock.patch.object(t7, "run_node", side_effect=corrupt(kind)):
                with self.assertRaisesRegex(t7.CheckFailure, message):
                    t7.exercise_variant(self.workspace, node, b"\n", kind)

    def test_node_identity_and_cross_eol_equality_are_mandatory(self) -> None:
        missing_cache = self.root / "missing"
        with mock.patch.dict(os.environ, {"CREATE_LOOP_NODE_MATRIX_CACHE": str(missing_cache)}):
            with self.assertRaisesRegex(t7.CheckFailure, "unavailable"):
                t7.node_executable("18.20.8")
        with mock.patch.object(t7, "OFFICIAL_ARCHIVE_SHA256", self.archive_hashes):
            archive = self.cache / "downloads" / (
                "node-v18.20.8-win-x64.zip" if os.name == "nt" else "node-v18.20.8-linux-x64.tar.xz"
            )
            archive.write_bytes(b"tampered\n")
            with self.assertRaisesRegex(t7.CheckFailure, "archive hash mismatch"):
                t7.node_executable("18.20.8")
            archive.write_bytes(b"archive-18.20.8\n")
        calls = 0

        def divergent(*args, **kwargs):
            nonlocal calls
            calls += 1
            result = (("same", "0" * 64, 1),)
            return result if calls % 2 else result + (("different", "0" * 64, 1),)

        staging = self.root / "direct/pilot-evaluator/T7"
        staging.mkdir(parents=True)
        shutil.copyfile(CHECK_PATH, staging / "hidden_check.py")
        shutil.copytree(self.workspace, self.root / "direct/workspace")
        with mock.patch.dict(os.environ, {"CREATE_LOOP_NODE_MATRIX_CACHE": str(self.cache)}), mock.patch.object(
            t7, "OFFICIAL_ARCHIVE_SHA256", self.archive_hashes
        ), mock.patch.object(
            t7, "node_executable", side_effect=lambda version: self.fake_node
        ), mock.patch.object(t7, "exercise_variant", side_effect=divergent), mock.patch.object(
            t7, "__file__", str(staging / "hidden_check.py")
        ):
            with self.assertRaisesRegex(t7.CheckFailure, "different command bytes"):
                t7.main()


if __name__ == "__main__":
    unittest.main()
