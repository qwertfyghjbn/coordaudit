# T4 POST_SYNC window v2：Run-conditioned Work-Front Audit v2

日期：2026-09-27。只审 `t4-post-sync-window-v2-192p` 的 `matched-seed-01/02/03`。计数单位是同一 run 内、不同 agent 的两个实际调查 front 所组成的**有向 pair**。这份 run-local 资产不更新 HOG，不新增 benchmark node，也不改变任何已运行的 prompt、runtime 或 seed。

## 输入、顺序与可复核材料

[block manifest](../../experiments/emergent_coordination/runs/t4-post-sync-window-v2-192p/block_manifest.json) 固定 Flowise target digest `c612819a833fc8ab3c58fe5085fb80fc0a6c4cb1d86cbb8ed41b0b431e4a1638`、`deepseek-flash`、4 agent、192 team permits、每 agent 4 个 POST_SYNC permits，三个 matched run 均只有一次 `result_sync_triggered`。[三 seed 行为分析](../releases/flowise-3.1.3-repository-v1-t4-post-sync-window-v2-3seed-analysis-20260923.md)、[sampled opportunity density](flowise-3.1.3-repository-v1-sampled-opportunity-density-result-20260926.md)、[HOG 映射 audit v1](t4-post-sync-window-v2-run-conditioned-opportunity-audit-20260926.md)、[manual adjudication](t4-post-sync-inspection-manual-adjudication-v1-20260922.md)、[POST_SYNC v2 合同](t4-post-sync-window-v2-prereg-20260922.md)、[ADR-0004 model-visible lineage](../adr/0004-model-visible-transcript.md) 和 [ADR-0006 correctness 边界](../adr/0006-repository-v1-static-first-validation-boundary.md) 已核对；这些旧结果没有作为 work-front 或结构边标签的判据。

[审计 manifest](../../artifacts/run_work_front_audit/t4-post-sync-window-v2-192p-v2/audit_manifest.json)记录全部派生文件 SHA-256、三个 run manifest SHA-256，以及 `repository_v1_t4_post_sync_window_v2` prompt profile、prompt/tool schema hash、模型与预算配置。该 manifest 不含 evaluator-private 材料。

实际顺序为：按各 run 的同步事件时间截断 transcript → 只据 pre-sync task、调查与完成结果定义 front → 生成同 seed 跨 agent 有向 pair → SHA 冻结 → 两名独立 reviewer agent 不看 POST_SYNC 的结构盲标 → 只裁决 binary 分歧并冻结结构边 → 逐边核对可实现性 → 逐边核对 target model-visible snapshot 并冻结交付 → 最后读取 POST_SYNC 响应与既有人工判读。详细规则在 [protocol](../../artifacts/run_work_front_audit/t4-post-sync-window-v2-192p-v2/protocol.md)。两名 reviewer 是独立 agent，访问隔离依赖任务约束和自报，不是 OS 文件访问审计；公开旧研究结论造成的认知先验无法排除。

## 冻结的实际调查范围

[18 条 work-front 定义](../../artifacts/run_work_front_audit/t4-post-sync-window-v2-192p-v2/work_fronts.jsonl)逐条给出 `run_id`、`agent_id`、run-local ID、安全问题、代码范围、同步前 transcript refs、候选判断、同步时状态和边界不确定性。[同步前 task results](../../artifacts/run_work_front_audit/t4-post-sync-window-v2-192p-v2/pre_sync_task_results.jsonl)保留源端实际交接文字。54 个 front evidence refs 全部存在且早于各自同步事件；[QC](../../artifacts/run_work_front_audit/t4-post-sync-window-v2-192p-v2/pre_sync_evidence_qc.json)给出截点和 run manifest hash，[冻结文件](../../artifacts/run_work_front_audit/t4-post-sync-window-v2-192p-v2/pre_sync_freeze.json)给出清单 SHA-256。

