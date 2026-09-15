from __future__ import annotations

import re
import unittest
from pathlib import Path

from experiments.emergent_coordination.harness.paths import TARGET_ROOT

LEAK_PATTERNS = [
    r"PT-PY",
    r"SSRF-PY",
    r"SSTI-PY",
    r"\bCVE\b",
    r"\bVULN\b",
    r"\bFIXED\b",
    r"ground_truth",
    r"PT-PY-REPO-001",
    r"PT-PY-REPO-002",
    r"SSRF-PY-REPO-001",
    r"SSRF-PY-REPO-002",
    r"SSTI-PY-REPO-001",
    r"near_miss",
    r"should_not_report",
    r"recall_anchor",
]

SOFT_LEAK_PATTERNS = [
    r"\bSSRF\b",
    r"\bSSTI\b",
    r"path traversal",
    r"template injection",
]


class LeakTest(unittest.TestCase):
    def test_no_benchmark_metadata_in_target(self):
        hits = []
        for path in TARGET_ROOT.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix in {".pyc"} or path.name == "__pycache__":
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern in LEAK_PATTERNS:
                if re.search(pattern, text, flags=re.IGNORECASE):
                    hits.append(f"{path.relative_to(TARGET_ROOT)}: {pattern}")
        self.assertEqual(hits, [], "benchmark metadata leaked into agent-visible target")

    def test_no_vulnerability_type_labels_in_target(self):
        hits = []
        for path in TARGET_ROOT.rglob("*"):
            if not path.is_file() or path.suffix in {".pyc"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern in SOFT_LEAK_PATTERNS:
                if re.search(pattern, text, flags=re.IGNORECASE):
                    hits.append(f"{path.relative_to(TARGET_ROOT)}: {pattern}")
        self.assertEqual(hits, [], "vulnerability-type labels leaked into agent-visible target")

    def test_forbidden_filenames_absent(self):
        names = {path.name for path in TARGET_ROOT.rglob("*") if path.is_file()}
        self.assertNotIn("ground_truth.json", names)
        self.assertNotIn("case.yaml", names)
        self.assertNotIn("provenance.json", names)


if __name__ == "__main__":
    unittest.main()
