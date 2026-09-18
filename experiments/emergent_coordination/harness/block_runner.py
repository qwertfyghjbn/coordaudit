"""Create an immutable evidence record for a matched N=4 block.

Freezing does not execute Agents. The runtime hardening gates are enforced by
the single-run runtime; this module remains deliberately unable to authorize,
bind, or schedule a complete live matched block.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from experiments.emergent_coordination.harness.contract import BlockConfig
from experiments.emergent_coordination.harness.cases import load_case
from experiments.emergent_coordination.harness.paths import EXPERIMENT_ROOT, REPO_ROOT
from experiments.emergent_coordination.harness.prompts import base_prompt, system_prompt, user_prompt
from experiments.emergent_coordination.harness.tools.specs import tools_for_mode


class BlockRunnerError(RuntimeError):
    pass


@dataclass(frozen=True)
class FrozenBlock:
    block_dir: Path
    manifest_path: Path
    manifest_hash: str


class BlockRunner:
    def __init__(self, config: BlockConfig, blocks_root: Path):
        config.validate()
        self.config = config
        self.blocks_root = Path(blocks_root)

    def freeze(self, block_id: str) -> FrozenBlock:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", block_id):
            raise BlockRunnerError("block id must contain only letters, digits, dots, underscores, or hyphens")
        block_dir = self.blocks_root / block_id
        if block_dir.exists():
            raise BlockRunnerError(f"refusing to overwrite existing block: {block_id}")

        manifest = self._build_manifest(block_id)
        encoded = _canonical_json(manifest)
        manifest["manifest_hash"] = _sha256_text(encoded)
        block_dir.mkdir(parents=True, exist_ok=False)
        manifest_path = block_dir / "block_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return FrozenBlock(block_dir=block_dir, manifest_path=manifest_path, manifest_hash=manifest["manifest_hash"])

    def _build_manifest(self, block_id: str) -> dict[str, Any]:
        case = load_case(self.config.repository_id)
        condition_hashes: dict[str, dict[str, str]] = {}
        for condition in self.config.conditions:
            system = system_prompt(condition.mode, "agent_001", case.prompt_profile)
            user = user_prompt(condition.mode, "agent_001", condition.agent_count, case.prompt_profile)
            condition_hashes[condition.id] = {
                "system_prompt": _sha256_text(system),
                "user_prompt": _sha256_text(user),
                "tool_schema": _sha256_json(tools_for_mode(condition.mode, case.finding_schema)),
            }
        common, schema = base_prompt(case.prompt_profile)
        return {
            "schema_version": 1,
            "block_id": block_id,
            "frozen_at": datetime.now(timezone.utc).isoformat(),
            "contract": self.config.as_dict(),
            "hashes": {
                "common_prompt": _sha256_text(common + "\n" + schema),
                "conditions": condition_hashes,
                "source_config": _sha256_json(self.config.as_dict()),
            },
            "digests": {
                "target_tree": tree_digest(case.target_root),
                "evaluator_private_tree": tree_digest(case.evaluator_private_root),
                "runtime_tree": runtime_source_digest(EXPERIMENT_ROOT),
                "git_commit": _git_commit(REPO_ROOT),
                "git_status": _git_status_digest(REPO_ROOT),
            },
            "live_gate": {
                "status": "open",
                "opened_on": "2026-09-18",
                "satisfied_before_execution": [
                    {
                        "requirement": "pre_call_permit_ledger",
                        "evidence": (
                            "harness/budget.py acquire_call_permit reserves a hard team permit before "
                            "provider dispatch and a retry always consumes a fresh permit; covered by "
                            "harness unit tests and exercised live by the S1 smoke of 2026-09-15"
                        ),
                    },
                    {
                        "requirement": "fail_closed_os_sandbox",
                        "evidence": (
                            "harness/tools/sandbox.py assert_os_sandbox_ready fails closed when bwrap is "
                            "missing (local bwrap 0.6.1); live bwrap self-check and real tool calls passed "
                            "in the S1 smoke of 2026-09-15"
                        ),
                    },
                    {
                        "requirement": "model_visible_transcript_and_reconciliation",
                        "evidence": (
                            "harness/events.py TranscriptLog records model-visible messages and "
                            "reconcile_run runs after every condition; the S1 smoke of 2026-09-15 closed "
                            "the loop with run_validity=valid and reconciliation=valid"
                        ),
                    },
                    {
                        "requirement": "strict_finding_schema_dedup_and_private_verification",
                        "evidence": (
                            "harness/findings.py and repository_v1_findings.py reject duplicate evidence "
                            "refs and anchor reuse; evaluator/repository_v1_score.py records "
                            "evaluator_verification separately from agent verification claims"
                        ),
                    },
                ],
            },
        }


def tree_digest(root: Path) -> str:
    """Hash an input tree by relative path and content, excluding generated cache."""
    if not root.is_dir():
        raise BlockRunnerError(f"tree to digest does not exist: {root.name}")
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def runtime_source_digest(experiment_root: Path) -> str:
    """Digest executable harness sources without allowing old run artifacts to affect it."""
    source_paths = (
        experiment_root / "harness",
        experiment_root / "evaluator",
        experiment_root / "analysis",
        experiment_root / "manifests",
        experiment_root / "run_experiment.py",
        experiment_root / "freeze_block.py",
        experiment_root / "__init__.py",
    )
    digest = hashlib.sha256()
    for source in source_paths:
        if source.is_dir():
            value = tree_digest(source)
        elif source.is_file():
            value = hashlib.sha256(source.read_bytes()).hexdigest()
        else:
            raise BlockRunnerError(f"runtime source is missing: {source.name}")
        digest.update(source.relative_to(experiment_root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(value.encode("ascii"))
    return digest.hexdigest()


def _git_commit(root: Path) -> str | None:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _git_status_digest(root: Path) -> str | None:
    try:
        result = subprocess.run(["git", "status", "--porcelain=v1"], cwd=root, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return _sha256_text(result.stdout) if result.returncode == 0 else None


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_json(value: Any) -> str:
    return _sha256_text(_canonical_json(value))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
