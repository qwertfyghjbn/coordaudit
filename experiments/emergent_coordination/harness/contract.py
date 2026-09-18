"""Frozen, comparable matched-block contract definitions.

This module deliberately describes the experiment without starting an agent
runtime. Preregistered contract families are the single source of truth for
freezeable matched blocks: a block may only be frozen when its configuration
matches a registered family exactly. The run runtime already enforces its
permit and sandbox requirements; a separate block executor is still required
to bind and schedule all conditions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ContractViolation(ValueError):
    """The supplied configuration does not match a preregistered block contract."""


@dataclass(frozen=True)
class ConditionSpec:
    id: str
    mode: str
    agent_count: int

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "mode": self.mode, "agent_count": self.agent_count}


N4_CONDITIONS = (
    ConditionSpec("S1", "single", 1),
    ConditionSpec("P4", "parallel", 4),
    ConditionSpec("B4", "raw_blackboard", 4),
    ConditionSpec("T4", "structured_team", 4),
)

# Backwards-compatible alias for the preregistered pilot condition set.
N4_PILOT_CONDITIONS = N4_CONDITIONS

# The five-condition flowise block adds the centralized-control baseline M4
# (1 manager + 3 workers) to the same N=4 condition set. The family stays
# inert until the case manifest declares M4 in matched_conditions; block
# freezing enforces that declaration.
N4M_FLOWISE_CONDITIONS = N4_CONDITIONS + (ConditionSpec("M4", "manager_worker", 4),)


@dataclass(frozen=True)
class ContractFamily:
    """A preregistered block contract: the only freezeable block shape."""

    contract_id: str
    repository_ids: tuple[str, ...]
    conditions: tuple[ConditionSpec, ...]
    provider: str
    requested_model: str
    max_output_tokens: int
    hard_team_call_permits: int
    wall_clock_timeout_seconds: int


CONTRACT_FAMILIES: dict[str, ContractFamily] = {
    family.contract_id: family
    for family in (
        ContractFamily(
            contract_id="n4_pilot_v0",
            repository_ids=("repo_pilot_v0",),
            conditions=N4_CONDITIONS,
            provider="openai_compatible",
            requested_model="deepseek-flash",
            max_output_tokens=1024,
            hard_team_call_permits=32,
            wall_clock_timeout_seconds=600,
        ),
        ContractFamily(
            contract_id="n4_flowise_v1",
            repository_ids=("flowise_3_1_3_repository_v1",),
            conditions=N4_CONDITIONS,
            provider="openai_compatible",
            requested_model="deepseek-flash",
            max_output_tokens=2048,
            hard_team_call_permits=64,
            wall_clock_timeout_seconds=1200,
        ),
        ContractFamily(
            contract_id="n4m_flowise_v1",
            repository_ids=("flowise_3_1_3_repository_v1",),
            conditions=N4M_FLOWISE_CONDITIONS,
            provider="openai_compatible",
            requested_model="deepseek-flash",
            max_output_tokens=2048,
            hard_team_call_permits=64,
            wall_clock_timeout_seconds=1200,
        ),
    )
}

# Contract JSONs frozen before the family registry (n4_pilot_v0.json) carry no
# contract_id; that contract is the unique legacy preregistration.
LEGACY_CONTRACT_ID = "n4_pilot_v0"


@dataclass(frozen=True)
class BlockConfig:
    schema_version: int
    contract_id: str
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
        family = CONTRACT_FAMILIES.get(self.contract_id)
        if family is None:
            raise ContractViolation(f"unknown block contract: {self.contract_id}")
        if self.schema_version != 1:
            raise ContractViolation("unsupported block contract schema version")
        if not self.repository_id or not self.repository_version:
            raise ContractViolation("repository identity and version are required")
        if self.repository_id not in family.repository_ids:
            raise ContractViolation(
                f"contract {family.contract_id} is preregistered for "
                f"{'/'.join(family.repository_ids)}, not {self.repository_id}"
            )
        if self.provider != family.provider:
            raise ContractViolation(
                f"contract {family.contract_id} requires provider={family.provider!r}"
            )
        if self.requested_model != family.requested_model:
            raise ContractViolation(
                f"contract {family.contract_id} requires requested_model={family.requested_model!r}"
            )
        if self.thinking_mode != "disabled":
            raise ContractViolation("matched blocks freeze DeepSeek non-thinking mode so temperature=0 is effective")
        if self.temperature != 0:
            raise ContractViolation("matched blocks freeze temperature=0 alongside disabled thinking")
        if self.max_output_tokens != family.max_output_tokens:
            raise ContractViolation(
                f"contract {family.contract_id} requires a "
                f"{family.max_output_tokens}-token per-call output ceiling"
            )
        if self.hard_team_call_permits != family.hard_team_call_permits:
            raise ContractViolation(
                f"contract {family.contract_id} requires exactly {family.hard_team_call_permits} shared call permits"
            )
        if self.max_steps != self.hard_team_call_permits:
            raise ContractViolation("max_steps is the permit-sized safety ceiling, not an allocation")
        if self.per_agent_token_cap is not None:
            raise ContractViolation("per-agent token caps are not part of a matched block contract")
        if self.max_provider_retries != 1:
            raise ContractViolation("matched blocks freeze exactly one harness-controlled provider retry")
        if self.wall_clock_timeout_seconds != family.wall_clock_timeout_seconds:
            raise ContractViolation(
                f"contract {family.contract_id} freezes "
                f"wall_clock_timeout_seconds={family.wall_clock_timeout_seconds}"
            )
        if self.token_stop_threshold is not None and self.token_stop_threshold <= 0:
            raise ContractViolation("token stop threshold must be positive when supplied")
        if self.conditions != family.conditions:
            raise ContractViolation(
                f"conditions must be exactly {'/'.join(condition.id for condition in family.conditions)} "
                f"in canonical form for contract {family.contract_id}"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_id": self.contract_id,
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
            contract_id=str(raw.get("contract_id", LEGACY_CONTRACT_ID)),
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
