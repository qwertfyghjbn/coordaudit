# T4 sequenced-bootstrap v1 corrected：3-seed matched diagnostic（2026-09-21）

## 预注册状态

本文件在补跑两个 seed 前建立。既有 `t4-sequenced-bootstrap-v1-corrected-192p` 保持 immutable，作为 seed-01；其 manifest hash 为
`1f1780996da420d5504efd3ed98fd97536f73abbe8f4da7d68df879a7e431fb5`。
三 seed 的合同冻结副本为 `t4-sequenced-bootstrap-v1-corrected-3seed-192p`，manifest hash 为
`b8d0e0718d59371895dc57a1af997e95f4406faa957146f2661147f8cd17ef6e`。

除 seed label 外，三个 run 共享同一 frozen contract：

- case：`flowise_3_1_3_repository_v1`，condition：T4 / 4 agents；
- model：`deepseek-flash`，`openai_compatible`，thinking disabled，temperature 0；
- `max_output_tokens=4096`，`max_steps=96`，`hard_team_call_permits=192`；
- `completion_policy=convergent_v2`，`team_completion_policy=all_agents_terminal_v1`；
- `team_finalization_policy=team_remaining_permits_v1`，`team_finalization_reserve=32`；
- `task_board_sequencing_policy=initialization_lease_v1`；
- prompt、tool schema、scheduler、retry、wall-clock、target、evaluator 和 finding schema 不变。

## Seed set（开跑前冻结）

| seed | run artifact |
|---|---|
| `n4-flowise-completion-calibration-v2-96p`（既有 corrected run） | `t4-sequenced-bootstrap-v1-corrected-192p/formal_t4-sequenced-bootstrap-v1-corrected` |
| `t4-sequenced-bootstrap-v1-corrected-192p-replicate-02` | `t4-sequenced-bootstrap-v1-corrected-3seed-192p/formal_seed-02` |
| `t4-sequenced-bootstrap-v1-corrected-192p-replicate-03` | `t4-sequenced-bootstrap-v1-corrected-3seed-192p/formal_seed-03` |

执行顺序固定为 seed-02 后 seed-03；不因中间结果修改 seed、预算、prompt、tools、scheduler、sequencing 或 completion semantics。Provider 不接收 API-level seed；这些值是 run provenance / matched diagnostic identity，不声称控制 provider trajectory。

## Primary outcomes（预注册）

1. `visible_tasks_at_decision`：每个 agent 首次 task decision 时观察到的 board task count，重点检验是否形成 `0→1→2→3` 可见性阶梯；
2. task scope overlap / decomposition quality；
3. duplicate ratio（文件与 aggregate，沿用 metrics schema）；
4. `create_task` / `claim_task` / `complete_task` 及 lease 顺序；
5. completed artifacts、`evidence_refs` 和 evidence reuse；
6. agent-001 等 `claimed_without_completion` 是否跨 seed 重复。

Finding count / TP / FN / unmatched 仅作 secondary outcomes，不作为本 diagnostic 的 primary success criterion。

## Analysis rule

只有当三个 seed 均为 infrastructure-valid，才汇总 primary outcomes；若出现 infrastructure-invalid，按既有 replacement contract 处理并保留原始 artifact，不为科学结果补跑。最终解释优先回答 sequencing visibility、scope overlap 和 task lifecycle，不把 finding/TP 差异解释为架构优劣。

## Live results

三条 run 均为 infrastructure-valid，且没有 provider failure。原始 artifact 保持在：

- [seed-01 corrected run](../../experiments/emergent_coordination/runs/t4-sequenced-bootstrap-v1-corrected-192p/formal_t4-sequenced-bootstrap-v1-corrected/metrics.json)
- [seed-02](../../experiments/emergent_coordination/runs/t4-sequenced-bootstrap-v1-corrected-3seed-192p/formal_seed-02/metrics.json)
- [seed-03](../../experiments/emergent_coordination/runs/t4-sequenced-bootstrap-v1-corrected-3seed-192p/formal_seed-03/metrics.json)

