from __future__ import annotations

import unittest

from experiments.emergent_coordination.harness.call_role import classify_call_role


class CallRoleTest(unittest.TestCase):
    def test_plain_reads_and_shell_are_exploration(self):
        self.assertEqual(classify_call_role(["read_file", "run_shell"], finalization_active=False), "exploration")
        self.assertEqual(classify_call_role([], finalization_active=False), "exploration")

    def test_coordination_tools_outrank_exploration(self):
        self.assertEqual(classify_call_role(["read_file", "claim_task"], finalization_active=False), "coordination")
        self.assertEqual(classify_call_role(["shared_create"], finalization_active=False), "coordination")

    def test_submission_outranks_everything_including_finalization(self):
        self.assertEqual(classify_call_role(["submit_findings"], finalization_active=True), "submission")
        self.assertEqual(
            classify_call_role(["submit_findings", "read_file", "claim_task"], finalization_active=True),
            "submission",
        )
        self.assertEqual(classify_call_role(["submit_findings"], finalization_active=False), "submission")

    def test_finalization_window_without_submit_is_finalization(self):
        self.assertEqual(classify_call_role(["read_file"], finalization_active=True), "finalization")
        self.assertEqual(classify_call_role([], finalization_active=True), "finalization")

    def test_finalization_does_not_leak_into_normal_calls(self):
        self.assertEqual(classify_call_role(["read_file"], finalization_active=False), "exploration")


if __name__ == "__main__":
    unittest.main()
