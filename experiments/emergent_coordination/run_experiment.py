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
from experiments.emergent_coordination.harness.llm.client import MockLLMClient, client_from_env
from experiments.emergent_coordination.harness.paths import DEFAULT_RUNS_DIR, MANIFEST_PATH
from experiments.emergent_coordination.harness.runner import RunConfig, run_experiment


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run repository-pilot-v0 coordination experiment.")
    parser.add_argument("--mode", required=True, choices=["single", "parallel", "raw_blackboard", "structured_team"])
    parser.add_argument("--agents", type=int, required=True)
    parser.add_argument("--model", default="mock")
    parser.add_argument("--seed", default="0")
    parser.add_argument("--mock", action="store_true", help="Use the scripted mock LLM client.")
    parser.add_argument("--live", action="store_true", help="Use LLM credentials from the environment.")
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    parser.add_argument("--smoke-budget", action="store_true")
    args = parser.parse_args()

    experiment = load_manifest()
    budgets = experiment["smoke_budgets"] if args.smoke_budget else experiment["default_budgets"]
    if args.live and not args.mock:
        llm = client_from_env()
        if llm is None:
            print("No LLM credentials found; refusing to start a live run.", file=sys.stderr)
            return 2
        model = llm.model
    else:
        llm = MockLLMClient()
        model = "mock"

    summary = run_experiment(
        RunConfig(
            mode=args.mode,
            agent_count=args.agents,
            model=model,
            seed=args.seed,
            budgets=budgets,
            max_steps=args.max_steps,
            runs_dir=Path(args.runs_dir),
        ),
        llm,
    )
    analysis = analyze_run(Path(summary["run_dir"]))
    print(json.dumps({"summary": summary, "analysis": analysis}, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
