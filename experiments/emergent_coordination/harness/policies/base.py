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
    enable_manager_board: bool = False

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


class ManagerWorkerPolicy(CoordinationPolicy):
    """Single-manager, single-layer star with task-triggered worker turns."""

    name = "manager_worker"
    enable_manager_board = True

    def run_agents(self, context: "RunContext") -> list[dict[str, Any]]:
        if context.config.agent_count < 2:
            raise ValueError("manager_worker mode requires one manager and at least one worker")
        manager_id, *worker_ids = context.agent_ids
        manager = context.make_session(manager_id, role="manager")
        workers = {agent_id: context.make_session(agent_id, role="worker") for agent_id in worker_ids}
        board = context.manager_board
        if board is None:  # defensive: policy contract should make this unreachable
            raise RuntimeError("manager-worker board was not initialized")

        # The manager receives the first turn. Afterwards it is resumed only
        # when it must make a new allocation decision or reports are ready.
        manager.advance()
        while not manager._finished:
            ready = [agent_id for agent_id in board.ready_workers() if not workers[agent_id]._finished]
            if ready:
                for agent_id in ready:
                    workers[agent_id].advance()
                if board.has_unobserved_reports():
                    manager.advance()
                continue
            if board.has_unobserved_reports():
                manager.advance()
                continue
            # No worker can make progress. The manager needs another turn to
            # assign work, inspect its latest tool result, or finish.
            manager.advance()

        for worker in workers.values():
            if not worker._finished:
                worker.stop_waiting()
        return [manager.result(), *(workers[agent_id].result() for agent_id in worker_ids)]


POLICIES: dict[str, CoordinationPolicy] = {
    "single": SequentialPolicy(),
    "parallel": ParallelPolicy(),
    "raw_blackboard": RawBlackboardPolicy(),
    "structured_team": StructuredTeamPolicy(),
    "manager_worker": ManagerWorkerPolicy(),
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
