# Flowise repository-v1 T4 post-sync-inspection-v2：3 seed follow-up

日期：2026-09-22  
冻结 block：`t4-post-sync-inspection-v2-192p`  
manual adjudication protocol：[v1](../research/t4-post-sync-inspection-manual-adjudication-v1-20260922.md)

## Scope

在已完成的 matched-seed-01-replacement-01 之后，以相同的 `repository_v1_t4_post_sync_inspection_v2` treatment 补跑 matched seeds 02 和 03。模型、192 permits、reserve=32、`initialization_lease_v1`、`task_closure_gate_v1`、`result_sync_v1`、scheduler、tool surface 和 finalization semantics 均保持与冻结 block 一致。

## Lifecycle validity

| Run | Seed | Validity / reconciliation | create / claim / complete | RESULT_SYNC | Team completion | Permits |
| --- | --- | --- | ---: | --- | --- | ---: |
| [seed 01 replacement](../../experiments/emergent_coordination/runs/t4-post-sync-inspection-v2-192p/matched-seed-01-replacement-01/summary.json) | `...-01` | valid / valid | 4 / 4 / 4 | once | clean, 4 submitted | 174 / 192 |
| [seed 02](../../experiments/emergent_coordination/runs/t4-post-sync-inspection-v2-192p/matched-seed-02/summary.json) | `...-02` | valid / valid | 4 / 4 / 4 | once | clean, 4 submitted | 184 / 192 |
| [seed 03](../../experiments/emergent_coordination/runs/t4-post-sync-inspection-v2-192p/matched-seed-03/summary.json) | `...-03` | valid / valid | 4 / 4 / 4 | once | clean, 4 submitted | 174 / 192 |

每个有效 run 都在 team finalization 后达到 result sync；每位 agent 的同步后下一模型回应直接提交 findings。没有同步后的 `read_file`、`list_files` 或 `run_shell`。

## R0–R4

| Run | R0 | R1 | R2 | R3 | R4 |
| --- | ---: | ---: | ---: | ---: | ---: |
| seed 01 replacement | 0 | 0 | 4 | 0 | 0 |
| seed 02 | 0 | 0 | 4 | 0 | 0 |
| seed 03 | 0 | 0 | 4 | 0 | 0 |
| Total | 0 | 0 | 12 | 0 | 0 |

R2 在此处表示模型留下了 selected foreign task、foreign refs 和 relevance judgment 的可追溯记录；它不证明 evidence body 已被读取，也不证明没有任何认知影响。

## Manual relevance adjudication

| Run | Selected artifact | Foreign evidence body read | Thematic relation only | Direct relation | Actionable lead | Follow-through | Foreign evidence incorporated |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| seed 01 replacement | 4 | 0 | 3 | 1 | 0 | 0 | 0 |
| seed 02 | 4 | 0 | 2 | 2 | 0 | 0 | 0 |
| seed 03 | 4 | 0 | 2 | 2 | 0 | 0 | 0 |
| Total | 12 | 0 | 7 | 5 | 0 | 0 | 0 |

“Direct relation” 的五个实例分别是：

1. seed 01 agent_004：foreign SSRF guard conclusion 与自身 raw `fetch()` bypass 的 control relationship；
2. seed 02 agent_002：foreign unscoped credential lookup 与自身 `workspaceId` 缺失查找的关系；
3. seed 02 agent_004：foreign global route-auth observation 与自身缺失 permission/tenant guard 的关系；
4. seed 03 agent_001：foreign public file-download weakness 与自身 `WHITELIST_URLS` trust-boundary finding 的关系；
5. seed 03 agent_002：foreign whitelist/unscoped-route result 与自身 listener unscoped authorization finding 的关系。

这些 relation 都来自 model-visible inspection responses；没有一条提出“读取某文件、搜索某调用点或执行测试以区分结论”的具体后续动作。没有 agent 在 result sync 后读取所选 foreign refs 对应的文件正文。结果与 action 的时间关系在各 run 中都是：result sync → inspection response → submit。

## Interpretation

三 seed 稳定证明该 prompt treatment 能让每个 agent 在最终提交前选择并评论 foreign completed artifact。它还显示模型可以指出具体 control/path relationship：12 条中 5 条达到 manual v1 的 direct relation。

当前设计无法检验这些关系是否会转化为验证行动：同步发生在 team finalization 已激活时，而各 agent 的下一回合都选择提交。R3=0 因而同时包含模型未提出 actionable lead 和没有可用的 post-sync exploration window 两个因素。R4=0 表明没有 foreign evidence_ref 被纳入最终 finding；它不排除 foreign result 对 confidence 或 framing 的影响。

下一实验若要推进到 verification/adoption，应把“关系识别”和“结果同步后可执行验证”分开处理：保持本轮 prompt 和标注规则，另行冻结一个只改变 sync/finalization timing 的 treatment，再测 actionable lead、follow-through、R3 与 R4。不能将这三个 seed 用作该 timing treatment 的替代证据。

## Supporting artifacts

- seed 02 [metrics](../../experiments/emergent_coordination/runs/t4-post-sync-inspection-v2-192p/matched-seed-02/metrics.json)、[completion replay](../../experiments/emergent_coordination/runs/t4-post-sync-inspection-v2-192p/matched-seed-02/completion_path_replay.json)、[lineage replay](../../experiments/emergent_coordination/runs/t4-post-sync-inspection-v2-192p/matched-seed-02/evidence_lineage_replay.json)
- seed 03 [metrics](../../experiments/emergent_coordination/runs/t4-post-sync-inspection-v2-192p/matched-seed-03/metrics.json)、[completion replay](../../experiments/emergent_coordination/runs/t4-post-sync-inspection-v2-192p/matched-seed-03/completion_path_replay.json)、[lineage replay](../../experiments/emergent_coordination/runs/t4-post-sync-inspection-v2-192p/matched-seed-03/evidence_lineage_replay.json)
