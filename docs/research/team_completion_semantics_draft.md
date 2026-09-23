# Multi-agent team completion semantics 草案

状态：Candidate E v1 是历史设计草案；其中与 `completion_v3` 实现对齐的 M4/manager-worker 子集已通过显式 generation 落地，但本草案不代表 S/P/B/T 已切换到 v3。当前冻结语义以 [`common_runtime_contract_completion_v3.md`](common_runtime_contract_completion_v3.md) 为准。

> 状态更新（2026-09-20）：本文第 13、15 节中的“不得开始 M4 live calibration”是 2026-09-19 gate 记录。随后用户明确授权并完成了 `n4m-flowise-calibration-v1-96p` 五条件 live calibration；结果与 trace 解释见 [`flowise-3.1.3-repository-v1-n4m-calibration-trace-review-20260920.md`](../releases/flowise-3.1.3-repository-v1-n4m-calibration-trace-review-20260920.md)。该运行验证了 live trace 可对账，但没有解除 worker identity mismatch、team-budget completion 或 coordination-effect 解释边界。

本文件建立在 [common runtime contract: `convergent_v2 @4096`](common_runtime_contract_completion_v2.md) 之上。它只规划 S1、P4、B4、T4、M4（以及后续更大 N）所需的 team-completion 语义、接口边界和纯 mock/unit tests；不改变 `completion_v2`、`convergent_v2`、4096 output ceiling、finding validator 或 hard dispatch-level finalization gate，也不定义正式的 multi-agent team policy。

## 1. Problem statement

单 Agent 的三个指标必须继续分开：

* **cognitive convergence**：Agent 表达证据足够并转向结束；
* **behavioral stopping**：Agent 实际停止探索和非必要 coordination acquisition；
* **submission completion**：payload 通过相同 schema/evidence validator 并被接受。

Team 还需要一个第四层、可独立观测的概念：**team completion**。它回答的是整个 team 是否已经没有仍需由 runtime 保证处理的在途生命周期，而不是“某个 Agent 说完了”或“某个 Agent 已 submit”。

本阶段的目标是让所有 topology 共享同一套 completion safety guarantees，同时避免把 finalization window、等待唤醒、报告汇总或 task 判断变成额外 coordination treatment。已实现的 v3 只覆盖显式 opt-in 的 manager-worker barrier；跨 topology 的 compatibility 仍需单独 contract。

## 2. Why S1 semantics cannot be copied directly

S1 只有一个 audit loop；P 是并行但相对独立的 Agent；B 有 shared store 的可见性和 lineage；T 可能有 task/claim/report lifecycle；M 有 manager、worker、assignment、report reception 和 re-assignment。因而同一个 per-agent step gate 的含义不同：

* P 中一个 Agent 提前结束通常不需要等待其他 Agent；
* B 中 write 已完成但 visibility/lineage 可能仍在事件队列；
* T 中 `waiting` 可能表示等待 assignment，而不是完成；
* M 中 manager 可能必须先接收报告，worker 才能结束；
* 统一的 wall/step gate 可能令 M/T 结构性地撞 gate，而不是暴露真实 coordination cost。

所以 public primitives 可以同构，team trigger 和 lifecycle drain 必须通过 mock 先证明不会制造 topology-specific advantage。第一版只把 team permit 作为 scientific completion boundary；wall-clock 不得改变 topology 的“该结束时间”。

## 3. Candidate completion models

| candidate | 语义 | 可取之处 | 主要失败模式 / 测试要求 | 本草案结论 |
|---|---|---|---|---|
| A global step-window | 到预设 team window，所有 Agent 同时进入 hard finalization | 简单、deterministic、接近 S1 | 截断 handoff/report；对 M/T 造成结构性偏置；把 waiting 当作同一时刻完成 | 不作为首选；保留作 baseline/control |
| B per-agent independent | 每个 Agent 按自身 step/convergence 独立 finalization | 不等待慢 Agent；局部 binding 易测量 | final worker evidence 无处消费；已 final Agent 是否可重激活；team submit owner 不清楚 | 不作为默认 team policy；可作为局部行为对照 |
| C quiescence-aware | 无 active task/report/message/exploration 且有 completion intent 才 finalization | 贴近真实 lifecycle | quiescence 定义易变成 scheduler；可能无限等待；不同 topology 可获得不同能力 | 作为候选组件，不单独冻结 |
| D coordinator-triggered | T lead/M manager 宣布 ready 后 team finalization | 与已有 coordinator role 对齐 | 把 coordinator 变成额外 completion primitive；P/B 无等价能力；manager 自己判断可能有 treatment effect | 仅作 topology capability 的实验候选，不作公共 trigger |
| E hybrid/bounded fail-safe | 自主完成优先；`remaining_team_permits <= preregistered_finalization_reserve` 时冻结新工作，进入确定性 bounded drain，再 hard finalization | 共享 safety envelope；不强迫同构 lifecycle；可量化 binding | drain 若可扩张会成为 scheduler；report adoption、late report、无 permit 情况必须严格定义 | **已作为 `completion_v3` 的 M4/manager-worker 子集实现；跨 topology 仍未冻结** |

### 3.1 Preferred candidate 的形态与实现范围

E 的 M4/manager-worker 子集已在 `completion_v3` mock/replay 中冻结；下面涉及跨 topology 的表述仍是接口边界，不是已启用的 S/P/B/T policy：

