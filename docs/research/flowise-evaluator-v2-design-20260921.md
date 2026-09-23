# evaluator-v1 → evaluator-v2 实现契约（2026-09-21）

> evaluator-v2 已实现为 `repository_v1_1_score.py`，绑定 30-root GT SHA-256 `4e41103ecbe6d96cb0bbe3cc54c0c4a574ac21d7825bc2adc36c723ee5978da8`。GT/case 清单的 `live_gate` 仍为 `blocked`；评分器实现不自动放开正式运行。

> 状态：**实现契约**。前置：[GT 覆盖审计](flowise-3.1.3-repository-v1-gt-coverage-audit-20260921.md)、[repository-v1.1 升级提案](flowise-3.1.3-repository-v1.1-upgrade-proposal-20260921.md)。
>
> 本实现不修改 GT 内容、evaluator-v1、旧 run 或历史得分。2026-09-21 的 retrospective rescore 已另行授权，并写入独立 artifact；见 [重评报告](../releases/flowise-3.1.3-repository-v1.1-retrospective-rescore-20260921.md)。

## 1. 目标与不变量

evaluator-v2（实现名 `repository_v1_1_score.py`，evaluator id `repository_v1_1`）服务 `flowise_3_1_3_repository_v1_1`。不变量：

1. **确定性优先**：formal score 完全由确定性规则产生（ADR-0005 延续）；LLM judge 不进入 formal score。
2. **双视图**：canonical benchmark score（对绑定的 30 roots，即 20 old roots + 10 new roots）与 novel finding adjudication（GT 外 finding 的人工裁决记录）严格分离；novel TP 不回填 canonical 分母。
3. **evaluator-v1 保持原样**：新实现放新文件；旧 runs 的 preregistered 得分不动。

## 2. 判定分类（六个基类及一个已审阅 GT-overlap 状态）

```
canonical_tp            —— 命中冻结 root 的 canonical / accepted primary anchor
equivalent_tp           —— 命中批准的 equivalent anchor，且通过该 root 的不变量证据约束
validated_novel_tp      —— GT 外、经独立裁决确认（只进 adjudication 视图，不进 formal recall）
false_positive          —— 命中 near-miss 或裁决反证
inconclusive            —— 证据不足/依赖运行时（含 known-unscored 面）
unmatched_unreviewed    —— 尚未裁决的 GT 外 finding（默认态）
gt_overlap_uncredited   —— 已有独立裁决关联冻结 root，但提交锚未满足 formal 匹配；不进 TP，也不进 novel view
```

匹配算法相对 v1 的三处变化：

1. **等价锚**：只有 `accepted_equivalent_realizations_v1_1` 批准的锚可匹配；同时合取 category、guard kind、affected object、reasoning terms 与该 root 的版本化不变量概念组。每个批准锚的 `invariant_match_evidence` 必须与 root 的 `semantic_invariant_v1_1` 相同。
   R07/R08 的历史函数名漂移锚仅保留在 GT 谱系中，不在 v2 中作为可执行锚；R02/R05 的 `accepted_primary_anchors_v1_1` 替代相应旧函数标签。
   历史 finding 使用短函数名或引号路由签名时，仅在同文件且冻结 excerpt 仍精确命中的前提下接受受限拼写别名；不同类名或不同路由不能据此匹配。
2. **fingerprint / dedup**：保留 v1 的 category、source、sink、guard、affected object 确定性 fingerprint；同 fingerprint 或同 root 的重复 finding 都不增加 TP。`variant_coverage` 不产生 formal TP。
3. **unmatched 输出结构化**：private `per_finding` 与 `semantic_judge.review_queue` 保留 fingerprint 和分类，供独立裁决流水线消费；不写 GT。

不输出混合 canonical 与 novel 的 precision：GT 外未裁决项存在时，单一 precision 不具备可解释性。

## 3. Semantic judge 边界（明确回答五问）

| 问题 | 回答 |
|---|---|
| 输入是什么 | 未来接口仅可取 deterministic unmatched 的冻结字段及必要静态证据；当前版本不调用 judge。 |
| 是否只用于 unmatched | 是。canonical 匹配永远先走确定性规则；judge 只看规则未命中的 finding。 |
| 是否影响 formal score | 否。judge 输出只写入 adjudication ledger（`validated_novel_tp`/`false_positive`/`inconclusive` 建议 + 依据），formal recall/precision 不变。 |
| 如何避免 judge 自由扩张 GT | judge 无 GT 写权限；其建议必须经人工裁决批次确认后才可能在**下一个版本**（v1.2）进入 GT，且带 agent_run_derived 标记；同一版本内 GT 冻结后不可变。 |
| 是否需要静态/动态证据才能接受 novel TP | 是。接受标准 = 静态 source→sink 链 + missing guard 的 file:line 证据（本次 40 cluster 的裁决即为该标准的执行样例）；仅当静态链不充分（如 KU02 沙箱面）时才要求 targeted local validation 或 dynamic 证据，否则落 inconclusive。 |