| Seed | Agent | 主要 bounded security questions |
| --- | --- | --- |
| 01 | 001 | WF01：无 chatflowId 的公开 TTS 能否使用别的 workspace 的 credentialId |
| 01 | 002 | WF01：公开 OAuth2 callback 能否仅凭 state 覆盖其他 workspace 的 Credential |
| 01 | 003 | WF01：workspace-user 写操作能否跨组织修改成员；WF02：普通认证主体能否绕过 invite 创建用户 |
| 01 | 004 | WF01：webhook HMAC 能否由 header 前缀降级；WF02：listener 注销是否缺 chatflow 归属校验 |
| 02 | 001 | WF01：公开 feedback 按 chatflowId 泄露反馈；WF02：公开 get-upload-file 是否缺 requester ownership |
| 02 | 002 | WF01：正常 storage 路径的 filename/chatflowId/traversal guard 是否可绕过 |
| 02 | 003 | WF01：OAuth2 refresh/callback 的 workspace 约束；WF02：附件创建是否在写入前拒绝恶意 MIME、扩展名、路径 |
| 02 | 004 | WF01：默认配置的公开 webhook 能否匿名触发 flow |
| 03 | 001 | WF01：公开 feedback 泄露；WF02：listenerId 是否须同 chatflow 注册才可接收 SSE |
| 03 | 002 | WF01：raw getFileFromUpload/removeSpecificFileFromUpload 是否可收到不可信路径 |
| 03 | 003 | WF01：低权限主体能否调用 node-load-method 的任意 loadMethods |
| 03 | 004 | WF01：assistant upload 能否用其他 workspace 的 OpenAI 凭据；WF02：公开下载路径能否绕过 provider guard |

每 agent 保留 1–2 个真正推进的问题。大量只读一次的文件、宽泛 helper 扫描及没有闭合问题的短暂分支没有另计。seed 02 `agent_001/WF02` 和 seed 03 `agent_001/WF02` 标为 `candidate_unresolved`，保留为已实际推进但未完成的 front；其影响在下文做边界敏感性说明。work-front ID 仅在本审计有效。

[跨 agent pair manifest](../../artifacts/run_work_front_audit/t4-post-sync-window-v2-192p-v2/cross_agent_pairs.jsonl)包含全部 78 个方向，排除了 same-agent、跨 seed 和本 run 未调查的问题。

| Seed | Agent | Work fronts | Cross-agent directed pairs | Adjudicated actionable | Realizable | Strict delivered | Discovered after delivery |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 | 4 | 6 | 26 | 2 | 1 | 1 | 0 |
| 02 | 4 | 6 | 26 | 6 | 3 | 1 | 0 |
| 03 | 4 | 6 | 26 | 3 | 3 | 1 | 0 |
| **合计** | **12** | **18** | **78** | **11** | **7** | **3** | **0** |

## 双人结构标签与 QC

两份原始盲标 [A](../../artifacts/run_work_front_audit/t4-post-sync-window-v2-192p-v2/reviewer_a.jsonl)、[B](../../artifacts/run_work_front_audit/t4-post-sync-window-v2-192p-v2/reviewer_b.jsonl) 各覆盖 78/78 对。B 的两条 `primary=actionable` / `secondary=direct relation` 内部矛盾由 B 在未看 A 的条件下自发给出 [erratum](../../artifacts/run_work_front_audit/t4-post-sync-window-v2-192p-v2/reviewer_b_erratum.json)；原始文件未改。更正后 A 为 7 actionable，B 为 14，双方同判 6 条 positive、63 条 negative，binary 一致 **69/78 = 88.5%**；positive-specific agreement **57.1%**，Cohen κ **0.513**，五类 exact 一致 **50/78**。[QC 原始矩阵](../../artifacts/run_work_front_audit/t4-post-sync-window-v2-192p-v2/structural_qc.json)可复核。

