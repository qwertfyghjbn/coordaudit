# Flowise 3.1.3 repository-v1 graph-v2：阶段 9 限定范围分析与扩展决定

日期：2026-09-24。本文只分析已经冻结的 `graph-v2` 和三个已冻结的
`t4-post-sync-window-v2-192p` matched seed。图绑定 manifest SHA-256
`d7013f79ffd21a7d7eb4a989ed44d16f46fd3d342ae167ca86a085311f69c041`；本报告不修改
`graph-v2`，也不把三个历史 run 当作独立的 architecture 因果比较。

指标由
[`scripts/report_hidden_graph_stage9.py`](../../scripts/report_hidden_graph_stage9.py)
从冻结 graph、Pilot A/B QC 和既有 operational mapping 重新计算，机器结果保存在
[`limited_analysis.json`](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/graph-v2/stage9/limited_analysis.json)。
扩展候选包由
[`scripts/prepare_hidden_graph_expansion.py`](../../scripts/prepare_hidden_graph_expansion.py)
生成，但在独立审定完成前不产生新 graph。

## 结论

- Pilot A 和 Pilot B 的节点边界、二元 actionable QC 均通过；两个 pilot 的最终边均无
  `uncertain` 状态。
- 决定：**不做一次性全量扩展**；可以进入**分批的结构扩展**。当前结果不能称为全仓库
  密度，也不能据此推断整个 T4 的 opportunity utilization。下一批必须建立新的版本化
  graph，不得改写冻结的 `graph-v2`。
- 三个历史 seed 的 Pilot B 映射和跨 agent coverage 不足：每个 run 的 actionable
  coverage 都是 `0/12`。因此行为层只报告覆盖不足；runtime window 的 12/12 delivery
  不能转写为 graph edge delivery。

## 1. 结构密度与分母

规划使用 `D=|V|(|V|-1)` 作为 directed-pair 分母，主密度为
`|E_actionable|/D`；不确定边给出全排除/全纳入上下界。

| 范围 | 节点 | directed pairs | actionable（下界–上界） | actionable density |
| --- | ---: | ---: | ---: | ---: |
| Pilot A | 6 | 30 | 3–3 | 10.000% |
| Pilot B 新增 | 10 | 210 | 9–9 | 4.286% |
| 冻结 graph-v2 | 16 | 240 | 12–12 | 5.000% |

`graph-v2` 的有向边类别为：`none=86`、`thematic-only=108`、`direct relation=34`、
`actionable cross-check=10`、`strong dependency=2`。因此宽口径非 `none` 为
`154/240=64.167%`；有至少一条非 `none` 方向的无序 dyad 为 `77/120`，有至少一条
actionable 方向的无序 dyad 为 `8/120`。这些是 16 节点 pilot 图内的描述，不能外推
到整个 repository。

## 2. Pilot QC 与 uncertain 上下界

| 项目 | 分母 | 结果 | uncertain |
| --- | ---: | ---: | ---: |
| Pilot A 节点 split/merge agreement | 15 | 15/15 | 0 |
| Pilot A actionable 二元 agreement | 30 | 28/30（93.333%） | 0 条最终边 |
| Pilot B 节点 split/merge agreement | 105 | 105/105 | 0 |
| Pilot B 新方向 actionable 二元 agreement | 210 | 203/210（96.667%） | 0 条最终边 |
| Pilot B 方向 agreement | 105 个无序 dyad | 99/105（94.286%） | 0 条最终边 |

Pilot A 的 actionable 下界/上界均为 `3/3`，Pilot B 新增边均为 `9/9`，所以冻结图的
actionable 区间为 `[12,12]`，密度区间为 `[5.000%, 5.000%]`。这里的上下界只反映
最终结构标注中的 `uncertain`；`out_of_graph` 任务或 finding 不是 uncertain 边，也不
会被改写为 `none`。

## 3. Condition-specific operational realizability

合同层分母固定为冻结图的 12 条 actionable directed edges：

| Condition | yes | no | uncertain | realizability（下界–上界） |
| --- | ---: | ---: | ---: | ---: |
| S1 | 0 | 12 | 0 | 0/12–0/12（0%） |
| P4 | 0 | 12 | 0 | 0/12–0/12（0%） |
| B4 | 12 | 0 | 0 | 12/12–12/12（100%） |
| T4 | 12 | 0 | 0 | 12/12–12/12（100%） |
| M4 | 12 | 0 | 0 | 12/12–12/12（100%） |

这一步只说明合同提供或不提供最小信息传递路径，不表示模型实际使用了该路径。三个
T4 run 在同步交接点的 run-specific 分母也都是 `R_{T4,r}=12`，三者均为 `12/12`
可实现；剩余 permit、POST_SYNC reservation 和窗口证据另见 operational handoff
产物。

