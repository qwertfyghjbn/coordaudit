# T-Pilot 1：共享仓库审计目标下的自然分工

状态：**v1 live seed 已改判 treatment-integrity failure / lease-starvation diagnostic（§9）；v2（initialization_lease_v3）已于 2026-09-28 完成冻结并获授权执行单 live seed（§10）**。本 pilot 只观察 T4 在一个共享目标下的工作分配机制；单个 seed 是机制 smoke test，不用于估计稳定效果或比较其他 coordination condition。既有 frozen historical manifests/runs 保持不变。[v1 最终 prereg](t_pilot_1_freeze/final_prereg_v1.json)与全部 frozen artifacts 不改写；v1 run 不做 A/B/C 分类。v2 唯一 runtime 差异是 `initialization_lease_v3`（设计：[INITIALIZATION_LEASE_V3_DESIGN.md](INITIALIZATION_LEASE_V3_DESIGN.md)）；[v2 final prereg](t_pilot_1_freeze/final_prereg_v2.json)（block canonical hash `10b78742…`）记录完整冻结证据。

## 1. 问题与实验单位

问题：四名 T4 agent 只接收同一个仓库级安全审计目标和现有协调能力时，是否自行形成不同的主要 **work front**，并通过看见 task board 调整后续选择，从而限制重复调查？这里的 work front 是可独立推进的有界安全问题及其源码链，不等于文件、目录、task 标题或漏洞类别。**parallel independent exploration** 可以产生不同覆盖；只有可追溯的 board 信息影响了选择，才记为 **coordination-induced division of labor**。

目标 target 沿用 `flowise_3_1_3_repository_v1` 的冻结 Agent-visible 快照。评价只用公开 run 证据与该快照；hidden evaluator、GT、source-case 标签、provenance 不进入 prompt、board、mount 或 tool result。TP/FP 仅作可选背景记录，不参与本 pilot 的判定。

## 2. Exact shared-objective prompt 与污染检查

四人收到**字节相同**的以下任务文字；agent ID 仅由现有 identity 字段提供：

> Audit the entire repository under `target/` within the fixed shared team budget. Find as many distinct, real security issues as possible while keeping unsupported findings to a minimum. Your work contributes to a shared team audit; individual finding count is not itself the objective. Use source-level evidence and bounded local validation when useful. Submit only findings you believe the evidence supports.

上段 UTF-8 原文（不含 Markdown `> ` 前缀或换行）的 SHA-256：`59f4519fc53cb1dca940ac636747fd0443221410163ce6930f75e267c405d28b`。运行时四人 user/shared-objective text 必须逐字相同；identity 仍在 system prompt 中。

系统侧只保留现有安全边界、**原样** `repository-v1` finding schema 和有界完成/提交说明，再用以下纯能力描述替代旧 T4 board 指导：

> Four agents share one team call budget. A shared task board is available. `list_tasks` shows its current tasks; `create_task` adds an open task; `claim_task` atomically claims an open task; `release_task` returns an owned task to open; `complete_task` closes an owned task with a result and evidence references. There is no assigned leader. A claimed task must be closed before that agent can submit findings.

上段 UTF-8 原文的 SHA-256：`c396950d227f08b8c1af168ba3d391a9a490bd1f95a9b49d94064c9b66a374c1`。**Not using the board is a valid model behavior**，不是 admission failure；不要求创建、认领、选择 scope、交叉验证或达成一致。最后一句只是现有 `task_closure_gate_v1` 的真实约束；不扩展到未认领的 open task。现有 finding schema 中的 `category` 枚举仍须保留以维持提交合同，但不得把枚举改写成工作分配建议。

**Prompt diff 必审**：旧 `REPOSITORY_V1_COMMON_INSTRUCTIONS` 枚举 HTTP、WebSocket、credential、file 等审计路径，可能充当分工菜单；新 profile 删除这句枚举。旧 `T4_BOARD_BOOTSTRAP_INSTRUCTIONS` 要求先 `list_tasks`、选未覆盖区域、避免重复并主要留在已认领 scope；`T4_NONOVERLAP_INSTRUCTIONS` 更直接强制错开；两者均不得继承。旧 `T4_RESULT_SYNC_INSTRUCTIONS` 与 POST_SYNC 文案提出避免重复、检查他人结果，也不得进入本 pilot。审查实际拼接后的 system/user/finalization prompt 以及每次 model request 的工具描述，确认没有模块/角色/安全类别分工示例，没有“avoid duplicate work”“inspect others before choosing”一类行为命令。通用的预算收尾指令可以保留，但不得增加分工指令。

