# T-Pilot 2：有界 final synthesis / deduplication（design / prereg 草案）

状态：**设计稿及实施补记（2026-09-28）**。下文保留设计阶段的待办措辞作为决策历史；§15 的实现审计、mock 定值和零网络闸门结果以 [implementation_audit.md](t_pilot_2_freeze/implementation_audit.md) 与冻结目录中的 final prereg 为准。定值为 R=3、read cap=1、W=60s。用户在本会话已明确授权完成闸门后运行单个正式 seed。

前置事实（全部来自已冻结产物）：T-Pilot 1 v2 attempt2（seed-02）admission PASS，`clean_complete`，4/4 submitted（finding 2/2/1/1，merged 6，0 invalid），169/192 permits，finalization 于第 160 次调用精确触发；board 零写；裁决（[adjudication_v2_attempt2.md](t_pilot_1_freeze/adjudication_v2_attempt2.md)）：6 条 raw 全部为真，#0/#5 同根 → 团队语义 5 unique；4 条 operative-GT-unmatched 均为真问题（对应 v1.1 未激活 root，CR1 仅背景）；分类 mixed / indeterminate。**T-Pilot 2 不修 search 行为，不验证 board 分工，不重新优化 T-Pilot 1。**

### 冻结后的 Pilot 2 机器（概览）

```text
T4 search（合同与 T-Pilot 1 逐字节相同）
  ↓
all agents terminal
  ↓
C_raw freeze（永久保留，hash 时序可证）
  ↓
condition-neutral finalizer（post-terminal，控制侧身份 team_finalizer，无 search 上下文）

allowed:    retain / merge / correct / drop
not allowed: 无 raw 来源的新 finding / broad search / agent communication

  ↓
explicit raw decisions（每 raw_id 恰好一个）+ C_final
  ↓
blind evaluation（Stage 1 盲评 → Stage 2 解盲 → Stage 3 转换判读）

report: C_raw、Δ_synthesis = C_final − C_raw、C_final
```

---

## 1. 研究问题与实验单位

> **RQ（唯一）**：在搜索阶段合同尽可能不变的前提下，一个有界的 final synthesis phase 能否把多个 agent 的 raw candidate findings 转换成质量更高的 team-final unique finding set？

- **实验单位**：一个 T4 run（单 seed mechanism smoke test），核心观测量是同一 run 内 `C_raw → C_final` 的变化，不是跨条件比较，不是协作次数。
- **明确不在范围内**：task-board 分工（Pilot 1 已研究）；搜索阶段任何强制分工/去重/互验/固定角色/预先协作指令；统计显著性；总分；**任何无 raw 来源的新 finding**——finalizer 不是第五个 search agent，即使验证读取中发现新问题也不得提交（§4/§7）。
- **先验机会**：Pilot 1 的 6→5（#0/#5 跨 agent 重复对，且两人在 finalization 阶段对同一文件做了同 content-hash 的验证读取，seq 1133/1139）说明 raw 层重复在当前合同下真实发生——这是 Pilot 2 存在的经验依据，但 **#0/#5 只允许进入 evaluator fixture，不得进入任何 agent-visible prompt**（§9）。

## 2. 当前 runtime 调研结果

以下为对现行代码的逐项核实（file:line 以当前工作树为准；正式冻结时以 runtime_tree digest 重新绑定）。

### 2.1 submit_findings 如何形成 merged team result

- 每 agent 提交经 `AgentSandbox.submit_findings`（`harness/tools/sandbox.py:367-438`）原子校验 schema + evidence；接受后置 `self._submitted`，回调 `RunContext._on_submit` 把该 agent payload 原样写入 `artifacts/{agent_id}_findings.json`（`harness/runner.py:137-141`）——**per-agent raw payload 在 submit 时刻已经不可变地落盘**。
- 团队结果 = `merge_findings`（`harness/runner.py:166-174`）：**纯 union，逐条加 `submitted_by` 字段，无任何去重/综合/变换**，写入 `merged_findings.json` 并交给 evaluator。即现行 C_final ≡ C_raw（union 语义）。
- **submission 是终态**：dispatch 循环看到 `_submitted is not None` 立即 `_finish("submitted")`（`harness/agent_loop.py:185-186,437-446`）。T 条件下 agent 提交后不再有任何 model call，**不存在**看到其他 agent findings 的通道（无 message/board 写入发生；Pilot 1 v2 board 全程零写）。

### 2.2 finalization reserve=32 的分配与消费

- `team_remaining_permits_v1`：`BudgetTracker.maybe_start_team_finalization`（`harness/budget.py:219-236`）在共享剩余 ≤ reserve（32）时原子翻转 finalization epoch；这是**共享窗口阈值，不是预留池**——普通调用可以消费这 32 个 permit，只是触发后工具面被裁剪为 `{submit_findings, read_file, complete_task}`（`harness/agent_loop.py:87-89,329-335`；`harness/completion.py:34`）。
- v2 attempt2 实测：触发于第 160 次调用（remaining=32），四人全部在窗口内提交，team 终止于 169/192，**剩余 23 个 permit 未被消费**。这证明"搜索后仍有预算余量"在此 seed 成立，但**没有任何机制保证**（另一 seed 可能花满 192）。
- 与之对照，completion_v3 的 `reserved_final_synthesis_permits=1` 是**静态预留**（`harness/budget.py:128-132,350-364`）：普通调用在 remaining ≤ 1 时被拒（reason `reserved_final_synthesis`），预留 permit 只能经 `authorize_final_synthesis` 转移给 manager 专用 call_kind。Pilot 2 需要的正是这种静态保护语义（新 call_kind），而非 32 窗口语义。

### 2.3 既有 final synthesis / manager synthesis 原语

已有一套完整的 manager synthesis 机器，可复用其**语义模式**（不是其角色）：

