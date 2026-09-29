# repository-v1 Hidden Opportunity Graph 离线格式 v1

本格式实现[构建规划](repository-v1-hidden-opportunity-graph-plan-20260923.md)的输入锁定与结构校验。它只供可信控制侧离线使用；不向 Agent workspace、`runs/`、prompt、task board 或 tool output 写入 graph 信息。

## 存放与命令

默认私有工作区为 `artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/graph-v1/`。`artifacts/*` 已被 `.gitignore` 忽略，graph 目录以 `0700` 创建。原 `evaluator_private/flowise_3_1_3_repository_v1/` 是 case manifest 绑定的冻结树，不在其中新增文件。代码位于 `scripts/hidden_opportunity_graph.py`，不进入 harness 的 runtime source digest。

```bash
python3 -m scripts.hidden_opportunity_graph init
python3 -m scripts.hidden_opportunity_graph validate
# 一批节点、边和原始标注写完后：
python3 -m scripts.hidden_opportunity_graph stamp-draft
```

`init` 只创建空白草稿，重复执行时要求现有输入锁完全一致。`validate` 只读。`stamp-draft` 仅更新草稿文件的 SHA-256，然后运行校验；冻结状态拒绝更新。变更冻结输入或协议时新建 graph version，不覆盖原锁。Pilot A 已冻结，当前校验结果为六节点、30 个有向对、`status=valid_frozen`；它只代表 Pilot A 校准范围，不代表全仓 graph 已完成。

## 冻结输入

`input_lock.json` 固定 `case_id`、`graph_version`、`graph_schema_version`、`annotation_protocol_version`、target tree SHA-256、原 evaluator-private tree SHA-256、GT generation，以及下列文件的仓库相对路径和 SHA-256：case manifest、v1 GT、safe siblings、validation metadata、构图协议、已批准的静态验证边界 ADR。它还记录节点纳入规则与 Pilot A 六组候选 ID；六节点结论来自后续独立边界复核，不由输入锁预设。

每次校验重新计算冻结 target 与 evaluator-private 树摘要，并检查 GT 与 target 的绑定。输入锁或协议文件变更会使校验失败。结构标注只使用锁定的 target、v1 GT、safe siblings、validation metadata 和威胁模型；历史 T4 行为不得用于节点或边定级。

## 文件与字段

`graph_manifest.json` 包含 graph/case/target/GT/协议身份、输入锁摘要，`nodes.jsonl`、`edges.jsonl` 与三个原始标注日志的 SHA-256，以及 `adjudication_date` 和 `adjudication_status`（`draft` 或 `frozen`）。文件摘要改变后必须显式执行 `stamp-draft`。冻结状态要求 ISO 日期、至少两个节点和已裁决的节点；边只可为 `adjudicated` 或 `uncertain`。

`nodes.jsonl` 每行一个调查单元，必填：`node_id`（`F001` 等稳定序号）、`security_question`、`code_scope`（target 相对文件路径数组）、`invariant`、`boundary_rationale`、`potential_artifact`、`evidence_refs`、`truth_status`、`gt_root_ids`、`adjudication_status`。可填 `near_miss_ids` 与 `uncertainty_note`。`truth_status` 为 `scored_positive`、`qualified_near_miss`、`admitted_unscored` 或 `unresolved`；前两类分别要求有效的 v1 root 或 near-miss ID。root variant 不另建节点；安全 sibling 只在窄范围源码链成立且构成独立问题时建节点。

`edges.jsonl` 对每个**不同节点的有序对**恰好一行，包括 `none`。`edge_id` 为 `graph-v1:<source_node>:<target_node>`；`direction` 固定为 `source_to_target`，反向另写一行。其余必填字段：`opportunity_type`、`mechanisms`、`source_artifact`、`target_claim`、`expected_effect`、`bounded_check`、`evidence`、`rationale`、`confidence`、`adjudication_status`、`reviewer_ids`、`uncertainty_note`。五类 `opportunity_type`、actionable 边界和 strong dependency 必要性按构建规划 §3。actionable 边须有非空的 A artifact、B claim、差分检查、效果和两端证据；非 `none` 边至少有 `source` 与 `target` 两种证据角色；`none`/`thematic-only` 的 `rationale` 应写排除理由。

