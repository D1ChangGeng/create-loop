from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import copy
import uuid
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = SKILL_ROOT / "tests" / "experiments"
sys.path.insert(0, str(EXPERIMENTS))

import reviewer_isolation as isolation  # noqa: E402


def write_file(path: Path, data: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8", newline="\n")
    os.chmod(path, mode)


@unittest.skipUnless(os.name == "nt" and shutil.which("wsl.exe"), "requires Windows WSL2")
class ReviewerIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        probe = subprocess.run(
            ["wsl.exe", "-d", "Ubuntu", "--", "sh", "-lc", "command -v bwrap >/dev/null && test -d /usr"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if probe.returncode != 0:
            self.skipTest("Ubuntu WSL2 with bubblewrap is unavailable")

    def wsl_path(self, path: Path) -> str:
        completed = subprocess.run(
            ["wsl.exe", "-d", "Ubuntu", "-e", "wslpath", "-a", str(path.resolve())],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        )
        return completed.stdout.decode("utf-8").strip()

    def fixture(self) -> tuple[Path, Path, str, str]:
        workspace = self.root / "anonymous"
        write_file(workspace / "context/task.md", "Compare anonymous A and B.\n")
        write_file(workspace / "A/code.txt", "A\n")
        write_file(workspace / "B/code.txt", "B\n")
        source_home = self.root / "source-codex-home"
        write_file(source_home / "auth.json", '{"token":"secret"}\n')
        write_file(source_home / "config.toml", "model = 'ignored'\n")
        write_file(source_home / "logs_2.sqlite", "must-not-be-copied\n")
        package = f"/tmp/create-loop-reviewer-isolation-{uuid.uuid4().hex}"
        fake_bytes = (
            b"#!/bin/sh\nset -eu\n"
            b"printf '%s\\n' '{\"type\":\"response.started\",\"provider_request_id\":\"fake-review-request\"}'\n"
            b"printf '%s\\n' '{\"type\":\"turn.completed\",\"provider_request_id\":\"fake-review-request\",\"usage\":{\"input_tokens\":1,\"cached_input_tokens\":0,\"output_tokens\":1,\"reasoning_output_tokens\":0,\"total_tokens\":2}}'\n"
            b"printf '%s\\n' '{\"preference\":\"tie\"}' > /output/final-response.json\n"
        )
        created = subprocess.run(
            [
                "wsl.exe", "-d", "Ubuntu", "-e", "sh", "-c",
                "set -eu; mkdir -p \"$1/bin\" \"$1/vendor/bin\"; "
                "cat > \"$1/codex\"; chmod 700 \"$1/codex\"; "
                "cp \"$1/codex\" \"$1/bin/codex.js\"; "
                "cp \"$1/codex\" \"$1/vendor/bin/codex\"; chmod 700 \"$1/vendor/bin/codex\"; "
                "printf '%s\\n' '{\"name\":\"@openai/codex\",\"version\":\"0.144.1\"}' > \"$1/package.json\"",
                "sh", package,
            ],
            input=fake_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if created.returncode != 0:
            self.skipTest("could not create native WSL fake Codex package")
        self.addCleanup(
            lambda: subprocess.run(
                ["wsl.exe", "-d", "Ubuntu", "-e", "rm", "-rf", package],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )
        )
        sentinel = self.root / "hidden-sentinel.txt"
        write_file(sentinel, "HIDDEN\n")
        return workspace, source_home, package, self.wsl_path(sentinel)

    def cli_identity(self, package: str) -> dict:
        snapshot = isolation.hash_wsl_package(
            package, distribution="Ubuntu", wsl_executable="wsl.exe",
        )
        files = {item["path"]: item for item in snapshot["files"]}
        return {
            "schema_version": "1.0",
            "id": "codex-0.144.1-linux-x64-test",
            "product": "codex-cli",
            "version": "0.144.1",
            "platform": "linux",
            "arch": "x86_64",
            "package_tree_sha256": snapshot["aggregate_sha256"],
            "launcher": {"path": "codex", "sha256": files["codex"]["sha256"]},
            "entrypoint": {"path": "bin/codex.js", "sha256": files["bin/codex.js"]["sha256"]},
            "package": {"path": "package.json", "sha256": files["package.json"]["sha256"]},
            "native_executable": {"path": "vendor/bin/codex", "sha256": files["vendor/bin/codex"]["sha256"]},
        }

    def authenticated_wrapper(self, name: str) -> tuple[Path, Path]:
        wrapper = self.root / f"{name}-network-wrapper.py"
        log = self.root / f"{name}-network-wrapper.jsonl"
        write_file(
            wrapper,
            "import json,pathlib,subprocess,sys\n"
            "args=sys.argv[1:]\n"
            "expected=['--session','fixture-review-session','--role','reviewer','--']\n"
            "if args[:5] != expected or len(args) == 5: raise SystemExit(91)\n"
            f"log=pathlib.Path({str(log)!r})\n"
            "with log.open('a',encoding='utf-8') as handle:\n"
            "    handle.write(json.dumps({'session':args[1],'role':args[3],"
            "'command':args[5:]},sort_keys=True)+'\\n')\n"
            "raise SystemExit(subprocess.run(args[5:]).returncode)\n",
            mode=0o700,
        )
        return wrapper, log

    def test_command_keeps_network_and_hides_host_mounts(self) -> None:
        command = isolation.build_bwrap_command(
            workspace_wsl="/tmp/workspace", output_wsl="/tmp/output",
            package_wsl="/opt/frozen-package", codex_home_wsl="/opt/minimal-home",
            child_command=("/opt/codex/codex", "--version"),
        )
        self.assertIn("--unshare-user", command)
        self.assertNotIn("--share-net", command)
        self.assertNotIn("/mnt", command)
        self.assertIn("--clearenv", command)
        self.assertEqual(command[command.index("--ro-bind", command.index("--dir")) + 2], isolation.SANDBOX_CODEX_HOME)

    def test_rejects_windows_interop_package_path(self) -> None:
        with self.assertRaisesRegex(isolation.IsolationError, "Windows interop"):
            isolation.build_bwrap_command(
                workspace_wsl="/tmp/workspace", output_wsl="/tmp/output",
                package_wsl="/mnt/d/codex", codex_home_wsl="/opt/minimal-home",
                child_command=("/opt/codex/codex",),
            )

    def test_real_bwrap_probe_and_fake_reviewer_prove_hidden_sentinel(self) -> None:
        workspace, source_home, package, sentinel_wsl = self.fixture()
        cli_identity = self.cli_identity(package)
        prepared = isolation.prepare_isolation(
            isolation_root=self.root / "isolation", workspace=workspace,
            codex_package_wsl=package,
            cli_identity=cli_identity,
            cli_identity_sha256=isolation.sha256_bytes(isolation.canonical_bytes(cli_identity)),
            source_codex_home=source_home,
            hidden_sentinel_wsl=sentinel_wsl,
        )
        self.assertEqual([item["path"] for item in prepared["home_snapshot"]["files"]], ["auth.json", "config.toml"])
        prompt = self.root / "prompt.txt"
        output = self.root / "response.json"
        raw = self.root / "events.jsonl"
        stderr = self.root / "stderr.log"
        schema = self.root / "output-schema.json"
        manifest = self.root / "isolation-manifest.json"
        wrapper, wrapper_log = self.authenticated_wrapper("successful")
        write_file(prompt, "Review A and B.\n")
        write_file(schema, '{"type":"object"}\n')
        network_boundary = {
            "fixture": "validated",
            "document": {"allowed_endpoint": {"host": "example.invalid"}},
        }
        with mock.patch.object(
            isolation.execution_boundary, "launch_prefix",
            return_value=[
                sys.executable, str(wrapper), "--session", "fixture-review-session",
                "--role", "reviewer", "--",
            ],
        ) as launch_prefix_mock, mock.patch.object(
            isolation,
            "_network_probe_script",
            return_value=(
                "import json\n"
                "open('/output/network-probes.json','w').write(json.dumps(["
                "{'kind':'provider','host':'example.invalid','observed':'allowed'},"
                "{'kind':'arbitrary','host':'example.com','observed':'denied'}]))\n"
            ),
        ):
            result = isolation.launch_reviewer(
                prepared=prepared, prompt_path=prompt, output_path=output,
                raw_path=raw, stderr_path=stderr, model="gpt-5.6-sol", reasoning_effort="ultra",
                provider={"provider_key": "custom", "display_name": "Zeo", "base_url": "https://example.invalid/v1", "wire_api": "responses", "requires_openai_auth": True},
                output_schema=schema, timeout_seconds=15, manifest_path=manifest,
                network_boundary=network_boundary,
            )
        launch_prefix_mock.assert_called_once_with(network_boundary, role="reviewer")
        self.assertEqual(result[0], 0)
        self.assertFalse(result[1])
        wrapper_calls = [
            json.loads(line) for line in wrapper_log.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(len(wrapper_calls), 3)
        self.assertEqual(
            {(item["session"], item["role"]) for item in wrapper_calls},
            {("fixture-review-session", "reviewer")},
        )
        self.assertTrue(all(item["command"][0].lower().endswith("wsl.exe") for item in wrapper_calls))
        value = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(value["network_namespace"], "authenticated-provider-only-launcher")
        self.assertTrue(all(item["expected"] == item["observed"] for item in value["access_probes"]))
        self.assertIn({"path": sentinel_wsl, "expected": "hidden", "observed": "hidden"}, value["access_probes"])
        self.assertEqual(
            {item["sandbox_path"] for item in value["runtime_roots"]},
            set(isolation.DEFAULT_RUNTIME_ROOTS),
        )
        self.assertTrue(all(
            item["source_path_sha256"] == isolation.sha256_bytes(item["sandbox_path"].encode("utf-8"))
            for item in value["runtime_roots"]
        ))
        self.assertEqual(
            {item["path"] for item in value["mount_observations"]},
            set(isolation.REQUIRED_READ_ONLY_MOUNTS),
        )
        self.assertEqual(value["codex_home"]["sandbox_path"], isolation.SANDBOX_CODEX_HOME)
        self.assertEqual(value["cli_identity"]["platform"], "linux")
        self.assertEqual(value["cli_identity"]["version"], "0.144.1")
        self.assertEqual(
            value["cli_identity"]["package_tree_sha256"],
            value["codex_package"]["source_sha256"],
        )
        self.assertTrue(output.is_file())
        for expected, mutate in (
            (
                "runtime root identity drifted",
                lambda document: document["runtime_roots"][0].__setitem__("source_path_sha256", "0" * 64),
            ),
            (
                "required mount is not read-only",
                lambda document: next(
                    item for item in document["mount_observations"] if item["path"] == "/etc/hosts"
                ).__setitem__("mode", "read-write"),
            ),
        ):
            with self.subTest(expected=expected):
                tampered = copy.deepcopy(value)
                mutate(tampered)
                core = {key: item for key, item in tampered.items() if key != "aggregate_sha256"}
                tampered["aggregate_sha256"] = isolation.sha256_bytes(isolation.canonical_bytes(core))
                with self.assertRaisesRegex(isolation.IsolationError, expected):
                    isolation._validate_manifest(tampered)

    def test_failed_denied_probe_stops_before_reviewer_codex_launch(self) -> None:
        workspace, source_home, package, sentinel_wsl = self.fixture()
        cli_identity = self.cli_identity(package)
        prepared = isolation.prepare_isolation(
            isolation_root=self.root / "denied-isolation", workspace=workspace,
            codex_package_wsl=package, cli_identity=cli_identity,
            cli_identity_sha256=isolation.sha256_bytes(isolation.canonical_bytes(cli_identity)),
            source_codex_home=source_home, hidden_sentinel_wsl=sentinel_wsl,
        )
        prompt = self.root / "denied-prompt.txt"
        output = self.root / "denied-response.json"
        raw = self.root / "denied-events.jsonl"
        stderr = self.root / "denied-stderr.log"
        schema = self.root / "denied-output-schema.json"
        manifest = self.root / "denied-isolation-manifest.json"
        wrapper, wrapper_log = self.authenticated_wrapper("denied")
        write_file(prompt, "Review A and B.\n")
        write_file(schema, '{"type":"object"}\n')
        with mock.patch.object(
            isolation.execution_boundary, "launch_prefix",
            return_value=[
                sys.executable, str(wrapper), "--session", "fixture-review-session",
                "--role", "reviewer", "--",
            ],
        ), mock.patch.object(
            isolation,
            "_network_probe_script",
            return_value=(
                "import json\n"
                "open('/output/network-probes.json','w').write(json.dumps(["
                "{'kind':'provider','host':'example.invalid','observed':'allowed'},"
                "{'kind':'arbitrary','host':'example.com','observed':'allowed'}]))\n"
            ),
        ):
            with self.assertRaisesRegex(
                isolation.IsolationError, "provider-only network isolation was not proven"
            ):
                isolation.launch_reviewer(
                    prepared=prepared, prompt_path=prompt, output_path=output,
                    raw_path=raw, stderr_path=stderr, model="gpt-5.6-sol",
                    reasoning_effort="ultra",
                    provider={
                        "provider_key": "custom", "display_name": "Zeo",
                        "base_url": "https://example.invalid/v1", "wire_api": "responses",
                        "requires_openai_auth": True,
                    },
                    output_schema=schema, timeout_seconds=15, manifest_path=manifest,
                    network_boundary={
                        "fixture": "validated",
                        "document": {"allowed_endpoint": {"host": "example.invalid"}},
                    },
                )
        wrapper_calls = [
            json.loads(line) for line in wrapper_log.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(len(wrapper_calls), 2)
        self.assertFalse(raw.exists())
        self.assertFalse(output.exists())
        self.assertFalse(manifest.exists())

    def test_frozen_package_hash_drift_fails_before_launch(self) -> None:
        workspace, source_home, package, sentinel_wsl = self.fixture()
        cli_identity = self.cli_identity(package)
        cli_identity["package_tree_sha256"] = "0" * 64
        with self.assertRaisesRegex(isolation.IsolationError, "package tree hash drifted"):
            isolation.prepare_isolation(
                isolation_root=self.root / "drifted-isolation", workspace=workspace,
                codex_package_wsl=package, cli_identity=cli_identity,
                cli_identity_sha256=isolation.sha256_bytes(isolation.canonical_bytes(cli_identity)),
                source_codex_home=source_home, hidden_sentinel_wsl=sentinel_wsl,
            )

    def test_linux_identity_version_and_component_hash_fail_closed(self) -> None:
        workspace, source_home, package, sentinel_wsl = self.fixture()
        for label, mutate, expected in (
            (
                "version",
                lambda identity: identity.__setitem__("version", "0.146.0"),
                "requires the frozen Linux Codex 0.144.1 identity",
            ),
            (
                "native",
                lambda identity: identity["native_executable"].__setitem__("sha256", "0" * 64),
                "native_executable hash drifted",
            ),
        ):
            with self.subTest(label=label):
                identity = self.cli_identity(package)
                mutate(identity)
                with self.assertRaisesRegex(isolation.IsolationError, expected):
                    isolation.prepare_isolation(
                        isolation_root=self.root / f"invalid-{label}", workspace=workspace,
                        codex_package_wsl=package, cli_identity=identity,
                        cli_identity_sha256=isolation.sha256_bytes(isolation.canonical_bytes(identity)),
                        source_codex_home=source_home, hidden_sentinel_wsl=sentinel_wsl,
                    )

    def test_access_manifest_validation_rejects_unproven_hidden_probe(self) -> None:
        invalid = {
            "schema_version": "1.0", "isolation_id": "reviewer-test",
            "backend": "wsl2-bubblewrap", "distribution": "Ubuntu",
            "network_namespace": "authenticated-provider-only-launcher",
            "namespace_flags": ["user", "ipc", "pid", "uts", "cgroup"],
            "workspace": {"sandbox_path": "/workspace", "mode": "read-only", "source_sha256": "1" * 64},
            "cli_identity": {
                "id": "codex-test", "version": "0.144.1", "platform": "linux", "arch": "x86_64",
                "identity_sha256": "7" * 64, "package_tree_sha256": "2" * 64,
                "launcher": {"path": "codex", "sha256": "8" * 64},
                "entrypoint": {"path": "bin/codex.js", "sha256": "9" * 64},
                "package": {"path": "package.json", "sha256": "a" * 64},
                "native_executable": {"path": "vendor/bin/codex", "sha256": "b" * 64},
            },
            "codex_package": {"sandbox_path": "/opt/codex", "mode": "read-only", "source_sha256": "2" * 64},
            "codex_home": {"sandbox_path": "/home/reviewer/.codex", "mode": "read-only", "source_sha256": "3" * 64},
            "runtime_roots": [{"sandbox_path": "/usr", "mode": "read-only", "source_path_sha256": "4" * 64}],
            "hidden_host_roots": ["/mnt", "/root", "/init", "/run"],
            "delivered_files": [{"path": "context/task.md", "sha256": "5" * 64, "size": 1}],
            "access_probes": [
                {"path": "/workspace", "expected": "readable", "observed": "readable"},
                {"path": "/opt/codex/codex", "expected": "readable", "observed": "readable"},
                {"path": "/home/reviewer/.codex/auth.json", "expected": "readable", "observed": "readable"},
                {"path": "/mnt", "expected": "hidden", "observed": "readable"},
            ],
            "mount_observations": [
                {"path": "/workspace", "mode": "read-only"},
                {"path": "/opt/codex", "mode": "read-only"},
                {"path": "/home/reviewer/.codex", "mode": "read-only"},
                {"path": "/usr", "mode": "read-only"},
            ],
            "environment": {"home": "/home/reviewer", "codex_home": "/home/reviewer/.codex", "path": "/opt/codex:/usr/bin:/bin", "cleared": True},
            "command_sha256": "6" * 64, "created_at": "2026-08-05T00:00:00Z",
        }
        invalid["aggregate_sha256"] = isolation.sha256_bytes(isolation.canonical_bytes(invalid))
        with self.assertRaisesRegex(isolation.IsolationError, "manifest is invalid"):
            isolation._validate_manifest(copy.deepcopy(invalid))


class ReviewerNetworkContractUnitTests(unittest.TestCase):
    def test_v1_network_contract_rejects_reviewer_before_platform_work(self) -> None:
        network_boundary = {"fixture": "validated"}
        with mock.patch.object(
            isolation.execution_boundary,
            "launch_prefix",
            side_effect=isolation.execution_boundary.ExecutionBoundaryError(
                "network boundary v1 cannot compose the WSL reviewer launch"
            ),
        ) as launch_prefix_mock, mock.patch.object(
            isolation, "_verify_linux_cli_package"
        ) as verify_package, mock.patch.object(
            isolation, "_snapshot_tree"
        ) as snapshot_tree, mock.patch.object(isolation, "_run") as run:
            with self.assertRaisesRegex(
                isolation.IsolationError,
                "reviewer network boundary is not launchable",
            ):
                isolation.launch_reviewer(
                    prepared={}, prompt_path=Path("prompt"), output_path=Path("output"),
                    raw_path=Path("raw"), stderr_path=Path("stderr"),
                    model="gpt-5.6-sol", reasoning_effort="ultra", provider={},
                    output_schema=Path("schema"), timeout_seconds=15,
                    manifest_path=Path("manifest"), network_boundary=network_boundary,
                )
        launch_prefix_mock.assert_called_once_with(network_boundary, role="reviewer")
        verify_package.assert_not_called()
        snapshot_tree.assert_not_called()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
