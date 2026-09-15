from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


SHARED_EVENTS = {"shared_list", "shared_read", "shared_create", "shared_mkdir"}


def load_events(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "logs" / "events.jsonl"
    events = []
    if not path.exists():
        return events
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def analyze_run(run_dir: Path) -> dict[str, Any]:
    events = load_events(run_dir)
    counts = Counter(event["event_type"] for event in events)
    agents_started = sorted({event["agent_id"] for event in events if event["event_type"] == "agent_started" and event.get("agent_id")})
    agents_finished = sorted({event["agent_id"] for event in events if event["event_type"] == "agent_finished" and event.get("agent_id")})

    input_tokens = 0
    output_tokens = 0
    for event in events:
        usage = event.get("token_usage") or {}
        input_tokens += int(usage.get("input_tokens") or 0)
        output_tokens += int(usage.get("output_tokens") or 0)

    evaluation = {}
    evaluation_path = run_dir / "evaluation.json"
    if evaluation_path.exists():
        evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))

    shared_paths = []
    cross_agent_reads = 0
    created_by: dict[str, str] = {}
    filename_prefixes: Counter[str] = Counter()
    for event in events:
        if event["event_type"] == "shared_create":
            path = (event.get("payload") or {}).get("path")
            if path:
                created_by[path] = event.get("agent_id")
                shared_paths.append(path)
                filename_prefixes[Path(path).name.split("_")[0]] += 1
        if event["event_type"] == "shared_read":
            path = (event.get("payload") or {}).get("path")
            owner = created_by.get(path)
            if owner and owner != event.get("agent_id"):
                cross_agent_reads += 1

    result = {
        "run_dir": str(run_dir),
        "agents_started": len(agents_started),
        "agents_finished": len(agents_finished),
        "total_input_tokens": input_tokens,
        "total_output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "findings_submitted": counts.get("finding_submitted", 0),
        "TP": evaluation.get("TP"),
        "FP": evaluation.get("FP"),
        "FN": evaluation.get("FN"),
        "precision": evaluation.get("precision"),
        "recall": evaluation.get("recall"),
        "shared_reads": counts.get("shared_read", 0),
        "shared_writes": counts.get("shared_create", 0),
        "tasks_created": counts.get("task_created", 0),
        "tasks_claimed": counts.get("task_claimed", 0),
        "messages_sent": counts.get("message_sent", 0),
        "errors": counts.get("error", 0),
        "timeouts": counts.get("timeout", 0),
        "budget_exhausted": counts.get("budget_exhausted", 0),
        "shared_path_activity": shared_paths,
        "cross_agent_reads": cross_agent_reads,
        "common_filename_prefixes": dict(filename_prefixes),
        "event_counts": dict(counts),
        "notes": [
            "This analyzer reports evidence only.",
            "It does not claim that a leader, mailbox, or other primitive emerged.",
        ],
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize a repository-pilot-v0 run directory.")
    parser.add_argument("run_dir")
    parser.add_argument("--output", help="Optional JSON output path")
    args = parser.parse_args()
    result = analyze_run(Path(args.run_dir))
    text = json.dumps(result, indent=2, ensure_ascii=False)
    print(text)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
