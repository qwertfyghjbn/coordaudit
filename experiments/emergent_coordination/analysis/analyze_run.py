"""Evidence-only run metrics and matched-block comparison artifacts."""

from __future__ import annotations

import argparse
import json
import re
import shlex
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping


METRICS_SCHEMA_VERSION = 1
BLOCK_COMPARISON_SCHEMA_VERSION = 1
_SEARCH_COMMANDS = frozenset({"rg", "grep", "git-grep", "ag", "ack"})
_TEST_COMMANDS = frozenset({"pytest", "unittest", "tox", "nox"})


def load_events(run_dir: Path) -> list[dict[str, Any]]:
    return _read_jsonl(Path(run_dir) / "logs" / "events.jsonl")


def analyze_run(run_dir: Path, *, write: bool = True) -> dict[str, Any]:
    """Build machine-readable, observational metrics for one completed run."""
    run_dir = Path(run_dir)
    events = load_events(run_dir)
    artifacts = _artifact_index(run_dir)
    summary = _read_json(run_dir / "summary.json", {})
    evaluation = _read_json(run_dir / "evaluation.json", {})
    findings = (_read_json(run_dir / "merged_findings.json", {}).get("findings") or [])
    counts = Counter(event.get("event_type") for event in events)
    agent_ids = _agent_ids(events, summary)

    duplicate_work = _duplicate_work(events, artifacts, findings)
    allocation = _resource_allocation(events, summary, agent_ids)
    blackboard = _blackboard_metrics(events)
    structured_team = _structured_team_metrics(events, artifacts, findings)
    result = {
        "schema_version": METRICS_SCHEMA_VERSION,
        "run_id": summary.get("run_id"),
        "run_dir": str(run_dir),
        "mode": summary.get("mode"),
        "agent_count": summary.get("agent_count"),
        "run_validity": summary.get("run_validity"),
        "reconciliation": summary.get("reconciliation"),
        "evaluation": evaluation,
        "duplicate_work": duplicate_work,
        "resource_allocation": allocation,
        "blackboard": blackboard,
        "structured_team": structured_team,
        "event_counts": dict(sorted(counts.items())),
        # Compatibility fields retained for the small existing analyzer API.
        "agents_started": len(_events_of(events, "agent_started")),
        "agents_finished": len(_events_of(events, "agent_finished")),
        "total_input_tokens": allocation["team"]["actual_input_tokens"],
        "total_output_tokens": allocation["team"]["actual_output_tokens"],
        "total_tokens": allocation["team"]["actual_tokens"],
        "findings_submitted": counts.get("finding_submitted", 0),
        "positive_recall": evaluation.get("positive_recall"),
        "known_near_miss_false_positives": evaluation.get("known_near_miss_false_positives"),
        "unmatched_review": evaluation.get("unmatched_review"),
        "precision_bounds": evaluation.get("precision_bounds"),
        "shared_reads": counts.get("shared_read", 0),
        "shared_writes": counts.get("shared_create", 0),
        "tasks_created": counts.get("task_created", 0),
        "tasks_claimed": counts.get("task_claimed", 0),
        "messages_sent": counts.get("message_sent", 0),
        "errors": counts.get("error", 0),
        "timeouts": counts.get("timeout", 0),
        "budget_exhausted": counts.get("budget_exhausted", 0),
        "shared_path_activity": sorted(blackboard["path_lineage"]),
        "cross_agent_reads": blackboard["cross_agent_read_count"],
        "notes": [
            "所有指标均是事件、转录或冻结输出可证明的观察事实。",
            "This analyzer reports evidence only.",
            "路径相邻、一次 shared read、任务状态或时间相邻均不自动证明协作、采纳、领导或意图。",
            "evidence_adoption 仅表示后续 finding 显式引用了已观察任务结果中的同一 evidence_ref。",
        ],
    }
    if write:
        _write_json(run_dir / "metrics.json", result)
    return result


