# Initialization Lease v3 设计说明：修复 T-Pilot 1 的 bootstrap 饥饿

状态：**设计冻结；实现与零网络测试已完成（2026-09-27），进度见 §8**。本 note 先记录 2026-09-27 对当前 runtime 的审计结果（§1），再冻结 `initialization_lease_v3` 语义（§2–§5）、测试计划（§6）与兼容性边界（§7）。历史 v1/v2 语义与 frozen artifacts 不变；T-Pilot 1 v1 live run 另行标记为 treatment-integrity failure（见 `T_PILOT_1_DESIGN.md` 的 v2 草案章节）。

## 1. 当前 runtime 审计（改码前调查）

### 1.1 lease 的实现位置

| 关注点 | 位置 |
| --- | --- |
| lease 状态与策略 | `harness/task_board.py` `TaskBoard.__init__`（`_initialization_policy/_order/_index/_owner/_initialized_agents`），policy ∈ {`initialization_lease_v1`, `initialization_lease_v2_optional`} |
| acquire / wait | `TaskBoard._await_initialization_lease`，由且仅由 `list_tasks`/`create_task`/`claim_task` 三个 gated 方法入口调用 |
| release（claim 成功） | `TaskBoard.claim_task` 成功路径 → `release_initialization_lease(reason="task_claimed")` |
| release（终止） | `harness/runner.py` `RunContext.run_one` 的 `finally` → `release_initialization_lease(reason="agent_terminal")` |
| v2 终止跳位 | `TaskBoard._skip_terminal_initialization_turns_locked`（仅 `initialization_lease_v2_optional`，仅对已终止且从未取得 lease 的顺位） |
| 调度 | `harness/policies/base.py` `_run_parallel`：`structured_team` 为每 agent 一线程（ThreadPoolExecutor），线程内串行执行 `AgentRunner.advance()` |

### 1.2 acquire / wait / release 触发条件

- **acquire**：未初始化 agent 的第一次 gated 调用（`list/create/claim`）且它位于顺位队首（`_initialization_owner is None and expected == agent_id`）。
- **wait**：未初始化 agent 的 gated 调用但不在队首 → `Condition.wait()` **无限期**阻塞该 agent 线程（发生在 tool dispatch 内部、该次 model call 的 permit 已结算之后）。
- **release**（v1/v2 仅有两条路径）：① 首次 `claim_task` 成功；② agent 终止（`run_one` finally）。**不存在** opt-out、超时或 dispatch 数上界。

### 1.3 典型流程的 model/provider round 数

`advance()` 每轮恰好一次 provider call；tool result 在 dispatch 后立即 append 进 `_messages`（`agent_loop.py` advance 内），由**下一轮** provider call 消费。因此正常 `list_tasks → (消费 snapshot) → create_task → (消费 task_id) → claim_task` 需要 **3 次产生 board tool call 的 model round**：create 依赖 list 结果进入上下文，claim 依赖 create 返回的 task_id（模型无法在同一 round 内预先写出该 id，故不能与 create 合并）；`list → claim existing` 为 2 轮。

### 1.4 一 agent 持 lease 时其他 agent 的处境

线程级并行：其他 agent 的**非 board 动作与 model call 完全不受阻**；只有其 gated board 调用会阻塞。但因为后位 agent 的 bootstrap 通常以 `list_tasks` 开始，一旦它 dispatch list 即整线程停摆——**从该时刻起到前位 release 为止，该 agent 无法执行任何后续动作**（包括纯调查动作），也感知不到预算状态。v1/v2 下 release 只发生在前位 claim 成功或**前位终止**时。

### 1.5 首个动作是非 board 工具时的 lease 处理（现状）

不触发任何 lease 逻辑：非 board 工具不经过 `_await_initialization_lease`。该 agent 保持 PENDING；若它位于队首之前（如 agent_001），后位 gated 调用持续等待，直到它最终调用 board 工具或终止。v2_optional 的终止跳位只在**终止后**生效。

### 1.6 各边界在现状下的行为

- `list_tasks → 非 board 动作`：lease 仍被持有（已 acquire），直到 claim 或终止——**这是 T-Pilot 1 live run 的直接根因**。
- `create_task` 未 claim：同样持有到终止。
- claim 失败（conflict）：`CoordinationError` 上抛，lease 不释放。
- board tool error / malformed arguments：不释放（malformed 甚至不进入 TaskBoard）。
- provider retry：发生在 `_complete_with_permit`（dispatch 之前），与 lease 无交互，不会重复推进 lease 状态（现状已正确）。

