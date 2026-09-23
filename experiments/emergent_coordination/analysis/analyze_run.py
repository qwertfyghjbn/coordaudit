"""Evidence-only run metrics and matched-block comparison artifacts."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments.emergent_coordination.harness.call_role import CALL_ROLES, COORDINATION_TOOLS, classify_call_role
from experiments.emergent_coordination.harness.completion import FINALIZATION_POLICIES, FINALIZATION_RESERVE, HARD_FINALIZATION_POLICIES


METRICS_SCHEMA_VERSION = 2
BLOCK_COMPARISON_SCHEMA_VERSION = 1
_SEARCH_COMMANDS = frozenset({"rg", "grep", "git-grep", "ag", "ack"})
_TEST_COMMANDS = frozenset({"pytest", "unittest", "tox", "nox"})
_CEILING_FINISH_REASONS = frozenset({"length"})
_SELECTED_FOREIGN_TASK_RE = re.compile(
    r"\bselected\s+foreign\s+task(?:\s+id)?[\s*`]*[:#-]?[\s*`]*(task_[A-Za-z0-9_-]+)`?",
    re.IGNORECASE,
)
_EXPLORATION_TOOL_NAMES = frozenset({"read_file", "list_files", "run_shell"}) | COORDINATION_TOOLS
_CEILING_FINISH_REASONS = frozenset({"length"})


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
    mode = str(summary.get("mode") or "")
    blackboard = _blackboard_metrics(events, mode=mode)
    structured_team = _structured_team_metrics(events, artifacts, findings, mode=mode)
    output_ceiling = _output_ceiling(events, run_dir)
    completion = _completion_metrics(events, run_dir)
    transcripts = [record for path in sorted((run_dir / "logs" / "transcripts").glob("*.jsonl")) for record in _read_jsonl(path)]
    result_sync = _result_sync_metrics(events, findings, agent_ids, transcripts)
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
        "output_ceiling": output_ceiling,
        "completion": completion,
        "result_sync": result_sync,
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


def _output_ceiling(events: list[dict[str, Any]], run_dir: Path) -> dict[str, Any]:
    """Per-call output-ceiling pressure by call role.

    Runtime ``llm_call`` events carry ``call_role``/``output_tokens``/
    ``max_output_tokens``/``finish_reason`` directly.  Older runs are backfilled
    from ``tool_call`` children, ``token_usage``, ``completion_phase_started``,
    and the run manifest, using the same classifier as the runtime path.
    """
    manifest = _read_json(Path(run_dir) / "run_manifest.json", {})
    finalization_first_step = _finalization_first_step(events, manifest)
    tools_by_call: dict[str, set[str]] = defaultdict(set)
    for event in _events_of(events, "tool_call"):
        tool = str((event.get("payload") or {}).get("tool") or "")
        if not tool:
            continue
        for parent in event.get("parent_event_ids") or []:
            tools_by_call[str(parent)].add(tool)
    calls: list[dict[str, Any]] = []
    for event in _events_of(events, "llm_call"):
        payload = event.get("payload") or {}
        if payload.get("outcome") != "succeeded":
            continue
        event_id = str(event.get("event_id"))
        role = payload.get("call_role")
        role_source = "payload"
        if role not in CALL_ROLES:
            role = classify_call_role(
                tools_by_call.get(event_id, set()),
                finalization_active=finalization_first_step is not None
                and _int(payload.get("step")) >= finalization_first_step,
            )
            role_source = "derived"
        token_usage = event.get("token_usage") or {}
        calls.append(
            {
                "role": role,
                "output_tokens": payload.get("output_tokens", token_usage.get("output_tokens")),
                "finish_reason": payload.get("finish_reason")
                or (payload.get("model_metadata") or {}).get("finish_reason"),
            }
        )
    max_output_tokens = None
    for event in _events_of(events, "llm_call"):
        value = (event.get("payload") or {}).get("max_output_tokens")
        if value is not None:
            max_output_tokens = value
            break
    if max_output_tokens is None:
        max_output_tokens = (manifest.get("model_profile") or {}).get("max_output_tokens")
    calls_by_role = Counter(call["role"] for call in calls)
    hits_by_role = Counter(
        call["role"] for call in calls if str(call.get("finish_reason")) in _CEILING_FINISH_REASONS
    )

    def _hit_rate(role: str | None) -> float | None:
        total = sum(calls_by_role.values()) if role is None else calls_by_role.get(role, 0)
        hits = sum(hits_by_role.values()) if role is None else hits_by_role.get(role, 0)
        return hits / total if total else None

    def _percentiles(values: list[int]) -> dict[str, int | None]:
        if not values:
            return {"p50": None, "p90": None, "p95": None, "p99": None}
        if len(values) == 1:
            return {key: values[0] for key in ("p50", "p90", "p95", "p99")}
        cutpoints = statistics.quantiles(values, n=100, method="inclusive")
        return {
            "p50": round(cutpoints[49]),
            "p90": round(cutpoints[89]),
            "p95": round(cutpoints[94]),
            "p99": round(cutpoints[98]),
        }

    overall_tokens = [_int(call.get("output_tokens")) for call in calls]
    return {
        "max_output_tokens": max_output_tokens,
        "calls": len(calls),
        "ceiling_hits": sum(hits_by_role.values()),
        "ceiling_hit_rate_overall": _hit_rate(None),
        "ceiling_hit_rate_by_role": {role: _hit_rate(role) for role in CALL_ROLES},
        "calls_by_role": {role: calls_by_role.get(role, 0) for role in CALL_ROLES},
        "ceiling_hits_by_role": {role: hits_by_role.get(role, 0) for role in CALL_ROLES},
        "output_tokens_percentiles_overall": _percentiles(overall_tokens),
        "output_tokens_percentiles_by_role": {
            role: _percentiles([_int(call.get("output_tokens")) for call in calls if call["role"] == role])
            for role in CALL_ROLES
        },
        "measurement_notes": [
            "ceiling hit 判据为 finish_reason=length 的成功调用；provider 失败调用不参与。",
            "call_role 优先取运行时记录；缺失时按 tool_call 子事件与 finalization 边界回溯推导，与运行时分类器同源。",
            "无该角色调用的 hit rate 记为 null，不按 0 解释。",
        ],
    }


def _finalization_first_step(events: list[dict[str, Any]], manifest: dict[str, Any]) -> int | None:
    started = _events_of(events, "completion_phase_started")
    if started:
        return min(_int((event.get("payload") or {}).get("step")) for event in started)
    if manifest.get("completion_policy") in FINALIZATION_POLICIES:
        max_steps = _int(manifest.get("max_steps"))
        if max_steps > FINALIZATION_RESERVE:
            return max_steps - FINALIZATION_RESERVE + 1
    return None


_CONVERGENCE_CUE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\benough evidence\b",
        r"\bsufficient evidence\b",
        r"\bready to submit\b",
        r"\btime to submit\b",
        r"\bconsolidate (?:my |the )?findings\b",
        r"\bstop (?:exploring|searching|scanning|looking)\b",
        r"\bdiminishing returns?\b",
        r"\bfinali[sz]e (?:my |the )?(?:submission|report|findings)\b",
        r"\bprepare (?:my |the )?(?:final )?(?:submission|payload|findings)\b",
        r"\bi have (?:enough|sufficient)\b",
        r"\bwrapping up\b",
        r"\bcompile (?:my |the )?findings\b",
    )
)
# Negation words immediately before a cue suppress it (e.g. "I do not have
# enough evidence").  Word-bounded because "Note:" must not match "not".
_CONVERGENCE_NEGATION_RE = re.compile(r"\b(?:not|no|never|without|lacks?|lacking|insufficient|need)\b|n't", re.IGNORECASE)


def _first_convergence_candidates(run_dir: Path) -> dict[str, dict[str, Any]]:
    """Earliest transcript cue that *may* express cognitive convergence.

    A mechanical candidate only: negation-guarded regex hits on
    model-response text.  The authoritative ``first_convergence_step``
    comes from trace review; this exists so the candidate judgement is
    reproducible and auditable.
    """
    candidates: dict[str, dict[str, Any]] = {}
    transcript_dir = run_dir / "logs" / "transcripts"
    if not transcript_dir.is_dir():
        return candidates
    for path in sorted(transcript_dir.glob("*.jsonl")):
        for record in _read_jsonl(path):
            if record.get("kind") != "model_response":
                continue
            content = (record.get("content") or {})
            text = str(content.get("content") or "")
            if not text:
                continue
            for pattern in _CONVERGENCE_CUE_PATTERNS:
                match = pattern.search(text)
                if match is None:
                    continue
                window = text[max(0, match.start() - 80) : match.start()]
                if _CONVERGENCE_NEGATION_RE.search(window):
                    continue
                agent = str(record.get("agent_id"))
                candidate = {
                    "step": _int(content.get("step")),
                    "cue": text[match.start() : match.start() + 120],
                    "transcript_id": record.get("transcript_id"),
                }
                existing = candidates.get(agent)
                if existing is None or candidate["step"] < existing["step"]:
                    candidates[agent] = candidate
                break
    return candidates


def _completion_metrics(events: list[dict[str, Any]], run_dir: Path) -> dict[str, Any]:
    """Mechanical completion-path metrics per agent.

    Everything here is derivable from events and transcripts: finalization
    window, dispatched exploration, submit attempts, hard-gate rejections,
    a convergence *cue* candidate, and a rule-based binding candidate.  The
    binding candidate never replaces trace review; it only pre-classes runs
    for it.
    """
    manifest = _read_json(Path(run_dir) / "run_manifest.json", {})
    policy = manifest.get("completion_policy")
    generation = "hard_gate" if policy in HARD_FINALIZATION_POLICIES else ("advisory" if policy in FINALIZATION_POLICIES else None)

    finalization_start: int | None = None
    started = _events_of(events, "completion_phase_started")
    if started:
        finalization_start = min(_int((event.get("payload") or {}).get("step")) for event in started)
        policy = (started[0].get("payload") or {}).get("policy") or policy
    team_started = _events_of(events, "team_finalization_started")
    team_payload = (team_started[0].get("payload") or {}) if team_started else {}
    team_finalization = {
        "triggered": bool(team_started),
        "trigger_call_index": team_payload.get("trigger_call_index"),
        "trigger_remaining_permits": team_payload.get("trigger_remaining_permits"),
        "reserve": team_payload.get("reserve"),
        "policy": team_payload.get("policy") or manifest.get("team_finalization_policy"),
        "exactly_once": len(team_started) <= 1,
        "active_agents_at_trigger": team_payload.get("active_agents") or [],
    }

    step_by_event: dict[str, int | None] = {}
    llm_calls_by_agent: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for event in _events_of(events, "llm_call"):
        step_by_event[str(event.get("event_id"))] = _int((event.get("payload") or {}).get("step"))
        if event.get("agent_id"):
            llm_calls_by_agent[str(event.get("agent_id"))].append((_int(event.get("sequence")), _int((event.get("payload") or {}).get("step"))))
    for calls in llm_calls_by_agent.values():
        calls.sort()

    def step_of(event: dict[str, Any]) -> int | None:
        for parent in event.get("parent_event_ids") or []:
            if str(parent) in step_by_event:
                return step_by_event[str(parent)]
        calls = llm_calls_by_agent.get(str(event.get("agent_id")), [])
        sequence = _int(event.get("sequence"))
        step: int | None = None
        for call_sequence, call_step in calls:
            if call_sequence <= sequence:
                step = call_step
            else:
                break
        return step

    dispatches: list[dict[str, Any]] = []
    for event in sorted(_events_of(events, "tool_call"), key=lambda item: _int(item.get("sequence"))):
        step_by_event[str(event.get("event_id"))] = step_of(event)
        payload = event.get("payload") or {}
        if "arguments" in payload or "argument_error" in payload:
            dispatches.append(event)

    submitted = _events_of(events, "finding_submitted")
    validator_rejections = _events_of(events, "finding_submission_rejected")
    prohibited = _events_of(events, "prohibited_tool_attempt")
    convergence_candidates = _first_convergence_candidates(Path(run_dir))

    agent_ids = sorted({str(event.get("agent_id")) for event in events if event.get("agent_id")})
    per_agent: dict[str, Any] = {}
    for agent in agent_ids:
        agent_dispatches = [event for event in dispatches if str(event.get("agent_id")) == agent]
        exploration_steps = [
            step_of(event)
            for event in agent_dispatches
            if str((event.get("payload") or {}).get("tool") or "") in _EXPLORATION_TOOL_NAMES and "arguments" in (event.get("payload") or {})
        ]
        submit_dispatches = [
            event for event in agent_dispatches if str((event.get("payload") or {}).get("tool") or "") == "submit_findings"
        ]
        invalid_submit_arguments = sum(1 for event in submit_dispatches if "argument_error" in (event.get("payload") or {}))
        agent_submitted = [event for event in submitted if str(event.get("agent_id")) == agent]
        agent_rejections = [event for event in validator_rejections if str(event.get("agent_id")) == agent]
        validator_steps = [step_of(event) for event in agent_submitted + agent_rejections]
        # A submit dispatch and the validator event it triggers share one step;
        # attempt counting is therefore step-level (deduplicated).
        attempt_steps = sorted({step for step in list(step_of(event) for event in submit_dispatches) + validator_steps if step is not None})
        first_submit = attempt_steps[0] if attempt_steps else None
        successful_submit = min((step_of(event) for event in agent_submitted if step_of(event) is not None), default=None)
        convergence = convergence_candidates.get(agent)
        convergence_step = convergence.get("step") if convergence else None
        agent_prohibited = [
            {
                "event_id": event.get("event_id"),
                "step": _int((event.get("payload") or {}).get("step")),
                "requested_tool": (event.get("payload") or {}).get("requested_tool"),
                "arguments_sha256": (event.get("payload") or {}).get("arguments_sha256"),
            }
            for event in prohibited
            if str(event.get("agent_id")) == agent
        ]
        last_exploration = max((step for step in exploration_steps if step is not None), default=None)
        exploration_after_convergence = (
            sum(1 for step in exploration_steps if step is not None and convergence_step is not None and step > convergence_step)
            if convergence_step is not None
            else None
        )
        record: dict[str, Any] = {
            "finalization_policy": policy,
            "finalization_generation": generation,
            "finalization_start_step": min(
                (_int((event.get("payload") or {}).get("step")) for event in started if str(event.get("agent_id")) == agent),
                default=finalization_start,
            ),
            "first_convergence_candidate_step": convergence_step,
            "first_convergence_candidate_cue": convergence.get("cue") if convergence else None,
            "last_exploration_step": last_exploration,
            "exploration_call_count": len(exploration_steps),
            "exploration_calls_after_first_convergence": exploration_after_convergence,
            "first_submit_attempt_step": first_submit,
            "successful_submit_step": successful_submit,
            "submission_attempt_count": len(agent_submitted) + len(agent_rejections),
            "submit_tool_call_count": len(submit_dispatches),
            "invalid_submit_argument_count": invalid_submit_arguments,
            "invalid_or_rejected_submission_count": len(agent_rejections) + invalid_submit_arguments,
        }
        if finalization_start is not None:
            submit_after = [step for step in attempt_steps if step >= finalization_start]
            had_convergence_before = convergence_step is not None and convergence_step < finalization_start
            had_submit_before = first_submit is not None and first_submit < finalization_start
            stopped_before = last_exploration is not None and last_exploration < finalization_start
            successful_after = successful_submit is not None and successful_submit >= finalization_start
            record.update(
                {
                    "had_convergence_candidate_before_finalization": had_convergence_before,
                    "had_submit_attempt_before_finalization": had_submit_before,
                    "last_exploration_before_finalization": stopped_before,
                    "prohibited_tool_attempts_after_finalization": len(agent_prohibited),
                    "prohibited_tool_names": sorted({str(item["requested_tool"]) for item in agent_prohibited}),
                    "prohibited_tool_attempts": agent_prohibited,
                    "submit_attempts_after_finalization": len(submit_after),
                    "successful_submit_after_finalization": successful_after,
                    "steps_from_finalization_to_submit": successful_submit - finalization_start if successful_submit is not None else None,
                }
            )
            if generation != "hard_gate":
                binding = None
            elif not had_convergence_before and not had_submit_before and agent_prohibited:
                binding = "binding_strong"
            elif not had_convergence_before and not had_submit_before:
                binding = "binding_candidate"
            elif had_convergence_before and (had_submit_before or stopped_before):
                binding = "non_binding_strong"
            elif had_convergence_before:
                binding = "non_binding_candidate"
            else:
                binding = "ambiguous"
            record["hard_finalization_binding_candidate"] = binding
        per_agent[agent] = record

    return {
        "policy": manifest.get("completion_policy"),
        "generation": generation,
        "finalization_start_step": finalization_start,
        "team_finalization": team_finalization,
        "per_agent": per_agent,
        "measurement_notes": [
            "first_convergence_candidate 是对 transcript 的否定词防护正则命中，仅是候选信号；权威判定以 trace review 为准，未观察到时不应猜测。",
            "exploration 计数只统计 model-selected dispatch（read_file/list_files/run_shell/coordination 工具），write_file 不算探索。",
            "hard_finalization_binding_candidate 是机械规则：finalization 前无收敛候选且无提交尝试 → binding；有收敛候选且已停探索或已提交 → non_binding；其余 ambiguous。不替代 trace review。",
        ],
    }


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
    enforced_limits = budget.get("enforced_limits") or budget.get("caps") or {}
    permit_cap = enforced_limits.get("hard_team_call_permits")
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


def _model_tool_invocations(events: list[dict[str, Any]], tool_names: Iterable[str]) -> dict[str, int]:
    """Count model-selected tool calls once, before tool-side event fan-out.

    A single tool invocation can legitimately produce both the dispatch
    ``tool_call`` event and a tool-specific event.  The dispatch event is the
    one carrying the model-generated arguments, so it is the only safe source
    for invocation counts.
    """
    names = {str(name) for name in tool_names}
    counts = Counter()
    for event in _events_of(events, "tool_call"):
        payload = event.get("payload") or {}
        tool = str(payload.get("tool") or "")
        if tool in names and isinstance(payload.get("arguments"), dict):
            counts[tool] += 1
    return {name: counts[name] for name in sorted(names)}


def _blackboard_metrics(events: list[dict[str, Any]], *, mode: str) -> dict[str, Any]:
    started = _timestamp(next(iter(_events_of(events, "run_started")), {}))
    writes = _events_of(events, "shared_create")
    reads = _events_of(events, "shared_read")
    tool_invocations = _model_tool_invocations(events, ("shared_list", "shared_read", "shared_mkdir", "shared_create"))
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
        "available": mode == "raw_blackboard",
        "availability_note": "available 表示该 condition 向 Agent 暴露 generic shared-store 工具，不表示发生了共享活动。",
        "model_tool_invocations": tool_invocations,
        "tool_activity_observed": any(tool_invocations.values()),
        "content_exchange_observed": bool(writes or reads),
        "first_write_latency_seconds": _duration_seconds(started, first_write),
        "first_read_latency_seconds": _duration_seconds(started, first_read),
        "write_count": len(writes),
        "read_count": len(reads),
        "cross_agent_read_count": sum(len(item["cross_agent_reads"]) for item in lineage.values()),
        "path_lineage": lineage,
        "lineage_note": "path/content hash lineage proves storage exposure only; it does not prove a reader used, trusted, or acted on the content.",
    }


def _structured_team_metrics(
    events: list[dict[str, Any]],
    artifacts: dict[tuple[str, str], Any],
    findings: list[dict[str, Any]],
    *,
    mode: str,
) -> dict[str, Any]:
    created = _events_of(events, "task_created")
    completed = _events_of(events, "task_completed")
    claimed = _events_of(events, "task_claimed")
    released = _events_of(events, "task_released")
    conflicts = _events_of(events, "task_claim_conflict")
    observed = _events_of(events, "task_result_observed")
    lease_waits = _events_of(events, "task_initialization_lease_waited")
    lease_acquires = _events_of(events, "task_initialization_lease_acquired")
    lease_releases = _events_of(events, "task_initialization_lease_released")
    tool_invocations = _model_tool_invocations(
        events,
        ("list_tasks", "create_task", "claim_task", "release_task", "complete_task"),
    )
    task_list_dispatches = {
        event.get("event_id")
        for event in _events_of(events, "tool_call")
        if (event.get("payload") or {}).get("tool") == "list_tasks"
        and isinstance((event.get("payload") or {}).get("arguments"), dict)
    }
    task_list_results = [
        event
        for event in _events_of(events, "tool_call")
        if (event.get("payload") or {}).get("tool") == "list_tasks"
        and "count" in (event.get("payload") or {})
        and bool(task_list_dispatches & set(event.get("parent_event_ids") or []))
    ]
    empty_task_list_results = [
        event for event in task_list_results if (event.get("payload") or {}).get("count") == 0
    ]
    first_create_sequence = min((_int(event.get("sequence")) for event in created), default=None)
    empty_before_first_create = [
        event
        for event in empty_task_list_results
        if first_create_sequence is not None and _int(event.get("sequence")) < first_create_sequence
    ]
    created_agents = {str(event.get("agent_id")) for event in created if event.get("agent_id")}
    empty_before_first_create_agents = {
        str(event.get("agent_id"))
        for event in empty_before_first_create
        if event.get("agent_id")
    }
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
        "available": mode == "structured_team",
        "availability_note": "available 表示该 condition 向 Agent 暴露 typed task 工具，不表示发生了任务生命周期活动。",
        "model_tool_invocations": tool_invocations,
        "tool_activity_observed": any(tool_invocations.values()),
        "lifecycle_activity_observed": bool(created or claimed or conflicts or completed or observed),
        "task_list_reads": {
            "invocation_count": tool_invocations["list_tasks"],
            "observed_result_count": len(task_list_results),
            "empty_result_count": sum((event.get("payload") or {}).get("count") == 0 for event in task_list_results),
            "nonempty_result_count": sum(_int((event.get("payload") or {}).get("count")) > 0 for event in task_list_results),
            "first_create_sequence": first_create_sequence,
            "empty_before_first_create_count": len(empty_before_first_create),
            "empty_before_first_create_agents": sorted(empty_before_first_create_agents),
            "all_creators_observed_empty_before_first_create": bool(created_agents)
            and created_agents <= empty_before_first_create_agents,
            "race_note": (
                "这是并发可见性的观测代理：若所有 create_task 的 agent 都在首个 create_task 事件前观察到空 board，"
                "prompt 无法从该观察中排除重叠；它不证明调用在同一时刻发生。"
            ),
            "result_note": "结果计数只关联到对应 model-selected list_tasks dispatch 的工具侧事件，避免把一次调用的双重日志误计为两次调用。",
        },
        "tasks_created": len(created),
        "tasks_claimed": len(claimed),
        "claim_conflicts": {"count": len(conflicts), "events": [event.get("event_id") for event in conflicts]},
        "tasks_released": len(released),
        "tasks_completed": len(completed),
        "unfinished_tasks_at_run_end": unfinished,
        "duplicate_task_descriptions": duplicate_tasks,
        "task_result_observations": {"count": len(observed), "events": [event.get("event_id") for event in observed]},
        "task_result_evidence_adoption": {"count": len(adoptions), "records": adoptions},
        "initialization_lease": {
            "wait_count": len(lease_waits),
            "acquire_count": len(lease_acquires),
            "release_count": len(lease_releases),
            "acquisition_order": [event.get("agent_id") for event in lease_acquires],
            "release_order": [event.get("agent_id") for event in lease_releases],
            "wait_events": [
                {
                    "event_id": event.get("event_id"),
                    "agent_id": event.get("agent_id"),
                    "expected_agent": (event.get("payload") or {}).get("expected_agent"),
                    "owner": (event.get("payload") or {}).get("owner"),
                }
                for event in lease_waits
            ],
            "exact_ordered_hand_off": [event.get("agent_id") for event in lease_acquires]
            == [event.get("agent_id") for event in lease_releases],
            "note": "runtime initialization lease only sequences first board visibility; it does not assign audit scopes or create tasks.",
        },
        "adoption_note": "仅当后续 finding 显式复用 completed task 的 evidence_ref 时计为 adoption；任务被列出或时间相邻不计。",
    }


def _result_sync_metrics(
    events: list[dict[str, Any]], findings: list[dict[str, Any]], agent_ids: list[str],
    transcripts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Classify the traceable visibility → inspection → adoption ladder.

    The runtime makes the raw completed-task snapshot model-visible.  An
    Listing exposes artifacts but does not establish focused inspection. A
    model-visible, evidence-backed selection is required for R2; a subsequent
    read/search is an R3 candidate, not proof of cognitive reliance.
    """
    triggered = _events_of(events, "result_sync_triggered")
    observed = _events_of(events, "result_sync_observed")
    post_sync_opened = _events_of(events, "post_sync_window_opened")
    post_sync_visible = _events_of(events, "post_sync_instruction_model_visible")
    post_sync_admitted = _events_of(events, "post_sync_provider_call_admitted")
    verification_attempted = _events_of(events, "verification_action_attempted")
    verification_visible = _events_of(events, "verification_evidence_model_visible")
    trigger = triggered[0] if triggered else {}
    trigger_payload = trigger.get("payload") or {}
    trigger_sequence = _int(trigger.get("sequence")) if trigger else None
    sync_id = trigger_payload.get("sync_id")
    observations_by_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in observed:
        observations_by_agent[str(event.get("agent_id"))].append(event)

    task_observations = _events_of(events, "task_result_observed")
    tool_calls = _events_of(events, "tool_call")
    file_reads = _events_of(events, "file_read")
    response_by_id = {
        str(record.get("transcript_id")): record
        for record in (transcripts or []) if record.get("kind") == "model_response"
    }
    response_events = [
        (event, response_by_id[reference])
        for event in _events_of(events, "llm_call")
        for reference in (event.get("artifact_refs") or [])
        if reference in response_by_id
    ]
    findings_by_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in findings:
        if finding.get("submitted_by"):
            findings_by_agent[str(finding["submitted_by"])].append(finding)

    per_agent: dict[str, Any] = {}
    outcome_counts: Counter[str] = Counter()
    for agent_id in agent_ids:
        opened_for_agent = [event for event in post_sync_opened if event.get("agent_id") == agent_id]
        visible_for_agent = [event for event in post_sync_visible if event.get("agent_id") == agent_id]
        admitted_for_agent = [event for event in post_sync_admitted if event.get("agent_id") == agent_id]
        verification_for_agent = [event for event in verification_attempted if event.get("agent_id") == agent_id]
        evidence_visible_for_agent = [event for event in verification_visible if event.get("agent_id") == agent_id]
        agent_observations = observations_by_agent.get(agent_id, [])
        first_observation = min(agent_observations, key=lambda item: _int(item.get("sequence")), default=None)
        visible_foreign = sorted({
            task_id
            for event in agent_observations
            for task_id in ((event.get("payload") or {}).get("foreign_completed_task_ids") or [])
        })
        foreign_inspected_events = [
            event
            for event in task_observations
            if event.get("agent_id") == agent_id
            and (event.get("payload") or {}).get("foreign") is True
            and (event.get("payload") or {}).get("observation_phase") == "post_result_sync"
        ]
        listed_task_ids = sorted({(event.get("payload") or {}).get("task_id") for event in foreign_inspected_events})
        foreign_tasks = {
            str(task.get("id")): task
            for observation in agent_observations
            for task in ((observation.get("payload") or {}).get("completed_tasks") or [])
            if task.get("owner") != agent_id and task.get("id") in visible_foreign
        }
        observation_sequence = _int(first_observation.get("sequence")) if first_observation else None
        inspection_events = []
        for event, response in response_events:
            if event.get("agent_id") != agent_id or observation_sequence is None or _int(event.get("sequence")) <= observation_sequence:
                continue
            text = str((response.get("content") or {}).get("content") or "")
            # The inspection record may discuss other foreign tasks while
            # explicitly selecting one. Prefer that labelled selection over
            # the weaker "only task ID mentioned" fallback.
            declared = [match.group(1) for match in _SELECTED_FOREIGN_TASK_RE.finditer(text) if match.group(1) in foreign_tasks]
            selected = sorted(set(declared)) or [
                task_id for task_id in foreign_tasks
                if re.search(r"(?<!\w)" + re.escape(task_id) + r"(?!\w)", text)
            ]
            if len(selected) != 1 or not re.search(r"\b(changes?|strengthens?|contradicts?|irrelevant|relevant|unchanged)\b", text, re.I):
                continue
            refs = [ref for ref in (foreign_tasks[selected[0]].get("evidence_refs") or []) if ref and ref in text]
            if not refs:
                continue
            inspection_events.append((event, response, selected[0], refs))
        inspected_task_ids = sorted({item[2] for item in inspection_events})
        inspected_refs = sorted({ref for item in inspection_events for ref in item[3]})
        first_inspection_sequence = min((_int(item[0].get("sequence")) for item in inspection_events), default=None)
        follow_up_sequences = [
            _int(event.get("sequence")) for event, response, _, _ in inspection_events
            if re.search(r"\b(changes?|strengthens?|contradicts?|relevant)\b", str((response.get("content") or {}).get("content") or ""), re.I)
            and re.search(r"\b(follow|check|verify|read|search|investigate|trace)\b", str((response.get("content") or {}).get("content") or ""), re.I)
        ]
        post_sync_actions = [
            event
            for event in tool_calls
            if event.get("agent_id") == agent_id
            and observation_sequence is not None
            and _int(event.get("sequence")) > observation_sequence
            and (event.get("payload") or {}).get("tool") in {"read_file", "list_files", "run_shell"}
            and "arguments" in (event.get("payload") or {})
        ]
        post_sync_file_reads = [
            event
            for event in file_reads
            if event.get("agent_id") == agent_id
            and observation_sequence is not None
            and _int(event.get("sequence")) > observation_sequence
        ]
        post_inspection_actions = [
            event for event in post_sync_actions + post_sync_file_reads
            if first_inspection_sequence is not None and _int(event.get("sequence")) > first_inspection_sequence
        ]
        foreign_visible_refs = sorted({
            reference
            for event in agent_observations
            for reference in ((event.get("payload") or {}).get("foreign_evidence_refs") or [])
        })
        incorporated_refs = sorted({
            reference
            for finding in findings_by_agent.get(agent_id, [])
            for reference in (finding.get("evidence_refs") or [])
            if reference in foreign_visible_refs
        })
        if not visible_foreign:
            level = "R0"
        elif incorporated_refs:
            level = "R4"
        elif not inspected_task_ids:
            level = "R1"
        elif follow_up_sequences and any(_int(event.get("sequence")) > min(follow_up_sequences) for event in post_inspection_actions):
            level = "R3"
        else:
            level = "R2"
        outcome_counts[level] += 1
        per_agent[agent_id] = {
            "initial_task_completed": bool(
                (trigger_payload.get("initial_claims") or {}).get(agent_id)
                and (trigger_payload.get("initial_claims") or {}).get(agent_id) in {
                    (event.get("payload") or {}).get("task_id") for event in _events_of(events, "task_completed")
                }
            ),
            "foreign_completed_tasks_visible": visible_foreign,
            "foreign_artifacts_listed": listed_task_ids,
            "foreign_artifacts_inspected": inspected_task_ids,
            "foreign_evidence_inspected": inspected_refs,
            "inspection_response_transcript_ids": [item[1].get("transcript_id") for item in inspection_events],
            "post_sync_search_read_actions": [event.get("event_id") for event in post_sync_actions + post_sync_file_reads],
            "post_inspection_search_read_actions": [event.get("event_id") for event in post_inspection_actions],
            "reasoning_changed": None,
            "finding_changed": None,
            "foreign_evidence_incorporated": bool(incorporated_refs),
            "incorporated_foreign_evidence_refs": incorporated_refs,
            "outcome_level": level,
            "sync_observation_event_ids": [event.get("event_id") for event in agent_observations],
            "post_sync_window_opened": bool(opened_for_agent),
            "post_sync_window_event_ids": [event.get("event_id") for event in opened_for_agent],
            "post_sync_instruction_model_visible": bool(visible_for_agent),
            "post_sync_instruction_event_ids": [event.get("event_id") for event in visible_for_agent],
            "post_sync_provider_call_admitted": bool(admitted_for_agent),
            "post_sync_provider_admission_event_ids": [event.get("event_id") for event in admitted_for_agent],
            "verification_action_attempted": bool(verification_for_agent),
            "verification_target": [
                (event.get("payload") or {}).get("verification_target") for event in verification_for_agent
            ],
            "verification_evidence_model_visible": bool(evidence_visible_for_agent),
            "verification_evidence_visibility_event_ids": [event.get("event_id") for event in evidence_visible_for_agent],
            "verification_opportunity_status": (
                "verification_attempted" if verification_for_agent
                else "opportunity_delivered_model_chose_not_to_verify" if admitted_for_agent
                else "no_post_sync_provider_opportunity"
            ),
        }
    return {
        "policy": "result_sync_v1" if triggered or observed else None,
        "measurement_version": "result_inspection_trace_v2_1",
        "triggered": bool(triggered),
        "trigger_event_id": trigger.get("event_id") if trigger else None,
        "trigger_event_sequence": trigger_sequence,
        "sync_id": sync_id,
        "trigger_count": len(triggered),
        "exactly_once": len(triggered) == 1,
        "participating_agents": trigger_payload.get("participating_agents") or agent_ids,
        "completed_initial_task_ids": trigger_payload.get("completed_initial_task_ids") or [],
        "per_agent": per_agent,
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "post_sync_opportunity": {
            "window_opened_count": len(post_sync_opened),
            "instruction_model_visible_count": len(post_sync_visible),
            "provider_call_admitted_count": len(post_sync_admitted),
            "verification_action_attempted_count": len(verification_attempted),
            "verification_evidence_model_visible_count": len(verification_visible),
            "note": "Opportunity provenance is runtime-recorded. Selection, direct relevance, actionable lead, post-verification judgment, and final adoption remain analyzer/manual-adjudication labels.",
        },
        "notes": [
            "result_sync_observed 是 raw completed-task snapshot 进入该 agent model-visible context 的 lineage 事件。",
            "list_tasks 仅证明列出；R2 要求同步后的 model_response 明确选出一个 foreign task、其 evidence_ref 和 relevance 判断。选择以 labelled Selected foreign task 字段为准，允许其后讨论其他未采用 artifact；未显式留下检查记录的行为仍为 R1/未证实。",
            "reasoning_changed 无法从不保存 hidden chain-of-thought 的 trace 直接判断；R3 要求明确检查、正向 relevance/跟进表述，以及之后的 read/search，但仍需人工确认行动与 foreign lead 有关；R4 要求 foreign evidence_ref 进入 final finding。",
            "finding_changed 不能从最终存在 finding 推断；没有可靠的 pre/post finding revision lineage 时保持 null。",
            "R4 是 evidence reuse 观察，不是 security effectiveness 或 TP 提升结论。",
            "verification_opportunity_status 区分 runtime 未交付 post-sync provider opportunity 与已交付而未观察到 verification action；它不从未行动推断模型动机。",
        ],
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
        "blackboard": {key: (metrics.get("blackboard") or {}).get(key) for key in ("available", "tool_activity_observed", "model_tool_invocations", "write_count", "read_count", "cross_agent_read_count", "first_write_latency_seconds", "first_read_latency_seconds")},
        "structured_team": {key: (metrics.get("structured_team") or {}).get(key) for key in ("available", "tool_activity_observed", "lifecycle_activity_observed", "model_tool_invocations", "task_list_reads", "tasks_created", "tasks_claimed", "tasks_completed", "claim_conflicts", "task_result_evidence_adoption")},
        "result_sync": {
            "triggered": (metrics.get("result_sync") or {}).get("triggered"),
            "exactly_once": (metrics.get("result_sync") or {}).get("exactly_once"),
            "outcome_counts": (metrics.get("result_sync") or {}).get("outcome_counts"),
        },
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
