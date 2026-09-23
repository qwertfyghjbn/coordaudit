# T4 POST_SYNC window v2 预注册

日期：2026-09-22。版本：`t4-post-sync-window-v2-192p`。本文件在任何 v2 live provider call 前冻结。v1 首 seed 的诊断见 [seed 01 诊断](../releases/flowise-3.1.3-repository-v1-t4-post-sync-window-v1-seed01-diagnostic-20260922.md)。v1 block 和运行产物保持原样；v2 是独立 treatment，不合并两版的行为计数。

## 修改的事实依据

v1 matched seed 01 的 runtime admission 全部通过，但 `agent_001` 读取 foreign 相关文件后又请求第二次 read，`agent_002` 的首次 submit 参数为无效 JSON；二者均无受限提交修复 request。v1 prompt 同时继承“Inspection is required”、强制的可见 inspection record/relevance 语句，并称 `list_tasks` 可用，与实际 POST_SYNC envelope 不一致。v2 只修正这两个问题。

## 冻结模型与预算

生命周期仍为 `INITIALIZING → ACTIVE → RESULT_SYNC → POST_SYNC → COMPLETE`。`RESULT_SYNC` 是一次 snapshot transition；`POST_SYNC` 是唯一行为机会窗口。`inspection`、`direct relevance`、`verification`、`judgment`、`adoption` 仍是模型选择和事后分析标签，不是 runtime state。内部 `open_initial`、`awaiting_verification_evidence`、`submit_only` 仅为工具/permit guard；`submit_only` 只允许提交或修复提交格式。

总硬预算仍是 192 attempted provider calls，team finalization reserve 仍是 32 threshold。4 名 eligible T4 agent 各保留 4 permits；普通池 176。首次 POST_SYNC 请求最多 2 次 provider attempts（含现有一次 retry）；若自愿选择一次 `read_file`，证据消费请求最多 2 次 attempts。成功请求少用的本 agent 保留 permits 可用于 `submit_findings` 专用修复调用，且每个修复请求沿用同一 provider retry/permit-consumption 规则。任何 agent 不能借用另一名 agent 的 reservation；总共仍不得超过 4 个本 agent POST_SYNC attempts 或 192 个 team attempts。provider timeout/error 消耗 permit，不退款、不增加特殊重试。

## POST_SYNC contract

1. 每位 eligible agent 必须先收到同一 raw foreign snapshot 与中性 POST_SYNC 指令，再至少有一个请求获得 provider admission；ACTIVE 无权消耗其 reservation。
2. 首次 request 可直接 `submit_findings`，也可自愿选择一次定向 `read_file`。如果读取发生，后续受保留预算保护的 provider request 必须能看到工具结果；该 request 只提供 `submit_findings`。
3. 成功读取后若模型要求第二次 read，dispatch 拒绝且不更改 ownership/scheduler；只要本 agent reservation 尚有余额，下一次 request 只提供 `submit_findings`，可根据已见证据收束。无效提交参数或无工具的文字回应也可进入同一有界提交修复路径。
4. 不强制 inspection、relevance、verification 或 foreign adoption；`read_file` 不是提交前置条件。`run_shell`、`list_files`、`list_tasks`、create/claim/delegate 和其他 coordination mutation 不在 POST_SYNC envelope 中。

新提示只说明 shared snapshot、具体相关性、自愿的一次定向读取、保持/修正/补充 finding 和直接提交的选择，不继承历史强制 inspection/relevance 指令，不声称 `list_tasks` 可用。模型每次请求实际可用的 tool schema 与 dispatch guard 必须一致。

## 分析与 admission

沿用 [manual adjudication v1](t4-post-sync-inspection-manual-adjudication-v1-20260922.md)，逐 agent 记录 foreign selection、body read、thematic/direct relation、actionable lead、target-aligned follow-through、post-evidence judgment 与 foreign evidence adoption。runtime 另外记录同步、window、instruction visible、provider admitted、verification attempted/evidence visible、submit 与 terminal reason。无 opportunity 与自愿不验证必须分开。`lead → verification` 的分母仅是 actionable lead 且 opportunity delivered 的 agent。

先通过静态路径审计、unit/mock、deterministic T4 replay、repository smoke 和 S/P/B/T 零网络 preflight，再运行一个 v2 matched seed 01；通过后才规划 seed 02/03。v2 admission：valid/reconciliation valid、4/4 initial task closure、RESULT_SYNC exactly once、4/4 window opened、4/4 instruction model-visible、4/4 首次 provider admitted、无因缺 POST_SYNC opportunity 导致的 forced completion。另单独报告 4/4 final submit 比例及提交修复使用情况；提交成功不是把 verification 强制化的 admission 条件。先过 admission，后分析行为链。

固定不变：repository-v1 target、T4 team size、result sync snapshot/foreign visibility、initialization lease、task closure gate、scheduler/ownership、finding schema、reconciliation、模型和最大输出、192 permits、32 finalization threshold、provider retry/consumption、人工判定定义。比较对象是 v1 seed 01 诊断与同 seed 的 permission v1；提示和有界收尾 guard 是 v2 的两项明确 intervention，不能从单个 seed 将二者的效果分离。