[最终 rendered prompt packet](t_pilot_1_freeze/final_prompt_packet_v1.json)从已注册的 `repository_v1_t_pilot_1_shared_objective` profile 生成，逐 agent 保存完整 system prompt、相同 user prompt、原样 finding schema、`convergent_v2` completion instructions、全部 tool schema/description、初始 model request 和 finalization message；packet 文件 SHA-256 为 `c313d25b104b6eace8feb51d12ca1f7602e20e3b70477fe61b0ba159c157609a`。零网络 T4 集成 run 的 **4/4 首次实际 `model_request.messages` 与 advertised tools** 逐字匹配 packet；claimed-task finalization mock 的实际 model request 含冻结的 exact 收尾消息及 `read_file`、`submit_findings`、`complete_task`。对渲染后 system/user、finding/completion 指令、tool descriptions 和 finalization text 的污染扫描为 `0` 命中：旧 repository path menu、board bootstrap、non-overlap、RESULT_SYNC/POST_SYNC、avoid-duplicate、inspect-others、choose-uncovered 文案均未出现。finding `category` 的 schema enum 是提交格式，不是任务菜单。动态 task/tool 内容仍以未来 run 的 model-visible transcript 为准；若实际 request 与冻结 packet 的静态部分不符，该 run 不通过 admission。

## 3. 与现有 T4 runtime 的最小差异和冻结变量

基线选已运行验证的 [`t4_flowise_sequenced_bootstrap_task_closure_v1`](../../experiments/emergent_coordination/manifests/t4_flowise_sequenced_bootstrap_task_closure_v1.json)，而非带 `result_sync_v1` / POST_SYNC window 的后续 profile。后者把四个 initial claim 的完成作为同步触发，并可能阻止已完成首个 task 的 agent 提交；在允许 agent 自主决定不用 board 的 prompt 下，这会把 task 使用变成事实上的完成前提。T-Pilot 1 不启用 RESULT_SYNC、POST_SYNC、最终综合或去重；这是选择现有稳定 T4 合同的边界，**不是修改 runtime 行为**。

本 pilot 对已验证 T4 task-closure baseline 做**两项版本化差异**：新 shared-objective prompt profile 去掉旧分工诱导；`initialization_lease_v2_optional` 在某 agent 未用 board 就终止时跳过其初始化顺位。旧 `initialization_lease_v1` 的行为和 historical runs 不改。这不是与旧 T4 run 的单句 prompt 对照，不能从旧运行差值推断 shared objective 的独立因果效应。冻结 target 与 evaluator digest、T4/`structured_team`、4 agents、`openai_compatible`/`deepseek-flash`、thinking disabled、temperature 0、4096 output ceiling、192 hard team call permits、96 max steps、1200 秒 wall clock、一次 provider retry、`completion_v2_team`、`convergent_v2`、`all_agents_terminal_v1`、`team_remaining_permits_v1` 及 reserve=32、`task_closure_gate_v1`、scheduler、task ownership、原工具 schema/dispatch、sandbox、permit 消耗和 finding schema。无 per-agent token cap、无 reserved final-synthesis permit。不得添加 role assignment、task 初始化模板、behavioral state 或对特定 agent 的额外 prompt。

Initialization lease 按 canonical ID 串行化首次 board operation，**不会替 agent 选 scope**；后手可能看见前手留下的 board 状态，这是 T4 treatment 的信息阶梯，不能描述成四个完全同时且独立的 spontaneous choices。正式报告必须给出每个 agent 第一次 scope decision 前**实际进入模型上下文**的 board snapshot（没有则记 `none`）。未使用 board 的 agent 可以直接调查/提交；若其选择不领取 task，这不是 admission failure。v2 在前手完全未用 board 就终止时发出 `task_initialization_turn_skipped` 并推进顺位，也能跳过提前终止的后手；不以强制 bootstrap prompt 绕过缺陷。

### Budget-triggered finalization 的冻结语义

