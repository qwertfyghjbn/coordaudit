"""Deterministically replay model-visible transcripts without provider calls.

This module diagnoses how an audit progressed from discovery to submission.  It
uses only the public run manifest, summary, events and model-visible transcript;
hidden evaluator assets and ground truth are deliberately out of scope.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any


COMPLETION_PATH_SCHEMA_VERSION = 1

_CATEGORY_PATTERNS = {
    "path_traversal": re.compile(r"path traversal|directory traversal|\.\./(?:\.\./)*|escape(?:s|d)? the base directory", re.I),
    "ssrf": re.compile(r"\bssrf\b|server[- ]side request forgery|169\.254\.169\.254|requests? to (?:arbitrary|internal) hosts?", re.I),
    "ssti": re.compile(r"\bssti\b|server[- ]side template injection|\{\{\s*7\s*\*\s*7\s*\}\}", re.I),
    "command_injection": re.compile(r"command injection", re.I),
    "sql_injection": re.compile(r"sql injection", re.I),
    "deserialization": re.compile(r"(?:unsafe |insecure )?deseriali[sz]ation", re.I),
    "access_control": re.compile(r"broken access control|idor\b|insecure direct object reference", re.I),
    "authentication": re.compile(r"authentication bypass", re.I),
    "information_disclosure": re.compile(r"information disclosure|sensitive (?:data|information) exposure", re.I),
}

_DISCOVERY_SHELL = re.compile(r"(?:^|[;&|]\s*)(?:find|ls|rg|grep|git\s+grep)\b", re.I)
_GENERIC_SECURITY_PATTERN = re.compile(
    r"\b(?:verify|analy[sz]e|identified?|confirm(?:ed)?|main)\b.{0,40}\bvulnerabilit(?:y|ies)\b",
    re.I,
)


def replay_completion_path(run_dir: Path, *, write: bool = True) -> dict[str, Any]:
    """Replay one completed run and report observable completion-path signals."""
    run_dir = Path(run_dir)
    summary = _read_json(run_dir / "summary.json", {})
    manifest = _read_json(run_dir / "run_manifest.json", {})
    output_ceiling = (manifest.get("model_profile") or {}).get("max_output_tokens")
    usage_by_permit = {
        item.get("permit_id"): item.get("token_usage") or {}
        for item in (summary.get("budget") or {}).get("permit_ledger") or []
        if item.get("permit_id")
    }
    result_by_agent = {
        item.get("agent_id"): item
        for item in summary.get("agent_results") or []
        if item.get("agent_id")
    }

    transcript_dir = run_dir / "logs" / "transcripts"
    transcript_paths = sorted(transcript_dir.glob("*.jsonl"))
    if not transcript_paths:
        raise ValueError(f"no model-visible transcripts found under {transcript_dir}")

    agents: dict[str, Any] = {}
    for transcript_path in transcript_paths:
        records = _read_jsonl(transcript_path)
        agent_id = str(records[0].get("agent_id") if records else transcript_path.stem)
        agents[agent_id] = _replay_agent(
            records,
            usage_by_permit=usage_by_permit,
            output_ceiling=output_ceiling,
            agent_result=result_by_agent.get(agent_id) or {},
        )

    pairwise_inspection = []
    for left_id, right_id in combinations(sorted(agents), 2):
        left = set(agents[left_id]["evidence"]["unique_paths"])
        right = set(agents[right_id]["evidence"]["unique_paths"])
        union = left | right
        pairwise_inspection.append(
            {
                "agents": [left_id, right_id],
                "shared_unique_paths": len(left & right),
                "union_unique_paths": len(union),
                "jaccard": len(left & right) / len(union) if union else 0.0,
            }
        )

    all_path_sets = [set(agent["evidence"]["unique_paths"]) for agent in agents.values()]
    common_paths = sorted(set.intersection(*all_path_sets)) if all_path_sets else []
    diagnostic = {
        "agents_with_category_hypothesis_signal": sum(bool(agent["hypothesis_signals"]) for agent in agents.values()),
        "agents_with_generic_security_signal": sum(bool(agent["generic_security_signal_steps"]) for agent in agents.values()),
        "agents_with_evidence_refs": sum(bool(agent["evidence"]["refs"]) for agent in agents.values()),
        "agents_with_submit_attempt": sum(bool(agent["submissions"]) for agent in agents.values()),
        "malformed_tool_argument_calls": sum(len(agent["malformed_tool_calls"]) for agent in agents.values()),
        "malformed_submit_calls": sum(
            sum(call["name"] == "submit_findings" for call in agent["malformed_tool_calls"])
            for agent in agents.values()
        ),
        "output_ceiling_hit_calls": sum(len(agent["output_ceiling_hit_steps"]) for agent in agents.values()),
        "finish_reason_recorded_calls": sum(agent["finish_reason_recorded_calls"] for agent in agents.values()),
        "all_agents_budget_exhausted": bool(agents)
        and all(agent["stop_reason"] == "budget_exhausted" for agent in agents.values()),
    }
    result = {
        "schema_version": COMPLETION_PATH_SCHEMA_VERSION,
        "run_id": summary.get("run_id"),
        "run_dir": str(run_dir),
        "mode": summary.get("mode"),
        "agent_count": summary.get("agent_count"),
        "output_ceiling": output_ceiling,
        "diagnostic_signals": diagnostic,
        "agents": agents,
        "cross_agent_inspection": {
            "common_unique_path_count": len(common_paths),
            "common_unique_paths": common_paths,
            "all_agents_read_same_unique_path_set": bool(all_path_sets)
            and all(paths == all_path_sets[0] for paths in all_path_sets[1:]),
            "pairwise": pairwise_inspection,
        },
        "interpretation_limits": [
            "漏洞类别信号来自模型响应正文或模型生成的工具参数，是确定性词法观察，不证明 finding 正确或命中 ground truth。",
            "evidence_ref_acquired 只证明 read_file 结果进入模型可见 transcript，不证明模型将其用于某个候选 finding。",
            "output_tokens 等于 ceiling 只表示截断风险；没有 provider finish_reason 时，单凭 token 数不能证明截断。",
            "本分析不读取 evaluator_private、ground_truth、provenance 或 verification。",
        ],
        "hidden_evaluator_used": False,
    }
    if write:
        _write_json(run_dir / "completion_path_replay.json", result)
    return result


def _replay_agent(
    records: list[dict[str, Any]],
    *,
    usage_by_permit: dict[str, dict[str, Any]],
    output_ceiling: int | None,
    agent_result: dict[str, Any],
) -> dict[str, Any]:
    responses = sorted(
        (record for record in records if record.get("kind") == "model_response"),
        key=lambda record: int(record.get("sequence") or 0),
    )
    tool_results = {
        (record.get("content") or {}).get("tool_call_id"): record
        for record in records
        if record.get("kind") == "tool_result"
    }
    phase_counts: Counter[str] = Counter()
    first_phase_step: dict[str, int] = {}
    evidence_records: list[dict[str, Any]] = []
    hypothesis_signals: list[dict[str, Any]] = []
    generic_security_steps: list[int] = []
    malformed_calls: list[dict[str, Any]] = []
    submissions: list[dict[str, Any]] = []
    ceiling_steps: list[int] = []
    finish_reason_recorded = 0
    timeline = []

    for response in responses:
        content = response.get("content") or {}
        step = int(content.get("step") or 0)
        permit_id = content.get("permit_id")
        response_text = str(content.get("content") or "")
        metadata = content.get("model_metadata") or {}
        finish_reason = metadata.get("finish_reason")
        if finish_reason is not None:
            finish_reason_recorded += 1
        usage = usage_by_permit.get(permit_id) or {}
        output_tokens = usage.get("output_tokens")
        ceiling_hit = bool(
            output_ceiling is not None
            and output_tokens is not None
            and int(output_tokens) >= int(output_ceiling)
        )
        if ceiling_hit:
            ceiling_steps.append(step)

        phases: set[str] = set()
        categories = _categories(response_text)
        if _GENERIC_SECURITY_PATTERN.search(response_text):
            generic_security_steps.append(step)
        if categories:
            phases.add("hypothesize")
            hypothesis_signals.append(
                {"step": step, "source": "response_content", "categories": categories, "excerpt": _excerpt(response_text)}
            )

        tool_names = []
        for call in content.get("tool_calls") or []:
            name = str(call.get("name") or "")
            tool_names.append(name)
            raw_arguments = str(call.get("arguments") or "{}")
            try:
                arguments = json.loads(raw_arguments)
                arguments_valid = isinstance(arguments, dict)
                if not arguments_valid:
                    raise ValueError("tool arguments are not an object")
            except (json.JSONDecodeError, ValueError) as exc:
                arguments = None
                malformed_calls.append(
                    {"step": step, "name": name, "error": str(exc), "raw_length": len(raw_arguments), "ceiling_hit": ceiling_hit}
                )

            if name == "list_files":
                phases.add("discover")
            elif name == "read_file":
                phases.add("inspect")
                evidence = _evidence_from_result(tool_results.get(call.get("id")))
                if evidence:
                    phases.add("evidence")
                    evidence_records.append({"step": step, **evidence})
            elif name == "run_shell":
                command = str((arguments or {}).get("command") or raw_arguments)
                phases.add("discover" if _DISCOVERY_SHELL.search(command) else "verify")
                command_categories = _categories(command)
                if command_categories:
                    phases.add("hypothesize")
                    hypothesis_signals.append(
                        {"step": step, "source": "tool_arguments", "categories": command_categories, "excerpt": _excerpt(command)}
                    )
            elif name == "submit_findings":
                phases.add("submit")
                findings = (arguments or {}).get("findings") if isinstance(arguments, dict) else None
                result_payload = _tool_result_payload(tool_results.get(call.get("id")))
                submissions.append(
                    {
                        "step": step,
                        "arguments_valid_json_object": arguments is not None,
                        "model_generated_finding_count": len(findings) if isinstance(findings, list) else None,
                        "observable_title_field_count": len(re.findall(r'"title"\s*:', raw_arguments)),
                        "observable_category_values": re.findall(r'"category"\s*:\s*"([^"]+)"', raw_arguments),
                        "observable_evidence_refs": sorted(set(re.findall(r'evt_\d+', raw_arguments))),
                        "tool_result": result_payload,
                        "ceiling_hit": ceiling_hit,
                    }
                )

        if not phases and response_text:
            phases.add("reflect")
        for phase in phases:
            phase_counts[phase] += 1
            first_phase_step.setdefault(phase, step)
        timeline.append(
            {
                "step": step,
                "phases": sorted(phases),
                "tool_names": tool_names,
                "hypothesis_categories": categories,
                "output_tokens": output_tokens,
                "output_ceiling_hit": ceiling_hit,
                "finish_reason": finish_reason,
            }
        )

    stop_reason = agent_result.get("stop_reason")
    return {
        "stop_reason": stop_reason,
        "model_calls_observed": len(responses),
        "phase_counts": dict(sorted(phase_counts.items())),
        "first_phase_step": dict(sorted(first_phase_step.items())),
        "hypothesis_signals": _dedupe_signals(hypothesis_signals),
        "generic_security_signal_steps": sorted(set(generic_security_steps)),
        "evidence": {
            "read_count": len(evidence_records),
            "unique_path_count": len({item["path"] for item in evidence_records}),
            "unique_paths": sorted({item["path"] for item in evidence_records}),
            "refs": [item["evidence_ref"] for item in evidence_records],
            "invalid_payload_json_count": sum(item.get("payload_json_valid") is False for item in evidence_records),
            "records": evidence_records,
        },
        "submissions": submissions,
        "malformed_tool_calls": malformed_calls,
        "output_ceiling_hit_steps": ceiling_steps,
        "finish_reason_recorded_calls": finish_reason_recorded,
        "last_model_step": timeline[-1] if timeline else None,
        "failure_classification": _classify_failure(
            stop_reason=stop_reason,
            hypothesis_signals=hypothesis_signals,
            evidence_records=evidence_records,
            submissions=submissions,
            malformed_calls=malformed_calls,
        ),
        "timeline": timeline,
    }


def _classify_failure(
    *,
    stop_reason: str | None,
    hypothesis_signals: list[dict[str, Any]],
    evidence_records: list[dict[str, Any]],
    submissions: list[dict[str, Any]],
    malformed_calls: list[dict[str, Any]],
) -> str:
    if any(call["name"] == "submit_findings" for call in malformed_calls):
        if any((item.get("tool_result") or {}).get("ok") and (item.get("tool_result") or {}).get("count") == 0 for item in submissions):
            return "malformed_submit_arguments_accepted_as_empty_payload"
        return "malformed_submit_arguments"
    if submissions:
        if any(item.get("model_generated_finding_count", 0) > 0 for item in submissions):
            return "nonempty_submission_observed"
        return "empty_submission_observed"
    if stop_reason == "budget_exhausted":
        if hypothesis_signals and evidence_records:
            return "candidate_signal_and_evidence_available_but_no_submission_before_budget_exhaustion"
        if hypothesis_signals:
            return "candidate_signal_but_no_submission_before_budget_exhaustion"
        return "no_candidate_signal_before_budget_exhaustion"
    if hypothesis_signals and evidence_records:
        return "candidate_signal_and_evidence_available_but_no_submission"
    if hypothesis_signals:
        return "candidate_signal_without_submission"
    return "no_candidate_signal_or_submission"


def _categories(text: str) -> list[str]:
    return [category for category, pattern in _CATEGORY_PATTERNS.items() if pattern.search(text)]


def _evidence_from_result(record: dict[str, Any] | None) -> dict[str, Any] | None:
    payload = _tool_result_payload(record)
    if isinstance(payload, dict) and payload.get("evidence_ref") and payload.get("path"):
        return {"evidence_ref": str(payload["evidence_ref"]), "path": str(payload["path"])}
    # A historical redactor could replace an absolute path inside the nested
    # JSON string without preserving its closing quote.  The two lineage fields
    # precede source content, so recover only those exact JSON string fields.
    raw = ((record or {}).get("content") or {}).get("content")
    if isinstance(raw, str):
        ref_match = re.search(r'"evidence_ref"\s*:\s*"([^"]+)"', raw)
        path_match = re.search(r'"path"\s*:\s*"([^"]+)"', raw)
        if ref_match and path_match:
            return {"evidence_ref": ref_match.group(1), "path": path_match.group(1), "payload_json_valid": False}
    return None


def _tool_result_payload(record: dict[str, Any] | None) -> Any:
    if not record:
        return None
    raw = (record.get("content") or {}).get("content")
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"unparsed_content": _excerpt(raw)}


def _dedupe_signals(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[int, tuple[str, ...]]] = set()
    result = []
    for signal in signals:
        key = (signal["step"], tuple(signal["categories"]))
        if key in seen:
            continue
        seen.add(key)
        result.append(signal)
    return result


def _excerpt(text: str, limit: int = 240) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3] + "..."


def _read_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="离线重放 CoordAudit completion path；不会调用 provider。")
    parser.add_argument("run_dir", help="已完成 run 的目录")
    parser.add_argument("--no-write", action="store_true", help="不写 completion_path_replay.json")
    parser.add_argument("--output", help="另写一份 JSON 输出")
    args = parser.parse_args()
    result = replay_completion_path(Path(args.run_dir), write=not args.no_write)
    if args.output:
        _write_json(Path(args.output), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
