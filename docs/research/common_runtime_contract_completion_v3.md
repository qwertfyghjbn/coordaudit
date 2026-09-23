# `completion_v3` team completion contract

> 状态勘误（2026-09-20）：本文第 13、15 节记录的是 2026-09-19 live 前 gate 与 M4 blocker audit。当日之后用户明确授权并执行了 `n4m-flowise-calibration-v1-96p` 五条件 live calibration；实际 trace review 见 [`flowise-3.1.3-repository-v1-n4m-calibration-trace-review-20260920.md`](../releases/flowise-3.1.3-repository-v1-n4m-calibration-trace-review-20260920.md)。该运行没有把 unresolved design blocker 追认为已解决，也没有产生 coordination-effect 结论；M4 的 worker identity mismatch 与 S/P/B/T 的 team-budget completion 缺口仍然是后续重跑前置条件。

状态：新世代、显式 opt-in；`completion_v1`/`completion_v2`、既有 manifest、replay 与历史结果不变。

## 审计结论

现有 `completion_v2` 的 `FINALIZATION_RESERVE=8` 是每个 Agent 的 step/tool gate，不是 team-owned permit。M4 的 manager 在自身第 5 步进入 hard finalization，`manager_list_tasks` 被拒绝；worker report 可以已 produced/queued，但只有 manager 再次 list 才能产生 `manager_report_observed`。当前旧 runtime 没有独立的 `model-visible`/`adopted` event：已知 M4 tape 将 manager 第 4 步实际进入 input 的 report 1/2 视为 model-visible，report 3 未进入；这两个语义不能由 no-call drain retroactively 改写。manager 完成后 worker 才被 `waiting_for_assignment` 收尾，run 末端的 `all_agents_terminal_v1` 只被动汇总，team outcome 保持 forced/unfinished。

## 冻结语义

* `hard_team_call_permits = N`，`reserved_final_synthesis_permits = 1`，`normal_work_permits = N - 1`；reserved permit 包含在 N 内。
* `BudgetTracker` 以显式 `call_kind` 和 `authorize_final_synthesis(manager)` 区分 normal/final call。normal call 在剩余 permits 小于等于 reserve 时被拒绝；barrier 提前停止 normal work 时，reserved permit 仍可在剩余预算中被授权。final synthesis 只能授权一次并消费唯一 permit。普通 call 沿用 matched contract 的一次 harness retry；final synthesis 不 retry。provider timeout/error 仍消费 permit。
* 状态为 `NORMAL_WORK → TEAM_FINALIZING → FINAL_SNAPSHOT_READY → MANAGER_FINAL_SYNTHESIS → TEAM_TERMINAL`；不能形成 snapshot 或 final synthesis 时为 `FORCED_UNFINISHED`。
* barrier 后不创建 assignment、不启动普通 reasoning。`waiting_for_assignment`、未完成 running assignment 在有限 barrier 上 deterministic 变为 `cancelled`；已有 `done`、`failed`、`timed_out` 保持 terminal。
* report transport 只允许 `produced → queued → delivered`。drain 不产生 model-visible/adopted。snapshot 冻结后 late report 记录为 late，不修改 snapshot。
* final synthesis 是 exactly-once 的真实 manager model call，输入含 immutable snapshot；snapshot 中实际进入该 request 的 report 记录为 model-visible。当前实现把 manager final submit payload 中显式引用 report evidence 的 report 记录为 adopted；没有被引用的 visible report 保持 ignored/rejected，不是 lifecycle completion 前提。
* team taxonomy：`completed`、`completed_with_worker_failure`、`forced_unfinished`。完成不等于所有 worker 成功。

机械 invariant：

```text
normal_work_permits + reserved_final_synthesis_permits == hard_team_call_permits
attempted_model_calls <= hard_team_call_permits
drain != model-visible
model-visible != adopted
 final_synthesis_calls <= 1
```

## Completion invariant

在当前 v3 runner 中，`completed` 或 `completed_with_worker_failure` 只在以下条件同时成立时发出：manager 的 reserved final synthesis 已提交最终结果；每个 worker 都处于 `done`、`failed`、`timed_out` 或 `cancelled`；snapshot 已冻结且 transport 没有被禁止的 in-flight report；final request 已实际包含该 snapshot；permit ledger 没有超过 hard budget。`model-visible` 不要求 `adopted`，也不要求所有 worker 成功。若 final synthesis 没有提交结果，结果为 `forced_unfinished`。

## 与旧 finalization reserve 的关系

旧 `FINALIZATION_RESERVE=8` 仍只服务 v1/v2 的 per-agent finalization window；它不拥有 team permit，也不改变 worker lifecycle。v3 的 `reserved_final_synthesis_permits=1` 是独立字段，只有显式传入 `completion_generation="completion_v3"` 且声明该字段的 contract 才启用。`n4m_flowise_completion_v3.json` 是当前 M4/manager-worker 的 opt-in contract；其 family 记录 S/P/B/T/M 的 block shape，不表示 S/P/B/T 已经切换到 v3。该 contract 固定 `max_output_tokens=4096` 与 `team_finalization_deadline_seconds=60`。

## 当前实现范围与未冻结项

当前 runner 明确只允许 `completion_v3` 由 `manager_worker` 使用；S/P/B/T 继续使用旧 generation。这样保持历史行为不变，但不能把包含 S/P/B/T/M 的 family manifest 解读为“所有条件已经共享 v3 lifecycle”。若要将 v3 扩展到 S/P/B/T，必须另行定义无 manager 的 final-synthesis owner、condition-scoped snapshot 输入和新的 matched-block contract。

v3 复用既有 hard permit、provider timeout、assignment/runtime bound，并增加独立的 `team_finalization_deadline_seconds=60`。计时从 `TEAM_FINALIZING` 进入时开始，覆盖 bounded drain 与 final synthesis admission；不得延长 global wall-clock。deadline 到期前未能授权 final synthesis 时，产生 `team_finalization_deadline_exceeded`，结果为 `forced_unfinished`；provider/runtime watchdog 或 ledger/reconciliation 破坏仍属于 `infrastructure_invalid`。该 deadline 不产生额外 permit 或 grace period。

## M4 mock replay 口径

旧世代继续复现 gate blocker：manager 第 4 步 input 中的 report 1/2 保持可见、report 3 未进入 input，worker 收尾为 `waiting_for_assignment`，且没有 retroactive adoption。新世代停止 normal work，关闭 waiting/running worker lifecycle，drain reports，冻结 snapshot，manager 用唯一 reserved call 读取全部 delivered reports 并提交。barrier cancellation 本身不是 worker failure；真实 `failed`/`timed_out` worker 才会得到 `completed_with_worker_failure`。manager 不采用某条 visible report 也不使 lifecycle 失败。

实现与测试均不调用 live provider。