开放式共享目标没有天然的“全仓已审完”时刻：**budget-triggered finalization != repository audit coverage complete**。本 pilot 测量固定预算内自然产生的任务分配和调查行为。`team_remaining_permits_v1` 在共享余额达到 32 时触发收尾；不生成未覆盖区域清单，不检查其他 agent，不要求去重、综合或重新分配。沿用现有 `convergent_v2`、`task_closure_gate_v1` 与现有 `team_finalization_message(..., task_lifecycle_reminder=True)`，其冻结 exact model-visible 文字如下（UTF-8 原文 SHA-256：`a67d60e1486854c3bc46c6241e9fd7e7390672511f0298dfcd6a22ddc99935a7`）：

> Team finalization phase is active because the shared permit ledger reached its preregistered reserve. Stop open-ended exploration and submit the complete repository-v1 payload now. You may use read_file only to bind strictly necessary evidence for a finding already identified; do not use shell or coordination tools. If no supported finding remains, submit an empty findings payload. If you still own a claimed task, close it with complete_task before finishing the run.

这里 `complete_task` 是末句所指的唯一 closure 例外；冻结的 finalization advertised/dispatch surface 为 `read_file`、`submit_findings`、`complete_task`。新 profile 的零网络 request 已验证该例外；未来若实际 run 丢失它，则属于 admission failure，不能靠让 agent 提前造假 task 或提前提交解决。

## 4. Admission：先判断轨迹是否可解释

在读取分工结果前，检查：`run_validity=valid` 且 reconciliation valid；4/4 agent 有真实首次 model request；target/prompt/tool schema/budget digest 与冻结合同一致；没有 provider failure/retry 风暴造成结构性失真；permit、step 与 wall-clock 上界未越界；每个 claimed task 的 claim→release/complete 转换可解释，提交者没有未关闭的 claimed task；team 进入有限终态，且不存在 open task 引起的 deadlock、无限创建或因预算耗尽而不明原因地被动退出。记录 `clean_complete`、`forced_complete`、各 agent submit/empty submit 与 stop reason；正常预算触发 finalization 不自动使 run 无效，但因生命周期缺陷导致的 forced completion 不通过 admission。

**不把 4/4 创建或认领 task、发现漏洞、4/4 非空 finding 当作 admission 条件**，否则预先筛掉“agent 自主不用 board”的结果。若 admission 不过，停止 A/B/C 分工分类，先定位 lease、closure、scheduler、provider 或 prompt/tool 不一致；保留原始产物，另行版本化修复方案。不得在同一 seed 内改 prompt 后继续分析。

## 5. 冻结提取口径

先按事件 ID、parent refs 和 model-visible transcript 重建各 agent 时间线。工具结果只有进入后续 `model_request.messages` 才算**看见**；不能以 task 创建时间早于下一次调用推定已看见。分析表每行至少保存 agent、时点、task ID/owner/status、可见 board snapshot、decision transcript ref、源码动作与 evidence ref、front ID、判定及不确定性。自动抽取后，对语义边界和 board 影响作人工 adjudication；标注先只看任务与源码动作确定 work front，再看 board 可见性和决策，避免用 task 标题倒推实际范围。所有人工判断保留引用、理由和不确定标签。

冻结轻量 adjudication protocol：**Stage 1** 自动提取 timeline、task events、model-visible board snapshots、文件/symbol 动作与 candidate front evidence；**Stage 2** 一名 primary reviewer 定义主要 fronts，标 scope/overlap 与 board-linked decisions，给 A/B/C 初判；**Stage 3** 第二 reviewer 只复核 front split/merge 歧义、全部 `explicit board-linked` positive、会改变 A/B/C 的关键 overlap 判断及最终分类。仅这些关键分歧再做 adjudication；不要求所有文件、symbol、front 全量双人独立标注。每条人工结论保留 transcript/event/evidence refs、rationale、`certain/uncertain` 标签与 reviewer 决定；分类前冻结复核表。

