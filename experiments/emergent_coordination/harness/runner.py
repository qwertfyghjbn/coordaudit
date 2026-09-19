from __future__ import annotations

import json
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from experiments.emergent_coordination.harness.agent_loop import AgentRunner
from experiments.emergent_coordination.harness.budget import (
    BudgetTracker,
    describe_budget_semantics,
    validate_budget_config,
)
from experiments.emergent_coordination.harness.events import EventLog, TranscriptLog, reconcile_run, utc_now
from experiments.emergent_coordination.harness.llm.client import LLMClient
from experiments.emergent_coordination.harness.cases import CaseDefinition, load_case
from experiments.emergent_coordination.harness.paths import DEFAULT_RUNS_DIR, REPO_ROOT, agent_id_for
from experiments.emergent_coordination.harness.policies.base import CoordinationPolicy, get_policy
from experiments.emergent_coordination.harness.shared_fs import SharedFilesystem
from experiments.emergent_coordination.harness.task_board import TaskBoard
from experiments.emergent_coordination.harness.manager_board import ManagerBoard
from experiments.emergent_coordination.harness.tools.sandbox import AgentSandbox, assert_os_sandbox_ready
from experiments.emergent_coordination.harness.workspace import WorkspaceLayout, prepare_run_workspace


@dataclass
class RunConfig:
    mode: str
    agent_count: int
    model: str = "mock"
    model_profile: dict[str, Any] | None = None
    seed: str = "0"
    budgets: dict[str, Any] | None = None
    max_steps: int = 12
    max_provider_retries: int = 0
    completion_policy: str | None = None
    require_os_sandbox: bool = False
    run_id: str | None = None
    runs_dir: Path = DEFAULT_RUNS_DIR
    evaluate: bool = True
    case_id: str = "repo_pilot_v0"


