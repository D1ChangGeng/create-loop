#!/usr/bin/env python3
"""Launch pilot reviewers inside a WSL2 bubblewrap read-isolation boundary.

Only an anonymous review workspace, a frozen Linux Codex package, a minimal
Codex home, and the required Linux runtime are mounted.  The outer authenticated
network launcher owns provider-only egress for the complete WSL/bubblewrap
process tree; bubblewrap does not opt back into the host network explicitly.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parents[1]
import sys
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from schema_runtime import SchemaError, check_schema, validate  # noqa: E402
import network_execution_boundary as execution_boundary  # noqa: E402


SCHEMA_PATH = HERE / "reviewer-isolation-manifest.schema.json"
CLI_SCHEMA_PATH = HERE / "cli-identity.schema.json"
SANDBOX_WORKSPACE = "/workspace"
SANDBOX_OUTPUT = "/output"
SANDBOX_PACKAGE = "/opt/codex"
SANDBOX_HOME = "/home/reviewer"
SANDBOX_CODEX_HOME = f"{SANDBOX_HOME}/.codex"
ALLOWED_CODEX_HOME_FILES = ("auth.json", "config.toml")
DEFAULT_RUNTIME_ROOTS = ("/usr", "/etc/ssl", "/etc/resolv.conf", "/etc/hosts")
HIDDEN_HOST_ROOTS = ("/mnt", "/root", "/init", "/run")
NAMESPACE_FLAGS = ("user", "ipc", "pid", "uts", "cgroup")
REQUIRED_READABLE_PATHS = (
    SANDBOX_WORKSPACE,
    f"{SANDBOX_PACKAGE}/codex",
    f"{SANDBOX_CODEX_HOME}/auth.json",
    *DEFAULT_RUNTIME_ROOTS,
)
REQUIRED_READ_ONLY_MOUNTS = (
    SANDBOX_WORKSPACE,
    SANDBOX_PACKAGE,
    SANDBOX_CODEX_HOME,
    *DEFAULT_RUNTIME_ROOTS,
)


class IsolationError(RuntimeError):
    """The reviewer isolation boundary could not be proven."""


def canonical_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise IsolationError(f"isolation value is not strict canonical JSON: {exc}") from exc


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _write_new_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise IsolationError(f"immutable isolation output already exists: {path}") from exc
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(canonical_bytes(value))
        handle.flush()
        os.fsync(handle.fileno())


def _validate_manifest(value: dict[str, Any]) -> None:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        check_schema(schema)
        errors = validate(value, schema)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, SchemaError) as exc:
        raise IsolationError(f"reviewer isolation schema is unavailable: {exc}") from exc
    if errors:
        raise IsolationError("reviewer isolation manifest is invalid: " + "; ".join(errors))
    if value["namespace_flags"] != list(NAMESPACE_FLAGS):
        raise IsolationError("reviewer isolation manifest is invalid: namespace flags drifted")
    expected_mounts = {
        SANDBOX_WORKSPACE: value["workspace"],
        SANDBOX_PACKAGE: value["codex_package"],
        SANDBOX_CODEX_HOME: value["codex_home"],
    }
    if any(
        mount["sandbox_path"] != path or mount["mode"] != "read-only"
        for path, mount in expected_mounts.items()
    ):
        raise IsolationError("reviewer isolation manifest is invalid: a core mount drifted")
    runtime_roots = {item["sandbox_path"]: item for item in value["runtime_roots"]}
    if set(runtime_roots) != set(DEFAULT_RUNTIME_ROOTS) or any(
        item["mode"] != "read-only"
        or item["source_path_sha256"] != sha256_bytes(path.encode("utf-8"))
        for path, item in runtime_roots.items()
    ):
        raise IsolationError("reviewer isolation manifest is invalid: runtime root identity drifted")
    hidden_roots = value["hidden_host_roots"]
    if not set(HIDDEN_HOST_ROOTS).issubset(hidden_roots):
        raise IsolationError("reviewer isolation manifest is invalid: a required hidden root is missing")
    expected_probes = {
        **{path: "readable" for path in REQUIRED_READABLE_PATHS},
        **{path: "hidden" for path in hidden_roots},
    }
    probes = {item["path"]: item for item in value["access_probes"]}
    if len(probes) != len(value["access_probes"]) or set(probes) != set(expected_probes) or any(
        item["expected"] != expected_probes[path] or item["observed"] != expected_probes[path]
        for path, item in probes.items()
    ):
        raise IsolationError("reviewer isolation manifest is invalid: an access probe did not prove its claim")
    observed_mounts = {item["path"]: item["mode"] for item in value["mount_observations"]}
    if len(observed_mounts) != len(value["mount_observations"]) or set(observed_mounts) != set(REQUIRED_READ_ONLY_MOUNTS) or any(
        mode != "read-only" for mode in observed_mounts.values()
    ):
        raise IsolationError("reviewer isolation manifest is invalid: a required mount is not read-only")
    if value["workspace"]["source_sha256"] != sha256_bytes(canonical_bytes(value["delivered_files"])):
        raise IsolationError("reviewer isolation manifest is invalid: delivered workspace binding drifted")
    cli = value["cli_identity"]
    identity_document = {
        "schema_version": "1.0",
        "id": cli["id"],
        "product": "codex-cli",
        "version": cli["version"],
        "platform": cli["platform"],
        "arch": cli["arch"],
        "package_tree_sha256": cli["package_tree_sha256"],
        **{
            name: cli[name]
            for name in ("launcher", "entrypoint", "package", "native_executable")
        },
    }
    if (
        cli["identity_sha256"] != sha256_bytes(canonical_bytes(identity_document))
        or cli["package_tree_sha256"] != value["codex_package"]["source_sha256"]
        or cli["launcher"]["path"] != "codex"
    ):
        raise IsolationError("reviewer isolation manifest is invalid: CLI identity binding drifted")
    if value["environment"] != {
        "home": SANDBOX_HOME,
        "codex_home": SANDBOX_CODEX_HOME,
        "path": f"{SANDBOX_PACKAGE}:/usr/bin:/bin",
        "cleared": True,
    }:
        raise IsolationError("reviewer isolation manifest is invalid: environment drifted")
    core = {key: item for key, item in value.items() if key != "aggregate_sha256"}
    if value["aggregate_sha256"] != sha256_bytes(canonical_bytes(core)):
        raise IsolationError("reviewer isolation manifest is invalid: aggregate hash drifted")


def _confined_file(root: Path, relative: str, label: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts) or "\\" in relative:
        raise IsolationError(f"{label} path is unsafe")
    path = root.joinpath(*pure.parts).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise IsolationError(f"{label} escapes its root") from exc
    if not path.is_file() or path.is_symlink():
        raise IsolationError(f"{label} must be a regular non-symlink file")
    return path


def _snapshot_tree(root: Path) -> dict[str, Any]:
    if not root.is_dir() or root.is_symlink():
        raise IsolationError(f"snapshot root is missing or unsafe: {root}")
    files: list[dict[str, Any]] = []
    identities: set[str] = set()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink():
            raise IsolationError(f"isolation source contains a symlink: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        identity = relative.casefold()
        if identity in identities:
            raise IsolationError("isolation source has case-folding path collisions")
        identities.add(identity)
        files.append({"path": relative, "sha256": sha256_file(path), "size": path.stat().st_size})
    if not files:
        raise IsolationError(f"isolation source has no files: {root}")
    return {"files": files, "aggregate_sha256": sha256_bytes(canonical_bytes(files))}


def _wsl_path(path: Path, *, distribution: str, wsl_executable: str) -> str:
    completed = subprocess.run(
        [wsl_executable, "-d", distribution, "-e", "wslpath", "-a", str(path.resolve())],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise IsolationError("WSL could not translate an isolation source path")
    try:
        value = completed.stdout.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError as exc:
        raise IsolationError("WSL returned a non-UTF-8 path") from exc
    if not value.startswith("/") or "\n" in value or "\r" in value:
        raise IsolationError("WSL returned an unsafe isolation source path")
    return value


def _native_wsl_path(path: str, label: str, *, allow_interop: bool = False) -> str:
    pure = PurePosixPath(path)
    if not pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise IsolationError(f"{label} must be an absolute normalized WSL path")
    if not allow_interop and (pure == PurePosixPath("/mnt") or PurePosixPath("/mnt") in pure.parents):
        raise IsolationError(f"{label} cannot be a Windows interop mount")
    return pure.as_posix()


def hash_wsl_package(
    root: str, *, distribution: str, wsl_executable: str,
) -> dict[str, Any]:
    """Hash a frozen WSL directory without exposing its bytes to Windows."""
    root = _native_wsl_path(root, "Codex package")
    script = (
        "import hashlib,json,os,sys\n"
        "root=sys.argv[1]; out=[]\n"
        "for base,dirs,files in os.walk(root,topdown=True,followlinks=False):\n"
        "    dirs[:]=sorted(dirs); files=sorted(files)\n"
        "    for name in files:\n"
        "        p=os.path.join(base,name); rel=os.path.relpath(p,root).replace(os.sep,'/')\n"
        "        if os.path.islink(p) or not os.path.isfile(p): raise SystemExit(13)\n"
        "        h=hashlib.sha256(); size=0\n"
        "        with open(p,'rb') as f:\n"
        "            while True:\n"
        "                b=f.read(1048576)\n"
        "                if not b: break\n"
        "                h.update(b); size+=len(b)\n"
        "        out.append({'path':rel,'sha256':h.hexdigest(),'size':size})\n"
        "out.sort(key=lambda x:x['path']); raw=json.dumps(out,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()\n"
        "print(json.dumps({'files':out,'aggregate_sha256':hashlib.sha256(raw).hexdigest()},sort_keys=True,separators=(',',':')))\n"
    )
    completed = subprocess.run(
        [wsl_executable, "-d", distribution, "-e", "python3", "-c", script, root],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if completed.returncode != 0:
        raise IsolationError("cannot hash frozen WSL Codex package")
    try:
        value = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IsolationError("WSL Codex package hash output is invalid") from exc
    if not isinstance(value, dict) or not value.get("files"):
        raise IsolationError("frozen WSL Codex package is empty")
    return value


def _validate_linux_cli_identity(identity: dict[str, Any]) -> None:
    try:
        schema = json.loads(CLI_SCHEMA_PATH.read_text(encoding="utf-8"))
        check_schema(schema)
        errors = validate(identity, schema)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, SchemaError) as exc:
        raise IsolationError(f"Linux CLI identity schema is unavailable: {exc}") from exc
    if errors:
        raise IsolationError("Linux CLI identity is invalid: " + "; ".join(errors))
    if (
        identity.get("platform") != "linux"
        or identity.get("arch") != "x86_64"
        or identity.get("version") != "0.144.1"
        or identity.get("launcher", {}).get("path") != "codex"
    ):
        raise IsolationError("reviewer requires the frozen Linux Codex 0.144.1 identity")


def _verify_linux_cli_package(
    root: str,
    identity: dict[str, Any],
    *,
    distribution: str,
    wsl_executable: str,
) -> dict[str, Any]:
    _validate_linux_cli_identity(identity)
    snapshot = hash_wsl_package(root, distribution=distribution, wsl_executable=wsl_executable)
    if snapshot["aggregate_sha256"] != identity["package_tree_sha256"]:
        raise IsolationError("frozen Linux Codex package tree hash drifted")
    files = {item["path"]: item for item in snapshot["files"]}
    components = ("launcher", "entrypoint", "package", "native_executable")
    expected_paths = [identity[name]["path"] for name in components]
    if len(expected_paths) != len(set(expected_paths)):
        raise IsolationError("Linux CLI identity component paths are not unique")
    for name in components:
        component = identity[name]
        observed = files.get(component["path"])
        if observed is None or observed["sha256"] != component["sha256"]:
            raise IsolationError(f"frozen Linux Codex {name} hash drifted")
    executable_path = identity["launcher"]["path"]
    probe = subprocess.run(
        [wsl_executable, "-d", distribution, "-e", "test", "-x", root + "/" + executable_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if probe.returncode != 0:
        raise IsolationError("frozen Linux Codex launcher is not executable")
    return snapshot


def _copy_minimal_codex_home(source: Path, target: Path) -> dict[str, Any]:
    if not source.is_dir() or source.is_symlink():
        raise IsolationError("source CODEX_HOME is missing or unsafe")
    target.mkdir(parents=True, mode=0o700)
    copied = 0
    for name in ALLOWED_CODEX_HOME_FILES:
        source_path = source / name
        if not source_path.exists():
            continue
        if not source_path.is_file() or source_path.is_symlink():
            raise IsolationError(f"source CODEX_HOME {name} is unsafe")
        target_path = target / name
        shutil.copyfile(source_path, target_path)
        os.chmod(target_path, 0o600)
        copied += 1
    if not (target / "auth.json").is_file():
        raise IsolationError("minimal reviewer CODEX_HOME requires auth.json")
    if copied == 0:
        raise IsolationError("minimal reviewer CODEX_HOME is empty")
    return _snapshot_tree(target)


def codex_arguments(
    *, model: str, reasoning_effort: str, provider: dict[str, Any], output_schema: str,
    output_path: str,
) -> list[str]:
    return [
        f"{SANDBOX_PACKAGE}/codex",
        "--ask-for-approval", "never",
        "--model", model,
        "--sandbox", "workspace-write",
        "--config", f'model_provider={json.dumps(provider["provider_key"])}',
        "--config", f'model_reasoning_effort={json.dumps(reasoning_effort)}',
        "--config", f'model_providers.{provider["provider_key"]}.name={json.dumps(provider["display_name"])}',
        "--config", f'model_providers.{provider["provider_key"]}.base_url={json.dumps(provider["base_url"])}',
        "--config", f'model_providers.{provider["provider_key"]}.wire_api={json.dumps(provider["wire_api"])}',
        "--config", f'model_providers.{provider["provider_key"]}.requires_openai_auth={str(provider["requires_openai_auth"]).lower()}',
        "--config", 'web_search="disabled"',
        "--config", 'shell_environment_policy.inherit="none"',
        "exec", "--json", "--ephemeral", "--ignore-user-config", "--ignore-rules",
        "--color", "never", "--cd", SANDBOX_WORKSPACE,
        "--output-schema", output_schema,
        "--output-last-message", output_path,
        "-",
    ]


def build_bwrap_command(
    *, workspace_wsl: str, output_wsl: str, package_wsl: str, codex_home_wsl: str,
    child_command: Iterable[str], runtime_roots: Iterable[str] = DEFAULT_RUNTIME_ROOTS,
) -> list[str]:
    _native_wsl_path(package_wsl, "Codex package")
    _native_wsl_path(codex_home_wsl, "minimal CODEX_HOME", allow_interop=True)
    command = [
        "bwrap",
        "--unshare-user", "--unshare-ipc", "--unshare-pid", "--unshare-uts",
        "--unshare-cgroup", "--die-with-parent", "--new-session",
        "--ro-bind", "/usr", "/usr",
        "--symlink", "usr/bin", "/bin",
        "--symlink", "usr/lib", "/lib",
        "--symlink", "usr/lib64", "/lib64",
    ]
    for root in runtime_roots:
        source = _native_wsl_path(root, "runtime root")
        if source == "/usr":
            continue
        command.extend(("--ro-bind", source, source))
    command.extend((
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        "--dir", "/home", "--dir", SANDBOX_HOME,
        "--ro-bind", codex_home_wsl, SANDBOX_CODEX_HOME,
        "--ro-bind", package_wsl, SANDBOX_PACKAGE,
        "--ro-bind", workspace_wsl, SANDBOX_WORKSPACE,
        "--bind", output_wsl, SANDBOX_OUTPUT,
        "--clearenv",
        "--setenv", "HOME", SANDBOX_HOME,
        "--setenv", "CODEX_HOME", SANDBOX_CODEX_HOME,
        "--setenv", "PATH", f"{SANDBOX_PACKAGE}:/usr/bin:/bin",
        "--setenv", "SSL_CERT_FILE", "/etc/ssl/certs/ca-certificates.crt",
        "--setenv", "NO_COLOR", "1",
        "--chdir", SANDBOX_WORKSPACE,
        "--",
        *child_command,
    ))
    return command


def _probe_script(hidden_sentinel: str) -> str:
    hidden_path = _native_wsl_path(hidden_sentinel, "hidden sentinel", allow_interop=True)
    hidden_roots = (*HIDDEN_HOST_ROOTS, hidden_path)
    probes = [*( (path, "readable") for path in REQUIRED_READABLE_PATHS),
              *( (path, "hidden") for path in hidden_roots)]
    probe_json = json.dumps(probes, separators=(",", ":"))
    mount_paths = json.dumps(sorted(set(REQUIRED_READ_ONLY_MOUNTS)), separators=(",", ":"))
    return (
        "import json,os,sys\n"
        f"probes={probe_json}\n"
        "result=[]\n"
        "for path,expected in probes:\n"
        "    try:\n"
        "        os.listdir(path) if os.path.isdir(path) else open(path,'rb').read(1)\n"
        "        observed='readable'\n"
        "    except (FileNotFoundError,PermissionError,NotADirectoryError,OSError):\n"
        "        observed='hidden'\n"
        "    result.append({'path':path,'expected':expected,'observed':observed})\n"
        "mounts=[]\n"
        "for line in open('/proc/self/mountinfo',encoding='utf-8'):\n"
        "    fields=line.rstrip('\\n').split(' '); sep=fields.index('-')\n"
        "    target=fields[4]; options=fields[5].split(',')\n"
        f"    if target in set({mount_paths}):\n"
        "        mounts.append({'path':target,'mode':'read-only' if 'ro' in options else 'read-write'})\n"
        "document={'access_probes':result,'mount_observations':sorted(mounts,key=lambda x:x['path'])}\n"
        "open('/output/access-probes.json','w',encoding='utf-8').write(json.dumps(document,sort_keys=True,separators=(',',':'))+'\\n')\n"
        f"required={{path:'read-only' for path in {mount_paths}}}\n"
        "observed={x['path']:x['mode'] for x in mounts}\n"
        "ok=all(x['expected']==x['observed'] for x in result) and all(observed.get(k)==v for k,v in required.items())\n"
        "sys.exit(0 if ok else 97)\n"
    )


def _network_probe_script(provider_host: str) -> str:
    return (
        "import json,socket,sys\n"
        f"checks=[('provider',{json.dumps(provider_host)}),('arbitrary','example.com')]\n"
        "results=[]\n"
        "for label,host in checks:\n"
        "    try:\n"
        "        with socket.create_connection((host,443),timeout=5): pass\n"
        "        observed='allowed'\n"
        "    except OSError:\n"
        "        observed='denied'\n"
        "    results.append({'kind':label,'host':host,'observed':observed})\n"
        "open('/output/network-probes.json','w',encoding='utf-8').write(json.dumps(results,sort_keys=True,separators=(',',':'))+'\\n')\n"
        "ok=results[0]['observed']=='allowed' and results[1]['observed']=='denied'\n"
        "sys.exit(0 if ok else 98)\n"
    )


def _read_probes(path: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    if not path.is_file() or path.is_symlink():
        raise IsolationError("reviewer access probes are missing")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IsolationError(f"cannot read reviewer access probes: {exc}") from exc
    if not isinstance(value, dict) or set(value) != {"access_probes", "mount_observations"}:
        raise IsolationError("reviewer access probes have an invalid shape")
    probes = value["access_probes"]
    mounts = value["mount_observations"]
    if not isinstance(probes, list) or not probes or not isinstance(mounts, list):
        raise IsolationError("reviewer access probes have an invalid shape")
    for item in probes:
        if (
            not isinstance(item, dict) or set(item) != {"path", "expected", "observed"}
            or item["expected"] not in {"readable", "hidden"}
            or item["observed"] != item["expected"]
        ):
            raise IsolationError("reviewer access isolation was not proven")
    required_mounts = {path: "read-only" for path in REQUIRED_READ_ONLY_MOUNTS}
    observed_mounts: dict[str, str] = {}
    for item in mounts:
        if (
            not isinstance(item, dict) or set(item) != {"path", "mode"}
            or item["mode"] not in {"read-only", "read-write"}
            or item["path"] in observed_mounts
        ):
            raise IsolationError("reviewer mount observations have an invalid shape")
        observed_mounts[item["path"]] = item["mode"]
    if set(observed_mounts) != set(required_mounts) or any(
        observed_mounts.get(path) != mode for path, mode in required_mounts.items()
    ):
        raise IsolationError("reviewer mount isolation was not proven")
    return probes, mounts


def _read_network_probes(path: Path, provider_host: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise IsolationError("reviewer network probes are missing")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IsolationError(f"cannot read reviewer network probes: {exc}") from exc
    if value != [
        {"kind": "provider", "host": provider_host, "observed": "allowed"},
        {"kind": "arbitrary", "host": "example.com", "observed": "denied"},
    ]:
        raise IsolationError("reviewer provider-only network isolation was not proven")


def _run(
    command: list[str], *, prompt_path: Path, raw_path: Path, stderr_path: Path,
    timeout_seconds: int, wsl_executable: str, launch_prefix: list[str],
) -> tuple[int, bool, float]:
    if not launch_prefix or not all(isinstance(item, str) and item for item in launch_prefix):
        raise IsolationError("reviewer launch requires a verified network wrapper")
    started = time.monotonic()
    with prompt_path.open("rb") as prompt, raw_path.open("xb") as raw, stderr_path.open("xb") as stderr:
        process = subprocess.Popen(
            [*launch_prefix, wsl_executable, "-d", command[0], "--", *command[1:]],
            stdin=prompt, stdout=raw, stderr=stderr,
            env={"SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows")},
        )
        try:
            returncode = process.wait(timeout=timeout_seconds)
            timed_out = False
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            returncode = process.wait(timeout=5)
    return returncode, timed_out, time.monotonic() - started


def prepare_isolation(
    *, isolation_root: Path, workspace: Path, codex_package_wsl: str,
    cli_identity: dict[str, Any], cli_identity_sha256: str,
    source_codex_home: Path, distribution: str = "Ubuntu", wsl_executable: str = "wsl.exe",
    hidden_sentinel_wsl: str,
) -> dict[str, Any]:
    if isolation_root.exists():
        if not isolation_root.is_dir() or isolation_root.is_symlink():
            raise IsolationError("reviewer isolation root is unsafe")
        manifest_path = isolation_root.parent / "reviewer-isolation-manifest.json"
        if manifest_path.exists():
            raise IsolationError("completed reviewer isolation cannot be prepared again")
    else:
        isolation_root.mkdir(parents=True)
    output = isolation_root / "output"
    minimal_home = isolation_root / "codex-home"
    if output.exists():
        if not output.is_dir() or output.is_symlink():
            raise IsolationError("reviewer isolation output is unsafe")
    else:
        output.mkdir()
    if minimal_home.exists():
        home_snapshot = _snapshot_tree(minimal_home)
        allowed = {item["path"] for item in home_snapshot["files"]}
        if "auth.json" not in allowed or not allowed.issubset(set(ALLOWED_CODEX_HOME_FILES)):
            raise IsolationError("recovered reviewer CODEX_HOME is not minimal")
    else:
        home_snapshot = _copy_minimal_codex_home(source_codex_home, minimal_home)
    workspace_snapshot = _snapshot_tree(workspace)
    package_path = _native_wsl_path(codex_package_wsl, "Codex package")
    if (
        not isinstance(cli_identity_sha256, str)
        or len(cli_identity_sha256) != 64
        or sha256_bytes(canonical_bytes(cli_identity)) != cli_identity_sha256
    ):
        raise IsolationError("frozen Linux CLI identity hash drifted")
    package_snapshot = _verify_linux_cli_package(
        package_path,
        cli_identity,
        distribution=distribution,
        wsl_executable=wsl_executable,
    )
    return {
        "root": isolation_root,
        "output": output,
        "minimal_home": minimal_home,
        "workspace_path": workspace,
        "workspace_snapshot": workspace_snapshot,
        "home_snapshot": home_snapshot,
        "package_wsl": package_path,
        "package_snapshot": package_snapshot,
        "cli_identity": cli_identity,
        "cli_identity_sha256": cli_identity_sha256,
        "package_sha256": cli_identity["package_tree_sha256"],
        "workspace_wsl": _wsl_path(workspace, distribution=distribution, wsl_executable=wsl_executable),
        "output_wsl": _wsl_path(output, distribution=distribution, wsl_executable=wsl_executable),
        "home_wsl": _wsl_path(minimal_home, distribution=distribution, wsl_executable=wsl_executable),
        "distribution": distribution,
        "wsl_executable": wsl_executable,
        "hidden_sentinel_wsl": _native_wsl_path(hidden_sentinel_wsl, "hidden sentinel", allow_interop=True),
    }


def launch_reviewer(
    *, prepared: dict[str, Any], prompt_path: Path, output_path: Path,
    raw_path: Path, stderr_path: Path, model: str, reasoning_effort: str,
    provider: dict[str, Any], output_schema: Path, timeout_seconds: int,
    manifest_path: Path, network_boundary: dict[str, Any],
) -> tuple[int, bool, bool, float]:
    try:
        launch_prefix = execution_boundary.launch_prefix(
            network_boundary, role="reviewer"
        )
    except execution_boundary.ExecutionBoundaryError as exc:
        raise IsolationError(f"reviewer network boundary is not launchable: {exc}") from exc
    package_before = _verify_linux_cli_package(
        prepared["package_wsl"], prepared["cli_identity"],
        distribution=prepared["distribution"], wsl_executable=prepared["wsl_executable"],
    )
    if package_before["aggregate_sha256"] != prepared["package_sha256"]:
        raise IsolationError("frozen Linux Codex package drifted before reviewer launch")
    workspace_before = _snapshot_tree(prepared["workspace_path"])
    output_schema_target = f"{SANDBOX_OUTPUT}/output-schema.json"
    output_target = f"{SANDBOX_OUTPUT}/final-response.json"
    output_schema_copy = prepared["output"] / "output-schema.json"
    if output_schema_copy.exists():
        if not output_schema_copy.is_file() or output_schema_copy.is_symlink() or sha256_file(output_schema_copy) != sha256_file(output_schema):
            raise IsolationError("reviewer output schema recovery artifact drifted")
    else:
        shutil.copyfile(output_schema, output_schema_copy)
    for stale in (
        prepared["output"] / "probe-stdout.log",
        prepared["output"] / "probe-stderr.log",
        prepared["output"] / "access-probes.json",
        prepared["output"] / "network-probe-stdout.log",
        prepared["output"] / "network-probe-stderr.log",
        prepared["output"] / "network-probes.json",
    ):
        if stale.exists():
            stale.unlink()
    if (prepared["output"] / "final-response.json").exists():
        raise IsolationError("reviewer provider attempt is in doubt; provider launch is not replayed")
    child = codex_arguments(
        model=model, reasoning_effort=reasoning_effort, provider=provider,
        output_schema=output_schema_target, output_path=output_target,
    )
    bwrap = build_bwrap_command(
        workspace_wsl=prepared["workspace_wsl"], output_wsl=prepared["output_wsl"],
        package_wsl=prepared["package_wsl"], codex_home_wsl=prepared["home_wsl"],
        child_command=child,
    )
    probe = build_bwrap_command(
        workspace_wsl=prepared["workspace_wsl"], output_wsl=prepared["output_wsl"],
        package_wsl=prepared["package_wsl"], codex_home_wsl=prepared["home_wsl"],
        child_command=("/usr/bin/python3", "-c", _probe_script(prepared["hidden_sentinel_wsl"])),
    )
    probe_return, probe_timeout, _ = _run(
        [prepared["distribution"], *probe], prompt_path=prompt_path,
        raw_path=prepared["output"] / "probe-stdout.log",
        stderr_path=prepared["output"] / "probe-stderr.log", timeout_seconds=min(timeout_seconds, 30),
        wsl_executable=prepared["wsl_executable"], launch_prefix=launch_prefix,
    )
    if probe_timeout or probe_return != 0:
        raise IsolationError("reviewer access probe failed closed")
    probes, mount_observations = _read_probes(prepared["output"] / "access-probes.json")
    provider_host = network_boundary["document"]["allowed_endpoint"]["host"]
    network_probe = build_bwrap_command(
        workspace_wsl=prepared["workspace_wsl"], output_wsl=prepared["output_wsl"],
        package_wsl=prepared["package_wsl"], codex_home_wsl=prepared["home_wsl"],
        child_command=("/usr/bin/python3", "-c", _network_probe_script(provider_host)),
    )
    network_return, network_timeout, _ = _run(
        [prepared["distribution"], *network_probe], prompt_path=prompt_path,
        raw_path=prepared["output"] / "network-probe-stdout.log",
        stderr_path=prepared["output"] / "network-probe-stderr.log",
        timeout_seconds=min(timeout_seconds, 20),
        wsl_executable=prepared["wsl_executable"], launch_prefix=launch_prefix,
    )
    if network_timeout or network_return != 0:
        raise IsolationError("reviewer provider-only network probe failed closed")
    _read_network_probes(prepared["output"] / "network-probes.json", provider_host)
    returncode, timed_out, elapsed = _run(
        [prepared["distribution"], *bwrap], prompt_path=prompt_path,
        raw_path=raw_path, stderr_path=stderr_path, timeout_seconds=timeout_seconds,
        wsl_executable=prepared["wsl_executable"], launch_prefix=launch_prefix,
    )
    response_source = prepared["output"] / "final-response.json"
    if response_source.is_file() and not response_source.is_symlink():
        shutil.copyfile(response_source, output_path)
    package_after = _verify_linux_cli_package(
        prepared["package_wsl"], prepared["cli_identity"],
        distribution=prepared["distribution"], wsl_executable=prepared["wsl_executable"],
    )
    if package_after != package_before:
        raise IsolationError("frozen Linux Codex package drifted during reviewer launch")
    workspace_after = _snapshot_tree(prepared["workspace_path"])
    if workspace_after != workspace_before:
        raise IsolationError("anonymous review workspace drifted during reviewer launch")
    delivered = prepared["workspace_snapshot"]["files"]
    manifest_core = {
        "schema_version": "1.0",
        "isolation_id": f"reviewer-{sha256_bytes(canonical_bytes(delivered))[:16]}",
        "backend": "wsl2-bubblewrap",
        "distribution": prepared["distribution"],
        "network_namespace": "authenticated-provider-only-launcher",
        "namespace_flags": list(NAMESPACE_FLAGS),
        "workspace": {"sandbox_path": SANDBOX_WORKSPACE, "mode": "read-only", "source_sha256": prepared["workspace_snapshot"]["aggregate_sha256"]},
        "cli_identity": {
            "id": prepared["cli_identity"]["id"],
            "version": prepared["cli_identity"]["version"],
            "platform": prepared["cli_identity"]["platform"],
            "arch": prepared["cli_identity"]["arch"],
            "identity_sha256": prepared["cli_identity_sha256"],
            "package_tree_sha256": prepared["cli_identity"]["package_tree_sha256"],
            **{
                name: prepared["cli_identity"][name]
                for name in ("launcher", "entrypoint", "package", "native_executable")
            },
        },
        "codex_package": {"sandbox_path": SANDBOX_PACKAGE, "mode": "read-only", "source_sha256": prepared["package_snapshot"]["aggregate_sha256"]},
        "codex_home": {"sandbox_path": SANDBOX_CODEX_HOME, "mode": "read-only", "source_sha256": prepared["home_snapshot"]["aggregate_sha256"]},
        "runtime_roots": [
            {"sandbox_path": path, "mode": "read-only", "source_path_sha256": sha256_bytes(path.encode("utf-8"))}
            for path in DEFAULT_RUNTIME_ROOTS
        ],
        "hidden_host_roots": [*HIDDEN_HOST_ROOTS, prepared["hidden_sentinel_wsl"]],
        "delivered_files": delivered,
        "access_probes": probes,
        "mount_observations": mount_observations,
        "environment": {"home": SANDBOX_HOME, "codex_home": SANDBOX_CODEX_HOME, "path": f"{SANDBOX_PACKAGE}:/usr/bin:/bin", "cleared": True},
        "command_sha256": sha256_bytes(canonical_bytes(bwrap)),
        "created_at": _now_text(),
    }
    manifest = manifest_core | {"aggregate_sha256": sha256_bytes(canonical_bytes(manifest_core))}
    _validate_manifest(manifest)
    _write_new_json(manifest_path, manifest)
    return returncode, timed_out, False, elapsed


__all__ = [
    "IsolationError", "SCHEMA_PATH", "build_bwrap_command", "codex_arguments",
    "hash_wsl_package", "launch_reviewer", "prepare_isolation", "sha256_bytes", "sha256_file",
]