### 1.7 permit accounting 与 lease waiting 的相互影响

无显式耦合：permit 在 model call 前 acquire、dispatch 前 settle。等待中的 agent 不消耗 permit，但也**无法收到 BudgetExhausted**（不在 `acquire_call_permit` 里），池子被队友 drain 时它仍沉睡；被唤醒后下一次 `advance()` 才立刻 `budget_exhausted`。reconciliation 看不到线程停摆（permit ledger 一致），因此该 run 仍判 `valid`——饥饿对现有 validity 指标不可见。

### 1.8 T-Pilot 1 v1 live run 的事件证据（runs/t-pilot-1-shared-objective-v1-192p，不改写）

- agent_002/003/004 先后发出 `task_initialization_lease_waited`（owner=null, expected=agent_001）；agent_001 经 `list_tasks` acquire。
- 4 次 release 的 reason 全部是 `agent_terminal`；4 次 acquire 分别发生在前一位终止之后——bootstrap 完全串行了 4 个 agent 生命周期。
- permits：96/65/30/1（合计恰为 192）；board 全程零写（仅 list）；agent_004 一生只有 1 次 model call。
- 结论：**lease 从"首次 board 决策的串行化"退化为"覆盖整个 agent 生命周期的门禁"**，属 treatment-integrity / starvation 缺陷，不是模型自然分工。

### 1.9 现有测试为何没有捕获

`test_harness.py::test_initialization_lease_orders_visibility_before_first_claim` 与 `test_t_pilot_1_preflight.py` 的 mock 要么立刻 `list→create→claim`（claim 即释放），要么两步内终止（terminal 快速释放）——等待总是有界的、run 总是完成的，"eventually releases" 恒真。没有任何测试断言：等待不以**前位终止**为前提、lease 持有时长有界、permit/参与机会分布不被 lease 结构性扭曲。即缺失的 invariant 是"**不得仅因前位不用 board 而结构性剥夺后位的普通调查机会**"。

## 2. v3 冻结语义

```text
lease only sequences initial board bootstrap;
it must not gate ordinary investigation.
```

- **gated 集合不变**：仍只有 `list_tasks`/`create_task`/`claim_task` 参与 bootstrap 串行化；`release_task`/`complete_task`/messages/artifacts 与所有调查工具不 gated。
- **opt-out（board optional）**：agent 在 PENDING（尚未取得 slot）时的第一个非 board 选择——任一非 gated tool dispatch，或一个未产生任何 tool call 的 model round——立即标记 initialized 并推进顺位；原动作照常执行，不暂停。
- **episode 内离开**：BOOTSTRAP_ACTIVE（持有 slot）期间出现任一非 gated tool dispatch 或无 tool call 的 round → `investigation_started` 释放（覆盖 `list → read_file`：snapshot 已被模型消费后释放）。
- **claim 成功** → 立即释放（沿用）。
- **终止/submit** → 释放（沿用 `run_one` finally；submit 本身是非 gated dispatch，会先触发释放）。
- **硬上界** → 见 §3，FORCE_RELEASED。
- opt-out 是单向的：该 agent 之后仍可自由使用 board（ungated），但不再回到串行顺位；串行保证只覆盖首个 bootstrap pass。

## 3. bootstrap episode 硬上界（冻结：3 次 gated dispatch）

比较过的候选：

| 候选 | 评估 |
| --- | --- |
| provider/model-call count | 需跨层归因；provider retry 会让计数不确定（重试是否计入 bootstrap 语义模糊）。否决。 |
| board-tool-call（gated dispatch）count | 在 `TaskBoard` 内可确定性计数，不依赖模型文字，retry 不重复计数（失败的请求不产生 dispatch）。**采纳**。 |
| bootstrap state-transition count | 与 dispatch count 在本实现中同构，不再单列。 |
| "一次 board observation + 一次 allocation decision" 语义上界 | 语义正确但需落地为可执行计数：observation = `list_tasks`，allocation decision = `create_task` 随后 `claim_task`，共 **3 次 gated dispatch**。与 dispatch bound=3 等价。 |

