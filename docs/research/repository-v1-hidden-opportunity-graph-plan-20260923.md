# repository-v1 Hidden Opportunity Graph 构建规划

日期：2026-09-23。状态：规划；尚未构建或标注 graph。适用 case：`flowise_3_1_3_repository_v1`，目标快照 SHA-256 为 `c612819a833fc8ab3c58fe5085fb80fc0a6c4cb1d86cbb8ed41b0b431e4a1638`。本文只定义 evaluator-side 离线资产与事后分析方法；不修改 frozen runtime、task assignment、prompt、tool surface、evaluator scoring 或历史 run。

## 1. 已核对的事实与研究边界

- [case manifest](../../experiments/emergent_coordination/manifests/flowise_3_1_3_repository_v1.json) 将 S1/P4/B4/T4 指向同一 Flowise 3.1.3 target、`repository-v1` prompt/finding schema 与 evaluator；T4 v2 是另行冻结的 4-agent、192 team permits 诊断合同，见 [v2 manifest](../../experiments/emergent_coordination/manifests/t4_flowise_post_sync_window_v2.json)。不得把它当作 S/P/B/T matched architecture block。
- evaluator-private [v1 ground truth](../../experiments/emergent_coordination/evaluator_private/flowise_3_1_3_repository_v1/ground_truth.json) 有 20 个 scored root、5 个 qualified near miss；[safe siblings](../../experiments/emergent_coordination/evaluator_private/flowise_3_1_3_repository_v1/safe_siblings.json) 另有仅供对照、不能证明整条路径安全的条目。root variant 不另计独立 finding。v1 GT 不是完整漏洞宇宙；[覆盖审计](flowise-3.1.3-repository-v1-gt-coverage-audit-20260921.md) 已记录未匹配真实候选和 v1 anchor 的局限。
- T4 的初始任务由 agent 在运行中 `create_task`、`claim_task`，ID 含随机 UUID，scope 也由 agent 选择；`initialization_lease_v1` 只排序首次 board 决策，不指定审计范围。[task board](../../experiments/emergent_coordination/harness/task_board.py) 与 [sequenced bootstrap 记录](../releases/flowise-3.1.3-repository-v1-t4-sequenced-bootstrap-v1-192p-20260921.md) 均支持这一点。S 没有跨 agent task；P/B 的分工也不能以 T4 task ID 表示。
- [T4 POST_SYNC v2 三 seed 分析](../releases/flowise-3.1.3-repository-v1-t4-post-sync-window-v2-3seed-analysis-20260923.md) 记录 12/12 agent 获得同步后首次请求，3/12 表达 direct relation，2/12 形成 actionable lead，2/2 lead 被验证，2/2 有证据后的判断，最终 foreign `evidence_ref` 纳入为 0/12。[人工定义](t4-post-sync-inspection-manual-adjudication-v1-20260922.md) 中的 strict selection 要求明确 foreign task ID；v2 为 0/12。这些是**已发生行为**，不是 benchmark 中潜在机会的分母。12/12 runtime window delivered 不等于 12/12 graph-relevant opportunity delivered。
- `repository-v1.1`/evaluator-v2 仍是[待激活的独立 generation](../releases/flowise-3.1.3-repository-v1.1-evaluator-v2-freeze-handoff-20260921.md)。本 graph v1 只绑定 v1 快照与 v1 GT；v1.1 候选不能悄悄改写其节点、边或历史分母。后续版本须有新 graph identity，并标记从历史 agent run 派生的证据循环性。

**两层定义**：**Structural Opportunity Graph** 是 benchmark/evaluator property：只依据冻结源码、v1 GT 与明确威胁模型，判断调查单元 A 可产出的具体信息是否有潜力改变 B 的判断、验证路径或必要搜索工作。它不要求某次 agent 真的产出、传递或利用该信息，也不以 S/P/B/T/M 的工具、通信、visibility、预算或生命周期为边的纳入条件。`客观` 指代码证据可复核，不声称 GT 完备。**Condition-specific Operational Realizability** 是 graph 冻结后的 condition/run property：再判断某条结构边在真实工具、通信、可见性、预算和生命周期约束下能否实现。结构上可执行与运行中可实现必须分别报告。