- `completion_v3.py`：团队状态机 `NORMAL_WORK → TEAM_FINALIZING → FINAL_SNAPSHOT_READY → MANAGER_FINAL_SYNTHESIS → TEAM_TERMINAL/FORCED_UNFINISHED`；`ReportTransport` 带 `produced/queued/delivered/model_visible/adopted/late` 单调转移；`FinalTeamSnapshot` 冻结 worker 终态 + reports + evidence_refs；60s 有界 deadline；exactly-once。
- `AgentRunner.final_synthesis`（`harness/agent_loop.py:259-309`）：把 "Final synthesis input (immutable team snapshot): " + JSON 追加进 manager 上下文，只 advertise `submit_findings`，call_kind=`final_synthesis` **retry_limit=0**（一次 provider 尝试，`agent_loop.py:463-465`），dispatch 层有独立 `reserved_final_synthesis_gate`。
- 编排在 `ManagerWorkerPolicy._run_completion_v3`（`harness/policies/base.py:110-215`）：barrier → terminalize → drain/freeze snapshot → authorize → final_synthesis → adopt_report（以 evidence 交集为 adoption 证据）。

**限制**：`final_synthesis` 硬编码 `role != "manager"` 拒绝（`agent_loop.py:261-262`）；`run_experiment` 把 completion_v3 锁在 `manager_worker` 模式（`harness/runner.py:194-206`）；`contract.py:745-746` 禁止任何非 completion_v3 合同使用 `reserved_final_synthesis_permits`。因此 T 条件复用需要**版本化扩展而非参数打开**。

### 2.4 raw candidate set 的稳定冻结点

- `TeamCompletionBarrier`（`all_agents_terminal_v1`，`harness/team_completion.py:56-98`）在"全部 agent 有 stop_reason 且 in_flight=0"时一次性翻转——这是天然、确定性、已有 reconciliation 支撑的 **raw freeze 点**。
- 提交时序两种都合法：early submit（finalization 前即终止）与窗口内 submit（v2 实际形态）。freeze 点定义在 all-terminal，对两者一致。
- 空/失败 payload：`stop_reason != submitted`（budget_exhausted / model_format_failure 等）的 agent，其 `{agent_id}_findings.json` 可能缺失——freeze 时按"该 agent 无提交"记录终态与空集，不得虚构。

### 2.5 外来 evidence 的可采性（synthesis 的关键约束）

- `validate_evidence_refs` 要求 evidence ref 属于**本 agent 的 file_read 事件**（`harness/repository_v1_findings.py:71-88`）；sandbox 侧唯一的例外通道是"经协调面变为 model-visible 的外来 refs"：`task_result_observed` / `result_sync_observed` / `manager_report_observed`（`harness/tools/sandbox.py:396-419`）。
- 推论：finalizer 若直接引用 raw findings 的 evt ID 会被现行校验拒绝。**必须新增一个版本化的可见性锚点事件**（如 `synthesis_input_model_visible`），把冻结快照内列出的 foreign refs 纳入可采集合——这正是 completion_v3 用 `manager_report_model_visible` 解决的同一问题。
- finalizer 自己的 `read_file` 产生自己的 file_read 事件，天然可采。

### 2.6 bounded synthesis phase 的挂点与 completion/closure/reconciliation 交互

- 挂点：`run_experiment` 在 `policy.run_agents` 返回后、`merge_findings`/evaluate 之前（`harness/runner.py:305-331`）插入一个 opt-in 的 post-terminal phase，不影响任何现行 policy。
- `task_closure_gate_v1` 只绑 search agent 的 submit；finalizer 无 board、无 claimed task，gate 平凡满足。`team_completion` 事件语义不变（仍指 search team 的 `clean_complete/forced_complete`）；synthesis phase 产生自己的终态事件。
- `reconcile_run` 要求 permit ledger 与 llm_call/transcripts 一一对应（`harness/events.py:347-360`）：finalizer 的每次调用走同一 permit/settle/transcript 路径即可满足；`EVENT_TYPES` 是封闭元组（`events.py:17-35`），新事件类型需要显式登记。
- 有效性规则（ADR-0002，`runner.py:422-456`）：≥2 次 provider failure attempts → `infrastructure_invalid`。finalizer 的 provider 失败计入同一 ledger 规则——synthesis 阶段的失败按 §5 的降级规则处理，但若造成 run 层 ≥2 失败仍判 invalid。
- 合同面：需要新 contract family + 新预算/策略字段（`contract.py` schema evolution）；case manifest 必须保持 byte-identical（graph input-lock 绑定，`block_runner.py:220-227` 注释），Pilot 2 可沿用"把新 contract_id 映射到 `t4_flowise_sequenced_bootstrap_task_closure_v1` 的 192-permit budget 条目"的既有特例，前提是 permits 仍为 192。

## 3. Synthesis authority：候选方案与推荐

| 维度 | 方案 1：指定一名现有 T agent 为 final synthesizer | **方案 2（推荐）：condition-neutral finalizer（新会话）** | 方案 3：多 agent review + deterministic reducer |
| --- | --- | --- | --- |
| 是否改变 T 的 coordination treatment | 改变：需重开已终止 agent 的生命周期（submit 即终态，§2.1），该 agent 获得他人 findings 的可见性，成为事实上的事后 manager | 不改变：search agent 的 prompt、工具面、生命周期逐字节不变；finalizer 在全队终止后才存在，search 阶段对它不可见 | 改变：所有（或 k 名）agent 都要被重开做 review round，等于向 search treatment 注入一个未预注册的 post-terminal 协调轮 |
| 未来 S/P/B/T/M 公平复用 | 差：S1 没有可指定的"另一名 agent"；各条件指定规则不同 | 好：与条件无关的公共输出层，同一 finalizer、同一输入合同、同一 reserve 可加在所有条件上 | 差：S1 无 peer（退化为单 agent 自评）；N 不同时投票语义不同；reducer 规则本身成为设计产物 |
| 是否引入 manager-like role | 是（对内） | 否（对外置、事后、无任何对 search agent 的分配/取消/重排权限；区别于 M 的 in-band manager：M 在搜索**期间**指挥） | 部分：投票+reducer 是一种委员会 manager |
| provenance 是否清楚 | 混杂：finalizer 的判断与其自身搜索历史/自身 findings 纠缠，dedup 偏向自身主张，无法区分"基于 C_raw 的判断"与"基于私有上下文的判断" | 清楚：finalizer 的 model-visible 输入**恰好等于冻结 C_raw 快照**（transcript 可逐字验证），判断只能来源于 C_raw + 其有界 read_file | 中等：每票可溯源，但最终归并来自 reducer 规则而非可审查的推理 |
| budget 可否严格控制 | 可，但该 agent 的 permit 归属扭曲 per-agent 统计 | 可：独立 call_kind + 静态 reserve + 独立时间窗（§6；failure 语义待 implementation audit） | 难以小：≥4 review calls + followups，reserve ≥8–12 |
| implementation complexity | 高（终态重开 + 现有 final_synthesis 的 manager 硬编码要拆） | 中（新增小型 runner + 新 call_kind + 新事件；search 路径零改动，369 现有测试零语义变更） | 高（重开全部 agent + 投票协议 + reducer 冻结） |
| merge / drop / correction（而非 union） | 能 | 能（全量 payload + per-finding `derived_from` + 显式 per-raw decisions，§4） | 能，但 merge/drop 阈值由 reducer 先验决定 |

