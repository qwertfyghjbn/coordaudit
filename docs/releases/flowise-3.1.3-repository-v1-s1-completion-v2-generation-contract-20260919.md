# Flowise 3.1.3 repository-v1 S1 completion_v2 世代契约与预注册（2026-09-19）

本文档是 `completion_v2` 世代的 generation contract 与 prereg-style 实验笔记。它在任何 live run 之前写就并提交；live 2×2 不得偏离本文件记录的 seed 列表、run 数量与成本上界。

## 1. 世代定义

`completion_v2` = 旧 completion-policy 语义 + 以下三项世代级变更：

1. **`max_output_tokens = 4096`**（旧世代 2048 冻结不动，仅作历史对照）。
2. **Hard dispatch-level finalization gate**：`convergent_v2` / `scheduler_only_v2` 的 finalization 窗口（最后 8 个 model call）内，dispatch authorization 层只放行 `submit_findings`。任何其他 tool call（手工构造、旧 schema、未 advertise、malformed/repaired arguments、重放旧 tool name）在参数解析之前被拒绝：不执行、记录 `prohibited_tool_attempt` 结构化事件（agent_id、step、call_id、requested_tool、finalization_active、rejected_by=hard_finalization_gate、arguments_sha256、arguments_bytes）、返回确定性 runtime rejection（`prohibited_tool_during_finalization`）、不泄漏目标内容、不恢复工具面。**不是字符串黑名单**：实现是 dispatch 层的 allowlist 交集（`FINALIZATION_ALLOWED_TOOLS ∩ mode allowlist`），位于 `agent_loop.py::_dispatch` 参数解析之前。
3. **新 instrumentation**：call_role/output-ceiling 字段（继承 4096 诊断轮）+ `prohibited_tool_attempt` 事件 + `metrics.json` 的 `completion` 段（convergence cue 候选、behavioral stopping、submission 路径、binding candidate 机械规则）。

世代政策值命名：`convergent_v2`、`scheduler_only_v2`。旧值 `convergent_v1`、`scheduler_only` 保留原 advisory（可绕过）语义不改动——旧 2048 runs 因此永远可按其自身语义解释。

### 2×2 矩阵（世代内）

| condition | prompt guidance | hard finalization |
|---|---:|---:|
| none | 0 | 0 |
| guidance_only | 1 | 0 |
| scheduler_only_v2 | 0 | 1 |
| convergent_v2 | 1 | 1 |

Factor A（guidance）prompt 文本与旧世代 byte-identical（`CONVERGENT_COMPLETION_INSTRUCTIONS` 未改）。finalization user message 也与旧世代对应条件 byte-identical；世代间唯一语义差 = hard gate + 4096 ceiling。

## 2. Generation digests

git commit：`f624fda`（本契约随同一提交入库；live runs 的 `run_manifest.json` 会记录该 commit）。

| 组件 | 定义 | sha256 |
|---|---|---|
| completion policy 语义 | `harness/completion.py`（政策集、reserve=8、gate allowlist、finalization message、拒绝 payload） | `66f3e83ae3e2dbaa988a36f6a55a325d60f8e0200e2dcef6912c3a54b42f4e44` |
| tool schema | `tools_for_mode("single","repository_v1")` canonical JSON | `d3491ddcc5ad36ee9303d3cabb7d1e90fc8912d6e21dcb604fc812d27129cdb2` |
| runtime gate 实现 | `harness/agent_loop.py` | `31ad7fd49353dde98c935749c2b63986845a38440da86d3c41f1eacc64e002ad` |
| prompt profile | `harness/prompts.py` | `74e77ae6d5de1a8f202a4563306b70dc51ba6d81b46ff818d3cc0d9b87ed8a2e` |
| system prompt — none = scheduler_only_v2 | 逐字节相同 | `c5f44795d24948b46606867a9a98e07dc7e7b61c00429c9039b8c13a5e5b009c` |
| system prompt — guidance_only = convergent_v2 | 逐字节相同 | `0a79182e3426e0b4fe5a9a8f1a89ec88e47b55d0f7308c24e38ba90d7a40fb85` |

与旧 2048 世代对照：none/scheduler（旧）的 system prompt hash 亦为 `c5f44795…`，guidance/conv（旧）亦为 `0a79182e…` → **Factor A 跨世代完全一致**；旧/新世代可由 completion policy 值、`prohibited_tool_attempt` 事件存在性与 `max_output_tokens` 三者中任一区分。

## 3. 固定实验配置（所有 12 个 run 一致）

- case：`flowise_3_1_3_repository_v1`（target snapshot、ground truth、provenance 不变）
- mode `single` / S1 / N=1；evaluator `repository_v1`、scoring 不变
- provider：`openai_compatible`，model `deepseek-flash`，thinking **disabled**，temperature 0.0
- `max_output_tokens = 4096`
- 128 permits（`hard_team_call_permits=128`）+ `max_steps=128` + `max_provider_retries=1`
- `prompt_profile`/finding schema：`repository_v1`
- 除 Factor B 自身定义的 finalization gate 外，四条件工具能力一致