| 维度 | 冻结指标与单位 |
| --- | --- |
| Task allocation | 按顺序列出初建 task 的 creator/描述/范围；首次和后续 claim、冲突、release、complete；每个 agent 首次自选的 scope 与实际首个深入 front；初建 task 两两的语义不同数；scope 扩大、缩小、改题、换 owner 的时间点；末端 open、unclaimed、claimed、重复 task 的 ID 与数目。`release→other claim` 算 work stealing/reassignment；只有自己换题算 scope adjustment。 |
| File / module overlap | 对实际 `read_file` 与 `run_shell` 的源码访问提取 target-relative 路径，区分枚举/粗扫与定向阅读；报告每 agent 集合、team union、两两 Jaccard、跨 agent 重复定向阅读动作占比。目录/模块用冻结 target 的路径层级归一化，同样报告交集；公共入口/helper 单独标注。 |
| Symbol overlap | 从定位命令、读取范围、引用 anchor 和 task result 提取函数/类/路由；无法可靠解析的 symbol 标 `unknown`，不得据此认定“不重叠”。记录跨 agent 同一 symbol 的重复定向检查及其目的。 |
| Security-question overlap | 每个实质性 front 记 `攻击者/输入 → 受保护对象或 sink → 应有安全不变式/guard`、源码范围、首末证据、判断状态。同一不变式和攻击路径的重复分析算语义重叠，即使文件不同；读同一共享 helper 但在检验不同问题时只算代码重叠。短暂打开文件、仅复述 task 标题和未推进的候选不算 front。 |
| Coverage diversity | 每 agent 的主要 front（其最多 focused investigation actions 的 front）、次要 front、team 已实际推进 front 的 union、仅该 agent 推进的 front 和动作数；报告 unique contribution 与跨 agent duplicated investigation。分母仅为**本 run 实际观察的 fronts**，不声称全仓覆盖率。 |
| Coordination behavior | 每次 board snapshot 后的 scope 决策，记录当时已可见的其他 task/owner、之前意图、之后选择和明确引用；分别标 `explicit board-linked`、`compatible but unproven`、`no evidence`。主动补充未覆盖区域、因他人 owner 改题、接手 open/released task、发生 claim conflict 后换 scope 各单列。 |

`focused investigation action` 指带具体安全问题的一次源码定向读取、定位搜索或局部验证工具调用；同一调用触及多个文件仍只算一次。task result 和模型文字用来判定动作目的与 front，不另加一次动作。全仓目录列举和一次性宽泛搜索另计，以免大量 cheap reads 稀释重叠。对每个由至少两名 agent 推进的 front，按事件顺序将首名 agent 开始后其他 agent 在该 front 的 focused actions 计为跨 agent 重复动作；分母为全队全部 focused actions，同一动作只计一次。另列出有明确目的的交叉核对，不能将其自动视作浪费。文件/目录/符号统计是可复核的代理量，**不代替 security-question overlap**。本 pilot 不要求交叉核对发生。

Board 影响的严格证据为：先有实际 model-visible board 内容（含他人 scope/owner），随后 agent 以该内容为根据明确改变、排除或补充某个可指认 front，接着有相符的 task 或源码动作。仅 `list_tasks`、时间相邻、碰巧不同文件、或事后声称“我们分工了”均不足。没有早于 board 的明确意图时，可凭模型在决策当回合对具体他人 task 的引用和随后的行动判 `explicit board-linked`；若只有行为顺序而无具体引用，归 `compatible but unproven`。这支持可观察机制归因，不等于无对照组的严格因果效应。

## 6. 单 seed 的 A/B/C 判定

只在 admission 通过后按以下**正式预注册**规则判定；阈值已冻结，不得在 live 后按结果调整。它们只是 single-seed mechanism smoke-test rubric，不是总体统计 cutoff：

| 结果 | 操作规则 |
| --- | --- |
| **A. Natural decomposition observed** | 至少 3/4 agent 的主要 security-question front 两两不同；跨 agent 对同一 front 的重复 focused actions 不超过全部 focused actions 的 1/4，且没有两个 agent 的多数动作落在同一 front；至少两个不同 agent 各有一次 `explicit board-linked` scope 决策并实际执行，至少一次是避开已覆盖 front 或补充未覆盖 front。 |
| **B. Diversity without coordination** | 满足 A 的 front 多样性和低重复条件，但没有达到 A 的 board-linked 证据；不同区域主要由各自首次独立选择或无从归因的选择形成。 |
| **C. Collapse to redundant exploration** | 至少两名 agent 的主要 front 相同，**且**同一 front 的跨 agent 重复 focused actions 超过 1/3；或四人虽建了不同标题的 task，但实际多数深入调查集中在同一个 security question 且 board 没有促成改题。 |

