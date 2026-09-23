# Flowise repository-v1 T4 post-sync-relevance-v1：3 seed 结果

日期：2026-09-22  
冻结 block：`t4-post-sync-relevance-v1-192p`  
manifest SHA-256：`48767d25a0c2ed8526430f00d23489c73024f507382b4988e7a62a8404c2131b`  
预注册：[relevance v1](../research/t4-post-sync-relevance-v1-prereg-20260922.md)；人工规则：[manual adjudication v1](../research/t4-post-sync-inspection-manual-adjudication-v1-20260922.md)

## Scope

本 treatment 保持 `result_sync_v1`、`initialization_lease_v1`、`task_closure_gate_v1`、decomposition、模型、scheduler、tool schema、192 permits 和 reserve=32 不变。唯一改动是 RESULT_SYNC 后的 instruction：要求区分主题相近与具体 control/path/invariant/call relationship，并给出一个可改变结论的验证目标，或明确没有有用目标；不要求 reuse、引用或修改 finding。

seed 01 的首次 driver 输出被外层输出通道截断，留下无终态的 partial trace（无 `summary.json`），不进入统计。为保留该 trace，使用相同 frozen seed 写入 `matched-seed-01-replacement-01`；该 replacement 是表中 seed 01 的计入样本。

## Lifecycle validity

| Run | Seed | Validity / reconciliation | create / claim / complete | RESULT_SYNC | Team completion | Permits |
| --- | --- | --- | ---: | --- | --- | ---: |
| [seed 01 replacement](../../experiments/emergent_coordination/runs/t4-post-sync-relevance-v1-192p/matched-seed-01-replacement-01/summary.json) | `...-01` | valid / valid | 4 / 4 / 4 | once | clean, 4 submitted | 182 / 192 |
| [seed 02](../../experiments/emergent_coordination/runs/t4-post-sync-relevance-v1-192p/matched-seed-02/summary.json) | `...-02` | valid / valid | 4 / 4 / 4 | once | clean, 4 submitted | 184 / 192 |
| [seed 03](../../experiments/emergent_coordination/runs/t4-post-sync-relevance-v1-192p/matched-seed-03/summary.json) | `...-03` | valid / valid | 4 / 4 / 4 | once | clean, 4 submitted | 175 / 192 |

每个有效 run 都保留 192 hard cap、reserve=32，且 RESULT_SYNC 只触发一次。completion-path 与 evidence-lineage replay 均已在三个 run 上完成；replay 不调用 provider，未读取 hidden evaluator/GT。

## R0–R4 与 provenance

| Run | R0 | R1 | R2 | R3 | R4 |
| --- | ---: | ---: | ---: | ---: | ---: |
| seed 01 replacement | 0 | 0 | 4 | 0 | 0 |
| seed 02 | 0 | 0 | 4 | 0 | 0 |
| seed 03 | 0 | 0 | 4 | 0 | 0 |
| Total | 0 | 0 | 12 | 0 | 0 |

每位 agent 在同步后都看见 3 个 foreign completed tasks，并明确选中一个 artifact、其 result/provenance 中的 evidence refs 及 relevance judgment，因此为 R2。`foreign_evidence_incorporated=false` 对 12/12 成立，最终 finding 没有 foreign evidence ref；因此 R4=0。没有同步后的 read/search/test，现有机械 R3 规则也为 0。

这里“Supporting evidence_refs examined”只表示 agent 在 completed-task snapshot 中看见并讨论 ref；按冻结人工规则，只有同步后 `read_file` 实际读取对应正文才算 foreign evidence body read。本 treatment 中该数为 0/12。

## Manual relevance adjudication

每位 agent 只取首次实质 inspection record；之后为修正 finding schema 的重复提交记录不重复计数。`T` 表示 thematic-only，`D` 表示满足 direct-relation 规则，`A` 表示 actionable lead，`F` 表示实际 follow-through。