每个源码证据项包含 `path`、`line`、`symbol`、`excerpt`、`excerpt_sha256`，边证据另有 `role`。`excerpt` 是从 `line` 开始的原样源码片段，hash 为其 UTF-8 字节的 SHA-256；校验器检查文件位于冻结 target 内、行号与片段一致。路径不可为绝对路径或包含 `..`。`symbol` 与代码语义是否正确仍须人工复核。graph 的 node/edge 字段白名单排除 runtime 工具、condition、预算等字段。

三个原始日志也使用 JSONL，并纳入 manifest 摘要：

| 文件 | 一行记录的必填内容 |
| --- | --- |
| `node_reviews.jsonl` | `reviewer_id`、`candidate_a/b`、各自 security question、`decision`（`split/merge/uncertain`）、`counterfactual`、`rationale`、`evidence_refs`。 |
| `edge_reviews.jsonl` | `reviewer_id`、有向端点、五级类别，以及与最终边相同的机制、最小信息、检查、证据、理由和置信度字段。 |
| `adjudications.jsonl` | `kind`（`node_boundary/edge`）、`item_id`、`adjudicator_id`、`decision`、`rationale`、`reviewer_ids`。 |

当前校验器验证 JSON 形状、引用、摘要、证据定位、有序对完整性和冻结状态的基本约束。它不能单独证明盲标独立性或源码推理正确；盲标隔离记录、第三人裁决与 Pilot A QC 报告构成另一个核验层。离线 condition 可实现性和 run mapping 使用单独文件，不进入本 graph manifest 或结构边分类。

## Pilot A 节点边界复核

`scripts/prepare_hidden_graph_pilot_a.py` 从私有 `pilot_a/source_spec.json` 与冻结源码生成六组 `candidate_packets.jsonl`、15 对单人 `boundary_preliminary.jsonl` 和摘要。给独立标注者的材料是 **`pilot_a/reviewer_bundle.json` 与 `review_form_template.jsonl`**；bundle 不含初判标签。标注者各自使用模板填写 15 对 split/merge/uncertain、反事实、理由和双侧源码证据，并分别保存为 `pilot_a/reviews/reviewer_a.jsonl`、`reviewer_b.jsonl`。复核者须避免查看其他人的记录、`boundary_preliminary.jsonl` 和任何历史 run 信息。

```bash
python3 -m scripts.prepare_hidden_graph_pilot_a verify
python3 -m scripts.check_hidden_graph_pilot_a_nodes check
# 仅在真实独立双人记录及必要的第三人裁决齐全、QC 通过后：
python3 -m scripts.check_hidden_graph_pilot_a_nodes freeze-nodes
```

若两人有分歧或共同标为 uncertain，第三人以 `pilot_a/reviews/adjudicator.jsonl` 对相应候选对记录决定、反事实、理由和双侧证据。`check` 核算 15 对覆盖、至少 14/15 一致、分歧裁决与最终分解；若最终有合并，标为 `pilot_revision_required`，不强作六节点或 30 对分母。通过时 `freeze-nodes` 生成私有 `nodes_frozen.jsonl` 与 `node_boundary_qc.json`，并把原始双人记录绑定到草稿 manifest。此时 `nodes.jsonl` 与 `edges.jsonl` 仍为空，下一阶段才建立完整有向边矩阵。测试中的模拟 reviewer ID 只验证 QC 代码，不构成真实独立标注。

2026-09-23 的另一会话预复核在 15 对上均判 split，与单人初判同向；该会话曾读包含历史结果的规划，记录也未按更新后的盲标模板提交，NM04 的若干源码行号引用还需订正。因此只保留为预复核旁证，不计入双人盲标一致率。预复核指出 R06 的导入路径后，私有证据包补入 `workspace:import` 入口、Assistant `workspaceId` 改写和保存锚，并重新生成摘要。正式标注应从更新后的 `reviewer_bundle.json` 开始。

更新包随后交由两个互不共享会话记录的独立标注上下文各自审查 15 对候选，原始记录分别保存在私有 `pilot_a/reviews/reviewer_a.jsonl` 与 `reviewer_b.jsonl`。两份记录均判 15 对 split，节点边界一致率 15/15；源码行及 excerpt hash 校验通过，无 `uncertain` 或分歧，无需第三人裁决。私有 `pilot_a/node_boundary_qc.json` 记录 reviewer/bundle 摘要和 QC 结果，`pilot_a/nodes_frozen.jsonl` 固定六节点语义及 30 个有向对分母。随后才开始边标注。