其余有效轨迹记为 **mixed / indeterminate**，逐项说明是多样性、重复还是 board 证据不满足；不得硬塞入 A/B/C。报告必须同时列出 `distinct primary fronts / 4`、`duplicate focused actions / all focused actions`、`explicit board-linked agents / 4` 的原始分子/分母，以及 1/4、1/3 阈值和人工不确定 front 合并/拆分的敏感性。一个 seed 达 A 也只说明该次观察到机制，不证明稳定、普遍或优于其他条件。可旁记 submitted findings、明显重复 finding 与 evaluator outcome；Unique TP、FP、precision、最终 team synthesis 和 finding deduplication 不进入 A/B/C，后两项留给 T-Pilot 2。

## 7. 单 seed 执行方案（本设计不执行）

冻结 seed identity 为 `t-pilot-1-flowise-shared-objective-seed-01`；它是 provenance 标识，不声称 provider 支持可控随机种子。新 [T-Pilot 1 contract config](../../experiments/emergent_coordination/manifests/t_pilot_1_shared_objective_v1.json) 和 [block manifest](t_pilot_1_freeze/t_pilot_1_shared_objective_v1/block_manifest.json) 已冻结；后者的 canonical `manifest_hash` 为 `be7c12f41cea6ba6df4bf1c4dfe8516a0d72b386f3d82442009200fd13ad437b`，绑定 target digest `c612819a833fc8ab3c58fe5085fb80fc0a6c4cb1d86cbb8ed41b0b431e4a1638`、runtime source digest `9475bdb3370a60eabca06714ebb0a4739c9a0afafe49781bfbfa57a1724b91ff` 与 tool schema digest `81707c840e64c97540da11f856ff1b7ca56b2c0b0d5ab073a44f0c4c52ac29d9`。[最终 prereg](t_pilot_1_freeze/final_prereg_v1.json)绑定 exact prompt、A/B/C、adjudication 和 preflight；其文件 SHA-256 为 `470aa6126355db8f9a422e08b0e609903cfa71fbe2073699c6c20431b67553c2`，明确 `live_execution_authorized=false`。旧 candidate packet/prereg 仅保留为修复前诊断记录，不是本次执行合同。

### Optional board × initialization lease：零网络 deterministic 检查

2026-09-27 先复现 v1 缺陷，再以新 `initialization_lease_v2_optional`、新 prompt profile、临时 workspace、真实 `TaskBoard`/`AgentRunner`/`RunContext`、mock provider 重测。所有模型调用均为本地 `MockLLMClient`，不启动 live API。旧 v1 的未使用 board 终止行为另有回归断言，避免暗改 historical contract。

| Case | 检查与结果 |
| --- | --- |
| A：完全不用 board，调查后 submit | **PASS**。四 agent 的真实 mock run 中前手读源码并提交，后手可 `list_tasks` 并继续；run valid、reconciliation valid。未使用 board 的终止顺位发出 `task_initialization_turn_skipped`，无永久等待。 |
| B：只 `list_tasks`，不 create/claim，然后调查/submit | **PASS**。集成 run 中后手 list、读源码、提交；单元检查中 list-only owner 终止后释放 lease。持有 lease 期间后手仍按原有序列等待，正式 trace 须记录。 |
| C：create→claim→investigate→complete→submit | **PASS**。新 profile 下工具 dispatch 全链路读取 `target/app/main.py` 生成 evidence ref，task 到 completed，随后空 finding submit 合法。 |
| D：create/claim→release→另一 agent claim | **PASS**。release 后 task 回 open，另一 agent 原子 claim 后成为 owner；T4 无独立 reassign API。额外检查提前终止的第三名 agent 在轮到它时被跳过。 |
| E：reserve 触发时 no/open/claimed task | **PASS**。新 profile 下无 task 和 open/unclaimed task 可提交；claimed task 在关闭前返回 `task_closure_required`，`complete_task` 在 finalization 的实际 model request 工具面中，关闭后可提交。 |

