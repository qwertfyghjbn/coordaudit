# Flowise 3.1.3 repository-v1 S1 completion-policy 消融（2026-09-19）

## A. 实验结果摘要

本次运行是独立的 128-permit S1 diagnostic，唯一自变量为
`completion_policy=none`。运行没有注入 `convergent_v1` 的收敛/提交提示，也没有进入
finalization-only tool surface；`submit_findings` 成功后终态语义保持不变。

- run：`single_n1_20260919T013923.221314+0000_14e9da39`
- case：`flowise_3_1_3_repository_v1`；condition：S1 / `single` / N=1
- model/provider：`deepseek-flash` / `openai_compatible`；thinking：disabled；temperature：0
- seed：`flowise-s1-128perm-completion-none-20260919`（独立 run seed）
- permits：128；`max_steps`：128；output ceiling：2048
- run validity / reconciliation：`valid` / `valid`
- completion policy：`none`（manifest 中记录为 `null`）
- git commit：`5a01249110d9c61be516e70b55ed13e99e087288`

观察结果：实际 model calls 为 `128/128`，最后一次调用为 step 128，未使用 permits 为 0。
Agent 没有成功提交 finding，终态为 `model_format_failure`（达到 permit-sized safety ceiling
后没有形成可提交 payload）；这不是 harness 改写的成功提交终态。提交 attempts 为 0，malformed
submission 为 0，evidence rejection 为 0，provider failure 为 0，output-ceiling hit 为 0。
finding 数量为 0，因此没有 finding evidence refs。公开 evaluator aggregate 为 `0/20 TP`、
`20 FN`、`0 unmatched review`、`0 invalid submissions`；本文不读取或披露 hidden evaluator 的
逐 finding 映射。

Transcript 中没有出现 Agent 首次表达“证据足够”“开始准备提交”或等价完成语义的 model
response。可见的候选/审查语义只包括 step 6 的 “path traversal candidate”、step 7 的
“SSRF candidate”、step 10 的 “command execution candidate”、step 35--36 的 IDOR 排查和
step 126 的 path-traversal candidate；直到 step 128 仍在读取 routes/controllers，未调用
`submit_findings`。因此本 run 的停止原因可归类为预算耗尽，而非 Agent 主动提交、context/output
ceiling 或 provider/tool failure。

## B. completion-policy 对照表

| 运行 | policy | permits | 实际 calls | 最后 step | 成功提交 | finding 数 | submission attempts / invalid | evidence rejection | output ceiling | provider failures | 公开 TP / unmatched |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|
| 96 baseline | `convergent_v1` | 96 | 89 | 89 | 是 | 3 | 2 / 1 | 1 | 0 | 0 | 1 / 2 |
| 128 baseline | `convergent_v1` | 128 | 90 | 90 | 是 | 4 | 2 / 1 | 1 | 1 | 0 | 2 / 2 |
| 本次 ablation | `none` | 128 | 128 | 128 | 否 | 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 |
| matched-seed replicate | `none` | 128 | 128 | 128 | 否 | 0 | 0 / 0 | 0 | 0 | 0 | 0 / 0 |

三次运行的 target/case、provider/model pin、base prompt profile、finding schema、tool surface、
2048 output ceiling 和 team-level budget 语义保持一致；baseline 与本次 ablation 使用独立
run seed，不能把跨 seed 的 finding/TP 差异解释为纯 policy 效应。

## C. 结论

1. **`none` 是否显著延后提交？** 是。在本次独立 run 中，提交从 baseline 的 step 89/90
   延后到未发生；Agent 用完 128 permits 仍未提交。由于 ablation seed 不同，幅度不能单独视为
   policy 的无偏效应，但方向和机制证据明确：移除 completion policy 后没有触发主动收敛提交。
