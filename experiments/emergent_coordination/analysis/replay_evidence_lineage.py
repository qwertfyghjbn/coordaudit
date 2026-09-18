"""Replay finding-to-file-read lineage without provider or private evaluator access."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.emergent_coordination.harness.paths import normalize_target_relative_path


SCHEMA_VERSION = 1


def replay_evidence_lineage(run_dir: Path, *, write: bool = True) -> dict[str, Any]:
    run_dir = Path(run_dir)
    transcript_dir = run_dir / "logs" / "transcripts"
    transcript_paths = sorted(transcript_dir.glob("*.jsonl"))
    if not transcript_paths:
        raise ValueError(f"no model-visible transcripts found under {transcript_dir}")

    agents: dict[str, Any] = {}
    classifications: Counter[str] = Counter()
    submission_count = 0
    finding_count = 0

    for transcript_path in transcript_paths:
        records = _read_jsonl(transcript_path)
        agent_id = str(records[0].get("agent_id") if records else transcript_path.stem)
        replay = _replay_agent(records)
        agents[agent_id] = replay
        submission_count += len(replay["submissions"])
        for submission in replay["submissions"]:
            for finding in submission["findings"]:
                finding_count += 1
                classifications[finding["classification"]] += 1

    result = {
        "schema_version": SCHEMA_VERSION,
        "run_dir": str(run_dir),
        "analysis_plane": "model_visible_transcript_only",
        "summary": {
            "agent_count": len(agents),
            "submission_count": submission_count,
            "finding_instance_count": finding_count,
            "classifications": dict(sorted(classifications.items())),
        },
        "agents": agents,
        "interpretation": {
            "historical_namespace_prefix_rejection": (
                "The recorded runtime rejected cited source/sink evidence even though the current common target-relative "
                "rule matches the same files; this identifies the pre-fix asymmetric comparison."
            ),
            "source_sink_evidence_mismatch": (
                "No reported source/sink file matches the cited file_read paths even after common normalization."
            ),
            "validator_match": "The current validator namespace comparison finds a cited source or sink file.",
        },
        "hidden_evaluator_used": False,
        "provider_calls": 0,
    }
    if write:
        (run_dir / "evidence_lineage_replay.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return result


def _replay_agent(records: list[dict[str, Any]]) -> dict[str, Any]:
    tool_results = {
        (record.get("content") or {}).get("tool_call_id"): _tool_result_payload(record)
        for record in records
        if record.get("kind") == "tool_result"
    }
    evidence: dict[str, str] = {}
    submissions: list[dict[str, Any]] = []

    for record in sorted(records, key=lambda item: int(item.get("sequence") or 0)):
        if record.get("kind") != "model_response":
            continue
        content = record.get("content") or {}
        step = int(content.get("step") or 0)
        for call in content.get("tool_calls") or []:
            name = call.get("name")
            result = tool_results.get(call.get("id"))
            if name == "read_file" and isinstance(result, dict):
                ref = result.get("evidence_ref")
                path = result.get("path")
                if ref and path:
                    evidence[str(ref)] = str(path)
            elif name == "submit_findings":
                submissions.append(_replay_submission(step, call, result, evidence))

    return {
        "evidence_ref_count": len(evidence),
        "evidence": [
            {"evidence_ref": ref, "observed_path": path, "validator_path": _evidence_path(path)}
            for ref, path in evidence.items()
        ],
        "submissions": submissions,
    }


def _replay_submission(
    step: int,
    call: dict[str, Any],
    result: Any,
    evidence: dict[str, str],
) -> dict[str, Any]:
    raw_arguments = str(call.get("arguments") or "{}")
    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        return {
            "step": step,
            "tool_call_id": call.get("id"),
            "arguments_valid": False,
            "parse_error": {"line": exc.lineno, "column": exc.colno},
            "tool_result": _result_status(result),
            "findings": [],
        }
    if not isinstance(arguments, dict):
        return {
            "step": step,
            "tool_call_id": call.get("id"),
            "arguments_valid": False,
            "parse_error": {"reason": "arguments_not_object"},
            "tool_result": _result_status(result),
            "findings": [],
        }

    findings = []
    for index, finding in enumerate(arguments.get("findings") or []):
        findings.append(_finding_lineage(index, finding, evidence, tool_result=_result_status(result)))
    return {
        "step": step,
        "tool_call_id": call.get("id"),
        "arguments_valid": True,
        "tool_result": _result_status(result),
        "findings": findings,
    }


def _finding_lineage(
    index: int,
    finding: Any,
    evidence: dict[str, str],
    *,
    tool_result: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(finding, dict):
        return {"index": index, "classification": "invalid_finding_shape"}
    source_file = str((finding.get("source") or {}).get("file") or "")
    sink_file = str((finding.get("sink") or {}).get("file") or "")
    refs = [str(ref) for ref in finding.get("evidence_refs") or []]
    missing_refs = [ref for ref in refs if ref not in evidence]
    cited_paths = [evidence[ref] for ref in refs if ref in evidence]
    raw_anchor_paths = {source_file, sink_file}
    validator_evidence_paths = {_evidence_path(path) for path in cited_paths}
    validator_anchor_paths = {_target_relative(source_file), _target_relative(sink_file)}
    validator_matches = sorted(validator_anchor_paths & validator_evidence_paths)

    if missing_refs:
        classification = "unknown_evidence_ref"
    elif validator_matches:
        if tool_result["ok"] is False and any(
            message == "must include a file_read of the reported source or sink file"
            for message in tool_result["error_messages"]
        ):
            classification = "historical_namespace_prefix_rejection"
        else:
            classification = "validator_match"
    else:
        classification = "source_sink_evidence_mismatch"

    return {
        "index": index,
        "category": finding.get("category"),
        "source_file": source_file,
        "sink_file": sink_file,
        "evidence_refs": refs,
        "cited_paths": cited_paths,
        "missing_refs": missing_refs,
        "raw_anchor_paths": sorted(raw_anchor_paths),
        "validator_anchor_paths": sorted(validator_anchor_paths),
        "validator_evidence_paths": sorted(validator_evidence_paths),
        "validator_matches": validator_matches,
        "classification": classification,
    }


def _result_status(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"ok": None}
    errors = result.get("errors") or []
    return {
        "ok": result.get("ok"),
        "count": result.get("count"),
        "error_paths": [error.get("path") for error in errors if isinstance(error, dict)],
        "error_messages": [error.get("message") for error in errors if isinstance(error, dict)],
    }


def _tool_result_payload(record: dict[str, Any]) -> Any:
    raw = (record.get("content") or {}).get("content")
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _evidence_path(path: str) -> str:
    """Mirror the current runtime validator's evidence-side normalization."""
    return normalize_target_relative_path(path)


def _target_relative(path: str) -> str:
    """Mirror the current runtime's common target-relative comparison rule."""
    return normalize_target_relative_path(path)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="离线重放 finding source/sink 与 file_read evidence lineage。")
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    result = replay_evidence_lineage(args.run_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