```text
Frozen repository snapshot → canonical investigation nodes → node split/merge QC
→ Structural Opportunity Graph → graph freeze
→ condition-specific Operational Realizability → run mapping
→ coverage → delivery → discovery → action → evidence consumption → judgment/disposition
```

## 2. 节点：冻结快照上的调查单元

主节点采用 **evaluator-side canonical investigation unit（调查单元）**：一个可独立推进、有明确 source/affected object/security invariant 与结论问题的 bounded work front。节点 ID 由 `case + snapshot + graph version + stable ordinal` 确定，例如 `F001`；ID 不含 seed、condition、agent ID、运行时 task ID 或 finding 文本。每个节点记代码范围、具体安全问题、可能产出的最小信息、证据锚、状态（scored positive / qualified near miss / admitted unscored / unresolved）和私有 GT root 映射。一个 root-cause cluster 的多个 manifestation/variant 合并；只有不同安全不变量且可独立裁决时才拆节点。安全 sibling 只有经过窄范围 source-chain 证明、且本身构成独立判断问题时才作节点；否则只作边证据。

**Split/merge decision protocol**：先为每个候选写一句 security question、待判定结论和必要的 source→sink/guard/ownership/reachability 链，再对相邻候选逐对判断：(1) 问题或被保护对象/不变量是否实质不同；(2) 两者能否独立得到不同真值，一方为真/假是否不会直接决定另一方；(3) 是否需要独立的 source→sink、guard、ownership 或 reachability 推理。不同问题且存在独立结论与必要推理时拆分，即使共享文件/helper；若只是一项 root cause 的入口、表现或 variant，且同一关键证据足以决定两者，则合并。GT root ID 不自动证明应拆，同文件/同类别也不自动证明应合。边界含混时记录反事实与争议，先 adjudicate 节点，再固定 `|V|` 和有序对分母；不能用 edge agreement 掩盖节点粒度分歧。

选择理由：GT root 稳定但只有正例且 v1 不完备；finding candidate 取决于某次模型，不能作为客观分母；initial task 的 ID 与范围随 seed/architecture 变化。调查单元以源码与问题为身份，先固定 graph，再用独立的 `run task/finding → node` 映射表解释行为。未能可靠映射的实际任务记 `unmapped/out_of_graph`，不得当作 `none`。若两个 agent 重复调查**同一节点**，记录为 node-level duplicate work；主 graph 不造自环或把它膨胀成跨节点边。

## 3. 有向边与互斥 taxonomy

对每个不同节点的**有序对** `A → B` 独立裁决：A 是可提供最小信息的 source，B 是可能受益的 target；`B → A` 必须另审，允许不同类别。双向成立时保存两条 directed record，不用无向边或 `bidirectional` 缩写。`none` 也保留在完整 pair matrix 中，以固定分母和支持漏标审计。第一优先分界是 **structurally actionable**（`actionable cross-check ∪ strong dependency`）与 non-actionable；五级细分仍记录，`strong dependency` 是更强的次级 subtype。最终主分析只使用 `adjudicated` 且非 `uncertain` 的边。

