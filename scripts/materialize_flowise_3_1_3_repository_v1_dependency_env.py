#!/usr/bin/env python3
"""Materialize the offline Node 24 dependency environment for the Flowise case.

This script is deliberately a trusted-control-plane build input at the same
trust level as the source materializer: every input is pinned and
digest-verified (the official Node distribution tarball against nodejs.org
SHASUMS256.txt, the frozen pnpm-lock.yaml taken from the agent-visible
target, and an exact pnpm version).  The environment itself is kept outside
both the agent-visible target and the frozen evaluator-private tree; only
its auditable metadata lands in the private tree.  Package fetching happens
during this recorded materialization only -- the class-B targeted validators
are expected to run against the finished environment with no network.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.emergent_coordination.harness.block_runner import tree_digest

CASE_ID = "flowise_3_1_3_repository_v1"
TARGET_ROOT = REPO_ROOT / "experiments/emergent_coordination/repositories" / CASE_ID
DEFAULT_ENV_ROOT = REPO_ROOT / "artifacts" / f"{CASE_ID}_dependency_env"
DEFAULT_METADATA = (
    REPO_ROOT
    / "experiments/emergent_coordination/evaluator_private"
    / CASE_ID
    / "dependency_materialization.json"
)

NODE_VERSION = "24.14.1"
NODE_DIST_BASE = f"https://nodejs.org/dist/v{NODE_VERSION}"
NODE_TARBALL_NAME = f"node-v{NODE_VERSION}-linux-x64.tar.xz"
NODE_TARBALL_URL = f"{NODE_DIST_BASE}/{NODE_TARBALL_NAME}"
NODE_SHASUMS_URL = f"{NODE_DIST_BASE}/SHASUMS256.txt"

PNPM_SPEC = "pnpm@10.26.0"
# Build-script policy is taken verbatim from the frozen snapshot's own
# package.json pnpm.onlyBuiltDependencies allowlist; the materializer must
# not widen it, because --dangerously-allow-all-builds conflicts with that
# setting and would run scripts the snapshot never approved.

SERVER_SMOKE_MODULES = ("express", "zod", "typescript")
COMPONENTS_SMOKE_MODULES = ("@langchain/core", "langchain", "typescript")


class DependencyEnvError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dependency_tree_digest(root: Path) -> str:
    """Content digest over regular files only, never following symlinks.

    pnpm workspaces link packages through a .pnpm virtual store, so the
    digest must be independent of pathlib glob symlink behaviour.
    """
    digest = hashlib.sha256()
    base = str(root)
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            if os.path.islink(full) or not os.path.isfile(full):
                continue
            relative = os.path.normpath(os.path.relpath(full, base))
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(hashlib.sha256(Path(full).read_bytes()).digest())
    return digest.hexdigest()


def _child_env(node_bin: Path, *, dead_proxy: bool = False) -> dict[str, str]:
    env = {
        "PATH": f"{node_bin}:/usr/local/bin:/usr/bin:/bin",
        "HOME": os.environ.get("HOME", str(Path.home())),
        # faiss-node's install script clones its sources with git; WSL2
        # intermittently breaks git over HTTP/2 (curl error 16).
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.version",
        "GIT_CONFIG_VALUE_0": "HTTP/1.1",
        # The snapshot is deliberately VCS-free, so the root postinstall
        # ("husky install", a dev-only git-hook setup) cannot run.
        "HUSKY": "0",
    }
    if dead_proxy:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            env[key] = "http://127.0.0.1:9"
        env["NO_PROXY"] = ""
        env["no_proxy"] = ""
    return env


def _run(
    *args: str,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    log: Path | None = None,
) -> str:
    completed = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True)
    output = (completed.stdout or "") + (completed.stderr or "")
    if log is not None:
        with log.open("a", encoding="utf-8") as handle:
            handle.write(f"$ {' '.join(args)}\n{output}\n")
    if completed.returncode:
        raise DependencyEnvError(
            f"command failed ({' '.join(args[:3])}): {output.strip()[-2000:]}"
        )
    return completed.stdout.strip()


def _download(url: str, destination: Path) -> None:
    with urllib.request.urlopen(url, timeout=120) as response:
        destination.write_bytes(response.read())


def _official_tarball_sha256(tmp: Path) -> str:
    shasums = tmp / "SHASUMS256.txt"
    _download(NODE_SHASUMS_URL, shasums)
    for line in shasums.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1] == NODE_TARBALL_NAME:
            return fields[0]
    raise DependencyEnvError(f"{NODE_TARBALL_NAME} missing from official SHASUMS256.txt")


def _extract_node_runtime(archive: Path, runtime_root: Path) -> None:
    top_dir = f"node-v{NODE_VERSION}-linux-x64"
    runtime_root.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive, "r:xz") as tar:
        for member in tar.getmembers():
            parts = Path(member.name).parts
            if not parts or parts[0] != top_dir:
                raise DependencyEnvError(f"unexpected member in node distribution: {member.name}")
            relative = Path(*parts[1:])
            if not relative.parts:
                continue
            destination = runtime_root / relative
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                destination.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                if source is None:
                    raise DependencyEnvError(f"could not read member: {member.name}")
                destination.write_bytes(source.read())
                destination.chmod(member.mode & 0o777)
            elif member.issym():
                target = os.path.normpath(os.path.join(relative.parent.as_posix(), member.linkname))
                if target.startswith("..") or os.path.isabs(target):
                    raise DependencyEnvError(f"unsafe symlink in node distribution: {member.name}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.symlink_to(member.linkname)
            else:
                raise DependencyEnvError(f"unsupported member type: {member.name} ({member.type})")


def _module_versions(node: Path, cwd: Path, modules: tuple[str, ...]) -> dict[str, str]:
    script = (
        "const out = {};"
        + "".join(
            f"out[{json.dumps(module)}] = require({json.dumps(module + '/package.json')}).version;"
            for module in modules
        )
        + "process.stdout.write(JSON.stringify(out));"
    )
    payload = _run(str(node), "-e", script, cwd=cwd)
    versions = json.loads(payload)
    missing = [module for module in modules if module not in versions]
    if missing:
        raise DependencyEnvError(f"smoke modules missing from environment: {missing}")
    return versions


def materialize(env_root: Path, metadata: Path) -> dict[str, object]:
    lockfile = TARGET_ROOT / "pnpm-lock.yaml"
    if not TARGET_ROOT.is_dir() or not lockfile.is_file():
        raise DependencyEnvError(f"frozen target or pnpm-lock.yaml missing under {TARGET_ROOT}")
    if env_root.exists():
        raise DependencyEnvError(f"refusing to overwrite existing environment: {env_root}")
    if metadata.exists():
        raise DependencyEnvError(f"refusing to overwrite existing metadata: {metadata}")
    manifest_path = REPO_ROOT / "experiments/emergent_coordination/manifests" / f"{CASE_ID}.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    target_digest = manifest["digests"]["target_tree_sha256"]
    if tree_digest(TARGET_ROOT) != target_digest:
        raise DependencyEnvError("on-disk target no longer matches the frozen manifest digest")

    lockfile_digest = _sha256_file(lockfile)
    lockfile_version = lockfile.read_text(encoding="utf-8").splitlines()[0].split(":")[-1].strip().strip("'\"")

    workspace = env_root / "workspace"
    runtime_root = env_root / "node-runtime"
    pnpm_root = env_root / "pnpm"
    logs = env_root / "logs"
    env_root.mkdir(parents=True)
    logs.mkdir()

    with tempfile.TemporaryDirectory(prefix="flowise-313-deps-") as tmp_name:
        tmp = Path(tmp_name)
        tarball = tmp / NODE_TARBALL_NAME
        _download(NODE_TARBALL_URL, tarball)
        tarball_digest = _sha256_file(tarball)
        official_digest = _official_tarball_sha256(tmp)
        if tarball_digest != official_digest:
            raise DependencyEnvError(
                f"node distribution sha256 mismatch: got {tarball_digest}, official {official_digest}"
            )
        _extract_node_runtime(tarball, runtime_root)

    node = runtime_root / "bin" / "node"
    npm_cli = runtime_root / "lib" / "node_modules" / "npm" / "bin" / "npm-cli.js"
    node_bin = runtime_root / "bin"
    if _run(str(node), "--version", env=_child_env(node_bin)) != f"v{NODE_VERSION}":
        raise DependencyEnvError("extracted node runtime reports a different version")

    _run(
        str(node), str(npm_cli), "install", "--global", f"--prefix={pnpm_root}", PNPM_SPEC,
        env=_child_env(node_bin), log=logs / "pnpm-toolchain.log",
    )
    pnpm_cli = pnpm_root / "lib" / "node_modules" / "pnpm" / "bin" / "pnpm.cjs"
    if not pnpm_cli.is_file():
        raise DependencyEnvError(f"pnpm entry point missing after install: {pnpm_cli}")
    pnpm_version = _run(str(node), str(pnpm_cli), "--version", env=_child_env(node_bin))

    shutil.copytree(TARGET_ROOT, workspace)
    workspace_preinstall_digest = tree_digest(workspace)
    if workspace_preinstall_digest != target_digest:
        shutil.rmtree(env_root, ignore_errors=True)
        raise DependencyEnvError("workspace copy diverges from the frozen target before install")

    for attempt in (1, 2):
        try:
            _run(
                str(node), str(pnpm_cli), "install", "--frozen-lockfile",
                cwd=workspace, env=_child_env(node_bin), log=logs / "pnpm-install.log",
            )
            break
        except DependencyEnvError as exc:
            if attempt == 2 or "ELIFECYCLE" not in str(exc):
                raise
            shutil.rmtree(workspace / "node_modules", ignore_errors=True)

    offline_install = _run(
        str(node), str(pnpm_cli), "install", "--frozen-lockfile", "--offline",
        cwd=workspace, env=_child_env(node_bin, dead_proxy=True), log=logs / "offline-check.log",
    )
    server_versions = _module_versions(node, workspace / "packages" / "server", SERVER_SMOKE_MODULES)
    components_versions = _module_versions(
        node, workspace / "packages" / "components", COMPONENTS_SMOKE_MODULES
    )
    jest_cli = workspace / "packages" / "components" / "node_modules" / "jest" / "bin" / "jest.js"
    jest_version = _run(
        str(node), str(jest_cli), "--version", cwd=workspace / "packages" / "components",
        env=_child_env(node_bin), log=logs / "smoke.log",
    )

    payload: dict[str, object] = {
        "schema_version": 1,
        "case_id": CASE_ID,
        "purpose": (
            "offline, snapshot-matched Node 24 dependency environment for the five class-B "
            "targeted validators; package fetching happens only during this recorded "
            "trusted-control-plane materialization, validation runs with no network"
        ),
        "as_of": "2026-09-18",
        "environment_root": env_root.relative_to(REPO_ROOT).as_posix(),
        "target_binding": {
            "target_root": TARGET_ROOT.relative_to(REPO_ROOT).as_posix(),
            "target_tree_sha256": target_digest,
            "workspace_preinstall_tree_sha256": workspace_preinstall_digest,
            "pnpm_lockfile": {
                "path": "pnpm-lock.yaml",
                "sha256": lockfile_digest,
                "lockfile_version": lockfile_version,
            },
        },
        "node_runtime": {
            "version": NODE_VERSION,
            "distribution": NODE_TARBALL_URL,
            "shasums": NODE_SHASUMS_URL,
            "tarball_sha256": tarball_digest,
            "verified_against_official_shasums": True,
            "runtime_tree_sha256": dependency_tree_digest(runtime_root),
        },
        "pnpm": {
            "spec": PNPM_SPEC,
            "version": pnpm_version,
            "toolchain_tree_sha256": dependency_tree_digest(pnpm_root),
        },
        "install": {
            "command": "pnpm install --frozen-lockfile",
            "build_script_policy": "frozen snapshot package.json pnpm.onlyBuiltDependencies allowlist",
            "env_overrides": ["HUSKY=0", "git http.version=HTTP/1.1"],
            "network_use": "package fetch during materialization only",
        },
        "node_modules_tree_sha256": dependency_tree_digest(workspace / "node_modules"),
        "offline_smoke": {
            "node_version": f"v{NODE_VERSION}",
            "pnpm_offline_install": offline_install.splitlines()[-1] if offline_install else "",
            "server_module_versions": server_versions,
            "components_module_versions": components_versions,
            "components_jest_version": jest_version,
        },
        "materializer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--environment", type=Path, default=DEFAULT_ENV_ROOT,
        help="new dependency environment directory (default: artifacts/<case>_dependency_env)",
    )
    parser.add_argument(
        "--metadata", type=Path, default=DEFAULT_METADATA,
        help="new private dependency materialization JSON (default: evaluator-private location)",
    )
    args = parser.parse_args()
    try:
        payload = materialize(args.environment.resolve(), args.metadata.resolve())
    except DependencyEnvError as exc:
        raise SystemExit(f"dependency environment materialization failed: {exc}") from exc
    print(json.dumps(
        {
            key: payload[key]
            for key in ("environment_root", "node_modules_tree_sha256", "pnpm", "offline_smoke")
        },
        ensure_ascii=False, sort_keys=True, indent=1,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
