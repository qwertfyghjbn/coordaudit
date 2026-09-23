# repository-v1 Hidden Opportunity Graph 构建规划

日期：2026-09-23。状态：规划；尚未构建或标注 graph。适用 case：`flowise_3_1_3_repository_v1`，目标快照 SHA-256 为 `c612819a833fc8ab3c58fe5085fb80fc0a6c4cb1d86cbb8ed41b0b431e4a1638`。本文只定义 evaluator-side 离线资产与事后分析方法；不修改 frozen runtime、task assignment、prompt、tool surface、evaluator scoring 或历史 run。

## 1. 已核对的事实与研究边界

- [case manifest](../../experiments/emergent_coordination/manifests/flowise_3_1_3_repository_v1.json) 将 S1/P4/B4/T4 指向同一 Flowise 3.1.3 target、`repository-v1` prompt/finding schema 与 evaluator；T4 v2 是另行冻结的 4-agent、192 team permits 诊断合同，见 [v2 manifest](../../experiments/emergent_coordination/manifests/t4_flowise_post_sync_window_v2.json)。不得把它当作 S/P/B/T matched architecture block。
- evaluator-private [v1 ground truth](../../experiments/emergent_coordination/evaluator_private/flowise_3_1_3_repository_v1/ground_truth.json) 有 20 个 scored root、5 个 qualified near miss；[safe siblings](../../experiments/emergent_coordination/evaluator_private/flowise_3_1_3_repository_v1/safe_siblings.json) 另有仅供对照、不能证明整条路径安全的条目。root variant 不另计独立 finding。v1 GT 不是完整漏洞宇宙；[覆盖审计](flowise-3.1.3-repository-v1-gt-coverage-audit-20260921.md) 已记录未匹配真实候选和 v1 anchor 的局限。
- T4 的初始任务由 agent 在运行中 `create_task`、`claim_task`，ID 含随机 UUID，scope 也由 agent 选择；`initialization_lease_v1` 只排序首次 board 决策，不指定审计范围。[task board](../../experiments/emergent_coordination/harness/task_board.py) 与 [sequenced bootstrap 记录](../releases/flowise-3.1.3-repository-v1-t4-sequenced-bootstrap-v1-192p-20260921.md) 均支持这一点。S 没有跨 agent task；P/B 的分工也不能以 T4 task ID 表示。
- [T4 POST_SYNC v2 三 seed 分析](../releases/flowise-3.1.3-repository-v1-t4-post-sync-window-v2-3seed-analysis-20260923.md) 记录 12/12 agent 获得同步后首次请求，3/12 表达 direct relation，2/12 形成 actionable lead，2/2 lead 被验证，2/2 有证据后的判断，最终 foreign `evidence_ref` 纳入为 0/12。[人工定义](t4-post-sync-inspection-manual-adjudication-v1-20260922.md) 中的 strict selection 要求明确 foreign task ID；v2 为 0/12。这些是**已发生行为**，不是 benchmark 中潜在机会的分母。12/12 runtime window delivered 不等于 12/12 graph-relevant opportunity delivered。
- `repository-v1.1`/evaluator-v2 仍是[待激活的独立 generation](../releases/flowise-3.1.3-repository-v1.1-evaluator-v2-freeze-handoff-20260921.md)。本 graph v1 只绑定 v1 快照与 v1 GT；v1.1 候选不能悄悄改写其节点、边或历史分母。后续版本须有新 graph identity，并标记从历史 agent run 派生的证据循环性。

**定义**：一条 opportunity 是在固定 target、审计能力与合理的静态/有界本地验证预算下，调查单元 A 可以产出一份具体、可传递的代码证据或阴性结论，而这份信息有潜力改变调查单元 B 的判断、验证路径或必要搜索工作。它不要求某次 agent 真的产出、传递或利用该信息。`客观` 只表示依据冻结代码和明确威胁模型可复核；不是声称 GT 完备或所有 agent 都有足够时间接触该边。

## 2. 节点：冻结快照上的调查单元

主节点采用 **evaluator-side canonical investigation unit（调查单元）**：一个可独立推进、有明确 source/affected object/security invariant 与结论问题的 bounded work front。节点 ID 由 `case + snapshot + graph version + stable ordinal` 确定，例如 `F001`；ID 不含 seed、condition、agent ID、运行时 task ID 或 finding 文本。每个节点记代码范围、具体安全问题、可能产出的最小信息、证据锚、状态（scored positive / qualified near miss / admitted unscored / unresolved）和私有 GT root 映射。一个 root-cause cluster 的多个 manifestation/variant 合并；只有不同安全不变量且可独立裁决时才拆节点。安全 sibling 只有经过窄范围 source-chain 证明、且本身构成独立判断问题时才作节点；否则只作边证据。