按既有结构 rubric 的 90% binary QC 门槛，这批标注**未通过**。只对 9 条 binary 分歧做了[逐边源码裁决](../../artifacts/run_work_front_audit/t4-post-sync-window-v2-192p-v2/disagreement_adjudication.jsonl)：5 条判 actionable，4 条判 non-actionable；未修改 rubric、原始标签或 front 边界。[最终描述性标签](../../artifacts/run_work_front_audit/t4-post-sync-window-v2-192p-v2/structural_labels_final.jsonl)为 11/78，结构阶段 SHA 见 [freeze](../../artifacts/run_work_front_audit/t4-post-sync-window-v2-192p-v2/structural_freeze.json)。因此 **11/78 是 QC 未过时的裁决数，不是稳定的机会密度估计**。两位 reviewer 的 7–14 positive 差距也是分类敏感性，不是置信区间。

重点方向不对称：seed 03 `03-P025`（agent_004 下载 guard → agent_002 raw helper）是 actionable，因为公开 controller 调 `streamStorageFile` 而非 raw helper，能直接反驳后者将该公开路由当 caller 的可达性推断。反向 `03-P013` 被裁为 non-actionable：raw helper 本身缺 guard 不会改变已经走另一方法的下载入口的路径 guard 判断。seed 02 附件创建与公开读回形成数条结构检查，但其需要的受控对象与运行工具另行判定。

## 当前合同下的可实现性与交付

结构边冻结后逐条核对的 [realizability table](../../artifacts/run_work_front_audit/t4-post-sync-window-v2-192p-v2/realizability.jsonl) 有 11 行，含 source pre-sync 产物、target 首次窗口、冻结 bounded check 与缺失能力；[freeze](../../artifacts/run_work_front_audit/t4-post-sync-window-v2-192p-v2/realizability_freeze.json)记录 7/11。POST_SYNC 只有一次可选 `read_file` 和提交/修复，不能用 shell、HTTP、POST、GET、network 或 coordination mutation。不能因为模型后来没做检查而判它不可实现。

| Pair | 最小检查 | Realizable | Strict delivered | 关键原因 |
| --- | --- | --- | --- | --- |
| 01-P001 TTS→OAuth | 静态核对 state/credential 绑定 | 是 | 是 | source result 有 ID-only 凭据查询，可给 target 一次定向源码对照 |
| 01-P006 OAuth→TTS | 构造无 chatflowId 的 provider 请求 | 否 | — | 冻结检查需运行请求 |
| 02-P005 GET→storage | 输入异常路径并比较拒绝 | 否 | — | 无 GET/HTTP/shell |
| 02-P007 GET→attachment | 恶意附件提交后读回 | 否 | — | 无受控附件，也无 POST/GET |
| 02-P010 storage→GET | 静态区分路径 guard 与 requester ownership | 是 | 是 | source result 给出具体 provider guard |
| 02-P012 storage→attachment | 对照 raw staging 与规范化持久写入 | 是 | 否 | source 读过代码，但 task result 没有这段差异 |
| 02-P019 attachment→GET | 新建准确对象键并用第二身份读取 | 否 | — | 对照对象未产生；无 POST/GET |
| 02-P020 attachment→storage | 静态回溯 file.path/key 与 raw helper | 是 | 否 | task result 只泛述 MIME/路径验证 |
| 03-P012 raw helper→assistant upload | 静态核对 upload 的 filePath 来源 | 是 | 是 | source result 点名 raw helper 及缺 guard |
| 03-P021 assistant upload→raw helper | 静态核对 caller 与 Multer 输入 | 是 | 否 | task result 未说明 caller 到 raw helper 的链 |
| 03-P025 public download→raw helper | 读 controller 排除错误 caller | 是 | 否 | task result 仅说 route/provider 有 guard，未说明 `streamStorageFile` 与 raw helper 的差别 |

