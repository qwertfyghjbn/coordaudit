from __future__ import annotations

import hashlib
import os
import shutil
import stat
from pathlib import Path
from typing import Iterable

from experiments.emergent_coordination.harness.paths import agent_id_for


FORBIDDEN_TARGET_NAMES = {
    "ground_truth.json",
    "case.yaml",
    "provenance.json",
}


class WorkspaceLayout:
    def __init__(self, run_dir: Path, agent_count: int):
        # CLI callers may pass a relative --runs-dir. Tool resolution uses
        # absolute paths, so the workspace root must use the same convention.
        self.run_dir = Path(run_dir).resolve()
        self.agent_count = agent_count
        self.runtime = self.run_dir / "runtime"
        self.shared = self.runtime / "shared"
        self.private_root = self.runtime / "private"
        self.target_root = self.runtime / "target"
        self.evaluator_private = self.run_dir / "evaluator_private"
        self.logs = self.run_dir / "logs"
        self.artifacts = self.run_dir / "artifacts"

    def agent_private(self, agent_id: str) -> Path:
        return self.private_root / agent_id

    def agent_target(self, agent_id: str) -> Path:
        return self.agent_private(agent_id) / "target"

    def agent_scratch(self, agent_id: str) -> Path:
        return self.agent_private(agent_id) / "scratch"

    def agent_ids(self) -> list[str]:
        return [agent_id_for(index) for index in range(1, self.agent_count + 1)]


def _copy_tree(src: Path, dst: Path, *, ignore_names: Iterable[str] = ()) -> None:
    ignore = set(ignore_names)
    dst.mkdir(parents=True, exist_ok=True)
    for root, dirs, files in os.walk(src):
        rel = Path(root).relative_to(src)
        dirs[:] = [
            name
            for name in dirs
            if name not in ignore and name != "__pycache__" and name != ".git"
        ]
        target_dir = dst / rel
        target_dir.mkdir(parents=True, exist_ok=True)
        for name in files:
            if name in ignore or name.endswith(".pyc"):
                continue
            shutil.copy2(Path(root) / name, target_dir / name)


def prepare_run_workspace(
    run_dir: Path,
    source_target: Path,
    agent_count: int,
    *,
    ground_truth: Path | None = None,
    provenance: Path | None = None,
) -> WorkspaceLayout:
    layout = WorkspaceLayout(run_dir, agent_count)
    layout.runtime.mkdir(parents=True, exist_ok=True)
    layout.shared.mkdir(parents=True, exist_ok=True)
    layout.private_root.mkdir(parents=True, exist_ok=True)
    layout.logs.mkdir(parents=True, exist_ok=True)
    layout.artifacts.mkdir(parents=True, exist_ok=True)
    layout.evaluator_private.mkdir(parents=True, exist_ok=True)

    _copy_tree(source_target, layout.target_root, ignore_names=FORBIDDEN_TARGET_NAMES)
    if ground_truth is not None and ground_truth.exists():
        shutil.copy2(ground_truth, layout.evaluator_private / "ground_truth.json")
    if provenance is not None and provenance.exists():
        shutil.copy2(provenance, layout.evaluator_private / "provenance.json")

    for agent_id in layout.agent_ids():
        private = layout.agent_private(agent_id)
        private.mkdir(parents=True, exist_ok=True)
        layout.agent_scratch(agent_id).mkdir(parents=True, exist_ok=True)
        _copy_tree(layout.target_root, layout.agent_target(agent_id))

    _lock_down_evaluator_private(layout.evaluator_private)
    return layout


def prepare_finalizer_workspace(layout: WorkspaceLayout, agent_id: str = "team_finalizer") -> Path:
    """Create the post-terminal finalizer's private target copy.

    Idempotent: called after every search agent is terminal, it only adds the
    finalizer's own directory under the existing private root and copies the
    same frozen target tree the search agents received.
    """
    private = layout.agent_private(agent_id)
    if layout.agent_target(agent_id).exists():
        return private
    private.mkdir(parents=True, exist_ok=True)
    layout.agent_scratch(agent_id).mkdir(parents=True, exist_ok=True)
    _copy_tree(layout.target_root, layout.agent_target(agent_id))
    return private


def _lock_down_evaluator_private(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))