**冻结 `BOOTSTRAP_TOOL_DISPATCH_BOUND = 3`**，依据 §1.3：完整正常路径 `list → create → claim` 的最小需求恰为 3 次产生 board tool call 的 model round；bound=3 不截断它（第 3 次 dispatch 若是成功 claim，走 `task_claimed` 释放，不触发 force），而 `list/create/list/list/...` 至多 3 次即被强制释放。claim 失败（conflict/依赖未满足）按原子 claim 语义上抛错误并计入 dispatch；`list → claim失败 → 重试 claim` 恰好 3 次，一次有界重试自然被允许，第 3 次仍失败则 FORCE_RELEASED，之后可继续 ungated 重试——无死锁。`create` 成功未 claim（E）：随后首个非 board dispatch/round 即释放；若继续刷 board 则在 3 次处强制释放。

## 4. v3 状态机

```text
PENDING
  ↓ (首次 gated dispatch 且位于队首)
BOOTSTRAP_ACTIVE
  ├─ PENDING 期首个非 board 选择 ─────────→ OPTED_OUT → RELEASED（从未持有 slot，记 turn_skipped）
  ├─ episode 内非 board dispatch / 无 tool call 的 round → RELEASED (investigation_started)
  ├─ bounded board episode, claim 成功 ───→ RELEASED (task_claimed)
  ├─ submit / terminal ───────────────────→ RELEASED (agent_terminal)
  └─ 第 3 次 gated dispatch 完成 ──────────→ FORCE_RELEASED (bootstrap_bound_reached)
```

Invariants（测试逐条对应）：

1. 非 board 调查永不仅因 initialization lease 被长期阻塞；
2. 前位不用 board 不得阻塞后位 bootstrap（PENDING opt-out 立即推进顺位）；
3. `list_tasks` 后允许模型消费 snapshot 再决定 create/claim（round 边界推进，dispatch 计数不跨 round 合并）；
4. lease 不延伸到普通调查阶段（episode 内任一非 board 动作即释放）；
5. successful claim 后必须释放（沿用）；
6. 达到冻结上界必须释放；
7. release exactly once（`_initialized_agents` 守卫，所有路径幂等）；
8. 顺位推进 deterministic（`_initialization_index` 单调、按 canonical order）；
9. 不改变 task ownership / closure gate 语义（不触碰 `release_task`/`complete_task`/closure gate）；
10. v3 不引入额外 provider call 或 permit（纯同步 bookkeeping + 既有 dispatch 路径上的 hook）。

## 5. 边界情况（A–J，全部进测试）

| Case | 行为 |
| --- | --- |
| A 首步 `read_file` | opt-out：标记 + 推进顺位；read 正常执行；后位可 bootstrap |
| B `list → read_file` | snapshot 已入 `_messages`；read dispatch 触发 `investigation_started` 释放 |
| C `list → create → claim` | 完整 bootstrap；claim 释放；不触发 bound |
| D `list → claim existing` | claim 释放 |
| E `create` 未 claim | 首个非 board 动作或 3 次 dispatch 上界释放 |
| F claim conflict | 错误上抛计入 dispatch；`list→claim失败→重试` 恰在界内；无死锁 |
| G board tool error / malformed | dispatch 计数与释放走 finally（error 也计次）；malformed 参数在 dispatch 层被拒，不进入 board，但该 round 已是非 board 行为→按 round 规则处理 |
| H provider retry | retry 发生在 dispatch 之前，不产生 dispatch、不推进状态；release 幂等 |
| I submit / terminate | submit dispatch 或 `run_one` finally 释放 |
| J 4/4 不用 board | 首个动作处各自 opt-out；无人等待；4/4 获得正常调查机会 |

## 6. 测试计划（零网络）

1. targeted unit（新 `tests/test_initialization_lease_v3.py`）：A–J、exactly-once、deterministic 顺位、v1/v2 回归不暗变。
2. lease+scheduler 集成：真实 `run_experiment`（structured_team, mock scripts）验证 §6 sequencing（agent_001 create/claim → agent_002 首次 list 可见）与 opt-out 并存。
3. closure/completion：closure gate、`convergent_v2` finalization 与 v3 并存语义不变。
4. shared-budget starvation stress：agent_001 永不用 board 且跑满许多步，断言 agent_002/003/004 不需等待 agent_001 终止、后位 slot 有界推进、无人复现 96/65/30/1 式的结构性剥夺（断言每 agent 最少参与机会，不断言 permit 均分）。
5. 全量 `tests/` 回归 + repository preflight/reconciliation smoke。

