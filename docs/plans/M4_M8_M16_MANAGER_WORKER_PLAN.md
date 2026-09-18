# M4/M8/M16 manager-worker 条件规划

> 状态注记（2026-09-17）：`manager_worker` harness 已实现（单 manager + N-1 workers），mock M4 全链路、角色隔离、evidence-chain 与预算耗尽测试通过，M16 mock 冒烟无死锁。本文件冻结 M 系列的实验定位、规模阶梯与 M16 的 manager 瓶颈诊断口径；`analyze_run` 的 M 专属指标段尚未实现，见 §6。

## 1. 定位

`M` 测试的是 **centralized task allocation**：一个 manager 拥有排他的分派/取消/重派权限，workers 只向 manager 回报与请求工作。它不是 star communication topology 实验——`N4_PILOT_PLAN.md` §7.8 的约束继续有效：M 是 centralized-control baseline，不得被表述或实现为 fixed-star topology experiment。

与既有条件的关系：

- `M − P`：中心化 task allocation 与 knowledge aggregation 的净效果（workers 独立并行 vs manager 分派）。
- `M − T`：typed task primitive 的自发使用 vs 该 primitive 被收归单一 manager 的排他控制。
- `M − B`：top-down star 状态板 vs bottom-up generic shared store。

## 2. 条件定义（实现语义）

- 一个 run 中 `agent_001` 是 manager，`agent_002..agent_N` 是 workers；manager 与 workers 共用同一 harness、模型入口与 target snapshot。
- **Role-restricted tool surfaces**：manager 暴露 `manager_create_task / manager_list_tasks / manager_cancel_task / manager_reassign_task`；worker 暴露 `worker_get_assignment / worker_report_task / worker_request_more`。两侧都不含 message、claim、broadcast 或 shared-store 工具；role 不匹配的调用在工具层被拒绝。
- **Board 能力边界**：`ManagerBoard` 是单层 star 状态。它刻意不提供 worker-to-worker lookup、broadcast、claim、delegation 或 mailbox；worker 只能看到自己的 assignment。每个 worker 同时最多持有一个 assigned task；只有 manager 可以创建、取消、重派。
- **调度语义**：manager 获得第一个 turn；此后 worker turn 由 assignment 触发（task-triggered），manager 在有未观察报告或需要新的分派决策时被恢复。manager 结束后，空闲 worker 以 `waiting_for_assignment` 收尾，不虚构模型格式失败。
- **Evidence chain**：manager 只能提交两类 evidence——自己 `read_file` 直接取得的，或经 `manager_list_tasks` 产生明确 `manager_report_observed` 事件的 worker 报告 evidence。未观察过的 worker evidence 引用会被 submission 校验拒绝。这与 ADR 0005 中 T 的 `task_result_observed` 语义对齐，不放宽、不新增通道。

## 3. 因果约束（与 S/P/B/T matched）

1. 同一 case（Agent-visible target、prompt profile、finding schema、evaluator）。
2. 同一模型配置与同一 base audit prompt；manager/worker 的角色指令只描述 coordination 职责，不得注入安全专家知识、审计 hint 或 ground truth 信息（manager prompt 增量仅限“分派/检查报告/决定剩余工作”）。
3. 同一 team-level budget：`hard_team_call_permits` 全局许可池（ADR 0002）。manager 是 N 个 slot 之一并计全局预算；`M16 = 1 manager + 15 workers`，不额外赠送第 17 个 aggregator slot。manager 的实际 permit/token 份额是 coordination outcome，不是预设配额。
4. hidden evaluator、ground truth 与 provenance 不进入 Agent mount、tool output 或 prompt。
5. M 的加入不得改变其他条件的工具面、prompt 或预算语义；M 与同 N 的 S/P/B/T 必须在同一个冻结 block contract 下运行。

## 4. 规模阶梯

| 条件 | 组成 | 用途 | 进入条件 |
|---|---|---|---|
| `M4` | 1 manager + 3 workers | 与既有 `S1/P4/B4/T4` 同 N 的 centralized-control baseline；`repository_pilot_v0` 的 5 个 work fronts 是下限约束 | 按 `N4_PILOT_PLAN.md` 不变：S/P/B/T block 已产生完整 trace，且 manager adapter 不携带专属审计知识/工具（已满足后者） |
| `M8` | 1 manager + 7 workers | 分派/重派与 fan-in 的初步 scaling 检查 | M4 matched block 机械指标（budget、lineage、reconcile）通过 |
| `M16` | 1 manager + 15 workers | 阶段一矩阵 `S1/P16/M16/R16/B16/T16` 的 M 成员；manager 瓶颈诊断点（§5） | M8 通过；case 具备 ≥ N 的 effective active-front count，且满足 condition-blind target selection |

