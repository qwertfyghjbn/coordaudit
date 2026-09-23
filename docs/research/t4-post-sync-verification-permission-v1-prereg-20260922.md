# T4 post-sync verification permission v1 预注册

日期：2026-09-22。冻结身份：`t4-post-sync-verification-permission-v1-192p`；manifest SHA-256：`426ffd32e0533bd8705856bb904bddefafba15bfeee5b07616ce904b89ca79a0`。对照为 [relevance v1 三 seed](../releases/flowise-3.1.3-repository-v1-t4-post-sync-relevance-v1-3seed-20260922.md)。本次只准备并冻结实验，不运行 live。

## 问题与单变量 treatment

relevance v1 的有效运行中，12/12 agent 有 foreign artifact inspection record，3/12 提出具体关联及 actionable verification lead，0/3 执行相应验证。`read_file` 在 team finalization 的工具门禁中仍可用，但原 finalization instruction 将其用途限定为既有 finding 的证据绑定，并要求尽快提交；`run_shell` 与 `list_files` 在该阶段不可用。这使“已提出验证目标但未行动”的原因尚不能归于模型的采用决策。

新 profile `repository_v1_t4_post_sync_verification_permission_v1` 保留 relevance v1 的初始 system/user prompt、raw RESULT_SYNC snapshot、inspection 与 relevance instruction，**仅在 RESULT_SYNC 消息末尾追加**：若已提出具体 foreign verification target，可在提交前自愿执行一次与目标匹配的有界验证动作。finalization 阶段可用已有 `read_file` 做定向读取；仅当既有工具界面在 finalization 前仍提供 `run_shell` 时，才可选择有界只读搜索。当前三条 actionable leads 均指向已知源码文件，定向读取足以验证其判别条件，因此没有增加搜索工具授权。一次动作是模型 instruction，不是新 gate；按 trace 核验有无超出。

不强迫执行动作、引用 foreign evidence、修改 finding 或复用结果。现有工具 schema、dispatch gate、result_sync、scheduler、team finalization runtime、192 permits、reserve=32、模型和 evaluator 均不变。若 sync 恰与 finalization 切换同一步，新 profile 只调整两条 user instruction 的呈现顺序，使 finalization 提示先于 RESULT_SYNC 权限说明；不改两者内容、事件触发或工具门禁。仍需核对每个 live model request 中的实际顺序；权限文字若未送达，则该 run 不用于判断模型采用意愿。

## Matched contract 与执行门槛

T4/4 agents；Flowise repository-v1 target；`deepseek-flash`、thinking disabled、temperature 0、max output 4096；`convergent_v2`、`all_agents_terminal_v1`、`team_remaining_permits_v1`；192 hard team permits、reserve=32、max steps=96、1200s、retry=1；`initialization_lease_v1`、`task_closure_gate_v1`、`result_sync_v1`。依次复用种子 `t4-result-sync-v1-matched-seed-01`、`-02`、`-03`，每个 seed 与 relevance v1 的有效运行对照。

live 前需完成契约/提示词 hash、零网络 mock、harness tests 与 S/P/B/T smoke。首个 live seed 必须 valid、4/4 closure、sync exactly once、provenance 完整且无 deadlock，再考虑其余 matched seeds。首次 run 若无终态，保留 partial trace 并单列；replacement 使用同 seed 和新 run-id，不把 partial trace 纳入机制比例。不得为了观察到行动而调整 prompt。

## 条件转移与人工判定

沿用 [manual adjudication v1](t4-post-sync-inspection-manual-adjudication-v1-20260922.md) 的 selected artifact、direct relation、actionable lead、follow-through、foreign evidence body read 和 final incorporation 规则。新增每位 agent 的 post-sync permission delivered、工具可用性、同步时剩余 permits、验证动作的 tool/event ID、读取文件或搜索目标、与 lead 的匹配判断、验证结果、判断变化与最终 finding 引用。所有判断只用 model-visible transcript、工具结果及最终 finding，不读取 hidden evaluator/GT。

按以下条件链同时报告分子与分母，不以 12 个 agent 作为每一步的固定分母：

1. `inspection → direct relevance`：直接关联人数 / 完成 inspection 人数；
2. `direct relevance → actionable lead`：具备目标与判别条件的人数 / 直接关联人数；
3. `actionable lead → verification action`：同步后执行与目标匹配的 read/search 人数 / 提出 actionable lead 人数。现有对照为 **0/3**；
4. `verification action → judgment update`：明确根据工具观察修正或巩固判断的人数 / 完成目标匹配动作人数；
5. `judgment update → final adoption`：foreign result/evidence 可追溯地进入最终 finding 的人数 / 已有可追溯判断变化人数。

另报告“所选 artifact 的直接关联”与“额外讨论的其他 foreign artifact 关联”，避免将非所选 artifact 的直接关系误算为所选结果。`read_file` 或 search 只有在 RESULT_SYNC 与 inspection record 之后、最终 submit 之前发生且与已提出的 target/判别条件相符才计入第三步；只列 evidence_ref、`list_tasks` 或重复提交不算。纯文字声称严重性改变、没有可对照的 pre/post finding lineage 时，判断变化标为 `unverified`，R3/R4 依现有机械定义独立报告。

只读辅助脚本 [post_sync_permission_review.py](../../scripts/post_sync_permission_review.py) 从单次 run 的 `metrics.json` 生成逐 agent 未判定模板，再根据人工填写的布尔字段与 tool/transcript/finding ID 汇总上述条件分母。未判定字段或伪造的动作 event ID 会被拒绝；脚本不把 task snapshot 的 evidence_ref 当成文件正文读取，不调用模型或 evaluator。人工需依据原始 trace 核实目标对齐、顺序和判断变化。

## 解释分支

若 permission 未送达、目标工具未提供或调用被门禁拒绝，是实施/机会失败。若 permission 送达且有剩余 permits，但仍无目标匹配动作，只说明澄清权限不足；随后应独立冻结带显式 post-sync 验证窗口或预留调用的 timing treatment。若出现定向 read/search 且据观察修正判断，可确认 cross-agent information flow。foreign evidence 进入最终 finding 是更强采用，不凭单次 run 推断 security effectiveness 提升。finding/TP 仅作次要结果。
