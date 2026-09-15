"""Frozen, comparable N=4 pilot contract definitions.

This module deliberately describes the experiment without starting an agent
runtime. It is the single source of truth for the S1/P4/B4/T4 matched block.
The run runtime already enforces its permit and sandbox requirements; a
separate block executor is still required to bind and schedule all conditions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ContractViolation(ValueError):
    """The supplied configuration is not the preregistered N=4 pilot contract."""


@dataclass(frozen=True)
class ConditionSpec:
    id: str
    mode: str
    agent_count: int

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "mode": self.mode, "agent_count": self.agent_count}


N4_PILOT_CONDITIONS = (
    ConditionSpec("S1", "single", 1),
    ConditionSpec("P4", "parallel", 4),
    ConditionSpec("B4", "raw_blackboard", 4),
    ConditionSpec("T4", "structured_team", 4),
)


@dataclass(frozen=True)
class BlockConfig:
    schema_version: int
    repository_id: str
    repository_version: str
    requested_model: str
    provider: str
    thinking_mode: str
    temperature: float
    max_output_tokens: int
    hard_team_call_permits: int
    max_steps: int
    wall_clock_timeout_seconds: int
    token_stop_threshold: int | None
    per_agent_token_cap: int | None
    max_provider_retries: int
    conditions: tuple[ConditionSpec, ...]

    def validate(self) -> None:
        if self.schema_version != 1:
            raise ContractViolation("unsupported block contract schema version")
        if not self.repository_id or not self.repository_version:
            raise ContractViolation("repository identity and version are required")
        if not self.requested_model or not self.provider:
            raise ContractViolation("provider and requested model are required")
        if self.thinking_mode != "disabled":
            raise ContractViolation("N=4 pilot freezes DeepSeek non-thinking mode so temperature=0 is effective")
        if self.temperature < 0:
            raise ContractViolation("temperature must be non-negative")
        if self.max_output_tokens != 1024:
            raise ContractViolation("N=4 pilot requires a 1024-token per-call output ceiling")
        if self.hard_team_call_permits != 32:
            raise ContractViolation("N=4 pilot requires exactly 32 shared call permits")
        if self.max_steps != self.hard_team_call_permits:
            raise ContractViolation("max_steps is the 32-step safety ceiling, not an allocation")
        if self.per_agent_token_cap is not None:
            raise ContractViolation("per-agent token caps are not part of the matched N=4 contract")
        if self.max_provider_retries != 1:
            raise ContractViolation("N=4 pilot requires exactly one harness-controlled provider retry")
        if self.wall_clock_timeout_seconds <= 0:
            raise ContractViolation("wall-clock timeout must be positive")
        if self.token_stop_threshold is not None and self.token_stop_threshold <= 0:
            raise ContractViolation("token stop threshold must be positive when supplied")
        if self.conditions != N4_PILOT_CONDITIONS:
            raise ContractViolation("conditions must be exactly S1, P4, B4, and T4 in canonical form")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "repository": {"id": self.repository_id, "version": self.repository_version},
            "model": {
                "provider": self.provider,
                "requested_model": self.requested_model,
                "thinking_mode": self.thinking_mode,
                "temperature": self.temperature,
                "max_output_tokens": self.max_output_tokens,
            },
            "hard_team_call_permits": self.hard_team_call_permits,
            "max_steps": self.max_steps,
            "wall_clock_timeout_seconds": self.wall_clock_timeout_seconds,
            "token_stop_threshold": self.token_stop_threshold,
            "per_agent_token_cap": self.per_agent_token_cap,
            "max_provider_retries": self.max_provider_retries,
            "conditions": [condition.as_dict() for condition in self.conditions],
        }


def load_block_config(path: Path) -> BlockConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    try:
        repository = raw["repository"]
        model = raw["model"]
        budget = raw["budget"]
        runtime = raw["runtime"]
        retry = raw["retry"]
        conditions = tuple(
            ConditionSpec(id=item["id"], mode=item["mode"], agent_count=int(item["agent_count"]))
            for item in raw["conditions"]
        )
        config = BlockConfig(
            schema_version=int(raw["schema_version"]),
            repository_id=str(repository["id"]),
            repository_version=str(repository["version"]),
            requested_model=str(model["requested_model"]),
            provider=str(model["provider"]),
            thinking_mode=str(model["thinking_mode"]),
            temperature=float(model["temperature"]),
            max_output_tokens=int(model["max_output_tokens"]),
            hard_team_call_permits=int(budget["hard_team_call_permits"]),
            max_steps=int(runtime["max_steps"]),
            wall_clock_timeout_seconds=int(runtime["wall_clock_timeout_seconds"]),
            token_stop_threshold=_optional_int(budget.get("token_stop_threshold")),
            per_agent_token_cap=_optional_int(budget.get("per_agent_token_cap")),
            max_provider_retries=int(retry["max_provider_retries"]),
            conditions=conditions,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractViolation(f"invalid block config: {exc}") from exc
    config.validate()
    return config


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)
