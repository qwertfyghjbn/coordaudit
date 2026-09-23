# Flowise repository-v1 T4 post-sync-inspection-v2 @ 192

日期：2026-09-22  
冻结 block：`t4-post-sync-inspection-v2-192p`  
block manifest hash：`e1073af3d07d8984eb7f5f3f2dc2e71fe4ec8863f077d2ca8942b31d32a24828`  
matched seed：`t4-result-sync-v1-matched-seed-01`

## 结论

此单 seed 达到本诊断的 lifecycle 入选门槛：`run_validity=valid`、reconciliation valid、4/4 initial task 完成、`result_sync_v1` 触发且仅一次、四名 agent 均 clean submit、无 deadlock，实际使用 174/192 permits。

显式 post-sync inspection instruction 将本次 run 的 traceable inspection 提升到 4/4：每位 agent 都选择一个 foreign completed artifact，列出其 foreign evidence refs，并给出独立 relevance judgment。没有 post-inspection read/search，也没有 foreign evidence_ref 进入最终 finding。因此本轮定位到 **relevance/adoption**，而不是 runtime visibility 或 inspection。

这不是 security effectiveness 或 TP 提升结论。

## Frozen treatment

profile：`repository_v1_t4_post_sync_inspection_v2`。

它与 `repository_v1_t4_result_sync_v1` 的初始 system/user prompt 逐字相同；五点 inspection instruction 仅在 `RESULT_SYNC` user message 中加入。runtime、工具、decomposition、`initialization_lease_v1`、`task_closure_gate_v1`、192 permits、reserve=32、scheduler、model、seed、submission/completion/finalization semantics 均不变。

要求 inspection，但不要求 reuse、citation 或 finding change。

## Live lifecycle

正式计入 trace：[`matched-seed-01-replacement-01`](../../experiments/emergent_coordination/runs/t4-post-sync-inspection-v2-192p/matched-seed-01-replacement-01/summary.json)

| 项目 | 结果 |
| --- | --- |
| initial create / claim / complete | 4 / 4 / 4 |
| result_sync trigger | event `evt_00001196`，sequence 1196 |
| result_sync | `triggered=true`、`trigger_count=1`、`exactly_once=true` |
| team completion | `clean_complete`，4/4 submitted |
| permits | 174 used，18 remaining，hard limit 192 |
| team finalization | remaining=32 时 call index 161，exactly once |
| provider/reconciliation | 0 provider failure；both valid |

第一次启动 artifact [`matched-seed-01`](../../experiments/emergent_coordination/runs/t4-post-sync-inspection-v2-192p/matched-seed-01/summary.json) 因 CLI 未显式传入 contract permit cap 而实际使用 case 默认 64 permits，不满足 frozen 192-permit contract，故不计入 R0–R4。它保留为配置失配记录；正式 trace 使用同一 seed、显式 `--hard-team-call-permits 192` 的 replacement。

## R0–R4

| Outcome | Agents | Count |
| --- | --- | ---: |
| R0 foreign artifact not visible | — | 0 |
| R1 visible but not inspected | — | 0 |
| R2 inspected but not adopted | agent_001, agent_002, agent_003, agent_004 | 4 |
| R3 inspection guided post-sync read/search | — | 0 |
| R4 foreign evidence incorporated in final finding | — | 0 |

`list_tasks` 没有被计为 inspection 或 R3。本次四人都直接检查 runtime 注入的 raw snapshot；没有 post-sync list/read/search action。

## Foreign-evidence provenance

| Inspector | Selected foreign task (owner) | Inspected foreign refs | Final foreign refs |
| --- | --- | --- | --- |
| agent_001 | `task_491864a68d` (agent_004) | `evt_00001159`, `evt_00000350`, `evt_00000672` | none |
| agent_002 | `task_491864a68d` (agent_004) | `evt_00001159`, `evt_00000350`, `evt_00000672` | none |
| agent_003 | `task_35fdd9e249` (agent_001) | `evt_00001014`, `evt_00001016`, `evt_00000994`, `evt_00001165` | none |
| agent_004 | `task_e4bc9c125b` (agent_002) | `evt_00000960`, `evt_00001177`, `evt_00000148` | none |

四条 inspection record 均在 model-visible transcripts 中。最终 merged findings 的 evidence_refs 都属于各 finding 提交者自己的 task evidence；traceable foreign-evidence adoption count 为 0。

## Measurement note

首次 post-run trace review 发现 analyzer 的 `v2` parser 错误地将 response 中讨论的其他未采用任务也当作 selected task，因而漏计 agent_002。`result_inspection_trace_v2_1` 改为优先解析显式的 `Selected foreign task ID` 字段（允许其后讨论其他 artifact），并添加 Markdown label regression test。该修复只重放已有 transcript，未修改冻结 runtime treatment，未发起额外 provider call；正式 `metrics.json` 已按 v2.1 重写。

## Secondary outcomes and next bottleneck

Evaluator secondary output：1 TP / 19 FN，positive recall 0.05，5 unmatched manual-review items。它不用于判断本 treatment 成功。

在本 seed 中，强制 inspection 已达到 4/4，而 R3=R4=0：每位 agent 都明确说明 foreign result 不重叠、仅作 corroboration，或不采用其 evidence。下一瓶颈是 **relevance/adoption**。在不改 prompt 来追求 reuse 的前提下，若要检验 model-policy effect，可按原预注册补两个 matched seeds；不能据这一单 run 宣称 security effectiveness 改善。

## Artifacts

- Frozen [block manifest](../../experiments/emergent_coordination/runs/t4-post-sync-inspection-v2-192p/block_manifest.json)
- Final [summary](../../experiments/emergent_coordination/runs/t4-post-sync-inspection-v2-192p/matched-seed-01-replacement-01/summary.json) and [metrics](../../experiments/emergent_coordination/runs/t4-post-sync-inspection-v2-192p/matched-seed-01-replacement-01/metrics.json)
- Read-only [completion replay](../../experiments/emergent_coordination/runs/t4-post-sync-inspection-v2-192p/matched-seed-01-replacement-01/completion_path_replay.json) and [evidence-lineage replay](../../experiments/emergent_coordination/runs/t4-post-sync-inspection-v2-192p/matched-seed-01-replacement-01/evidence_lineage_replay.json)