**推荐：方案 2**，并把"确定性 union"作为冻结的降级回退（§5）。理由：(a) 它是唯一保持 search-stage treatment 逐字节不变的方案；(b) 它是唯一可原样推广为 S/P/B/T/M 公共输出层的方案（§14）；(c) provenance 干净——"finalizer 只见过 C_raw"是可从 transcript 逐字验证的命题，使 raw→final 的每个变化可归因；(d) provenance 干净——"finalizer 只见过 C_raw"是可从 transcript 逐字验证的命题，使 raw→final 的每个变化可归因；(e) 预算严格有界（静态预留语义与 completion_v3 同构；per-call retry/failure 语义列入 §6 implementation audit），实现上是"复用语义模式、去掉 manager 角色"。方案 1 的致命伤是重开终态 + 上下文偏置 + 使 T 事后趋同于 M；方案 3 的致命伤是成本、策略污染与 reducer 先验不可分离。

## 4. Raw / Final candidate lifecycle

### C_raw（synthesis 开始前冻结）

定义：全部 search agent 到达终态那一刻，各 agent 已接受 payload 的并集，逐条附：

- `raw_id`：冻结时按 submission 事件序确定性分配（`raw_00`, `raw_01`, …，全 run 唯一）；
- `submitted_by`（agent provenance）、submission 事件 ID 与 wall-clock 时间；
- 完整 repository-v1 finding 字段（title/category/severity/source/sink/guard/affected_object/trust_boundary/reasoning_summary/evidence_refs/verification/variant_coverage/confidence）；
- `evidence_map`：该 finding 每个 evt ID → target-relative 路径（来自 file_read 事件索引，控制侧生成）；
- 提交者终态（stop_reason）。

冻结动作：控制侧把上述内容 canonical-JSON（sort_keys）写入 `artifacts/raw_candidate_set.json`，sha256 记入 `raw_candidate_set_frozen` 事件。**此后任何组件不得改写该文件；`{agent_id}_findings.json` 与 merged union 继续保留**（禁止覆盖原始 candidate）。

### C_final（synthesis 完成后的 team-final set）

- finalizer 经 `submit_team_findings` 提交；payload = repository-v1 字段 + 每条新增 **`derived_from: [raw_id, …]`** + **`raw_decisions`**（§8），控制侧写入 `artifacts/team_final_findings.json`，并由其显式 decisions 生成 `raw_disposition.json`；sha256 记入 `team_findings_submitted` 事件。
- 追溯规则（由 intake 校验强制）：**∀ final finding：`derived_from.length ≥ 1`**。
  - `derived_from = [一个 raw_id]` 且字段实质同 → **retained**；
  - `derived_from` ⊇ 2 个 raw_id → **merged**；
  - `derived_from = [一个 raw_id]` 且字段级 diff 非空 → **corrected**（含 narrowing / strengthening）；
  - **`derived_from = []` 一律拒绝**：Pilot 2 v1 不存在"新 synthesis judgment"合法路径。finalizer 的合法动作集冻结为 retain / merge / correct / drop；即使它在验证读取中发现新的问题，也不得提交——**Pilot 2 测量的是 synthesis transformation，不是给系统增加第五个 search agent**。
- **显式 raw decisions**：`submit_team_findings` 除 final findings 外必须携带 `raw_decisions` 数组——**每个 `raw_id` 恰好一个 decision**：`{raw_id, action ∈ {retain, merge, correct, drop}, target_final_id / merged_with, evidence_refs, rationale}`（schema 细节见 §8）。对 drop 必须保存 rationale 与 evidence_refs（允许为空数组，但为空必须显式呈现，供 `unsupported drop` 统计）。控制侧的 `raw_disposition.json` **由 finalizer 的显式 decisions 生成**；"raw_id 未出现在任何 `derived_from`"只作为一致性交叉校验（与 decisions 不一致 → intake 拒绝或 admission fail），**不得作为 drop 的唯一推导来源**。**drop 不删除任何 raw 记录；dropped raw 不允许静默消失。**

### 边界情形（冻结）

- 某提交者 payload 为空或无提交：C_raw 含其空集与终态，snapshot 如实呈现。
- C_raw 全空（0 findings）：跳过 model 调用，`C_final = ∅`，事件 `synthesis_skipped_empty_raw`；不消耗 reserve。
- finalizer 在 reserve 内未能产出合法 payload：`C_final := C_raw 的确定性 union`（即 Pilot 1 的 merge 语义，附 `synthesis_degraded` 事件与原因）——**降级不是 run 失败**，是记录在案的产出路径。

## 5. Synthesis phase 状态机（`team_synthesis_v1`；方向冻结，R/W 数值待 mock）

全队层级，post-terminal，一次性：

