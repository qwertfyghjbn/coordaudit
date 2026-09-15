from __future__ import annotations

import unittest

from experiments.emergent_coordination.harness.prompts import system_prompt, user_prompt
from experiments.emergent_coordination.harness.tools.specs import tools_for_mode


class PromptPolicyTest(unittest.TestCase):
    def test_blackboard_prompt_does_not_induce_organization(self):
        text = system_prompt("raw_blackboard", "agent_001") + user_prompt("raw_blackboard", "agent_001", 2)
        forbidden = [
            "you are a team",
            "please cooperate",
            "divide the work",
            "mailbox",
            "claim a task",
            "elect a leader",
            "look at other agents",
        ]
        lowered = text.lower()
        for phrase in forbidden:
            self.assertNotIn(phrase, lowered)
        self.assertIn("/shared is a persistent directory", text)

    def test_tool_sets_differ_by_mode(self):
        names = lambda mode: {item["function"]["name"] for item in tools_for_mode(mode)}
        self.assertNotIn("shared_create", names("single"))
        self.assertNotIn("shared_create", names("parallel"))
        self.assertIn("shared_create", names("raw_blackboard"))
        self.assertNotIn("claim_task", names("raw_blackboard"))
        self.assertIn("claim_task", names("structured_team"))
        self.assertNotIn("list_agents", names("raw_blackboard"))


if __name__ == "__main__":
    unittest.main()
