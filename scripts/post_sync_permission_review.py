"""Manual-review template and conditional transition counts for the T4 permission study.

This reads only the analysis-plane metrics. Direct relevance, action alignment,
and judgment changes require human review of model-visible transcripts; an
evidence_ref listed in a task is never treated as a file-body read.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


STAGES = (
    ("inspection_to_relevance", "inspected", "direct_relation"),
    ("relevance_to_lead", "direct_relation", "actionable_lead"),
    ("lead_to_verification", "actionable_lead", "target_aligned_verification"),
    ("verification_to_update", "target_aligned_verification", "judgment_update"),
    ("update_to_adoption", "judgment_update", "final_adoption"),
)
MANUAL_FIELDS = ("direct_relation", "actionable_lead", "target_aligned_verification", "judgment_update", "final_adoption")


def review_template(run_dir: Path) -> dict[str, Any]:
    """Prepare one unresolved, provenance-carrying row per synchronized agent."""
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    sync = metrics.get("result_sync") or {}
    if not sync.get("exactly_once"):
        raise ValueError("RESULT_SYNC must have triggered exactly once")
    rows = []
    for agent_id, data in sorted((sync.get("per_agent") or {}).items()):
        rows.append({
            "agent_id": agent_id,
            "observed": {
                "inspected_task_ids": data.get("foreign_artifacts_inspected") or [],
                "inspection_transcript_ids": data.get("inspection_response_transcript_ids") or [],
                "post_inspection_action_event_ids": data.get("post_inspection_search_read_actions") or [],
                "foreign_evidence_refs_in_final": data.get("incorporated_foreign_evidence_refs") or [],
                "r_level": data.get("outcome_level"),
            },
            "review": {
                "direct_relation": None,
                "actionable_lead": None,
                "verification_target": None,
                "discriminating_observation": None,
                "target_aligned_verification": None,
                "verification_action_event_ids": [],
                "judgment_update": None,
                "judgment_transcript_id": None,
                "final_adoption": None,
                "final_finding_ref": None,
            },
        })
    return {"schema_version": 1, "run_id": run_dir.name, "agents": rows}


def summarize_review(review: dict[str, Any]) -> dict[str, Any]:
    """Count conditional transitions only after each agent has been reviewed."""
    rows = review.get("agents")
    if not isinstance(rows, list) or not rows:
        raise ValueError("review requires nonempty agents")
    flags: list[dict[str, bool]] = []
    seen: set[str] = set()
    for row in rows:
        agent_id = row.get("agent_id")
        if not isinstance(agent_id, str) or agent_id in seen:
            raise ValueError("agent IDs must be nonempty and unique")
        seen.add(agent_id)
        observed, manual = row.get("observed") or {}, row.get("review") or {}
        inspected = bool(observed.get("inspected_task_ids") and observed.get("inspection_transcript_ids"))
        for field in MANUAL_FIELDS:
            if type(manual.get(field)) is not bool:
                raise ValueError(f"{agent_id}: unresolved or non-boolean {field}")
        direct, lead = manual["direct_relation"], manual["actionable_lead"]
        verified, updated, adopted = (
            manual["target_aligned_verification"], manual["judgment_update"], manual["final_adoption"]
        )
        if direct and not inspected:
            raise ValueError(f"{agent_id}: direct relation requires an inspection record")
        if lead and (not direct or not manual.get("verification_target") or not manual.get("discriminating_observation")):
            raise ValueError(f"{agent_id}: actionable lead requires direct relation, target and discriminant")
        action_ids = manual.get("verification_action_event_ids") or []
        if verified:
            candidates = set(observed.get("post_inspection_action_event_ids") or [])
            if not lead or not action_ids or not set(action_ids).issubset(candidates):
                raise ValueError(f"{agent_id}: verified action needs an actionable lead and observed event IDs")
        if updated and (not verified or not manual.get("judgment_transcript_id")):
            raise ValueError(f"{agent_id}: judgment update needs verified action and transcript provenance")
        if adopted and not manual.get("final_finding_ref"):
            raise ValueError(f"{agent_id}: final adoption needs a finding reference")
        flags.append({
            "inspected": inspected,
            "direct_relation": direct,
            "actionable_lead": lead,
            "target_aligned_verification": verified,
            "judgment_update": updated,
            "final_adoption": adopted,
        })

    transitions = {}
    for name, source, destination in STAGES:
        denominator = sum(row[source] for row in flags)
        numerator = sum(row[source] and row[destination] for row in flags)
        transitions[name] = {
            "numerator": numerator,
            "denominator": denominator,
            "ratio": numerator / denominator if denominator else None,
        }
    return {
        "schema_version": 1,
        "run_id": review.get("run_id"),
        "agent_count": len(flags),
        "transitions": transitions,
        "final_adoption_total": sum(row["final_adoption"] for row in flags),
        "notes": "Transitions after inspection require manual target/provenance review; ratios with zero denominators are null.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--template", type=Path, metavar="RUN_DIR")
    group.add_argument("--summarize", type=Path, metavar="REVIEW_JSON")
    args = parser.parse_args()
    result = (
        review_template(args.template)
        if args.template is not None
        else summarize_review(json.loads(args.summarize.read_text(encoding="utf-8")))
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