| `opportunity_type` | 必须满足的判定标准 | 不计入可执行机会的界限 |
| --- | --- | --- |
| `none` | 无可证实的共享代码、控制或信息价值；或现有证据反驳所猜关系。 | 不能仅因未观察到 agent 互动就判 `none`。 |
| `thematic-only` | 只共享漏洞类别、包、文件、宽泛攻击面或抽象主题；未指出 A 的哪份结论会触及 B 的哪条具体路径/判断。 | 同为 authorization、SSRF、同文件，至多到此级。 |
| `direct relation` | 代码证明共享**具体** helper、source/sink、调用链、guard 或授权不变量，并能说清信息关联；但尚无最小、可区分结果的 B 判断/验证行为，或预期节省的搜索工作不具体。 | 不能因为“可能有用”而自动升为 actionable。 |
| `actionable cross-check` | 在 direct 之上，明确 A 可产出的证据、B 的目标 claim，以及一个抽象的最小验证行为或可证明省去的重复子搜索；写明正/负结果将如何 validate、refute、narrow、extend B，或如何避免重复查同一子问题。B 可不依赖 A 独立完成。 | 无指定对象和区分性结果的“去看看”不算；某 condition 暂无 `read_file`/search、通信或剩余 permits 不使结构边消失。 |
| `strong dependency` | 满足 actionable，且 B 的关键结论**逻辑上依赖** A 所调查的具体子命题（例如同一 sink 的实际 guard 或调用链可达性）；A 的结论是 B 证据链所需的前提/反证，不只是加速。须给出必要性论证与反事实：若该子命题为假，B 的结论如何改变。 | 不是运行时 `task.dependencies`，也不要求 B 只能由 A 来查；“同一类别/同一服务”不足以成立。 |

判定顺序先问 actionable/non-actionable，再对已证实的 actionable 区分 `actionable cross-check` 与 `strong dependency`；每个有序对恰好一个主类别。多个价值机制（shared sink/source/control、shared authorization invariant、common helper/call chain、positive/negative differential、validate/refute/narrow/extend、de-duplication）放入 `mechanisms[]`，不另叠加计数。`bounded_check` 描述结构层的最小信息检查或复用行为，例如 inspect helper X、compare guard Y、trace caller Z、check negative differential；不指定某个 condition 必须提供哪种工具。若两个方向都似乎有用，分别写 A 可给 B 与 B 可给 A 的具体信息；信息价值不对称时只保留相应方向的高等级。若 actionable 已证实而 strong 的必要性未证实，归 `actionable cross-check` 并在 rationale 记 subtype 争议；只有 actionable 边界本身证据不足时才将边标 `uncertain`，不把猜测升档。

## 4. 标注协议与隐藏性

1. **固定输入和盲化**：先记录 case ID、target/GT/safe-sibling 文件 SHA-256、graph schema 版本、节点纳入规则与 pilot 范围。结构标注者只看冻结 target、v1 evaluator-private GT、safe siblings、validation metadata 和已批准的威胁模型；节点与边冻结前不看 T4 transcript、finding、score、task 结果或各 condition 表现。公开 advisory/provenance 只能帮助定位代码，不能替代快照上的 source→sink/guard 证据。
2. **先裁节点边界**：两名标注者独立审查同一候选源码/GT 锚，按 §2 给出节点拆分/合并及反事实理由；比较分歧，由第三人依据源码裁决，固定节点语义和 `|V|` 后才标边。Pilot A 尤其不能把六个预列候选直接当作无争议的六个节点。
3. **生成高召回边候选**：从已固定节点的 root/sibling 锚和代码索引提取函数、调用者/被调用者、共享查询谓词、route guard、source/sink、对象归属与安全不变量；提出有序候选及反向边。对候选写最小 A artifact、B claim 和抽象差分检查。自动化只能提出候选，不能定级；类别相同、同目录或词向量相似只可用于待审队列。pilot 穷举全部有序对；全量扩展时抽样复核机器未提名对以估计漏边。
4. **独立双人边标注与 adjudication**：两名标注者分别按 §3 判所有 pilot 有序对，先判 actionable/non-actionable 和方向，再判五级 subtype。每条非 `none` 边至少给两处 target-relative `path:line`/symbol（A 证据与 B 消费点）、所依据的 excerpt hash、最小信息包、B 的预期决策/省工以及正负结果；`none`/`thematic-only` 也记排除理由。第三人依据源码裁决分歧；证据无法闭合的边留 `uncertain`，列出缺失事实与可能区间。禁止用某次 run 的实际 action 证明机会存在。冻结 adjudicated graph 与 digest 后才进行 condition/run 分析；发现漏边/错边需版本化修订。
5. **Condition-specific Operational Realizability**：另建离线 condition 判定表，不写回 graph。逐结构 actionable 边核对 S/P/B/T/M 的真实工具、信息传递通道、visibility、team permits、可用阶段与生命周期，判断最小信息能否从 A 到 B、B 能否执行抽象检查；状态为 `yes/no/uncertain` 并记依据。再于预定的结果交接点按历史 run 的剩余预算/窗口标记 run-specific realizability；若此前 agent 已耗尽预算，将这种资源结果与合同本身不可实现分开报告。这一步只读冻结合同与事件账本，不用 agent 是否选择相关行动来反推“可实现”。S 的跨 agent 机会不适用，另计单 agent 的内部复用。
6. **运行映射分离**：另一份表把每个 run 的 task/finding 映射到零个或多个调查单元，记录 `scope_declared`、实际触及的 code/evidence、映射信心和 run ID；只用 ACTIVE/RESULT_SYNC 前证据确定 coverage 与 A artifact 是否产生。然后才解盲 POST_SYNC 的可见消息、动作与最终 finding，按 [ADR-0004 lineage 边界](../adr/0004-model-visible-transcript.md) 连接 event、transcript、task、evidence、finding。依次报告 structurally actionable、operationally realizable、covered、delivered、discovered、acted、evidence consumed、judgment affected；泛称相似不能代替显式证据链。