选择理由：GT root 稳定但只有正例且 v1 不完备；finding candidate 取决于某次模型，不能作为客观分母；initial task 的 ID 与范围随 seed/architecture 变化。调查单元以源码与问题为身份，先固定 graph，再用独立的 `run task/finding → node` 映射表解释行为。未能可靠映射的实际任务记 `unmapped/out_of_graph`，不得当作 `none`。若两个 agent 重复调查**同一节点**，记录为 node-level duplicate work；主 graph 不造自环或把它膨胀成跨节点边。

## 3. 有向边与互斥 taxonomy

对每个不同节点的**有序对** `A → B` 独立裁决：A 是可提供最小信息的 source，B 是可能受益的 target；`B → A` 必须另审，允许不同类别。双向成立时保存两条 directed record，不用无向边或 `bidirectional` 缩写。`none` 也保留在完整 pair matrix 中，以固定分母和支持漏标审计。最终主分析只使用 `adjudicated` 且非 `uncertain` 的边。

| `opportunity_type` | 必须满足的判定标准 | 不计入可执行机会的界限 |
| --- | --- | --- |
| `none` | 无可证实的共享代码、控制或信息价值；或现有证据反驳所猜关系。 | 不能仅因未观察到 agent 互动就判 `none`。 |
| `thematic-only` | 只共享漏洞类别、包、文件、宽泛攻击面或抽象主题；未指出 A 的哪份结论会触及 B 的哪条具体路径/判断。 | 同为 authorization、SSRF、同文件，至多到此级。 |
| `direct relation` | 代码证明共享**具体** helper、source/sink、调用链、guard 或授权不变量，并能说清信息关联；但尚无有界、可区分结果的 B 决策/验证动作，或预期节省的搜索工作不具体。 | 不能因为“可能有用”而自动升为 actionable。 |
| `actionable cross-check` | 在 direct 之上，明确 A 可产出的证据、B 的目标 claim，以及一个允许工具内有界的 read/search/test 或可证明省去的重复子搜索；写明正/负结果将如何 validate、refute、narrow、extend B，或如何避免重复查同一子问题。B 可不依赖 A 独立完成。 | 无指定目标和区分性结果的“去看看”不算。 |
| `strong dependency` | 满足 actionable，且 B 的关键结论**逻辑上依赖** A 所调查的具体子命题（例如同一 sink 的实际 guard 或调用链可达性）；A 的结论是 B 证据链所需的前提/反证，不只是加速。须给出必要性论证与反事实：若该子命题为假，B 的结论如何改变。 | 不是运行时 `task.dependencies`，也不要求 B 只能由 A 来查；“同一类别/同一服务”不足以成立。 |

判定顺序从 `strong dependency` 向下寻找最高**已证明**等级，每个有序对恰好一个主类别。多个价值机制（shared sink/source/control、shared authorization invariant、common helper/call chain、positive/negative differential、validate/refute/narrow/extend、de-duplication）放入 `mechanisms[]`，不另叠加计数。若两个方向都似乎有用，分别写 A 可给 B 与 B 可给 A 的具体信息；信息价值不对称时只保留相应方向的高等级。证据不完整时保留当前可证的较低等级和 `uncertain` 裁决状态，不能把猜测升档。

## 4. 标注协议与隐藏性

