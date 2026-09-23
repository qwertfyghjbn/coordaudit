# Flowise repository-v1 T4 result-inspection-prompt-v1 @ 192

日期：2026-09-21  
冻结 block：`t4-result-inspection-prompt-v1-192p`  
最终 manifest hash：`98e80e8bf961be345dc84f1cf0fc15d22f47249c80164c1220388b79fdf245cb`  
matched seed：`t4-result-sync-v1-matched-seed-01`

## 结论状态

冻结和代码回归成功，但本轮没有产生可解释的 R0–R4 live outcome：两个同 seed 尝试都没有触发 `result_sync_v1`，因此 analyzer 中的 `R0` 只是“同步未到达”的机械占位，不是 visibility failure。

主 replacement trace 的状态是：192/192 permits exhausted、team forced complete、只有 agent_004 submitted、`result_sync_triggered=0`。由于 result synchronization 没有发生，不能判断 inspection、relevance、adoption 或 cross-agent information flow，也不补第三个 seed。

## Frozen treatment

新的 prompt profile 是 [`repository_v1_t4_result_inspection_prompt_v1`](../../experiments/emergent_coordination/harness/prompts.py)，只替换 result-sync 后的 system instruction：

1. 至少检查一个其他 agent owned 的 completed task；
2. 选择对当前 security reasoning 最相关的 artifact，而非任意选择；
3. 检查 result 和 supporting evidence；
4. 独立判断其改变、加强、反驳或与当前工作无关；
5. 不理解 foreign evidence 支持内容时不得纳入。

没有要求 reuse、citation 或 finding change。tool schema、raw result-sync message、runtime barrier、decomposition、task lifecycle、sequencing、closure、model、seed strategy、scheduler、192 permits、reserve=32 和 finalization semantics 均保持 matched。

为了兼容既有 `task_closure_gate_v1`，新 prompt profile 仅被加入 AgentRunner 原有的 task-lifecycle finalization allowlist；没有增加工具或放宽 hard finalization gate。这是 profile 接入修复，不是 treatment capability。

## Tests

- result-sync/prompt/contract targeted tests：`36 passed`；
- 全套 harness：`262 passed, 4 subtests passed`；
- `git diff --check`：通过；
- 新 profile 与旧 result-sync profile 的 structured-team tool names 完全相同；
- contract 验证 192 permits、reserve=32、`initialization_lease_v1`、`task_closure_gate_v1`、`result_sync_v1` 和 T4-only 条件。

## Live traces

### 首次尝试：`matched-seed-01`

该 trace 发现一个接入遗漏：新 profile 未进入 AgentRunner 的既有 task-lifecycle allowlist。team finalization 开始后，agent_003/004 的合法 `complete_task` 被 hard finalization gate 拒绝；只有 2/4 initial tasks completed，result sync 未触发，192 permits 用尽。该 trace 不纳入主结果。

### Replacement：`matched-seed-01-replacement-01`

修复 allowlist 后，仍未形成 valid diagnostic：

- 192/192 permits used；
- team finalization 在 remaining=32、call index=161 exactly once 触发；
- 3 个 tasks created/claimed/completed；agent_004 没有 initial claim，直接提交；
- 其余 agents 在 `result_sync_pending` 状态下继续消耗 permit；
- `result_sync_triggered=0`、`result_sync_observed=0`；
- team completion 为 `forced_complete`，3 个 agent `budget_exhausted`，仅 agent_004 submitted；
- 没有 provider failure，transcript reconciliation valid，但语义上不满足 4-agent matched closure/sync 条件。

因此 replacement 仍是 infrastructure/semantic invalid for this diagnostic，而不是 R0。

## R0–R4

| outcome | 可解释统计 |
| --- | ---: |
| R0：foreign artifact not visible | 不适用；同步未触发 |
| R1：visible but not inspected | 不适用 |
| R2：inspected but not used | 不适用 |
| R3：inspection changed search/reasoning | 不适用 |
| R4：foreign evidence in final finding | 不适用 |

`metrics.json` 中的 `R0=4` 表示每个 agent 都没有 `result_sync_observed`，不能据此归因于 visibility implementation failure。

## Diagnosis

当前最先出现的瓶颈是 treatment 下的 completion/scheduling validity，而不是 inspection/adoption：prompt 要求本身改变了模型调用轨迹，导致在固定 192 permits 和 reserve=32 下，部分 agent 没有在同步前完成 initial task lifecycle，另一个 agent 没有 claim task 即提交。由于同步前提未满足，不能观察用户本轮想区分的 R1→R2 转换。

本轮不引入 `inspection_gate_v1`：它只适用于“同步已发生但明确 inspection instruction 仍被忽略”的 valid trace；本轮尚未到达该判断条件。

正式 block manifest：[`block_manifest.json`](../../experiments/emergent_coordination/runs/t4-result-inspection-prompt-v1-192p/block_manifest.json)  
首次 invalid trace：[`matched-seed-01`](../../experiments/emergent_coordination/runs/t4-result-inspection-prompt-v1-192p/matched-seed-01/summary.json)  
replacement trace：[`matched-seed-01-replacement-01`](../../experiments/emergent_coordination/runs/t4-result-inspection-prompt-v1-192p/matched-seed-01-replacement-01/summary.json)