Graph 文件及原始 adjudication 只放 trusted evaluator-side 私有区域或独立受限离线 artifact；运行目录中的 `runtime/target`、Agent workspace、tool output、task board、prompt、model-visible transcript、公开 case manifest 都不能引用或复制它。离线分析器必须在 run 完结后单向读取 graph 和脱敏 trace；不得从 graph 回写任务、消息、动态提示、工具结果或 live score。公开报告仅发布经审查的聚合指标和必要的脱敏例子；`evaluator_private` 内容、GT 标签、source-case provenance 不进入 Agent mount。规划文档本身也不得被用作审计 Agent 的输入。

## 5. 建议的 versioned schema

私有 `graph_manifest` 记录 `graph_schema_version`、`case_id`、`target_sha256`、`gt_generation`/GT SHA-256、safe-sibling SHA-256、`annotation_protocol_version`、节点/边文件哈希、adjudication 日期与状态。`nodes.jsonl` 一节点一行，至少含 `node_id`、`security_question`、`code_scope`、`invariant`、`boundary_rationale`、`evidence_refs`、`truth_status`、`gt_root_ids`、`adjudication_status`。`boundary_rationale` 简述 §2 的拆分/合并理由；GT 身份与详细 code evidence 不发布给 Agent。

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
  "bounded_check": "抽象最小检查，例如 inspect helper X / compare guard Y，及其正负结果",
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

`direction` 的唯一合法值为 `source_to_target`，方向由两个 node 字段决定；反向另写一行。`none` 边可用空 `mechanisms/evidence`，但必须有排除理由。`confidence` 为 `high/medium/low`，只表示代码证据强度；`adjudication_status` 为 `proposed/agreed/adjudicated/uncertain/rejected`，与 confidence 分开。生产统计只接收 `adjudicated`；`uncertain` 给上下界敏感性分析。`source_artifact`、`target_claim`、`expected_effect` 与抽象 `bounded_check` 对 actionable/strong 必填。graph 的 node/edge schema **不含** `read_file`/search 等 runtime 工具、condition 或预算字段；节点和边在同一 graph version 中不可更改 ID 语义。

