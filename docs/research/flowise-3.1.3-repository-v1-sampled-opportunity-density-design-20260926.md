# repository-v1 sampled opportunity-density：预注册设计

日期：2026-09-26。状态：抽样清单与盲标包已冻结，正式标签产生前确定本设计。

## 输入核对与停止背景

- `expansion-node-set-v2` 冻结 27 节点，其中 graph-v2 既有 16 节点、新增 11 节点；node manifest SHA-256：`9a745bc77c4d9ad2f9a34e9946546459f9899ac10e0860b435921af96c96b840`。
- 全体有向异节点 pair 为 `27 × 26 = 702`。graph-v2 旧节点内部 240 对已有 Pilot A/B 冻结结构标签；`expansion-pair-universe-v1` 冻结另外 462 对，分别为 old→new 176、new→old 176、new→new 110。pair universe manifest SHA-256：`e6308ea59dbb152a3591a955a1522ddf5b5995bdc765f09a3356f5b202e337c4`。
- Batch-01 冻结了 66 对新 pair；其原始 binary 一致为 65/66，exact 五类一致为 44/66。Batch-03 的 66 对原始 binary 一致仅 57/66，低于预注册 `ceil(0.90×66)=60` 门槛；五类一致 42/66。Batch-03 未裁决、未冻结，其标签不是 graph truth，也不进入本次估计。
- exhaustive expansion 已因 actionable binary agreement 未通过预注册门槛而停止；本任务改为 sampled estimation，不是继续完成原全量计划。当前五类 rubric 的 substantive taxonomy、decision order、record requirements 沿用 `expansion-edge-rubric-v1`。本任务仅收窄 reviewer 可读材料，明确 100 对样本的行政范围。

## Estimand 与设计

主要目标是冻结的 702 对中 `actionable cross-check ∪ strong dependency` 所占比例。其他三类与五类细分只作描述。每个 directed pair 是一个抽样单元，反向 pair 独立入样。

按旧／新节点方向划四层，分别无放回简单随机抽样。排序键为 `SHA-256("repository-v1-hog-density-20260926-v1|<stratum>|<source>|<target>")`；每层取散列值最小的固定数量，碰撞以 pair 字典序打破。抽样脚本不读取 edge label、run 或 collaboration 结果。

| Stratum | 总数 N | 样本 n | 入样概率 | 设计权重 |
|---|---:|---:|---:|---:|
| old→old | 240 | 34 | 34/240 | 240/34 |
| old→new | 176 | 25 | 25/176 | 176/25 |
| new→old | 176 | 25 | 25/176 | 176/25 |
| new→new | 110 | 16 | 16/110 | 110/16 |
| 合计 | 702 | 100 | — | — |

100 对约占总体 14.2%，对应 200 条独立 reviewer 记录。在 prevalence 为 5–10% 的量级，二项近似 95% 半宽约 4–6 个百分点；这是成本与绝对精度的折中，不能精确分辨极低 prevalence 的细小差异。四层配额接近总体占比，但不是严格 self-weighting；总体点估计必须加权。

若 Pilot、graph-v2 或 Batch-01 pair 落入样本，两个 reviewer 也从同一盲包重新标注；旧标签不提供给 reviewer，不进入估计器。这样所有样本对使用同一 raw agreement gate。Batch-03 failed 标签也不会被复用。冻结 node metadata 只用于节点语义和旧／新归属；没有使用 security cluster 进一步分层，避免事后定义分组。

## Reviewer、QC 与估计规则

两个独立 reviewer agent 只可读取盲包四文件及冻结 target 源码树。盲包节点条目排除了 `gt_root_ids`、`truth_status`、旧 `adjudication_status` 与 `boundary_rationale`；没有历史条件行为、旧 edge label、peer 输出或裁决。access log 记录各自声明读过的路径；校验器验证声明范围及引用源码的 path/line/excerpt/hash。日志是 reviewer 自报，不能当作 OS 级访问证明。正式标注前，两个模板记录的机械 smoke 对 bundle、schema、access 范围正反例和禁止标签字段完成检查；smoke 不产生正式标签。

预注册 primary gate：100 对 raw reviewer 的 actionable binary 一致至少 90 对。失败即停止估计并报告 taxonomy reliability failure，不能靠第三人裁决把失败轮变成通过。exact 五类一致、五类 confusion matrix、reviewer marginals 和分歧类型照常报告，但不构成 primary gate。通过后仅对样本内五类分歧或 actionable 边界 uncertainty 做第三人裁决；保留所有 raw 记录，不修 rubric 或 reviewer threshold。

设第 h 层总体大小为 `N_h`，样本大小为 `n_h`，最终样本 actionable 数为 `y_h`。总体密度估计 `p̂ = Σ_h (N_h/702)(y_h/n_h)`，可行动 pair 总数估计为 `702p̂`。报告分层无放回设计方差 `Σ_h (N_h/702)^2(1−n_h/N_h)s_h²/n_h`，其中 `s_h² = n_h p̂_h(1−p̂_h)/(n_h−1)`；95% 正态近似区间截在 0–1。小 positive count 时其覆盖率有限，应与原始各层计数共同解读。若最终仍有 uncertain，则分别把这些 sampled pair 全设为 non-actionable 和 actionable，按同一权重给出下／上敏感性界。

本研究只估计 benchmark 的静态结构机会密度，不产生 exact full-graph density、T4 run-conditioned mapping、架构特定 utilization 或 coordination 效果判断。

## 冻结材料

- [机器可读预注册](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/sampled-opportunity-density-v1/sampling_prereg.json)
- [100 对样本与每对入样概率](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/sampled-opportunity-density-v1/sampled_pairs.jsonl)：SHA-256 `1e795ddd52338df11d0ed045cafe076091efcbdd1e1afb1f3810c8ed23f56981`
- [盲标包 identity](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/sampled-opportunity-density-v1/packet/packet_manifest.json)：packet manifest SHA-256 `1890614a6914fcb7b32728a7e2075b02cc3558ddca5b3a6f7aa4d0570670c71c`
- [smoke QC](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/sampled-opportunity-density-v1/smoke_qc.json)
