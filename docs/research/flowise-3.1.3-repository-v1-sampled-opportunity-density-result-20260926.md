# repository-v1 sampled opportunity-density：结果与限定解释

日期：2026-09-26。状态：`sampled-opportunity-density-v1` 已冻结。本报告只针对冻结的 Flowise 3.1.3 `repository-v1` 27-node、702 directed-pair universe；它不是完整图的逐边真值。

## 执行与 QC

抽样遵循[预注册设计](flowise-3.1.3-repository-v1-sampled-opportunity-density-design-20260926.md)：四层固定 SHA-256 排序、无放回取 100 对。两个互不共享标注上下文的 reviewer agent 各自重盲标全部 100 对，包含落入样本的 34 条 old→old 和 12 条 Batch-01 既有标签对。旧标签未进入盲包或正式估计。packet 的节点语义、冻结源码、五类 rubric 与模板通过先行机械 smoke；两份正式记录的 schema、源码摘录/hash 和声明 access 范围均通过校验。access log 为 reviewer 自报，不是 OS 级文件访问审计。

原始双人 actionable binary 一致 **97/100 = 97%**，达到预注册 `≥90/100` 门槛。五类 exact 一致 **74/100 = 74%**。26 个五类分歧中，3 个跨 actionable 边界，23 个只在 non-actionable 三类内部；没有 actionable subtype 分歧或 reviewer `uncertainty_note`。第三人仅裁决这 26 对，没有修订 rubric、重训阈值或更改原始记录；3 个 binary 边界争议最终都裁为 actionable。最终无 uncertain pair。

| Reviewer A \ Reviewer B | none | thematic-only | direct relation | actionable cross-check | strong dependency |
|---|---:|---:|---:|---:|---:|
| none | 46 | 4 | 0 | 0 | 0 |
| thematic-only | 7 | 20 | 1 | 0 | 0 |
| direct relation | 3 | 8 | 5 | 2 | 0 |
| actionable cross-check | 0 | 1 | 0 | 3 | 0 |
| strong dependency | 0 | 0 | 0 | 0 | 0 |

Reviewer marginal：A 为 `none 50 / thematic-only 28 / direct 18 / cross-check 4 / strong 0`；B 为 `none 56 / thematic-only 33 / direct 6 / cross-check 5 / strong 0`。binary matrix 为双方 non-actionable 94、双方 actionable 3、A only 1、B only 2。由于正例稀少，97% overall agreement 之外还应看 positive-specific agreement **66.7%** 和 binary Cohen κ **0.651**；通过预注册门槛不等于边界没有标注误差。

## 加权估计

最终样本 actionable 为 **6/100**。各层使用 `N_h/n_h` 权重，总体点估计为 **6.00%**，即在 702 对中估计约 **42 对** actionable structural opportunity。原始 6/100 是描述性分数；正式总体估计由四层加权给出，两者接近是本次近比例配额的结果。

| Stratum | 总体 N | 样本 n | Actionable y | 层内估计 |
|---|---:|---:|---:|---:|
| old→old | 240 | 34 | 4 | 11.76% |
| old→new | 176 | 25 | 0 | 0.00% |
| new→old | 176 | 25 | 1 | 4.00% |
| new→new | 110 | 16 | 1 | 6.25% |

预注册的分层有限总体方差给出 SE **2.20 个百分点**，95% 正态近似区间为 **1.69%–10.32%**，对应约 **12–72 对**。六个 positive 使正态近似的尾部覆盖不稳；补充的逐层超几何精确反演加 Bonferroni 同时区间为 **1.28%–26.07%**，对应 **9–183 对**，明显更保守。两种区间都反映抽样误差，不包含全部分类误差。最终 uncertain 为 0，所以按 uncertain 全排除／全纳入的预注册敏感性界均为 **6.00%**。

## 标注稳定性与解释边界

以下为正式估计完成后的**事后诊断**，不替换预注册估计器：若将 3 个 raw binary 分歧一律设为 non-actionable／actionable，加权密度范围为 **2.99%–6.00%**。这 3 对都位于 old→old 层，因此该层 11.76% 的表面较高值尤其依赖裁决。

与冻结旧标签的重叠也只用于跨轮稳定性审计：34 条 graph-v2 old→old 重叠中 binary 一致 31 条、五类 exact 一致 14 条；12 条 Batch-01 重叠中 binary 一致 11 条、五类 exact 一致 6 条。将这些历史重叠标签**事后替换**会得到约 4.02% 的描述性数值，但此操作违反统一重盲标口径，不能作为正式估计。四条跨轮 binary 冲突表明 taxonomy 仍有一定标注敏感性；未修改旧冻结 graph 或 Batch-01。

**对研究问题的回答：** 在固定的 27-node 全有向 pair universe 中，actionable relation 的点估计处于个位数百分比量级，支持“总体较稀疏”的限定说法。样本中 old→old 观察到 4/34，其他方向合计 2/66；可以说 old→old 在本样本中更集中，但各层 positive 很少，不能可靠排序或断言 old→new 的真实密度为零。稀疏结构机会可以帮助解释 observed collaboration 为何可能较少，给“该固定节点宇宙的平均 pair collaboration pressure 较低”提供有限支持；保守区间仍允许明显高于点估计的密度，实际 run 触及的节点对也可能富集 actionable relation，因此不能单靠本抽样强称整个 benchmark 在所有工作分配下 pressure 都低。

本研究不能推出 exact 702-pair graph density、未入样单个 pair 的标签、特定运行中机会是否可实现或被利用、任何架构的 utilization、T4 coordination 质量，也不能解释运行时没有协作的因果来源。低结构密度不是 T4 coordination 良好的证据。

**建议：停止为当前密度问题继续构建 462-pair exhaustive HOG。** 这轮 sampled estimate 已给出成本可控的量级判断；Batch-03 曾因 57/66 actionable binary agreement 低于 60/66 预注册门槛而失败，原全量计划已停止。本研究不恢复 Batch-02..07、不冻结 Batch-03 failed 标签、不更新 frozen runtime。若将来确需逐边 atlas，应作为新的独立研究目标评估可靠性、成本和标注口径。

## 冻结输出

- [样本清单与设计](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/sampled-opportunity-density-v1/sampled_pairs.jsonl)、[盲包 identity](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/sampled-opportunity-density-v1/packet/packet_manifest.json)、[smoke](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/sampled-opportunity-density-v1/smoke_qc.json)
- [Reviewer A](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/sampled-opportunity-density-v1/reviews/reviewer_a.jsonl)、[Reviewer B](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/sampled-opportunity-density-v1/reviews/reviewer_b.jsonl)、[分歧裁决](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/sampled-opportunity-density-v1/reviews/adjudicator.jsonl)
- [原始 QC](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/sampled-opportunity-density-v1/qc_report.json)、[最终样本标签](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/sampled-opportunity-density-v1/final_sample_labels.jsonl)、[加权估计与区间](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/sampled-opportunity-density-v1/density_estimate.json)、[事后稳定性诊断](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/sampled-opportunity-density-v1/posthoc_robustness.json)
- [样本冻结摘要](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/sampled-opportunity-density-v1/sample_freeze.json)