独立的离线 operational/run mapping 记录只需关联 `edge_id`、condition/run ID、`operationally_realizable`（`yes/no/uncertain`）、工具/通信/visibility/预算/生命周期依据，以及后续 coverage→disposition 阶段与 event/transcript refs。它不属于 graph identity，不能作为结构边存在或分类的输入。

## 6. 指标与分母

设 `V` 为已裁决调查单元，`D = |V|(|V|-1)` 为不同节点的 directed pair universe；`E_d`、`E_a`、`E_s` 分别是 `direct relation`、`actionable cross-check`、`strong dependency`。结构指标只按 graph 的**唯一边**计，`E_actionable = E_a ∪ E_s` 与 architecture 无关。graph 冻结后定义 condition `c` 合同下可实现的子集 `R_c ⊆ E_actionable`，run `r` 在预定交接点的可实现子集 `R_{c,r} ⊆ R_c`。行为指标以 `(run_id, edge_id, source_agent, target_agent)` 为一次 opportunity instance，同一边可在一个 run 中有多个接收方，但一名接收方的同一边只计一次。所有指标按 graph version、case 与 GT generation 报告；不把 variant、同节点重复或 `uncertain` 混入点估计，并附 uncertain 全纳入/全排除界限。

| 指标 | 定义与解释 |
| --- | --- |
| benchmark opportunity density | 主值为 `|E_actionable|/D`（结构上可执行的 directed density，与 condition 无关）；另报宽口径 `(|E_d|+|E_a|+|E_s|)/D`、无向 dyad 数及各类数量，避免方向双计造成误读。 |
| actionable opportunity count | `|E_actionable|`，同时报 strong 单列、每类边数与有至少一条入/出 actionable 边的节点比例；不按某 condition 可用工具扣减。 |
| operational realizability | 分别报 condition 合同的 `|R_c|/|E_actionable|` 与 run 交接点的 `|R_{c,r}|/|E_actionable|`，列不可实现/不确定的边数及工具、通信、visibility、预算或生命周期原因；二者都不修改 graph。零分母记 N/A。 |
| opportunity coverage | 每 run 报 `R_{c,r} 中至少有一个 cross-agent covered instance 的唯一边数 / |R_{c,r}|`，并列报相对全部 `E_actionable` 的覆盖率。covered 要求 A、B 被**不同** agent 实际调查，且 A 的特定子问题有可分享结果；另报 node coverage。`delivered instances / covered instances` 单列，不混入 coverage。delivered 要求 A 结果在 B 决策前实际进入 B 的 model-visible context；可用窗口已在 realizability 层判定。 |
| opportunity utilization rate | `used instances / delivered instances`；`used` 要求 B 在看见 A artifact 后完成与该边匹配的验证/明确省去重复子搜索，或基于可追溯证据作出 disposition。另报 `discovered/delivered`、`acted/discovered`、`evidence_consumed/acted`、`judgment_affected/evidence_consumed`。仅提及 foreign 主题不算。零分母记 N/A。 |
| discovered / missed opportunity | `discovered` 要求 B 明确识别 A 的具体 artifact 与 B 的关系；另记原 T4 strict task-ID selection，不能重写既有 0/12。`missed = operationally realizable 且 delivered，但未 discovered`；结构边不可实现、未覆盖或未交付均另列，不记 missed。识别了但无 action 单列。 |
| architecture-specific reuse rate | 每 condition 先报结构边中的 `realizable/actionable`，再以可实现的 instance 报 `delivered/covered`、`used/delivered` 与 `used/covered`，区分 **strict foreign-ref provenance** 和 **claim-level disposition**；后者不能冒充前者。S1 没有跨 agent 分母，改报 within-agent cross-front reuse；P4 如无信息通道则 `R_c=0`、后续条件率 N/A。B4/T4/M 依各自真实合同判 realizability，再按实际 model-visible 证据判 delivery。 |
| 每类 opportunity 利用率 | 对 `actionable cross-check`、`strong dependency` 分别报告 realizability、coverage、delivery、discovery、action、evidence consumption、judgment/disposition、strict/claim reuse；`direct relation` 只报描述性相关性，`none/thematic-only` 只做误触/负对照，不当 actionable 分母。 |

