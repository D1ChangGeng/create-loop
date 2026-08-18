from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
EXPERIMENTS = ROOT / "skills" / "create-loop" / "tests" / "experiments"
SCRIPTS = ROOT / "skills" / "create-loop" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(EXPERIMENTS))

import network_execution_boundary as boundary  # noqa: E402
from schema_runtime import check_schema, validate  # noqa: E402


NOW = datetime(2026, 8, 5, 0, 0, tzinfo=timezone.utc)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


class NetworkExecutionBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in (
            "network-execution-boundary.schema.json",
            "cli-identity.schema.json",
            "provider-profile.schema.json",
        ):
            (self.root / name).write_bytes((EXPERIMENTS / name).read_bytes())

    def bind(self, path: Path, *, identity: str | None = None) -> dict[str, str]:
        value = {
            "path": path.relative_to(self.root).as_posix(),
            "sha256": boundary._sha256_file(path),
        }
        if identity is not None:
            return {"id": identity, **value}
        return value

    def fixture(self) -> tuple[dict, dict]:
        producer = self.root / "identities/producer.json"
        write_json(producer, {
            "schema_version": "1.0", "id": "codex-0.144.1-windows",
            "product": "codex-cli", "version": "0.144.1",
            "launcher_sha256": "1" * 64, "entrypoint_sha256": "2" * 64,
            "package_sha256": "3" * 64, "native_executable_sha256": "4" * 64,
        })
        reviewer = self.root / "identities/reviewer.json"
        write_json(reviewer, {
            "schema_version": "1.0", "id": "codex-0.144.1-linux-x64",
            "product": "codex-cli", "version": "0.144.1", "platform": "linux",
            "arch": "x86_64", "package_tree_sha256": "5" * 64,
            "launcher": {"path": "codex", "sha256": "6" * 64},
            "entrypoint": {"path": "bin/codex.js", "sha256": "7" * 64},
            "package": {"path": "package.json", "sha256": "8" * 64},
            "native_executable": {"path": "vendor/bin/codex", "sha256": "9" * 64},
        })
        provider = self.root / "provider.json"
        write_json(provider, {
            "schema_version": "1.0", "id": "custom-zeo-responses-ultra",
            "provider_key": "custom", "display_name": "Zeo", "wire_api": "responses",
            "base_url": "https://api.payapionline.top/v1", "requires_openai_auth": True,
            "auth_source": "CODEX_HOME", "model": "gpt-5.6-sol", "reasoning_effort": "ultra",
        })
        backend = self.root / "network/backend.json"
        adapter = self.root / "network/adapter.py"
        launcher = self.root / "network/launcher.py"
        policy = self.root / "network/policy.json"
        provider_probe = self.root / "network/provider-probe.json"
        denied_probe = self.root / "network/denied-probe.json"
        for path, value in (
            (backend, {"backend": "fixture-firewall", "version": "1"}),
            (policy, {"default": "deny", "allow": ["api.payapionline.top:443"]}),
            (provider_probe, {"endpoint": "api.payapionline.top:443", "result": "allowed"}),
            (denied_probe, {"endpoint": "example.com:443", "result": "denied"}),
        ):
            write_json(path, value)
        adapter.write_text("# authenticated fixture backend adapter\n", encoding="utf-8")
        launcher.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        network = self.root / "network/boundary.json"
        document = {
            "schema_version": "1.0", "id": "pilot-provider-only-boundary",
            "policy": "provider-api-only",
            "roles": ["calibration", "producer", "reviewer"],
            "provider_profile_sha256": boundary._sha256_file(provider),
            "allowed_endpoint": {
                "scheme": "https", "host": "api.payapionline.top", "port": 443,
                "path_prefix": "/v1",
            },
            "enforcement": {
                "backend": "test-provider-boundary-v1",
                "backend_identity": self.bind(backend), "default_action": "deny",
                "launcher": {
                    "path": str(launcher.resolve()),
                    "sha256": boundary._sha256_file(launcher),
                },
                "adapter": self.bind(adapter),
                "launch_arguments": [
                    "{adapter}", "--session", "{session_id}",
                    "--role", "{role}", "{command}",
                ],
                "session_id": "fixture-session-1",
                "applies_to_process_tree": True, "dns_fail_closed": True,
            },
            "verification": {
                "policy_export": self.bind(policy), "provider_probe": self.bind(provider_probe),
                "denied_probe": self.bind(denied_probe), "provider_probe_result": "allowed",
                "denied_probe_result": "denied", "session_id": "fixture-session-1",
                "launcher_sha256": boundary._sha256_file(launcher),
                "adapter_sha256": boundary._sha256_file(adapter),
                "verified_at": "2026-08-04T00:00:00Z",
                "valid_until": "2099-08-06T00:00:00Z",
            },
        }
        write_json(network, document)
        preregistration = {
            "provider": self.bind(provider, identity="custom-zeo-responses-ultra"),
            "cli_identities": {
                "calibration_reuses": "producer",
                "producer": {
                    "status": "frozen", "platform": "windows", "arch": "x86_64",
                    "version": "0.144.1", "binding": self.bind(
                        producer, identity="codex-0.144.1-windows"
                    ), "reason": None,
                },
                "reviewer": {
                    "status": "frozen", "platform": "linux", "arch": "x86_64",
                    "version": "0.144.1", "binding": self.bind(
                        reviewer, identity="codex-0.144.1-linux-x64"
                    ), "reason": None,
                },
            },
            "execution": {
                "network_boundary": {
                    "status": "frozen",
                    "binding": self.bind(network, identity="pilot-provider-only-boundary"),
                    "reason": None,
                }
            },
        }
        return preregistration, document

    def test_schema_is_supported_and_requires_real_default_deny_proof(self) -> None:
        schema = json.loads(
            (EXPERIMENTS / "network-execution-boundary.schema.json").read_text(encoding="utf-8")
        )
        check_schema(schema)
        _, document = self.fixture()
        self.assertEqual(validate(document, schema), [])
        declarative = copy.deepcopy(document)
        declarative["enforcement"].pop("launcher")
        self.assertTrue(validate(declarative, schema))

    def test_repository_state_reports_stable_cli_and_network_blockers(self) -> None:
        preregistration = json.loads(
            (EXPERIMENTS / "pilot-preregistration.json").read_text(encoding="utf-8")
        )
        blockers = boundary.inspect_execution_blockers(preregistration, EXPERIMENTS)
        self.assertEqual([item["code"] for item in blockers], [
            "reviewer_cli_identity", "network_boundary",
        ])
        self.assertEqual(blockers[0]["state"], "unresolved")
        self.assertIn(blockers[1]["state"], {"missing", "unresolved"})
        with self.assertRaisesRegex(
            boundary.ExecutionBoundaryError,
            r"reviewer_cli_identity:unresolved",
        ):
            boundary.require_execution_ready(preregistration, EXPERIMENTS)

    def trusted_fixture(self, adapter_sha256: str):
        return mock.patch.object(
            boundary,
            "TRUSTED_LAUNCH_BACKENDS",
            {"test-provider-boundary-v1": adapter_sha256},
        )

    def test_static_self_consistent_boundary_is_not_ready_without_registered_backend(self) -> None:
        preregistration, _ = self.fixture()
        blockers = boundary.inspect_execution_blockers(preregistration, self.root)
        self.assertEqual(blockers[0]["code"], "network_boundary")
        self.assertIn("not implemented or trusted", blockers[0]["detail"])

    def test_registered_exact_provider_boundary_supplies_native_producer_prefix(self) -> None:
        preregistration, _ = self.fixture()
        document = json.loads((self.root / "network/boundary.json").read_text(encoding="utf-8"))
        adapter_hash = document["enforcement"]["adapter"]["sha256"]
        with self.trusted_fixture(adapter_hash):
            blockers = boundary.inspect_execution_blockers(
                preregistration, self.root, required_role="producer"
            )
            self.assertEqual(blockers, [])
            full_blockers = boundary.inspect_execution_blockers(preregistration, self.root)
            self.assertEqual(full_blockers[0]["code"], "network_boundary")
            self.assertIn("cannot compose the WSL reviewer launch", full_blockers[0]["detail"])
            validated = boundary.require_execution_ready(
                preregistration, self.root, required_role="producer"
            )
            prefix = boundary.launch_prefix(validated, role="producer")
        self.assertEqual(validated["document"]["policy"], "provider-api-only")
        self.assertEqual(validated["provider"]["base_url"], "https://api.payapionline.top/v1")
        self.assertEqual(prefix[-4:], ["--session", "fixture-session-1", "--role", "producer"])

    def test_role_readiness_validates_only_the_effective_cli_and_complete_pilot(self) -> None:
        preregistration, _ = self.fixture()
        document = json.loads((self.root / "network/boundary.json").read_text(encoding="utf-8"))
        adapter_hash = document["enforcement"]["adapter"]["sha256"]
        unresolved = copy.deepcopy(preregistration)
        unresolved["cli_identities"]["reviewer"] = {
            "status": "unresolved", "platform": "linux", "arch": "x86_64",
            "version": "0.144.1", "binding": None, "reason": "payload unavailable",
        }
        with self.trusted_fixture(adapter_hash):
            calibration_blockers = boundary.inspect_execution_blockers(
                unresolved, self.root, required_role="calibration"
            )
            producer_blockers = boundary.inspect_execution_blockers(
                unresolved, self.root, required_role="producer"
            )
            self.assertEqual(calibration_blockers, [])
            self.assertEqual(producer_blockers, [])
            calibration = boundary.require_execution_ready(
                unresolved, self.root, required_role="calibration"
            )
            producer = boundary.require_execution_ready(
                unresolved, self.root, required_role="producer"
            )
            self.assertEqual(set(calibration["cli_identities"]), {"producer"})
            self.assertEqual(set(producer["cli_identities"]), {"producer"})
            with self.assertRaisesRegex(
                boundary.ExecutionBoundaryError, r"reviewer_cli_identity:unresolved"
            ):
                boundary.require_execution_ready(unresolved, self.root)
            with self.assertRaisesRegex(
                boundary.ExecutionBoundaryError, r"reviewer_cli_identity:unresolved"
            ):
                boundary.require_execution_ready(
                    unresolved, self.root, required_role="reviewer"
                )

            with self.assertRaisesRegex(
                boundary.ExecutionBoundaryError, "unsupported network-bound role"
            ):
                boundary.inspect_execution_blockers(
                    unresolved, self.root, required_role="observer"
                )

    def test_v1_outer_prefix_rejects_wsl_reviewer_topology(self) -> None:
        preregistration, _ = self.fixture()
        document = json.loads((self.root / "network/boundary.json").read_text(encoding="utf-8"))
        adapter_hash = document["enforcement"]["adapter"]["sha256"]
        with self.trusted_fixture(adapter_hash):
            validated = boundary.require_execution_ready(
                preregistration, self.root, required_role="producer"
            )
            with self.assertRaisesRegex(
                boundary.ExecutionBoundaryError,
                "cannot compose the WSL reviewer launch",
            ):
                boundary.launch_prefix(validated, role="reviewer")
            with self.assertRaisesRegex(
                boundary.ExecutionBoundaryError,
                "cannot compose the WSL reviewer launch",
            ):
                boundary.prove_live_boundary(validated, role="reviewer")

    def test_live_probe_and_provider_launch_use_the_same_wrapper_session(self) -> None:
        preregistration, _ = self.fixture()
        document = json.loads((self.root / "network/boundary.json").read_text(encoding="utf-8"))
        adapter_hash = document["enforcement"]["adapter"]["sha256"]
        with self.trusted_fixture(adapter_hash):
            validated = boundary.require_execution_ready(
                preregistration, self.root, required_role="producer"
            )
            with mock.patch.object(boundary.subprocess, "run") as run:
                run.return_value.returncode = 0
                boundary.prove_live_boundary(validated, role="producer")
        self.assertEqual(run.call_count, 2)
        for call in run.call_args_list:
            command = call.args[0]
            self.assertEqual(command[1], str(self.root / "network/adapter.py"))
            self.assertEqual(
                command[2:6],
                ["--session", "fixture-session-1", "--role", "producer"],
            )
        self.assertIn("api.payapionline.top", run.call_args_list[0].args[0])
        self.assertIn("example.com", run.call_args_list[1].args[0])

    def test_registered_fake_authenticated_adapter_executes_the_child_command(self) -> None:
        preregistration, _ = self.fixture()
        adapter_path = self.root / "network/adapter.py"
        adapter_path.write_text(
            "import subprocess,sys\n"
            "args=sys.argv[1:]\n"
            "expected=['--session','fixture-session-1','--role','producer','--']\n"
            "if args[:5] != expected or len(args) == 5: raise SystemExit(91)\n"
            "raise SystemExit(subprocess.run(args[5:]).returncode)\n",
            encoding="utf-8",
            newline="\n",
        )
        network_path = self.root / "network/boundary.json"
        document = json.loads(network_path.read_text(encoding="utf-8"))
        launcher = Path(sys.executable).resolve()
        document["enforcement"]["launcher"] = {
            "path": str(launcher), "sha256": boundary._sha256_file(launcher),
        }
        document["enforcement"]["adapter"] = self.bind(adapter_path)
        document["enforcement"]["launch_arguments"] = [
            "{adapter}", "--session", "{session_id}", "--role", "{role}",
            "--", "{command}",
        ]
        document["verification"]["launcher_sha256"] = boundary._sha256_file(launcher)
        document["verification"]["adapter_sha256"] = boundary._sha256_file(adapter_path)
        write_json(network_path, document)
        preregistration["execution"]["network_boundary"]["binding"]["sha256"] = (
            boundary._sha256_file(network_path)
        )
        adapter_hash = boundary._sha256_file(adapter_path)
        with self.trusted_fixture(adapter_hash):
            validated = boundary.require_execution_ready(
                preregistration, self.root, required_role="producer"
            )
            prefix = boundary.launch_prefix(validated, role="producer")
            completed = subprocess.run(
                [
                    *prefix,
                    sys.executable,
                    "-c",
                    "import sys;sys.stdout.write('authenticated-child-ok')",
                ],
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )
        self.assertEqual(
            prefix,
            [
                str(launcher), str(adapter_path), "--session", "fixture-session-1",
                "--role", "producer", "--",
            ],
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "authenticated-child-ok")

    def test_removed_backend_and_launcher_drift_fail_closed_after_validation(self) -> None:
        preregistration, _ = self.fixture()
        document = json.loads((self.root / "network/boundary.json").read_text(encoding="utf-8"))
        adapter_hash = document["enforcement"]["adapter"]["sha256"]
        with self.trusted_fixture(adapter_hash):
            validated = boundary.require_execution_ready(
                preregistration, self.root, required_role="producer"
            )
        with self.assertRaisesRegex(boundary.ExecutionBoundaryError, "adapter drifted"):
            boundary.launch_prefix(validated, role="producer")

        launcher = Path(validated["launch"]["launcher"])
        launcher.write_text("drifted\n", encoding="utf-8")
        with self.trusted_fixture(adapter_hash):
            with self.assertRaisesRegex(boundary.ExecutionBoundaryError, "launcher drifted"):
                boundary.launch_prefix(validated, role="producer")

    def test_tool_profile_declaration_cannot_replace_network_boundary(self) -> None:
        preregistration, _ = self.fixture()
        preregistration["execution"].pop("network_boundary")
        preregistration["execution"]["tool_profile"] = {
            "id": "provider-workspace-no-publish",
            "network": "provider-api-only",
        }
        blockers = boundary.inspect_execution_blockers(preregistration, self.root)
        self.assertEqual(blockers, [{
            "code": "network_boundary", "state": "missing",
            "detail": "network execution boundary is missing",
        }])

    def test_endpoint_hash_expiry_and_denied_probe_fail_closed(self) -> None:
        cases = {}
        preregistration, _ = self.fixture()
        network_path = self.root / preregistration["execution"]["network_boundary"]["binding"]["path"]

        mismatch = json.loads(network_path.read_text(encoding="utf-8"))
        mismatch["allowed_endpoint"]["host"] = "example.com"
        cases["endpoint"] = (mismatch, "endpoint differs")

        expired = json.loads(network_path.read_text(encoding="utf-8"))
        expired["verification"]["valid_until"] = "2026-08-05T00:00:00Z"
        cases["expiry"] = (expired, "proof is expired")

        denied = json.loads(network_path.read_text(encoding="utf-8"))
        denied["verification"]["denied_probe_result"] = "allowed"
        cases["denied-probe"] = (denied, "schema validation failed")

        for name, (document, message) in cases.items():
            with self.subTest(name=name):
                current = copy.deepcopy(preregistration)
                write_json(network_path, document)
                current["execution"]["network_boundary"]["binding"]["sha256"] = boundary._sha256_file(
                    network_path
                )
                adapter_hash = document["enforcement"]["adapter"]["sha256"]
                with self.trusted_fixture(adapter_hash):
                    with self.assertRaisesRegex(boundary.ExecutionBoundaryError, message):
                        boundary._validate_boundary(current, self.root, now=NOW)
                original_preregistration, original = self.fixture()
                preregistration = original_preregistration
                network_path = self.root / preregistration["execution"]["network_boundary"]["binding"]["path"]

    def test_session_adapter_launcher_and_command_marker_drift_fail_closed(self) -> None:
        preregistration, _ = self.fixture()
        network_path = self.root / preregistration["execution"]["network_boundary"]["binding"]["path"]
        original = json.loads(network_path.read_text(encoding="utf-8"))
        cases = (
            (
                "session",
                lambda value: value["verification"].__setitem__("session_id", "other-session"),
                "different sessions",
            ),
            (
                "adapter",
                lambda value: value["verification"].__setitem__("adapter_sha256", "0" * 64),
                "adapter hash differs",
            ),
            (
                "launcher",
                lambda value: value["verification"].__setitem__("launcher_sha256", "0" * 64),
                "launcher hash differs",
            ),
            (
                "command-marker",
                lambda value: value["enforcement"].__setitem__(
                    "launch_arguments", ["{adapter}", "{command}", "after-command"]
                ),
                "must end with one exact command marker",
            ),
        )
        for label, mutate, expected in cases:
            with self.subTest(label=label):
                value = copy.deepcopy(original)
                mutate(value)
                write_json(network_path, value)
                current = copy.deepcopy(preregistration)
                current["execution"]["network_boundary"]["binding"]["sha256"] = boundary._sha256_file(
                    network_path
                )
                adapter_hash = value["enforcement"]["adapter"]["sha256"]
                with self.trusted_fixture(adapter_hash):
                    with self.assertRaisesRegex(boundary.ExecutionBoundaryError, expected):
                        boundary._validate_boundary(current, self.root, now=NOW)

    def test_hash_and_path_escape_fail_closed(self) -> None:
        preregistration, _ = self.fixture()
        drifted = copy.deepcopy(preregistration)
        drifted["execution"]["network_boundary"]["binding"]["sha256"] = "0" * 64
        blockers = boundary.inspect_execution_blockers(drifted, self.root)
        self.assertEqual(blockers[0]["code"], "network_boundary")
        self.assertIn("hash drifted", blockers[0]["detail"])

        escaped = copy.deepcopy(preregistration)
        escaped["execution"]["network_boundary"]["binding"]["path"] = "../boundary.json"
        blockers = boundary.inspect_execution_blockers(escaped, self.root)
        self.assertIn("path is unsafe", blockers[0]["detail"])


if __name__ == "__main__":
    unittest.main()
