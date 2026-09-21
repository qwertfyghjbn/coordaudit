# evaluator-v1 → evaluator-v2 设计提案（2026-09-21）

> GT gate 后的候选分母已更新为 30 roots（见 [GT freeze gates](../releases/flowise-3.1.3-repository-v1.1-gt-freeze-gates-20260921.md)）；本文的 29-root 输出示例是此前设计占位，实施前需按冻结身份更新。evaluator-v2 尚未实现。

> 状态：**提案**（设计冻结待批准；实现未开始）。前置：[GT 覆盖审计](flowise-3.1.3-repository-v1-gt-coverage-audit-20260921.md)、[repository-v1.1 升级提案](flowise-3.1.3-repository-v1.1-upgrade-proposal-20260921.md)。
>
> 本设计不改变内容冻结判断：`repository-v1.1 FREEZE_READY = no`，且唯一 blocker 仅为升级提案 §5 的 FRB-01 至 FRB-04。v2 实现本身是 freeze-ready 后的 activation 工作。

## 1. 目标与不变量

evaluator-v2（实现名 `repository_v1_1_score.py`，evaluator id `repository_v1_1`）服务 `flowise_3_1_3_repository_v1_1`。不变量：

1. **确定性优先**：formal score 完全由确定性规则产生（ADR-0005 延续）；LLM judge 不进入 formal score。
2. **双视图**：canonical benchmark score（对冻结的 29 roots，即 20 old roots + 9 proposed new roots）与 novel finding adjudication（GT 外 finding 的人工裁决记录）严格分离；novel TP 不回填 canonical 分母。
3. **evaluator-v1 保持原样**：新实现放新文件；旧 runs 的 preregistered 得分不动。

## 2. 判定分类（升级为五类）

```
canonical_tp            —— 命中冻结 root（canonical 或等价锚 + 不变量术语约束）
validated_novel_tp      —— GT 外、经独立裁决确认（只进 adjudication 视图，不进 formal recall）
false_positive          —— 命中 near-miss 或裁决反证
inconclusive            —— 证据不足/依赖运行时（含 known-unscored 面）
unmatched_unreviewed    —— 尚未裁决的 GT 外 finding（默认态）
```

匹配算法相对 v1 的三处变化：

1. **等价锚**：`_anchor_match` 的期望锚集合从 `spec["anchors"]` 扩为 `spec["anchors"] + spec.get("equivalent_anchors_v1_1", [])`；其余五段合取（category/guard_kind/affected_object/reasoning）不变——等价锚不是放宽，是同一不变量下的多实现位置。
2. **fingerprint** 增加归一化锚（file+function+excerpt hash），并把 `variant_coverage` 参与匹配的隐性漏洞显式化：报告锚集合统一处理，消除"把 canonical anchor 塞进 variant_coverage 才能匹配"的怪异路径。
3. **unmatched 输出结构化**：每条 unmatched 附带 `novel_review_required` 载荷（claim 摘要、锚、类别），供 condition-blind 裁决流水线消费；不再只是一个计数。

precision 补齐：恢复 pilot 的 closed-world lower bound / labeled-only upper bound 双界（v1 的 repository evaluator 丢失了该字段）。

## 3. Semantic judge 边界（明确回答五问）

| 问题 | 回答 |
|---|---|
| 输入是什么 | 单条 unmatched finding 的冻结字段（title/category/source/sink/guard/affected_object/trust_boundary/reasoning_summary/evidence_refs 的事件文件清单）+ 该 root 的 invariant 文本。不含其他 run、不含 GT 全集、不含裁决历史。 |
| 是否只用于 unmatched | 是。canonical 匹配永远先走确定性规则；judge 只看规则未命中的 finding。 |
| 是否影响 formal score | 否。judge 输出只写入 adjudication ledger（`validated_novel_tp`/`false_positive`/`inconclusive` 建议 + 依据），formal recall/precision 不变。 |
| 如何避免 judge 自由扩张 GT | judge 无 GT 写权限；其建议必须经人工裁决批次确认后才可能在**下一个版本**（v1.2）进入 GT，且带 agent_run_derived 标记；同一版本内 GT 冻结后不可变。 |
| 是否需要静态/动态证据才能接受 novel TP | 是。接受标准 = 静态 source→sink 链 + missing guard 的 file:line 证据（本次 40 cluster 的裁决即为该标准的执行样例）；仅当静态链不充分（如 KU02 沙箱面）时才要求 targeted local validation 或 dynamic 证据，否则落 inconclusive。 |

