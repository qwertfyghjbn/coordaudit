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

# The 192-permit follow-up is deliberately a single-condition diagnostic:
# only T4 changes its shared exploration budget; all completion semantics stay
# bound to the v2 team-finalization lifecycle.
T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS = (
    ConditionSpec("T4", "structured_team", 4),
)

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
    reserved_final_synthesis_permits: int = 0
    completion_generation: str | None = None
    team_finalization_deadline_seconds: int | None = None
    max_steps: int | None = None
    team_finalization_policy: str | None = None
    team_finalization_reserve: int = 0
    task_board_sequencing_policy: str | None = None
    task_closure_policy: str | None = None
    result_sync_policy: str | None = None
    post_sync_window_policy: str | None = None
    post_sync_reservation_per_agent: int = 0


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
            contract_id="n4_flowise_completion_calibration_v2",
            repository_ids=("flowise_3_1_3_repository_v1",),
            conditions=N4_CONDITIONS,
            provider="openai_compatible",
            requested_model="deepseek-flash",
            max_output_tokens=4096,
            hard_team_call_permits=96,
            wall_clock_timeout_seconds=1200,
            max_steps=96,
            team_finalization_policy="team_remaining_permits_v1",
            team_finalization_reserve=32,
        ),
        ContractFamily(
            contract_id="t4_flowise_completion_budget_diagnostic_v1",
            repository_ids=("flowise_3_1_3_repository_v1",),
            conditions=T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS,
            provider="openai_compatible",
            requested_model="deepseek-flash",
            max_output_tokens=4096,
            hard_team_call_permits=192,
            wall_clock_timeout_seconds=1200,
            # Preserve the v2 per-agent safety ceiling; only the shared team
            # exploration budget is expanded in this diagnostic.
            max_steps=96,
            team_finalization_policy="team_remaining_permits_v1",
            team_finalization_reserve=32,
        ),
        ContractFamily(
            contract_id="t4_flowise_board_bootstrap_adoption_v1",
            repository_ids=("flowise_3_1_3_repository_v1",),
            conditions=T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS,
            provider="openai_compatible",
            requested_model="deepseek-flash",
            max_output_tokens=4096,
            hard_team_call_permits=192,
            wall_clock_timeout_seconds=1200,
            max_steps=96,
            team_finalization_policy="team_remaining_permits_v1",
            team_finalization_reserve=32,
        ),
        ContractFamily(
            contract_id="t4_flowise_task_lifecycle_v2",
            repository_ids=("flowise_3_1_3_repository_v1",),
            conditions=T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS,
            provider="openai_compatible",
            requested_model="deepseek-flash",
            max_output_tokens=4096,
            hard_team_call_permits=192,
            wall_clock_timeout_seconds=1200,
            max_steps=96,
            team_finalization_policy="team_remaining_permits_v1",
            team_finalization_reserve=32,
        ),
        ContractFamily(
            contract_id="t4_flowise_nonoverlap_v1",
            repository_ids=("flowise_3_1_3_repository_v1",),
            conditions=T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS,
            provider="openai_compatible",
            requested_model="deepseek-flash",
            max_output_tokens=4096,
            hard_team_call_permits=192,
            wall_clock_timeout_seconds=1200,
            max_steps=96,
            team_finalization_policy="team_remaining_permits_v1",
            team_finalization_reserve=32,
        ),
        ContractFamily(
            contract_id="t4_flowise_sequenced_bootstrap_v1",
            repository_ids=("flowise_3_1_3_repository_v1",),
            conditions=T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS,
            provider="openai_compatible",
            requested_model="deepseek-flash",
            max_output_tokens=4096,
            hard_team_call_permits=192,
            wall_clock_timeout_seconds=1200,
            max_steps=96,
            team_finalization_policy="team_remaining_permits_v1",
            team_finalization_reserve=32,
            task_board_sequencing_policy="initialization_lease_v1",
        ),
        ContractFamily(
            contract_id="t4_flowise_sequenced_bootstrap_task_closure_v1",
            repository_ids=("flowise_3_1_3_repository_v1",),
            conditions=T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS,
            provider="openai_compatible",
            requested_model="deepseek-flash",
            max_output_tokens=4096,
            hard_team_call_permits=192,
            wall_clock_timeout_seconds=1200,
            max_steps=96,
            team_finalization_policy="team_remaining_permits_v1",
            team_finalization_reserve=32,
            task_board_sequencing_policy="initialization_lease_v1",
            task_closure_policy="task_closure_gate_v1",
        ),
        ContractFamily(
            contract_id="t4_flowise_result_sync_v1",
            repository_ids=("flowise_3_1_3_repository_v1",),
            conditions=T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS,
            provider="openai_compatible",
            requested_model="deepseek-flash",
            max_output_tokens=4096,
            hard_team_call_permits=192,
            wall_clock_timeout_seconds=1200,
            max_steps=96,
            team_finalization_policy="team_remaining_permits_v1",
            team_finalization_reserve=32,
            task_board_sequencing_policy="initialization_lease_v1",
            task_closure_policy="task_closure_gate_v1",
            result_sync_policy="result_sync_v1",
        ),
        ContractFamily(
            contract_id="t4_flowise_result_inspection_prompt_v1",
            repository_ids=("flowise_3_1_3_repository_v1",),
            conditions=T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS,
            provider="openai_compatible",
            requested_model="deepseek-flash",
            max_output_tokens=4096,
            hard_team_call_permits=192,
            wall_clock_timeout_seconds=1200,
            max_steps=96,
            team_finalization_policy="team_remaining_permits_v1",
            team_finalization_reserve=32,
            task_board_sequencing_policy="initialization_lease_v1",
            task_closure_policy="task_closure_gate_v1",
            result_sync_policy="result_sync_v1",
        ),
        ContractFamily(
            contract_id="t4_flowise_post_sync_inspection_v2",
            repository_ids=("flowise_3_1_3_repository_v1",),
            conditions=T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS,
            provider="openai_compatible",
            requested_model="deepseek-flash",
            max_output_tokens=4096,
            hard_team_call_permits=192,
            wall_clock_timeout_seconds=1200,
            max_steps=96,
            team_finalization_policy="team_remaining_permits_v1",
            team_finalization_reserve=32,
            task_board_sequencing_policy="initialization_lease_v1",
            task_closure_policy="task_closure_gate_v1",
            result_sync_policy="result_sync_v1",
        ),
        ContractFamily(
            contract_id="t4_flowise_post_sync_relevance_v1",
            repository_ids=("flowise_3_1_3_repository_v1",),
            conditions=T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS,
            provider="openai_compatible",
            requested_model="deepseek-flash",
            max_output_tokens=4096,
            hard_team_call_permits=192,
            wall_clock_timeout_seconds=1200,
            max_steps=96,
            team_finalization_policy="team_remaining_permits_v1",
            team_finalization_reserve=32,
            task_board_sequencing_policy="initialization_lease_v1",
            task_closure_policy="task_closure_gate_v1",
            result_sync_policy="result_sync_v1",
        ),
        ContractFamily(
            contract_id="t4_flowise_post_sync_verification_permission_v1",
            repository_ids=("flowise_3_1_3_repository_v1",),
            conditions=T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS,
            provider="openai_compatible",
            requested_model="deepseek-flash",
            max_output_tokens=4096,
            hard_team_call_permits=192,
            wall_clock_timeout_seconds=1200,
            max_steps=96,
            team_finalization_policy="team_remaining_permits_v1",
            team_finalization_reserve=32,
            task_board_sequencing_policy="initialization_lease_v1",
            task_closure_policy="task_closure_gate_v1",
            result_sync_policy="result_sync_v1",
        ),
        ContractFamily(
            contract_id="t4_flowise_post_sync_window_v1",
            repository_ids=("flowise_3_1_3_repository_v1",),
            conditions=T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS,
            provider="openai_compatible",
            requested_model="deepseek-flash",
            max_output_tokens=4096,
            hard_team_call_permits=192,
            wall_clock_timeout_seconds=1200,
            max_steps=96,
            team_finalization_policy="team_remaining_permits_v1",
            team_finalization_reserve=32,
            task_board_sequencing_policy="initialization_lease_v1",
            task_closure_policy="task_closure_gate_v1",
            result_sync_policy="result_sync_v1",
            post_sync_window_policy="t4_post_sync_window_v1",
            post_sync_reservation_per_agent=4,
        ),
        ContractFamily(
            contract_id="t4_flowise_post_sync_window_v2",
            repository_ids=("flowise_3_1_3_repository_v1",),
            conditions=T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS,
            provider="openai_compatible",
            requested_model="deepseek-flash",
            max_output_tokens=4096,
            hard_team_call_permits=192,
            wall_clock_timeout_seconds=1200,
            max_steps=96,
            team_finalization_policy="team_remaining_permits_v1",
            team_finalization_reserve=32,
            task_board_sequencing_policy="initialization_lease_v1",
            task_closure_policy="task_closure_gate_v1",
            result_sync_policy="result_sync_v1",
            post_sync_window_policy="t4_post_sync_window_v2",
            post_sync_reservation_per_agent=4,
        ),
        ContractFamily(
            contract_id="n4m_flowise_completion_v3",
            repository_ids=("flowise_3_1_3_repository_v1",),
            conditions=N4M_FLOWISE_CONDITIONS,
            provider="openai_compatible",
            requested_model="deepseek-flash",
            max_output_tokens=4096,
            hard_team_call_permits=64,
            wall_clock_timeout_seconds=1200,
            reserved_final_synthesis_permits=1,
            completion_generation="completion_v3",
            team_finalization_deadline_seconds=60,
        ),
        ContractFamily(
            contract_id="n4m_flowise_calibration_v1",
            repository_ids=("flowise_3_1_3_repository_v1",),
            conditions=N4M_FLOWISE_CONDITIONS,
            provider="openai_compatible",
            requested_model="deepseek-flash",
            max_output_tokens=4096,
            hard_team_call_permits=96,
            wall_clock_timeout_seconds=1200,
            max_steps=96,
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
    final_synthesis_retries: int = 0
    completion_policy: str | None = None
    team_completion_policy: str | None = None
    team_finalization_policy: str | None = None
    team_finalization_reserve: int = 0
    task_board_sequencing_policy: str | None = None
    task_closure_policy: str | None = None
    result_sync_policy: str | None = None
    post_sync_window_policy: str | None = None
    post_sync_reservation_per_agent: int = 0
    reserved_final_synthesis_permits: int = 0
    completion_generation: str | None = None
    team_finalization_deadline_seconds: int | None = None
    condition_runtime: dict[str, dict[str, Any]] | None = None
    prompt_profile: str | None = None

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
        expected_max_steps = family.max_steps if family.max_steps is not None else self.hard_team_call_permits
        if self.max_steps != expected_max_steps:
            raise ContractViolation(f"max_steps must equal the contract safety ceiling ({expected_max_steps})")
        if self.per_agent_token_cap is not None:
            raise ContractViolation("per-agent token caps are not part of a matched block contract")
        if self.max_provider_retries != 1:
            raise ContractViolation("matched blocks freeze exactly one harness-controlled provider retry")
        if self.final_synthesis_retries != 0:
            raise ContractViolation("final synthesis is frozen with no retry")
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
        if self.completion_policy not in {
            None, "convergent_v1", "guidance_only", "scheduler_only", "convergent_v2", "scheduler_only_v2"
        }:
            raise ContractViolation("unsupported completion_policy")
        if self.team_completion_policy not in {None, "all_agents_terminal_v1"}:
            if self.team_completion_policy != "team_completion_v3":
                raise ContractViolation("unsupported team_completion_policy")
        if self.team_finalization_policy not in {None, "team_remaining_permits_v1"}:
            raise ContractViolation("unsupported team_finalization_policy")
        if self.task_board_sequencing_policy not in {None, "initialization_lease_v1"}:
            raise ContractViolation("unsupported task_board_sequencing_policy")
        if self.task_closure_policy not in {None, "task_closure_gate_v1"}:
            raise ContractViolation("unsupported task_closure_policy")
        if self.result_sync_policy not in {None, "result_sync_v1"}:
            raise ContractViolation("unsupported result_sync_policy")
        if self.post_sync_window_policy not in {None, "t4_post_sync_window_v1", "t4_post_sync_window_v2"}:
            raise ContractViolation("unsupported post_sync_window_policy")
        if self.post_sync_reservation_per_agent < 0:
            raise ContractViolation("post_sync_reservation_per_agent must be non-negative")
        if self.post_sync_window_policy is None and self.post_sync_reservation_per_agent:
            raise ContractViolation("post-sync reservation requires a post-sync window policy")
        if self.team_finalization_reserve < 0 or self.team_finalization_reserve > self.hard_team_call_permits:
            raise ContractViolation("team_finalization_reserve must be within the hard team budget")
        if self.reserved_final_synthesis_permits < 0:
            raise ContractViolation("reserved final synthesis permits must be non-negative")
        if self.completion_generation not in {None, "completion_v2_team", "completion_v3", "mixed_v2_v3"}:
            raise ContractViolation("unsupported completion_generation")
        if self.prompt_profile not in {
            None,
            "repository_v1",
            "repository_v1_t4_board_bootstrap",
            "repository_v1_t4_task_lifecycle_v2",
            "repository_v1_t4_nonoverlap_v1",
            "repository_v1_t4_sequenced_bootstrap_v1",
            "repository_v1_t4_result_sync_v1",
            "repository_v1_t4_result_inspection_prompt_v1",
            "repository_v1_t4_post_sync_inspection_v2",
            "repository_v1_t4_post_sync_relevance_v1",
            "repository_v1_t4_post_sync_verification_permission_v1",
            "repository_v1_t4_post_sync_window_v1",
            "repository_v1_t4_post_sync_window_v2",
        }:
            raise ContractViolation("unsupported prompt_profile")
        if self.contract_id == "n4_flowise_completion_calibration_v2":
            if self.completion_generation != "completion_v2_team":
                raise ContractViolation("team calibration requires completion_generation=completion_v2_team")
            if self.completion_policy != "convergent_v2" or self.team_completion_policy != "all_agents_terminal_v1":
                raise ContractViolation("team calibration freezes convergent_v2 and all_agents_terminal_v1")
            if self.team_finalization_policy != family.team_finalization_policy or self.team_finalization_reserve != family.team_finalization_reserve:
                raise ContractViolation("team calibration freezes team_remaining_permits_v1 with reserve=32")
            if self.conditions != N4_CONDITIONS:
                raise ContractViolation("team calibration excludes M4")
        elif self.contract_id == "t4_flowise_completion_budget_diagnostic_v1":
            if self.completion_generation != "completion_v2_team":
                raise ContractViolation("T4 budget diagnostic requires completion_generation=completion_v2_team")
            if self.completion_policy != "convergent_v2" or self.team_completion_policy != "all_agents_terminal_v1":
                raise ContractViolation("T4 budget diagnostic freezes convergent_v2 and all_agents_terminal_v1")
            if self.team_finalization_policy != family.team_finalization_policy or self.team_finalization_reserve != 32:
                raise ContractViolation("T4 budget diagnostic freezes team_remaining_permits_v1 with reserve=32")
            if self.conditions != T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS:
                raise ContractViolation("T4 budget diagnostic contains T4 only")
        elif self.contract_id == "t4_flowise_board_bootstrap_adoption_v1":
            if self.completion_generation != "completion_v2_team":
                raise ContractViolation("T4 board bootstrap requires completion_generation=completion_v2_team")
            if self.completion_policy != "convergent_v2" or self.team_completion_policy != "all_agents_terminal_v1":
                raise ContractViolation("T4 board bootstrap freezes convergent_v2 and all_agents_terminal_v1")
            if self.team_finalization_policy != family.team_finalization_policy or self.team_finalization_reserve != 32:
                raise ContractViolation("T4 board bootstrap freezes team_remaining_permits_v1 with reserve=32")
            if self.conditions != T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS:
                raise ContractViolation("T4 board bootstrap contains T4 only")
            if self.prompt_profile != "repository_v1_t4_board_bootstrap":
                raise ContractViolation("T4 board bootstrap requires its versioned prompt profile")
        elif self.contract_id == "t4_flowise_task_lifecycle_v2":
            if self.completion_generation != "completion_v2_team":
                raise ContractViolation("T4 task lifecycle requires completion_generation=completion_v2_team")
            if self.completion_policy != "convergent_v2" or self.team_completion_policy != "all_agents_terminal_v1":
                raise ContractViolation("T4 task lifecycle freezes convergent_v2 and all_agents_terminal_v1")
            if self.team_finalization_policy != family.team_finalization_policy or self.team_finalization_reserve != 32:
                raise ContractViolation("T4 task lifecycle freezes team_remaining_permits_v1 with reserve=32")
            if self.conditions != T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS:
                raise ContractViolation("T4 task lifecycle contains T4 only")
            if self.prompt_profile != "repository_v1_t4_task_lifecycle_v2":
                raise ContractViolation("T4 task lifecycle requires its versioned prompt profile")
        elif self.contract_id == "t4_flowise_nonoverlap_v1":
            if self.completion_generation != "completion_v2_team":
                raise ContractViolation("T4 nonoverlap requires completion_generation=completion_v2_team")
            if self.completion_policy != "convergent_v2" or self.team_completion_policy != "all_agents_terminal_v1":
                raise ContractViolation("T4 nonoverlap freezes convergent_v2 and all_agents_terminal_v1")
            if self.team_finalization_policy != family.team_finalization_policy or self.team_finalization_reserve != 32:
                raise ContractViolation("T4 nonoverlap freezes team_remaining_permits_v1 with reserve=32")
            if self.conditions != T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS:
                raise ContractViolation("T4 nonoverlap contains T4 only")
            if self.prompt_profile != "repository_v1_t4_nonoverlap_v1":
                raise ContractViolation("T4 nonoverlap requires its versioned prompt profile")
        elif self.contract_id == "t4_flowise_sequenced_bootstrap_v1":
            if self.completion_generation != "completion_v2_team":
                raise ContractViolation("T4 sequenced bootstrap requires completion_generation=completion_v2_team")
            if self.completion_policy != "convergent_v2" or self.team_completion_policy != "all_agents_terminal_v1":
                raise ContractViolation("T4 sequenced bootstrap freezes convergent_v2 and all_agents_terminal_v1")
            if self.team_finalization_policy != family.team_finalization_policy or self.team_finalization_reserve != 32:
                raise ContractViolation("T4 sequenced bootstrap freezes team_remaining_permits_v1 with reserve=32")
            if self.task_board_sequencing_policy != family.task_board_sequencing_policy:
                raise ContractViolation("T4 sequenced bootstrap requires initialization_lease_v1")
            if self.conditions != T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS:
                raise ContractViolation("T4 sequenced bootstrap contains T4 only")
            if self.prompt_profile != "repository_v1_t4_sequenced_bootstrap_v1":
                raise ContractViolation("T4 sequenced bootstrap requires its versioned prompt profile")
        elif self.contract_id == "t4_flowise_sequenced_bootstrap_task_closure_v1":
            if self.completion_generation != "completion_v2_team":
                raise ContractViolation("T4 sequenced task-closure diagnostic requires completion_generation=completion_v2_team")
            if self.completion_policy != "convergent_v2" or self.team_completion_policy != "all_agents_terminal_v1":
                raise ContractViolation("T4 sequenced task-closure diagnostic freezes convergent_v2 and all_agents_terminal_v1")
            if self.team_finalization_policy != family.team_finalization_policy or self.team_finalization_reserve != 32:
                raise ContractViolation("T4 sequenced task-closure diagnostic freezes team_remaining_permits_v1 with reserve=32")
            if self.task_board_sequencing_policy != family.task_board_sequencing_policy:
                raise ContractViolation("T4 sequenced task-closure diagnostic requires initialization_lease_v1")
            if self.task_closure_policy != family.task_closure_policy:
                raise ContractViolation("T4 sequenced task-closure diagnostic requires task_closure_gate_v1")
            if self.conditions != T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS:
                raise ContractViolation("T4 sequenced task-closure diagnostic contains T4 only")
            if self.prompt_profile != "repository_v1_t4_sequenced_bootstrap_v1":
                raise ContractViolation("T4 sequenced task-closure diagnostic preserves the sequenced bootstrap prompt")
        elif self.contract_id == "t4_flowise_result_sync_v1":
            if self.completion_generation != "completion_v2_team":
                raise ContractViolation("T4 result-sync diagnostic requires completion_generation=completion_v2_team")
            if self.completion_policy != "convergent_v2" or self.team_completion_policy != "all_agents_terminal_v1":
                raise ContractViolation("T4 result-sync diagnostic freezes convergent_v2 and all_agents_terminal_v1")
            if self.team_finalization_policy != family.team_finalization_policy or self.team_finalization_reserve != 32:
                raise ContractViolation("T4 result-sync diagnostic freezes team_remaining_permits_v1 with reserve=32")
            if self.task_board_sequencing_policy != family.task_board_sequencing_policy:
                raise ContractViolation("T4 result-sync diagnostic requires initialization_lease_v1")
            if self.task_closure_policy != family.task_closure_policy:
                raise ContractViolation("T4 result-sync diagnostic requires task_closure_gate_v1")
            if self.result_sync_policy != family.result_sync_policy:
                raise ContractViolation("T4 result-sync diagnostic requires result_sync_v1")
            if self.conditions != T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS:
                raise ContractViolation("T4 result-sync diagnostic contains T4 only")
            if self.prompt_profile != "repository_v1_t4_result_sync_v1":
                raise ContractViolation("T4 result-sync diagnostic requires its versioned prompt profile")
        elif self.contract_id == "t4_flowise_result_inspection_prompt_v1":
            if self.completion_generation != "completion_v2_team":
                raise ContractViolation("T4 result-inspection diagnostic requires completion_generation=completion_v2_team")
            if self.completion_policy != "convergent_v2" or self.team_completion_policy != "all_agents_terminal_v1":
                raise ContractViolation("T4 result-inspection diagnostic freezes convergent_v2 and all_agents_terminal_v1")
            if self.team_finalization_policy != family.team_finalization_policy or self.team_finalization_reserve != 32:
                raise ContractViolation("T4 result-inspection diagnostic freezes team_remaining_permits_v1 with reserve=32")
            if self.task_board_sequencing_policy != family.task_board_sequencing_policy:
                raise ContractViolation("T4 result-inspection diagnostic requires initialization_lease_v1")
            if self.task_closure_policy != family.task_closure_policy:
                raise ContractViolation("T4 result-inspection diagnostic requires task_closure_gate_v1")
            if self.result_sync_policy != family.result_sync_policy:
                raise ContractViolation("T4 result-inspection diagnostic requires result_sync_v1")
            if self.conditions != T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS:
                raise ContractViolation("T4 result-inspection diagnostic contains T4 only")
            if self.prompt_profile != "repository_v1_t4_result_inspection_prompt_v1":
                raise ContractViolation("T4 result-inspection diagnostic requires its versioned prompt profile")
        elif self.contract_id == "t4_flowise_post_sync_inspection_v2":
            if self.completion_generation != "completion_v2_team":
                raise ContractViolation("T4 post-sync inspection requires completion_generation=completion_v2_team")
            if self.completion_policy != "convergent_v2" or self.team_completion_policy != "all_agents_terminal_v1":
                raise ContractViolation("T4 post-sync inspection freezes completion policies")
            if self.team_finalization_policy != family.team_finalization_policy or self.team_finalization_reserve != 32:
                raise ContractViolation("T4 post-sync inspection freezes finalization reserve=32")
            if self.task_board_sequencing_policy != family.task_board_sequencing_policy or self.task_closure_policy != family.task_closure_policy:
                raise ContractViolation("T4 post-sync inspection freezes sequencing and task closure")
            if self.result_sync_policy != family.result_sync_policy or self.conditions != T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS:
                raise ContractViolation("T4 post-sync inspection requires result_sync_v1 and T4 only")
            if self.prompt_profile != "repository_v1_t4_post_sync_inspection_v2":
                raise ContractViolation("T4 post-sync inspection requires its versioned prompt profile")
        elif self.contract_id == "t4_flowise_post_sync_relevance_v1":
            if self.completion_generation != "completion_v2_team":
                raise ContractViolation("T4 post-sync relevance requires completion_generation=completion_v2_team")
            if self.completion_policy != "convergent_v2" or self.team_completion_policy != "all_agents_terminal_v1":
                raise ContractViolation("T4 post-sync relevance freezes completion policies")
            if self.team_finalization_policy != family.team_finalization_policy or self.team_finalization_reserve != 32:
                raise ContractViolation("T4 post-sync relevance freezes finalization reserve=32")
            if self.task_board_sequencing_policy != family.task_board_sequencing_policy or self.task_closure_policy != family.task_closure_policy:
                raise ContractViolation("T4 post-sync relevance freezes sequencing and task closure")
            if self.result_sync_policy != family.result_sync_policy or self.conditions != T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS:
                raise ContractViolation("T4 post-sync relevance requires result_sync_v1 and T4 only")
            if self.prompt_profile != "repository_v1_t4_post_sync_relevance_v1":
                raise ContractViolation("T4 post-sync relevance requires its versioned prompt profile")
        elif self.contract_id == "t4_flowise_post_sync_verification_permission_v1":
            if self.completion_generation != "completion_v2_team":
                raise ContractViolation("T4 post-sync verification permission requires completion_generation=completion_v2_team")
            if self.completion_policy != "convergent_v2" or self.team_completion_policy != "all_agents_terminal_v1":
                raise ContractViolation("T4 post-sync verification permission freezes completion policies")
            if self.team_finalization_policy != family.team_finalization_policy or self.team_finalization_reserve != 32:
                raise ContractViolation("T4 post-sync verification permission freezes finalization reserve=32")
            if self.task_board_sequencing_policy != family.task_board_sequencing_policy or self.task_closure_policy != family.task_closure_policy:
                raise ContractViolation("T4 post-sync verification permission freezes sequencing and task closure")
            if self.result_sync_policy != family.result_sync_policy or self.conditions != T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS:
                raise ContractViolation("T4 post-sync verification permission requires result_sync_v1 and T4 only")
            if self.prompt_profile != "repository_v1_t4_post_sync_verification_permission_v1":
                raise ContractViolation("T4 post-sync verification permission requires its versioned prompt profile")
        elif self.contract_id == "t4_flowise_post_sync_window_v1":
            if self.completion_generation != "completion_v2_team":
                raise ContractViolation("T4 post-sync window requires completion_generation=completion_v2_team")
            if self.completion_policy != "convergent_v2" or self.team_completion_policy != "all_agents_terminal_v1":
                raise ContractViolation("T4 post-sync window freezes completion policies")
            if self.team_finalization_policy != family.team_finalization_policy or self.team_finalization_reserve != 32:
                raise ContractViolation("T4 post-sync window freezes finalization reserve=32")
            if self.task_board_sequencing_policy != family.task_board_sequencing_policy or self.task_closure_policy != family.task_closure_policy:
                raise ContractViolation("T4 post-sync window freezes sequencing and task closure")
            if self.result_sync_policy != family.result_sync_policy or self.conditions != T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS:
                raise ContractViolation("T4 post-sync window requires result_sync_v1 and T4 only")
            if self.post_sync_window_policy != family.post_sync_window_policy or self.post_sync_reservation_per_agent != family.post_sync_reservation_per_agent:
                raise ContractViolation("T4 post-sync window requires its frozen reservation policy")
            if self.prompt_profile != "repository_v1_t4_post_sync_window_v1":
                raise ContractViolation("T4 post-sync window requires its versioned prompt profile")
        elif self.contract_id == "t4_flowise_post_sync_window_v2":
            if self.completion_generation != "completion_v2_team":
                raise ContractViolation("T4 post-sync window v2 requires completion_generation=completion_v2_team")
            if self.completion_policy != "convergent_v2" or self.team_completion_policy != "all_agents_terminal_v1":
                raise ContractViolation("T4 post-sync window v2 freezes completion policies")
            if self.team_finalization_policy != family.team_finalization_policy or self.team_finalization_reserve != 32:
                raise ContractViolation("T4 post-sync window v2 freezes finalization reserve=32")
            if self.task_board_sequencing_policy != family.task_board_sequencing_policy or self.task_closure_policy != family.task_closure_policy:
                raise ContractViolation("T4 post-sync window v2 freezes sequencing and task closure")
            if self.result_sync_policy != family.result_sync_policy or self.conditions != T4_COMPLETION_BUDGET_DIAGNOSTIC_CONDITIONS:
                raise ContractViolation("T4 post-sync window v2 requires result_sync_v1 and T4 only")
            if self.post_sync_window_policy != family.post_sync_window_policy or self.post_sync_reservation_per_agent != family.post_sync_reservation_per_agent:
                raise ContractViolation("T4 post-sync window v2 requires its frozen reservation policy")
            if self.prompt_profile != "repository_v1_t4_post_sync_window_v2":
                raise ContractViolation("T4 post-sync window v2 requires its versioned prompt profile")
        elif self.contract_id == "n4m_flowise_completion_v3":
            if self.completion_generation != "completion_v3" or self.reserved_final_synthesis_permits != 1:
                raise ContractViolation("completion_v3 contract requires exactly one reserved synthesis permit")
            if self.team_completion_policy not in {None, "team_completion_v3"}:
                raise ContractViolation("completion_v3 contract requires team_completion_v3")
            if self.team_finalization_deadline_seconds != family.team_finalization_deadline_seconds:
                raise ContractViolation("completion_v3 contract requires team_finalization_deadline_seconds=60")
        elif self.contract_id == "n4m_flowise_calibration_v1":
            self._validate_mixed_calibration_runtime()
        elif self.reserved_final_synthesis_permits or self.completion_generation or self.team_finalization_deadline_seconds is not None or self.condition_runtime is not None or self.team_finalization_policy is not None or self.team_finalization_reserve:
            raise ContractViolation("reserved final synthesis is only enabled by an explicit completion_v3 contract")

    def _validate_mixed_calibration_runtime(self) -> None:
        if self.completion_generation != "mixed_v2_v3":
            raise ContractViolation("mixed calibration requires completion_generation=mixed_v2_v3")
        if self.team_completion_policy is not None:
            raise ContractViolation("mixed calibration records team policy per condition")
        if self.reserved_final_synthesis_permits or self.team_finalization_deadline_seconds is not None:
            raise ContractViolation("mixed calibration records M4 finalization fields per condition")
        expected_ids = {condition.id for condition in N4M_FLOWISE_CONDITIONS}
        if self.condition_runtime is None or set(self.condition_runtime) != expected_ids:
            raise ContractViolation("mixed calibration requires one runtime mapping for every condition")
        for condition in N4M_FLOWISE_CONDITIONS:
            spec = self.condition_runtime[condition.id]
            if not isinstance(spec, dict):
                raise ContractViolation(f"condition runtime for {condition.id} must be an object")
            common = {
                "completion_policy": "convergent_v2",
                "max_provider_retries": 1,
                "stop_labels": [
                    "submitted",
                    "budget_exhausted",
                    "max_steps",
                    "model_format_failure",
                    "timeout",
                    "timed_out",
                    "error",
                    "cancelled",
                ],
            }
            for key, expected in common.items():
                if spec.get(key) != expected:
                    raise ContractViolation(f"{condition.id} requires {key}={expected!r}")
            if condition.id == "M4":
                expected = {
                    "completion_generation": "completion_v3",
                    "team_completion_policy": "team_completion_v3",
                    "reserved_final_synthesis_permits": 1,
                    "team_finalization_deadline_seconds": 60,
                    "submission_owner": "manager_agent_001",
                    "merge_semantics": "manager_final_synthesis_payload_with_submitted_by_then_evaluator_fingerprint_dedup",
                }
            else:
                expected = {
                    "completion_generation": "completion_v2",
                    "team_completion_policy": "all_agents_terminal_v1",
                    "reserved_final_synthesis_permits": 0,
                    "team_finalization_deadline_seconds": None,
                    "submission_owner": "participating_agents",
                    "merge_semantics": "deterministic_concat_with_submitted_by_then_evaluator_fingerprint_dedup",
                }
            for key, value in expected.items():
                if spec.get(key) != value:
                    raise ContractViolation(f"{condition.id} requires {key}={value!r}")
            if set(spec) - set(common) - set(expected):
                raise ContractViolation(f"unexpected mixed calibration fields for {condition.id}")

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
            "final_synthesis_retries": self.final_synthesis_retries,
            "conditions": [condition.as_dict() for condition in self.conditions],
            "completion_policy": self.completion_policy,
            "team_completion_policy": self.team_completion_policy,
            "team_finalization_policy": self.team_finalization_policy,
            "team_finalization_reserve": self.team_finalization_reserve,
            "task_board_sequencing_policy": self.task_board_sequencing_policy,
            "task_closure_policy": self.task_closure_policy,
            "result_sync_policy": self.result_sync_policy,
            "post_sync_window_policy": self.post_sync_window_policy,
            "post_sync_reservation_per_agent": self.post_sync_reservation_per_agent,
            "reserved_final_synthesis_permits": self.reserved_final_synthesis_permits,
            "completion_generation": self.completion_generation,
            "team_finalization_deadline_seconds": self.team_finalization_deadline_seconds,
            **({"condition_runtime": self.condition_runtime} if self.condition_runtime is not None else {}),
            **({"prompt_profile": self.prompt_profile} if self.prompt_profile is not None else {}),
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
            final_synthesis_retries=int(retry.get("final_synthesis_retries", 0) or 0),
            completion_policy=(str(raw["completion_policy"]) if raw.get("completion_policy") is not None else None),
            team_completion_policy=(
                str(raw["team_completion_policy"])
                if raw.get("team_completion_policy") is not None
                else None
            ),
            team_finalization_policy=(
                str(raw["team_finalization_policy"])
                if raw.get("team_finalization_policy") is not None
                else None
            ),
            team_finalization_reserve=int(raw.get("team_finalization_reserve", 0) or 0),
            reserved_final_synthesis_permits=int(budget.get("reserved_final_synthesis_permits", 0) or 0),
            completion_generation=(
                str(raw["completion_generation"]) if raw.get("completion_generation") is not None else None
            ),
            team_finalization_deadline_seconds=_optional_int(raw.get("team_finalization_deadline_seconds")),
            condition_runtime=(
                {str(key): dict(value) for key, value in raw["condition_runtime"].items()}
                if isinstance(raw.get("condition_runtime"), dict)
                else None
            ),
            prompt_profile=(str(raw["prompt_profile"]) if raw.get("prompt_profile") is not None else None),
            task_board_sequencing_policy=(
                str(raw["task_board_sequencing_policy"])
                if raw.get("task_board_sequencing_policy") is not None
                else None
            ),
            task_closure_policy=(str(raw["task_closure_policy"]) if raw.get("task_closure_policy") is not None else None),
            result_sync_policy=(str(raw["result_sync_policy"]) if raw.get("result_sync_policy") is not None else None),
            post_sync_window_policy=(str(raw["post_sync_window_policy"]) if raw.get("post_sync_window_policy") is not None else None),
            post_sync_reservation_per_agent=int(budget.get("post_sync_reservation_per_agent", 0) or 0),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractViolation(f"invalid block config: {exc}") from exc
    config.validate()
    return config


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)