1. Agent/team 可以自主 convergence、stopping 和 submit；任何一个 Agent submit 不自动结束 team。
2. Runtime 维护统一的 hard team permit ledger、公共 finalization gate 和事件 lineage；不自动分配任务、不总结报告、不判断 backlog 价值。
3. canonical team safety boundary 是 `remaining_team_permits <= preregistered_finalization_reserve`，与现有 atomic team permit ledger 一致；该 reserve 是 matched block 的公共、预注册参数，不得按 topology 临时改变；wall-clock 仅用于 infrastructure watchdog，event/tick 只用于 drain bound。
4. 达到 boundary 后 runtime **冻结新工作**，创建一次 bounded coordination drain；wall-clock timeout 不得伪装成 scientific completion boundary。
5. drain 只做 transport/reconciliation，不替 Agent 阅读、解释、选择、合并或 adoption；不产生 model call、不创建新 task、不触发新探索。
6. drain 结束后才进入 hard finalization。finalization 仍然是 dispatch-level allowlist：只允许 frozen submit path；不能借 drain 恢复工具面。
7. Agent 的 waiting 是可恢复生命周期，不等于 done；但 waiting 本身不消耗 call。没有 unresolved obligation 的 waiting Agent 不应仅因等待而阻塞 team 的 safety finalization。

第二优先候选是 `C + E` 的受限组合：只有 topology 已存在的 task/report 状态才可作为 quiescence 观测，且必须受相同的 drain bound 约束；它不能给 T/M 额外 permits、model calls 或隐藏摘要。

明确拒绝把 A、B、D 直接作为跨 topology 的正式 policy：它们可作为 mock control，用来暴露 window、独立 finalization 和 coordinator authority 的偏置。

## 4. Minimal team state model

状态模型必须足够小，且只包含 runtime 能安全观测的事实。建议 mock interface 使用如下逻辑 snapshot（字段名为草案，不是 frozen schema）：

```text
TeamSnapshot
  team_event_seq                 # 单调事件序号，不是额外 model step
  permit_ledger                  # granted / consumed / remaining
  agents[id].status              # active | waiting | hard_finalizing | done
  agents[id].convergence         # existing convergence-v2 observation, nullable
  agents[id].last_exploration    # existing stopping metric, nullable
  agents[id].local_submission    # none | reported | submitted | rejected | accepted
  in_flight_model_calls          # count + call ids, observability only
  in_flight_tool_calls           # count + call ids, dispatch safety
  pending_coordination_events    # queued messages/reports/artifact events
  finalization                   # normal | freeze | drain | hard_finalization | close
  lineage_watermark              # last reconciled event/artifact sequence
```

字段分层：

| 分层 | 字段 | 规则 |
|---|---|---|
| universal runtime state | `team_event_seq`、permit ledger、agent status、in-flight counts、submission status、finalization phase、lineage watermark | 所有 S/P/B/T/M 都存在；没有 task/message 时值为 0 或空集合，不要求 condition 伪造 task |
| optional topology state | `active_tasks`、`pending_reports`、`unconsumed_shared_artifacts`、assignment/claim state、manager/lead role | 只有该 condition 已冻结并暴露该 primitive 时存在；runtime 只记录事实，不创造等价能力 |
| derived observability | active agents at boundary、team intent、quiescence candidate、individual/team binding、late report count | 由事件派生，不可作为隐藏 prompt/tool input；不得替代 Agent 的判断 |

`active_tasks`、`pending_reports` 和 `unconsumed_shared_artifacts` 不是 universal blocking predicates。它们是否影响 completion 必须在各 topology 的 preregistered lifecycle contract 中声明，并在相同的 hard safety boundary 下测量。

### 4.1 Information lineage states

transport、visibility、semantic adoption 和 submission 是不同状态，不能在 drain 中隐式折叠：

```text
produced -> queued -> delivered -> model_visible -> adopted -> submitted
```

* `produced`：Agent/tool 已生成 report、artifact 或 finding payload；
* `queued`：事件已进入可传输队列；
* `delivered`：目标 channel/board/store 已完成机械传输或 reconciliation；
* `model_visible`：目标 Agent 的 model-visible context 已实际包含该信息；
* `adopted`：目标 Agent 在其自身可审计输出/状态中明确采用该 evidence；
* `submitted`：该 evidence 随合法 submission payload 被 validator 接受。

Drain 可以推进 `queued -> delivered` 以及已完成 artifact 的 visibility/lineage reconciliation，但不能自动推进 `delivered -> model_visible`、`model_visible -> adopted` 或 `adopted -> submitted`。如果某 topology 有不经过 Agent 语义处理的 deterministic merge，必须由该 topology contract preregister；generic completion runtime 不得推断。

### 4.2 状态转换不变量

* `waiting` 只能由显式 pause/request-more/assignment boundary 产生；它不消耗 model call，也不自动产生 model call。
* local submit/report 不是 hard finalization；只要 topology 原本允许，Agent 之后仍可进入 `waiting` 并由合法 coordination event resume。
* `hard_finalizing` 是不可逆 runtime phase；进入后不得重新激活同一 Agent 的探索/coordination 工具，只允许 frozen submit path。
* `done` 表示该 Agent 的生命周期已 terminal（accepted submission 或明确 terminal failure），不是“暂时没有任务”。
* 任何 transition 都有 event、agent/team id、event sequence、permit effect（通常为 0）和 lineage reference。
* team completion 不由单一 `local_submission=accepted` 推断；必须同时记录其余 Agent、在途 operation、drain 和 pending lifecycle 状态。

### 4.3 Candidate E v1 state machine

```text
NORMAL
  | voluntary completion allowed
  | remaining_team_permits <= preregistered_finalization_reserve
  v
FREEZE
  | prohibit creation of new work
  | snapshot team_event_seq / lineage watermark
  v
DRAIN
  | transport + reconciliation only
  | no semantic adoption, no model calls, no new task/exploration
  | fixed non-model scheduler/event tick bound
  v
HARD_FINALIZATION
  | submit-only dispatch gate
  | irreversible for each affected Agent
  v
CLOSE
  |- clean_complete
  `- forced_complete