def analyze_matched_block(
    block_dir: Path,
    condition_runs: Mapping[str, Path] | None = None,
    *,
    write: bool = True,
) -> dict[str, Any]:
    """Compare one run per frozen condition without making causal claims.

    A frozen block records the intended contract but historically did not own
    execution.  Callers therefore may supply explicit ``condition=run_dir``
    mappings.  Without them, completed runs are discovered beneath block_dir.
    Missing, duplicate, or infrastructure-invalid conditions are reported as
    incompleteness rather than silently compared.
    """
    block_dir = Path(block_dir)
    manifest = _read_json(block_dir / "block_manifest.json", None)
    if not manifest:
        raise ValueError("block_manifest.json is required for matched-block analysis")
    expected = manifest.get("contract", {}).get("conditions") or []
    expected_by_id = {str(item["id"]): item for item in expected}
    resolved = _resolve_condition_runs(block_dir, expected_by_id, condition_runs)
    condition_rows: dict[str, Any] = {}
    missing: list[str] = []
    invalid: list[str] = []
    mismatched: list[str] = []

    for condition_id, spec in expected_by_id.items():
        candidates = resolved.get(condition_id, [])
        if len(candidates) != 1:
            missing.append(condition_id)
            condition_rows[condition_id] = {"status": "missing_or_ambiguous", "run_dirs": [str(path) for path in candidates]}
            continue
        run_dir = candidates[0]
        metrics = analyze_run(run_dir, write=True)
        summary = _read_json(run_dir / "summary.json", {})
        actual = {"mode": summary.get("mode"), "agent_count": summary.get("agent_count")}
        condition_match = actual == {"mode": spec.get("mode"), "agent_count": spec.get("agent_count")}
        validity = (summary.get("run_validity") or {}).get("status")
        status = "included"
        if not condition_match:
            status = "condition_mismatch"
            mismatched.append(condition_id)
        elif validity == "infrastructure_invalid":
            status = "infrastructure_invalid"
            invalid.append(condition_id)
        condition_rows[condition_id] = {
            "status": status,
            "run_dir": str(run_dir),
            "actual_condition": actual,
            "run_validity": summary.get("run_validity"),
            "metrics": _comparison_projection(metrics),
        }

    included = {key: row for key, row in condition_rows.items() if row.get("status") == "included"}
    status = "complete" if len(included) == len(expected_by_id) else "incomplete_or_invalid"
    comparison = {
        "schema_version": BLOCK_COMPARISON_SCHEMA_VERSION,
        "block_id": manifest.get("block_id"),
        "block_manifest_hash": manifest.get("manifest_hash"),
        "status": status,
        "conditions": condition_rows,
        "completeness": {
            "expected_conditions": list(expected_by_id),
            "included_conditions": sorted(included),
            "missing_or_ambiguous_conditions": sorted(missing),
            "condition_mismatches": sorted(mismatched),
            "infrastructure_invalid_conditions": sorted(invalid),
        },
        "comparisons_to_S1": _comparisons_to_s1(included),
        "contract_verification_limits": [
            "此汇总校验 mode、agent_count 与 run validity；旧单 run manifest 未保存 block_id/prompt/tool hash 回指，不能单凭此文件证明完整合同匹配。",
            "比较仅并列观察指标，不宣称 coordination adapter 导致了任一差异。",
        ],
        "notes": [
            "未完成或 infrastructure-invalid 的条件保留在输出中，不会静默纳入 matched comparison。",
            "shared/task 行为需要显式 lineage 或 evidence_ref 才报告为 exposure/adoption；不从时间相邻推断协作。",
        ],
    }
    if write:
        _write_json(block_dir / "block_comparison.json", comparison)
    return comparison


def _duplicate_work(events: list[dict[str, Any]], artifacts: dict[tuple[str, str], Any], findings: list[dict[str, Any]]) -> dict[str, Any]:
    file_observations = [
        _observation(event, _normalize_path((event.get("payload") or {}).get("path")))
        for event in _events_of(events, "file_read")
        if _normalize_path((event.get("payload") or {}).get("path"))
    ]
    search_observations: list[dict[str, Any]] = []
    test_observations: list[dict[str, Any]] = []
    for event in _events_of(events, "tool_call"):
        command = _shell_command(event, artifacts)
        if command is None:
            continue
        kind, fingerprint = _shell_fingerprint(command)
        if kind == "search":
            search_observations.append(_observation(event, fingerprint))
        elif kind == "test":
            test_observations.append(_observation(event, fingerprint))
    hypothesis_observations = []
    for index, finding in enumerate(findings):
        source = finding.get("source") or {}
        sink = finding.get("sink") or {}
        fingerprint = "|".join(
            [
                _normalize_text(finding.get("category")),
                _normalize_path(source.get("file")),
                _normalize_text(source.get("function")),
                _normalize_text(source.get("anchor")),
                _normalize_path(sink.get("file")),
                _normalize_text(sink.get("function")),
                _normalize_text(sink.get("anchor")),
            ]
        )
        hypothesis_observations.append(
            {"event_id": f"finding_{index:04d}", "agent_id": finding.get("submitted_by"), "fingerprint": fingerprint}
        )
    categories = {
        "files": _group_work(file_observations),
        "searches": _group_work(search_observations),
        "source_sink_hypotheses": _group_work(hypothesis_observations),
        "tests": _group_work(test_observations),
    }
    total = sum(item["total_observations"] for item in categories.values())
    repeated = sum(item["cross_agent_repeated_observations"] for item in categories.values())
    return {
        "categories": categories,
        "aggregate": {
            "total_observations": total,
            "cross_agent_repeated_observations": repeated,
            "cross_agent_duplicate_ratio": repeated / total if total else 0.0,
        },
    }


