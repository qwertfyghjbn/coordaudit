# Flowise repository-v1 expansion node gate 核查

日期：2026-09-26。范围仅为 graph-v2 后续 11 个 opaque 候选的 qualification、
split/merge 与 node-set 冻结；不开展边标注或历史运行重映射。

## 9/11 与 10/11 的预注册口径

- [`repository-v1-hidden-opportunity-graph-plan-20260923.md`](repository-v1-hidden-opportunity-graph-plan-20260923.md)
  §2 规定先裁决节点边界再固定分母；§8 规定通过两个 pilot 后分批扩展、先做
  split/merge QC。它没有为这 11 项 expansion qualification 预注册 90% 门槛。
- [`hidden-opportunity-graph-schema-v1.md`](hidden-opportunity-graph-schema-v1.md) 的
  19/21 是 Pilot B 的 21 项资格重盲标专用门槛；至少 90% split/merge 是 Pilot B
  所选节点边界的门槛。规划 §6 的 90% 是 Pilot A actionable 边一致率门槛。
- 因此 10/11 = `ceil(0.9 × 11)` 只是扩展 QC 脚本后来引入的**非预注册、非阻断参考值**。
  原始两人资格决定一致 9/11（81.818%）；C01、C06、C11 含分歧或 uncertain，
  第三人逐项裁决后 11 项均 admit、无 unresolved。保留原始 9/11，不通过裁决
  将其改写成 11/11，也不重跑资格整批。

## 资格原始记录

三份 qualification/adjudication 原始记录已从临时目录只读复制到私有
`artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/expansion-qc-v4/reviews/`，
各文件 SHA-256 写入 `qualification_preservation.json`；原 `/tmp` 文件仍保留。
`node_eligibility_qc.json` 是重新运行 QC 后的结果，不是新的盲标。

资格只确认候选是否可形成 bounded investigation question。两份资格记录与第三人
裁决继续作为后续节点冻结的输入，没有因 9/11 低于非门槛参考值而重跑。

## Boundary smoke、完整复核与身份修订

两名隔离 boundary reviewer 先各审 C01、C02 两行作为 smoke；schema、源码
excerpt/hash 与候选锚点回连均通过。之后各完成 11 行，覆盖 16 个既有节点与
11 个新候选的全部 **231 个无序 split/merge 对**。v5 原始记录与第三人仅对
分歧作的裁决，保存在私有 `expansion-qc-v4/boundary_reviews/`。

冻结前核对 candidate 到 evaluator-private 目标身份时，发现 C01、C04、C11 的
早期问题表述分别偏向 workspace 范围、对象范围、会话归属，未精确表达各自锚点的
变量值导出、路由动作权限、会话 ID 运行时类型不变量。已生成的
`expansion-node-set-v1` 因此仅保留为过程记录，**由 v2 取代，不作为最终节点集**。
没有改写原始资格或 v5 boundary 记录。

以不含 GT 标签及历史运行结果的 v6 小包，原两名隔离 reviewer 仅重审
C01、C04、C11；随后针对 C09 的路由动作权限身份，各作一次局部补核。
完整审查中的其他七行保持原样。原始补核、v5 记录、合成后的两份 11 行审查和
第三人裁决均连同 SHA-256 保存在私有
`expansion-qc-v4/boundary_reviews_v6/record_preservation.json`。

最终两份审查在 **228/231** 对上同判；仅 F004–C08、C05–C06、C04–C09
三对存在分歧。第三人只裁决这三对，均判 split。机器 QC 得到 **231 split、
0 merge、0 uncertain**，没有未解决候选。C04 与 C09 虽都涉及路由动作权限，
但分别保护 ChatMessage 与 UpsertHistory，修复一处不会修复另一处。

## 最终冻结范围

[`expansion-node-set-current.json`](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/expansion-node-set-current.json)
指向 `expansion-node-set-v2`。v2 在 graph-v2 的 16 个既有节点上新增 11 个独立节点，
共 **27 个节点**；覆盖既有 evaluator-private 集合的 20 个 roots、5 个 qualified
near misses，并保留 2 个既有 admitted-unscored 节点。冻结 manifest 的 SHA-256 为
`9a745bc77c4d9ad2f9a34e9946546459f9899ac10e0860b435921af96c96b840`，
状态为 `frozen_nodes_only`。v2 重算核验通过，graph-v2 仍为有效冻结状态。

本轮只冻结节点。新增有向边、边合同、运行映射及扩展后的结构分母均未开展；
不能把这 27 个节点称为已冻结的完整 graph。