```

`infrastructure_invalid` 不属于 CLOSE 的第三种 completion outcome，而是独立的 run-validity axis（见 §7.3）。wall-clock watchdog、permit accounting、lineage、isolation 或 runtime invariant 出错时不能把结果伪装成普通 `forced_complete`。

## 5. Waiting semantics

### 5.1 Local submission/report is recoverable

local submission/report 包括：submit local finding artifact、report to manager、publish shared evidence、declare current task done。它们只更新相应 Agent/task/store 的 lineage 和 `local_submission` 状态，不自动进入 `hard_finalizing`，也不触发 topology-specific kill switch。只要原 topology contract 允许，Agent 可以在此后进入 `waiting`，并由已有合法 assignment、clarification 或 report event resume。

`hard_finalizing` 只有在 Candidate E state machine 的 runtime/team finalization phase 真正 active 时才成立；一旦进入则不可逆，所有 resume、探索和 coordination acquisition 都必须由 hard dispatch gate 拒绝。

`waiting` 的定义是：Agent 当前没有可执行的已授权工作，或者主动请求下一项工作；它仍可能被后续 assignment/report/manager action 恢复。它不是 `done`，也不是 implicit convergence。

建议的公共规则：

1. pause/resume 由 runtime/scheduler 的已有事件驱动，不调用 provider；resume 只有在已有 coordination event（例如 assignment）到达时才发生。
2. waiting Agent 在无 unresolved obligation 时不阻止 team 进入 safety finalization；它被记录为 waiting-at-boundary，而非 done。
3. waiting Agent 若仍绑定 active task、未发送的 report、未完成的 handoff 或其他 topology 已定义 obligation，则 `clean team completion=false`；hard boundary 仍可触发 fail-safe，但必须标记 forced/unfinished lifecycle。
4. manager active、workers 全 waiting 时，team 只有在 manager 有明确 completion intent、没有 active task/pending report/in-flight operation 且 submission 合法时才可能完成。workers waiting 本身不构成完成证据。
5. manager done、worker waiting 但有 unresolved task 时，team 不完成；如果没有 unresolved obligation，waiting worker 不应被无偿唤醒来“证明完成”。

这些规则不授权 runtime 自动决定 task 是否有价值，也不把 waiting 转换成额外 model call。

### 5.2 Public unread invariant

**Unread information is not, by itself, an unresolved lifecycle obligation.**

shared store 中的 unread artifact、unclaimed backlog、unused artifact 或 optional report，不能仅凭“存在”阻止 clean completion，否则 B 会天然比 P 更难完成。只有 topology contract 已明确声明某 artifact/report 必须被消费、接收或关闭时，才可作为 blocking obligation；generic completion runtime 不得自行升级其语义。

## 6. Coordination drain semantics

首选候选 E 需要一个非常短、确定性的 drain，但 drain 仍是待 mock 验证的 primitive，不是新 completion treatment。

### 6.1 Core invariant: transport/reconciliation is not semantic adoption

> **Drain may transport/reconcile already-existing information, but it may not semantically adopt, summarize, interpret, select, merge, or reason over that information on behalf of an Agent.**

Drain 绝不能把 worker report 自动变成 manager knowledge、把 report 内容加入 final finding、选择 evidence、判断 report 是否支持漏洞、总结/去重/融合 findings，或把 `delivered` 提升为 `adopted`。这条 invariant 是 Candidate E v1 的核心边界。

### 6.2 允许的内容

* `queued -> delivered` 的 report/message transport；
* 已完成但尚未推进 visibility/lineage watermark 的 shared artifact reconciliation；
* 已经 dispatch 的 tool operation 的返回事件入账（不重新 dispatch）；
* task close/report receive 的机械状态更新。

### 6.3 明确禁止的内容

* 新 repo read/search/shell 或新 hypothesis；
* 新 model call、retry、submission repair call 或隐式 manager summary；
* 新 task、reassignment、claim、handoff 或扩大 backlog；
* runtime 自动去重 finding、判断 task 价值、替 Agent 选择 evidence；
* 从 delivered 反推 model-visible、adopted 或 submitted。

### 6.4 v1 bound 和 ordering

Candidate E mock v1 使用统一的 **non-model scheduler/event reconciliation tick** 作为 drain 单位，canonical fixture 默认 `drain_max_ticks=8`。该数值可在 mock fixture 中显式配置以测试边界，但同一 test matrix 的所有 topology 必须使用相同值；不得因为 M/T 有更多 lifecycle 就自动延长。tick 只推进已存在的 transport/reconciliation queue，不产生 model call，也不消耗 extra permit。

* drain 不使用 wall-clock 作为 scientific boundary；wall-clock 只用于 infrastructure watchdog；
* drain 不使用额外 permits；
* 以 `team_event_seq` 固定 snapshot cutoff；FIFO 处理 cutoff 之前的 queued events。drain 期间新到但超过 cutoff 的事件不重新打开探索。
* 每个 tick 最多完成一个确定性的 non-model reconciliation turn；达到 `drain_max_ticks` 仍未处理的 event 标记 `late` / `unfinished`，不扩张 bound。
* 已经在途的 provider call 若返回，只记录结果和 lineage；不得自动触发 follow-up call。未返回的 call 到 bound 时标记 `in_flight_at_drain_close`。
* drain 结束后进入 hard finalization；所有非-submit dispatch 都由既有 hard gate 拒绝并记录 `prohibited_tool_attempt`。

cutoff 前产生但 freeze 前未进入目标 Agent model-visible context 的 report，drain 可以标记为 `delivered_unadopted_at_close`，但不得 retroactively 标记为 adopted 或进入 accepted submission。cutoff 后或 accepted submission 后到达的 report 保留原始 lineage，默认标记 `late_report_recorded_unscored`；若与 accepted finding 冲突，再加 `contradiction_after_close`。是否允许显式、预注册的 post-submit reconciliation 仍是开放问题。

## 7. Finalization semantics

必须区分两个指标：

* **individual hard finalization**：某 Agent 的 dispatch gate 已 active；记录该 Agent 是否在此前已有 convergence/stopping/local submit attempt，以及 gate 是否改变其下一步行为。
* **team finalization**：team safety boundary 已触发、drain 已关闭并开始统一 lifecycle close；记录 boundary 时 active/waiting/hard-finalizing agents、pending tasks/reports、in-flight operations 和 forced flag。

候选 E 下：

* local submission/report 可以早于 team finalization；不结束其他 Agent，也不使该 Agent 不可恢复；
* `hard_finalizing` 不能重新开放探索或 coordination acquisition；只允许 frozen submit path；
* team hard finalization 只在 bounded drain 关闭后触发；若存在未解决 lifecycle，仍可 forced close，但不能把它报告为 clean completion；
* team submission owner（P/B/T/M 的 aggregator/manager/individual）必须在各 condition preregistration 中明确，completion policy 不能隐式改变 deterministic finding merge semantics。

### 7.1 Submission owner boundary

mock fixture 可以显式注入 `submission_owner` 和 deterministic merge protocol；generic completion runtime 不得从 topology 名称、Agent role 或 report 数量推断 owner，也不得替 P/B/T/M 选择最终 owner。

### 7.2 Completion outcome

第一版冻结以下两个 completion outcome：

* **`clean_complete`**：team 正常完成；required lifecycle obligations 已关闭；lineage reconciliation 完整；submission contract 满足；hard fail-safe 没有强行截断仍需新 model work 的 lifecycle。
* **`forced_complete`**：公共 permit safety boundary 已达到；runtime 正常执行 freeze/drain/hard finalization；存在 unfinished lifecycle、binding、pending task/report 或未完成 adoption，但 permit accounting、lineage、isolation 和 runtime invariants 均正常。它是有效实验结果，不能自动标记为 invalid。

### 7.3 Independent run-validity axis

`infrastructure_invalid` 不是 CLOSE 的第三种 completion outcome，而是独立的 run-validity 值。它只用于 permit accounting 错误、lineage/hash/reconciliation 破坏、sandbox/isolation failure、runtime invariant violation、model/config drift、required logging 丢失、harness bug 或 infrastructure watchdog 中断等情况。换言之，**wall-clock timeout ≠ scientific completion boundary**；watchdog 中断进入 infrastructure outcome，不进入普通 `forced_complete`。

因此结果必须使用两个轴表示，例如：

```text
completion_outcome = clean_complete | forced_complete
run_validity       = valid | infrastructure_invalid
```

`valid + forced_complete` 合法且可能正是 coordination bottleneck 的研究结果；watchdog 中断不能伪装成普通 forced completion。若 `run_validity=infrastructure_invalid`，completion outcome 不参与有效实验主指标（可保留已观测的 partial state 供诊断）。

## 8. Condition-neutral vs topology-specific state

### 必须 topology-neutral

* `completion_v2`、4096 ceiling、frozen guidance、hard dispatch allowlist；
* team permit ledger、无免费 calls、retry/timeout 记账；
* event sequence、lineage、prohibited attempt logging；
* convergence/stopping/submission 三层 metrics 及 individual/team binding 术语；
* drain 的禁止事项、bound 记录方式、late event 不得自动重开探索；
* hidden evaluator、ground truth、private provenance 不得进入任何 Agent-visible channel。

### 允许 topology-specific，但必须显式、可见、不可扩张

* P 的 independent Agent set；
* B 的 shared store artifact visibility；
* T 的 task/claim/release/handoff/report 状态；
* M 的 manager/worker role、assignment、report reception、reassignment；
* submission owner 和 finding merge 输入，只能使用该 condition 原本拥有的 coordination primitive。

Topology-specific 字段只影响 observability 和已冻结 lifecycle 的安全关闭，不得改变公共 output ceiling、permit 数、evidence schema 或给某个 condition 一组其他 condition 没有的 hidden model calls。

## 9. Mock/unit test matrix

测试实现建议只使用 `MockProvider`、`MockPermitLedger`、`MockEventQueue`、`MockLineageStore`、`MockSubmissionValidator` 和可编排的 `TeamStateFixture`。fixture 应能注入 event sequence、in-flight operation、validator outcome 和 provider return；不得连接 provider、读取 hidden evaluator 或运行真实实验。

当前已提供 test-only 验证 scaffolding：`experiments/emergent_coordination/tests/test_team_completion_semantics.py`。它实现上述最小 mock 组件并覆盖 GEN/P/B/T/M/BUD/EVD 全部编号；该文件不调用 live provider，也不改变正式 runtime。

mock replay review 已增加可审计 tape：`experiments/emergent_coordination/tests/fixtures/team_completion_replay_cases.json`，由 `test_team_completion_replay.py` 进行双重 deterministic replay。当前包含 10 个关键正向 tape 和 3 个负向 replay 检查；正向 tape 的 canonical snapshot、permit、phase、lineage、late event 和 prohibited attempt 必须两次完全一致。

实际 harness mock preflight 已增加于 `test_team_completion_harness_preflight.py`：使用生产 `run_experiment`、真实 sandbox/event log/permit ledger 和 `MockLLMClient`，覆盖 S1、P4、B4、T4、M4 及 N=4 hard-gate path；该 preflight 不连接网络。M4 的显式 fixture 观察到 worker report 后进入 `waiting_for_assignment`、由 manager 完成 submission，这只是 topology fixture 的生命周期事实，不是 generic completion runtime 对 submission owner 的冻结。更重要的是，在与其他 topology 相同的 `max_steps=12`、8-step reserve 下，manager 的第二次 `manager_list_tasks` 会撞 hard finalization，因而无法观察全部 3 个 report；这是 live 前必须解决或明确 preregister 的 readiness blocker，不能通过给 M4 静默增加 step 来规避。

### 9.1 通用 matrix

| ID | setup | 必须断言 |
|---|---|---|
| GEN01 | 所有 Agent 在 team boundary 前自主停止并 accepted submit | hard gate non-binding；0 extra calls；team clean close；lineage watermark 完整 |
| GEN02 | 仅一个 Agent 无限探索，其余已完成 | fail-safe 结束 team；记录 offending individual binding；不删除其他 findings；无额外 model call |
| GEN03 | Agent 已 convergence 但继续 read/search | `cognitive=yes, behavioral=no`；gap 可计算；不得把它当 done 或 clean quiescence |
| GEN04 | Agent 停止探索但 submit 被 validator 拒绝 | 只允许 preregistered bounded repair；无 repair permit 时不 reopen exploration；rejection 与 finding absence 分开 |
| GEN05 | hard finalization 中请求 read/search/shell/coordination | dispatch-level hard gate 不可绕过；工具未执行；每次有 prohibited event |
| GEN06 | drain 队列含 report/message/artifact visibility | 只按 cutoff/FIFO transport/reconcile；0 model calls；lineage watermark 单调；不改变 adoption |
| GEN07 | drain 期间新 event 到达 | 不扩大 drain、不新建 task、不恢复 exploration；记录 late event |
| GEN08 | hard finalization 后尝试 resume/重新 claim | 失败且可审计；Agent 保持 `hard_finalizing`/done，不产生 hidden work |
| GEN09 | simultaneous submit attempts | accepted/rejected 顺序由固定 event sequence 决定；merge semantics 不由 completion policy 改写 |

### 9.2 P-specific

| ID | setup | 必须断言 |
|---|---|---|
| P01 | 4 independent agents，3 done、1 active | 不能因 3 个 done 就隐式结束 active；boundary 时只截断未完成者；3 个 accepted payload 保留 |
| P02 | Agent A 早 submit，Agent B 后发现更强 finding | A submit 不终止 team；B evidence 可按原 schema 进入 deterministic merge；无 runtime 自动重排 |
| P03 | 多 Agent 同时准备 submission | attempt/accept 顺序、merge owner、lineage deterministic；无双重 team close |

### 9.3 B-specific

| ID | setup | 必须断言 |
|---|---|---|
| B01 | A 写 shared evidence，B 尚未读取，A 准备 final | A 的 local final 不删除/隐藏 artifact；B 是否消费由 B 自己决定；unread 不自动等于 runtime obligation |
| B02 | store 有未消费 artifact，所有 Agent 声称完成 | 未读信息默认不阻止 team completion；记录 `unconsumed_shared_artifacts`，不得自动唤醒或总结 |
| B03 | Agent 在 finalization 后读取 shared store | hard gate 拒绝，不能获得新 evidence；禁止 attempt 可审计 |
| B04 | store write 完成但 visibility/lineage 未落盘 | bounded drain 可 reconcile 已完成 write；若超 bound，标记 `lineage_reconciliation_pending`，不生成新 call；append-only lineage 仍完整，否则为 `infrastructure_invalid` |

### 9.4 T-specific

| ID | setup | 必须断言 |
|---|---|---|
| T01 | 所有 task terminal | 若无 pending report/in-flight op，可 clean close；task primitive 不扩张为 runtime scheduler |
| T02 | task active，owner waiting | team 不是 clean complete；waiting 不等于 done；hard boundary 可 forced close 并标 unfinished |
| T03 | task complete，report 尚未被 lead/other Agent 接收 | queued report 在 drain cutoff 前可收取；不需要免费 model call |
| T04 | Agent 在 finalization 前想 claim 新 task | 若尚未 freeze，按原 T primitive 处理并记 permit；freeze 后拒绝；runtime 不评价 task 价值 |
| T05 | finalization 时有 unclaimed backlog | backlog 不自动证明必须继续；按 preregistered T lifecycle 记录，不能由 runtime 自动分配；forced close 必须标 pending backlog |

### 9.5 M-specific

| ID | setup | 必须断言 |
|---|---|---|
| M01 | manager active，workers done，reports 全收到 | manager 可在合法 schema 下 submit；worker done 不被重新唤醒；无额外 summary call |
| M02 | 一个 worker report pending | manager/team 不能报告 clean completion；queued report 可在 drain consume；超 bound 则为带 unfinished lifecycle 的 `forced_complete` 候选 |
| M03 | worker waiting，无 assignment | waiting 不等于 done；若无 active task/obligation，不应仅为“确认”而产生 call |
| M04 | manager 在 finalization window 内想 reassign | freeze 前按原 M primitive；freeze 后拒绝；不得因为 M 有 manager 就获得额外 window |
| M05 | manager 表达 completion，但 worker 仍 running | manager convergence 不等于 team completion；worker 的 individual binding/late evidence 分开记录 |
| M06 | worker evidence 已完成，manager 尚未读取 report | drain 只消费已排队 report；不自动替 manager 总结或重新探索 |
| M07 | manager submit 后 worker 返回 late report | late report 保留 lineage，默认 `recorded_unscored`，不静默改 accepted payload；需有明确 run metric |

### 9.6 Budget exhaustion

| ID | setup | 必须断言 |
|---|---|---|
| BUD01 | team 剩 0 permits，但有 pending reports | 无 model call；只可执行 bounded non-call drain；报告最终为 consumed/late/unfinished 之一 |
| BUD02 | manager 想处理最后一个 report，但无 permit | 不触发免费 call；若 report 已在队列可由 drain 消费，否则标 unfinished |
| BUD03 | worker timeout 消耗最后 permit | ledger 不超额；in-flight/timeout 事件完整；team forced close 可测量 |
| BUD04 | submission repair 需要新 call，但 budget=0 | repair rejected/deferred；不得 reopen exploration；validator rejection 与 budget exhaustion 同时记录 |
| BUD05 | 多个 Agent 竞争最后 permit | grant 顺序由固定 event/ledger 原子规则决定；无 topology-specific priority；所有 denied calls 可审计 |

### 9.7 Evidence/adoption boundary

这些测试专门验证 `transport != visibility != adoption != submission`：

| ID | setup | 必须断言 |
|---|---|---|
| EVD01 | worker report 在 cutoff 前生成并排队，但 manager 从未 model-visible 地看到 | drain 可以 deliver；manager `adopted=false`；final payload 不得把它当作 manager-adopted evidence；lineage=`delivered_unadopted_at_close` |
| EVD02 | report 已进入 manager model-visible context，但 manager 没有明确采用 | `seen=true` / `adopted=false`；completion runtime 不得自动升级 adoption |
| EVD03 | manager 在 freeze 前明确采用 report evidence | adoption lineage 保留；后续 drain 不改变语义状态；submission 可按原 finding protocol 使用 |
| EVD04 | B shared-store artifact 在 drain 阶段才完成 visibility | `visible_at_close=true`；不能 retroactively 视为其他 Agent 已读取；unread artifact 不自动阻止 completion |
| EVD05 | late report 与已经 accepted finding 冲突 | accepted payload 不被静默修改；report 保留 lineage；记录 `contradiction_after_close` |
| EVD06 | 多个 Agent 独立产生相同 evidence，但只有一个被 aggregator adopted | provenance 保留多个 producer；adoption lineage 只指向实际采用路径；runtime 不自动去重后伪造 adoption |

## 10. Binding and completion metrics

每个 multi-agent run 至少记录以下 per-agent 字段：

* `first_convergence_step/source/confidence`；
* `last_exploration_step` 与 `exploration_calls_after_convergence`；
* local report/submit steps 与 `hard_finalization_enter_step`；
* `prohibited_tool_attempts_after_finalization`；
* `individual_binding_classification`（binding / non_binding / ambiguous）；
* submission attempts、accepted/rejected reason；
* evidence lineage counts for `produced` / `queued` / `delivered` / `model_visible` / `adopted` / `submitted`。

每个 team 额外记录：

* `team_finalization_start` 与 `team_finalization_end`；
* boundary 时 `active_agents`、`waiting_agents`、`hard_finalizing_agents`；
* `pending_tasks`、`pending_reports`、`pending_coordination_events`；
* `in_flight_model_calls`、`in_flight_tool_calls`；
* drain start/cutoff/close、late events、lineage reconciliation outcome；
* `submission_state`、`runtime_forced_completion`；
* `completion_outcome`（`clean_complete` / `forced_complete`）与 `run_validity`（`valid` / `infrastructure_invalid`）；
* `team_binding_classification`。

建议定义：

* **individual binding**：若无 hard gate，该 Agent 在同一可比边界仍有可执行探索/coordination attempt，而 gate 后被迫停止，则为 binding；若已有 stopping/submit intent，则 non-binding；证据不足为 ambiguous。
* **team binding**：若无 runtime gate，至少一个 team lifecycle 会在同一 permit/window 边界继续产生可执行 event，且不是仅等待 drain 的已存在事件，则为 binding。pending report 本身不等于 team binding；必须区分 queued/non-call drain 与需要新 model call 的 work。

不能把 `team_finalization_start`、`accepted submission` 或 `all agents waiting` 单独当作 team completion rate。报告必须同时给 clean/forced、pending lifecycle、lineage adoption 和 late evidence 分解，并始终将 completion outcome 与 run validity 分轴报告。

## 11. Bias and confound analysis

### 危险 A：T/M coordination overhead 更容易撞 gate

对策是共用 team permits、相同 permit-based hard safety boundary 和相同 drain bound；额外 task/report 只作为 observed lifecycle state。报告 `pending_tasks/reports` 与 binding，而不是为 T/M 静默增加 calls。wall-clock watchdog 只能产生 infrastructure outcome，不能成为 topology-specific completion treatment。

### 危险 B：P 易独立结束，M 需等待报告

不能用同一个 per-agent step 直接截断所有 topology。preferred candidate 把 team safety boundary 放在公共 team permit reserve 上，并允许无-call drain transport 已在途报告；M 若仍需要新 model call，必须承担真实预算成本，不能由 runtime 补足。delivery 也不等于 manager adoption。

### 危险 C：为修复 M 提供更长的 topology-specific drain

drain bound、事件顺序和禁止事项必须公共化。若将来证明某种 lifecycle 需要不同参数，必须作为 preregistered、可见的 condition parameter 单独比较，不能藏在 completion policy。

### 其他必须监测的混淆

* manager/lead 的 completion expression 与 runtime nudge 的因果来源；
* report visibility 延迟与 provider latency；
* shared store unread artifact 与真正 unresolved obligation；
* `unread != unresolved obligation`，除非 topology contract 明确定义消费义务；
* validator rejection、budget exhaustion、malformed tool call 的不同 stop reason；
* drain 处理的事件是否曾经在 Agent-visible channel 中出现。

## 12. Preferred candidate and open questions

### Preferred candidate（待 mock 验证）

`E: public hard fail-safe + bounded, no-call, minimal lifecycle drain`。理由是它把不可绕过的 safety guarantee 保持为公共 runtime primitive，同时允许 P/B/T/M 保留各自已冻结的 lifecycle facts；它不把 coordinator、task backlog 或 unread artifact 自动升级为 runtime 判断。

Candidate E v1 现在已明确：

* primary safety boundary：`remaining_team_permits <= preregistered_finalization_reserve`；
* watchdog 不等于 scientific completion boundary；
* drain 只 transport/reconcile，不 semantic adopt；
* canonical mock drain unit：`drain_max_ticks=8` non-model scheduler/event reconciliation ticks；
* cutoff 前但未 model-visible/adopted 的 report 不得进入当前 accepted payload；
* completion outcome 为 `clean_complete` 或 `forced_complete`，run validity 独立记录；
* local submit/report 可恢复，只有 `hard_finalizing` 不可逆；
* unread information 不自动成为 unresolved obligation。

### Second-best candidate

受限 `C + E`：只有 topology 已经拥有的 task/report state 才可作为“是否 clean close”的观测，且永远不能解除公共 bound、增加 permits 或产生 model call。

### v1 已决定（不再作为 open question）

1. primary safety boundary 是 team-level permit reserve；wall-clock 只作 infrastructure watchdog；
2. drain 的 canonical unit 是统一的 non-model scheduler/event reconciliation tick，mock v1 默认 `drain_max_ticks=8`；
3. cutoff 前未进入目标 Agent model-visible context 的 report 不得 retroactively 进入当前 accepted payload；
4. drain 不执行 semantic adoption；`delivered` 不等于 `adopted`；
5. completion outcome 只有 `clean_complete` / `forced_complete`，并与 `run_validity` 分轴；
6. local submit/report 不触发 irreversible hard finalization；
7. unread artifact、unclaimed backlog、unused artifact、optional report 不自动成为 blocking obligation。

### 仍需 mock 结果或 topology contract 决定

1. 是否需要独立 `team_completion_intent` event，还是由已有 manager/Agent submission intent 组合派生；
2. 是否允许正式、预注册的 post-submit reconciliation；
3. P/B/T/M 各自的最终 submission owner 和 deterministic merge protocol；
4. 更大 N 是否需要新的、公开的 lifecycle parameter；
5. 是否将受限 `C + E` 作为后续替代 candidate；
6. cutoff 前已 `model_visible` 但未 adopted 的 report 是否永远只保留为未采用证据，还是 topology contract 可给出额外、非 runtime 的处理规则。

## 13. Gate before live N=4 calibration

`completion_v3` 的 M4 mock/replay gate 与 60 秒独立 finalization deadline 已完成冻结；本节其余条件仍是 S/P/B/T/M live block 的前置要求，因此本轮仍不授权 live provider。

当前待 freeze review 的定档文件为 [`n4m_flowise_calibration_v1.json`](../../experiments/emergent_coordination/manifests/n4m_flowise_calibration_v1.json)：所有 condition 使用同一份 96-permit team ledger、4096 output ceiling、96 max steps、1200 秒 wall-clock 和一次普通 harness retry；S1/P4/B4/T4 映射到 `completion_v2 + all_agents_terminal_v1`，M4 映射到 `completion_v3 + team_completion_v3`，其 1 个 final synthesis reserve 包含在 96 内，deadline 固定 60 秒。该文件只表达 preregistration，不授权 live 执行。

在允许跑 S1/P4/B4/T4/M4 live calibration 前，至少满足以下 gate：

* 通用 GEN01–GEN09、P01–P03、B01–B04、T01–T05、M01–M07、BUD01–BUD05、EVD01–EVD06 的纯 mock/unit tests 全部通过；
* `completion_v2 @4096`、M4 `completion_v3 @4096` 的 frozen prompt/policy/schema/tool/runtime digests 不变；任何 team extension 只增加日志和状态观察，不修改单 Agent semantics；
* hard finalization 在所有 Agent、role、malformed/replayed tool payload 下不可绕过；prohibited attempts 有 event；
* waiting/resume 无免费 model call，且 waiting 不再被当作 done；
* `EVD01–EVD06` 全部通过；`produced` / `queued` / `delivered` / `model_visible` / `adopted` / `submitted` lineage 可区分；
* drain 的 cutoff、FIFO、`drain_max_ticks` bound、late report 和 in-flight operation 语义 deterministic；无 semantic adoption、自动总结、分配、去重或隐藏 evidence；
* permit=0、timeout、validator rejection、repair denial 的结果 deterministic，ledger 永不超额；
* evidence/report/task/artifact lineage reconciliation 通过，accepted payload 不被 late event 静默改写；
* local submit/report 不触发 irreversible hard finalization；只有 `hard_finalizing` 后 resume 才会被拒绝；
* unread information 不自动成为 unresolved obligation，除非 topology contract 已明确消费义务；
* 每个 run 能产生 individual/team binding、`clean_complete`/`forced_complete`、pending lifecycle、submission、adoption 和 late evidence 指标；
* completion outcome 与 `run_validity` 独立记录；`valid + forced_complete` 不得被标为 infrastructure-invalid；
* S/P/B/T/M 的 Agent-visible target、base prompt、finding schema、公共 budget、provider/model/config 和 hidden-evaluator isolation 仍完全一致；
* topology-specific lifecycle parameter、submission owner、merge semantics、stop labels 已在 live block manifest 中公开 preregister，不能由 runtime 临时决定；
* M4 `completion_v3` contract 明确冻结 `team_finalization_deadline_seconds=60`、normal call 一次 harness retry、final synthesis 不 retry；先完成 mock replay review 和 contract review，再允许任何 live provider call。此文档本身不授权 live experiment。

## 14. Scope boundary

本草案不定义 S/P/B/T 的新 team policy，也没有修改 target、旧 manifest 或 `completion_v2` 公共语义。`completion_v3` 已实现 Candidate E 的显式 M4/manager-worker 子集：team-owned reserved permit、barrier、worker terminalization、transport drain、immutable snapshot 和 exactly-once final synthesis；实现细节与冻结字段见 [`common_runtime_contract_completion_v3.md`](common_runtime_contract_completion_v3.md)。team-wide cross-topology trigger、S/P/B/T 的 submission owner、以及 post-submit reconciliation 仍留给下一阶段 contract 冻结；M4 的独立 `team_finalization_deadline_seconds=60` 已在 v3 opt-in contract 中冻结。

## 15. M4 blocker audit（2026-09-19，mock-only）

### 15.1 可复核重放与 transcript/event reference

使用实际 `run_experiment` + 本地 `MockLLMClient` 的命令为：

```text
pytest -q experiments/emergent_coordination/tests/test_team_completion_harness_preflight.py::test_actual_harness_m4_manager_worker_preflight
```

固定 manifest 是 `max_steps=12`、`completion_policy=convergent_v2`、`max_output_tokens=4096`、`prompt_profile=repository_v1`、`finding_schema=repository_v1`；finalization reserve 为公共 `8`。该测试不创建 provider client，也不访问网络。

稳定的 transcript/event reference（事件序号本身每次 run 可变，以下字段是可重放的 lineage/key）：

| reference | 观察结果 |
|---|---|
| manager call `m1..m3` / `manager_task_created` | 三个 task 都 produced，并进入 manager board 的 queued/assigned 状态 |
| worker calls `w2-2`, `w3-2`, `w4-2` / `manager_worker_reported` | 三个 report 都 produced；report IDs 为 `manager_report_0001_manager_task_0001..0003` |
| manager `manager_list_tasks` step 4 / `manager_task_listed` | 唯一成功的 list；manager model-visible 观察到的 report 是已成功列出的子集（当前 fixture 通常为前两个），不是三个全量 |
| `completion_phase_started(agent_001, step=5, reserved_steps=8)` | manager 在第 5 个自身 dispatch step 进入 finalization（`12-8+1`） |
| manager call `m5` / `prohibited_tool_attempt(step=5, requested_tool=manager_list_tasks)` | 第二次 list 被 `hard_finalization_gate` 拒绝；没有参数解析、board dispatch 或新的观察 |
| manager call `m6` / `finding_submitted(count=0)` | manager 是当前 fixture 的 submission owner，空 `repository-v1` payload 被 accepted；late report 不会改写它 |
| worker `agent_finished(reason=waiting_for_assignment)` | 三个 worker 都 waiting；waiting 不是 `done`，也没有 worker submission |

因此，本 fixture 的 lineage 是：三份 report 均 produced/queued，只有成功 list 返回的子集 delivered 到 manager model-visible context；该 actual preflight 未执行 Candidate E drain，现有 board transport 也没有把其余 report 变成 `model_visible`、`adopted` 或 `submitted`。当前 manager 的 individual binding 是 step-5 hard gate；team binding 是 forced/unfinished（waiting workers 与未观察 report 并存）。

### 15.2 候选方案的 mock/replay 结果（不选择正式 policy）

| 候选 | mock/replay 约束 | 是否产生 M4-specific extra budget | 当前判断 |
|---|---|---:|---|
| bounded no-call drain（Candidate E） | 只推进 `queued -> delivered`；不产生 model-visible context，不执行 adoption；`permit=0` 也只能 transport | 否 | 可作为公共 primitive，但不能修复 manager 需要语义观察/采纳的缺口 |
| coordinator-triggered M4 lifecycle | 仅由已存在、合法的 manager/coordinator event 触发 lifecycle close；不授予 manager 额外 call | 语义上是 M4-specific topology contract；若改变 dispatch 窗口则是 extra treatment | 只能作为单独 preregistered 候选，不能藏入公共 completion policy |
| local report + waiting/resume | report 后 worker 可 waiting；只有已有合法 assignment/event 才能 resume；`hard_finalizing` 后 resume 必拒绝 | 否 | 可保留为 lifecycle 事实；waiting 不得当作 done |
| current per-agent gate baseline | 保留 `max_steps=12` 与 reserve=8；manager 第二次 `list_tasks` 在 step 5 后拒绝，观察被截断 | 否 | 这是当前 blocker 基线，不是 clean completion |

对应的 test-only replay case 为 `CANDIDATE_E_NO_CALL_DRAIN`、`CANDIDATE_COORDINATOR_NO_EXTRA_CALL`、`CANDIDATE_WAITING_RESUME` 和 `M4_PER_AGENT_GATE_BASELINE`；纯语义测试另覆盖 produced/queued、delivered-unadopted、model-visible-but-not-adopted、explicit adoption、late report、accepted submission 不变和 zero-permit no-call。

### 15.3 是否能在不增加 model call 的情况下 clean complete

在当前 M4 fixture 的语义要求下，不能确认 clean completion：Candidate E 的 no-call drain 可以把报告机械地 delivered，但不能把未观察报告 retroactively 变成 manager model-visible/adopted；而现有 per-agent gate 又拒绝了 manager 的第二次 `list_tasks`。给 manager 静默增加 step、permit、drain tick 或 retry 会形成 M4-specific extra budget，违反匹配约束。coordinator-triggered lifecycle 若需要改变这一点，也必须先成为公开的 topology contract 并单独比较。

所以当前状态是 **unresolved design blocker**，不是 runtime bug 修复，也不是 infrastructure-invalid。M4 尚未达到 live calibration gate；在公共 `completion_v2`/`convergent_v2` 语义不变且没有公开、等价的 lifecycle contract 之前，**不得开始 M4 live calibration**。