def _group_work(observations: Iterable[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for observation in observations:
        fingerprint = observation.get("fingerprint")
        if fingerprint:
            groups[str(fingerprint)].append(observation)
    repeated = 0
    duplicate_groups = []
    for fingerprint, items in sorted(groups.items()):
        agents = sorted({str(item.get("agent_id")) for item in items if item.get("agent_id")})
        if len(agents) > 1:
            repeated += len(agents) - 1
            duplicate_groups.append(
                {"fingerprint": fingerprint, "agents": agents, "event_ids": [item["event_id"] for item in items], "observation_count": len(items)}
            )
    total = sum(len(items) for items in groups.values())
    return {
        "total_observations": total,
        "unique_fingerprints": len(groups),
        "cross_agent_repeated_observations": repeated,
        "cross_agent_duplicate_ratio": repeated / total if total else 0.0,
        "duplicate_groups": duplicate_groups,
    }


def _resource_allocation(events: list[dict[str, Any]], summary: dict[str, Any], agent_ids: list[str]) -> dict[str, Any]:
    budget = summary.get("budget") or {}
    ledger = budget.get("permit_ledger") or []
    per_agent = budget.get("per_agent") or {}
    starts = {event.get("agent_id"): _timestamp(event) for event in _events_of(events, "agent_started")}
    ends = {event.get("agent_id"): _timestamp(event) for event in _events_of(events, "agent_finished")}
    agents: dict[str, Any] = {}
    for agent_id in agent_ids:
        attempts = [entry for entry in ledger if entry.get("agent_id") == agent_id]
        usage = per_agent.get(agent_id) or {}
        active_seconds = _duration_seconds(starts.get(agent_id), ends.get(agent_id))
        agents[agent_id] = {
            "permits_acquired": len(attempts),
            "permits_succeeded": sum(entry.get("outcome") == "succeeded" for entry in attempts),
            "permits_failed": sum(entry.get("outcome") in {"timeout", "provider_error"} for entry in attempts),
            "actual_input_tokens": _int(usage.get("input_tokens")),
            "actual_output_tokens": _int(usage.get("output_tokens")),
            "actual_tokens": _int(usage.get("input_tokens")) + _int(usage.get("output_tokens")),
            "active_wall_seconds": active_seconds,
        }
    caps = budget.get("caps") or {}
    permit_cap = caps.get("hard_team_call_permits")
    permit_values = [item["permits_acquired"] for item in agents.values()]
    token_values = [item["actual_tokens"] for item in agents.values()]
    active_values = [item["active_wall_seconds"] or 0.0 for item in agents.values()]
    return {
        "team": {
            "hard_team_call_permits": permit_cap,
            "permits_acquired": len(ledger),
            "unused_permits": max(0, _int(permit_cap) - len(ledger)) if permit_cap is not None else None,
            "actual_input_tokens": sum(item["actual_input_tokens"] for item in agents.values()),
            "actual_output_tokens": sum(item["actual_output_tokens"] for item in agents.values()),
            "actual_tokens": sum(item["actual_tokens"] for item in agents.values()),
            "max_active_concurrency": _max_concurrency(starts, ends),
            "gini": {"permits": _gini(permit_values), "tokens": _gini(token_values), "active_wall_time": _gini(active_values)},
        },
        "per_agent": agents,
        "measurement_notes": [
            "active_wall_seconds 是 agent_started 至 agent_finished 的观测包络，非 CPU 时间。",
            "provider retries 已通过 permit ledger 单独计入。",
        ],
    }


def _blackboard_metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    started = _timestamp(next(iter(_events_of(events, "run_started")), {}))
    writes = _events_of(events, "shared_create")
    reads = _events_of(events, "shared_read")
    lineage: dict[str, dict[str, Any]] = {}
    for event in sorted(writes + reads, key=lambda item: _int(item.get("sequence"))):
        payload = event.get("payload") or {}
        path = payload.get("path")
        if not path:
            continue
        item = lineage.setdefault(str(path), {"writes": [], "reads": [], "cross_agent_reads": [], "exact_content_hash_links": []})
        record = {"event_id": event.get("event_id"), "agent_id": event.get("agent_id"), "content_hash": payload.get("content_hash"), "sequence": event.get("sequence")}
        if event.get("event_type") == "shared_create":
            item["writes"].append(record)
        else:
            item["reads"].append(record)
            prior_writes = [write for write in item["writes"] if write.get("agent_id") != event.get("agent_id")]
            if prior_writes:
                item["cross_agent_reads"].append({"read_event_id": event.get("event_id"), "writer_event_ids": [write["event_id"] for write in prior_writes]})
            for write in prior_writes:
                if write.get("content_hash") and write.get("content_hash") == record.get("content_hash"):
                    item["exact_content_hash_links"].append({"write_event_id": write["event_id"], "read_event_id": event.get("event_id")})
    first_write = _timestamp(writes[0]) if writes else None
    first_read = _timestamp(reads[0]) if reads else None
    return {
        "available": bool(writes or reads),
        "first_write_latency_seconds": _duration_seconds(started, first_write),
        "first_read_latency_seconds": _duration_seconds(started, first_read),
        "write_count": len(writes),
        "read_count": len(reads),
        "cross_agent_read_count": sum(len(item["cross_agent_reads"]) for item in lineage.values()),
        "path_lineage": lineage,
        "lineage_note": "path/content hash lineage proves storage exposure only; it does not prove a reader used, trusted, or acted on the content.",
    }


def _structured_team_metrics(events: list[dict[str, Any]], artifacts: dict[tuple[str, str], Any], findings: list[dict[str, Any]]) -> dict[str, Any]:
    created = _events_of(events, "task_created")
    completed = _events_of(events, "task_completed")
    claimed = _events_of(events, "task_claimed")
    released = _events_of(events, "task_released")
    conflicts = _events_of(events, "task_claim_conflict")
    observed = _events_of(events, "task_result_observed")
    created_by_id = {(event.get("payload") or {}).get("id"): event for event in created}
    completed_by_id = {(event.get("payload") or {}).get("task_id"): event for event in completed}
    claimed_by_id = {(event.get("payload") or {}).get("task_id"): event for event in claimed}
    released_ids = {(event.get("payload") or {}).get("task_id") for event in released}
    descriptions = []
    for event in created:
        description = _artifact_for(event, artifacts, "payload.description")
        if isinstance(description, str):
            descriptions.append(_observation(event, _normalize_text(description)))
    duplicate_tasks = _group_work(descriptions)
    task_evidence = {
        task_id: set((event.get("payload") or {}).get("evidence_refs") or [])
        for task_id, event in completed_by_id.items()
    }
    adoptions = []
    for task_id, evidence_refs in task_evidence.items():
        completer = completed_by_id[task_id].get("agent_id")
        for index, finding in enumerate(findings):
            adopted = sorted(evidence_refs & set(finding.get("evidence_refs") or []))
            if adopted and finding.get("submitted_by") != completer:
                adoptions.append({"task_id": task_id, "task_completer": completer, "finding_index": index, "finding_agent": finding.get("submitted_by"), "evidence_refs": adopted})
    unfinished = []
    for task_id, event in created_by_id.items():
        if task_id not in completed_by_id:
            state = "claimed_without_completion" if task_id in claimed_by_id and task_id not in released_ids else "open_or_released_without_completion"
            unfinished.append({"task_id": task_id, "state_at_run_end": state, "creator": event.get("agent_id")})
    return {
        "available": bool(created or claimed or conflicts or completed or observed),
        "tasks_created": len(created),
        "tasks_claimed": len(claimed),
        "claim_conflicts": {"count": len(conflicts), "events": [event.get("event_id") for event in conflicts]},
        "tasks_released": len(released),
        "tasks_completed": len(completed),
        "unfinished_tasks_at_run_end": unfinished,
        "duplicate_task_descriptions": duplicate_tasks,
        "task_result_observations": {"count": len(observed), "events": [event.get("event_id") for event in observed]},
        "task_result_evidence_adoption": {"count": len(adoptions), "records": adoptions},
        "adoption_note": "仅当后续 finding 显式复用 completed task 的 evidence_ref 时计为 adoption；任务被列出或时间相邻不计。",
    }


def _resolve_condition_runs(block_dir: Path, expected: dict[str, dict[str, Any]], supplied: Mapping[str, Path] | None) -> dict[str, list[Path]]:
    resolved: dict[str, list[Path]] = defaultdict(list)
    if supplied:
        for condition_id, path in supplied.items():
            resolved[str(condition_id)].append(Path(path))
        return resolved
    for manifest_path in block_dir.rglob("run_manifest.json"):
        manifest = _read_json(manifest_path, {})
        for condition_id, spec in expected.items():
            if manifest.get("mode") == spec.get("mode") and manifest.get("agent_count") == spec.get("agent_count"):
                resolved[condition_id].append(manifest_path.parent)
    return resolved


def _comparison_projection(metrics: dict[str, Any]) -> dict[str, Any]:
    evaluation = metrics.get("evaluation") or {}
    allocation = metrics.get("resource_allocation") or {}
    return {
        "positive_recall": evaluation.get("positive_recall"),
        "known_near_miss_false_positives": evaluation.get("known_near_miss_false_positives"),
        "unmatched_review": evaluation.get("unmatched_review"),
        "invalid_submissions": evaluation.get("invalid_submissions"),
        "duplicates": evaluation.get("duplicates"),
        "duplicate_work": (metrics.get("duplicate_work") or {}).get("aggregate"),
        "resource": (allocation.get("team") or {}),
        "blackboard": {key: (metrics.get("blackboard") or {}).get(key) for key in ("write_count", "read_count", "cross_agent_read_count", "first_write_latency_seconds", "first_read_latency_seconds")},
        "structured_team": {key: (metrics.get("structured_team") or {}).get(key) for key in ("tasks_created", "tasks_claimed", "tasks_completed", "claim_conflicts", "task_result_evidence_adoption")},
    }


def _comparisons_to_s1(included: dict[str, dict[str, Any]]) -> dict[str, Any]:
    baseline = included.get("S1", {}).get("metrics")
    if not baseline:
        return {"status": "S1_not_included", "rows": {}}
    base_recall = _nested_number(baseline, "positive_recall", "value")
    base_tokens = _nested_number(baseline, "resource", "actual_tokens")
    base_work = _nested_number(baseline, "duplicate_work", "cross_agent_duplicate_ratio")
    rows = {}
    for condition_id, row in included.items():
        metrics = row.get("metrics") or {}
        rows[condition_id] = {
            "positive_recall_delta": _subtract(_nested_number(metrics, "positive_recall", "value"), base_recall),
            "actual_tokens_delta": _subtract(_nested_number(metrics, "resource", "actual_tokens"), base_tokens),
            "cross_agent_duplicate_work_ratio_delta": _subtract(_nested_number(metrics, "duplicate_work", "cross_agent_duplicate_ratio"), base_work),
        }
    return {"status": "observational", "baseline": "S1", "rows": rows}


def _shell_command(event: dict[str, Any], artifacts: dict[tuple[str, str], Any]) -> str | None:
    payload = event.get("payload") or {}
    if payload.get("tool") != "run_shell":
        return None
    arguments = _artifact_for(event, artifacts, "payload.arguments")
    if isinstance(arguments, dict) and isinstance(arguments.get("command"), str):
        return arguments["command"]
    return None


def _shell_fingerprint(command: str) -> tuple[str | None, str | None]:
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    normalized = " ".join(tokens).lower()
    executable = Path(tokens[0]).name if tokens else ""
    if executable in _SEARCH_COMMANDS or any(token in _SEARCH_COMMANDS for token in tokens[:3]):
        return "search", normalized
    if executable in _TEST_COMMANDS or any(token in _TEST_COMMANDS for token in tokens) or ("-m" in tokens and any(token in {"pytest", "unittest"} for token in tokens)):
        return "test", normalized
    return None, None


def _artifact_index(run_dir: Path) -> dict[tuple[str, str], Any]:
    index: dict[tuple[str, str], Any] = {}
    for record in _read_jsonl(run_dir / "logs" / "artifacts"):
        event_id = record.get("event_id")
        field = record.get("field")
        if event_id and field:
            index[(str(event_id), str(field))] = record.get("content")
    return index


def _artifact_for(event: dict[str, Any], artifacts: dict[tuple[str, str], Any], field: str) -> Any:
    return artifacts.get((str(event.get("event_id")), field))


def _observation(event: dict[str, Any], fingerprint: str | None) -> dict[str, Any]:
    return {"event_id": event.get("event_id"), "agent_id": event.get("agent_id"), "fingerprint": fingerprint}


def _events_of(events: list[dict[str, Any]], event_type: str) -> list[dict[str, Any]]:
    return [event for event in events if event.get("event_type") == event_type]


def _agent_ids(events: list[dict[str, Any]], summary: dict[str, Any]) -> list[str]:
    values = {str(event["agent_id"]) for event in events if event.get("agent_id")}
    values.update(str(item.get("agent_id")) for item in summary.get("agent_results") or [] if item.get("agent_id"))
    return sorted(values)


def _normalize_path(value: Any) -> str:
    text = str(value or "").replace("\\", "/").strip().lower()
    return text.removeprefix("target/").removeprefix("./")


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _timestamp(event: dict[str, Any]) -> datetime | None:
    value = event.get("timestamp")
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _duration_seconds(start: datetime | None, end: datetime | None) -> float | None:
    return (end - start).total_seconds() if start is not None and end is not None else None


def _max_concurrency(starts: Mapping[str, datetime | None], ends: Mapping[str, datetime | None]) -> int:
    points = []
    for agent_id, start in starts.items():
        end = ends.get(agent_id)
        if start is not None and end is not None:
            points.append((start, 1))
            points.append((end, -1))
    active = maximum = 0
    for _, delta in sorted(points, key=lambda item: (item[0], item[1])):
        active += delta
        maximum = max(maximum, active)
    return maximum


def _gini(values: Iterable[float | int]) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered or sum(ordered) == 0:
        return 0.0
    count = len(ordered)
    return (2 * sum((index + 1) * value for index, value in enumerate(ordered)) / (count * sum(ordered))) - (count + 1) / count


def _nested_number(value: dict[str, Any], first: str, second: str) -> float | int | None:
    nested = value.get(first) or {}
    return nested.get(second) if isinstance(nested, dict) else None


def _subtract(left: float | int | None, right: float | int | None) -> float | int | None:
    return left - right if left is not None and right is not None else None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _read_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if path.is_dir():
        records: list[dict[str, Any]] = []
        for child in sorted(path.glob("*.jsonl")):
            records.extend(_read_jsonl(child))
        return records
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _parse_condition_runs(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        condition, separator, raw_path = value.partition("=")
        if not separator or not condition or not raw_path:
            raise ValueError("--condition-run must use CONDITION_ID=RUN_DIR")
        result[condition] = Path(raw_path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 CoordAudit 单 run metrics 或 matched-block comparison。")
    parser.add_argument("run_dir", nargs="?", help="已完成 run 的目录")
    parser.add_argument("--block-dir", help="含 block_manifest.json 的冻结 block 目录")
    parser.add_argument("--condition-run", action="append", default=[], help="显式映射，如 S1=/path/to/run")
    parser.add_argument("--output", help="可选输出路径；默认写 metrics.json 或 block_comparison.json")
    parser.add_argument("--no-write", action="store_true", help="只计算并打印，不写默认产物")
    args = parser.parse_args()
    if bool(args.run_dir) == bool(args.block_dir):
        parser.error("必须且只能提供 run_dir 或 --block-dir")
    if args.block_dir:
        result = analyze_matched_block(Path(args.block_dir), _parse_condition_runs(args.condition_run), write=not args.no_write)
    else:
        if args.condition_run:
            parser.error("--condition-run 只能与 --block-dir 一起使用")
        result = analyze_run(Path(args.run_dir), write=not args.no_write)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    if args.output:
        _write_json(Path(args.output), result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