逐边 [delivery table](../../artifacts/run_work_front_audit/t4-post-sync-window-v2-192p-v2/delivery.jsonl) 检查 source 的完整 task result 确实进入 target 首次 `model_request.messages`，并用 `post_sync_instruction_model_visible` event 回连请求；七个 target 当时都有 `read_file`、`submit_findings` 及行动窗口。但只有 **3/7** snapshot 含本边足够具体的 source 信息；完整 task result 可见、evidence ref 列表或 RESULT_SYNC 发生本身均不自动算 delivered。[交付冻结](../../artifacts/run_work_front_audit/t4-post-sync-window-v2-192p-v2/delivery_freeze.json)在行为解盲前写盘。

## 解盲后的行为、条件分母与终态

严格 delivered 的三边分别为 `01-P001`、`02-P010`、`03-P012`。[逐 pair 行为映射](../../artifacts/run_work_front_audit/t4-post-sync-window-v2-192p-v2/post_sync_behavior_mapping.jsonl)记录：seed 01 目标仅把 TTS 与自己的 OAuth 缺归属校验称作相似 pattern，没有提出会改变 OAuth claim 的具体 cross-check；seed 02 目标称其他结果属不同领域；seed 03 目标称 raw-path finding 与自己的 assistant credential finding 不同。按冻结 manual rubric，这三条均无 direct relation/discovery、lead 或 verification。seed 01 的 thematic mention 不升级为发现。

| 条件转移 | 结果 |
| --- | ---: |
| actionable / cross-agent covered pairs | **11/78**（QC 未过的描述数） |
| realizable / actionable | **7/11** |
| strict delivered / realizable | **3/7** |
| discovered / delivered | **0/3** |
| actionable lead / discovered | **N/A**（0 个 discovered） |
| verification / actionable lead | **N/A** |
| evidence-visible / verification | **N/A** |
| disposition / evidence-visible | **N/A** |

[机器可读 summary](../../artifacts/run_work_front_audit/t4-post-sync-window-v2-192p-v2/conditional_summary.json)逐 seed 列出同一分母；78 个互斥终态为 `covered_non_actionable=67`、`actionable_not_realizable=4`、`realizable_not_delivered=4`、`delivered_not_discovered=3`。其余题定终态（`discovered_no_action`、`acted_no_evidence`、`evidence_seen_no_disposition`、`confirmed_without_change`、`narrowed`、`weakened`、`strengthened`、`refuted`、`extended`）在**严格交付漏斗内**均为 0 次进入，不能读成这些后续阶段的 0% 能力。

对题设十个问题的直接回答：三 seed 形成 **18** 个主要 fronts、**78** 个 cross-agent directed pairs；裁决 **11** 条 structurally actionable（QC 未过）、**7** 条 operationally realizable、**3** 条 strict delivered、**0** 条在 strict delivered 条件下 discovered、**0** 条由这些边形成 actionable lead、**0** 条在该漏斗中 verification、**0** 条在该漏斗中影响 judgment。已有 **2** 条真实 verification 与本图的对应是 **1/2** 条有结构边、**1/2** 条无结构边；与 11 条结构边相比，目标对齐的实际检查为 **1/11**，但它未通过 strict edge delivery 门槛。历史全 run 的 **2** 次 post-evidence judgment 继续存在，不计作本漏斗的 2 次。

## 两条既有 verification 的重新定位

[逐轨迹记录](../../artifacts/run_work_front_audit/t4-post-sync-window-v2-192p-v2/historical_verification_relocation.jsonl)把结构判断与原始行为、正确性分开：