| 状态 | 进入条件 | 动作与不变量 |
| --- | --- | --- |
| `SEARCH` | — | 与 T-Pilot 1 逐字节相同（completion_v2_team 全套；见 §13）。唯一差异：普通调用的许可下界从 0 变为 `192 − R`（§6） |
| `RAW_FROZEN` | `all_agents_terminal_v1` barrier 满足且 in_flight=0 | 写 `raw_candidate_set.json`；发 `raw_candidate_set_frozen`（含 hash、raw 计数、提交者终态表）。若 0 findings → 转 `SKIPPED_EMPTY` 终态 |
| `SYNTHESIS_INPUT_VISIBLE` | raw 冻结完成 | 创建 finalizer 会话（新 runner、无 search 上下文）；首个 model request = 冻结快照的确定性渲染 + synthesis instructions；请求落 transcript 后发 `synthesis_started` + `synthesis_input_model_visible`（该事件同时是外来 evidence 可采性锚点，§2.5；并核对 transcript 内嵌快照 hash = 冻结 hash，否则 admission fail） |
| `SYNTHESIS_ACTIVE` | 输入已可见 | 每次 model call = call_kind `team_synthesis`，逐次消耗静态 reserve R，**每次调用 provider retry=0**（沿用 `final_synthesis` 语义，`agent_loop.py:463-465`；failure 后 phase 能否继续属 §6 implementation-audit 项，不得预设"可 retry"）；advertise 工具面 `{read_file, submit_team_findings}`（§7）；schema 违规 → 同现有 submit-retry 语义回 field errors、在 reserve 内重试 |
| `FINAL_RECORDED` | 合法 `submit_team_findings`（findings + raw_decisions 完整）被接受 | 写 `team_final_findings.json` + `raw_disposition.json`（**源自 submission 内的显式 raw_decisions**，反向缺失仅作一致性校验）；发 `team_findings_submitted`（含 hash、计数、decision 统计）；phase 终态 |
| `SYNTHESIS_DEGRADED` | reserve 耗尽 / phase wall-clock 到期 / run 级 wall-clock 耗尽 / 提供方失败致无法继续 | `C_final := 确定性 union(C_raw)`；发 `synthesis_degraded`（原因字段：`reserve_exhausted` / `deadline` / `provider_failure`）。不判 run 无效（除非触发 ADR-0002 的 ≥2 失败规则） |

不变量（admission 检查项）：(1) 冻结 hash 早于任何 synthesis provider request；(2) finalizer 的全部 model-visible 输入 = 快照 + 其自身有界 read 结果（transcript 可证）；(3) 每次 synthesis 调用有 permit/settle/transcript 三对账；(4) `derived_from` 全部指向存在的 `raw_id` 且**每条 ≥1**（无新-finding 路径）；(5) 每个 `raw_id` 恰好一个显式 decision，且与 final findings 的 `derived_from` 集一致（不一致 → intake 拒绝或 admission fail）；(6) search agent 事件流中不出现任何 synthesis 侧信息。

**事件面（冻结，保持最小）**：`raw_candidate_set_frozen` / `synthesis_started` / `synthesis_input_model_visible` / `team_findings_submitted` / `team_findings_submission_rejected` / `synthesis_degraded` / `synthesis_skipped_empty_raw` 共 7 个；显式 raw decisions 全部包含在最终 submission payload 与 `team_findings_submitted` 事件内，**不为单个 decision 建事件**。

**评估产物（命名冻结）**：`evaluation_raw.json`（C_raw-union 口径）、`evaluation_final.json`（C_final 口径）、`synthesis_delta.json`（Δ_synthesis 指标）。run 结束时对两个口径各跑一次 operative repository_v1 evaluator；v1.1 仅背景。若现有 pipeline 仍写 `evaluation.json`（现行代码从 raw union 计算），必须在 run_manifest 中显式记录其 alias 关系（= `evaluation_raw.json`）并版本化，不得让其语义含糊漂移。

## 6. Budget / reserve 方案

| 方案 | 机制 | 因果解释问题 |
| --- | --- | --- |
| A. 用现有 192 内的**剩余**预算（无静态保护） | team 终止后如有剩余 permit 则做 synthesis | synthesis 的可用性成为搜索花费的内生函数：花满 192 的 run 静默无 synthesis → 按结果筛选 treatment 强度；"mechanically successful"无法保证；未来条件下 S1/T4 剩余量系统不同 → 不可比 |
| **B.（推荐）静态子预算**：search 与 synthesis 固定切分 | `synthesis_reserve_permits = R` 静态预留于 192 内；普通与 finalization 调用在 remaining ≤ R 时被拒（新 reason `team_synthesis_reserved`，机制同 `post_sync_reservation`，`budget.py:324-327,390-391`）；R 只能被 call_kind `team_synthesis` 消费 | 搜索工作预算 192 → 192−R（R 按最低能力合同由 mock 定值，§6）：与 Pilot 1 的跨 pilot 搜索行为比较有此微小混杂，须显式报告；但 Pilot 2 的主对比是**同一 run 内** raw→final，不受影响。所有未来条件可加同一 R，保持 matched |
| C. 临时额外 synthesis budget（192 + R） | phase 用额外 permit | 违反本仓核心因果约束（S/P/B/T 同一 fixed team budget）；总花费不再 matched，架构比较失效；只能作显式声明"不可比"的工程诊断，不进正式 pilot |

**provider-failure 语义：`implementation-audit required before R freeze`。**此前一稿曾推断"一次 provider failure 后仍可 retry 成功"与 per-call `retry_limit=0`（`agent_loop.py:463-465` 的 `final_synthesis` 语义）可以并存；该推断**未经实现验证，作废**。R 冻结前必须在真实 synthesis loop 上逐条核实：(a) 一次 provider failure 后 phase 是否立即 degrade；(b) outer synthesis loop 是否还能再发新的 provider call（新 permit、同 phase）；(c) failure 是否消费 reserve；(d) ADR-0002 的失败计数如何累计（finalizer 失败与 search agent 失败是否同池）；(e) schema-invalid 重试与 provider-failure 是否走不同路径（预算与事件上均可区分）。

**R 的冻结规则（规则冻结，数值不冻结）**：先用 deterministic mock 实测最小 synthesis workflow，再取**满足最低能力合同的最小 reserve**：

```text
最低能力合同（R 必须覆盖的最坏有界路径）：
1 次必要 evidence read
+ 该 read 的工具结果进入下一次 model context
+ 最多 1 次 schema correction
+ 最终 submit
```

候选优先测试 `R ∈ {2,3,4}`；**不得为了减少预算占比而选择无法满足该合同的 R**。下表是 mock 的实测对象（工作流变体枚举；每次调用 0 自动重试；read 的工具结果需下一次 model call 才可见），**不再是本文的预算推导依据**：