1. **固定输入和盲化**：先记录 case ID、target/GT/safe-sibling 文件 SHA-256、graph schema 版本、节点纳入规则与 pilot 范围。标注者只看冻结 target、v1 evaluator-private GT、safe siblings、validation metadata 和已批准的威胁模型；候选生成与首轮判边期间不看 T4 transcript、finding、score、task 结果或各 condition 表现。公开 advisory/provenance 只能帮助定位代码，不能替代快照上的 source→sink/guard 证据。
2. **生成高召回候选**：从 root/sibling 锚和代码索引提取函数、调用者/被调用者、共享查询谓词、route guard、source/sink、对象归属与安全不变量；提出有序候选及反向边。对候选写最小 A artifact、B claim 和可能的差分检查。自动化只能提出候选，不能定级；类别相同、同目录或词向量相似只可用于待审队列。pilot 穷举全部有序对；全量扩展时抽样复核机器未提名对以估计漏边。
3. **独立双人标注**：两名标注者分别按 §3 判所有 pilot 有序对，先判是否有代码级 direct relation，再判是否有可执行差分与逻辑依赖。每条非 `none` 边至少给两处 target-relative `path:line`/symbol（A 证据与 B 消费点）、所依据的 excerpt hash、最小信息包、B 的预期决策/省工以及正负结果；`none`/`thematic-only` 也记排除理由。禁止用某次 run 的实际 action 证明机会存在。
4. **adjudication**：比较类别、方向、作用机制、证据和边界；第三人依据源码裁决。证据无法闭合的边留 `uncertain`，列出缺失事实与可能区间，不强迫二选一。冻结 adjudicated graph 与 digest 后，才开始 T4 事后映射。发现漏边/错边需要版本化修订和变更原因，不能无痕修改旧 graph 或回填历史行为定义。
5. **运行映射分离**：另一份表把每个 run 的 task/finding 映射到零个或多个调查单元，记录 `scope_declared`、实际触及的 code/evidence、映射信心和 run ID；只用 ACTIVE/RESULT_SYNC 前证据确定 coverage 与 A artifact 是否产生。然后才解盲 POST_SYNC 的可见消息、动作与最终 finding，按 [ADR-0004 lineage 边界](../adr/0004-model-visible-transcript.md) 连接 event、transcript、task、evidence、finding。泛称相似不能代替显式证据链。

Graph 文件及原始 adjudication 只放 trusted evaluator-side 私有区域或独立受限离线 artifact；运行目录中的 `runtime/target`、Agent workspace、tool output、task board、prompt、model-visible transcript、公开 case manifest 都不能引用或复制它。离线分析器必须在 run 完结后单向读取 graph 和脱敏 trace；不得从 graph 回写任务、消息、动态提示、工具结果或 live score。公开报告仅发布经审查的聚合指标和必要的脱敏例子；`evaluator_private` 内容、GT 标签、source-case provenance 不进入 Agent mount。规划文档本身也不得被用作审计 Agent 的输入。

## 5. 建议的 versioned schema

私有 `graph_manifest` 记录 `graph_schema_version`、`case_id`、`target_sha256`、`gt_generation`/GT SHA-256、safe-sibling SHA-256、`annotation_protocol_version`、节点/边文件哈希、adjudication 日期与状态。`nodes.jsonl` 一节点一行，至少含 `node_id`、`security_question`、`code_scope`、`invariant`、`evidence_refs`、`truth_status`、`gt_root_ids`、`adjudication_status`。GT 身份与详细 code evidence 不发布给 Agent。

`edges.jsonl` 对每个有序对一行，`edge_id` 由 graph version 与 `source_node/target_node` 确定；示意字段如下，占位符不是已判定的真实边：

```json
{
  "edge_id": "graph-v1:F001:F002",
  "source_node": "F001",
  "target_node": "F002",
  "direction": "source_to_target",
  "opportunity_type": "actionable cross-check",
  "mechanisms": ["shared_guard", "negative_differential"],
  "source_artifact": "A 能产生的最小代码结论及其适用范围",
  "target_claim": "B 中可能被改变的具体判断",
  "expected_effect": ["narrow", "refute"],
  "bounded_check": "允许工具内的具体 read/search/test 与正负结果",
  "evidence": [
    {"role": "source", "path": "target-relative/path", "line": 0, "symbol": "...", "excerpt_sha256": "..."},
    {"role": "target", "path": "target-relative/path", "line": 0, "symbol": "...", "excerpt_sha256": "..."}
  ],
  "rationale": "为什么 A 的结果能改变 B；为什么尚非强依赖",
  "confidence": "high",
  "adjudication_status": "adjudicated",
  "reviewer_ids": ["reviewer_a", "reviewer_b"],
  "uncertainty_note": null
}
```

`direction` 的唯一合法值为 `source_to_target`，方向由两个 node 字段决定；反向另写一行。`none` 边可用空 `mechanisms/evidence`，但必须有排除理由。`confidence` 为 `high/medium/low`，只表示代码证据强度；`adjudication_status` 为 `proposed/agreed/adjudicated/uncertain/rejected`，与 confidence 分开。生产统计只接收 `adjudicated`；`uncertain` 给上下界敏感性分析。`source_artifact`、`target_claim`、`expected_effect` 与 `bounded_check` 对 actionable/strong 必填，以便机器检查分类一致性。节点和边在同一 graph version 中不可更改 ID 语义。