执行记录：seed-02 的外层启动脚本在 run 已完整落盘后只因读取不存在的摘要键而返回非零；`summary.json`、`metrics.json`、reconciliation 和 evaluator 结果均完整且 valid，因此不构成 run-level infrastructure invalid。

### Primary metrics

| seed | attempted calls | visible_tasks_at_decision | create / claim / complete | completed artifacts with evidence_refs | unfinished claimed task | file duplicate ratio | aggregate duplicate ratio |
|---|---:|---|---:|---:|---|---:|---:|
| seed-01 | 174 | 0→1→2→3 | 4 / 4 / 3 | 3 / 3 | agent_001 | 0.1912 | 0.1699 |
| seed-02 | 174 | 0→1→2→3 | 4 / 4 / 3 | 3 / 3 | agent_003 | 0.3333 | 0.3209 |
| seed-03 | 169 | 0→1→2→3 | 4 / 4 / 4 | 4 / 4 | none | 0.1508 | 0.1357 |

所有 seed 的 initialization lease 都是 `agent_001 → agent_002 → agent_003 → agent_004`，并且 `team_finalization` 都在 call 161、remaining permits=32、exactly once 触发；没有 completion regression。三个 seed 的 task-result evidence adoption 均为 0。

### Scope overlap / decomposition

三条 trace 的 task description fingerprint 均为 4 个 unique / 0 个 exact duplicate。语义层面仍需按 task JSON 阅读，而不能把 fingerprint 当作 overlap 证明：

- seed-01 形成 routes/controllers、server security utilities、server services、enterprise SSO/RBAC 四个相对清晰的 subsystem/layer scope；
- seed-02 的 agent_001 使用了较宽的 routes/controllers/services scope，与 credential/auth、MCP/webhook、file-handling 三个邻域存在残余边界重叠；
- seed-03 分成 server routes/controllers、components nodes、services/utils/middleware、enterprise 四个主要区域，边界最清晰。

作为描述性对照，旧 T4-task-lifecycle 的 file/aggregate duplicate ratio 是 `0.4833 / 0.4531`，旧 T4-nonoverlap 是 `0.4531`；三 seed 的 file ratio 全部低于这些值，均值为 `0.2251`，aggregate 均值为 `0.2088`。这支持 sequencing primitive 改善可见性并通常降低重复工作，但 n=3 只作 matched diagnostic evidence，不做显著性检验或 architecture ranking。

### Claimed-without-completion

`claimed_without_completion` 没有在三个 seed 中稳定固定到同一个 agent：seed-01 为 agent_001，seed-02 为 agent_003，seed-03 为 0/4。因而这是仍存在的模型 lifecycle-compliance 随机性（2/3 seed 各有一个未完成 task），不是 initialization-lease race；completed task 的 evidence_refs 在三个 seed 中均非空。

### Secondary finding outcome

merged findings / formal TP 分别为 seed-01 `4 / 0`、seed-02 `5 / 0`、seed-03 `9 / 0`。这些数只作为 secondary observation，不用于判断 sequencing 或 task-board effectiveness。

## 结论

本次 3-seed diagnostic 达到预注册的核心可解释性门槛：三个 seed 均重现 `0→1→2→3` 的 deterministic board visibility，且相对两个历史 T4 prompt-only/lifecycle 对照，三个 seed 的文件重复率都更低。由此，`initialization_lease_v1` 对消除首次 `list_tasks → create_task` race、改善自然 decomposition 的证据明显强于单条 trace。

但 task lifecycle 尚未完全稳定：2/3 seed 仍各留下一个 claimed task，且没有任何 seed 观察到 completed-artifact evidence reuse。下一步应把 completion-before-submit compliance / evidence adoption 单独作为 lifecycle diagnostic，不应把它与 sequencing visibility 或 finding/TP 混合解释。
