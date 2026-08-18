from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = SKILL_ROOT / "tests" / "experiments"
sys.path.insert(0, str(EXPERIMENTS))
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import deterministic_runner as runner  # noqa: E402
import freeze_experiment  # noqa: E402
from schema_runtime import validate  # noqa: E402


class DeterministicRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_catalog_parses_the_captured_bytes(self) -> None:
        captured = (EXPERIMENTS / "deterministic-fixture-catalog.json").read_bytes()
        catalog = runner.load_catalog_bytes(captured)
        self.assertEqual([case["case_id"] for case in catalog["cases"]], ["accept-control", "reject-control"])

    def test_catalog_does_not_reopen_the_path_after_byte_capture(self) -> None:
        path = self.root / "catalog.json"
        path.write_bytes((EXPERIMENTS / "deterministic-fixture-catalog.json").read_bytes())
        original = Path.read_bytes
        reads = 0

        def read_once(candidate: Path) -> bytes:
            nonlocal reads
            if candidate == path:
                reads += 1
                if reads > 1:
                    raise AssertionError("catalog path reopened")
            return original(candidate)

        with mock.patch.object(Path, "read_bytes", read_once):
            runner.load_catalog(path)
        self.assertEqual(reads, 1)

    def test_run_rejects_a_runner_label_with_different_bytes(self) -> None:
        fake_runner = self.root / "runner.py"
        fake_runner.write_text("# not the imported runner\n", encoding="utf-8", newline="\n")
        preregistration = runner.load_json(EXPERIMENTS / "preregistration.json")
        with self.assertRaisesRegex(runner.DeterministicRunnerError, "do not match the imported"):
            runner.run_suite(
                EXPERIMENTS,
                preregistration,
                "v2",
                catalog_path=EXPERIMENTS / "deterministic-fixture-catalog.json",
                tool_profile_path=EXPERIMENTS / "tool-profiles" / "local-full-no-publish.json",
                candidate_skill_root=SKILL_ROOT,
                runner_path=fake_runner,
            )

    def test_run_rejects_a_tool_profile_not_bound_by_preregistration(self) -> None:
        profile = json.loads((EXPERIMENTS / "tool-profiles" / "local-full-no-publish.json").read_text(encoding="utf-8"))
        self.assertEqual(profile["environment"]["credential_allow"], [])
        profile["id"] = "different-profile"
        path = self.root / "tool-profile.json"
        path.write_text(json.dumps(profile) + "\n", encoding="utf-8", newline="\n")
        preregistration = runner.load_json(EXPERIMENTS / "preregistration.json")
        with self.assertRaisesRegex(runner.DeterministicRunnerError, "path drifted|hash drifted|ID drifted"):
            runner.run_suite(
                EXPERIMENTS,
                preregistration,
                "v2",
                catalog_path=EXPERIMENTS / "deterministic-fixture-catalog.json",
                tool_profile_path=path,
                candidate_skill_root=SKILL_ROOT,
            )

    def minimal_captured_source(
        self,
        validator: bytes,
        *,
        helper: bytes | None = None,
        schema: bytes | None = None,
        fixture: bytes = b"{}\n",
    ) -> tuple[dict, dict[str, bytes], dict]:
        captured = {
            "scripts/validate_loop_dir.py": validator,
            "examples/fixture/goal.json": fixture,
        }
        if helper is not None:
            captured["scripts/helper.py"] = helper
        if schema is not None:
            captured["schemas/test.json"] = schema
        entries = [
            {
                "path": path,
                "sha256": runner.sha256_bytes(data),
                "size": len(data),
                "mode": "0644",
            }
            for path, data in sorted(captured.items())
        ]
        manifest = {"files": entries, "aggregate_sha256": runner.sha256_bytes(runner.canonical_bytes(entries))}
        case = {
            "case_id": "control",
            "expected": "accept",
            "protocols": {
                "v2": {
                    "validator": "validate_loop_dir",
                    "fixture": "examples/fixture",
                    "mutation": "none",
                }
            },
        }
        return manifest, captured, case

    def run_minimal_case(
        self,
        manifest: dict,
        captured: dict[str, bytes],
        case: dict,
        *,
        live_root: Path | None = None,
        swaps: dict[str, bytes] | None = None,
    ) -> dict:
        environment = runner._subprocess_environment(
            runner._load_tool_profile(EXPERIMENTS / "tool-profiles" / "local-full-no-publish.json"),
            "v2",
        )
        original_run = subprocess.run

        def swap_and_restore(command, **kwargs):
            originals: dict[Path, bytes] = {}
            if live_root is not None:
                for relative, replacement in (swaps or {}).items():
                    path = live_root / Path(*relative.split("/"))
                    originals[path] = path.read_bytes()
                    path.write_bytes(replacement)
            try:
                return original_run(command, **kwargs)
            finally:
                for path, data in originals.items():
                    path.write_bytes(data)

        run_context = (
            mock.patch.object(runner.subprocess, "run", side_effect=swap_and_restore)
            if live_root is not None
            else mock.patch.object(runner.subprocess, "run", wraps=original_run)
        )
        with run_context:
            return runner._run_case(
                manifest,
                captured,
                case,
                "v2",
                environment,
                (EXPERIMENTS / "deterministic-case-result.schema.json").read_bytes(),
            )

    def materialize_live_source(self, captured: dict[str, bytes]) -> Path:
        root = self.root / "live-source"
        for relative, data in captured.items():
            target = root / Path(*relative.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        return root

    def exposed_source_swap(self, relative: str, replacement: bytes, *, delegate=None):
        original_run = delegate or subprocess.run
        touched: list[Path] = []

        def swap_and_restore(command, **kwargs):
            target = None
            original = None
            if len(command) >= 5:
                scripts = Path(command[-2])
                if scripts.name == "scripts" and scripts.is_dir():
                    candidate = scripts.parent / Path(*relative.split("/"))
                    if candidate.is_file():
                        target = candidate
                        original = target.read_bytes()
                        target.write_bytes(replacement)
                        touched.append(target)
            try:
                return original_run(command, **kwargs)
            finally:
                if target is not None and original is not None:
                    target.write_bytes(original)

        return swap_and_restore, touched

    def test_run_accepts_same_profile_and_runner_bytes_at_staged_paths(self) -> None:
        staged_profile = self.root / "profile.json"
        staged_runner = self.root / "runner.py"
        shutil.copyfile(EXPERIMENTS / "tool-profiles" / "local-full-no-publish.json", staged_profile)
        staged_runner.write_bytes(runner.IMPORTED_RUNNER_BYTES)
        preregistration = runner.load_json(EXPERIMENTS / "preregistration.json")
        result = runner.run_suite(
            EXPERIMENTS,
            preregistration,
            "v2",
            catalog_path=EXPERIMENTS / "deterministic-fixture-catalog.json",
            tool_profile_path=staged_profile,
            candidate_skill_root=SKILL_ROOT,
            runner_path=staged_runner,
        )
        self.assertEqual(result["tool_profile_sha256"], preregistration["execution_config"]["tool_profile"]["sha256"])
        self.assertEqual(result["runner_sha256"], runner.IMPORTED_RUNNER_SHA256)

    def test_run_rejects_result_schema_not_bound_by_instrument(self) -> None:
        experiment = self.root / "experiment"
        shutil.copytree(EXPERIMENTS, experiment)
        schema = experiment / "deterministic-case-result.schema.json"
        schema.write_text('{"type":"object"}\n', encoding="utf-8", newline="\n")
        preregistration = runner.load_json(experiment / "preregistration.json")
        with self.assertRaisesRegex(runner.DeterministicRunnerError, "case-result schema is not the frozen"):
            runner.run_suite(
                experiment,
                preregistration,
                "v2",
                catalog_path=experiment / "deterministic-fixture-catalog.json",
                tool_profile_path=experiment / "tool-profiles" / "local-full-no-publish.json",
                candidate_skill_root=SKILL_ROOT,
            )

    def test_run_binds_imported_runner_bytes_not_changed_module_file(self) -> None:
        staged_runner = self.root / "runner.py"
        staged_runner.write_bytes(b"# replacement after import\n")
        preregistration = runner.load_json(EXPERIMENTS / "preregistration.json")
        with self.assertRaisesRegex(runner.DeterministicRunnerError, "do not match the imported"):
            runner.run_suite(
                EXPERIMENTS,
                preregistration,
                "v2",
                catalog_path=EXPERIMENTS / "deterministic-fixture-catalog.json",
                tool_profile_path=EXPERIMENTS / "tool-profiles" / "local-full-no-publish.json",
                candidate_skill_root=SKILL_ROOT,
                runner_path=staged_runner,
            )

    def test_v1_environment_denials_are_case_insensitive(self) -> None:
        profile = runner._load_tool_profile(EXPERIMENTS / "tool-profiles" / "local-full-no-publish.json")
        with (
            mock.patch.dict(
                os.environ,
                {
                    "PATH": os.environ.get("PATH", ""),
                    "openai_token": "secret",
                    "AWS_TEST": "secret",
                    "PYTHONIOENCODING": "latin-1",
                },
                clear=True,
            ),
            mock.patch.object(runner.site, "ENABLE_USER_SITE", True),
            mock.patch.object(runner.site, "getusersitepackages", return_value="user-site"),
        ):
            environment = runner._subprocess_environment(profile, "v1")
        self.assertNotIn("openai_token", environment)
        self.assertNotIn("AWS_TEST", environment)
        self.assertEqual(environment["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(environment["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertEqual(environment["PYTHONPATH"], "user-site")
        self.assertLessEqual(set(environment), {"PATH", "PYTHONIOENCODING", "PYTHONDONTWRITEBYTECODE", "PYTHONPATH"})

    def test_v2_environment_excludes_user_site_and_uses_isolated_imports(self) -> None:
        profile = runner._load_tool_profile(EXPERIMENTS / "tool-profiles" / "local-full-no-publish.json")
        with (
            mock.patch.dict(os.environ, {"PATH": os.environ.get("PATH", "")}, clear=True),
            mock.patch.object(runner.site, "ENABLE_USER_SITE", True),
            mock.patch.object(runner.site, "getusersitepackages", side_effect=AssertionError("user site queried for v2")),
        ):
            environment = runner._subprocess_environment(profile, "v2")
        self.assertNotIn("PYTHONPATH", environment)

        manifest, captured, case = self.minimal_captured_source(b"raise SystemExit(0)\n")
        completed = mock.Mock(returncode=0)
        with mock.patch.object(runner.subprocess, "run", return_value=completed) as run:
            runner._run_case(
                manifest,
                captured,
                case,
                "v2",
                environment,
                (EXPERIMENTS / "deterministic-case-result.schema.json").read_bytes(),
            )
        self.assertEqual(run.call_args.args[0][:3], [sys.executable, "-s", "-c"])
        payload = json.loads(run.call_args.kwargs["input"])
        validator = next(item for item in payload["source_files"] if item["path"] == "scripts/validate_loop_dir.py")
        self.assertEqual(runner.base64.b64decode(validator["data"]), b"raise SystemExit(0)\n")
        self.assertNotIn("cwd", run.call_args.kwargs)
        self.assertEqual(len(run.call_args.args[0]), 4)

    def test_transient_validator_swap_cannot_change_executed_bytes(self) -> None:
        manifest, captured, case = self.minimal_captured_source(b"raise SystemExit(1)\n")
        case["expected"] = "reject"
        live_root = self.materialize_live_source(captured)
        with mock.patch.object(runner.subprocess, "run", wraps=subprocess.run) as run:
            result = self.run_minimal_case(
                manifest,
                captured,
                case,
                live_root=live_root,
                swaps={"scripts/validate_loop_dir.py": b"raise SystemExit(0)\n"},
            )
        self.assertEqual(result["actual"], "reject")
        self.assertEqual((live_root / "scripts" / "validate_loop_dir.py").read_bytes(), captured["scripts/validate_loop_dir.py"])

    def test_transient_imported_module_swap_cannot_change_executed_bytes(self) -> None:
        manifest, captured, case = self.minimal_captured_source(
            b"import helper\nraise SystemExit(helper.exit_code())\n",
            helper=b"def exit_code():\n    return 1\n",
        )
        case["expected"] = "reject"
        swap, touched = self.exposed_source_swap("scripts/helper.py", b"def exit_code():\n    return 0\n")
        with mock.patch.object(runner.subprocess, "run", side_effect=swap):
            result = runner._run_case(
                manifest,
                captured,
                case,
                "v2",
                runner._subprocess_environment(
                    runner._load_tool_profile(EXPERIMENTS / "tool-profiles" / "local-full-no-publish.json"),
                    "v2",
                ),
                (EXPERIMENTS / "deterministic-case-result.schema.json").read_bytes(),
            )
        self.assertEqual(result["actual"], "reject")
        self.assertEqual(touched, [])
        payload_helper = next(item for item in runner._execution_source_files(manifest, captured) if item["path"] == "scripts/helper.py")
        self.assertEqual(runner.base64.b64decode(payload_helper["data"]), captured["scripts/helper.py"])

    def test_transient_schema_swap_cannot_change_executed_bytes(self) -> None:
        validator = (
            b"import json\nfrom pathlib import Path\n"
            b"schema = json.loads((Path(__file__).parent.parent / 'schemas' / 'test.json').read_text())\n"
            b"raise SystemExit(schema['exit_code'])\n"
        )
        manifest, captured, case = self.minimal_captured_source(validator, schema=b'{"exit_code":1}\n')
        case["expected"] = "reject"
        swap, touched = self.exposed_source_swap("schemas/test.json", b'{"exit_code":0}\n')
        with mock.patch.object(runner.subprocess, "run", side_effect=swap):
            result = runner._run_case(
                manifest,
                captured,
                case,
                "v2",
                runner._subprocess_environment(
                    runner._load_tool_profile(EXPERIMENTS / "tool-profiles" / "local-full-no-publish.json"),
                    "v2",
                ),
                (EXPERIMENTS / "deterministic-case-result.schema.json").read_bytes(),
            )
        self.assertEqual(result["actual"], "reject")
        self.assertEqual(touched, [])
        payload_schema = next(item for item in runner._execution_source_files(manifest, captured) if item["path"] == "schemas/test.json")
        self.assertEqual(runner.base64.b64decode(payload_schema["data"]), captured["schemas/test.json"])

    def test_swap_helper_changes_the_legacy_live_source_result(self) -> None:
        root = self.materialize_live_source(
            {"scripts/helper.py": b"def exit_code():\n    return 1\n"}
        )
        validator = root / "scripts" / "validate_loop_dir.py"
        validator.write_text(
            "import helper\nraise SystemExit(helper.exit_code())\n",
            encoding="utf-8",
            newline="\n",
        )
        launcher = (
            "import runpy, sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "runpy.run_path(sys.argv[2], run_name='__main__')\n"
        )
        command = [sys.executable, "-B", "-s", "-c", launcher, str(root / "scripts"), str(validator)]
        control = subprocess.run(command, check=False, capture_output=True, text=True)
        self.assertEqual(control.returncode, 1)

        replacement = b"def exit_code():\n    return 0\n"
        swap, touched = self.exposed_source_swap("scripts/helper.py", replacement)
        exposed = swap(command, check=False, capture_output=True, text=True)
        self.assertEqual(exposed.returncode, 0)
        self.assertEqual(touched, [root / "scripts" / "helper.py"])
        self.assertEqual(
            (root / "scripts" / "helper.py").read_bytes(),
            b"def exit_code():\n    return 1\n",
        )

    def test_run_suite_exposes_no_parent_source_tree_to_subprocess_swap(self) -> None:
        experiment = self.root / "experiment"
        shutil.copytree(EXPERIMENTS, experiment)
        expected = freeze_experiment.compute_freeze(
            experiment_dir=experiment,
            skill_root=SKILL_ROOT,
            repo_root=SKILL_ROOT.parents[1],
        )
        for path, data in expected.items():
            path.write_bytes(data)
        swap, touched = self.exposed_source_swap(
            "scripts/project_loop.py",
            b"raise RuntimeError('transient exposed-source swap')\n",
        )

        with mock.patch.object(runner.subprocess, "run", side_effect=swap):
            result = runner.run_suite(
                experiment,
                runner.load_json(experiment / "preregistration.json"),
                "v2",
                catalog_path=experiment / "deterministic-fixture-catalog.json",
                tool_profile_path=experiment / "tool-profiles" / "local-full-no-publish.json",
                candidate_skill_root=SKILL_ROOT,
                runner_path=EXPERIMENTS / "deterministic_runner.py",
            )

        self.assertEqual(
            [(case["case_id"], case["actual"]) for case in result["cases"]],
            [("accept-control", "accept"), ("reject-control", "reject")],
        )
        self.assertEqual(touched, [])

    def test_transient_fixture_swap_cannot_change_executed_bytes(self) -> None:
        manifest, captured, case = self.minimal_captured_source(
            b"import json, sys\nfrom pathlib import Path\n"
            b"raise SystemExit(0 if json.loads((Path(sys.argv[1]) / 'goal.json').read_text()).get('original') else 1)\n",
            fixture=b'{"original":true}\n',
        )
        live_root = self.materialize_live_source(captured)
        result = self.run_minimal_case(
            manifest,
            captured,
            case,
            live_root=live_root,
            swaps={"examples/fixture/goal.json": b'{"replacement":true}\n'},
        )
        self.assertEqual(result["actual"], "accept")

    def test_validator_cannot_mutate_executed_fixture(self) -> None:
        manifest, captured, case = self.minimal_captured_source(
            b"import sys\nfrom pathlib import Path\n"
            b"(Path(sys.argv[1]) / 'goal.json').write_text('{\"mutated\":true}\\n')\nraise SystemExit(0)\n"
        )
        with self.assertRaisesRegex(runner.DeterministicRunnerError, "mutated its executed fixture"):
            self.run_minimal_case(manifest, captured, case)

    def test_validator_cannot_mutate_captured_source_tree(self) -> None:
        manifest, captured, case = self.minimal_captured_source(
            b"from pathlib import Path\n"
            b"(Path(__file__).parent / 'helper.py').write_text('changed\\n')\nraise SystemExit(0)\n",
            helper=b"original\n",
        )
        with self.assertRaisesRegex(runner.DeterministicRunnerError, "mutated its captured source tree"):
            self.run_minimal_case(manifest, captured, case)

    def test_actual_run_suite_result_matches_authoritative_schema(self) -> None:
        result = runner.run_suite(
            EXPERIMENTS,
            runner.load_json(EXPERIMENTS / "preregistration.json"),
            "v2",
            catalog_path=EXPERIMENTS / "deterministic-fixture-catalog.json",
            tool_profile_path=EXPERIMENTS / "tool-profiles" / "local-full-no-publish.json",
            candidate_skill_root=SKILL_ROOT,
        )
        schema = runner.load_json(EXPERIMENTS / "deterministic-authoritative-run.schema.json")
        self.assertEqual(validate(result, schema), [])

    def test_authoritative_cli_shapes_have_independent_schemas(self) -> None:
        case_schema = runner.load_json(EXPERIMENTS / "deterministic-case-result.schema.json")
        run_schema = runner.load_json(EXPERIMENTS / "deterministic-authoritative-run.schema.json")
        sample_case = {
            "schema_version": "1.0",
            "algorithm": "create-loop-deterministic-case-result-v1",
            "case_id": "accept-control",
            "protocol": "v2",
            "expected": "accept",
            "actual": "accept",
            "validator": {"id": "validate_loop_dir", "sha256": "0" * 64},
            "source_fixture_sha256": "1" * 64,
            "executed_fixture_sha256": "2" * 64,
            "returncode": 0,
        }
        sample_run = {
            "schema_version": "1.0",
            "algorithm": "create-loop-deterministic-validator-run-v1",
            "experiment_id": "experiment",
            "preregistration_sha256": "3" * 64,
            "protocol": "v2",
            "source_sha256": "4" * 64,
            "fixture_catalog_sha256": "5" * 64,
            "runner_sha256": "6" * 64,
            "tool_profile_sha256": "7" * 64,
            "cases": [sample_case, {**sample_case, "case_id": "reject-control", "expected": "reject", "actual": "reject", "returncode": 1}],
        }
        self.assertEqual(validate(sample_case, case_schema), [])
        self.assertEqual(validate(sample_run, run_schema), [])
        submission_schema = runner.load_json(EXPERIMENTS / "deterministic-suite-result.schema.json")
        self.assertTrue(validate(sample_run, submission_schema))


if __name__ == "__main__":
    unittest.main()
