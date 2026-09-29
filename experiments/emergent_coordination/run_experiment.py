#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.emergent_coordination.analysis.analyze_run import analyze_run
from experiments.emergent_coordination.harness.budget import TokenUsage
from experiments.emergent_coordination.harness.llm.client import LLMResponse, MockLLMClient, client_from_env
from experiments.emergent_coordination.harness.cases import available_case_ids, load_case
from experiments.emergent_coordination.harness.paths import DEFAULT_RUNS_DIR
from experiments.emergent_coordination.harness.runner import RunConfig, run_experiment


def load_manifest(case_id: str = "repo_pilot_v0") -> dict:
    return load_case(case_id).manifest


def mock_client_for_case(experiment: dict) -> MockLLMClient:
    """Provide a schema-valid no-op response for deterministic CLI smoke runs."""
    if experiment.get("finding_schema") == "repository_v1":
        return MockLLMClient(
            default=[
                LLMResponse(
                    content=json.dumps({"schema_version": "repository-v1", "findings": []}),
                    tool_calls=[],
                    usage=TokenUsage(input_tokens=1, output_tokens=1, model="mock"),
                    raw={"mock": True},
                )
            ]
        )
    return MockLLMClient()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a registered repository coordination experiment.")
    parser.add_argument("--case", default="repo_pilot_v0", choices=available_case_ids())
    parser.add_argument("--mode", required=True, choices=["single", "parallel", "raw_blackboard", "structured_team", "manager_worker"])
    parser.add_argument("--agents", type=int, required=True)
    parser.add_argument("--model", help="Requested provider model; overrides LLM_MODEL for this run.")
    parser.add_argument(
        "--thinking-mode",
        choices=["enabled", "disabled"],
        help="Explicit provider thinking mode; overrides LLM_THINKING_MODE for this run.",
    )
    parser.add_argument("--seed", default="0")
    parser.add_argument("--run-id", help="Stable run directory identifier for a preregistered diagnostic.")
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=1024,
        help="Per-provider-response output ceiling; defaults to the frozen 1024-token contract.",
    )
    parser.add_argument("--mock", action="store_true", help="Use the scripted mock LLM client.")
    parser.add_argument("--live", action="store_true", help="Use LLM credentials from the environment.")
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument(
        "--completion-policy",
        choices=["none", "convergent_v1", "guidance_only", "scheduler_only", "convergent_v2", "scheduler_only_v2"],
        default="none",
        help=(
            "Optional completion-path calibration; formal blocks use none. "
            "Generation-2 policies (convergent_v2/scheduler_only_v2) enforce a hard dispatch gate during finalization."
        ),
    )
    parser.add_argument(
        "--team-completion-policy",
        choices=["none", "all_agents_terminal_v1"],
        default="none",
        help="Runtime team barrier; independent from the agent completion policy.",
    )
    parser.add_argument(
        "--team-finalization-policy",
        choices=["none", "team_remaining_permits_v1"],
        default="none",
        help="Shared-ledger finalization trigger; formal calibration freezes team_remaining_permits_v1.",
    )
    parser.add_argument(
        "--team-finalization-reserve",
        type=int,
        default=0,
        help="Team permit threshold that activates finalization.",
    )
    parser.add_argument(
        "--task-closure-policy",
        choices=["none", "task_closure_gate_v1"],
        default="none",
        help="Optional versioned runtime gate requiring claimed tasks to close before submission.",
    )
    parser.add_argument(
        "--result-sync-policy",
        choices=["none", "result_sync_v1"],
        default="none",
        help="Optional deterministic post-task result visibility barrier.",
    )
    parser.add_argument(
        "--post-sync-window-policy",
        choices=["none", "t4_post_sync_window_v1", "t4_post_sync_window_v2"],
        default="none",
        help="Opt-in neutral POST_SYNC execution window; requires result_sync_v1.",
    )
    parser.add_argument(
        "--post-sync-reservation-per-agent",
        type=int,
        help="Permits statically reserved inside the team cap for each POST_SYNC-eligible agent.",
    )
    parser.add_argument(
        "--task-board-sequencing-policy",
        choices=["none", "initialization_lease_v1", "initialization_lease_v2_optional", "initialization_lease_v3"],
        default="none",
        help="Optional versioned first-board visibility lease.",
    )
    parser.add_argument(
        "--synthesis-phase-policy",
        choices=["none", "team_synthesis_v1"],
        default="none",
        help="T-Pilot 2 post-terminal condition-neutral finalizer over the frozen raw candidate set.",
    )
    parser.add_argument(
        "--completion-generation",
        choices=["none", "completion_v2_team"],
        default="none",
        help="Explicit versioned team-completion generation for a registered pilot.",
    )
    parser.add_argument(
        "--synthesis-reserve-permits",
        type=int,
        help="Permits statically reserved inside the team cap for the synthesis phase.",
    )
    parser.add_argument(
        "--synthesis-window-seconds",
        type=float,
        help="Static wall-clock window reserved for the synthesis phase inside the run wall clock.",
    )
    parser.add_argument(
        "--synthesis-read-file-cap",
        type=int,
        help="Bounded verification read allowance for the finalizer.",
    )
    parser.add_argument(
        "--prompt-profile",
        help="Explicit versioned prompt profile; result_sync_v1 defaults to repository_v1_t4_result_sync_v1.",
    )
    parser.add_argument(
        "--hard-team-call-permits",
        type=int,
        help="Override the manifest team call-permit cap for a non-formal calibration run.",
    )
    parser.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    parser.add_argument("--smoke-budget", action="store_true")
    args = parser.parse_args()
    if args.max_output_tokens <= 0:
        parser.error("--max-output-tokens must be positive")
    if args.hard_team_call_permits is not None and args.hard_team_call_permits <= 0:
        parser.error("--hard-team-call-permits must be positive")
    if args.post_sync_reservation_per_agent is not None and args.post_sync_reservation_per_agent < 0:
        parser.error("--post-sync-reservation-per-agent must be non-negative")
    if args.post_sync_window_policy != "none" and args.result_sync_policy != "result_sync_v1":
        parser.error("--post-sync-window-policy requires --result-sync-policy result_sync_v1")
    if args.synthesis_phase_policy == "none" and (
        args.synthesis_reserve_permits or args.synthesis_window_seconds or args.synthesis_read_file_cap
    ):
        parser.error("synthesis budget flags require --synthesis-phase-policy team_synthesis_v1")

    experiment = load_manifest(args.case)
    budgets = dict(experiment["smoke_budgets"] if args.smoke_budget else experiment["default_budgets"])
    if args.hard_team_call_permits is not None:
        budgets["hard_team_call_permits"] = args.hard_team_call_permits
    if args.post_sync_reservation_per_agent is not None:
        budgets["post_sync_reservation_per_agent"] = args.post_sync_reservation_per_agent
    if args.live and not args.mock:
        llm = client_from_env(
            model=args.model,
            thinking_mode=args.thinking_mode,
            max_tokens=args.max_output_tokens,
        )
        if llm is None:
            print("No LLM credentials found; refusing to start a live run.", file=sys.stderr)
            return 2
        model = llm.model
    else:
        llm = mock_client_for_case(experiment)
        model = "mock"

    summary = run_experiment(
        RunConfig(
            mode=args.mode,
            agent_count=args.agents,
            model=model,
            model_profile=(
                {
                    "requested_model": model,
                    "provider": "openai_compatible",
                    "thinking_mode": llm.thinking_mode,
                    "temperature": llm.temperature,
                    "max_output_tokens": llm.max_tokens,
                }
                if args.live and not args.mock
                else {"requested_model": "mock"}
            ),
            seed=args.seed,
            run_id=args.run_id,
            budgets=budgets,
            max_steps=args.max_steps,
            max_provider_retries=int(budgets.get("max_provider_retries", 0)),
            completion_policy=None if args.completion_policy == "none" else args.completion_policy,
            team_completion_policy=None if args.team_completion_policy == "none" else args.team_completion_policy,
            team_finalization_policy=None if args.team_finalization_policy == "none" else args.team_finalization_policy,
            team_finalization_reserve=args.team_finalization_reserve,
            task_board_sequencing_policy=(
                None if args.task_board_sequencing_policy == "none" else args.task_board_sequencing_policy
            ),
            task_closure_policy=None if args.task_closure_policy == "none" else args.task_closure_policy,
            result_sync_policy=None if args.result_sync_policy == "none" else args.result_sync_policy,
            post_sync_window_policy=(
                None if args.post_sync_window_policy == "none" else args.post_sync_window_policy
            ),
            synthesis_phase_policy=(None if args.synthesis_phase_policy == "none" else args.synthesis_phase_policy),
            completion_generation=(None if args.completion_generation == "none" else args.completion_generation),
            synthesis_reserve_permits=int(args.synthesis_reserve_permits or 0),
            synthesis_window_seconds=(float(args.synthesis_window_seconds) if args.synthesis_window_seconds is not None else None),
            synthesis_read_file_cap=int(args.synthesis_read_file_cap if args.synthesis_read_file_cap is not None else 1),
            prompt_profile=(
                args.prompt_profile
                or (
                    (
                        "repository_v1_t4_post_sync_window_v2"
                        if args.post_sync_window_policy == "t4_post_sync_window_v2"
                        else "repository_v1_t4_post_sync_window_v1"
                    )
                    if args.post_sync_window_policy in {"t4_post_sync_window_v1", "t4_post_sync_window_v2"}
                    else "repository_v1_t4_result_sync_v1"
                    if args.result_sync_policy == "result_sync_v1"
                    else None
                )
            ),
            require_os_sandbox=bool(args.live and not args.mock),
            runs_dir=Path(args.runs_dir),
            case_id=args.case,
        ),
        llm,
    )
    analysis = analyze_run(Path(summary["run_dir"]))
    print(json.dumps({"summary": summary, "analysis": analysis}, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