class RunContext:
    def __init__(
        self,
        *,
        config: RunConfig,
        layout: WorkspaceLayout,
        event_log: EventLog,
        transcript_log: TranscriptLog,
        budget: BudgetTracker,
        llm: LLMClient,
        policy: CoordinationPolicy,
        shared: SharedFilesystem | None,
        board: TaskBoard | None,
        manager_board: ManagerBoard | None,
        case: CaseDefinition,
    ):
        self.config = config
        self.layout = layout
        self.event_log = event_log
        self.transcript_log = transcript_log
        self.budget = budget
        self.llm = llm
        self.policy = policy
        self.shared = shared
        self.board = board
        self.manager_board = manager_board
        self.case = case
        self.agent_ids = [agent_id_for(index) for index in range(1, config.agent_count + 1)]
        self.submissions: dict[str, dict[str, Any]] = {}
        self.started_at = time.monotonic()

    def make_session(self, agent_id: str, *, role: str | None = None) -> AgentRunner:
        elapsed = time.monotonic() - self.started_at
        self.budget.check_wall_clock(elapsed)
        sandbox = AgentSandbox(
            agent_id,
            self.layout,
            self.event_log,
            shared=self.shared if self.policy.enable_shared else None,
            board=self.board if self.policy.enable_board else None,
            manager_board=self.manager_board if self.policy.enable_manager_board else None,
            internet=False,
            require_os_sandbox=self.config.require_os_sandbox,
            finding_schema=self.case.finding_schema,
            submit_callback=self._on_submit,
        )
        runner = AgentRunner(
            agent_id=agent_id,
            mode=self.config.mode,
            agent_count=self.config.agent_count,
            role=role,
            sandbox=sandbox,
            llm=self.llm,
            event_log=self.event_log,
            transcript_log=self.transcript_log,
            budget=self.budget,
            prompt_profile=self.case.prompt_profile,
            finding_schema=self.case.finding_schema,
            completion_policy=self.config.completion_policy,
            max_steps=self.config.max_steps,
            max_provider_retries=self.config.max_provider_retries,
        )
        return runner

    def run_one(self, agent_id: str) -> dict[str, Any]:
        return self.make_session(agent_id).run()

    def _on_submit(self, agent_id: str, payload: dict[str, Any]) -> None:
        self.submissions[agent_id] = payload
        dest = self.layout.artifacts / f"{agent_id}_findings.json"
        dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _archive_evaluator_private(layout: WorkspaceLayout, case: CaseDefinition) -> None:
    layout.evaluator_private.mkdir(parents=True, exist_ok=True)
    shutil.copy2(case.ground_truth_path, layout.evaluator_private / "ground_truth.json")
    if case.provenance_path is not None:
        shutil.copy2(case.provenance_path, layout.evaluator_private / "provenance.json")


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
    budgets = dict(config.budgets or {})
    validate_budget_config(budgets)
    policy = get_policy(config.mode)
    if config.mode == "single" and config.agent_count != 1:
        raise ValueError("single mode requires agent_count=1")
    if config.mode == "manager_worker" and config.agent_count < 2:
        raise ValueError("manager_worker mode requires one manager and at least one worker")
    if config.agent_count < 1:
        raise ValueError("agent_count must be >= 1")
    if config.model != "mock" and not config.require_os_sandbox:
        raise ValueError("live runs require fail-closed OS sandbox verification")
    if config.require_os_sandbox:
        assert_os_sandbox_ready()
    case = load_case(config.case_id)

    run_id = config.run_id or f"{config.mode}_n{config.agent_count}_{utc_now().replace(':', '').replace('-', '')}_{uuid.uuid4().hex[:8]}"
    run_dir = Path(config.runs_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    layout = prepare_run_workspace(
        run_dir,
        case.target_root,
        config.agent_count,
        ground_truth=None,
        provenance=None,
    )
    event_log = EventLog(layout.logs / "events.jsonl", run_id=run_id, target=case.case_id)
    transcript_log = TranscriptLog(layout.logs / "transcripts", run_id=run_id, event_log=event_log)
    budget = BudgetTracker(
        hard_team_call_permits=budgets.get("hard_team_call_permits"),
        token_stop_threshold=budgets.get("token_stop_threshold"),
        wall_clock_timeout=budgets.get("wall_clock_timeout"),
    )
    shared = SharedFilesystem(layout.shared, event_log, layout.artifacts / "shared_snapshots") if policy.enable_shared else None
    board = TaskBoard(layout.runtime / "coordination", event_log) if policy.enable_board else None
    manager_board = (
        ManagerBoard(event_log, "agent_001", [agent_id_for(index) for index in range(2, config.agent_count + 1)])
        if policy.enable_manager_board
        else None
    )

    manifest = {
        "run_id": run_id,
        "repository": case.case_id,
        "mode": config.mode,
        "agent_count": config.agent_count,
        "model": config.model,
        "model_profile": config.model_profile or {"requested_model": config.model},
        "seed": config.seed,
        "budgets": budgets,
        "budget_semantics": describe_budget_semantics(budgets),
        "max_steps": config.max_steps,
        "max_provider_retries": config.max_provider_retries,
        "completion_policy": config.completion_policy,
        "require_os_sandbox": config.require_os_sandbox,
        "start_time": utc_now(),
        "git_commit": git_commit(REPO_ROOT),
        "experiment_manifest": str(case.manifest_path.relative_to(REPO_ROOT)),
        "prompt_profile": case.prompt_profile,
        "finding_schema": case.finding_schema,
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    event_log.emit("run_started", payload={"mode": config.mode, "agent_count": config.agent_count})

    context = RunContext(
        config=config,
        layout=layout,
        event_log=event_log,
        transcript_log=transcript_log,
        budget=budget,
        llm=llm,
        policy=policy,
        shared=shared,
        board=board,
        manager_board=manager_board,
        case=case,
    )
    agent_results = policy.run_agents(context)
    _archive_evaluator_private(layout, case)
    merged = merge_findings(agent_results)
    (run_dir / "merged_findings.json").write_text(
        json.dumps({"findings": merged}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    invalid_submissions = sum(int(item.get("invalid_submission_attempts", 0)) for item in agent_results)
    evaluation = None
    if config.evaluate:
        ground_truth = _load_ground_truth_for_case(case, layout.evaluator_private / "ground_truth.json")
        evaluation_bundle = _evaluate_for_case(case, merged, ground_truth, invalid_submissions)
        evaluation = evaluation_bundle["public"]
        (run_dir / "evaluation.json").write_text(
            json.dumps(evaluation, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (layout.evaluator_private / "verification.json").write_text(
            json.dumps(evaluation_bundle["private"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    budget_snapshot = budget.snapshot()
    validity = classify_infrastructure_validity(budget_snapshot, agent_results)
    preliminary_reconciliation = reconcile_run(event_log, transcript_log, budget_snapshot)
    validity = _combine_validity(validity, preliminary_reconciliation)
    event_log.emit(
        "run_finished",
        payload={"merged_finding_count": len(merged), "run_validity": validity["status"]},
        outcome=validity["status"],
        budget_progress=budget_snapshot,
    )
    reconciliation = reconcile_run(event_log, transcript_log, budget_snapshot)
    validity = _combine_validity(classify_infrastructure_validity(budget_snapshot, agent_results), reconciliation)
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
                "submission_attempts": item.get("submission_attempts", 0),
                "invalid_submission_attempts": item.get("invalid_submission_attempts", 0),
                "invalid_submission_arguments": item.get("invalid_submission_arguments", 0),
            }
            for item in agent_results
        ],
        "merged_finding_count": len(merged),
        "invalid_submissions": invalid_submissions,
        "budget": budget_snapshot,
        "run_validity": validity,
        "reconciliation": reconciliation,
        "evaluation": evaluation,
        "end_time": utc_now(),
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    # Every completed run carries a machine-readable observational metric file.
    # Imported lazily to keep the runtime/analysis dependency one-way.
    from experiments.emergent_coordination.analysis.analyze_run import analyze_run

    analyze_run(run_dir, write=True)
    return summary


def _load_ground_truth_for_case(case: CaseDefinition, archived_path: Path) -> dict[str, Any]:
    path = archived_path if archived_path.exists() else case.ground_truth_path
    if case.evaluator == "repository_pilot_v0":
        from experiments.emergent_coordination.evaluator.score import load_ground_truth

        return load_ground_truth(path)
    if case.evaluator == "repository_v1":
        from experiments.emergent_coordination.evaluator.repository_v1_score import load_ground_truth

        return load_ground_truth(path)
    raise ValueError("unsupported case evaluator")


def _evaluate_for_case(
    case: CaseDefinition, findings: list[dict[str, Any]], ground_truth: dict[str, Any], invalid_submissions: int
) -> dict[str, Any]:
    if case.evaluator == "repository_pilot_v0":
        from experiments.emergent_coordination.evaluator.score import evaluate_findings

        return evaluate_findings(findings, ground_truth, invalid_submissions=invalid_submissions)
    if case.evaluator == "repository_v1":
        from experiments.emergent_coordination.evaluator.repository_v1_score import evaluate_findings

        return evaluate_findings(findings, ground_truth, invalid_submissions=invalid_submissions)
    raise ValueError("unsupported case evaluator")


def classify_infrastructure_validity(
    budget_snapshot: dict[str, Any], agent_results: list[dict[str, Any]]
) -> dict[str, Any]:
    """Apply ADR-0002's provider-failure validity rule to a completed run."""
    ledger = budget_snapshot.get("permit_ledger") or []
    failures = [entry for entry in ledger if entry.get("outcome") in {"timeout", "provider_error"}]
    if not failures:
        return {"status": "valid", "provider_failure_attempts": 0, "reasons": []}
    if len(failures) >= 2:
        return {
            "status": "infrastructure_invalid",
            "provider_failure_attempts": len(failures),
            "reasons": ["two_or_more_provider_failure_attempts"],
        }
    failed = failures[0]
    recovered = any(
        entry.get("agent_id") == failed.get("agent_id")
        and entry.get("outcome") == "succeeded"
        and int(entry.get("attempt_number", 0)) > int(failed.get("attempt_number", 0))
        for entry in ledger
    )
    agent_terminated = any(
        result.get("agent_id") == failed.get("agent_id") and result.get("stop_reason") == "error" for result in agent_results
    )
    if not recovered or agent_terminated:
        return {
            "status": "infrastructure_invalid",
            "provider_failure_attempts": 1,
            "reasons": ["unrecovered_provider_failure_terminated_agent"],
        }
    return {
        "status": "valid_with_infrastructure_warning",
        "provider_failure_attempts": 1,
        "reasons": ["single_recovered_provider_failure"],
    }


def _combine_validity(provider_validity: dict[str, Any], reconciliation: dict[str, Any]) -> dict[str, Any]:
    """Transcript/index failures override otherwise valid provider accounting."""
    if reconciliation.get("status") == "valid":
        return provider_validity
    reasons = list(provider_validity.get("reasons") or []) + [
        f"transcript_reconciliation:{reason}" for reason in reconciliation.get("reasons") or []
    ]
    return {
        "status": "infrastructure_invalid",
        "provider_failure_attempts": provider_validity.get("provider_failure_attempts", 0),
        "reasons": sorted(set(reasons)),
    }
