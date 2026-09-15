from __future__ import annotations

import json
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from experiments.emergent_coordination.evaluator.score import evaluate_findings, load_ground_truth
from experiments.emergent_coordination.harness.agent_loop import AgentRunner
from experiments.emergent_coordination.harness.budget import BudgetTracker
from experiments.emergent_coordination.harness.events import EventLog, utc_now
from experiments.emergent_coordination.harness.llm.client import LLMClient
from experiments.emergent_coordination.harness.paths import (
    DEFAULT_RUNS_DIR,
    GROUND_TRUTH_PATH,
    MANIFEST_PATH,
    PROVENANCE_PATH,
    REPO_ROOT,
    TARGET_ROOT,
    agent_id_for,
)
from experiments.emergent_coordination.harness.policies.base import CoordinationPolicy, get_policy
from experiments.emergent_coordination.harness.shared_fs import SharedFilesystem
from experiments.emergent_coordination.harness.task_board import TaskBoard
from experiments.emergent_coordination.harness.tools.sandbox import AgentSandbox
from experiments.emergent_coordination.harness.workspace import WorkspaceLayout, prepare_run_workspace


@dataclass
class RunConfig:
    mode: str
    agent_count: int
    model: str = "mock"
    seed: str = "0"
    budgets: dict[str, Any] | None = None
    max_steps: int = 12
    run_id: str | None = None
    runs_dir: Path = DEFAULT_RUNS_DIR
    evaluate: bool = True


class RunContext:
    def __init__(
        self,
        *,
        config: RunConfig,
        layout: WorkspaceLayout,
        event_log: EventLog,
        budget: BudgetTracker,
        llm: LLMClient,
        policy: CoordinationPolicy,
        shared: SharedFilesystem | None,
        board: TaskBoard | None,
    ):
        self.config = config
        self.layout = layout
        self.event_log = event_log
        self.budget = budget
        self.llm = llm
        self.policy = policy
        self.shared = shared
        self.board = board
        self.agent_ids = [agent_id_for(index) for index in range(1, config.agent_count + 1)]
        self.submissions: dict[str, dict[str, Any]] = {}
        self.started_at = time.monotonic()

    def run_one(self, agent_id: str) -> dict[str, Any]:
        elapsed = time.monotonic() - self.started_at
        self.budget.check_wall_clock(elapsed)
        sandbox = AgentSandbox(
            agent_id,
            self.layout,
            self.event_log,
            shared=self.shared if self.policy.enable_shared else None,
            board=self.board if self.policy.enable_board else None,
            internet=False,
            submit_callback=self._on_submit,
        )
        runner = AgentRunner(
            agent_id=agent_id,
            mode=self.config.mode,
            agent_count=self.config.agent_count,
            sandbox=sandbox,
            llm=self.llm,
            event_log=self.event_log,
            budget=self.budget,
            max_steps=self.config.max_steps,
        )
        return runner.run()

    def _on_submit(self, agent_id: str, payload: dict[str, Any]) -> None:
        self.submissions[agent_id] = payload
        dest = self.layout.artifacts / f"{agent_id}_findings.json"
        dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _archive_evaluator_private(layout: WorkspaceLayout) -> None:
    layout.evaluator_private.mkdir(parents=True, exist_ok=True)
    if GROUND_TRUTH_PATH.exists():
        shutil.copy2(GROUND_TRUTH_PATH, layout.evaluator_private / "ground_truth.json")
    if PROVENANCE_PATH.exists():
        shutil.copy2(PROVENANCE_PATH, layout.evaluator_private / "provenance.json")


def git_commit(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return None


def merge_findings(agent_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = []
    for result in agent_results:
        payload = result.get("findings") or {}
        for finding in payload.get("findings", []):
            item = dict(finding)
            item.setdefault("submitted_by", result.get("agent_id"))
            merged.append(item)
    return merged


def run_experiment(config: RunConfig, llm: LLMClient) -> dict[str, Any]:
    policy = get_policy(config.mode)
    if config.mode == "single" and config.agent_count != 1:
        raise ValueError("single mode requires agent_count=1")
    if config.agent_count < 1:
        raise ValueError("agent_count must be >= 1")

    run_id = config.run_id or f"{config.mode}_n{config.agent_count}_{utc_now().replace(':', '').replace('-', '')}_{uuid.uuid4().hex[:8]}"
    run_dir = Path(config.runs_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    layout = prepare_run_workspace(
        run_dir,
        TARGET_ROOT,
        config.agent_count,
        ground_truth=None,
        provenance=None,
    )
    event_log = EventLog(layout.logs / "events.jsonl", run_id=run_id)
    budgets = config.budgets or {}
    budget = BudgetTracker(
        global_input_token_cap=budgets.get("global_input_token_cap"),
        global_output_token_cap=budgets.get("global_output_token_cap"),
        per_agent_token_cap=budgets.get("per_agent_token_cap"),
        max_llm_calls=budgets.get("max_llm_calls"),
        wall_clock_timeout=budgets.get("wall_clock_timeout"),
    )
    shared = SharedFilesystem(layout.shared, event_log, layout.artifacts / "shared_snapshots") if policy.enable_shared else None
    board = TaskBoard(layout.runtime / "coordination", event_log) if policy.enable_board else None

    manifest = {
        "run_id": run_id,
        "repository": "repo_pilot_v0",
        "mode": config.mode,
        "agent_count": config.agent_count,
        "model": config.model,
        "seed": config.seed,
        "budgets": budgets,
        "start_time": utc_now(),
        "git_commit": git_commit(REPO_ROOT),
        "experiment_manifest": str(MANIFEST_PATH),
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    event_log.emit("run_started", payload={"mode": config.mode, "agent_count": config.agent_count})

    context = RunContext(
        config=config,
        layout=layout,
        event_log=event_log,
        budget=budget,
        llm=llm,
        policy=policy,
        shared=shared,
        board=board,
    )
    agent_results = policy.run_agents(context)
    _archive_evaluator_private(layout)
    merged = merge_findings(agent_results)
    (run_dir / "merged_findings.json").write_text(
        json.dumps({"findings": merged}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    evaluation = None
    if config.evaluate:
        gt_path = layout.evaluator_private / "ground_truth.json"
        if not gt_path.exists():
            gt_path = GROUND_TRUTH_PATH
        ground_truth = load_ground_truth(gt_path)
        evaluation = evaluate_findings(merged, ground_truth)
        (run_dir / "evaluation.json").write_text(
            json.dumps(evaluation, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    summary = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "mode": config.mode,
        "agent_count": config.agent_count,
        "agent_results": [
            {
                "agent_id": item["agent_id"],
                "stop_reason": item["stop_reason"],
                "finding_count": len((item.get("findings") or {}).get("findings") or []),
            }
            for item in agent_results
        ],
        "merged_finding_count": len(merged),
        "budget": budget.snapshot(),
        "evaluation": evaluation,
        "end_time": utc_now(),
    }
    event_log.emit("run_finished", payload={"merged_finding_count": len(merged)})
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return summary
