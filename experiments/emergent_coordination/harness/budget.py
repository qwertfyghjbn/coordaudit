from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any


BUDGET_SCHEMA_VERSION = 2
LEGACY_BUDGET_KEYS = frozenset(
    {"global_input_token_cap", "global_output_token_cap", "per_agent_token_cap", "max_llm_calls"}
)


def validate_budget_config(budgets: dict[str, Any]) -> None:
    legacy = sorted(LEGACY_BUDGET_KEYS & set(budgets))
    if legacy:
        joined = ", ".join(legacy)
        raise ValueError(
            f"legacy budget fields are not supported by the runtime permit path: {joined}; "
            "use hard_team_call_permits and optional token_stop_threshold"
        )


def describe_budget_semantics(budgets: dict[str, Any]) -> dict[str, Any]:
    threshold = budgets.get("token_stop_threshold")
    return {
        "schema_version": BUDGET_SCHEMA_VERSION,
        "primary_budget_unit": "attempted_model_call",
        "token_usage_role": "observed_outcome",
        "retry_attempts_consume_permits": True,
        "token_stop": {
            "kind": "soft_post_response",
            "threshold": threshold,
            "basis": "provider_reported_input_plus_output",
            "max_in_flight_calls": 1 if threshold is not None else None,
        },
    }


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
    _condition: threading.Condition = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.hard_team_call_permits is not None and self.hard_team_call_permits < 0:
            raise ValueError("hard_team_call_permits must be non-negative")
        if self.token_stop_threshold is not None and self.token_stop_threshold <= 0:
            raise ValueError("token_stop_threshold must be positive")
        self._condition = threading.Condition(self._lock)

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
                "schema_version": BUDGET_SCHEMA_VERSION,
                "llm_calls": self.llm_calls,
                "attempted_llm_calls": self.llm_calls,
                "per_agent": {key: dict(value) for key, value in self.per_agent.items()},
                "permit_ledger": [dict(entry) for entry in self.permit_ledger],
                "enforced_limits": {
                    "hard_team_call_permits": self.hard_team_call_permits,
                },
                "runtime_limits": {
                    "wall_clock_timeout_seconds": self.wall_clock_timeout,
                },
                "soft_stops": {
                    "token_stop_threshold": self.token_stop_threshold,
                    "basis": "provider_reported_input_plus_output",
                    "max_in_flight_calls": 1 if self.token_stop_threshold is not None else None,
                },
                "observed_usage": {
                    "input_tokens": self.global_input_tokens,
                    "cached_input_tokens": self.global_cached_input_tokens,
                    "output_tokens": self.global_output_tokens,
                    "reasoning_tokens": self.global_reasoning_tokens,
                },
            }

    def acquire_call_permit(self, agent_id: str, *, retry_of: str | None = None) -> CallPermit:
        """Reserve one hard team permit before a request reaches the provider.

        The caller must settle the returned permit even if the provider times
        out or errors.  A retry is always a fresh permit and can optionally
        point at the permit it replaces.
        """
        with self._condition:
            while True:
                if self.hard_team_call_permits is not None and self.llm_calls >= self.hard_team_call_permits:
                    raise BudgetExhausted("hard_team_call_permits", self.snapshot())
                if self.token_stop_threshold is None:
                    break
                observed_tokens = self.global_input_tokens + self.global_output_tokens
                if observed_tokens >= self.token_stop_threshold:
                    raise BudgetExhausted("token_stop_threshold", self.snapshot())
                # Provider usage is authoritative only after a response.  A
                # threshold-enabled run therefore serializes provider calls.
                # Temporary in-flight occupancy waits; it is not exhaustion.
                if not any(entry["outcome"] == "granted" for entry in self.permit_ledger):
                    break
                self._condition.wait()
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
        with self._condition:
            ledger_entry = next((entry for entry in self.permit_ledger if entry["permit_id"] == permit.permit_id), None)
            if ledger_entry is None:
                raise ValueError(f"unknown permit: {permit.permit_id}")
            if ledger_entry["outcome"] != "granted":
                raise ValueError(f"permit already settled: {permit.permit_id}")
            token_usage = usage or TokenUsage()
            self._record_usage(permit.agent_id, token_usage)
            ledger_entry["outcome"] = outcome
            ledger_entry["token_usage"] = token_usage.as_dict()
            self._condition.notify_all()

    def check_wall_clock(self, elapsed_seconds: float) -> None:
        if self.wall_clock_timeout is None:
            return
        if elapsed_seconds > self.wall_clock_timeout:
            raise BudgetExhausted(
                "wall_clock_timeout",
                {**self.snapshot(), "elapsed_seconds": elapsed_seconds},
            )

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