## 4. 预注册：matched seeds 与 run 计划

**决定（开跑前冻结）：3 matched seeds × 4 cells = 12 runs。** 依据：上一实验日已常规执行 16 个 live 128-permit run（每个 ~8–13M input / 13–27K output tokens），12 个 run 在既有成本模式内；用户优先目标为 3 matched seeds。**开跑后不得根据结果增删 seed。**

| seed | 值 |
|---|---|
| Seed A | `flowise-s1-completion-v2-seedA-20260919` |
| Seed B | `flowise-s1-completion-v2-seedB-20260919` |
| Seed C | `flowise-s1-completion-v2-seedC-20260919` |

每个 seed 内 run 顺序固定：none → guidance_only → scheduler_only_v2 → convergent_v2；seed 顺序 A → B → C。

### 成本上界（硬上界）

- permits：12 × 128 = **1536 attempted calls** 上限
- input tokens：≤ **180M**（15M/run，观测最差 12.96M）
- output tokens：≤ **768K**（64K/run，观测最差 26.6K）
- 墙钟：≤ 25 min/run

超限即停并报告，不自动续跑。provider failure 按 ADR-0002 有效性规则处理；infrastructure_invalid 的 run 补跑同一 seed 同一 condition 一次，仅限 infra 原因。

### 已知限制（预注册承认）

- seed 只记录于 manifest、不发给 API；provider 生成随机 tool_call ID 进入后续消息 → matched seed ≠ matched trajectory。本设计的价值在 run provenance 完整与跨条件配对记录，而非轨迹配对。
- 每格 n=3 仍小；主结论以机制层指标 + trace review 呈现，不做显著性检验。

## 5. 预注册主指标与假设

主指标（机制层，先于 TP）：

1. `first_convergence_step`（trace review 权威判定；transcript 正则命中仅为候选，`not_observed` 不猜测）
2. `exploration_calls_after_first_convergence`（dispatch 口径：read_file/list_files/run_shell/coordination 工具）
3. `first_submit_attempt_step` / `successful_submit_step` / submission completion；两个 gap（convergence→first submit、convergence→successful submit）
4. **hard-finalization binding rate**（scheduler_only_v2 与 convergent_v2 各自）：机械候选规则（finalization 前无收敛且无提交尝试 → binding；+ 窗口内 prohibited attempt → binding_strong；有收敛且已停探索/已提交 → non_binding；其余 ambiguous）+ 人工 trace review 终审
5. `prohibited_tool_attempts_after_finalization` 及 tool 名称分布

次级指标：TP/FN、finding count、unmatched/manual-review、calls consumed、unused permits、submission attempts、rejected/invalid submissions、ceiling hits（finish_reason=length 比例、p50/p90/p95/p99）、provider failures。

假设（H1–H6，逐条 supported / partially / not supported / unresolved + trace evidence）：H1 guidance 提高主动认知收敛发生率/更早；H2 hard finalization 提高 submission completion 但≠cognitive convergence；H3 scheduler_only_v2 的 binding rate 高于 convergent_v2；H4 convergent_v2 中 scheduler 主要 fail-safe；H5 interaction 主要体现为缩短 convergence→successful submission 距离；H6 none@128 仍持续探索而非主动完成。

**none@192 capacity probe 本轮不跑。** 触发条件（供下轮判断）：matched-seed none@128 多数 run 在 128 步附近仍持续探索、无收敛意图、无提交。

## 6. 旧世代处理

旧 2048 runs（advisory finalization）保持冻结：不重写、不重评分、不回填 matched block、不假装其 Factor B 是 hard gate。报告中仅作 historical diagnostic evidence。

## 7. Post-hoc classification-v2 amendment

正式 12-run 回溯后，`first_convergence_step` 的 trace-review 口径升级为 classification schema v2：cognitive convergence、behavioral stopping、submission completion 三者严格分离，并为首次 expression 记录 `spontaneous`、`guidance_consistent`、`nudge_induced`、`finalization_induced`、`ambiguous` 或 `not_observed` 来源。该勘误不修改本 prereg 的 run、events、transcripts、finding score 或原始 metrics；派生结果与 rubric 见 `docs/research/convergence-classification-v2-20260919.md`。因此本文件中 H1 的 prereg wording 不应被当作最终分类结果，最终表述以 classification-v2 amendment 和主报告勘误为准。

后续 S/P/B/T/M 共用的 completion primitives 已冻结于 `docs/research/common_runtime_contract_completion_v2.md`；该 contract 明确 `team completion trigger = TBD`，不把 S1 finalization timing 偷渡为 team semantics。
