from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


class BudgetExhausted(Exception):
    def __init__(self, reason: str, snapshot: dict[str, Any]):
        super().__init__(reason)
        self.reason = reason
        self.snapshot = snapshot


@dataclass
class TokenUsage:
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    model: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "model": self.model,
        }


def _as_int(value: int | None) -> int:
    return 0 if value is None else int(value)


@dataclass
class BudgetTracker:
    global_input_token_cap: int | None = None
    global_output_token_cap: int | None = None
    per_agent_token_cap: int | None = None
    max_llm_calls: int | None = None
    wall_clock_timeout: float | None = None
    global_input_tokens: int = 0
    global_output_tokens: int = 0
    global_cached_input_tokens: int = 0
    global_reasoning_tokens: int = 0
    llm_calls: int = 0
    per_agent: dict[str, dict[str, int]] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def _agent_bucket(self, agent_id: str) -> dict[str, int]:
        bucket = self.per_agent.setdefault(
            agent_id,
            {
                "input_tokens": 0,
                "output_tokens": 0,
                "cached_input_tokens": 0,
                "reasoning_tokens": 0,
                "llm_calls": 0,
            },
        )
        return bucket

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "global_input_tokens": self.global_input_tokens,
                "global_output_tokens": self.global_output_tokens,
                "global_cached_input_tokens": self.global_cached_input_tokens,
                "global_reasoning_tokens": self.global_reasoning_tokens,
                "llm_calls": self.llm_calls,
                "per_agent": {key: dict(value) for key, value in self.per_agent.items()},
                "caps": {
                    "global_input_token_cap": self.global_input_token_cap,
                    "global_output_token_cap": self.global_output_token_cap,
                    "per_agent_token_cap": self.per_agent_token_cap,
                    "max_llm_calls": self.max_llm_calls,
                    "wall_clock_timeout": self.wall_clock_timeout,
                },
            }

    def check_wall_clock(self, elapsed_seconds: float) -> None:
        if self.wall_clock_timeout is None:
            return
        if elapsed_seconds > self.wall_clock_timeout:
            raise BudgetExhausted(
                "wall_clock_timeout",
                {**self.snapshot(), "elapsed_seconds": elapsed_seconds},
            )

    def charge(self, agent_id: str, usage: TokenUsage) -> None:
        with self._lock:
            if self.max_llm_calls is not None and self.llm_calls + 1 > self.max_llm_calls:
                raise BudgetExhausted("max_llm_calls", self.snapshot())

            input_tokens = _as_int(usage.input_tokens)
            output_tokens = _as_int(usage.output_tokens)
            cached = _as_int(usage.cached_input_tokens)
            reasoning = _as_int(usage.reasoning_tokens)

            if (
                self.global_input_token_cap is not None
                and self.global_input_tokens + input_tokens > self.global_input_token_cap
            ):
                raise BudgetExhausted("global_input_token_cap", self.snapshot())
            if (
                self.global_output_token_cap is not None
                and self.global_output_tokens + output_tokens > self.global_output_token_cap
            ):
                raise BudgetExhausted("global_output_token_cap", self.snapshot())

            bucket = self._agent_bucket(agent_id)
            agent_total = (
                bucket["input_tokens"]
                + bucket["output_tokens"]
                + input_tokens
                + output_tokens
            )
            if self.per_agent_token_cap is not None and agent_total > self.per_agent_token_cap:
                raise BudgetExhausted("per_agent_token_cap", self.snapshot())

            self.llm_calls += 1
            self.global_input_tokens += input_tokens
            self.global_output_tokens += output_tokens
            self.global_cached_input_tokens += cached
            self.global_reasoning_tokens += reasoning
            bucket["llm_calls"] += 1
            bucket["input_tokens"] += input_tokens
            bucket["output_tokens"] += output_tokens
            bucket["cached_input_tokens"] += cached
            bucket["reasoning_tokens"] += reasoning
