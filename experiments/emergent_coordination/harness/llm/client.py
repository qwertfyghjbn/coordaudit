from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

from experiments.emergent_coordination.harness.budget import TokenUsage


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[dict[str, Any]]
    usage: TokenUsage
    raw: dict[str, Any]
    model_metadata: dict[str, Any] = field(default_factory=dict)


class LLMClient(Protocol):
    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        agent_id: str,
        tool_choice: dict[str, Any] | str | None = None,
    ) -> LLMResponse:
        ...


class MockLLMClient:
    """Scripted client for unit/mock tests. Never calls a network API."""

    def __init__(self, scripts: dict[str, list[LLMResponse]] | None = None, default: list[LLMResponse] | None = None):
        self.scripts = scripts or {}
        self.default = default or []
        self.calls: dict[str, int] = {}

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        agent_id: str,
        tool_choice: dict[str, Any] | str | None = None,
    ) -> LLMResponse:
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
        max_tokens: int = 1024,
        timeout_seconds: float = 60.0,
        thinking_mode: str = "disabled",
    ):
        from openai import OpenAI

        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        if thinking_mode not in {"enabled", "disabled"}:
            raise ValueError("thinking_mode must be 'enabled' or 'disabled'")
        self.thinking_mode = thinking_mode
        # SDK retries would make extra provider attempts invisible to the
        # harness permit ledger. Retries, if added later, must re-enter the
        # AgentRunner and obtain a distinct permit.
        self.client = OpenAI(api_key=api_key, base_url=base_url, max_retries=0, timeout=timeout_seconds)

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        agent_id: str,
        tool_choice: dict[str, Any] | str | None = None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "extra_body": {"thinking": {"type": self.thinking_mode}},
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
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
            model=getattr(response, "model", None) or self.model,
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
            model_metadata={
                "requested_model": self.model,
                "resolved_model": getattr(response, "model", None),
                "system_fingerprint": getattr(response, "system_fingerprint", None),
                "provider_response_id": getattr(response, "id", None),
                "thinking_mode": self.thinking_mode,
            },
        )


def _maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def client_from_env(
    *,
    model: str | None = None,
    thinking_mode: str | None = None,
    max_tokens: int = 1024,
) -> OpenAICompatibleClient | None:
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAICompatibleClient(
        api_key=api_key,
        base_url=os.environ.get("LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL"),
        model=model or os.environ.get("LLM_MODEL") or os.environ.get("OPENAI_MODEL") or "unknown",
        thinking_mode=thinking_mode or os.environ.get("LLM_THINKING_MODE") or "disabled",
        max_tokens=max_tokens,
    )
