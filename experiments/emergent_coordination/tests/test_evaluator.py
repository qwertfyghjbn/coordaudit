from __future__ import annotations

import unittest

from experiments.emergent_coordination.evaluator.score import evaluate_findings, load_ground_truth
from experiments.emergent_coordination.harness.paths import GROUND_TRUTH_PATH


class EvaluatorTest(unittest.TestCase):
    def setUp(self):
        self.gt = load_ground_truth(GROUND_TRUTH_PATH)

    def test_perfect_positive_set(self):
        findings = [
            {
                "title": "Workspace files can be read outside the storage root",
                "category": "path_traversal",
                "files": ["app/common/storage.py"],
                "functions": ["read_file"],
                "source": "app/routes/files.py download filename query",
                "sink": "open(file_path) after os.path.join",
            },
            {
                "title": "Integration fetch sends attacker URLs outbound",
                "category": "server-side request forgery",
                "files": ["app/common/http_client.py"],
                "functions": ["get_url"],
                "sink": "requests.get(url)",
            },
            {
                "title": "Report title is compiled as a template",
                "category": "template injection",
                "files": ["app/common/templates.py"],
                "functions": ["render_report_template"],
                "sink": "Environment.from_string(template_str)",
            },
        ]
        result = evaluate_findings(findings, self.gt)
        self.assertEqual(result["TP"], 3)
        self.assertEqual(result["FP"], 0)
        self.assertEqual(result["FN"], 0)
        self.assertEqual(result["precision"], 1.0)
        self.assertEqual(result["recall"], 1.0)
        self.assertFalse(result["semantic_judge_used"])

    def test_near_miss_is_false_positive_not_required_hit(self):
        findings = [
            {
                "title": "Document download looks like a file read issue",
                "category": "path_traversal",
                "files": ["app/services/document_service.py", "app/common/io.py"],
                "functions": ["_resolve_safe_path", "read_file"],
            }
        ]
        result = evaluate_findings(findings, self.gt)
        self.assertEqual(result["TP"], 0)
        self.assertEqual(result["FN"], 3)
        self.assertEqual(result["near_miss_false_positives"], 1)
        self.assertEqual(result["FP"], 1)

    def test_duplicate_positive_is_counted(self):
        finding = {
            "title": "join open",
            "category": "path_traversal",
            "files": ["app/common/storage.py"],
            "functions": ["read_file"],
            "sink": "open(",
        }
        result = evaluate_findings([finding, dict(finding)], self.gt)
        self.assertEqual(result["TP"], 1)
        self.assertEqual(result["duplicate_findings"], 1)

    def test_unrelated_finding_is_fp(self):
        findings = [{"title": "debug mode", "category": "misconfiguration", "files": ["app/main.py"]}]
        result = evaluate_findings(findings, self.gt)
        self.assertEqual(result["TP"], 0)
        self.assertEqual(result["FP"], 1)
        self.assertEqual(result["FN"], 3)


if __name__ == "__main__":
    unittest.main()