因此冻结的语义为：**open/unclaimed task 不阻塞 team completion；claimed unfinished task 继续受 closure gate 约束；未用 board 的 agent 无须制造虚假 task 才能结束**。v2 仅记录并跳过已终止但未取得 board lease 的顺位；旧 v1 不变。A–E 及四 agent 有限终止已通过。

零网络回归：完整 `experiments/emergent_coordination/tests` **343 passed，9 subtests passed**；独立 S/P/B/T mock harness preflight（含 M4/hard-gate）**6 passed**；repository-v1 contract/case selection **17 passed**；`repository_pilot_v0` repository smoke **6 passed**；T-Pilot 1 A–E 定向回归在最终 packet 更新后 **12 passed**。首次全套运行的 9 个 graph input-lock 失败由本次短暂修改 case manifest 引起；已撤回该修改，图测试与完整套件均重跑通过。没有修订 hidden graph 私有资产或 frozen target。

### Live 前闸门

`exact prompt frozen`、`rendered prompt contamination audit pass`（零网络真实 model-visible request）、`optional-board/lease mock pass`、`closure/completion mock pass`、`zero-network preflight pass`、`manifest/digest frozen`、`A/B/C rubric frozen`、`adjudication protocol frozen` **已全部通过**。这仅使方案具备**单独请求一个 live seed 授权**的条件；它本身不授权也不启动 live。另行获授权后，run 产物写入 `experiments/emergent_coordination/runs/`，默认不提交；先做 admission，后作 A/B/C 判定，不按结果追加 seed 或改阈值。

## 8. 主要 validity threats 与后续闸门

- **Prompt 残留**：base prompt 的路径枚举、旧 board bootstrap、nonoverlap、RESULT_SYNC/POST_SYNC 指令会直接教会目标行为。以实际 model-visible request 审查为准；若残留，run 不用于自然分工结论。
- **Lease 顺序与 board 可见性**：固定先后手可使后手更容易选空白范围；报告各 agent 首次决策前可见的 task，不把顺序优势误说成纯模型自发性。
- **指标误判**：同文件可服务不同问题、不同文件可追同一问题；shell 搜索未必代表深入阅读。保留 front 级证据、`unknown` 与边界敏感性。
- **预算与收尾**：共享 permit 竞争、32-permit finalization 和 claim-closure gate 会截断尚未完成的调查。报告每 agent permits、active steps、未完成 front、task 终态；不能把预算截断直接解释为拒绝协作。
- **单 seed 与 target 特性**：不同 front 的机会密度、模型随机性和 Flowise 结构都会影响结果；本设计不支持频率、显著性或跨仓外推。
- **隐藏信息泄漏**：审计者可在可信控制侧核对 case digest；Agent 可见侧不得包含 GT、历史 work-front 标签或人工 adjudication。

**进入 T-Pilot 2 的条件**：admission 通过，四人能正常终止且 task lifecycle 不需补丁；A 表明值得研究后续综合/去重。B 也可进入 T-Pilot 2，但须把“没有观察到 board 驱动分工”作为前提，并将综合/去重问题与分工问题分开。若 mixed 但证据完整，先判断是单 seed 不确定性还是明确的任务语义问题，再决定是否做新版本 pilot。

**先调整任务语义或 bootstrap 的条件**：admission 因 lease、open/claimed task 或完成 gate 失败；prompt 为了有效终止不得不强制初始任务；board snapshot 未真实进入模型上下文；或 C 且 trace 显示 task 标题空泛、认领不反映实际 scope、board 信息无法支持调整。任何调整都须单独版本化、重新冻结并重新 smoke；不得回写本 seed 或把修复后的结果与本 pilot 混算。

## 9. v1 live run 处置：treatment-integrity failure（2026-09-27）

冻结合同本身执行正确：192/192 permits、run_validity=valid、reconciliation=valid、0 provider failure、finalization 在 remaining=32 处精确触发、冻结 finalization 消息与三工具面逐字进入请求。但 initialization lease 暴露出**结构性 treatment-integrity 缺陷**，事件证据（`runs/t-pilot-1-shared-objective-v1-192p/formal_t-pilot-1-shared-objective-v1/logs/events.jsonl`，不改写）：