## 6. 指标与分母

设 `V` 为已裁决调查单元，`D = |V|(|V|-1)` 为不同节点的 directed pair universe；`E_d`、`E_a`、`E_s` 分别是 `direct relation`、`actionable cross-check`、`strong dependency`。结构指标按 graph 的**唯一边**计；行为指标以 `(run_id, edge_id, source_agent, target_agent)` 为一次 opportunity instance，同一边可在一个 run 中有多个接收方，但一名接收方的同一边只计一次。所有指标按 graph version、case 与 GT generation 报告；不把 variant、同节点重复或 `uncertain` 混入点估计，并附 uncertain 全纳入/全排除界限。

| 指标 | 定义与解释 |
| --- | --- |
| benchmark opportunity density | 主值为 `(|E_a|+|E_s|)/D`（有可执行协作价值的 directed density）；另报宽口径 `(|E_d|+|E_a|+|E_s|)/D`、无向 dyad 数及各类数量，避免方向双计造成误读。 |
| actionable opportunity count | `|E_a|+|E_s|`，同时报 strong 单列、每类边数与有至少一条入/出 actionable 边的节点比例。 |
| opportunity coverage | 每 run 报 `有至少一个 cross-agent covered instance 的唯一 actionable 边数 / graph actionable 边数`。covered instance 要求 A、B 被**不同** agent 实际调查，A 的特定子问题有可分享结果；另报 node coverage 与 `delivered instances / covered instances`。delivered 要求 A 结果在 B 决策前实际进入 B 的 model-visible context，且 B 有相应 action window。不能只凭 task scope、board 可用或 12/12 window admission 认定 delivered。 |
| opportunity utilization rate | `used instances / delivered instances`；`used` 要求 B 在看见 A artifact 后完成与该边匹配的 read/search/test、明确的子搜索省工，或基于可追溯证据作出 disposition。仅提及 foreign 主题不算。若分母为零，记 N/A。 |
| discovered / missed opportunity | `discovered` 要求 B 明确识别 A 的具体 artifact 与 B 的关系；另记原 T4 strict task-ID selection，不能重写既有 0/12。`missed = delivered instance 且未 discovered`；未覆盖/未交付是 `not exposed`，不能记 missed。识别了但无 action 单列。 |
| architecture-specific reuse rate | 每 condition 以 instance 分别报 `delivered/covered`、`used/delivered` 与 `used/covered`，再分 **strict foreign-ref provenance** 和 **claim-level disposition**；后者不能冒充前者。S1 没有跨 agent 分母，改报 within-agent cross-front reuse；P4 若无信息通道则 delivered 为零、条件率 N/A。B4/T4 依各自真实可见 store/task 证据判 delivered，不从工具存在推定。 |
| 每类 opportunity 利用率 | 对 `direct relation`、`actionable cross-check`、`strong dependency` 分别报告 coverage、delivery、discovery、action、evidence-visible、post-evidence judgment、strict/claim reuse；`none/thematic-only` 只做误触/负对照，不当 actionable 分母。 |

对被调查的节点对先判 `no_structural_link`（graph 为 none/thematic）、`direct_nonactionable`、`out_of_graph` 或 actionable；前三种不能记成 agent 漏发现。对 actionable 边的每个 run/agent-pair 保留互斥终态：`no_cross_agent_coverage`、`covered_not_delivered`、`delivered_not_discovered`、`discovered_no_action`、`acted_no_new_evidence`、`evidence_seen_no_disposition`、`confirmed_without_change`、`judgment_changed`（strengthened/weakened/refuted/narrowed/extended）。`judgment_changed` 必须对照 B 行动前后的同一 claim；确认原判断属于 `confirmed_without_change`。另记正确性复核，不能把 judgment 变化直接算成正确 TP。若一个实际 action 匹配多条边，预先按最具体 evidence/claim 绑定主边并保留次级映射，主计数只算一次。

## 7. 小规模 pilot 与质量控制

**先做一个六节点 pilot**：在 v1 GT 中取共享 credential lookup/credential-use 语义的 R04、R05、R06、R20；加入已证明窄范围安全的 NM04 作为正负差分对照；加入同一 TTS 文件但不同不变量的 R19 作为“同文件未必 actionable”负对照。这些 ID 只是 evaluator-side pilot 选择规则，不是预先判定边。合计 6 节点、30 个有序对；不从任何 T4 lead/finding 反推增删节点。R04/R05/R06 的独立 root 身份按 v1 保留，R20 的具体 caller/helper 关系与 NM04 的适用范围必须重新沿源码核验；不能凭 GT 标签自动给边定级。