## Pilot A 有向边校准与冻结

`scripts/prepare_hidden_graph_pilot_a_edges.py` 从已裁决的六节点生成完整 30 个方向的私有盲标包。首轮两名独立标注者各交 30 条记录；actionable 二元一致 26/30，低于规划要求的 90%，故保留 `pilot_a/edges/edge_round1_qc.json` 和原始记录，不将首轮结果冻结。第三人复核分歧后，`scripts/prepare_hidden_graph_pilot_a_edges_round2.py` 仅把通用边界规则写入新版包，未把首轮逐边标签或历史 run 结果给第二轮标注者；两名新标注者对全部 30 个方向重新独立盲标。

第二轮 actionable 二元一致 28/30（93.33%），五级 exact agreement 为 26/30（86.67%），二次加权 κ 为 0.94；15 个无序节点对中，actionable 方向集合一致 13 对。第三人对类别分歧及附不确定说明的 14 个方向作源码裁决，含两条 actionable 边界争议；最终 30 条边均已裁决，无 `uncertain`。分类为 `none` 8、`direct relation` 19、`actionable cross-check` 1、`strong dependency` 2，`thematic-only` 0。三个最终 actionable 方向分别是 `F001→F004`、`F004→F006`（strong）和 `F006→F004`（cross-check），均有 A/B 双侧冻结源码锚。NM04 与 credential 节点的负对照只达到 `direct relation`，未升为 actionable。

最终主图的 `graph_manifest.json`、`nodes.jsonl`、`edges.jsonl`、`edge_reviews.jsonl`、`adjudications.jsonl` 均保存在上述私有工作区。`pilot_a/edges_round2/edge_qc.json` 保存两轮版本链、双人原始记录摘要、裁决摘要、混淆矩阵、正例和方向分歧及控制对结论。冻结后使用以下只读命令复核：

```bash
python3 -m scripts.hidden_opportunity_graph validate
python3 -m scripts.check_hidden_graph_pilot_a_edges check --round 2
```

`prepare_hidden_graph_pilot_a_edges* verify` 只适用于冻结前的草稿构包阶段。Pilot A 结果仅校准此六节点范围的结构 taxonomy；后续 Pilot B 和 condition/run 可实现性须另行判断，不能用此图的边密度外推全仓。

## Pilot B 源码分层候选与新版本

Pilot B 使用独立的 `graph-v2` 草稿；原 `graph-v1` 保持冻结。`graph-v2/input_lock.json` 绑定相同的 target、v1 GT、协议与威胁模型，并额外绑定 Pilot A 冻结 manifest 和私有 `pilot-b-prep-v1/packet_manifest.json`。候选包从 v1 GT 中剔除 Pilot A 六项后，按规划的五层列出剩余 root/qualified near miss；文件/存储层另有两项从冻结路由、控制器、存储与验证源码提出的 **bounded unscored question**。21 项均是待审候选，不因 GT 身份、同层归属或源码锚自动获得节点资格，也不预判文件/存储问题的真值。

```bash
python3 -m scripts.prepare_hidden_graph_pilot_b_candidates verify
python3 -m scripts.prepare_hidden_graph_pilot_b_candidates_round2 verify
python3 -m scripts.hidden_opportunity_graph validate --graph-version graph-v2
python3 -m scripts.check_hidden_graph_pilot_b_candidates check --round 2
```

第一轮候选资格独立评审得到 20/21 的纳入决定一致，R16 已经第三人裁决；但共同口径把若干安全路径仅因漏洞未成立而排除，与规划 §2 允许独立安全 near miss 节点的规则不符。原始记录和 `pilot-b-prep-v1/node_round1_manual_qc.json` 保留。`pilot-b-prep-v1/round2/` 给新的隔离标注者提供完整 21 项重盲标包，只加入通用资格澄清，并把 R02 的源码函数定位提示更正为冻结快照中的实际函数；不包含首轮逐项标签。`check --round 2` 要求两份完整记录、至少 19/21 的纳入决定一致，以及对全部分歧或不确定项的第三人裁决。通过资格 QC 后仍须按每层至多两项、不同 source→sink/guard 问题优先及固定字典序做选择，再审所选节点间和 Pilot A 节点间的 split/merge 边界。确定 `|V|` 后，才能建立 `|V|(|V|-1)` 的完整有向对矩阵并进行独立边盲标。