对被调查的节点对先判 `no_structural_link`（graph 为 none/thematic）、`direct_nonactionable`、`out_of_graph` 或 structurally actionable；前三种不能记成 agent 漏发现。对 actionable 边再区分 `operationally_unrealizable`、`no_cross_agent_coverage`、`covered_not_delivered`、`delivered_not_discovered`、`discovered_no_action`、`acted_no_new_evidence`、`evidence_seen_no_disposition`、`confirmed_without_change`、`judgment_changed`（strengthened/weakened/refuted/narrowed/extended）。这些是离线分析标签，不是新增 runtime state。`judgment_changed` 必须对照 B 行动前后的同一 claim；确认原判断属于 `confirmed_without_change`。另记正确性复核，不能把 judgment 变化直接算成正确 TP。若一个实际 action 匹配多条边，预先按最具体 evidence/claim 绑定主边并保留次级映射，主计数只算一次。

## 7. 两阶段小规模 pilot 与质量控制

### Pilot A — taxonomy calibration

保留六个**候选**调查单元：v1 GT 的 R04、R05、R06、R20，窄范围安全对照 NM04，以及同一 TTS 文件但不同不变量的 R19。它们用于测试 positive relation、negative differential、同文件异 invariant、方向和 actionable/non-actionable 边界；不是按 T4 行为选的，也不预判任一条边。预期六节点、30 个 directed pairs。先将这六组源码/GT 锚交给两名标注者独立作 §2 的 split/merge 判定，比较 15 个无序候选对的节点边界决定，第三人裁决后才冻结六节点语义和 30 对分母；若六节点分解经源码审查不能成立，暂停并版本化修订 pilot，不强行以 30 对计算 edge agreement。R04/R05/R06 的 v1 独立 root 身份是候选依据，R20 的 caller/helper 关系与 NM04 的窄适用范围仍须独立核验。

节点冻结后，两名标注者各自穷举 30 个方向，优先报告 actionable/non-actionable 的二元一致率与正例分歧、方向一致性、证据 `path:line`/hash 可定位性和 positive/negative control 判定。**主要 QC gate**：节点 split/merge 决定至少 14/15 一致且所有分歧经源码裁决；actionable 二元一致率至少 90% 且每条任一标注者判为 actionable 的分歧边已复核；所有 actionable 方向分歧裁决完成；所有最终 actionable 边的 A/B 证据位置可在冻结快照复核。完整五分类 exact agreement、混淆矩阵与加权 κ 仍报告，但不作为独立阻断门槛。若分歧主要是 `actionable cross-check` 对 `strong dependency`，且上述主门槛通过，可保留 subtype 分歧记录并继续；第三人不能证明 strong 必要性时按已证实的 `actionable cross-check` 冻结，不使整条 actionable 边变成 `uncertain`。主门槛未过则修订定义、保留旧版记录并重新盲标整批。

### Pilot B — explanatory coverage

只在 Pilot A 节点/taxonomy 冻结后选择和标注 Pilot B。现先固定**与历史 T4 行为无关**的源码分层和抽样规则：按 [v1 freeze candidate 的 active fronts](../releases/flowise-3.1.3-repository-v1-freeze-candidate-20260916.md) 与冻结 target/GT 建候选池，覆盖 (1) enterprise 身份、组织与 HTTP route/object guard，(2) credential/secret 的读取与序列化，(3) 文件/存储路径与本地对象边界，(4) process/SQL/session 等本地 runtime capability，(5) model URL/document loader 等出站集成与网络边界。每层至多取两个经 §2 独立源码资格审查的节点；优先不同 source→sink/guard 问题，再按 target-relative path、symbol、invariant 的固定字典序选取；Pilot A 节点不重复入选。若某层没有合格节点，报告空层，不根据 T4 trace 补位。文件/存储层可从 target 的 storage provider、文件 controller 与 validator 源码提出**未预判真值**的 bounded question；v1 GT 没有覆盖这些路径时标明 unscored/uncertain，不能把历史 feedback/storage finding 当作节点来源。其余层优先 v1 root/qualified near miss，safe-sibling contrast-only 条目只作证据，不能自动成节点。

