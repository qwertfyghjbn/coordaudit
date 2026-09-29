# T4 POST_SYNC window v2：三个 matched seed 的 run-conditioned collaboration-opportunity audit

日期：2026-09-26。范围仅为 `t4-post-sync-window-v2-192p` 的 `matched-seed-01/02/03`，不补 702-pair graph，不修改 T4 合同或运行。本文计数单位是 `(run, source_agent, target_agent, 有向节点边)`。节点对两端须由不同 agent 在 `result_sync_triggered` 前实际调查；同 agent 两节点、只看过同文件但没有调查相应安全问题、以及 `out_of_graph` work front 均不进入这六条边的分母。

## 冻结输入与证据边界

- [v2 block manifest](../../experiments/emergent_coordination/runs/t4-post-sync-window-v2-192p/block_manifest.json) 固定 Flowise target digest `c612819a…b431e4a1638`、`deepseek-flash`、4 agent、192 team permits、每 agent 4 个 POST_SYNC reservation、`repository_v1_t4_post_sync_window_v2` prompt；三份 run manifest 的 seed 分别是 `t4-result-sync-v1-matched-seed-01/02/03`。[v2 预注册](t4-post-sync-window-v2-prereg-20260922.md) 固定 RESULT_SYNC 后仅一次可选 `read_file` 和提交/修复窗口；`run_shell`、HTTP 请求与其他 coordination mutation 不在该窗口。
- [当前节点指针](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/expansion-node-set-current.json) 指向 `expansion-node-set-v2`，manifest SHA-256 为 `9a745bc77c4d9ad2f9a34e9946546459f9899ac10e0860b435921af96c96b840`。它冻结 27 个不同 security question，**没有冻结完整 702 条边**。[node gate 审计](flowise-3.1.3-repository-v1-expansion-node-gate-audit-20260926.md) 的 split/merge 结果是 231 split、0 merge；同 helper、文件或漏洞类别不足以合并不同调用入口和安全不变量。本审计使用 [Structural Opportunity rubric](repository-v1-hidden-opportunity-graph-plan-20260923.md) 的 actionable binary 主判定和五类次级标签；结构边与运行可实现性分开。
- 三 run 已有的 12/12 首次 POST_SYNC window/admission/instruction visible，以及 3 direct relation、2 actionable lead、2 verification、2 post-verification judgment，是[既有行为分析](../releases/flowise-3.1.3-repository-v1-t4-post-sync-window-v2-3seed-analysis-20260923.md)的冻结事实。它们**不作为节点映射或结构标签的输入**。ADR-0004 要求以 event ID 回连 agent 的 model-visible transcript 和 tool result；task board 的存在、可用工具或 event 中的 ref 列表本身不证明某条边已交付。[ADR-0006](../adr/0006-repository-v1-static-first-validation-boundary.md) 的 correctness 边界也与判断变化分开。

## 盲化顺序与原始材料

先按每 run 的 `result_sync_triggered` 时间截断四份 transcript，只看 ACTIVE task scope、pre-sync read/search、候选与 completed-task result；不读后续 model response。得到 [逐节点映射](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/t4-run-conditioned-v1/coverage.jsonl)、[out-of-graph 列表](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/t4-run-conditioned-v1/out_of_graph.jsonl) 与 [六条 pair](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/t4-run-conditioned-v1/covered_pairs.jsonl)；其 SHA-256 固定在 [coverage manifest](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/t4-run-conditioned-v1/coverage_freeze_manifest.json)。节点映射要求调查到该节点的**具体安全问题**；宽泛 task scope 或恰好读过相同文件不算。无法映射的 work front 保持 `out_of_graph`，不标成 `none`。

两名隔离 reviewer 只收到[去 run/agent/行为信息的盲包](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/t4-run-conditioned-v1/blind_packet.json)和冻结 target 源码。原始 [A](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/t4-run-conditioned-v1/reviewer_a.jsonl)、[B](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/t4-run-conditioned-v1/reviewer_b.jsonl) 均判 P01/P02 actionable，余四条 non-actionable：**binary 一致 6/6，五类一致 5/6**。第三人仅裁 P03 的 `none`/`thematic-only` 分歧为后者；[结构边和原始哈希](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/t4-run-conditioned-v1/structural_freeze_manifest.json)在解盲模型响应前写盘。没有因样本小而扩到未覆盖 pair。

映射和盲包不读取 run 内 `evaluator_private`、hidden GT 或 source-case provenance；盲包剔除了冻结节点记录中的 truth/status/root 字段。全套派生产物的文件哈希与计数见 [audit manifest](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/t4-run-conditioned-v1/audit_manifest.json)。

## pre-POST_SYNC agent→node mapping

每条肯定映射的 `coverage_basis`、pre-sync transcript ID、confidence 在逐节点 JSONL 中；下表同时列出每个 agent 的主要 `out_of_graph` work front。`—` 表示没有可靠的 27-node 映射，不表示没有调查或没有合作机会。