| 变体 | 调用序列 | permit 数 |
| --- | --- | --- |
| V1 首次即合法提交 | submit | 1 |
| V2 一次 schema 纠错后提交 | invalid→errors→submit | 2 |
| V3 一次验证读取后提交 | read_file→（结果可见）→submit | 2 |
| V4 验证读取 + 一次纠错 | read→invalid→submit | 3 |
| V5 两次验证读取后提交 | read→read→submit | 3 |

与 reserve=32 的交互：finalization 触发条件（remaining ≤ 32，即第 160 次调用）**不变**；finalization 窗口内 search agent 最多花到 remaining=R（v2 实际停在 23，预期行为不变）。

### 6.1 Wall-clock reservation（静态时间预算，新增）

permit reserve 不足以保证 synthesis opportunity——search 可能在耗尽 permits 前先耗尽墙钟。两个候选：

| 方案 | 语义 | 因果/执行问题 |
| --- | --- | --- |
| A | search 与 synthesis 共享 1200s，无时间预留 | search 使用接近全部 1200s → raw freeze 后 synthesis 几乎无执行时间；synthesis 可用性再次成为搜索行为的内生函数 |
| **B（采用）** | 总 wall-clock 仍 1200s；`search_deadline = 1200 − W`，`synthesis window = W` | search 阶段显式损失 W 秒（须申报，§13）；换来 synthesis opportunity 的时间保证 |

**W 的推导（保守但有限；最终值 mock 实测后按同一公式定稿，不得现在拍脑袋冻结）**。依据一：冻结 v2 attempt2 run 的实测 provider latency（169 次成功调用）：mean 1.1s / median 1.0s / p95 1.7s / p99 3.6s / max 5.0s；与 synthesis submit 最同形的 finalization 窗口调用 mean 2.5s / max 5.0s。依据二：mock workflow（上表 V1–V5）。依据三：最大候选 R=4。依据四：read_file 为本地文件读（亚秒级）。公式：

```text
W = R_max × L_submit_max + N_read_max × L_read + C_overhead
  ≈ 4 × 5.0s + 2 × 1s + 10s ≈ 32s
```

保守取整 **W = 60s** 作为工作值（与 completion_v3 barrier deadline=60s 的先例一致），mock 定稿；若 mock 显示需要更大 W，**总 run wall clock 仍不增加**（维持 1200s），只能扩大 W 并在合同中显式申报 search 损失。冻结后：search deadline = 1140s，synthesis window = 60s。**执行点警告（implementation-audit 必核项）**：当前 T 路径 wall clock 仅在 `make_session` 检查（`runner.py:94-95`；`BudgetTracker.check_wall_clock` 未接入 call admission）——search deadline 与 synthesis window 的强制执行点必须实现并核验（§15-5）。

## 7. Tool surface

finalizer 的允许行为冻结为：

```text
inspect C_raw
→ optionally read bounded source evidence（仅验证 raw candidate 的已有 claim）
→ decide retain / merge / correct / drop
→ submit full final set + explicit raw decisions
```

- advertise 且仅 advertise：`read_file`（沿用现有 spec 与 evidence_ref 语义）、`submit_team_findings`（§8）。dispatch 层 allowlist 硬闸：任何其他工具在参数解析前拒绝并落 `prohibited_tool_attempt`（复用 `agent_loop.py:689-727` 模式）。
- **明确禁止**：broad repository exploration；整仓 list/search（不 advertise `list_files`/`run_shell`）；board / message / shared FS；调用或消息其他 agent；创建新 investigation task；**提交无 raw 来源的新 finding**（§4）。
- `read_file` 仅用于验证 raw candidate 的已有 claim；**次数上限与 R 一样由 deterministic mock 定值后再冻结**（候选 1–2 次；mock 矩阵见 §12），不现在拍脑袋冻结。
- search agent 的工具面**逐字节不变**（frozen tool_schema digest `81707c84…` 继续作为 search 侧合同；新工具只存在于 finalizer 会话）。

## 8. Candidate / evidence 的 model-visible contract

**快照渲染（确定性）**：`SYNTHESIS_INPUT_VISIBLE` 的 user message = 冻结快照的 canonical JSON（与 `raw_candidate_set.json` 同 hash），包含：raw 条目数组（`raw_id`、**稳定匿名 contributor token**（`contributor_0`、`contributor_1`、…：同一 agent 的所有 raw findings 恒用同一 token；finalizer 不看到真实 agent ID、条件、顺位或角色名称，但可以判断两条 finding 是否来自同一/不同 contributor；token→agent 映射只存控制侧）、全部 repository-v1 字段、`evidence_map`、提交时序索引）+ 提交者终态表 + synthesis instructions。不包含：GT/v1.1 root、#0/#5 判例文字、条件标签、search transcripts、board 状态。

**evidence_map 冻结为最小形态**：`evidence_ref → target-relative path`，仅此而已。不得包含：GT/root label；evaluator verdict；v1.1 信息；Pilot 1 #0/#5 adjudication 文字；任何 historical correctness label；architecture/condition metadata。

**Synthesis instructions 要点（草案，冻结前需 contamination 扫描）**：任务 = 产出 team-final repository-v1 payload；要求 (a) 同一安全不变式与同一 sink/受保护对象的多条 raw 合并为一条（`derived_from` 列全部成员）；(b) 仅在证据不足以支持时删除（drop 须可在 raw evidence 上复核）；(c) 修正（severity/scope/guard/verification）须有证据支撑（引用 raw 已有 refs、外来 refs，或自己的新 read 均可）；(d) **不得创建与 C_raw 无关的新 finding**——合法动作仅 retain/merge/correct/drop，验证读取中发现的新问题也不得提交；(e) 对每个 raw candidate 给出恰好一个显式 decision（含 rationale；drop 的 evidence_refs 允许为空但必须显式呈现）；(f) 可以选择不改变任何内容（原样保留是合法输出）。

**`submit_team_findings` schema（新版本化合同 `repository-v1-synthesis-v1`）**：

```text
{
  schema_version: "repository-v1-synthesis-v1",
  findings: [ { …全部 repository-v1 字段（校验规则逐字复用 repository_v1_findings.py）…,
               derived_from: [raw_id, …]  // ∀ finding: length ≥ 1；=[] 一律拒绝 } ],
  raw_decisions: [ { raw_id, action: retain | merge | correct | drop,
                     target_final_id / merged_with, evidence_refs, rationale } ]
}
```