约束：

- M8/M16 不得使用 `repository_pilot_v0`（fronts 不足，N=4 只是下限）。候选 case 必须按 `CONTEXT.md` 的 condition-blind target selection 冻结：不得因为某种 coordination mechanism 更容易获益而选仓。
- 每一档的 permits 数值由当次冻结 block contract 决定，M 与同 block 的 S/P/B/T/R 共享同一数值；不因 manager 角色调整。

## 5. M16 作为 manager 瓶颈诊断点

**假设**：随着 N 增大，manager 的串行决策循环（observe reports → decide → assign/reassign）与 15 个 worker 的报告 fan-in 会成为团队约束——manager 消耗的 permit 份额上升、worker idle 时间上升、worker 报告的 evidence 在最终 submission 中的保留率下降。M16 是该假设的首个有统计意义的观测点：fan-in 与分派负载在 M4/M8 下太弱，不足以区分“manager 瓶颈”与“work front 供给不足”。

**诊断指标**（继承 `N4_PILOT_PLAN.md` §7.8 并细化口径）：

| 指标 | 口径 |
|---|---|
| manager permit/token share | manager 获取的 permits 与 observed tokens 占团队总量的比例，按 M4/M8/M16 报告斜率 |
| worker idle / queue time | assignment 完成回报（`manager_worker_reported`）到该 worker 下一次被分派（`manager_task_assigned`）或 run 结束的间隔；从未获得第二个 task 的 worker 计入 idle |
| assignment→start latency | `manager_task_assigned` 到对应 worker `manager_assignment_observed` 的间隔 |
| reassignment 计数 | `manager_task_reassigned` 事件数及原因分布 |
| manager fan-in | 每次 manager turn 经 `manager_list_tasks` 新观察的 `manager_report_observed` 报告数（分布，而非均值） |
| worker result 保留率 | worker 报告携带的 `evidence_refs` 中，最终 manager submission 实际引用的比例；用于识别 manager 对 worker 结果的丢失/压缩 |
| critical path | 首个 `manager_task_assigned` → manager `finding_submitted` 的墙钟序列 |

**判读规则**：

1. 若 M4→M8→M16 上 manager share 与 worker idle 同步上升且 worker result 保留率下降，判 manager 为瓶颈；
2. 若 idle 上升但 manager share 平稳，优先怀疑 work front 供给不足（对照该 case 的 effective active-front count），不得直接归因 manager；
3. `M16 − P16` 的产出差异只在两者同预算、同 case、同 seed 的 matched block 内解读；
4. 单 seed 只做描述性诊断，不做架构优劣结论。

## 6. 实施状态（2026-09-17）

已实现并测试：

- `harness/manager_board.py`（role-restricted star board + manager/worker 事件）、`tools_for_mode(mode, …, role)` 的 manager/worker 工具面、`sandbox` 的 M 工具与 `manager_report_observed` evidence 白名单、`prompts` 的 MANAGER/WORKER 指令、`policies/base.py` 的 `ManagerWorkerPolicy`（task-triggered worker turns）、`runner` 接线与 `manager_worker` CLI mode。
- `tests/test_manager_worker.py`：M4 mock 全链路（含团队 permit 断言）、角色隔离（工具面 + board 调用）、evidence-chain 正向/负向、团队 permits 耗尽干净停止。M16 mock 冒烟（1+15）无死锁。

未实现（后续工作，按序）：

1. `analysis/analyze_run.py` 的 `manager_worker` 指标段（§5 的表；进 `metrics.json`，schema 沿用 v2 的“能力暴露 vs 实际活动”区分）。
2. M4 进入正式 matched block 的 freeze/执行记录。
3. M8/M16 所需 case 的 condition-blind 冻结与 block contract。

## 7. 非目标

- 不做 star/chain/tree/mesh 等 communication graph 解读，也不从 M 的 trace 反向声明 topology 结论。
- 不给 manager 专属审计工具、额外 ground truth 通道或更大的隐式权限；不给 worker 之间任何消息或 claim 能力。
- 不实现 lease、crash recovery、跨进程 CAS 或 manager 故障转移。
- 不为 M 单独调整预算单位、扣费口径或 block contract 字段。