## 4. 历史 run 的 coverage、delivery 与行为分母

| Run | task（mapped/总数） | finding 文件（mapped/总数） | 映射节点 | coverage 分母 | covered actionable edges | runtime delivery 行 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| seed 01 | 1/4 | 1/3 | 2/16 | 12 | 0（0%） | 4/4 |
| seed 02 | 1/4 | 0/4 | 2/16 | 12 | 0（0%） | 4/4 |
| seed 03 | 2/4 | 2/4 | 3/16 | 12 | 0（0%） | 4/4 |

三次 run 合计为 12 个 task、11 个 finding 文件；未映射项分别保留为
`out_of_graph`。由于没有任何 run 形成跨 agent 的 covered actionable edge，graph-relevant
delivery 的分母为 0，`delivered/covered`、`used/delivered`、`discovered/delivered`
以及后续 graph-edge action rate 均为 **N/A**，不能用 12/12 runtime delivery 行填充。

解盲后的 12 个 agent-run 行只作描述性记录：delivery 12/12、direct relation 3/12、
actionable lead 2/12、evidence consumed 2/2、judgment changed 2/2、strict foreign
evidence-ref adoption 0/12；3 个被选中的 foreign artifact 均保留为
`out_of_graph`。这些数字没有进入结构边 coverage 分母。

## 5. 扩展决定与范围限制

`graph-v2` 当前覆盖 v1 GT 中 20 个 roots 的 11 个、5 个 qualified near misses 的 3 个，
另有 2 个 admitted-unscored fronts。Pilot QC 足以支持下一步**分批结构扩展**，但当前
coverage 不足以支持全量行为结论。

下一步按以下顺序执行：

1. 以新的 graph version 分批处理剩余 9 个 roots 和 2 个 near misses；每批先做节点
   split/merge QC，再穷举该批与既有节点的全部有向 pairs。
2. 独立资格审查并裁决新增 unscored fronts；不能从 T4 历史 finding 补位，也不能把
   当前两个 unscored 节点当作完整 unscored universe。
3. 每批冻结后重新计算 `|V|`、`D`、各类边数、actionable uncertain 上下界及五个
   condition 的 `R_c`；如果引入新运行，再单独重新计算 `R_{c,r}`、coverage 和
   graph-relevant delivery 分母。
4. 在出现足够跨 agent 映射之前，只报告 coverage 不足；不把未观察到的 edge instance
   判成 `none`、missed opportunity 或整个架构的 utilization 结论。

剩余候选只是待独立节点 QC 的源码锚点，不是已冻结节点或边。新增 unscored front
的数量与身份尚未确定，不能提前放入分母。

已建立去标签、未标注的第一批候选包
[`expansion-prep-v4-blind`](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/expansion-prep-v4-blind)，
包含 11 个 opaque 候选、既有节点边界摘要、盲化规则和 11 行匹配的空白审定模板，并
固定为 4/4/3 三个批次；其状态为 `verified_ungraded_blind_node_batch_plan`。v4 不含
ground truth、source-case 标签、provenance、历史运行或既有 edge labels。此前 v1/v2/v3
包只作构建过程记录；没有任何一个旧包生成新 graph 或进入结构、行为分母。

v4 的两份盲标已各覆盖 11/11 候选，证据路径、行号、excerpt 与 SHA-256 均通过
target 回连；双人二元决定一致为 9/11（81.818%）。C01、C06、C11 的分歧或
uncertain 记录已由独立第三人逐项裁决，最终 11 项均无 unresolved。节点资格 QC
状态为 `ready_for_boundary_and_selection_qc`；9/11 作为非预注册、非阻断的参考
诊断保留。后续完整 boundary QC 与局部身份复核已完成，最终独立节点集冻结为
[`expansion-node-set-v2`](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/expansion-node-set-v2)，
详见[节点关口核查](flowise-3.1.3-repository-v1-expansion-node-gate-audit-20260926.md)。
此处阶段 9 的 graph-v2 分母和运行映射不变；新增边尚未审定，因此没有生成 graph-v3。

## 6. 复核命令

```bash
python3 -m scripts.report_hidden_graph_stage9 run
python3 -m scripts.report_hidden_graph_stage9 verify
python3 -m scripts.prepare_hidden_graph_expansion verify
python3 -m scripts.prepare_hidden_graph_expansion_blind verify
python3 -m scripts.check_hidden_graph_expansion_nodes check
python3 -m scripts.analyze_hidden_graph_operational verify
python3 -m scripts.hidden_opportunity_graph validate --graph-version graph-v2
git diff --check
```

阶段 9 的机器核验通过：结构分母为 240，actionable 区间为 12–12；五个 condition
没有 uncertain；三个 run 的 covered actionable edge 均为 0；扩展决定为
`proceed_staged_structural_expansion_with_coverage_limit`。