约束（intake 强制）：findings 上限 32 条、evidence_refs ≤16、去重等约束同现行；**每个 `raw_id` 恰好一个 decision（缺失/重复/未知 raw_id 均拒绝）**；`derived_from` 只能指向存在的 `raw_id`；decisions 与 findings 的 `derived_from` 集必须一致（dropped raw 不允许静默消失）。evidence 校验：可采集合 = 快照内列出的 foreign refs（经 `synthesis_input_model_visible` 锚定）∪ finalizer 自己的 file_read；anchor 覆盖规则（evidence 须触及所报 source/sink/guard 文件之一）不变，`evidence_map` 提供路径即可复用现行实现。

## 9. Dedup / truth / correction evaluator（两层分离）

**原则**：dedup/root clustering 与 truth judgment 是两个独立裁决层；`GT unmatched = FP` 明确禁止。

**层 1 — truth adjudication（condition-blind，逐条 raw 与逐条 final 独立进行）**，标签四分类（沿用 v2 裁决的方法学：代码级核验 + 冻结 GT；评审者不知提交者/条件）：
- `matched_gt_valid`（operative repository_v1 GT 命中且代码核验为真）；
- `novel_valid_gt_unmatched`（GT 未覆盖但代码核验为真——v1.1 仅作 CR1 式背景对照，不改判）；
- `unsupported_false_positive`（声明与代码核验矛盾或证据不支撑）；
- `unresolved`（无法裁定，保留 uncertain 标签与理由）。

**层 2 — root clustering（语义，同层 1 独立进行）**：按 v2 裁决 §2 的判据（同一安全不变式 + 同一 sink 家族 + 同一受保护对象 = 同根）分别对 C_raw 与 C_final 聚类，得 raw roots / final roots。**#0/#5 的裁决只构造 evaluator-design fixture（同构不同锚的重复对、错误合并对、应删未删对等），其文字与锚点不得进入任何 agent-visible 产物。**

**裁决顺序（冻结）**：

```text
Stage 1: condition-blind truth adjudication + root clustering
         （对 raw 与 final 独立进行；reviewer 不知 finalizer 对任何 raw 做过什么转换）
Stage 2: 解盲 raw ↔ final provenance（derived_from / raw_decisions）
Stage 3: 评价 merge / drop / correction 是否正确（下表 + §10）
```

reviewer 不得因已知 finalizer 删除/合并了某条 finding 而影响其 Stage-1 raw truth/root 判断。第二 reviewer / adjudication 仅对**影响 Δ 的关键分歧**进行，不默认全量双人标注（沿用 Pilot 1 stage-3 聚焦复核模式）。

**冻结的转换判定定义**（对每个 synthesis 决策逐项评级；"正确/错误"以层 1+层 2 的 adjudication 为准）：

| 判定 | 冻结定义 |
| --- | --- |
| true duplicate merge | `derived_from` ⊇2 raw 且这些 raw 被层 2 判同根，且 final 条目覆盖该根的共享不变式 |
| false merge | `derived_from` ⊇2 raw 但层 2 判不同根（语义信息损失） |
| duplicate retained | raw 存在同根对，但 final 中仍有 ≥2 条判同根（漏合并） |
| valid finding retained | raw 判 `matched_gt_valid`/`novel_valid`，其根在 final 中被覆盖 |
| valid finding incorrectly dropped | raw 判 valid，其根在 final 中无任何覆盖且无 layer-1 依据充分的 drop 理由 |
| unsupported correctly suppressed | raw 判 `unsupported_false_positive` 且其根未进 final |
| unsupported retained | raw 判 unsupported 且仍以对齐条目存在于 final |
| correction（narrowing / strengthening / other） | final 条目对其 `derived_from` 单根 raw 的 {severity, guard.kind, trust_boundary/affected_object, anchor 范围, verification.status} 有字段级 diff。**correctness 以证据充分性与代码级裁决为准**：`supported` = 现有证据（raw 已有 refs 或新 refs）足以支持新 claim，且 code-level adjudication 支持新值——**不要求出现新的 evidence ref**（finalizer 对已有证据做更正确的解释同样是 supported correction）；`incorrect` = adjudication 支持原值，或新 claim 无证据支撑。是否引入新 evidence ref 单列为 provenance 指标（§10），不作为 correctness 必要条件 |

## 10. Raw→final metrics（无总分；全部原始分子/分母 + adjudication 依据）

| 维度 | 指标 |
| --- | --- |
| Dedup | raw finding count；raw semantic unique roots（层 2）；duplicate pairs/groups（raw 同根组）；correctly merged duplicates（true merge 数）；duplicate findings remaining（漏合并条数）；false merges。（merge/drop 计数一律以**显式 raw_decisions** 为源） |
| Validity | valid unique findings retained（两个 valid 标签合计的根保留数）；valid findings incorrectly dropped；unsupported findings suppressed；unsupported findings retained；unresolved 计数 |
| Correction | 各字段类 correction 计数（scope/reachability/severity/guard/verification）；correction supported by evidence（§9 口径，**不要求新 ref**）；incorrect correction；引入新 evidence ref 的 correction 数（provenance 旁记） |
| Evidence / provenance | final 条目引用 foreign-agent evidence 的比例；每个 merge/correction 是否携带明确 evidence refs；**explicit drop decisions 中 evidence_refs 为空的计数（unsupported-drop 候选）及其 rationale 可核性**；intake 拒绝的 `derived_from=[]` 提交计数（闸生效证据） |
| Cost | synthesis provider calls（成功/失败）；synthesis permits 消耗 / R / 192（占比）；synthesis tokens（in/out）；降级事件与原因；read_file 使用次数 |

核心报告对象是 `C_raw → C_final` 的变化（Δ 表 + 逐决策 adjudication 表），不是协作次数。

## 11. Admission 与 success criteria（单 seed mechanism smoke）

