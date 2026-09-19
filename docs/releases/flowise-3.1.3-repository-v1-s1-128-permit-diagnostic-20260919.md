# Flowise repository-v1 S1 128-permit diagnostic（2026-09-19）

## 运行结论

本次独立 128-permit S1 diagnostic 有效完成，公开 evaluator 结果为 `2/20 TP`。但 Agent 在第 90 次调用自行提交，实际只消耗 `90/128` permits，未进入预留的最后 8-call finalization phase；因此这不是一次“128 次完整探索容量”的观测，而是一次在更高上限下提前收敛的 S1 trace。

运行：

- run：`single_n1_20260919T005712.105877+0000_9f6f60b1`
- case：`flowise_3_1_3_repository_v1`
- condition：S1 / `single` / N=1
- model/provider：`deepseek-flash` / `openai_compatible`
- thinking：disabled
- output ceiling：2048
- hard team permits：128
- `max_steps`：128
- completion policy：`convergent_v1`
- run validity：`valid`
- reconciliation：`valid`
- provider failure attempts：0

实际结果：

| 指标 | 结果 |
|---|---:|
| provider calls / permits | 90 / 128 |
| 未使用 permits | 38 |
| completion phase | 未触发；Agent 在第 90 步自行提交 |
| submit attempts | 3 |
| 成功提交 payload | 1（4 findings） |
| invalid submission | 1 |
| output ceiling hit | 1 |
| positive recall | 2 TP / 20 positives（0.10） |
| unmatched review | 2 |

提交路径中，第 87 步出现 malformed `submit_findings`；第 88 步提交因第四条 finding 缺少已读取的 source/sink/guard evidence 被拒绝；第 90 步重试成功。该结果说明高 permit 上限并不自动解决 JSON 完整性或 evidence lineage 问题。

## 与前序 diagnostic 对照

| 运行 | calls | 成功提交 findings | TP | unmatched | invalid submit | 未使用 permits |
|---|---:|---:|---:|---:|---:|---:|
| 64-permit completion calibration | 57 | 2 | 0 | 2 | 0 | 7 |
| 96-permit diagnostic | 89 | 3 | 1 | 2 | 1 | 7 |
| 128-permit diagnostic | 90 | 4 | 2 | 2 | 1 | 38 |

这些运行使用不同 seed 和 permit 上限，只能作为容量诊断，不能当作 matched causal comparison。公开 evaluator 不披露 2 条 TP 对应哪两个 finding；本记录不读取 evaluator private、ground truth 或 provenance。

## 边际收益判断

128-run 相比 96-run 多产生 1 个公开 TP 和 1 条提交 finding，但实际只比 96-run 多消耗 1 个 model call，并留下 38 个 permits。这个结果不能证明 128 permits 本身带来了确定的 recall 提升；更可能说明 Agent 的自发提交时机、seed 方差和候选证据质量已经成为主导因素。

当前不建议继续直接增加到 192 或更高 permits。后续优先级应是：

1. 对 128-run 的 4 条 finding 做 condition-blind 人工复核，并检查 route-level evidence 是否完整；
2. 若需要量化 seed 方差，优先复跑一个同配置 128-permit replicate，而不是继续提高单次上限；
3. 只有在多个 128 replicate 都显示提交前仍有明确的新证据产生，且 permit 接近耗尽时，才重新讨论更高预算。

原始运行与 `completion_path_replay.json`、`evidence_lineage_replay.json` 保留在 `experiments/emergent_coordination/runs/`，默认不提交。

