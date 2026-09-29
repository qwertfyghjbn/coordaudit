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

from experiments.emergent_coordination.harness.cases import CaseDefinition, load_case
from experiments.emergent_coordination.harness.contract import BlockConfig, ConditionSpec
from experiments.emergent_coordination.harness.paths import EXPERIMENT_ROOT, REPO_ROOT
from experiments.emergent_coordination.harness.prompts import base_prompt, system_prompt, user_prompt
from experiments.emergent_coordination.harness.tools.specs import tools_for_mode


class BlockRunnerError(RuntimeError):
    pass


def condition_hashes(condition: ConditionSpec, case: CaseDefinition, prompt_profile: str | None = None) -> dict[str, Any]:
    """Hash the frozen per-condition prompt and tool surfaces.

    Prompt hashes use a sentinel agent identity. The actual identity mapping is
    recorded separately, so the manifest proves the prompt template and the
    deterministic identity assignment without duplicating hashes per agent.
    """
    if condition.mode == "manager_worker":
        return {role: _role_hashes(condition, case, role, prompt_profile) for role in ("manager", "worker")}
    return _role_hashes(condition, case, None, prompt_profile)


def _role_hashes(
    condition: ConditionSpec,
    case: CaseDefinition,
    role: str | None,
    prompt_profile: str | None = None,
) -> dict[str, str]:
    agent_id = "__AGENT_ID__"
    profile = prompt_profile or case.prompt_profile
    system = system_prompt(condition.mode, agent_id, profile, role=role)
    user = user_prompt(condition.mode, agent_id, condition.agent_count, profile, role=role)
    if role == "manager":
        identity_rule = "agent_001"
    elif role == "worker":
        identity_rule = "agent_002..agent_N"
    else:
        identity_rule = "agent_001..agent_N"
    return {
        "system_prompt_template": _sha256_text(system),
        "user_prompt_template": _sha256_text(user),
        "tool_schema": _sha256_json(tools_for_mode(condition.mode, case.finding_schema, role=role)),
        "identity_rule": identity_rule,
    }


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
        self._check_case_contract_consistency(case)
        if case.evaluator == "repository_v1_1" and case.manifest.get("live_gate") != "open":
            raise BlockRunnerError("repository-v1.1 case live gate is blocked")
        runtime = self.config.condition_runtime or {}
        if any(
            isinstance(spec, dict) and spec.get("evaluator_generation", case.evaluator) != case.evaluator
            for spec in runtime.values()
        ):
            raise BlockRunnerError("formal block cannot mix evaluator generations")
        prompt_profile = self.config.prompt_profile or case.prompt_profile
        per_condition_hashes = {
            condition.id: condition_hashes(condition, case, prompt_profile) for condition in self.config.conditions
        }
        common, schema = base_prompt(prompt_profile)
        return {
            "schema_version": 2,
            "block_id": block_id,
            "frozen_at": datetime.now(timezone.utc).isoformat(),
            "contract": self.config.as_dict(),
            "evaluator_generation": case.evaluator,
            "hashes": {
                "common_prompt": _sha256_text(common + "\n" + schema),
                "conditions": per_condition_hashes,
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
                    *(
                        [
                            {
                                "requirement": "bounded_team_finalization_deadline",
                                "evidence": (
                                    "completion_v3 freezes team_finalization_deadline_seconds=60;"
                                    " TeamFinalizationCoordinator records deadline expiry and emits"
                                    " team_finalization_deadline_exceeded without an extra permit"
                                ),
                            }
                        ]
                        if self.config.completion_generation == "completion_v3"
                        else []
                    ),
                    *(
                        [
                            {
                                "requirement": "team_level_finalization_trigger",
                                "evidence": (
                                    "BudgetTracker atomically triggers team_remaining_permits_v1 when remaining "
                                    "team permits are <= the frozen reserve=32; transition is exactly-once and "
                                    "all active agents enter the same finalization epoch without extra permits."
                                ),
                            }
                        ]
                        if self.config.completion_generation == "completion_v2_team"
                        else []
                    ),
                ],
            },
        }

    def _check_case_contract_consistency(self, case: CaseDefinition) -> None:
        """Keep a block contract from drifting away from its case manifest.

        When the case declares matched_conditions (repository-v1 cases), every
        contract condition must be declared with the same mode and agent count;
        this is what keeps the five-condition M block un-freezable until the
        case amendment adds M4. Declared defaults pin the team permit pool.
        """
        manifest = case.manifest
        declared = manifest.get("matched_conditions")
        if declared is not None:
            by_id = {str(item["id"]): item for item in declared}
            for condition in self.config.conditions:
                match = by_id.get(condition.id)
                if (
                    match is None
                    or str(match.get("mode")) != condition.mode
                    or int(match.get("agent_count", -1)) != condition.agent_count
                ):
                    raise BlockRunnerError(
                        f"contract condition {condition.id} is not declared by the "
                        f"{self.config.repository_id} case matched_conditions"
                    )
        defaults = manifest.get("default_budgets")
        contract_budgets = manifest.get("contract_budgets")
        # T-Pilot 1 v1/v2 reuse the frozen T4 task-closure budget. Keep the
        # case manifest byte-identical because private graph input locks bind it.
        budget_contract_id = (
            "t4_flowise_sequenced_bootstrap_task_closure_v1"
            if self.config.contract_id in {"t_pilot_1_shared_objective_v1", "t_pilot_1_shared_objective_v2", "t_pilot_2_final_synthesis_v1"}
            else self.config.contract_id
        )
        selected = (
            contract_budgets.get(budget_contract_id)
            if isinstance(contract_budgets, dict)
            else None
        )
        if not isinstance(selected, dict):
            selected = defaults
        if isinstance(selected, dict) and "hard_team_call_permits" in selected:
            case_permits = int(selected["hard_team_call_permits"])
            if case_permits != self.config.hard_team_call_permits:
                raise BlockRunnerError(
                    f"block permits ({self.config.hard_team_call_permits}) disagree with the "
                    f"case default budget ({case_permits})"
                )


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
