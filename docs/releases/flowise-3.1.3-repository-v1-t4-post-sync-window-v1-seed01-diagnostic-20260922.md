# T4 POST_SYNC window v1：matched seed 01 诊断与逐 agent 人工判定

日期：2026-09-22。实验 block：`t4-post-sync-window-v1-192p`。有效运行是 `matched-seed-01-replacement-03`；此前两份同 seed 的中断目录均不是有效结果。本文件只评价已有运行，不更改 v1 frozen manifest、历史运行产物或 manual adjudication v1 定义。

## 总判定

**机会保证通过，完整 reuse 未闭环。** [summary](../../experiments/emergent_coordination/runs/t4-post-sync-window-v1-192p/matched-seed-01-replacement-03/summary.json) 为 valid，reconciliation valid；4/4 initial task closure，`RESULT_SYNC` exactly once；4/4 POST_SYNC window opened、instruction model-visible、首次 provider call admitted。180/192 个 permit 被使用，没有 provider failure。旧 verification-permission v1 的 matched seed 01 在同步后是 0/4 request admitted；本次解决了该机会缺失问题。

Team completion 仍为 `forced_complete`：`agent_001`、`agent_002` 因 post-sync 收尾未提交而结束；`agent_003`、`agent_004` submitted。未用 12 permits 中，11 个属于按 agent 隔离但 v1 无提交修复路径的 POST_SYNC reservation，1 个属于普通池。这个结果不能说成“因缺首次 POST_SYNC 机会强制结束”。

## 逐 agent 判定

判定沿用 [manual adjudication v1](../research/t4-post-sync-inspection-manual-adjudication-v1-20260922.md)：只看 model-visible transcript、工具结果、final finding 与事件。`foreign evidence body read` 仅在同步后读取 foreign `evidence_ref` 对应文件正文时为是；仅在文字中列 ref 不算。以下 transcript ID 均位于本 run 的 `logs/transcripts/`。

| Agent | foreign selection / body read | relation / actionable lead | follow-through / evidence visible | post-evidence judgment / final adoption |
| --- | --- | --- | --- | --- |
| `agent_001` | 选 `task_79118a4016`；读了 foreign ref `evt_00001197` 对应的 `target/packages/server/src/index.ts` 正文 | 直接相关：foreign middleware 顺序和 whitelist 判定会影响自身 OAuth callback 的 unauthenticated-reachability 前提；提出读取 `index.ts` 区分结论 | 是：`evt_00001270`–`evt_00001272`，后续 request `evt_00001277` 已可见证据 | `trn_agent_001_00000174` 解释了 middleware，但仍要再查 whitelist 常量，结论未收束；第二次 read 被拒 `evt_00001286`，无 final submit、无 adoption。机械 R3。 |
| `agent_002` | 选 `task_79118a4016`；未读 foreign 文件正文 | 仅主题相邻：foreign XSS/auth 路径与自身 `importAssistants` SQL sink 无具体调用关系；无 foreign actionable lead | 无 verification | `trn_agent_002_00000172` 选择保留原 finding，但 `submit_findings` 参数 JSON 无效，后续请求被 reservation guard 拒绝；无 final submit、无 adoption。机械 R2。 |
| `agent_003` | 选 `task_e91ff908d3`；未读其 foreign 文件正文 | 仅主题相邻：OAuth callback 与自身 `sanitizeMiddleware` 路径不同；无 actionable lead | 无 verification | `trn_agent_003_00000128` 保留自身 finding 并成功提交；最终 refs 只有自身 `evt_00001178`、`evt_00001197`，无 foreign adoption。机械 R2。 |
| `agent_004` | 选 `task_79118a4016`；未读 foreign 文件正文 | 自述为主题关联，未指出与自身 components scope 的具体调用或共享控制；无 actionable lead | 无 verification | `trn_agent_004_00000145` 保持空 findings 并成功提交；无 foreign adoption。机械 R2。 |

条件计数：foreign artifact selected 4/4；foreign evidence body read 1/4；direct relation 1/4；`direct relation → actionable lead` 1/1；`actionable lead + opportunity → target-aligned verification` 1/1；`verification → evidence model-visible` 1/1；已收束的 post-verification judgment 与 final adoption 均为 0/1。这里的 1/1 仅是一名 agent 的诊断轨迹，不能估计稳定转移率。

## 解释限制与下一版本动机

v1 的 `repository_v1_t4_post_sync_window_v1` 实际拼接了旧版 `T4_RESULT_INSPECTION_PROMPT_INSTRUCTIONS` 和 relevance 指令，其中写有“Inspection is required”、要求可见 inspection record，并声称 `list_tasks` 可用。四名 agent 都产出 inspection record，因此不能把 4/4 selection 解释为模型完全自主选择。

v1 每名 agent 预留 4 permit，但成功的首次 request 后，只有发生 `read_file` 才能使用 evidence-consumption request；该 request 后也无受限的提交修复调用。`agent_002` 的无效 JSON 和 `agent_001` 的第二次 read 均在模型已获得机会后使提交失败。下一版本需纠正 prompt 继承，并允许在原有个人 reservation 内进行 `submit_findings` 修复；这与首次机会保证、一次 verification 上限及 192 总预算相容。