## 7. Backward compatibility

- 新版本化 runtime identity：`initialization_lease_v3`（CLI choice、`ContractFamily` 校验集合、`TaskBoard` 策略集合三处注册）。
- v1/v2 行为逐字节保留：计数、opt-out、bound、skip 推进均以 `policy == v3` 为门；v2 的 `task_initialization_turn_skipped.reason` 仍为 `agent_terminal_without_lease`。
- 事件 schema 不新增类型：v3 复用 `task_initialization_lease_released`（新增 reason：`investigation_started`、`bootstrap_bound_reached`；payload 附 `board_dispatches` 与可选 `trigger`）与 `task_initialization_turn_skipped`（新增 reason：`bootstrap_opt_out`，对应 PENDING 期 opt-out；owner 期 opt-out 记为 released `investigation_started`）。
- 新合同家族 `t_pilot_1_shared_objective_v2`（policy=v3，其余与 v1 家族逐字段相同）；T-Pilot 1 v1 manifest 与 frozen artifacts 不改写；`block_runner` 的 budget-contract 映射为 v2 增加同一条目。

## 8. 实现与验证进度（操作状态，随工作更新）

已落盘的实现（2026-09-27）：

| 文件 | 变更 |
| --- | --- |
| `harness/task_board.py` | `INITIALIZATION_LEASE_V3`/`LEASE_GATED_OPERATIONS`/`BOOTSTRAP_TOOL_DISPATCH_BOUND=3` 常量；`note_non_board_activity`；`_count_bootstrap_dispatch_locked`；`_enforce_bootstrap_bound`（三个 gated 方法 try/finally）；`_release_initialization_lease_locked` 增加 trigger/board_dispatches payload；`_skip_terminal_initialization_turns_locked` 泛化为 per-agent skip reason（v2 仍发 `agent_terminal_without_lease`）；非 owner 终止标记对 {v2_optional, v3} 生效 |
| `harness/agent_loop.py` | `_dispatch` 顶部对非 gated 工具调 `note_non_board_activity`（trigger=non_board_tool）；`advance()` 对零 tool-call round 调用（trigger=non_board_round） |
| `run_experiment.py` | CLI 增加 `initialization_lease_v3` choice |
| `harness/contract.py` | policy 校验集合 + `t_pilot_1_shared_objective_v2` ContractFamily 及其 validation 分支 |
| `harness/block_runner.py` | budget-contract 映射包含 v2 |
| `manifests/t_pilot_1_shared_objective_v2.json` | 新 manifest（相对 v1 仅 policy 差异，preregistration.status=draft） |
| `tests/test_initialization_lease_v3.py` | 26 个测试：unit A–J + exactly-once + v1/v2 回归 + AgentRunner（malformed/submit/retry/手动 interleave）+ 集成（sequencing 保留 / starvation stress / all-opt-out / mixed）+ closure/finalization + contract 注册 |
| `docs/plans/T_PILOT_1_DESIGN.md` | §9 v1 live run 改判 treatment-integrity failure；§10 v2 草案 |
| `docs/plans/t_pilot_1_freeze/prereg_draft_v2.json` | v2 prereg 草案（status=draft，live_execution_authorized=false） |

**最终验证（2026-09-27，全部零网络）：**

- `tests/test_initialization_lease_v3.py`：**26 passed**。
- 全量 `experiments/emergent_coordination/tests`：**369 passed + 9 subtests passed**（改动前基线 343 + 新增 26，零回归；包含 harness tests、repository-v1 contract/case selection、S/P/B/T/M4 mock harness preflight）。
- CLI mock smoke（repo_pilot_v0）：S1/P4/B4/T4（T4 走 `initialization_lease_v3`）全部 `run_validity=valid`、`reconciliation=valid`。
- live API 调用：0；未启动任何 live seed；v1 run 与 frozen artifacts 未改动。

测试编写中确认的两个事实：dispatch 层 `tool_call` 事件在 lease 等待之前发出，时序断言须用 board 级观察事件（payload 含 `count`）；target 快照中存在 `target/app/main.py`、不存在 `target/package.json`。

T-Pilot 1 v2 重新授权 live 前仍需：以 v2 合同冻结 block manifest（runtime_source digest 因本修复改变）、prompt packet 逐字复验 + contamination 审计重跑、prereg 由 draft 转 final。
