from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol

from experiments.emergent_coordination.harness.budget import TokenUsage


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[dict[str, Any]]
    usage: TokenUsage
    raw: dict[str, Any]


class LLMClient(Protocol):
    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        agent_id: str,
    ) -> LLMResponse:
        ...


class MockLLMClient:
    """Scripted client for unit/mock tests. Never calls a network API."""

    def __init__(self, scripts: dict[str, list[LLMResponse]] | None = None, default: list[LLMResponse] | None = None):
        self.scripts = scripts or {}
        self.default = default or []
        self.calls: dict[str, int] = {}

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], *, agent_id: str) -> LLMResponse:
        index = self.calls.get(agent_id, 0)
        self.calls[agent_id] = index + 1
        sequence = self.scripts.get(agent_id, self.default)
        if index >= len(sequence):
            return LLMResponse(
                content=json.dumps({"findings": []}),
                tool_calls=[],
                usage=TokenUsage(input_tokens=1, output_tokens=1, model="mock"),
                raw={"mock": True, "exhausted": True},
            )
        return sequence[index]


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ):
        from openai import OpenAI

        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], *, agent_id: str) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
        response = self.client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        usage = getattr(response, "usage", None)
        details = getattr(usage, "completion_tokens_details", None) if usage else None
        prompt_details = getattr(usage, "prompt_tokens_details", None) if usage else None
        token_usage = TokenUsage(
            input_tokens=_maybe_int(getattr(usage, "prompt_tokens", None)),
            cached_input_tokens=_maybe_int(getattr(prompt_details, "cached_tokens", None) if prompt_details else None),
            output_tokens=_maybe_int(getattr(usage, "completion_tokens", None)),
            reasoning_tokens=_maybe_int(getattr(details, "reasoning_tokens", None) if details else None),
            model=self.model,
        )
        tool_calls = []
        for call in message.tool_calls or []:
            tool_calls.append(
                {
                    "id": call.id,
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                }
            )
        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            usage=token_usage,
            raw=response.model_dump() if hasattr(response, "model_dump") else {},
        )


def _maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def client_from_env() -> OpenAICompatibleClient | None:
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAICompatibleClient(
        api_key=api_key,
        base_url=os.environ.get("LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL"),
        model=os.environ.get("LLM_MODEL") or os.environ.get("OPENAI_MODEL") or "unknown",
    )
