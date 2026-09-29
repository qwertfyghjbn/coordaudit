# Flowise repository-v1 expansion 462-pair 正式标注批次规划

日期：2026-09-26。本会话只做 batch planning：把冻结的 462-pair universe 拆成
7 个可恢复、可审计、负载相对均衡的执行单元。未启动 reviewer A/B，未做任何
adjudication，未改 pair universe，未冻结 structural graph。

## 输入与核验

输入为已冻结的 `expansion-pair-universe-v1`（manifest SHA-256 `e6308ea5…37c4`，
pairs `8bcd6380…302c`），`freeze_hidden_graph_pair_universe verify` 与内嵌
validator 全过（462 / 176 / 176 / 110，无重复、自环、与 240 old-old 重叠或缺失）。
批次 manifest 绑定 node set `expansion-node-set-v2`（manifest `9a745bc7…b840`）、
graph-v2、annotation protocol `repository-v1-hidden-opportunity-graph-20260923`。

## 分批算法（deterministic、label-blind、history-blind）

`scripts/plan_hidden_graph_edge_annotation_batches.py`（plan/verify 双命令，逐字节复核）：

1. 每个 pair_class 内按 `pair_id` 字典序升序（canonical order）。
2. 7 个 batch（`edge-annotation-batch-01..07`），每批 66 对。
3. 类配额 = base `N//7` + extras `N%7`；extras 按固定类别顺序
   (new_to_old, new_to_new, old_to_new) 逐类给"当前总量最小、编号最小"的 batch，
   机械产出唯一可行组合：batch-01=(25,26,15)、batch-02..06=(25,25,16)、
   batch-07=(26,25,15)，每批恰 66。
4. 类内蛇形轮发（偶数轮 01→07、奇数轮 07→01，跳过配额已满 batch）。
   纯升序轮发会使 batch-01 拿到各类位置 ≡0 (mod 7) 的全部 pair（176≡1 mod 7），
   把同一无序节点对的双方向集中到单批（实测 26 个 dual-direction dyad 落在
   batch-01）；蛇形把该对齐打散为 0–9 个/批。

分配只使用 pair_id / source / target / pair_class 与批次算术，不使用任何机会
类型猜测、Pilot A/B 历史 edge 标签、T4/P/B/S/M 行为、actionability、verification
或 Stage 9 结果。

## 批次与校验结果

| batch | n | old→new | new→old | new→new | both-dir dyads | max src | max tgt |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 01 | 66 | 25 | 26 | 15 | 8 | 4 | 4 |
| 02 | 66 | 25 | 25 | 16 | 3 | 4 | 5 |
| 03 | 66 | 25 | 25 | 16 | 9 | 5 | 5 |
| 04 | 66 | 25 | 25 | 16 | 1 | 5 | 5 |
| 05 | 66 | 25 | 25 | 16 | 7 | 4 | 5 |
| 06 | 66 | 25 | 25 | 16 | 0 | 4 | 5 |
| 07 | 66 | 26 | 25 | 15 | 8 | 6 | 5 |

全局 validator 全过：coverage 462/462、7 批、每批 66、批内无重复、任意两批交集为
空、missing 0、unknown pair 0、类总和 176/176/110、每批类分布极差 ≤1。每批
distinct sources 25–27 / distinct targets 27，代码区域（components vs server 端点）
占比稳定（21–25 vs 107–111），无 source/target/cluster 集中。

产物（私有，0600）：`artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/expansion-edge-batches-v1/`
下 `batch-01..07/{manifest.json, pairs.jsonl}` 与 `batch_index.json`
（SHA-256 `ea438110…d22c`）。manifest 含 batch_id、pair universe 版本与 digest、
node set 版本、pair_count、三类计数、pair_ids、batch_digest、`status=planned`。

## 执行语义（已写入 batch_index.json，未启动）

每批：reviewer A/B 并行独立盲标（隔离上下文、自足 packet，模式同 smoke 包）→
schema/completeness QC → agreement report → disagreement-only 第三人裁决 →
batch freeze。reviewer 不得见对方结果、此前批次最终标签、裁决摘要或任何
history-based 协作结果；若需历史批次才能理解 rubric，判为 package 缺陷，修
bundle 而非开放标签。checkpointed：batch N+1 仅在 batch N 冻结后启动。rubric/
schema 在 batch-01 正式开始后冻结；必须修改时开新 batch-plan 版本并显式列出
失效批次，禁止静默混用。
