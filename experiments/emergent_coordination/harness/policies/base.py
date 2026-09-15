from __future__ import annotations

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from experiments.emergent_coordination.harness.runner import RunContext


class CoordinationPolicy(ABC):
    """Mode-specific wiring around a shared AgentRunner.

    Future modes (manager_worker, fixed_roles, fixed_graph) should implement
    this interface rather than forking the runner.
    """

    name: str
    enable_shared: bool = False
    enable_board: bool = False

    @abstractmethod
    def run_agents(self, context: "RunContext") -> list[dict[str, Any]]:
        raise NotImplementedError


class SequentialPolicy(CoordinationPolicy):
    name = "single"
    enable_shared = False
    enable_board = False

    def run_agents(self, context: "RunContext") -> list[dict[str, Any]]:
        return [context.run_one(agent_id) for agent_id in context.agent_ids]


class ParallelPolicy(CoordinationPolicy):
    name = "parallel"
    enable_shared = False
    enable_board = False

    def run_agents(self, context: "RunContext") -> list[dict[str, Any]]:
        return _run_parallel(context)


class RawBlackboardPolicy(CoordinationPolicy):
    name = "raw_blackboard"
    enable_shared = True
    enable_board = False

    def run_agents(self, context: "RunContext") -> list[dict[str, Any]]:
        return _run_parallel(context)


class StructuredTeamPolicy(CoordinationPolicy):
    name = "structured_team"
    enable_shared = False
    enable_board = True

    def run_agents(self, context: "RunContext") -> list[dict[str, Any]]:
        return _run_parallel(context)


POLICIES: dict[str, CoordinationPolicy] = {
    "single": SequentialPolicy(),
    "parallel": ParallelPolicy(),
    "raw_blackboard": RawBlackboardPolicy(),
    "structured_team": StructuredTeamPolicy(),
}


def get_policy(mode: str) -> CoordinationPolicy:
    if mode not in POLICIES:
        raise ValueError(f"unsupported mode: {mode}")
    return POLICIES[mode]


def _run_parallel(context: "RunContext") -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=len(context.agent_ids)) as pool:
        futures = {pool.submit(context.run_one, agent_id): agent_id for agent_id in context.agent_ids}
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda item: item["agent_id"])
    return results