实现顺序上 judge 是**可后置**的：v2 首版可以只做确定性匹配 + unmatched 结构化输出，人工裁决照旧（本次审计的 batch 流程已验证可行）；judge 作为裁决辅助在未来版本加入。

## 4. 双视图输出

```jsonc
// evaluation.json（public）
{
  "canonical_score": {                       // 视图 A：只对 29 个冻结 roots
    "true_positives": …, "false_negatives": …,
    "recall": …,
    "matched_roots": […],                    // private 部分才有明细
    "precision_bounds": { "closed_world_lower": …, "labeled_only_upper": … }
  },
  "novel_adjudication": {                    // 视图 B：GT 外 finding 的裁决账目
    "validated_novel_tp": …, "false_positive": …,
    "inconclusive": …, "unmatched_unreviewed": …,
    "note": "adjudication-only; never part of canonical recall"
  },
  "duplicates": …, "invalid_submissions": …, "variant_coverage": …,
  "semantic_judge_used": false               // judge 启用时如实置 true 并注明仅辅助裁决
}
```

历史可比性：canonical 视图对 20 个 v1 roots 的子集召回可与 evaluator-v1 结果并列报告（同 anchors 同规则），29-root 召回单独报告；两者都在 public 输出中显式分列，避免跨 generation 误比。

## 5. Retrospective rescore 计划

对 63 个冻结 flowise runs 的统一重评（**不覆盖任何旧产物**）：

1. 每个 run 在其目录旁产出 `evaluation_v1_1_retrospective.json`，同保留 `evaluation.json`（v1 原件）；两份并列，manifest 不变。
2. 输出同时含：`original_preregistered_v1_score`（从旧 evaluation.json 原样拷贝）+ `retrospective_v1_1_score`（canonical 29-root 视图 + novel adjudication 视图）+ `delta_breakdown`（每 root：v1 命中/v1.1 命中/新增命中来源——anchor 修复 vs 等价锚 vs 新 root）。
3. 报告规则（写死在产物 header）：R21-R29 源自历史 agent outputs；任何 run 的 v1.1 分数是 retrospective adjudication 陈述，不是 independent generalization evidence；正式比较需冻结后、未参与 GT 构造的新 seed / 新 matched block。
4. 执行时机：v1.1 冻结后一次性批处理；脚本按 run 只读运行，不改 runtime/trace。

## 6. 实现与测试清单（批准后执行）

1. `evaluator/repository_v1_1_score.py`（新文件；`schema_version` 校验 `repository-v1.1-ground-truth`）。
2. 单测：等价锚命中（用 UC03/UC12/UC38 的历史 finding 形状做 fixture）、invariant 术语约束不放宽（等价锚 + 错 category 必须拒）、五分类输出、precision 双界、fingerprint 归一化。
3. 回归：对 63 个历史 runs 跑 retrospective，抽样 5 个 run 人工核对 delta_breakdown 与本次 40-cluster 裁决一致（预期：R04 命中数上升、R07/R08 从 0 变为可命中、R21/R22/R23 有历史命中、17 个 FP cluster 仍 unmatched→adjudication 视图为 FP）。
4. `runner.py` 的 evaluator 分派加 `repository_v1_1` 分支（保持 `repository_v1` 分支不动）。
5. harness tests + repository smoke tests + S/P/B/T/M mock smoke 全绿（AGENTS.md 要求）。

## 7. 明确不做

- 不把 novel TP 塞进旧 GT denominator 宣称 recall 提升；
- 不用 v1.1 分数改写任何 preregistered 结论；
- 不在 judge 未实现前声称"semantic judge 已启用"；
- 不把 dependency CVE 计入任何视图。
- 不把 GitHub Discussions 的未收集状态写成 v1.1 blocker；它属于本轮 collection protocol 的 scope-excluded 来源。
