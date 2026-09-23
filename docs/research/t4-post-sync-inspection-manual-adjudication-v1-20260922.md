# T4 post-sync inspection manual adjudication v1

适用 block：`t4-post-sync-inspection-v2-192p`。本规则在 matched seed 02 与 03 启动前固定，用于人工复核每位 agent 的 RESULT_SYNC 后 inspection record；不改变 R0–R4 的机械定义。

## Unit

每位发生 result sync observation 的 agent 有一条审阅记录。审阅者只读取 model-visible RESULT_SYNC message、后续 model response、工具结果、最终 finding 和事件序列。

## Fields

| Field | 判定 |
| --- | --- |
| foreign artifact selected | 模型明确标出一个 foreign completed task ID。 |
| foreign evidence body read | 仅当同步后该 agent 用 `read_file` 实际读取与该 foreign evidence_ref 对应的文件正文时为是。result 中列出 ref、复述 result 或显示 ref ID 均为否。 |
| thematic relation | 只说明相同包、漏洞类别、信任边界或总体模式，但未说明一个具体 foreign 观察如何影响自身候选 finding。 |
| direct relation | 指出共享的具体代码路径、控制、不变量或调用关系，并说明该 foreign 观察会加强、削弱、反驳或改变自身候选 finding。 |
| actionable lead | 提出一个后续可执行的 read/search/test，指定目标和预期用来区分结论的结果。仅说“相关”“加强”“可交叉验证”不算。 |
| follow-through | 在 inspection 后实际执行该 lead 对应的 read/search/test。 |
| foreign evidence incorporated | 最终 finding 显式引用该 foreign task 的 evidence_ref。 |

`direct relation` 与 `actionable lead` 可以同时为是；`thematic relation` 只在没有 direct relation 时计数。每个肯定结论都要附 transcript ID 与 event/tool ID；证据不足时标为 `uncertain`，不做推断。

## Reporting

每个有效 seed 报告各字段逐 agent 状态，以及 aggregate count。R3/R4 仍分别按既有 trace 规则和最终 foreign evidence provenance 计算；本人工表用于解释 R2 内部的 relevance 与 adoption 瓶颈。
