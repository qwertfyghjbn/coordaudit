from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any


BUDGET_SCHEMA_VERSION = 3
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
    reserve = int(budgets.get("team_finalization_reserve", 0) or 0)
    hard = budgets.get("hard_team_call_permits")
    if reserve < 0:
        raise ValueError("team_finalization_reserve must be non-negative")
    if hard is not None and reserve > int(hard):
        raise ValueError("team_finalization_reserve cannot exceed hard_team_call_permits")
    post_sync_per_agent = int(budgets.get("post_sync_reservation_per_agent", 0) or 0)
    post_sync_agents = int(budgets.get("post_sync_reservation_agents", 0) or 0)
    if post_sync_per_agent < 0 or post_sync_agents < 0:
        raise ValueError("post-sync reservation values must be non-negative")
    if hard is not None and post_sync_per_agent * post_sync_agents > int(hard):
        raise ValueError("post-sync reservations cannot exceed hard_team_call_permits")


def describe_budget_semantics(budgets: dict[str, Any]) -> dict[str, Any]:
    threshold = budgets.get("token_stop_threshold")
    reserved = int(budgets.get("reserved_final_synthesis_permits", 0) or 0)
    team_reserve = int(budgets.get("team_finalization_reserve", 0) or 0)
    post_sync_per_agent = int(budgets.get("post_sync_reservation_per_agent", 0) or 0)
    post_sync_agents = int(budgets.get("post_sync_reservation_agents", 0) or 0)
    hard = budgets.get("hard_team_call_permits")
    return {
        "schema_version": BUDGET_SCHEMA_VERSION,
        "primary_budget_unit": "attempted_model_call",
        "token_usage_role": "observed_outcome",
        "retry_attempts_consume_permits": True,
        "reserved_final_synthesis": {
            "permits": reserved,
            "normal_work_permits": None if hard is None else int(hard) - reserved,
            "inside_hard_budget": True,
        },
        "team_finalization": {
            "policy": budgets.get("team_finalization_policy"),
            "reserve": team_reserve,
            "trigger": "remaining_team_permits_lte_reserve" if team_reserve else None,
            "inside_hard_budget": True,
        },
        "post_sync_reservation": {
            "permits_per_eligible_agent": post_sync_per_agent,
            "eligible_agents": post_sync_agents,
            "total_reserved_permits": post_sync_per_agent * post_sync_agents,
            "normal_work_permits": (
                None if hard is None else int(hard) - post_sync_per_agent * post_sync_agents
            ),
            "inside_hard_budget": True,
            "retry_attempts_consume_reservation": True,
        },
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
    # completion_v3 reserves a permit inside (never in addition to) the
    # declared team budget.  The default keeps every frozen generation's
    # accounting byte-for-byte compatible.
    reserved_final_synthesis_permits: int = 0
    team_finalization_policy: str | None = None
    team_finalization_reserve: int = 0
    # The reservation is static: ordinary work can never consume these
    # permits before RESULT_SYNC makes an eligible agent's POST_SYNC window
    # available.  Individual agents retain their allocation; it is not a
    # shared last-minute pool.
    post_sync_reservation_per_agent: int = 0
    post_sync_eligible_agents: tuple[str, ...] = ()
    token_stop_threshold: int | None = None
    wall_clock_timeout: float | None = None
    global_input_tokens: int = 0
    global_output_tokens: int = 0
    global_cached_input_tokens: int = 0
    global_reasoning_tokens: int = 0
    llm_calls: int = 0
    per_agent: dict[str, dict[str, int]] = field(default_factory=dict)
    permit_ledger: list[dict[str, Any]] = field(default_factory=list)
    admission_closed: bool = False
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _condition: threading.Condition = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.hard_team_call_permits is not None and self.hard_team_call_permits < 0:
            raise ValueError("hard_team_call_permits must be non-negative")
        if self.token_stop_threshold is not None and self.token_stop_threshold <= 0:
            raise ValueError("token_stop_threshold must be positive")
        if self.reserved_final_synthesis_permits < 0:
            raise ValueError("reserved_final_synthesis_permits must be non-negative")
        if (
            self.hard_team_call_permits is not None
            and self.reserved_final_synthesis_permits > self.hard_team_call_permits
        ):
            raise ValueError("reserved final synthesis permits cannot exceed the hard team budget")
        if self.team_finalization_reserve < 0:
            raise ValueError("team_finalization_reserve must be non-negative")
        if (
            self.hard_team_call_permits is not None
            and self.team_finalization_reserve > self.hard_team_call_permits
        ):
            raise ValueError("team_finalization_reserve cannot exceed the hard team budget")
        if self.team_finalization_policy not in {None, "team_remaining_permits_v1"}:
            raise ValueError(f"unsupported team_finalization_policy: {self.team_finalization_policy}")
        if self.post_sync_reservation_per_agent < 0:
            raise ValueError("post_sync_reservation_per_agent must be non-negative")
        if len(set(self.post_sync_eligible_agents)) != len(self.post_sync_eligible_agents):
            raise ValueError("post_sync_eligible_agents must be unique")
        if self.post_sync_reservation_per_agent and not self.post_sync_eligible_agents:
            raise ValueError("post-sync reservation requires eligible agents")
        if (
            self.hard_team_call_permits is not None
            and self.post_sync_reservation_per_agent * len(self.post_sync_eligible_agents) > self.hard_team_call_permits
        ):
            raise ValueError("post-sync reservations cannot exceed the hard team budget")
        self._final_synthesis_authorized: str | None = None
        self._team_finalization_started = False
        self._team_finalization_trigger: dict[str, Any] | None = None
        self._team_finalization_event_emitted = False
        self._registered_agents: set[str] = set()
        self._terminal_agents: set[str] = set()
        self._post_sync_windows: dict[str, dict[str, Any]] = {
            agent_id: {
                "opened": False,
                "initial_attempted": False,
                "verification_pending": False,
                "initial_attempts": 0,
                "followup_attempts": 0,
                "attempts": 0,
            }
            for agent_id in self.post_sync_eligible_agents
        }
        self._condition = threading.Condition(self._lock)

    def register_agent(self, agent_id: str) -> None:
        with self._lock:
            self._registered_agents.add(agent_id)
            self._terminal_agents.discard(agent_id)

    def mark_agent_terminal(self, agent_id: str) -> None:
        with self._lock:
            self._terminal_agents.add(agent_id)

    @property
    def team_finalization_active(self) -> bool:
        with self._lock:
            return self._team_finalization_started

    def maybe_start_team_finalization(self) -> dict[str, Any] | None:
        """Atomically enter the shared finalization epoch at the reserve boundary."""
        with self._condition:
            if self.team_finalization_policy is None or self._team_finalization_started:
                return None
            remaining = self.remaining_permits
            if remaining is None or remaining > self.team_finalization_reserve:
                return None
            self._team_finalization_started = True
            self._team_finalization_trigger = {
                "policy": self.team_finalization_policy,
                "reserve": self.team_finalization_reserve,
                "trigger_call_index": self.llm_calls + 1,
                "trigger_remaining_permits": remaining,
                "active_agents": sorted(self._registered_agents - self._terminal_agents),
            }
            self._condition.notify_all()
            return dict(self._team_finalization_trigger)

    def claim_team_finalization_trigger(self) -> dict[str, Any] | None:
        """Return the one transition record that should be written to events."""
        with self._lock:
            if self._team_finalization_trigger is None or self._team_finalization_event_emitted:
                return None
            self._team_finalization_event_emitted = True
            return dict(self._team_finalization_trigger)

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
            enforced_limits: dict[str, Any] = {"hard_team_call_permits": self.hard_team_call_permits}
            if self.reserved_final_synthesis_permits:
                enforced_limits.update(
                    {
                        "reserved_final_synthesis_permits": self.reserved_final_synthesis_permits,
                        "normal_work_permits": (
                            None
                            if self.hard_team_call_permits is None
                            else self.hard_team_call_permits - self.reserved_final_synthesis_permits
                        ),
                    }
                )
            return {
                "schema_version": BUDGET_SCHEMA_VERSION,
                "llm_calls": self.llm_calls,
                "attempted_llm_calls": self.llm_calls,
                "per_agent": {key: dict(value) for key, value in self.per_agent.items()},
                "permit_ledger": [dict(entry) for entry in self.permit_ledger],
                "admission_closed": self.admission_closed,
                "team_finalization": {
                    "policy": self.team_finalization_policy,
                    "reserve": self.team_finalization_reserve,
                    "active": self._team_finalization_started,
                    "trigger": dict(self._team_finalization_trigger) if self._team_finalization_trigger else None,
                },
                "post_sync_reservation": {
                    "permits_per_eligible_agent": self.post_sync_reservation_per_agent,
                    "eligible_agents": list(self.post_sync_eligible_agents),
                    "total_reserved_permits": self._post_sync_reserved_total,
                    "normal_work_permits": self._normal_work_permit_limit,
                    "windows": {agent_id: dict(state) for agent_id, state in self._post_sync_windows.items()},
                },
                "final_synthesis_authorized_for": self._final_synthesis_authorized,
                "in_flight_provider_calls": sum(1 for entry in self.permit_ledger if entry.get("outcome") == "granted"),
                "enforced_limits": enforced_limits,
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

    @property
    def remaining_permits(self) -> int | None:
        with self._lock:
            if self.hard_team_call_permits is None:
                return None
            return max(0, self.hard_team_call_permits - self.llm_calls)

    @property
    def _post_sync_reserved_total(self) -> int:
        return self.post_sync_reservation_per_agent * len(self.post_sync_eligible_agents)

    @property
    def _normal_work_permit_limit(self) -> int | None:
        if self.hard_team_call_permits is None:
            return None
        return self.hard_team_call_permits - self._post_sync_reserved_total

    def open_post_sync_window(self, agent_id: str) -> dict[str, Any]:
        """Make one pre-reserved POST_SYNC window available to an eligible agent."""
        with self._condition:
            state = self._post_sync_windows.get(agent_id)
            if state is None:
                raise BudgetExhausted("post_sync_agent_not_eligible", self.snapshot())
            state["opened"] = True
            self._condition.notify_all()
            return dict(state)

    def mark_post_sync_verification_attempted(self, agent_id: str) -> dict[str, Any]:
        """Require the next reserved request to carry the tool result to the model."""
        with self._condition:
            state = self._post_sync_windows.get(agent_id)
            if state is None or not state["opened"] or not state["initial_attempted"]:
                raise BudgetExhausted("post_sync_verification_not_available", self.snapshot())
            if state["verification_pending"]:
                raise BudgetExhausted("post_sync_verification_already_pending", self.snapshot())
            state["verification_pending"] = True
            return dict(state)

    def authorize_final_synthesis(self, agent_id: str) -> None:
        """Transfer ownership of the reserved permit to final synthesis.

        Authorization is an explicit state transition.  It can only happen at
        the reserved boundary, so ordinary calls cannot consume the permit.
        """
        with self._condition:
            if self.reserved_final_synthesis_permits != 1:
                raise BudgetExhausted("final_synthesis_not_reserved", self.snapshot())
            remaining = self.remaining_permits
            if remaining is None or remaining < self.reserved_final_synthesis_permits:
                raise BudgetExhausted("final_synthesis_boundary_not_reached", self.snapshot())
            if self._final_synthesis_authorized is not None:
                raise BudgetExhausted("final_synthesis_already_authorized", self.snapshot())
            self._final_synthesis_authorized = agent_id

    def acquire_call_permit(
        self,
        agent_id: str,
        *,
        retry_of: str | None = None,
        call_kind: str = "normal",
    ) -> CallPermit:
        """Reserve one hard team permit before a request reaches the provider.

        The caller must settle the returned permit even if the provider times
        out or errors.  A retry is always a fresh permit and can optionally
        point at the permit it replaces.
        """
        with self._condition:
            # Admission and the reserve-boundary transition share this lock.
            # This prevents several parallel callers that observed 33 permits
            # from crossing the 32 boundary before any caller records it.
            self.maybe_start_team_finalization()
            while True:
                if self.hard_team_call_permits is not None and self.llm_calls >= self.hard_team_call_permits:
                    self.admission_closed = True
                    raise BudgetExhausted("hard_team_call_permits", self.snapshot())
                if call_kind not in {"normal", "final_synthesis", "post_sync_initial", "post_sync_followup", "post_sync_submit"}:
                    raise ValueError(f"unsupported call kind: {call_kind}")
                if call_kind == "normal" and self._normal_work_permit_limit is not None and self.llm_calls >= self._normal_work_permit_limit:
                    raise BudgetExhausted("post_sync_reservation_protected", self.snapshot())
                if call_kind.startswith("post_sync_"):
                    state = self._post_sync_windows.get(agent_id)
                    if state is None or not state["opened"]:
                        raise BudgetExhausted("post_sync_window_not_open", self.snapshot())
                    if state["attempts"] >= self.post_sync_reservation_per_agent:
                        raise BudgetExhausted("post_sync_reservation_exhausted", self.snapshot())
                    if call_kind == "post_sync_initial" and (
                        state["verification_pending"] or state["initial_attempts"] >= 2
                    ):
                        raise BudgetExhausted("post_sync_initial_already_attempted", self.snapshot())
                    if call_kind == "post_sync_followup" and (
                        not state["verification_pending"] or state["followup_attempts"] >= 2
                    ):
                        raise BudgetExhausted("post_sync_followup_not_required", self.snapshot())
                    if call_kind == "post_sync_submit" and (
                        not state["initial_attempted"]
                        or (state["verification_pending"] and not state["followup_attempts"])
                    ):
                        raise BudgetExhausted("post_sync_submit_not_ready", self.snapshot())
                if call_kind == "normal" and self.reserved_final_synthesis_permits:
                    if self._final_synthesis_authorized is not None:
                        self.admission_closed = True
                        raise BudgetExhausted("team_finalization_active", self.snapshot())
                    remaining = self.hard_team_call_permits - self.llm_calls if self.hard_team_call_permits is not None else None
                    if remaining is not None and remaining <= self.reserved_final_synthesis_permits:
                        self.admission_closed = True
                        raise BudgetExhausted("reserved_final_synthesis", self.snapshot())
                if call_kind == "final_synthesis":
                    if self._final_synthesis_authorized != agent_id:
                        raise BudgetExhausted("final_synthesis_not_authorized", self.snapshot())
                    if self.reserved_final_synthesis_permits != 1:
                        raise BudgetExhausted("final_synthesis_not_reserved", self.snapshot())
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
            if self.hard_team_call_permits is not None and self.llm_calls >= self.hard_team_call_permits:
                # Closing admission is distinct from completion: this request
                # still settles and processes its returned local actions.
                self.admission_closed = True
            bucket = self._agent_bucket(agent_id)
            bucket["llm_calls"] += 1
            if call_kind.startswith("post_sync_"):
                state = self._post_sync_windows[agent_id]
                state["attempts"] += 1
                if call_kind == "post_sync_initial":
                    state["initial_attempted"] = True
                    state["initial_attempts"] += 1
                elif call_kind == "post_sync_followup":
                    state["followup_attempts"] += 1
            permit = CallPermit(
                permit_id=f"permit_{uuid.uuid4().hex}",
                agent_id=agent_id,
                attempt_number=self.llm_calls,
                retry_of=retry_of,
            )
            self.permit_ledger.append({**permit.as_dict(), "call_kind": call_kind, "outcome": "granted", "token_usage": {}})
            if call_kind == "final_synthesis":
                self._final_synthesis_authorized = None
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
