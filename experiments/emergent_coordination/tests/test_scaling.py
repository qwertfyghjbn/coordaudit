from __future__ import annotations

import unittest

from experiments.emergent_coordination.harness.paths import agent_id_for
from experiments.emergent_coordination.harness.policies.base import get_policy


class ScalingTest(unittest.TestCase):
    def test_agent_ids_extend_to_32_without_renaming(self):
        self.assertEqual(agent_id_for(1), "agent_001")
        self.assertEqual(agent_id_for(16), "agent_016")
        self.assertEqual(agent_id_for(32), "agent_032")

    def test_all_pilot_modes_are_registered(self):
        for mode in ("single", "parallel", "raw_blackboard", "structured_team"):
            policy = get_policy(mode)
            self.assertEqual(policy.name, mode)
