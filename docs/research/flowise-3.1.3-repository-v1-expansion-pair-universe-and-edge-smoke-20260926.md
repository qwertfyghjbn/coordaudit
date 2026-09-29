# Flowise repository-v1 expansion 462-pair universe 冻结与 edge smoke

日期：2026-09-26。范围仅为两件事：冻结 `expansion-pair-universe-v1`，以及对正式
edge reviewer 包做一次 **non-production** smoke。正式 462-pair 双人盲标、裁决、
完整 702-pair graph 冻结、run mapping 与 Stage 9 更新均未开始。

## 462-pair universe 冻结

- 基础核对通过：graph-v2 冻结 16 节点 / 240 条 old-old 有向对完整唯一；
  `expansion-node-set-v2` 冻结 27 节点（新增 11），与
  [`expansion-node-gate-audit`](flowise-3.1.3-repository-v1-expansion-node-gate-audit-20260926.md)
  一致。
- `scripts/freeze_hidden_graph_pair_universe.py` 以 render/verify 双命令从冻结输入
  确定性重 deriving 全部产物；`pair_universe.jsonl` 每行
  `pair_id / source_node / target_node / pair_class / node_set_version`，不含任何
  opportunity label。
- validator 结果：total=462、old_to_new=176、new_to_old=176、new_to_new=110、
  duplicates=0、self_edges=0、overlap_with_existing_240=0、missing=0、
  no_extra_beyond_702_minus_240、pair_id 模式与端点全集检查全部通过。
- 绑定：case `flowise_3_1_3_repository_v1`、target SHA-256
  `c612819a…1638`、node set `expansion-node-set-v2`（manifest `9a745bc7…b840`、
  nodes `c506905e…6807`）、base graph `graph-v2`、annotation protocol
  `repository-v1-hidden-opportunity-graph-20260923`、schema 1.0.0。
- 产物（私有，0600）：`artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/expansion-pair-universe-v1/`
  下 `pair_universe.jsonl`（SHA-256 `8bcd6380…302c`）、`pair_universe_manifest.json`
  （`e6308ea5…37c4`）、`pair_universe_validation.json`。
  `expansion-node-set-current.json` 与历史冻结资产未被改动。

## 正式 reviewer 包与 smoke

- `scripts/prepare_hidden_graph_expansion_edge_smoke.py` 沿用 Pilot B round-3
  自足包模式（rubric + bundle + form template + manifest，全部带 SHA-256 并在
  verify 时逐字节复核），rubric 五级 taxonomy、decision_order、structural vs
  operational 区分与 round-3 一致，另加 non-production 声明、access-log 要求和
  excerpt hash 规则。构包自检确认包内不含任何已冻结 edge ID 或标签。
- smoke 选择规则（预先定义、与历史标签无关）：按 pair_class 分组、pair_id 字典序、
  每组取索引 0 与 len//2，共 6 对，覆盖三类与 6 个不同节点：
  F001→F017、F009→F017（old→new）；F017→F001、F022→F009（new→old）；
  F017→F018、F022→F023（new→new）。
- 两名隔离子代理（expansion-smoke-reviewer-a/b）并行独立完成 6 对判断，
  输出与 access log 存于 `expansion-edge-smoke-v1/reviews/`；
  `scripts/check_hidden_graph_expansion_edge_smoke.py check` 12 项 gate 全过，
  状态 `smoke_passed`；控制侧人工读核见同目录 `smoke_manual_review.json`
  （verdict smoke_pass）。
- smoke 结果明确标记 `non_production_infrastructure_validation_only`，不得并入
  正式标注；正式阶段须对全部 462 对（含这 6 对）重新独立盲标。

## 遗留到正式阶段的事项

- smoke 未出现 actionable/strong 判例，actionable 专属必填字段路径仅被 schema
  逻辑覆盖、未经真实判例行使；且与标签无关的选择规则无法刻意抽出 actionable 对。
- 正式包可吸收两条 reviewer 反馈：non-none 证据要求明确覆盖 thematic-only /
  direct relation；声明 mechanisms 词表是否开放。
- smoke 中 bundle 预计算 `shared_code_paths/shared_symbols` 对 6 对均为空，而源码
  实际存在共享 helper（F022/F009 的 `readUserByEmail`）；该字段只是候选提示，
  正式 rubric 已按 round-3 口径声明"共享本身不定级"，无需改结构。