当前 `semantic_judge_used=false`，private review queue 是未来接入点。可信裁决通过独立 `adjudications` 控制面映射注入；`validated_novel_tp` 必须具备 reviewer、provenance、condition-blind 标记、independent code validation 和 source/sink/guard evidence。Agent 字段或 judge 建议不能自我授予此状态；frozen near-miss 反证优先于 novel 裁决。

## 4. 双视图输出

```jsonc
// evaluation.json（public）
{
  "evaluator_generation": "repository_v1_1",
  "case_id": "flowise_3_1_3_repository_v1_1",
  "ground_truth_sha256": "4e41103ecbe6d96cb0bbe3cc54c0c4a574ac21d7825bc2adc36c723ee5978da8",
  "canonical_score": {                       // 视图 A：只对 30 个冻结 roots
    "root_denominator": 30,
    "true_positives": …, "false_negatives": …,
    "recall": …, "canonical_tp": …, "equivalent_tp": …,
    "duplicates": …, "known_gt_overlap_uncredited": … // root/anchor 明细只在 private
  },
  "novel_finding_view": {                   // 视图 B：GT 外 finding 的裁决账目
    "validated_novel_tp": …, "false_positive": …,
    "inconclusive": …, "unmatched_unreviewed": …,
    "note": "adjudication-only; never part of canonical recall"
  },
  "invalid_submissions": …,
  "semantic_judge_used": false
}
```

跨 generation 不直接比较 recall：分母、锚和规则不同，旧 run 的原始 v1 score 保持原样。formal block manifest 固定单一 `evaluator_generation`，不接受 per-condition 混用。

## 5. Retrospective rescore（已独立执行）

独立授权的重评扫描到 69 个历史 Flowise-v1 run manifest，其中 68 个同时具备原始 finding、v1 public score 与 private verification；1 个不完整 run 只记录排除理由。原 adjudication ledger 的 63 个 run 全部包含在 68 个适用 run 内。

1. 每个 run 的原始 `evaluation.json`、private verification、manifest 与 findings 均只读；新结果写入 `artifacts/retrospective/flowise_repository_v1_1_evaluator_v2_20260921/runs/<historical-relative-path>/retrospective.json`，不会覆盖历史 run。
2. 每份结果并列记录原 v1 结果引用与 SHA-256、v2 canonical/novel 分类、逐 finding transition、root/锚来源、输入哈希与 circularity 标记。
3. 68 个 run 的 v1 public/private score 全部原样复现；v2 输出重复计算一致，固定 30-root 分母与 root uniqueness；输出 manifest 列出所有输入和结果的 hash。
4. agent-run-derived GT 的发现源 run 显式标记；任何 retrospective TP 都不是 independent generalization evidence。

## 6. 实现与测试

1. `evaluator/repository_v1_1_score.py`（新文件；`schema_version` 校验 `repository-v1.1-ground-truth`）。
2. 单测：canonical、批准等价锚、错误锚、R07/R08 drift、category/guard/invariant mismatch、fingerprint/root 去重、novel 分流、GT hash pin、确定性与 v1 回归。
3. 实现阶段只使用 fixtures / copied input；本次获单独授权后才只读批量重评历史 runs。
4. `runner.py` 的 evaluator 分派加 `repository_v1_1` 分支（保持 `repository_v1` 分支不动）。
5. harness tests + repository smoke tests + S/P/B/T mock fixtures（AGENTS.md 要求）；正式 v1.1 run 继续受 case live gate 阻止。

## 7. 明确不做

- 不把 novel TP 塞进旧 GT denominator 宣称 recall 提升；
- 不用 v1.1 分数改写任何 preregistered 结论；
- 不在 judge 未实现前声称"semantic judge 已启用"；
- 不把 dependency CVE 计入任何视图。
- 不把 GitHub Discussions 的未收集状态写成 v1.1 blocker；它属于本轮 collection protocol 的 scope-excluded 来源。