| Seed | Agent | Transcript | Selected | Relation | A | F | Foreign body read / incorporated |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 01r | agent_001 | `trn_agent_001_00000177` | `task_505da27efc` | T；另讨论 `task_a63e36bed3` 的直接 auth-control relation | yes | no | no / no |
| 01r | agent_002 | `trn_agent_002_00000163` | `task_505da27efc` | T | no | no | no / no |
| 01r | agent_003 | `trn_agent_003_00000145` | `task_a63e36bed3` | T | no | no | no / no |
| 01r | agent_004 | `trn_agent_004_00000136` | `task_a63e36bed3` | D | yes | no | no / no |
| 02 | agent_001 | `trn_agent_001_00000176` | `task_61e54bebc3` | T | no | no | no / no |
| 02 | agent_002 | `trn_agent_002_00000159` | `task_61e54bebc3` | T | no | no | no / no |
| 02 | agent_003 | `trn_agent_003_00000152` | `task_0e63986d8a` | T | no | no | no / no |
| 02 | agent_004 | `trn_agent_004_00000115` | `task_0e63986d8a` | T | no | no | no / no |
| 03 | agent_001 | `trn_agent_001_00000159` | `task_feeb6539bc` | T | no | no | no / no |
| 03 | agent_002 | `trn_agent_002_00000175` | `task_2a63b1b7c2` | D | yes | no | no / no |
| 03 | agent_003 | `trn_agent_003_00000116` | `task_2a63b1b7c2` | T | no | no | no / no |
| 03 | agent_004 | `trn_agent_004_00000123` | `task_53cb3d769a` | T | no | no | no / no |

聚合为：selected=12/12、foreign evidence body read=0/12、thematic-only=9/12、direct relation=3/12（其中一例是 seed 01 agent_001 对非 selected 的额外 foreign artifact）、actionable lead=3/12、follow-through=0/12、foreign evidence incorporated=0/12。九条记录明确为无直接关系，九条明确为无有用验证目标。

三个 actionable leads 都有具体目标和反事实判别条件：seed 01 agent_001 的 whitelist/controller/credential scoping，seed 01 agent_004 的 `validateFlowAPIKey` default-allow 可达性，seed 03 agent_002 的 global whitelist middleware 与 `validateAPIKey`。最后一例明确说 foreign auth-model result 将其候选从“未认证”重述为需 API-key/JWT 的 permission-scope gap；但没有 post-sync 工具动作、没有 foreign ref 进入 finding，故它是可追溯的模型陈述而不是 R3/R4 证据。

## Interpretation and secondary outcomes

结果排除 visibility 与 inspection 为当前瓶颈：completed artifacts 在最终提交前对所有其他 agents model-visible，且强制 inspection 为 12/12。relevance instruction 没有产生 provenance-complete R3/R4；其清楚可见的效果是从 v2 的 0 个 actionable lead 变为本 treatment 的 3 个。三 seed 的 direct-relation 数为 3，而 v2 为 5，样本太小且 agent outputs 有变异，不能据此宣称 direct-relation 提升。

当前下一个瓶颈是 **adoption/verification opportunity**，不是 runtime visibility：同步仍发生在 team finalization 激活后，所有 agent 都直接提交，因而没有可观察的 post-sync follow-through window。finding 数、severity 或 TP 不用于本实验成功判定；本报告不作 security-effectiveness 结论。

若继续推进，应另行冻结只改变 result-sync 后可执行验证窗口的 timing treatment，并保持本 relevance prompt、budget、reserve 与人工规则不变；不要以自动 merge、强制 reuse 或 prompt 反复调优替代该因果分离。

## Supporting artifacts

- seed 01 replacement：[metrics](../../experiments/emergent_coordination/runs/t4-post-sync-relevance-v1-192p/matched-seed-01-replacement-01/metrics.json)、[completion replay](../../experiments/emergent_coordination/runs/t4-post-sync-relevance-v1-192p/matched-seed-01-replacement-01/completion_path_replay.json)、[lineage replay](../../experiments/emergent_coordination/runs/t4-post-sync-relevance-v1-192p/matched-seed-01-replacement-01/evidence_lineage_replay.json)
- seed 02：[metrics](../../experiments/emergent_coordination/runs/t4-post-sync-relevance-v1-192p/matched-seed-02/metrics.json)、[completion replay](../../experiments/emergent_coordination/runs/t4-post-sync-relevance-v1-192p/matched-seed-02/completion_path_replay.json)、[lineage replay](../../experiments/emergent_coordination/runs/t4-post-sync-relevance-v1-192p/matched-seed-02/evidence_lineage_replay.json)
- seed 03：[metrics](../../experiments/emergent_coordination/runs/t4-post-sync-relevance-v1-192p/matched-seed-03/metrics.json)、[completion replay](../../experiments/emergent_coordination/runs/t4-post-sync-relevance-v1-192p/matched-seed-03/completion_path_replay.json)、[lineage replay](../../experiments/emergent_coordination/runs/t4-post-sync-relevance-v1-192p/matched-seed-03/evidence_lineage_replay.json)