资格 QC 通过后，人工选择者在私有 `pilot-b-prep-v1/round2/selection_spec.json` 记录 `selection_version=pilot-b-selection-v1`、`selected`、`excluded_admitted` 与 `empty_strata`。每个 `selected` 项填写 `candidate_id`、区分同层问题的 `distinct_mechanism`、`selection_rationale` 和 `potential_artifact`；每个已合格但未选项记录其 `distinct_mechanism` 和排除理由。人工先按安全问题和必要 source→sink/guard 链归并同层机制；选择校验要求每层按 target-relative path、symbol、invariant 的字典序取前两个不同机制的最早候选，拒绝超过两项、遗漏合格候选或把合格层留空。机制归并本身仍须在选择理由中用源码解释。

本次第二轮资格记录对 21/21 项一致判定可纳入，文件/存储两项的范围说明经第三人依据源码裁决；两者仍为未评分的有界问题，未预断安全真值。按固定分层与排序选出 `NM01、R01；NM02、R02；U_FILE_02、U_FILE_01；R13、R11；R14、R17`，五层各两项。对所选节点与 Pilot A/其他所选节点的 105 个无序边界对，两份独立记录 105/105 同判 split，无需第三人边界裁决。`pilot_b/node_boundary_qc.json` 与 `nodes_frozen.jsonl` 固定了 16 个节点（新增 6 个 scored root、2 个 qualified near miss、2 个 admitted unscored）及 240 个有向对分母，其中 210 个是待审新增方向。

边标注首轮虽各完成 210 个方向，但一名标注者披露读到了 schema 文档中的 Pilot A 已冻结边类别；`pilot_b/edges/edge_round1_manual_qc.json` 将其明确记为受污染预审，原始记录保留且不计正式一致率。第二轮两名新标注者在写入前对完整规划作了越界搜索，检索输出含历史 T4 与 Pilot A/QC 文字，故在 `pilot_b/edges_round2/edge_round2_manual_qc.json` 记录停止、无正式标注。第三轮 `pilot_b/edges_round3/` 在包内提供自足的五级 taxonomy、证据字段与精确的可读路径，仅允许新的隔离上下文读取该包和冻结 target/GT/safe siblings/verification metadata；该轮 210 对的双人结果才可进入正式边 QC。

随后由两个隔离上下文分别审查所选节点与 Pilot A、以及所选节点彼此之间的全部无序边界对。设新增节点数为 `n`，需审 `6n+n(n-1)/2` 对；该阶段要求至少 90% 的 split/merge 决定一致、分歧经第三人裁决、最终没有未决或合并边界，才生成 `nodes_frozen.jsonl`。边包只包含新增方向，数量为 `(6+n)(5+n)-30`；Pilot A 已冻结的 30 个方向按原摘要继承，并在最终 graph 中换用新版本的 edge ID。新增方向仍须双人独立盲标、actionable 二元一致至少 90%、正例及方向分歧经裁决、最终 actionable 边有 A/B 双侧源码锚，才可冻结完整矩阵。

```bash
# 两份节点资格记录和必要裁决到齐后
python3 -m scripts.check_hidden_graph_pilot_b_candidates check --round 2
# 选择记录通过后，生成所选节点的盲标包
python3 -m scripts.prepare_hidden_graph_pilot_b_boundaries build
# 两份边界记录和必要裁决到齐后
python3 -m scripts.check_hidden_graph_pilot_b_boundaries check
python3 -m scripts.check_hidden_graph_pilot_b_boundaries freeze-nodes
# 节点语义固定后，核对正式第三轮新增方向盲标包
python3 -m scripts.prepare_hidden_graph_pilot_b_edges_round3 verify
# 两份边记录和必要裁决到齐后
python3 -m scripts.check_hidden_graph_pilot_b_edges check
python3 -m scripts.check_hidden_graph_pilot_b_edges freeze-edges
python3 -m scripts.hidden_opportunity_graph validate --graph-version graph-v2
```

`graph-v2` 冻结前，选择、边界和边记录的状态均应以各自的 QC 命令为准；草稿结构校验通过不代表正式盲标或质量关口通过。若主要一致率未达门槛，应保存失败轮记录、修订通用定义并对相应整批重新盲标，不能用第三人裁决把失败轮直接转为通过。
