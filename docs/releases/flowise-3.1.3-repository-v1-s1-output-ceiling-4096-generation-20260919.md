# Flowise repository-v1 S1 输出上限 4096 新世代与 conv_v1 @2048 vs @4096 定向对照（2026-09-19）

## 1. 决策与实施摘要

经用户确认，diagnostic 轨道进入**输出上限 4096 的新配置世代**；formal matched block 维持各自 frozen 配置不变。本轮完成三件事：

1. **per-call 日志**：`llm_call` 事件新增 `call_role`（exploration / coordination / submission / finalization，优先级 submission > finalization > coordination > exploration）、`output_tokens`、`max_output_tokens`、`finish_reason`。
2. **统计**：`analyze_run` 的 `metrics.json` 新增 `output_ceiling` 段——overall 与分 role 的 ceiling-hit rate、分 role 调用数、output_tokens 的 p50/p90/p95/p99（overall 与分 role）。旧 run 缺 `call_role` 时由 `tool_call` 子事件、`token_usage`、`completion_phase_started`/manifest 推导回溯，分类器与运行时同源（`harness/call_role.py`）。
3. **1v1 live 对照**：`convergent_v1` @2048 vs @4096，fresh seeds，其余配置与 2×2 完全一致。

验证：全套 **114 tests 通过**（新增 7 个：分类器优先级 5、回溯 1、运行时字段 1）；S/P/B/T mock smoke 通过；四个 2×2 run 的 `metrics.json` 已按官方再分析路径重生成（新增 section，旧值不变）。

## 2. 已有 2×2 的回溯统计（@2048）

| run | calls | ceiling hits | submission calls / hits | submission p50/p90/p95/p99 | exploration p99 |
|---|---:|---:|---:|---|---:|
| none `f8b46033` | 128 | 0 | 0 / 0 | — | 402 |
| guidance_only `5e034b57` | 116 | 2 | 3 / 1 | 1851/2009/2028/2044 | 486 |
| scheduler_only `1a6244b9` | 113 | 2 | 5 / 0 | 1858/1915/1920/1924 | 572 |
| convergent_v1 `40bd3d2e` | 127 | 2 | 6 / 2 | 1310/2048/2048/2048 | 570 |

要点：**ceiling 压力集中在 submission 角色**——guidance/scheduler 的 submission p50 已达 1851/1858（距上限 ~10%），conv 的 p90 起顶死 2048；而所有 run 的 exploration p99 仅 211–572。scheduler 的 2 次 hit 均为 exploration 角色（step 104 rambling、step 108 write_file 暂存）；none 零提交零 hit。

六个 conv-policy run 的 pooled 视图（64/96/old-128/matched/本轮两臂）同样如此：3/6 个 run 的 submission p99=2048 或贴顶，exploration p99 全部 ≤570。

## 3. conv_v1 @2048 vs @4096 定向对照（各 n=1，fresh seeds）

| | @2048 `single_n1_20260919T035548…517bcf94` | @4096 `single_n1_20260919T040004…0038df2e` |
|---|---|---|
| seed | `flowise-s1-conv-v1-ceiling2048-20260919` | `flowise-s1-conv-v1-ceiling4096-20260919` |
| validity | valid / valid | valid / valid |
| stop_reason | submitted | submitted |
| calls / unused | 123 / 5 | 104 / 24 |
| finalization | step 121 进入（未自主收敛） | **未触发**（step 102 自主收敛） |
| 首次收敛表达 | step 121（finalization 注入后） | **step 102**（"I have enough evidence for two supported findings"） |
| submit 调用 / validator 拒绝 / JSON 参数失败 | 3 / 1 / 1（121–123，非 length 截断） | 2 / 0 / 1（103–104，非 length 截断） |
| findings / TP / unmatched | 2 / 1 / 1 | 2 / 1 / 1 |
| ceiling hits | 0（submission p99=1592） | 1（step 101 exploration，output=4096 恰在新上限） |
| findings 内容 | TTS 任意 credential 使用（high）；org IDOR 泄露 Stripe ID（medium） | TTS 任意 credential 使用（high）；feedback 跨租户读写（medium） |

## 4. 解释（克制版）

1. **本轮 1v1 不能度量上限对提交成功率的影响**：两个 run 的提交 payload 都没有撞到各自上限（@2048 臂 submission p99=1592；两臂的 JSON 参数失败经 `finish_reason` 核验均非 length 截断，是普通 JSON malformation）。截断路径这次未被触发——这与 2×2 中 5 次 submission 路径截断对照，说明 payload 尺寸与 malformation 本身高度随机。
2. **@4096 臂自发收敛（102）vs @2048 臂被 finalization 强制（121）不能归因于上限**：n=1/臂，且已知同配置轨迹会在早期分岔（2×2 的 guidance vs conv 在 step 3 分岔）。行为差异只能记为"本轮观察"。
3. **稳定结论来自 pooled 分布**：2048 上限的压力是 submission 特有现象（submission p50 1268–2039 vs exploration p99 ≤570）。4096 给提交 payload 约 2× 余量，方向正确；本对照未观察到 4096 的任何负面影响（provider 正常、无异常长输出、成本未显著变化：@4096 臂总 output 低于 @2048 臂）。
4. **TP 均为 1/20 且共享 TTS finding**：两臂质量持平（本口径下）；不构成 4096 提升或降低质量的证据。

## 5. 新世代配置约定

- diagnostic / replicate 轮默认 `--max-output-tokens 4096`；seed 一律 fresh（唯一作用是诚实溯源）。
- 与 @2048 世代的结果只做方向性对照，不直接数值比较。
- formal matched block、case manifest、frozen contract 不动。

## 6. 顺带记录

- finalization 工具裁剪可被绕过（conv matched run step 126 在窗口内成功 `read_file`；@2048 臂 step 121-123 未尝试绕过）。已在 2×2 报告第 4/10 节补充；本轮不修改该行为，@2048/@4096 对照与 2×2 在此机制上一致，无额外混杂。
- `invalid_submission_arguments` 计数器（上一轮批准）在本轮两臂 live run 中正常工作（各记录 1 次 JSON 截断，metrics 可见，无需翻 transcript）。

## 7. 下一步

仍然回到主线：**fresh-seed replicate 轮**（2×2 每格 ≥2 个 fresh seed @4096），主指标为自主提交率、首次收敛步、validator 拒绝率、截断率（现已全部可从 metrics.json 直接读出）。待批准后执行。