- agent_002/003/004 的首次 `list_tasks` 都在 turn 0 发出 `task_initialization_lease_waited`；agent_001 经 `list_tasks` 取得 lease 后**全程未再使用 board、直到 termination 才释放**；
- 四次 release 的 reason 全部为 `agent_terminal`，四次 acquire 逐一发生在前一位终止之后——bootstrap 串行化了 4 个完整 agent 生命周期；
- permit 分布 96/65/30/1（恰为 192）：agent_004 一生只有 1 次 model call，被结构性剥夺参与机会；board 全程零写（4 次 list 全空）；
- 等待发生在 tool dispatch 内部、permit 已结算之后，reconciliation 对线程停摆不可见，因此 run 仍判 valid——这是 validity 指标的盲区，不是模型自然分工。

处置：**v1 run 记为 treatment-integrity failure / lease-starvation diagnostic；不做 A/B/C 分类**（分工数据被 lease 结构性污染，A/B/C 的前提不成立）；frozen artifacts、v1 manifest、prompt packet、prereg 全部原样保留；根因与 dispatch 语义调查见 [INITIALIZATION_LEASE_V3_DESIGN.md](INITIALIZATION_LEASE_V3_DESIGN.md) §1。

## 10. v2 修复草案（initialization_lease_v3，等待授权）

- **唯一 runtime 差异**：`task_board_sequencing_policy: initialization_lease_v2_optional → initialization_lease_v3`。shared-objective prompt、A/B/C rubric、预算（192/96/1200/1 retry）、模型、target、finding schema、closure/finalization/completion 语义全部冻结不变。合同：[t_pilot_1_shared_objective_v2](../../experiments/emergent_coordination/manifests/t_pilot_1_shared_objective_v2.json)（`preregistration.status=draft_pending_zero_network_preflight`，seed identity 预定为 `t-pilot-1-flowise-shared-objective-seed-02`）；[v2 prereg 草案](t_pilot_1_freeze/prereg_draft_v2.json)。
- v3 语义（冻结）：lease 只串行化首次 board bootstrap（`list → create → claim`）；非 board 动作或无 tool call 的 round 立即 opt-out/释放且不暂停该动作；bootstrap episode 硬上界 = 3 次 gated dispatch（FORCE_RELEASED）；claim 成功立即释放；release exactly once；不引入额外 provider call 或 permit。v1/v2 历史语义逐字节保留。
- 零网络验证（2026-09-27 实测）：新增 `tests/test_initialization_lease_v3.py` **26 passed**（A–J 边界、exactly-once、v1/v2 回归、sequencing 保留——agent_001 create/claim 后 agent_002 的 allocation round 的 model request 中可见 claimed snapshot、starvation stress——agent_001 不用 board 跑 24 步时 agent_002/003/004 的 board 观察全部先于其 termination、all-opt-out、mixed、closure/finalization、contract 注册）；全量 `experiments/emergent_coordination/tests` **369 passed + 9 subtests**（基线 343 + 新增 26，零回归）；S/P/B/T CLI mock smoke 全部 valid/valid（T 走 v3 policy）。
- 重新授权 live 前仍需（v2 正式冻结流程）：以 v2 合同冻结 block manifest（runtime_source digest 将因本修复改变，需重新计算）、复用并核验 v1 prompt packet 逐字不变、渲染 contamination 审计重跑、prereg 由 draft 转 final。本任务未执行上述冻结，也未调用 live API。

## 11. v2 冻结与正式执行记录（2026-09-28）

**冻结完成**：block manifest 已冻结（`t_pilot_1_freeze/t_pilot_1_shared_objective_v2/block_manifest.json`，canonical hash `10b78742681fb3053bdd7f3e18fad790ff7649e69c82a5e380633def84c50e42`）。与 v1 逐字段对比：contract 差异仅 `contract_id` 与 `task_board_sequencing_policy`；`target_tree`/`evaluator_private_tree`/`git_commit` 与 prompt hash 组（common_prompt、T4 system/user/tool_schema/identity）全部相同；`runtime_tree` 更新为 `5b4fe4b5…`（lease v3 代码，预期内）。零网络复验：v3 mock run 4/4 初始 model_request.messages 与 advertised tools 同 frozen packet 逐字一致；contamination 扫描 0 命中（path menu/board bootstrap/nonoverlap/RESULT_SYNC/POST_SYNC/avoid-duplicate/inspect-others/choose-uncovered）；finalization 文本与 {read_file, submit_findings, complete_task} 面不变。[final_prereg_v2.json](t_pilot_1_freeze/final_prereg_v2.json) 已固化全部 hash 并记录用户授权（单 live seed，不追加）。