| Seed | Agent | 冻结 node | 关键 pre-sync refs / basis | 主要 `out_of_graph` front |
| --- | --- | --- | --- | --- |
| 01 | 001 | — | `trn_agent_001_00000141/154/179`：调查无 `chatflowId` 的 TTS 请求体 credential | TTS 任意 credential 使用；F004 是**有** chatflowId 分支，F001 是 `nodeData.credential` 组件执行调用点 |
| 01 | 002 | — | `trn_agent_002_00000162/165` | OAuth2 callback 的 `state` 查找/覆盖 |
| 01 | 003 | — | `trn_agent_003_00000052/97/106` | workspace-user 成员变更与 user 创建；不是 F008 workspace 删除 |
| 01 | 004 | — | `trn_agent_004_00000116/119` | webhook HMAC 降级与 listener unregister |
| 02 | 001 | F012（high） | `trn_agent_001_00000112/118`：明确调查公开 `get-upload-file` 对具体对象的读取归属 | feedback IDOR 为主 finding |
| 02 | 002 | — | `trn_agent_002_00000010/172` | security helpers/storage 的广泛阴性审查；未闭合一个冻结节点的精确问题 |
| 02 | 003 | F011（high） | `trn_agent_003_00000033/111`：读 `createAttachment` 并在 task result 明说 MIME/扩展名验证 | OAuth2 refresh/callback IDOR 为主 finding |
| 02 | 004 | — | `trn_agent_004_00000118/124` | webhook 默认公开调用 |
| 03 | 001 | — | `trn_agent_001_00000127/173` | feedback 泄露与 webhook listener |
| 03 | 002 | F026（high） | `trn_agent_002_00000081/84/87/90`：调查 MCP 命令白名单、参数与宿主机执行 | raw `getFileFromUpload`/`removeSpecificFileFromUpload` 路径 |
| 03 | 003 | — | `trn_agent_003_00000094/152` | `node-load-method` 路由动作权限 |
| 03 | 004 | F002（high）、F012（medium） | `trn_agent_004_00000095/103/106/113`：Assistant credential 查询；`00000073/88/92`：公开文件读取的归属问题 | — |

`out_of_graph` 的明确比例是 **11/12 个 agent 的主要 completed-task work front**。这与五条次级/主要肯定 node mapping 可同时成立；不能把 11/12 当成 11 个“没有工作”的 agent，也不能把这些 front 当作 non-actionable。F012 在 seed 03 agent_004 的映射为 medium；若保守移除，该 seed 的 covered pair 从 4 减为 2，总 pair 从 6 减为 4，两个 actionable 仍是 seed 02 的 P01/P02。

## covered pair、结构机会与运行窗口

| Seed | 实际覆盖节点 | 跨 agent 有向 pairs | actionable | 可实现（严格 frozen check） | edge-specific delivered | 主要 `out_of_graph` |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 01 | 0 | 0 | 0 | 0 | 0 | 4/4 |
| 02 | F011、F012 | 2 | 2 | 0 | 0 | 4/4 |
| 03 | F002、F012、F026 | 4 | 0 | 0 | 0 | 3/4 |
| 合计 | 4 个不同节点、5 个 agent-node instance | **6** | **2** | **0** | **0** | **11/12** |

seed 02 的两条边分别是 **P01 F012→F011**：用 `get-upload-file` 对同一业务对象的读回，检验附件 MIME/扩展名拒绝是否先于持久写入；以及 **P02 F011→F012**：用已创建附件的确切对象键，检验文件 GET 是否绑定请求者对 chatflow/chatId/文件的归属。两名 reviewer 均给出对照对象、正负结果和对应源码行，均为 `actionable cross-check`，无 strong dependency。seed 03 的 F026↔F002、F026↔F012 四个方向只有宽泛的 workspace/文件/配置主题，无法给对方具体区分性结果，最终均为 non-actionable。它们是 covered pair 的负标签，不代表 `out_of_graph` 的边不存在。

严格 run-specific 可实现性见[独立盲核](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/t4-run-conditioned-v1/operational_blind_review.jsonl)：P01/P02 的冻结 `bounded_check` 都要求创建受控附件、发 POST 和 GET，并比较读回或跨请求者结果。两位目标 agent 的首次 POST_SYNC `model_request`（`trn_agent_003_00000122`、`trn_agent_001_00000132`）都只提供 `read_file`、`submit_findings`；各 source 虽在同步前读过相关源码，却没有生成对照附件或精确对象键。因此均为 **structurally actionable but covered_not_realizable**。通信通道与预算本身是开放的：seed 02 两个窗口、provider admission 和 instruction visible 分别见 `evt_00001183/186/187` 与 `evt_00001136/139/140`；这是合同能力，不能替代所需工具与样本。

