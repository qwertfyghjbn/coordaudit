from __future__ import annotations

import threading
import uuid
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


@dataclass(frozen=True)
class CallPermit:
    """An atomically issued authorization for exactly one provider request."""

    permit_id: str
    agent_id: str
    attempt_number: int
    retry_of: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "permit_id": self.permit_id,
            "agent_id": self.agent_id,
            "attempt_number": self.attempt_number,
            "retry_of": self.retry_of,
        }


@dataclass
class BudgetTracker:
    global_input_token_cap: int | None = None
    global_output_token_cap: int | None = None
    per_agent_token_cap: int | None = None
    max_llm_calls: int | None = None
    hard_team_call_permits: int | None = None
    token_stop_threshold: int | None = None
    wall_clock_timeout: float | None = None
    global_input_tokens: int = 0
    global_output_tokens: int = 0
    global_cached_input_tokens: int = 0
    global_reasoning_tokens: int = 0
    llm_calls: int = 0
    per_agent: dict[str, dict[str, int]] = field(default_factory=dict)
    permit_ledger: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def __post_init__(self) -> None:
        if self.hard_team_call_permits is not None and self.hard_team_call_permits < 0:
            raise ValueError("hard_team_call_permits must be non-negative")
        if self.max_llm_calls is not None and self.max_llm_calls < 0:
            raise ValueError("max_llm_calls must be non-negative")
        if self.token_stop_threshold is not None and self.token_stop_threshold <= 0:
            raise ValueError("token_stop_threshold must be positive")
        if (
            self.hard_team_call_permits is not None
            and self.max_llm_calls is not None
            and self.hard_team_call_permits != self.max_llm_calls
        ):
            raise ValueError("max_llm_calls and hard_team_call_permits disagree")

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
                "attempted_llm_calls": self.llm_calls,
                "per_agent": {key: dict(value) for key, value in self.per_agent.items()},
                "permit_ledger": [dict(entry) for entry in self.permit_ledger],
                "caps": {
                    "global_input_token_cap": self.global_input_token_cap,
                    "global_output_token_cap": self.global_output_token_cap,
                    "per_agent_token_cap": self.per_agent_token_cap,
                    "max_llm_calls": self.max_llm_calls,
                    "hard_team_call_permits": self._permit_limit(),
                    "token_stop_threshold": self.token_stop_threshold,
                    "wall_clock_timeout": self.wall_clock_timeout,
                },
            }

    def acquire_call_permit(self, agent_id: str, *, retry_of: str | None = None) -> CallPermit:
        """Reserve one hard team permit before a request reaches the provider.

        The caller must settle the returned permit even if the provider times
        out or errors.  A retry is always a fresh permit and can optionally
        point at the permit it replaces.
        """
        with self._lock:
            limit = self._permit_limit()
            if limit is not None and self.llm_calls >= limit:
                raise BudgetExhausted("hard_team_call_permits", self.snapshot())
            if self.token_stop_threshold is not None:
                observed_tokens = self.global_input_tokens + self.global_output_tokens
                if observed_tokens >= self.token_stop_threshold:
                    raise BudgetExhausted("token_stop_threshold", self.snapshot())
                # Usage is authoritative only after a response. Restricting a
                # threshold-enabled budget to one request in flight gives the
                # soft stop its stated one-call maximum overshoot guarantee.
                if any(entry["outcome"] == "granted" for entry in self.permit_ledger):
                    raise BudgetExhausted("token_stop_in_flight", self.snapshot())
            if retry_of is not None and not any(entry["permit_id"] == retry_of for entry in self.permit_ledger):
                raise ValueError(f"retry refers to unknown permit: {retry_of}")

            self.llm_calls += 1
            bucket = self._agent_bucket(agent_id)
            bucket["llm_calls"] += 1
            permit = CallPermit(
                permit_id=f"permit_{uuid.uuid4().hex}",
                agent_id=agent_id,
                attempt_number=self.llm_calls,
                retry_of=retry_of,
            )
            self.permit_ledger.append({**permit.as_dict(), "outcome": "granted", "token_usage": {}})
            return permit

    def settle_call_permit(self, permit: CallPermit, *, outcome: str, usage: TokenUsage | None = None) -> None:
        """Record the provider outcome and its actual reported usage.

        This never refunds a permit: attempted calls are the hard-budget unit.
        Token values are observations reported after the request, not a second
        admission decision.
        """
        if outcome not in {"succeeded", "timeout", "provider_error"}:
            raise ValueError(f"unsupported provider outcome: {outcome}")
        with self._lock:
            ledger_entry = next((entry for entry in self.permit_ledger if entry["permit_id"] == permit.permit_id), None)
            if ledger_entry is None:
                raise ValueError(f"unknown permit: {permit.permit_id}")
            if ledger_entry["outcome"] != "granted":
                raise ValueError(f"permit already settled: {permit.permit_id}")
            token_usage = usage or TokenUsage()
            self._record_usage(permit.agent_id, token_usage)
            ledger_entry["outcome"] = outcome
            ledger_entry["token_usage"] = token_usage.as_dict()

    def _permit_limit(self) -> int | None:
        if self.hard_team_call_permits is not None:
            return self.hard_team_call_permits
        return self.max_llm_calls

    def check_wall_clock(self, elapsed_seconds: float) -> None:
        if self.wall_clock_timeout is None:
            return
        if elapsed_seconds > self.wall_clock_timeout:
            raise BudgetExhausted(
                "wall_clock_timeout",
                {**self.snapshot(), "elapsed_seconds": elapsed_seconds},
            )

    def charge(self, agent_id: str, usage: TokenUsage) -> None:
        """Legacy test/helper API with pre-known usage.

        Live callers must use acquire_call_permit() followed by
        settle_call_permit(); provider usage is unavailable before a request.
        """
        with self._lock:
            limit = self._permit_limit()
            if limit is not None and self.llm_calls + 1 > limit:
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
            bucket["llm_calls"] += 1
            self._record_usage(agent_id, usage)

    def _record_usage(self, agent_id: str, usage: TokenUsage) -> None:
        input_tokens = _as_int(usage.input_tokens)
        output_tokens = _as_int(usage.output_tokens)
        cached = _as_int(usage.cached_input_tokens)
        reasoning = _as_int(usage.reasoning_tokens)
        self.global_input_tokens += input_tokens
        self.global_output_tokens += output_tokens
        self.global_cached_input_tokens += cached
        self.global_reasoning_tokens += reasoning
        bucket = self._agent_bucket(agent_id)
        bucket["input_tokens"] += input_tokens
        bucket["output_tokens"] += output_tokens
        bucket["cached_input_tokens"] += cached
        bucket["reasoning_tokens"] += reasoning
