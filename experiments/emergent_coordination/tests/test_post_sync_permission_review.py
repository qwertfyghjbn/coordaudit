from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.post_sync_permission_review import review_template, summarize_review


class PostSyncPermissionReviewTest(unittest.TestCase):
    def test_conditional_denominators_keep_actionable_leads_as_action_denominator(self):
        agents = []
        for index in range(12):
            lead = index < 3
            agents.append({
                "agent_id": f"agent_{index:03d}",
                "observed": {
                    "inspected_task_ids": ["foreign"],
                    "inspection_transcript_ids": [f"trn_{index}"],
                    "post_inspection_action_event_ids": [],
                },
                "review": {
                    "direct_relation": lead,
                    "actionable_lead": lead,
                    "verification_target": "target/path.ts" if lead else None,
                    "discriminating_observation": "guard is reachable" if lead else None,
                    "target_aligned_verification": False,
                    "verification_action_event_ids": [],
                    "judgment_update": False,
                    "judgment_transcript_id": None,
                    "final_adoption": False,
                    "final_finding_ref": None,
                },
            })
        summary = summarize_review({"run_id": "control", "agents": agents})
        self.assertEqual(summary["transitions"]["inspection_to_relevance"]["denominator"], 12)
        self.assertEqual(summary["transitions"]["relevance_to_lead"]["denominator"], 3)
        self.assertEqual(summary["transitions"]["lead_to_verification"], {
            "numerator": 0, "denominator": 3, "ratio": 0.0,
        })
        self.assertIsNone(summary["transitions"]["verification_to_update"]["ratio"])

        agents[0]["observed"]["post_inspection_action_event_ids"] = ["evt_read"]
        agents[0]["review"].update({
            "target_aligned_verification": True,
            "verification_action_event_ids": ["evt_read"],
            "judgment_update": True,
            "judgment_transcript_id": "trn_post_read",
            "final_adoption": True,
            "final_finding_ref": "finding_1",
        })
        summary = summarize_review({"run_id": "treatment", "agents": agents})
        self.assertEqual(summary["transitions"]["lead_to_verification"]["numerator"], 1)
        self.assertEqual(summary["transitions"]["lead_to_verification"]["denominator"], 3)
        self.assertEqual(summary["transitions"]["verification_to_update"]["denominator"], 1)
        self.assertEqual(summary["transitions"]["update_to_adoption"]["numerator"], 1)

    def test_requires_manual_adjudication_and_observed_action_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "metrics.json").write_text(json.dumps({"result_sync": {
                "exactly_once": True,
                "per_agent": {"agent_001": {
                    "foreign_artifacts_inspected": ["foreign"],
                    "inspection_response_transcript_ids": ["trn_1"],
                    "post_inspection_search_read_actions": ["evt_read"],
                    "foreign_evidence_inspected": ["evt_foreign_ref"],
                }},
            }}), encoding="utf-8")
            template = review_template(directory)
            row = template["agents"][0]
            self.assertEqual(row["observed"]["post_inspection_action_event_ids"], ["evt_read"])
            self.assertNotIn("evt_foreign_ref", json.dumps(row["observed"]))
            with self.assertRaisesRegex(ValueError, "unresolved"):
                summarize_review(template)
            row["review"].update({
                "direct_relation": True,
                "actionable_lead": True,
                "verification_target": "target/path.ts",
                "discriminating_observation": "guard reachable",
                "target_aligned_verification": True,
                "verification_action_event_ids": ["evt_fabricated"],
                "judgment_update": False,
                "final_adoption": False,
            })
            with self.assertRaisesRegex(ValueError, "observed event IDs"):
                summarize_review(template)


if __name__ == "__main__":
    unittest.main()
