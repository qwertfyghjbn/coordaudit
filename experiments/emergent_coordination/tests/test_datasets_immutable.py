from __future__ import annotations

import json
import unittest

from experiments.emergent_coordination.harness.paths import PROVENANCE_PATH

SOURCE_CASES = [
    "PT-PY-REPO-001",
    "PT-PY-REPO-002",
    "SSRF-PY-REPO-001",
    "SSRF-PY-REPO-002",
    "SSTI-PY-REPO-001",
]


class DatasetsImmutableTest(unittest.TestCase):
    def test_provenance_freezes_source_ground_truth_hashes(self):
        payload = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
        source_repository = payload["source_repository"]
        self.assertEqual(source_repository["remote"], "https://github.com/qwertfyghjbn/vuln-audit-system-eval")
        self.assertRegex(source_repository["commit"], r"^[0-9a-f]{40}$")
        hashes = source_repository["source_ground_truth_sha256"]
        self.assertEqual(set(hashes), set(SOURCE_CASES))
        for digest in hashes.values():
            self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_provenance_points_at_the_five_requested_cases(self):
        payload = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
        derived = [item["source_case"] for item in payload["derived_from"]]
        self.assertEqual(set(derived), set(SOURCE_CASES))
        self.assertEqual(len(derived), 5)