两名标注者独立穷举 30 对，报告 exact agreement、actionable（`E_a ∪ E_s`）二元一致率、类别混淆矩阵与加权 κ；小样本同时列原始分子/分母，不只报 κ。预设检查目标为 actionable 边界一致率 ≥90%、类别 exact agreement ≥80%、所有方向和 strong-dependency 分歧均经第三人源码裁决。未达到时修订定义并**重新盲标整批**，保留旧版结果；不能只改有争议的 T4 相关边。抽查 evidence `path:line`/hash 对冻结 target 的可定位性、negative contrast 的完整 guard 链、是否错误把 category/文件重合升为可执行边。pilot 输出 graph 摘要与争议表，不改评分。

Graph 冻结后，才对 [T4 v2 三个既有 seed](../releases/flowise-3.1.3-repository-v1-t4-post-sync-window-v2-3seed-analysis-20260923.md) 做**回顾性**任务映射与盲于 POST_SYNC 结果的 exposure 判定，随后解盲行为阶段。逐 seed 列 4 个 initial task 对 pilot 节点的映射、跨 agent covered/delivered 边、`none/thematic-only` 负对照，以及四种关键情形：没有结构机会、结构机会未交付、有交付但未发现、发现后未行动/行动并改变判断。与旧报告的 3 direct、2 lead、2 action、0 strict adoption 对照时，只问这些行为是否落在 pilot 已冻结边及哪个阶段；不把旧标签当边的真值。原报告中的 feedback/storage 等超出此 pilot 或 v1 GT 的内容须标 `outside_pilot`，绝不能据此称 `none`。

pilot 若能可靠区分 positive/negative/direction，并在其**有 coverage 的 T4 子集**中把 sparse collaboration 定位到结构稀疏、交付、识别、行动或判断阶段，才算解释性检验通过。若三 seed 中 pilot 没有足够的 cross-agent covered/delivered 边，则结论为“taxonomy 可测，当前 T4 稀疏性解释不足”；按预先定义的下一源码簇扩展，不声称整个 T4 没机会。既有三 seed 和已知 finding 会带来回顾性解释偏差；独立验证需在 graph 冻结后用未参与构图的新运行或新 case，且须另行授权任何 live 实验。

## 8. 扩展与主要 validity threats

pilot 通过后，按冻结 v1 的 20 roots、5 qualified near misses 与经独立代码审定的 bounded unscored work fronts 分批建立节点；先覆盖每个 root 的源/宿/guard 和真实 safe sibling，再审跨簇共享 helper、授权不变量和正负差分。每批保留全有序 pair universe、自动候选来源、人工边界裁决与 non-candidate 抽样漏边率；版本化发布 graph digest、标注协议、节点/边数量和 uncertain 界限。GT generation 或 target 变更时新建 graph，不覆盖 v1。历史 run 只作只读 retrospective mapping；任何 agent-run-derived 新节点在后续 generation 记录来源，参与其发现的历史 run 不算独立泛化证据。

主要威胁及控制：v1 GT 不完备造成节点/密度下界（报告 scope、`unmapped` 与敏感性界限）；静态调用图与配置分支不保证真实可达（要求 source→sink/guard 链、必要时有界离线验证）；同一 root variants、双向边或一个 action 对多边会放大计数（合并 root、单独有序判边、主 action 只归一边）；pilot 选取 credential 簇可能高估全仓关系密度（只报告该簇结果，扩展分层）；标注者知道历史 T4 会发生 hindsight bias（构图盲于 traces，冻结后才映射）；宽泛 task scope 不等于实际证据覆盖（核对 ACTIVE 证据）；交付/利用受 condition 的工具与预算影响（结构 graph 保持 condition-blind，事后分阶段统计）；一次判断变化可能仍不正确（独立 correctness 复核）；v1 与待激活 v1.1 的 GT 漂移和历史候选循环性（绑定 generation/hash，绝不混用分母）。

本方案的判定对象始终是**冻结 benchmark 中可由代码证据支持的潜在信息价值**。实际 task、交付、发现、行动和判断只用于在 graph 冻结后解释未利用机会，不能倒过来决定 graph 的节点或边。