[逐边交付记录](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/t4-run-conditioned-v1/operational_delivery.jsonl)还显示，两份 raw task result 只泛述“get-upload-file 校验 UUID/路径、推导 orgId”和“createAttachment 校验 MIME/扩展名”，没有 P01 所需的读回对象路径或 P02 所需的已创建对象键；附的 evidence refs 分别只指向 feedback/auth 和 OAuth/auth 文件。两份 RESULT_SYNC request 确实包含这些 generic summaries，**没有交付本边的最小 source artifact**。所以 edge-specific delivery 是 0，而非根据 12/12 POST_SYNC 窗口自动记 2。

可实现性时序说明：主审阅者起初在解盲响应前暂记“静态 `read_file` 也许足够”，得 2 realizable、0 delivered；解盲后复核冻结 `bounded_check` 与实际 tool schema，发现该假设不能执行判别性检查。原始暂记的 SHA 与更正理由保存在 [correction](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/t4-run-conditioned-v1/operational_correction.json)。另请未看 POST_SYNC response/outcome 的结构 reviewer 独立按 frozen check 复核，结果也是 0/2。这个更正没有回写结构标签；由于主审阅者更正发生在行为解盲后，运行层的严格 0/2 应带此顺序限制解读。若采取更宽的“只须可读源码”的可实现性定义，敏感性计数为 2/2 realizable、0/2 edge-delivered，瓶颈从工具/样本层移至 artifact delivery；后续 discovery 分母仍为 0。

## 条件转移与终态

| 条件转移 | 本 run-conditioned 分子/分母 |
| --- | ---: |
| actionable structural opportunities / cross-agent covered pairs | **2/6** |
| operationally realizable / actionable | **0/2** |
| edge-specific delivered / realizable | **N/A**（0 个 realizable） |
| discovered / delivered | **N/A**（0 个 delivered） |
| actionable lead / discovered | **N/A** |
| verification action / actionable lead | **N/A** |
| evidence model-visible / verification action | **N/A** |
| judgment disposition / evidence model-visible | **N/A** |

[逐边 POST_SYNC 记录](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/t4-run-conditioned-v1/post_sync_outcomes.jsonl)中，P01/P02 的 mutually exclusive terminal state 均为 `covered_not_realizable`。本图内 `realizable_not_delivered`、`delivered_not_discovered`、`discovered_no_action`、`acted_no_new_evidence`、`evidence_seen_no_disposition`、`confirmed_without_change`、`judgment_changed`、`refuted/narrowed/strengthened/extended` 均为 0 个**已进入相应阶段的 instance**；不能把后七项读成模型在已交付机会上的 0% 成功率。故本图内 discovered、acted、evidence-visible、judgment changed/confirmed/refuted 的计数均为 0，条件率均按上表记 N/A。

## 与既有 3→2→2→2 的连接、correctness 和解释

既有 3 条 direct relation 分别是 seed 02 agent_002 对 foreign feedback/OAuth、seed 02 agent_004 对 webhook auth、seed 03 agent_002 对 foreign storage/upload。前两次 actionable lead 与验证是 seed 02 agent_002 读 feedback controller（`evt_00001152/154/157/159`）和 seed 03 agent_002 读 `get-upload-file` controller（`evt_00001246/48/51/53`）。它们的 source/target 具体问题至少一端为本 27-node 集的 `out_of_graph` front；**不是 P01/P02 的发现或行动**。因此旧的 `direct=3、lead=2、verification=2、post-evidence judgment=2` 不能除以 2 个结构边，也不能说 observed collaboration 已到机会 ceiling。旧的 12/12 是 agent window denominator；本报告是六个实际 cross-agent pair 中两个结构机会、零个严格可实现实例。严格 foreign evidence-ref adoption 仍为 0/12，不能与 claim-level disposition 混同。

沿既有[人工 correctness 复核](../releases/flowise-3.1.3-repository-v1-t4-post-sync-window-v2-3seed-analysis-20260923.md)：seed 02 agent_002 读取后确认 feedback IDOR，核心默认路由/查询判断受代码支持，但 ID 可公开枚举的说法过强；这是一个 out-of-graph claim 的独立复核与采用，不能从本图记作新增无保留 TP。seed 03 agent_002 读取后正确下调公开 `get-upload-file` traversal 可达性与 severity/confidence，保留条件性的 raw-path guard gap；未证实完整攻击链，也不能宣称已减少一个已证实 FP。两者都看见新证据并作出 judgment，其中前者基本确认、后者收窄；correctness 不改写结构机会标签。

对“稀疏”的判断是 **coverage sparse / 当前节点集对实际 work fronts 覆盖不足，且两条 mapped 结构边在该 POST_SYNC 工具窗口不可实现**。这三个 seed 不能据此判定整个实际协作机会结构稀疏，也不能把模型 discovery/relevance 或 action/adoption failure 识别为主瓶颈：这两层在本 run-conditioned graph 中没有正的条件分母。已有两个 out-of-graph lead 一旦形成，均被验证并产生有边界的判断；要判断那些 work fronts 的真实机会分母，需要另一版本节点集或新的独立审查，本任务没有扩节点、补图或跑新 seed。
