# CoordAudit v0 非正式 Calibration 补遗（2026-09-15）

本补遗记录 `coord-audit-v0` 冻结之后为验证 harness 与 task-supply 风险所做的非正式 calibration。它不修改 `coord-audit-v0`、不创建 matched block、不会产生 S1/P4/B4/T4 的正式比较结果，也不覆盖正式 N=4 合同中的 1024 output ceiling。

所有原始运行产物保留在被忽略的 `experiments/emergent_coordination/runs/calibration/`；本文只给出非敏感的聚合观测、run ID 与解释边界。不会发布 hidden evaluator anchors、source case 标签、provenance、provider response ID 或模型正文。

## 修复与可观测性基线

| 项目 | 处理 | 验证 |
| --- | --- | --- |
| 相对 run directory | `WorkspaceLayout` 在使用前规范化为绝对路径 | 相对目录下 Agent 可列出并读取 target |
| malformed tool arguments | malformed JSON 或非 object 参数显式记录为 rejected tool call，并返回结构化错误；不再降级为 `{}` 或空提交 | 回归测试覆盖截断 `submit_findings` 与非 object 参数 |
| provider 结束原因 | 每个成功 provider response 持久化 `finish_reason` 至 event 与 model-visible transcript | 独立 compatibility probe 返回 `tool_calls` 与 `stop` |
| transcript 脱敏 | 宿主路径脱敏不再吞掉嵌套 JSON 的转义边界 | 嵌套 tool-result JSON 回归测试 |
| finding 路径比较 | source、sink、`file_read` evidence 与 evaluator target-file 比较统一为 target-relative；可选 `target/`、`./` 与反斜杠只在 trusted control plane 规范化 | intake/evaluator 正反向回归与 lineage replay |
| 2048 diagnostic 覆盖 | CLI 提供显式 `--max-output-tokens`；默认仍为正式合同的 1024 | client 回归测试与 runtime smoke |

相关决策已写入 [`ADR 0004`](../adr/0004-model-visible-transcript.md) 与 [`ADR 0005`](../adr/0005-bounded-deterministic-evaluation.md)。路径规范化只统一同一 target 文件的表示，不改变 Agent-visible target、prompt、finding 语义、ground truth 内容或 coordination affordance。

## Calibration 结果摘要

| 运行 | 合同摘要 | 聚合观测 | 可作出的结论 |
| --- | --- | --- | --- |
| `single_n1_20260915T124129.109774+0000_14611cf8` | S1、1024、32 permits | valid；23 permits；6 次 `finish_reason=length` 的截断 submit 被拒绝；最终空提交 | 1024 下存在 output-ceiling pressure；不是能力或 ceiling 结论 |
| `single_n1_20260915T125825.997618+0000_1a1f2aef` | S1、2048、32 permits | valid；23 permits；无 length；4 次 finding evidence rejection；1 条 unmatched | 2048 消除了已观察的截断路径；后续定位到历史路径命名空间误拒绝 |
| `single_n1_20260915T135003.786982+0000_c227e0c1` | S1、2048、修复后的 target-relative 比较、32 permits | valid；18 permits；3 条有效 finding；3/3 evaluator-verified positives；0 invalid submission | 路径规范化缺陷已被修复；最后一个 verified positive 在 permit 18，**不满足** permit 8 以内的 strong S1 ceiling 判据 |
| `parallel_n4_20260915T135744.418415+0000_d73f03b7` | P4、2048、修复后的 target-relative 比较、4 Agent 共享 32 permits、无共享状态 | valid；32 permits 耗尽；0 submission/0 verified positive；跨 Agent 文件读取重复率约 74.7%；一次 provider error 经一次 retry 后继续 | 在该无共享 P4 calibration 中，并行探索未在预算内进入提交阶段；不能据此推断 P4、front supply 或 coordination adapter 的正式效果 |

P4 的 32 permits 是团队共享的原子 ledger，而非每 Agent 固定 8 个配额；该次实际获得 9、8、7、8 个 permits。provider error 与 retry 均按合同消耗 permit。

## 解释边界与下一步

- 这组运行不是正式 matched block。每轮均有独立 calibration ID、replicate ID 与冻结记录，不能把单次 S1/P4 差异称为因果比较。
- 正式 v0 合同仍是 1024 output ceiling；2048 仅用于定位 output truncation 与 finding-intake 路径问题的 diagnostic，不能回写或覆盖正式合同。
- 当前没有 strong ceiling signal：S1 虽已验证 3/3 positives，但完成于 permit 18，而非预注册的 permit 8 以内；P4 又未形成可评分提交。
- 在启动 B4、T4 前，必须为每个 condition 单独冻结同一修复后 runtime、2048 diagnostic 配置、4 Agent、32 个团队共享 permits 与相同 target/model/prompt/tool schema；B4 只能提供 generic persistent store，T4 才可提供 typed task、atomic claim 和受记录的结果/消息。
- 若后续需要正式结论，应先实现 matched-block executor，并重新冻结一个统一的正式合同；不得将本文 calibration 结果直接升格。

## 验证状态

路径规范化修复后，70 项 harness tests、6 项 repository smoke tests 以及 S/P/B/T mock smoke 均通过。本文所列 live calibration 的原始 event、permit ledger、model-visible transcript、reconciliation 与 evaluator-private verification 均保留于各自的 ignored run artifact 中。