**Mechanically successful**（先于任何效果判读检查）：
- raw set 在任何 synthesis provider request 之前冻结（hash 时序可证）；
- synthesis 获得完整 model-visible candidate/evidence（首个 synthesis request transcript 含冻结 hash）；
- final set 全量可追溯（`derived_from` 全合法且**每条 ≥1**、每个 raw_id 恰好一个显式 decision 且与 final findings 一致、无 accepted `derived_from=[]` 条目）；
- clean completion：search team `clean_complete`、有限终态、reconciliation valid、无 provider/runtime defect 主导（ADR-0002）；
- search 侧合同与 Pilot 1 逐字节一致（prompt packet / tool digest / 预算语义，§13）。
admission 不过 → 停止效果判读，定位 runtime/合同问题，保留产物，版本化修复后另行 seed；不得同 seed 改合同续跑。

**Useful synthesis**（仅当 raw set 实际存在 synthesis opportunity 时评价；opportunity 由 §9 adjudication 判定：≥1 raw 同根对 / ≥1 unsupported raw / ≥1 同根矛盾主张 / ≥1 可修正主张错误）：
- 观察是否至少发生一种**正确**转换：dedup（true merge）/ FP suppression / evidence-based correction；
- 同时必须报告：valid-root retention、false merge/drop（任一 false merge 或 valid-drop 即如实记录，不设遮掩性阈值）。

**结果标签**（互斥）：`mechanism_pass_useful`（≥1 正确转换）/ `mechanism_pass_no_correct_transformation`（有机会但无正确转换——这是该 seed 对 RQ 的诚实答案）/ `non_diagnostic`（raw 无任何 opportunity：**"不发生修改"不是失败**，如实记录）/ `mechanism_fail_runtime`（admission 失败或降级由 runtime defect 主导）。不做统计推断，不追加 seed。

## 12. 零网络 / mock tests 计划（实现阶段执行，本任务未实现）

新增 `tests/test_t_pilot_2_synthesis.py`（+ 合同测试），全部 `MockLLMClient`、临时 workspace、真实 `TaskBoard/AgentRunner/RunContext/BudgetTracker`。最低覆盖矩阵：

**Transformation（转换正确性，fixture 驱动）**：retain；true merge；false merge fixture；correct drop；incorrect valid drop；evidence-supported correction（含"仅重释已有证据、无新 ref"变体）；unsupported correction；duplicate retained（漏合并）。

**Schema（显式 decisions 与来源闸）**：每个 raw_id 恰好一个 decision；unknown raw_id 拒绝；duplicate decision 拒绝；final finding `derived_from=[]` 拒绝；merge provenance 完整（merged 成员全列于 derived_from 与 merge decision）；dropped raw 不允许静默消失（无 decision，或 final 无覆盖且无 drop decision → intake/admission 拒绝）。

**Budget（数值定值矩阵）**：R 候选 {2,3,4} × read cap 候选 {1,2} × 工作流变体（direct submit / 1 read→submit / invalid→submit / 1 read→invalid→submit / 2 reads→submit）；schema correction 路径与 permit 记账；provider failure 注入（§6 审计项 (a)–(e) 逐条断言）；reserve exhaustion → 降级 union + `synthesis_degraded`；wall-clock reservation（search deadline 与 synthesis window 边界各触发一次路径）。

**Isolation（隔离）**：search packet 与 Pilot 1 frozen packet 逐字节一致（含 finalization 文本与三工具面）；finalizer 看不到 condition/GT/history（快照内容断言 + contamination 扫描：GT/v1.1 root 锚点、#0/#5 判例文字、avoid-duplicate/inspect-others 类旧文案误入 search 侧的反向扫描）；synthesis 信息不回流 search agents（事件流断言）。

**回归与 preflight 闸门**：全套现有 tests（基线 369 passed + 9 subtests）零回归；S/P/B/T mock smoke 不变；闸门流程沿用 Pilot 1：合同/manifest 冻结 → packet hash → contamination → mock 全绿 → prereg draft→final → 用户单独授权 live。

## 13. 与 T-Pilot 1 保持不变的 frozen variables

| 项 | 冻结值（与 v2 attempt2 合同相同） |
| --- | --- |
| shared-objective search prompt | `repository_v1_t_pilot_1_shared_objective`（common/user/board-capability 文本及 hash `59f4519f…`/`c396950d…` 不变） |
| 条件与规模 | T4 / structured_team / 4 agents |
| 模型 | openai_compatible / deepseek-flash / thinking disabled / temperature 0 / 4096 output |
| target | `flowise_3_1_3_repository_v1` 冻结快照（tree digest `c612819a…`） |
| 工具语义 | search agent 工具 schema/dispatch/sandbox 逐字节不变（digest `81707c84…`） |
| lease | `initialization_lease_v3` |
| board | optional（不要求创建/认领/使用） |
| search 行为合同 | 不添加分工/去重/互验/角色/预协作指令；board 使用仍是合法模型行为 |
| 完成合同 | `convergent_v2` + `all_agents_terminal_v1` + `team_remaining_permits_v1` + reserve=32 + `task_closure_gate_v1`；finalization 消息与三工具面不变（hash `a67d60e1…`） |
| 预算框架 | hard_team_call_permits=192、max_steps=96、wall_clock=1200s（总墙钟不变，按 §6.1 划出 synthesis window W）、max_provider_retries=1（search 调用）、finalization 触发于 remaining≤32 |
| finding schema | repository-v1（search agent 提交面逐字节不变） |

**申报偏差（两项，均须写入 run_manifest 与报告）**：(1) 静态 synthesis reserve R（数值待 mock 定值，候选 ∈{2,3,4}）使普通（search+finalization）调用的许可上界变为 192−R；(2) wall-clock reservation（§6.1 方案 B）：`search_deadline = 1200s − W`、`synthesis window = W`，**总 run wall clock 不增加**，search 阶段显式损失 W 秒（v2 实测全程 58s，实际不绑定，但合同如实申报）。`reserved_final_synthesis_permits` 维持 0（completion_v3 原语不被启用，新机制是独立版本化路径）。新增内容严格局限于：`raw candidate freeze → bounded synthesis phase → team-final set`。

## 14. 对未来 S/P/B/T/M 比较的公平性处理

**立场：本机制设计为可成为所有条件的公共输出层（condition-neutral 可扩展性是 Pilot 2 的设计约束）；其效果的表述冻结为：**

