# Flowise repository-v1.1 retrospective rescore（2026-09-21）

状态：**有效的只读描述性重评；不是新的独立 benchmark 实验**。GT identity 为 `flowise_3_1_3_repository_v1_1`，GT SHA-256 为 `4e41103ecbe6d96cb0bbe3cc54c0c4a574ac21d7825bc2adc36c723ee5978da8`，v2 计分分母固定 30 roots。case 的 live gate 未因此开放。

## 范围与产物

历史 run tree 中发现 69 个 Flowise repository-v1 manifest；68 个具备原始 `merged_findings.json`、`evaluation.json` 和 private verification，均已只读重评。`single_n1_20260919T044459.225844+0000_d31ce38b` 缺少这些完成产物，仅列入排除清单。原 unmatched ledger 的 63 个 run、94 条已聚类 finding 全部在 68 个适用 run 中。

全部新产物位于 `artifacts/retrospective/flowise_repository_v1_1_evaluator_v2_20260921/`：68 份逐 run `retrospective.json`，以及 `summary.json`、`transition_matrix.json`、`circularity_summary.json`、`manifest.json`。manifest SHA-256：`0ddedba014df9b0e6efdebb4215dbb5e7698ab0ed50cc40c3a6cc6eaa82df430`。两个不同历史 block 复用了 `run_id=matched-seed-01`，所以逐 run 以原目录相对路径消歧，不改原 block/run identity。

## v1 unmatched → v2 transition

计数单位是原 evaluator-v1 标为 `unmatched_review` 的单条 finding，**不是**独立漏洞数或 root 数。68 个适用 run 共 122 条；其中 94 条来自原聚类账本，另外 28 条来自账本之后的适用 run。

| v2 状态 | 122 条中的数量 | 原 94 条中的数量 |
|---|---:|---:|
| `canonical_tp` | 39 | 34 |
| `equivalent_tp` | 15 | 14 |
| `validated_novel_tp` | 0 | 0 |
| `false_positive` | 25 | 25 |
| `inconclusive` | 3 | 3 |
| `gt_overlap_uncredited` | 8 | 8 |
| `unmatched_unreviewed` | 20 | 0 |
| `duplicate_root` | 12 | 10 |

`gt_overlap_uncredited` 表示独立裁决把该 claim 关联到冻结 root，但历史 finding 的锚/约束不足以取得 formal TP；不进入 canonical TP，也不伪装成 GT 外 novel。`duplicate_root` 同样不增加 TP。`validated_novel_tp=0` 是因为已验证的历史候选已纳入本版 root 或等价锚；不能把它们再作为 GT 外新发现计分。UC26 按冻结 TM6 规则保留为非 positive 的 `inconclusive`。

冻结的旧 root 中，R02、R05、R07、R08 带有锚修复/漂移口径。本批历史 finding 实际从 v1 unmatched 转成 formal TP 的漂移修复只有 **R08：2 条 equivalent TP**；R02、R05、R07 在这批提交证据中为 0。其他旧 root 的新增 equivalent 命中按 `transition_matrix.json` 的 root/anchor 明细追溯，不混称函数名漂移修复。

## Condition 仅作描述

以下为 run 与 root-hit 的总量，v1 分母是每 run 20 roots，v2 是每 run 30 roots；不同 condition 的 run/seed 数不平衡，不能用这些总量排序 topology。

| condition | runs | 原 v1 TP | v2 canonical TP | v2 equivalent TP |
|---|---:|---:|---:|---:|
| S | 37 | 8 | 26 | 7 |
| P | 5 | 0 | 2 | 1 |
| B | 5 | 0 | 2 | 0 |
| T | 18 | 5 | 21 | 7 |
| M | 3 | 0 | 0 | 0 |

## Circularity 与回归

32 个 run 的 retrospective 结果涉及 agent-run-derived GT/等价锚；其中 28 个是本次 GT additions 的历史发现源。每份逐 run 产物显式记录 `agent_run_derived_gt_overlap`、对应 cluster/root/anchor，以及 `independent_generalization_evidence=false`。所有 retrospective TP 均只表示新版规则下的历史归类，不能作为 agent 的独立泛化证据，更不能据此声称任一 topology 优于其他 topology。

重评预检发现并修复两处 v2 缺陷：一是历史 finding 的短函数名与引号路由签名导致同文件、同冻结 excerpt 的合法锚漏匹配；现在仅在文件和 excerpt 精确对应时接受受限别名。二是已裁决但未满足 formal 锚约束的 GT-overlap 被误列为未审阅 novel；现在单列 `gt_overlap_uncredited`。修复后重新运行 v2 定向回归与全量预检，68 个原 v1 public/private 结果逐一复现，v2 每 run 重复计算相同，30-root 分母与唯一性全量通过；独立产物写入后再生并逐字节核验 72 个文件，同时核验所有历史输入 hash。未修改任何原 run artifact、v1 result、preregistered score 或 block identity。

`RETROSPECTIVE_RESCORE_VALID = yes`。该判断仅针对上述只读、可复现的描述性重评，不改变原实验解释或 case live gate。