2. **`none` 是否增加 finding 数量？** 否；本 run 为 0 条，而两个 convergent baseline
   分别为 3 和 4 条。这里的 0 条与预算耗尽/未形成 payload 绑定，不能推断 `none` 的长期发现
   能力必然更低。
3. **`none` 是否降低 malformed/evidence rejection？** 观测上是 0/0，但原因是没有提交尝试，
   不是 payload 质量已被证明更好；不能将其解释为降低了提交错误率。
4. **早停主要来自 convergent_v1，还是 Agent 自身的“证据足够”判断？** 在已有两个
   `convergent_v1` run 中，Agent 在 step 89/90 提交；两个 `none` run（包括复用 128 baseline
   seed 的 matched-seed replicate）都在 step 128 耗尽预算，且没有表达“证据足够/准备提交”。
   这使“96/128 的早停主要由 convergent_v1 的收敛/提交引导及 finalization 机制促成”的判断
   更有力；当前 prompt 下没有观察到稳定的 Agent 自发收敛提交。仍需更多 seed 才能估计方差，
   但 matched-seed 结果已排除了本次首个 ablation 的 seed 差异作为唯一解释。

本消融不支持声称 Flowise case 在训练集中，也不支持把 3--4 条解释为 S 架构的内在最大发现
数量。

## D. 下一步建议

- 先做同 seed（若 provider 允许确定性复现）和至少一个不同 seed 的 `none` 128-permit replicate，
  记录首次“证据足够/准备提交”语义、提交尝试和停止 step。
- 若重复仍在 80--100 permits 内主动提交，说明早停不只由 completion policy 造成；若重复继续
  耗尽预算且 finding 增加，再评估 prompt 中的证据闭环与提交格式支持。
- 将 malformed/evidence rejection 与“是否尝试提交”分开统计；不能用本次 0 rejection 代替
  payload 质量结论。
- 在完成 matched seed/不同 seed 的消融前，不提高正式 frozen block 的发现上限解释，也不修改
  正式 frozen block。

matched-seed replicate：

- run：`single_n1_20260919T015554.026898+0000_f8b46033`
- seed：`flowise-s1-128perm-diagnostic-20260919`（与 128-permit `convergent_v1` baseline 相同）
- 结果：`128/128` calls、step 128 结束、0 finding、0 submission attempts、0 malformed、0
  evidence rejection、0 output-ceiling hit、0 provider failure、公开 `0/20 TP`。
- transcript 中没有“证据足够/准备提交”语义；step 110--119 仍在进行 workspace/IDOR 相关探索。

## E. 可复核 manifest / hash 记录

本次 run 的 `run_manifest.json`、`summary.json`、`metrics.json`、events 和 transcript 均保留在：

`experiments/emergent_coordination/runs/single_n1_20260919T013923.221314+0000_14e9da39/`

matched-seed replicate 的同类产物保留在：

`experiments/emergent_coordination/runs/single_n1_20260919T015554.026898+0000_f8b46033/`

case manifest 中记录的 public reproducibility digests：

| 项目 | SHA-256 |
|---|---|
| target tree | `c612819a833fc8ab3c58fe5085fb80fc0a6c4cb1d86cbb8ed41b0b431e4a1638` |
| base prompt | `a63820831f9ab8864eb318444cfc8ad0b126043161833f145f8840e68c9581ec` |
| finding schema | `97ad0335dde33ffd45a2056d7b8e15b79375fbea5a40c2e82d7f774ba7999c48` |
| tool surface | `fd50774151b621069f3a82aeaf76a3355227318efafcec085c5ca58d72c2e1f0` |

本次实际 harness 文件 hash 也可复核：`prompts.py`
`0f9e72ced5f6265e72b24466c98858b0d2b15e3799ddbf0c6ee3f8d2deb5f14d`，`tools/specs.py`
`14a456dfcae8248fe5fb3d3a07eeefd53056c3c0e708f3e4a8573c69f6c90972`。运行产物默认不提交；本
文档不包含 evaluator_private 内容。