> common finalizer 保留 C_raw，因此**不会删除 raw-layer architecture evidence**；但它**可能 attenuate、amplify 或 transform differences at C_final**。本设计不声称 synthesis 层"不掩盖"架构差异。

未来正式比较必须**同时报告三层，不得只比较 C_final**：

- `C_raw`：search / coordination architecture 的直接产出（各条件 agent 自产提交的冻结并集）；
- `Δ_synthesis = C_final − C_raw`：公共 post-hoc synthesis 的作用（已裁决的 retain/merge/correct/drop 转换集）；
- `C_final`：end-to-end system 的最终产出。

其余原则不变：finalizer 是 condition-blind 的（输入 = raw findings + 匿名 contributor token + 最小 evidence 路径映射；无条件标签、无 search transcripts、无 board/shared 状态；同模型、同 prompt、同 reserve、同时间窗、同输入合同），它给 T 的东西与给 S/P/B 的完全相同；不违反 B/T 能力隔离（AGENTS.md：finalizer 是控制侧输出层，不向任何条件注入 message/task/claim/leader 能力）；若未来某比较选择不采纳公共层，公平规则是"**要么所有条件都有 neutral finalizer，要么都没有；绝不 T-only**"。

**M 条件暂不解决（明确降级为后续事项）**：Pilot 2 是 T-only mechanism pilot；M 的 worker-report / manager-output raw boundary 在正式 S/P/B/T/M comparison prereg 前单独冻结，不阻塞也不预决于本设计。当前只要求 neutral finalizer 的设计保持 condition-neutral 可扩展性。

## 15. 冻结状态与实现前余项

**方向性设计已在本文件冻结（实现不得偏离）**：synthesis authority = condition-neutral finalizer（控制侧身份 `team_finalizer`，独立 `synthesis_runner.py` 或等价独立 post-terminal runner；不重开 AgentRunner search 生命周期；不是第五个 search agent；不复用 completion_v3 identity）；新 contract family；search prompt / tool / runtime digest 不变。∀ final finding `derived_from ≥ 1`（无新-finding 路径，§4）；显式 raw_decisions（每 raw_id 恰好一个，§4/§8）；finalizer 能力边界（§7）；contributor 匿名化（§8）；evidence_map 最小形态（§8）；事件最小清单 7 个（§5）；evaluator 三段顺序与 correction 口径（§9）；评估产物命名（§5）；wall-clock reservation 方案 B 语义（§6.1）；architecture-fairness 三层报告口径（§14）。

**implementation audit + deterministic mock 后才能定值（数值不得先冻结）**：

1. `synthesis_reserve_permits = R`：候选优先测 {2,3,4}；按 §6 冻结规则取**满足最低能力合同的最小值**；不得为降低预算占比选不满足合同的 R。
2. `read_file` 次数上限：候选 {1,2}；与 R 一起按 §12 Budget 矩阵定值。
3. `synthesis window W`：按 §6.1 公式 + mock 实测定稿（工作值 60s；总墙钟不变）。
4. **provider-failure 语义核实（R freeze 的前置）**：§6 审计项 (a)–(e)——一次 failure 后是否立即 degrade、outer loop 能否再发新 call、failure 是否消费 reserve、ADR-0002 如何累计、schema-invalid 与 provider-failure 是否分路径。
5. **wall-clock 执行点核实**：当前 T 路径 wall clock 仅在 `make_session` 检查（`runner.py:94-95`；`check_wall_clock` 未接入 call admission）——search deadline 与 synthesis window 的强制执行点须实现并核验。

**实现时逐字冻结（方向已定，只差文本/schema 定稿）**：

6. finalizer prompt 全文（§8 指令逐字化 + 渲染 packet + contamination 扫描，含 #0/#5/GT 锚点反向扫描）后冻结 hash。
7. `submit_team_findings` / `repository-v1-synthesis-v1` intake 校验器逐字段定稿（含 raw_decisions 结构、错误返回格式、decisions↔derived_from 一致性校验）。
8. contract.py schema evolution：新 contract family、新预算/策略字段（`synthesis_reserve_permits`、`synthesis_window_seconds` 等）、复用 `t4_flowise_sequenced_bootstrap_task_closure_v1` 的 192-permit budget 映射特例；case manifest 保持 byte-identical（graph input-lock）。
9. 新事件类型登记与 reconciliation 规则（§5 七事件 + `call_kind=team_synthesis` 白名单 + deny reason `team_synthesis_reserved`）。
10. 双口径评估产物与 `evaluation.json` alias 关系的 run_manifest 记录字段（§5）。

**明确延后（不阻塞 Pilot 2）**：

11. M 条件 C_raw 边界：正式 S/P/B/T/M comparison prereg 前单独冻结（§14）。
12. seed identity 预置 `t-pilot-2-final-synthesis-seed-01`；沿用"冻结 → preflight 全绿 → 用户单独授权单 live seed → 不追加"流程；live 前 0 次 API 调用。
13. evaluator fixture 集（§9 判定定义的可执行 fixture：同根对/假合并/漏合并/应删未删/有证据修正（含无新 ref 变体）/无证据修正）与 stage-2/3 人工裁决人员安排。

---

**边界重申**：本文件为收紧后的 design/prereg 草案（R / read cap / W 三个数值待 implementation audit + mock 定值）。未修改任何 runtime 代码；未跑任何测试；未运行任何 live provider；T-Pilot 1 的全部 frozen artifacts、run 产物与裁决不改写。核心原则：**Pilot 2 v1 只研究对已有 raw findings 的有界 transformation；不要把 synthesis 偷偷变成额外搜索阶段。**（search 合同一字不改。）

## 16. 实施补记（2026-09-28）

§15-4/§15-5 审计和 §12 零网络定值已完成，见 [implementation audit](t_pilot_2_freeze/implementation_audit.md)。正式合同使用 `t_pilot_2_final_synthesis_v1`，数值 R=3、read cap=1、W=60s；search 阶段的 T-Pilot 1 冻结 prompt/tool packet 在完整 T4 mock 中逐字复验。冻结 packet、block manifest、最终 prereg 和正式运行的 admission/裁决另存 `t_pilot_2_freeze/`；旧段落的“未实现/未测试/待定值”仅描述本稿写作时状态。
