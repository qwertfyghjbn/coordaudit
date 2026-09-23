# T4 POST_SYNC window v1 预注册

日期：2026-09-22。实验身份：`t4-post-sync-window-v1-192p`。本文件只冻结下一次 T4 matched-seed 的 runtime contract 与分析门槛；不记录 live 结果，也不修改任何历史 frozen block 或 artifact。

## 审计结论与改动边界

当前 `result_sync_v1` 在所有 participating agent 的 initial claimed task 都完成时发出一次 `result_sync_triggered`，并在每个 agent 下一次 loop turn 用 `observe_result_sync` 把同一 raw completed-task snapshot 加入 user context。`task_closure_gate_v1` 只拒绝仍持有 claimed task 的 `submit_findings`；`initialization_lease_v1` 只串行首次 list/create/claim；两者均不定义 post-sync 行为。

旧 `team_finalization_reserve=32` 是 shared ledger 的阈值：剩余 permit 小于等于 32 时才开启 team finalization/tool gate。它不为任何 agent 预分配 permit，也不要求 RESULT_SYNC 后发生 provider request。因此 `t4-post-sync-verification-permission-v1` 的 matched-seed-01 可以在 RESULT_SYNC 后到达 192/192，四位 agent 的下一次请求全被 hard cap 拒绝；这是一条 opportunity-delivery failure trace，不能解释为拒绝 verification。

新 contract 保留 repository-v1 target、T4 size、`result_sync_v1` snapshot、foreign visibility、scheduler、ownership、lease、closure gate、finding schema、reconciliation、provider retry 和 permit-consumption 规则。唯一 runtime intervention 是 `t4_post_sync_window_v1`：在 RESULT_SYNC 之后给每名 eligible agent 一个中性 `POST_SYNC` execution window。它不是 inspection、relevance、verification 或 adoption 的 state；这些继续由 analyzer 与既有 manual adjudication 事后重建。

## 生命周期与 invariants

```text
INITIALIZING → ACTIVE → team closure satisfied → RESULT_SYNC → POST_SYNC → COMPLETE
```

`RESULT_SYNC` 是一次 transition/event；`POST_SYNC` 是唯一新增 execution window。实现的冻结 invariants：

1. 对每位 eligible T4 agent，snapshot 已 delivered、window opened、POST_SYNC instruction 写入 model request 后，至少一个 post-sync provider request 获得 admission。
2. 若该 agent 在其首次 POST_SYNC response 中自愿调用一次允许的 `read_file` verification action，runtime 阻止同一 response 的提交，并预留后续 provider request，将 tool result 回送给模型；该后续 request 只允许 final submission。
3. verification 始终可选。首次 POST_SYNC request 可直接 `submit_findings`；没有 `read_file`、没有 foreign reuse、没有 finding change 都是合法模型选择。

## Permit accounting

总预算仍为 192 个 attempted provider calls。4 名 T4 agent 各静态保留 4 个 permits，普通池为 176：

| 保留项（每 eligible agent） | permits | 原因 |
| --- | ---: | --- |
| 首次 POST_SYNC request 与现有一次 retry | 2 | provider timeout/error 仍消耗 permit，且 normal retry 语义不变 |
| verification evidence-consumption request 与现有一次 retry | 2 | `read_file` 后至少能请求模型观察结果；失败仍按同一 retry/consumption 规则处理 |

未使用的 agent reservation 不会转交给其他 agent，也不能在 ACTIVE/pre-sync 消耗。该设计没有扩大总预算；`team_finalization_reserve=32` 保留为原有 shared finalization threshold。运行 manifest、budget snapshot 和 permit ledger 会记录 `call_kind`、normal pool、每 agent window/attempt 状态，使 reconciliation 仍以 attempted call 为唯一硬单位。

## POST_SYNC envelope 和提示语义

raw foreign snapshot 已随 RESULT_SYNC 直接进入 context；首次窗口只 advertise/dispatch `read_file`、`submit_findings`，其中 `read_file` 是最多一次的窄 verification action。证据回传 request 只 advertise/dispatch `submit_findings`。`run_shell`、list_files、list_tasks、task create/claim/release/complete、message/delegate 和任何 broad exploration 均不可在窗口中调用。

提示语不采用线性 checklist。它要求模型自行查看 foreign artifacts、判断是否对自身 finding 具体相关；只有形成 decision-changing target 时才可选择一次 targeted read；随后可保持、修正或补充 finding，或认为证据足够而直接提交。runtime 不把任何这些选择变成 gate。

## 观测与分析

runtime provenance：`result_sync_triggered`、`post_sync_window_opened`、`post_sync_instruction_model_visible`、`post_sync_provider_call_admitted`、`verification_action_attempted`（含 target）、`verification_evidence_model_visible` 与既有 `finding_submitted`。`metrics.json` 明确区分 `no_post_sync_provider_opportunity` 与 `opportunity_delivered_model_chose_not_to_verify`。

`foreign_artifact_selected`、direct relevance、actionable verification lead、post-verification judgment 和 final adoption 不改为 runtime states。沿用 [manual adjudication v1](t4-post-sync-inspection-manual-adjudication-v1-20260922.md)：只有 model-visible transcript、tool result 与 final finding 可用于判定。`lead → verification action` 的分母为“actionable lead 且 post-sync opportunity delivered”的 agent，不是所有 agent。

## 执行计划与 admission gate

先执行零网络 unit/mock、deterministic replay、repository smoke 与 S/P/B/T mock preflight。随后仅运行一个 matched seed：`t4-result-sync-v1-matched-seed-01`，对照 verification-permission v1 的同 seed；不得在运行中调 prompt 或 budget。

该 seed 只有同时满足以下条件才可分析行为链：valid 且 reconciliation valid；4/4 initial closure；RESULT_SYNC exactly once；4/4 POST_SYNC window opened；4/4 instruction model-visible；4/4 provider call admitted；没有因缺 post-sync opportunity 造成的 forced completion。通过后才报告 `inspection → direct relevance → actionable lead → verification opportunity → verification action → judgment update → final adoption`。若首 seed 合格，再按同一冻结 contract 顺序运行 `...-02` 与 `...-03`。