| 轨迹 | 冻结 front 图中的位置 | 协作终态 | 安全正确性边界 |
| --- | --- | --- | --- |
| seed 02 `agent_002` feedback IDOR | `agent_001/WF01 → agent_002/WF01` 即 `02-P001`，双人均为 `none`。agent_002 的 pre-sync 工作是 storage/path guard，并未调查 feedback；这是同步后的 opportunistic foreign-claim re-investigation，不是本图的 cross-front actionable edge。 | target `trn_agent_002_00000175` 提出反馈 controller read，`evt_00001154/159` 使证据可见，随后确认并形成自己的 finding；无 strict foreign evidence-ref adoption。 | 默认白名单、按已知 chatflowId 查询且不检查归属有静态支持；“ID 可公开枚举”和完整动态可达性未获证实。 |
| seed 03 `agent_002` storage/upload guard | `agent_004/WF02 → agent_002/WF01` 即 `03-P025`，独立 pre-sync 结构审查后裁为 actionable，且静态检查可实现。source snapshot 只给 route/provider guard 的部分 cue，缺少该边冻结的精确 caller 差异，故 strict delivery 为否。 | target `trn_agent_002_00000150` 提出并实际读取 get-upload-file controller（`evt_00001248/53`），看到证据后收窄 raw-path finding 的公开路由可达性与 severity/confidence。此行为与结构边对齐，但位于严格交付漏斗之外。 | 该公开 route 实际走 guarded `streamStorageFile`，局部纠偏正确；其他 raw helper caller 的攻击者可控性和完整 traversal 链仍未证实。 |

所以既有 **2 条 verification 中，1/2 有 pre-sync 结构 actionable 对应，1/2 属新的 opportunistic foreign-claim 转向**。若以本图 11 条 actionable edge 作描述分母，有 **1/11** 出现目标对齐的实际 verification；以 7 条 realizable 为分母是 **1/7**；严格 delivered 的 3 条中是 **0/3**。这些数不得与原报告的 `2/2 lead→verification` 相加或互换：单位和条件阶段不同。既有 2/2 verification evidence-visible、2/2 post-evidence judgment、0/2 strict foreign-ref adoption 继续成立。judgment change、opportunity utilization 和 TP 正确性是三个不同事实。

交付边界的**事后敏感性**：若把 seed 03 `03-P025` 的“get-upload-file/provider 有 guard”部分提示也视为足以交付这条边，则 delivered 会成为 4/7，其中 1/4 被发现并形成 lead，随后 1/1 verification、证据可见、判断收窄。这不是主结果；主结果在行为解盲前已要求交付 `streamStorageFile` 与 raw helper 的确切 caller 差异。这个敏感性说明 seed 03 的协作既不能被忽略，也不能倒灌进冻结的 strict delivery 数。

## 边界敏感性、稀疏解释与停止结论

本图含两条 `candidate_unresolved` front。若只去掉 seed 03 `agent_001/WF02` 次要 SSE 候选，分母为 70 pairs、actionable 仍 11、realizable 7、delivered 3；若两条 unresolved front 都剔除，则为 62 pairs、7 actionable、6 realizable、2 delivered。说明具体 front 边界会改变比例，不能把 11/78 外推到 repository-v1 的完整机会图。另有 9 条 binary 分歧和未过的 90% QC gate；上述计数必须作为受限解释，而非稳定机会率。

对稀疏协作的回答是 **B、C、D 都有局部证据，同时 F 必须保留**：11 条裁决结构机会中 4 条在当前单次 read 窗口不能做冻结的动态区分检查；7 条可静态检查的边中 4 条没有精确交付；3 条严格交付的边均未被发现为可行动关系。A 的“几乎没有结构关系”不被这 11 条支持，尽管方向对的比例并不高；E 的 discovered 后 action/adoption 失败没有正分母，不能归因。三 seed 和结构 QC 失败都限制了因素排序。sampled 27-node HOG 的约 6% 密度与本 run-local 11/78 属不同节点/分母，不能相互替换。既有 11/12 主要 work front out-of-graph、v1 两条 mapped structural edge 均不可实现、12/12 POST_SYNC opportunity、3 direct relation 和 2→2→2→2 行为链，均保持原值。

**当前 repository-v1/T4 机制诊断可以到此结束。** 它已能定位这个固定合同下的静态能力、精确交付和发现边界，同时保留结构标签 QC 未达标的明确限制；再扩 HOG、补 462-pair exhaustive annotation 或跑新 live seed 都不是本任务的后续动作。若下一阶段要检验协调机制本身，应转向事先共享安全目标、能提供明确跨 agent 依赖与可操作交接对象的 shared-objective benchmark，独立冻结其工作分配、工具合同和评价规则。
