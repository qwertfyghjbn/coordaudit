from __future__ import annotations

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, TYPE_CHECKING

from experiments.emergent_coordination.harness.completion_v3 import (
    COMPLETION_V3,
    TeamFinalizationCoordinator,
)

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
        if context.config.completion_generation == COMPLETION_V3:
            return self._run_completion_v3(context, manager, workers, worker_ids)
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

    def _run_completion_v3(self, context: "RunContext", manager: Any, workers: dict[str, Any], worker_ids: list[str]) -> list[dict[str, Any]]:
        coordinator = TeamFinalizationCoordinator(
            worker_ids=worker_ids,
            finalization_deadline_seconds=context.config.team_finalization_deadline_seconds or 60,
        )
        board = context.manager_board
        # Normal work owns every permit except the explicitly reserved one.
        while not manager._finished and context.budget.remaining_permits != 1:
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
            manager.advance()

        states = {
            agent_id: _worker_terminal_state(workers[agent_id])
            for agent_id in worker_ids
        }
        context.event_log.emit(
            "team_finalization_started",
            payload={"generation": COMPLETION_V3, "reserved_final_synthesis_permits": 1, "worker_states": states},
        )
        coordinator.enter_barrier(states)
        for agent_id, worker in workers.items():
            if not worker._finished or worker._stop_reason == "waiting_for_assignment":
                worker.terminalize("cancelled")
            context.event_log.emit(
                "worker_terminalized",
                agent_id=agent_id,
                payload={"state": coordinator.worker_states[agent_id], "reason": "team_finalization_barrier"},
            )
        board.drain_reports()
        board_snapshot = board.final_snapshot(completion_reason="completion_v3_barrier")
        for report in board_snapshot["reports"]:
            coordinator.transport.produce(
                report["id"], report["worker_id"], report.get("result", ""), report.get("evidence_refs", [])
            )
            coordinator.transport.queue(report["id"])
        snapshot = coordinator.drain_and_freeze(
            unresolved_tasks=board_snapshot["unresolved_tasks"],
            reason="completion_v3_barrier",
        )
        snapshot_payload = snapshot.as_payload()
        snapshot_payload["reports"] = board_snapshot["reports"]
        context.event_log.emit("final_snapshot_ready", payload=snapshot_payload)

        final_ok = False
        deadline_exceeded = coordinator.deadline_exceeded()
        if deadline_exceeded:
            context.event_log.emit(
                "team_finalization_deadline_exceeded",
                payload={
                    "generation": COMPLETION_V3,
                    "deadline_seconds": coordinator.finalization_deadline_seconds,
                    "state": coordinator.state.value,
                },
                outcome="forced_unfinished",
            )
            outcome = coordinator.finish_deadline()
            manager.terminalize("cancelled")
        elif context.budget.remaining_permits is not None and context.budget.remaining_permits >= 1:
            try:
                context.budget.authorize_final_synthesis(manager.agent_id)
                coordinator.begin_final_synthesis()
                report_ids = [report["id"] for report in board_snapshot["reports"]]
                result = manager.final_synthesis(
                    snapshot_payload,
                    on_request=lambda _request: (
                        coordinator.record_final_synthesis_request(),
                        board.mark_final_synthesis_visible(report_ids),
                    ),
                )
                final_ok = result.get("stop_reason") == "submitted"
                if final_ok:
                    adopted_evidence = {
                        ref
                        for finding in (result.get("findings") or {}).get("findings", [])
                        for ref in finding.get("evidence_refs", [])
                    }
                    for report in board_snapshot["reports"]:
                        if adopted_evidence & set(report.get("evidence_refs", [])):
                            board.adopt_report(report["id"])
            except Exception as exc:  # bounded failure is an explicit outcome
                context.event_log.emit("error", agent_id=manager.agent_id, payload={"error": str(exc), "type": type(exc).__name__})
            # Barrier cancellation is a deterministic lifecycle close, not a
            # worker failure.  Only provider/task failure or timeout changes
            # the team outcome taxonomy.
            worker_failure = any(state in {"failed", "timed_out"} for state in coordinator.worker_states.values())
            outcome = coordinator.finish(submitted=final_ok, worker_failure=worker_failure)
        else:
            outcome = coordinator.finish_deadline()
        context.team_completion_v3_result = {
            "policy": "team_completion_v3",
            "classification": outcome,
            "state": coordinator.state.value,
            "snapshot": snapshot_payload,
            "reserved_final_synthesis_permits": 1,
        }
        context.event_log.emit("team_completion", payload=context.team_completion_v3_result, outcome=outcome, budget_progress=context.budget.snapshot())
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


def _worker_terminal_state(worker: Any) -> str:
    reason = worker._stop_reason if worker._finished else "running"
    if reason in {"submitted", "completed", "done"}:
        return "done"
    if reason in {"timeout", "timed_out"}:
        return "timed_out"
    if reason in {"error", "failed"}:
        return "failed"
    if reason in {"waiting_for_assignment", "cancelled"}:
        return reason
    return "running"
