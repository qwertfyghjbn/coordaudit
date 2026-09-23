# Flowise repository-v1 T4 post-sync-verification-permission-v1：3 seed 结果

日期：2026-09-22  
冻结 block：`t4-post-sync-verification-permission-v1-192p`  
manifest SHA-256：`426ffd32e0533bd8705856bb904bddefafba15bfeee5b07616ce904b89ca79a0`  
预注册：[verification permission v1](../research/t4-post-sync-verification-permission-v1-prereg-20260922.md)

## Scope

本 treatment 保留 relevance v1 的初始 prompt、RESULT_SYNC snapshot、inspection/relevance instruction、`result_sync_v1`、`initialization_lease_v1`、`task_closure_gate_v1`、scheduler、tool schema、192 permits 和 reserve=32。唯一改动为 RESULT_SYNC 后说明：若已形成具体 foreign verification target，可在提交前自愿执行一次有界、目标匹配的验证动作。

finalization 中现有 `read_file` 仍可用，`run_shell` 不可用；新文字明确前者也可用于 foreign cross-check。该 profile 不增加 permit、不改变 runtime 工具门禁或保留 post-sync 调用窗口。

## Lifecycle 与 permission delivery

| Run | Validity / reconciliation | Team completion | create / claim / complete | Calls | RESULT_SYNC | Permission delivered to model |
| --- | --- | --- | ---: | ---: | --- | ---: |
| [seed 01](../../experiments/emergent_coordination/runs/t4-post-sync-verification-permission-v1-192p/matched-seed-01/summary.json) | valid / valid | forced_complete | 4 / 4 / 4 | 192 / 192 | once | 0 / 4 |
| [seed 02](../../experiments/emergent_coordination/runs/t4-post-sync-verification-permission-v1-192p/matched-seed-02/summary.json) | valid / valid | clean_complete | 4 / 4 / 4 | 172 / 192 | once | 4 / 4 |
| [seed 03](../../experiments/emergent_coordination/runs/t4-post-sync-verification-permission-v1-192p/matched-seed-03/summary.json) | valid / valid | clean_complete | 4 / 4 / 4 | 187 / 192 | once | 4 / 4 |

三个 run 均保留 reserve=32，task closure 有效，RESULT_SYNC only once。seed 01 的四项 initial task 都完成且同步触发，但同步后每个 agent 的下一次 permit 请求均被 hard cap 拒绝；没有任何 post-sync provider call。因此 permission 没有进入 model-visible request，不能用于判断 `actionable lead → verification action`。这是一条 opportunity-delivery failure trace，不是 agent 拒绝验证的证据。

seed 02/03 每位 agent 的同步后 request 都以 permission instruction 为最后一条 user message；其可用工具包括 `read_file`，不包括 `run_shell`。两个 eligible run 均无 deadlock。

## R0–R4 与 provenance

| Run | R0 | R1 | R2 | R3 | R4 |
| --- | ---: | ---: | ---: | ---: | ---: |
| seed 01 | 0 | 4 | 0 | 0 | 0 |
| seed 02 | 0 | 0 | 4 | 0 | 0 |
| seed 03 | 0 | 0 | 4 | 0 | 0 |

seed 01 的 R1 是未获得 post-sync 模型调用的机械结果，不解释为 inspection failure。seed 02/03 的 8 位 agent 都明确选中 foreign artifact 并作出判断，故为 R2。同步后没有 target-aligned `read_file`、没有 foreign evidence body read，最终 finding 没有 foreign evidence ref，因此 R3/R4 均为 0。

## 条件转移人工复核

仅对 permission 实际投递的 seed 02/03 计入条件分母。每位 agent 取首次实质 inspection record；重试 finding schema 的重复 record 不重复计数。判定遵循 [manual adjudication v1](../research/t4-post-sync-inspection-manual-adjudication-v1-20260922.md) 和本轮预注册。

| Run | Inspection | Direct relation | Actionable lead | Target-aligned verification | Judgment update after verification | Final adoption |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| seed 02 | 4 | 0 | 0 | 0 | 0 | 0 |
| seed 03 | 4 | 1 | 1 | 0 | 0 | 0 |
| Eligible total | 8 | 1 | 1 | 0 | 0 | 0 |

对应的条件比例为：

| Transition | Numerator / denominator |
| --- | --- |
| inspection → direct relevance | 1 / 8 |
| direct relevance → actionable lead | 1 / 1 |
| actionable lead → target-aligned verification action | 0 / 1 |
| verification action → judgment update | 0 / 0 |
| judgment update → final adoption | 0 / 0 |

唯一 actionable lead 来自 seed 03 `agent_004` 的 `trn_agent_004_00000165`：它将 foreign sibling handler 与自身 handler 关联到相同的 `streamStorageFile` sink，并提出读取该函数以判定是否存在 per-chatflow ownership/secret check。agent 明确表示既有静态证据足够、不会花这次允许的读取；其随后重试 submission 的 record 也保持同一判断。它声称 finding 的 severity framing 应收窄，但没有 verification action 或 foreign ref adoption，因此不记为 post-verification update、R3 或 R4。

## Interpretation

本轮没有观察到 permission-only instruction 将 actionable lead 转为验证动作：可分析分母为 1，结果为 0/1。它不支持把此前的 0 行动归因于 permission 文本本身，因为 seed 01 没有 delivery，且 seed 02/03 仅产生一个 lead。它说明在 agent 已看见 permission、`read_file` 也确实可用的情况下，单纯澄清许可仍不足以使这一个 lead 被执行。

下一步应冻结一个独立的 post-sync verification-window/timing treatment：保留本轮 permission prompt、192 permits、reserve=32、工具和人工规则，为 RESULT_SYNC 后提供显式的可执行验证阶段或预留调用，再测 `lead → action`。只有这种窗口也存在且仍无 follow-through，才能将瓶颈更有把握地推进到 model policy / adoption decision。

## Supporting artifacts

- seed 01：[metrics](../../experiments/emergent_coordination/runs/t4-post-sync-verification-permission-v1-192p/matched-seed-01/metrics.json)、[completion replay](../../experiments/emergent_coordination/runs/t4-post-sync-verification-permission-v1-192p/matched-seed-01/completion_path_replay.json)、[lineage replay](../../experiments/emergent_coordination/runs/t4-post-sync-verification-permission-v1-192p/matched-seed-01/evidence_lineage_replay.json)
- seed 02：[metrics](../../experiments/emergent_coordination/runs/t4-post-sync-verification-permission-v1-192p/matched-seed-02/metrics.json)、[completion replay](../../experiments/emergent_coordination/runs/t4-post-sync-verification-permission-v1-192p/matched-seed-02/completion_path_replay.json)、[lineage replay](../../experiments/emergent_coordination/runs/t4-post-sync-verification-permission-v1-192p/matched-seed-02/evidence_lineage_replay.json)
- seed 03：[metrics](../../experiments/emergent_coordination/runs/t4-post-sync-verification-permission-v1-192p/matched-seed-03/metrics.json)、[completion replay](../../experiments/emergent_coordination/runs/t4-post-sync-verification-permission-v1-192p/matched-seed-03/completion_path_replay.json)、[lineage replay](../../experiments/emergent_coordination/runs/t4-post-sync-verification-permission-v1-192p/matched-seed-03/evidence_lineage_replay.json)
