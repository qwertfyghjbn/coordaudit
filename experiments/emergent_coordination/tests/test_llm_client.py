from __future__ import annotations

import sys
import types
import unittest
from types import SimpleNamespace
from unittest import mock

from experiments.emergent_coordination.harness.llm.client import OpenAICompatibleClient


class _FakeCompletions:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        message = SimpleNamespace(
            content="probe complete",
            tool_calls=[
                SimpleNamespace(
                    id="call_001",
                    function=SimpleNamespace(name="compatibility_echo", arguments='{"value":"coord-audit"}'),
                )
            ],
        )
        usage = SimpleNamespace(
            prompt_tokens=11,
            completion_tokens=7,
            prompt_tokens_details=SimpleNamespace(cached_tokens=2),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=None),
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)],
            usage=usage,
            model="deepseek-flash-resolved",
            system_fingerprint="fp_test",
            id="chat_test",
            model_dump=lambda: {"id": "chat_test"},
        )


class _FakeOpenAI:
    latest = None

    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        self.completions = _FakeCompletions()
        self.chat = SimpleNamespace(completions=self.completions)
        type(self).latest = self


class OpenAICompatibleClientTest(unittest.TestCase):
    def test_records_resolved_model_and_sends_non_thinking_tool_request(self):
        with mock.patch.dict(sys.modules, {"openai": types.SimpleNamespace(OpenAI=_FakeOpenAI)}):
            client = OpenAICompatibleClient(
                api_key="test-key",
                base_url="https://provider.example",
                model="deepseek-flash",
                thinking_mode="disabled",
                max_tokens=64,
            )
            response = client.complete(
                [{"role": "user", "content": "probe"}],
                [{"type": "function", "function": {"name": "compatibility_echo"}}],
                agent_id="test",
                tool_choice={"type": "function", "function": {"name": "compatibility_echo"}},
            )

        self.assertEqual(_FakeOpenAI.latest.init_kwargs["max_retries"], 0)
        request = _FakeOpenAI.latest.completions.kwargs
        self.assertEqual(request["extra_body"], {"thinking": {"type": "disabled"}})
        self.assertEqual(request["tool_choice"]["function"]["name"], "compatibility_echo")
        self.assertEqual(response.usage.model, "deepseek-flash-resolved")
        self.assertEqual(response.model_metadata["requested_model"], "deepseek-flash")
        self.assertEqual(response.model_metadata["resolved_model"], "deepseek-flash-resolved")
        self.assertEqual(response.model_metadata["system_fingerprint"], "fp_test")


if __name__ == "__main__":
    unittest.main()
