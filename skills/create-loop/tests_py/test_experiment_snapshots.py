from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = ROOT / "skills" / "create-loop"
EXPERIMENTS = SKILL_ROOT / "tests" / "experiments"
sys.path.insert(0, str(EXPERIMENTS))

import snapshot_tools as snapshots  # noqa: E402
import freeze_experiment as freeze  # noqa: E402


EXPECTED_PILOT_INPUTS = {
    "cli-identities/codex-0.144.1-windows.json",
    "codex_exec_adapter.py",
    "interruption-evidence-manifest.schema.json",
    "network-execution-boundary.schema.json",
    "network_execution_boundary.py",
    "pilot-calibration-result.schema.json",
    "pilot-evaluator-manifest.json",
    "pilot-final-freeze.schema.json",
    "pilot-pre-calibration-freeze.schema.json",
    "pilot-preregistration.schema.json",
    "pilot-presented-artifact.schema.json",
    "pilot-run-plan.schema.json",
    "pilot-scenarios.json",
    "pilot_campaign.py",
    "pilot_freeze.py",
    "pilot_harness.py",
    "pilot_runners.py",
    "provider-profiles/custom-zeo-responses.json",
    "reviewer-isolation-manifest.schema.json",
    "reviewer_isolation.py",
    "workspace-population-seal.schema.json",
}


def run_git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


class SnapshotToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.skill = self.repo / "skills" / "create-loop"
        for name in snapshots.SUBJECT_INCLUDE:
            target = self.skill / name
            if "." in name:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(f"{name}\n", encoding="utf-8", newline="\n")
            else:
                target.mkdir(parents=True, exist_ok=True)
                (target / "seed.txt").write_text(f"{name}\n", encoding="utf-8", newline="\n")
        run_git(self.repo, "init", "-q")
        run_git(self.repo, "config", "user.name", "Snapshot Test")
        run_git(self.repo, "config", "user.email", "snapshot@example.invalid")
        run_git(self.repo, "add", ".")
        run_git(self.repo, "commit", "-qm", "baseline")
        self.head = run_git(self.repo, "rev-parse", "HEAD")

    @staticmethod
    def tree_state(root: Path) -> dict[str, tuple[int, bytes]]:
        return {
            path.relative_to(root).as_posix(): (path.stat().st_mtime_ns, path.read_bytes())
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    @staticmethod
    def no_bytecode_env() -> dict[str, str]:
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return env

    def test_strict_json_rejects_non_standard_numbers(self) -> None:
        path = Path(self.temp.name) / "bad.json"
        for value in ("NaN", "Infinity", "-Infinity"):
            path.write_text(f'{{"value":{value}}}\n', encoding="utf-8", newline="\n")
            with self.assertRaisesRegex(snapshots.SnapshotError, "non-standard JSON"):
                snapshots.load_json(path)

    def test_worktree_snapshot_is_deterministic_and_binds_head(self) -> None:
        first = snapshots.build_worktree_snapshot(
            self.skill,
            repo_root=self.repo,
            snapshot_id="candidate-v2",
            protocol="v2",
            base_git_commit=self.head,
        )
        second = snapshots.build_worktree_snapshot(
            self.skill,
            repo_root=self.repo,
            snapshot_id="candidate-v2",
            protocol="v2",
            base_git_commit=self.head,
        )
        self.assertEqual(snapshots.canonical_bytes(first), snapshots.canonical_bytes(second))
        with self.assertRaisesRegex(snapshots.SnapshotError, "must equal the repository HEAD"):
            snapshots.build_worktree_snapshot(
                self.skill,
                repo_root=self.repo,
                snapshot_id="candidate-v2",
                protocol="v2",
                base_git_commit="f" * 40,
            )

    def test_worktree_uses_git_index_modes_on_windows(self) -> None:
        script = self.skill / "scripts" / "seed.txt"
        run_git(self.repo, "update-index", "--chmod=+x", "skills/create-loop/scripts/seed.txt")
        manifest = snapshots.build_worktree_snapshot(
            self.skill,
            repo_root=self.repo,
            snapshot_id="candidate-v2",
            protocol="v2",
            base_git_commit=self.head,
        )
        entry = next(item for item in manifest["files"] if item["path"] == "scripts/seed.txt")
        self.assertEqual(entry["mode"], "0755")
        self.assertTrue(script.is_file())

    def test_source_paths_reject_windows_unmaterializable_names(self) -> None:
        manifest = snapshots.build_worktree_snapshot(
            self.skill,
            repo_root=self.repo,
            snapshot_id="candidate-v2",
            protocol="v2",
            base_git_commit=self.head,
        )
        manifest["files"][0]["path"] = "references/CON.txt"
        with self.assertRaisesRegex(snapshots.SnapshotError, "not materializable"):
            snapshots.validate_source_snapshot(manifest)

    def test_git_snapshot_is_independent_of_dirty_worktree(self) -> None:
        first, first_archive = snapshots.build_git_snapshot(
            self.repo,
            revision=self.head,
            skill_rel="skills/create-loop",
            snapshot_id="baseline-v1",
            protocol="v1",
        )
        (self.skill / "SKILL.md").write_text("dirty\n", encoding="utf-8", newline="\n")
        second, second_archive = snapshots.build_git_snapshot(
            self.repo,
            revision=self.head,
            skill_rel="skills/create-loop",
            snapshot_id="baseline-v1",
            protocol="v1",
        )
        self.assertEqual(first, second)
        self.assertEqual(first_archive, second_archive)

    def test_archive_rejects_duplicate_members(self) -> None:
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for _ in range(2):
                info = tarfile.TarInfo("SKILL.md")
                info.size = 1
                info.mode = 0o644
                info.mtime = 0
                info.uid = 0
                info.gid = 0
                archive.addfile(info, io.BytesIO(b"x"))
        manifest = {
            "schema_version": "1.0",
            "algorithm": "sha256-source-snapshot-v1",
            "snapshot_id": "baseline-v1",
            "protocol": "v1",
            "root": ".",
            "include": list(snapshots.SUBJECT_INCLUDE),
            "exclude": list(snapshots.CACHE_EXCLUDE),
            "origin": {"kind": "git-commit", "commit": self.head},
            "files": [{"path": "SKILL.md", "sha256": snapshots.sha256_bytes(b"x"), "size": 1, "mode": "0644"}],
            "aggregate_sha256": "0" * 64,
            "archive": {"format": "ustar-v1", "sha256": snapshots.sha256_bytes(output.getvalue()), "size": len(output.getvalue())},
        }
        manifest["aggregate_sha256"] = snapshots.sha256_bytes(snapshots.canonical_bytes(manifest["files"]))
        with self.assertRaisesRegex(snapshots.SnapshotError, "duplicate member"):
            snapshots.validate_source_snapshot(manifest, archive_bytes=output.getvalue())

    def test_instrument_manifest_requires_every_role_and_detects_drift(self) -> None:
        root = Path(self.temp.name) / "instrument"
        root.mkdir()
        inputs: dict[str, str] = {}
        for role in sorted(snapshots.ROLE_NAMES):
            name = f"{role}.txt"
            (root / name).write_text(role, encoding="utf-8", newline="\n")
            inputs[name] = role
        manifest = snapshots.build_instrument_manifest(root, inputs)
        snapshots.validate_instrument_manifest(root, manifest)
        (root / "harness.txt").write_text("drift", encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(snapshots.SnapshotError, "instrument file drifted"):
            snapshots.validate_instrument_manifest(root, manifest)
        manifest["files"] = [item for item in manifest["files"] if item["role"] != "harness"]
        manifest["include"] = [item["path"] for item in manifest["files"]]
        manifest["aggregate_sha256"] = snapshots.sha256_bytes(snapshots.canonical_bytes(manifest["files"]))
        with self.assertRaisesRegex(snapshots.SnapshotError, "missing required roles"):
            snapshots.validate_instrument_manifest(root, manifest)

    def test_repository_instrument_input_roles_are_complete(self) -> None:
        self.assertEqual(
            set(snapshots.EXPERIMENT_INSTRUMENT_INPUTS),
            snapshots.repository_instrument_input_paths(EXPERIMENTS),
        )
        self.assertTrue(EXPECTED_PILOT_INPUTS <= set(snapshots.EXPERIMENT_INSTRUMENT_INPUTS))
        self.assertEqual(set(snapshots.EXPERIMENT_INSTRUMENT_INPUTS.values()), snapshots.ROLE_NAMES)
        self.assertEqual(snapshots.REQUIRED_INSTRUMENT_ROLES, snapshots.ROLE_NAMES)

    def test_repository_instrument_exact_set_rejects_unclassified_asset(self) -> None:
        experiment_dir = Path(self.temp.name) / "experiment-input-set"
        for relative in snapshots.EXPERIMENT_INSTRUMENT_INPUTS:
            target = experiment_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(relative + "\n", encoding="utf-8", newline="\n")
        snapshots.validate_repository_instrument_input_set(experiment_dir)
        unexpected = experiment_dir / "pilot-new-control.schema.json"
        unexpected.write_text("{}\n", encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(snapshots.SnapshotError, "unclassified=pilot-new-control"):
            snapshots.validate_repository_instrument_input_set(experiment_dir)

    def test_instrument_manifest_hash_is_the_canonical_file_hash(self) -> None:
        root = Path(self.temp.name) / "instrument-hash"
        root.mkdir()
        inputs: dict[str, str] = {}
        for role in sorted(snapshots.ROLE_NAMES):
            name = f"{role}.txt"
            (root / name).write_text(role, encoding="utf-8", newline="\n")
            inputs[name] = role
        manifest = snapshots.build_instrument_manifest(root, inputs)
        self.assertEqual(
            snapshots.instrument_manifest_sha256(manifest),
            snapshots.sha256_bytes(snapshots.canonical_bytes(manifest)),
        )

    def test_instrument_manifest_can_bind_pending_candidate_bytes(self) -> None:
        root = Path(self.temp.name) / "instrument-override"
        root.mkdir()
        inputs: dict[str, str] = {}
        for role in sorted(snapshots.ROLE_NAMES):
            name = f"{role}.txt"
            (root / name).write_text(role, encoding="utf-8", newline="\n")
            inputs[name] = role
        pending = b"pending candidate bytes\n"
        manifest = snapshots.build_instrument_manifest(
            root,
            inputs,
            content_overrides={"fixture.txt": pending},
        )
        fixture = next(entry for entry in manifest["files"] if entry["path"] == "fixture.txt")
        self.assertEqual(fixture["sha256"], snapshots.sha256_bytes(pending))
        self.assertEqual(fixture["size"], len(pending))
        snapshots.validate_instrument_manifest(
            root,
            manifest,
            expected_inputs=inputs,
            content_overrides={"fixture.txt": pending},
        )

    def test_instrument_manifest_rejects_declared_input_set_drift(self) -> None:
        root = Path(self.temp.name) / "instrument-exact-set"
        root.mkdir()
        inputs: dict[str, str] = {}
        for role in sorted(snapshots.ROLE_NAMES):
            name = f"{role}.txt"
            (root / name).write_text(role, encoding="utf-8", newline="\n")
            inputs[name] = role
        manifest = snapshots.build_instrument_manifest(root, inputs)
        reduced = dict(inputs)
        reduced.pop("source.txt")
        with self.assertRaisesRegex(snapshots.SnapshotError, "path and role set drifted"):
            snapshots.validate_instrument_manifest(root, manifest, expected_inputs=reduced)

    def test_repository_freeze_check_is_read_only_and_current(self) -> None:
        root = EXPERIMENTS
        before = self.tree_state(root)
        result = subprocess.run(
            [sys.executable, str(root / "freeze_experiment.py"), "--check"],
            text=True,
            capture_output=True,
            check=False,
            env=self.no_bytecode_env(),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, self.tree_state(root))

    def test_compute_freeze_detects_static_instrument_drift_without_writing(self) -> None:
        for instrument_path in (
            "deterministic-fixture-catalog.json",
            "deterministic-fixture-catalog.schema.json",
            "deterministic_runner.py",
            "evaluation.py",
            "execution_guard.py",
        ):
            with self.subTest(instrument_path=instrument_path):
                experiment_dir = Path(self.temp.name) / f"experiment-drift-{Path(instrument_path).stem}"
                shutil.copytree(EXPERIMENTS, experiment_dir)
                target = experiment_dir / instrument_path
                target.write_bytes(target.read_bytes() + b"\n")
                before = self.tree_state(experiment_dir)
                expected = freeze.compute_freeze(
                    experiment_dir=experiment_dir,
                    skill_root=SKILL_ROOT,
                    repo_root=ROOT,
                )
                self.assertNotEqual(
                    expected[experiment_dir / "instrument-manifest.json"],
                    (experiment_dir / "instrument-manifest.json").read_bytes(),
                )
                self.assertEqual(before, self.tree_state(experiment_dir))

    def test_snapshot_schemas_use_supported_runtime_keywords(self) -> None:
        sample, archive = snapshots.build_git_snapshot(
            self.repo,
            revision=self.head,
            skill_rel="skills/create-loop",
            snapshot_id="baseline-v1",
            protocol="v1",
        )
        snapshots.validate_source_snapshot(sample, archive_bytes=archive)


if __name__ == "__main__":
    unittest.main()
