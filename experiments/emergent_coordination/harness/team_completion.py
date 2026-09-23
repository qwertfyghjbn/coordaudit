"""Deterministic team/run completion barrier."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Iterable


ALL_AGENTS_TERMINAL_V1 = "all_agents_terminal_v1"
TEAM_RUNNING = "TEAM_RUNNING"
ADMISSION_CLOSED = "ADMISSION_CLOSED"
ALL_AGENTS_TERMINAL = "ALL_AGENTS_TERMINAL"


@dataclass(frozen=True)
class TeamCompletion:
    classification: str
    trigger: str
    terminal_reasons: dict[str, str]
    permits_used: int
    permits_remaining: int | None
    in_flight: int

    def as_payload(self, *, policy: str = ALL_AGENTS_TERMINAL_V1) -> dict[str, Any]:
        return {
            "policy": policy,
            "classification": self.classification,
            "trigger": self.trigger,
            "terminal_reasons": dict(sorted(self.terminal_reasons.items())),
            "permits_used": self.permits_used,
            "permits_remaining": self.permits_remaining,
            "in_flight": self.in_flight,
            "state": ALL_AGENTS_TERMINAL,
        }


class TeamCompletionBarrier:
    """One-shot barrier independent of topology or convergence policy."""

    def __init__(self, *, agent_ids: Iterable[str], policy: str | None):
        if policy not in {None, ALL_AGENTS_TERMINAL_V1}:
            raise ValueError(f"unsupported team completion policy: {policy}")
        self.policy = policy
        self.agent_ids = tuple(agent_ids)
        if not self.agent_ids or len(set(self.agent_ids)) != len(self.agent_ids):
            raise ValueError("team completion requires unique participating agent ids")
        self.state = TEAM_RUNNING
        self._emitted = False
        self._lock = threading.Lock()

    @property
    def emitted(self) -> bool:
        return self._emitted

    def evaluate(
        self,
        agent_results: list[dict[str, Any]],
        *,
        budget_snapshot: dict[str, Any],
        infrastructure_status: str = "valid",
    ) -> TeamCompletion | None:
        if self.policy is None:
            return None
        with self._lock:
            if self._emitted:
                return None
            by_id = {str(item.get("agent_id")): item for item in agent_results}
            if any(agent_id not in by_id for agent_id in self.agent_ids):
                self.state = TEAM_RUNNING
                return None
            raw_reasons = {agent_id: by_id[agent_id].get("stop_reason") for agent_id in self.agent_ids}
            reasons = {agent_id: str(raw_reasons[agent_id]) for agent_id in self.agent_ids}
            in_flight = _in_flight(budget_snapshot)
            if any(reason is None or str(reason) == "" for reason in raw_reasons.values()) or in_flight:
                self.state = ADMISSION_CLOSED if _admission_closed(budget_snapshot) else TEAM_RUNNING
                return None
            self.state = ALL_AGENTS_TERMINAL
            permits_used = int(budget_snapshot.get("attempted_llm_calls", budget_snapshot.get("llm_calls", 0)))
            configured = (budget_snapshot.get("enforced_limits") or {}).get("hard_team_call_permits")
            remaining = None if configured is None else max(0, int(configured) - permits_used)
            if infrastructure_status == "infrastructure_invalid":
                classification = "invalid"
            elif all(reasons[agent_id] == "submitted" for agent_id in self.agent_ids):
                classification = "clean_complete"
            else:
                classification = "forced_complete"
            trigger = "admission_closed_then_drained" if _admission_closed(budget_snapshot) else "all_agents_terminal"
            result = TeamCompletion(
                classification=classification,
                trigger=trigger,
                terminal_reasons=reasons,
                permits_used=permits_used,
                permits_remaining=remaining,
                in_flight=in_flight,
            )
            self._emitted = True
            return result

    def emit(self, event_log: Any, agent_results: list[dict[str, Any]], *, budget_snapshot: dict[str, Any], infrastructure_status: str = "valid") -> dict[str, Any] | None:
        result = self.evaluate(agent_results, budget_snapshot=budget_snapshot, infrastructure_status=infrastructure_status)
        if result is None:
            return None
        return event_log.emit("team_completion", payload=result.as_payload(policy=self.policy), outcome=result.classification, budget_progress=budget_snapshot)


def _admission_closed(snapshot: dict[str, Any]) -> bool:
    return bool(snapshot.get("admission_closed"))


def _in_flight(snapshot: dict[str, Any]) -> int:
    explicit = snapshot.get("in_flight_provider_calls")
    if explicit is not None:
        return int(explicit)
    return sum(1 for entry in snapshot.get("permit_ledger") or [] if entry.get("outcome") == "granted")
