# Flowise repository-v1 S1 96-permit diagnostic（2026-09-19）

## 运行结论

本次独立 S1 diagnostic 有效完成，并相较此前 64-permit completion calibration 产生了可观测的信息增益：公开 evaluator 结果从 `0/20 TP` 变为 `1/20 TP`。因此 96 permits 对当前单 Agent 的证据覆盖和 finding 质量有一定收益，但仍不是正式 matched block，也不能单独支持 coordination effect 结论。

运行：

- run：`single_n1_20260919T004958.035995+0000_2c9edb89`
- case：`flowise_3_1_3_repository_v1`
- condition：S1 / `single` / N=1
- model/provider：`deepseek-flash` / `openai_compatible`
- thinking：disabled
- output ceiling：2048
- hard team permits：96
- `max_steps`：96
- completion policy：`convergent_v1`
- run validity：`valid`
- reconciliation：`valid`
- provider failure attempts：0

实际结果：

| 指标 | 结果 |
|---|---:|
| provider calls / permits | 89 / 96 |
| 未使用 permits | 7 |
| completion phase | 第 89 次调用进入并成功提交 |
| submit attempts | 3 |
| 成功提交 payload | 1（3 findings） |
| invalid submission | 1 |
| output ceiling hit | 0 |
| positive recall | 1 TP / 20 positives（0.05） |
| unmatched review | 2 |

完成路径 replay 显示：第 86 步的一次提交因第二条 finding 没有读取 source/sink/guard 文件而被拒绝；第 88 步出现一次 malformed `submit_findings` 参数；第 89 步重试成功。该轨迹证明 finalization reserve 能把 Agent 推入提交阶段，但不能消除 evidence completeness 和 JSON 生成错误。

## Findings 观察

成功 payload 包含三个新的 endpoint-level 候选：TTS credential 使用、public chatbot config 信息泄露、get-upload-file 私有附件访问。它们均需要人工复核；公开结果只说明其中一条匹配了 evaluator positive，不能在不读取 evaluator private 的情况下确定是哪一条。

其中至少有一条 finding 的 source/sink/guard evidence 在首次提交时不完整，说明“提交成功”与“证据闭环完成”仍是两个独立指标。`evidence_lineage_replay.json` 记录了成功提交中的 `validator_match`、`source_sink_evidence_mismatch` 和 `unknown_evidence_ref` 观察。

## 与 64-permit 运行对照

| 运行 | calls | 成功提交 findings | TP | unmatched | invalid submit |
|---|---:|---:|---:|---:|---:|
| 64-permit completion calibration | 57 | 2 | 0 | 2 | 0 |
| 96-permit diagnostic | 89 | 3 | 1 | 2 | 1 |

该对照不是 matched causal comparison：permit 数量不同，且两次使用不同 seed；它只用于容量诊断。

## 是否继续 128 permits

96-run 已满足继续扩容的预注册条件（产生新的 endpoint-level evidence，并出现 1 个公开 TP），因此可以进行一次 128-permit S1 diagnostic，但应限定为“证据闭环稳定性与边际 recall”实验，而不是默认扩大正式预算。

128-run 的建议门槛：

1. 保持相同 target、provider/model、2048 ceiling、base prompt、finding schema 和 `convergent_v1`；只增加 team permits 与 `max_steps=128`。
2. 仍保留最后 8 次调用作为 finalization reserve。
3. 预先记录停止标准：若新增 permits 只带来重复候选、evidence rejection 或 malformed submit，而没有新的 endpoint-level evidence/TP，则停止后续扩容。
4. 128 仍使用独立 seed/run ID，不能回写或替换已冻结的 64-permit formal block。

原始运行和 replay 产物保留在 `experiments/emergent_coordination/runs/`，默认不提交。

