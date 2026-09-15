# 0005. Pilot 使用有边界的确定性 Finding 评估

## 状态

Accepted

## 决策

`submit_findings` 对完整payload执行原子式严格schema校验，无效时返回逐字段错误并允许Agent在剩余permits内重试。TP必须匹配canonical category、source与sink/guard anchors；同一`category + normalized source + normalized sink`只计一个TP并保留全部provenance。命中已标注near miss确定计为FP；schema合法但未命中已知标签的finding记为`unmatched_review`，不自动断言真伪。Primary output报告positive recall、known-near-miss FP、unmatched、invalid submissions与duplicates，并同时给closed-world precision lower bound和labeled-only precision upper bound，而不是无假设的单一precision/F1。

## 理由

当前composite ground truth只标注预设targets，不能证明仓库没有off-target漏洞；把所有unmatched自动算FP会制造虚假精确性。反过来完全忽略unmatched又会奖励无约束提交。严格evidence schema、确定性near-miss陷阱和显式precision bounds保留了可自动比较性，也暴露了标注不完备性。

## 后果

- 最终没有有效payload属于`model_format_failure`，不是infrastructure-invalid；未命中的已知positives仍形成FN。
- Benchmark snapshot oracle、Agent reproduction claim和evaluator verification分别记录，Agent自报不能产生verified finding。
- Unmatched可做condition-blind人工复核，但不能回写当前matched block；复核只进入后续versioned adjudication。

## 实现对齐（2026-09-15）

冻结 schema 拒绝缺失、额外或类型错误字段，并要求 source/sink anchor 与非空、可见的 `evidence_ref`。默认 evidence 必须来自提交者的 `file_read`；T 中已完成任务的 evidence 只有在接收者 `list_tasks` 后产生明确 `task_result_observed` 事件时才可引用。public `evaluation.json` 只给聚合结果，ground-truth assignment、anchors、per-finding verification 与 duplicate provenance 留在 `evaluator_private/verification.json`。分析器只在后续 finding 复用这类已观察 task-result evidence 时计为 evidence adoption；它不因任务列表、相邻路径或一次 shared read 推断协作。