Pilot B 仍先做节点 QC、盲标并冻结结构边，再独立判 S/P/B/T/M 的 operational realizability；之后才对 [T4 v2 三个既有 seed](../releases/flowise-3.1.3-repository-v1-t4-post-sync-window-v2-3seed-analysis-20260923.md) 作**回顾性** task→node 映射。先报告每 seed 的可映射 task/agent 比例、结构 actionable 边、可实现边和 covered/delivered instance；再解盲 POST_SYNC 的 discovery、action、evidence consumption、judgment/disposition。与旧报告的 3 direct、2 lead、2 action、0 strict adoption 对照时，只问行为落在哪条已冻结边和哪一阶段，不把旧标签当边的真值。超出 Pilot B 的 task/finding 记 `outside_pilot/out_of_graph`，绝不能据此称 `none`。

Pilot B 的解释力取决于实际节点映射和可实现机会的覆盖范围：若足够覆盖的子集显示机会止于 realizability、coverage、delivery、discovery 或 action，可给出**该子集**的 sparse-collaboration 分解；若映射太少或没有可实现的跨 agent pair，只报告覆盖不足，不推断整个 T4 没有机会。既有 seed 的分析仍是回顾性解释，不是独立泛化或 architecture 因果比较；未来独立验证需 graph 冻结后的新运行或新 case，任何 live 实验另行授权。

## 8. 扩展与主要 validity threats

Pilot A 的 taxonomy 与 Pilot B 的覆盖检查通过后，按冻结 v1 的 20 roots、5 qualified near misses 与经独立代码审定的 bounded unscored work fronts 分批建立节点；先执行 split/merge QC，再审跨簇共享 helper、授权不变量和正负差分。每批保留全有序 pair universe、自动候选来源、人工边界裁决与 non-candidate 抽样漏边率；版本化发布 graph digest、标注协议、节点/边数量和 uncertain 界限。GT generation 或 target 变更时新建 graph，不覆盖 v1。历史 run 只作只读 retrospective mapping；任何 agent-run-derived 新节点在后续 generation 记录来源，参与其发现的历史 run 不算独立泛化证据。

主要威胁及控制：v1 GT 不完备造成节点/密度下界（报告 scope、`unmapped` 与敏感性界限）；静态调用图与配置分支不保证真实可达（要求 source→sink/guard 链、必要时有界离线验证）；主观 split/merge 会改变 `|V|` 和边密度（先双人判节点、裁决后才判边）；同一 root variants、双向边或一个 action 对多边会放大计数（合并 root、单独有序判边、主 action 只归一边）；Pilot A 的 credential 簇可能高估全仓关系密度（不外推，Pilot B 按源码分层）；标注者知道历史 T4 会发生 hindsight bias（构图盲于 traces，冻结后才映射）；宽泛 task scope 不等于实际证据覆盖（核对 ACTIVE 证据）；交付/利用受 condition 的工具与预算影响（结构 graph 保持 condition-blind，将 contract 可实现性、运行中预算耗尽和 agent 行动选择分开报告）；一次判断变化可能仍不正确（独立 correctness 复核）；v1 与待激活 v1.1 的 GT 漂移和历史候选循环性（绑定 generation/hash，绝不混用分母）。

本方案的判定对象始终是**冻结 benchmark 中可由代码证据支持的潜在信息价值**。实际 task、交付、发现、行动和判断只用于在 graph 冻结后解释未利用机会，不能倒过来决定 graph 的节点或边。