**正式执行**（用户授权：完成冻结流程后开始正式运行；seed `t-pilot-1-flowise-shared-objective-seed-02`）：

- **Attempt 1（`formal_t-pilot-1-shared-objective-v2`）：infrastructure_invalid（ADR-0002）**。agent_002 前 2 次调用（含唯一一次 harness retry）连续 `APIConnectionError` 未恢复，另有 agent_004 一次已恢复的单次失败；`two_or_more_provider_failure_attempts`（共 3 次失败）→ 无效，不做 A/B/C。**lease v3 机制本身表现正确**：0 次 `lease_waited`、0 次 acquire（四人全部在首个非 board 动作/终止路径 opt-out 或 terminal-skip），6 次 `list_tasks` 均为 opt-out 后的合法 ungated 读取，无任何 agent 因 lease 被阻塞（permit 56/2/54/54，agent_002 的 2 次是 provider 故障而非 lease）。产物原样保留。
- Provider 健康探测（`compatibility_smoke.py`）通过后，按 corrected-run 惯例执行 **attempt 2（`formal_t-pilot-1-shared-objective-v2-attempt2`，同 seed、同冻结参数）**。

**Attempt 2 结果（formal seed，2026-09-28）：admission PASS。**

- `run_validity=valid`（0 provider failure）、`reconciliation=valid`、`team_completion=clean_complete`（4/4 submitted，finding 2/2/1/1，merged 6，0 invalid submission）；169/192 permits，finalization 在第 160 次调用精确触发（remaining=32=reserve）。
- **Lease integrity（v2 的核心目的）**：0 次 `lease_waited`、0 次 acquire/release——四人的第一个动作都是非 board 调查，各自在 dispatch 处 `bootstrap_opt_out` 确定性推进顺位；8 次 `list_tasks`（每人 2 次）全部为 opt-out 后的合法 ungated 读取；**无人被 lease 阻塞**，permit 分布 39/44/42/44（对照 v1 的 96/65/30/1）。board 仍零写（模型行为与 v1 一致：偏好直接调查），但 runtime 不再惩罚这一选择。
- Admission 逐项：validity/reconciliation ✓；4/4 首次 model request 与 frozen packet 逐字一致 ✓；permit/step/wall-clock 未越界 ✓；无 claimed task（board 零写），closure gate 平凡满足 ✓；有限终态 4/4 ✓；无未解决 lease wait、无 agent 被压缩到单次调用 ✓。
- 后续：A/B/C 判定按冻结 stage 1–3 adjudication 流程人工进行（本 run 的 board-linked 证据情况以人工提取为准）；TP/FP 仅背景记录。

## 12. v2 attempt2 裁决记录（stage 2/3，2026-09-28）

用户授权下由 agent 执行冻结 adjudication protocol 的四项遗留任务，完整记录见 [adjudication_v2_attempt2.md](t_pilot_1_freeze/adjudication_v2_attempt2.md)。要点：① 四条 unmatched finding 代码级核验全部为真，但对 operative repository_v1 GT（20 roots）无 root 匹配（锚点/不变式不同源），均非 FP，恰对应 v1.1 未激活的 agent-run-derived root R21/R22/R25（CR1 背景对照，不计分；evaluation.json 维持 TP=2/20）；② #0/#5 裁定同根合并（同一不变式与 sink 家族，#0 ⊇ #5），团队语义独立 finding 为 5；③ a4 primary front = FR-C1/FR-D 10:9 临界 tie（uncertain，任何读法下均非 OAuth2 front）；④ "横向扫描"按冻结定义不构成 front，分解后 distinct primary fronts = 3/4（tie 翻转则 4/4）。Rubric 原始量：duplicate focused actions 86/223=0.386（敏感性 0.35–0.52，>1/4），单 front 最大重复 0.099（<1/3），board-linked 0/4。**最终分类：mixed / indeterminate**（A 因 board 证据与重复率不可达；B 多样性满足但重复超标；C 两条件均不满足）。stage-1 报告的"初步倾向 B"因分母错误撤回。
