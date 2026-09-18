# CoordAudit v0：N=4 非正式均衡 Calibration 与 Trace 诊断（2026-09-16）

## 结论状态

本记录固化截至 2026-09-16 的非正式 calibration 观察，供后续实验设计使用。它**不是**正式 matched block，也不构成对任何 coordination adapter 效果的因果结论。

在当前 `repository_pilot_v0`、模型与预算组合下，S 能完成 finding 提交；P、B、T 的 N=4 样本都在共享预算耗尽前进入了证据收集和候选判断，但没有留下足够的提交收尾空间。B 没有使用 generic shared store；T 的每个 Agent 都查询过一次空 task board，但没有创建或领取任务。

这应解释为当前模型—prompt—小仓库—共享预算的交互诊断，而不是“B/T 无效”、更不是已证明的架构差异。

## 固定范围与保密边界

- target：`repository_pilot_v0`；本记录不公开 source case 标签、provenance、ground-truth anchor 或 hidden evaluator 细节。
- 请求配置：`deepseek-flash`、非思考模式、temperature 0、单次输出上限 2048、每队 32 个模型调用 permits、`max_steps=32`、最长 600 秒、单次 provider retry 上限为 1。
- S/P/B/T 使用相同的 base audit prompt、Agent-visible target、finding schema 与 team-level permit budget；各 adapter 的工具边界遵循仓库的因果约束。
- 原始 run artifact 位于 `experiments/emergent_coordination/runs/calibration/`，默认不提交；本文只记录可公开的聚合观察、run ID 与方法边界，不包含模型正文、provider response ID 或私有评估输入。

2048 输出上限与冻结的正式 N=4 合约（1024）不同，且当前正式 block executor 仍不可用。因此下列数据只能作为 capacity calibration，不能写入正式结果表。

## 纳入样本

下表中的“可用”包括 `valid`；P 的首个样本为 `valid_with_infrastructure_warning`，其单次 provider failure 已由允许的 retry 恢复，故保留并单独标注。所有样本均保留 run manifest、events 与 summary。

| 条件 | 可用 run ID（缩写） | 状态 | 可观察结果 |
| --- | --- | --- | --- |
| S1 | `c227e0c1`、`712fa4fa`、`c00fd0da` | 3 × `valid` | 三次均有非空 finding 提交；分别使用 18、14、21 permits。 |
| P4 | `d73f03b7`、`f8799abc`、`adf20d48` | 1 × `valid_with_infrastructure_warning`，2 × `valid` | 三次均用尽 32 permits，未提交 finding。 |
| B4 | `8f4461b3`、`06a43582`、`a756b665` | 3 × `valid` | 三次均用尽 32 permits，未提交 finding，未调用 shared-store 工具。 |
| T4 | `eb5f3278`、`2c8ee464`、`7da0493e` | 3 × `valid` | 三次均用尽 32 permits，未提交 finding；task lifecycle 操作为零。 |

完整路径可由缩写定位如下：

- S：`s1-2048-path-normalization-diagnostic-20260915/single_n1_20260915T135003.786982+0000_c227e0c1`，以及 `n4-balanced-replication-20260915/` 下的 `single_n1_20260915T150033.215718+0000_712fa4fa`、`single_n1_20260915T150106.777763+0000_c00fd0da`。
- P：`p4-2048-front-supply-probe-20260915/parallel_n4_20260915T135744.418415+0000_d73f03b7`，以及 `n4-balanced-replication-20260915/p4-retries/` 下的 `parallel_n4_20260915T150657.006679+0000_f8799abc`、`parallel_n4_20260915T150733.264563+0000_adf20d48`。
- B：`b4-t4-2048-diagnostic-20260915/retries/` 下的 `raw_blackboard_n4_20260915T142707.916433+0000_8f4461b3`、`raw_blackboard_n4_20260915T142941.471702+0000_06a43582`，以及 `n4-balanced-replication-20260915/raw_blackboard_n4_20260915T150321.301377+0000_a756b665`。
- T：`b4-t4-2048-diagnostic-20260915/t4/structured_team_n4_20260915T144424.959279+0000_eb5f3278`，以及 `n4-balanced-replication-20260915/` 下的 `structured_team_n4_20260915T150340.711872+0000_2c8ee464`、`structured_team_n4_20260915T150354.181552+0000_7da0493e`。

均衡采样过程中另有 5 个 infrastructure-invalid attempts（P4 3 个、B4 2 个），均因 provider transport failure 而未形成完整 observation，已排除在表外；它们不应被误读成 zero-finding 结果。P4 的 warning 样本与这些无效尝试不同：其失败已在受限 retry 内恢复，run 本身完整可审计。

## Trace-level 重放观察

使用 `analysis/replay_completion_path.py` 对上表 12 个可用样本离线重放 events。该分析不调用 provider，不读取 hidden evaluator 输入，也不向 run 目录写回结果。

| 观察项 | S1（3 个 Agent） | P4 / B4 / T4（各 12 个 Agent） |
| --- | --- | --- |
| 首次明确证据 | 全部第 2 次模型调用 | 全部第 2 次模型调用 |
| 候选/类别信号 | 3/3；通常第 7–10 次调用 | P 9/12、B 9/12、T 11/12；通常约第 7 次调用 |
| 发现候选后的剩余调用 | 4–11 次 | 0–2 次，中位数 1 次 |
| finding 提交 | 3/3 非空 | 0/36 |
| 解析/上限异常 | 无 malformed submit 或 tool ceiling hit | 无 malformed submit 或 tool ceiling hit |

P/B/T 的每个 Agent 实际获得 6–9 次调用（中位数 8），并高度重复地扫描同一小仓库：跨 Agent 的文件读取重叠约为 73%–75%。第 1 次调用的典型动作是 `list_files`；T 的 12 个 Agent 还都会同时执行一次 `list_tasks`。第 2–6 次调用主要为全仓文件读取，约第 7 次才转入 shell 验证与候选判断，随后通常已经没有可用于 finding finalization 的调用。末段验证仍以 shell 为主，并未转入提交。

B 的 12 个 Agent 对 generic shared store 的 read/write 调用均为零。T 虽有 12 次 `list_tasks`，但 `create_task`、`claim_task`、`release_task`、`complete_task` 均为零：task board 在启动时为空，Agent 没有把它转化为后续的工作分配或结果同步。

## 当前解释与反证边界

1. 这不是 finding schema、解析器、tool ceiling 或明显 harness 故障：有效轨迹没有 malformed submit，且没有触发工具上限。
2. team-level 32 permits 是先到先得的共享额度；模型上下文不显示总/剩余 permits。permit 耗尽发生在下一次模型调用之前，因此没有一个可见的“请立刻提交”的最终回合，也没有保留的 finalization budget。
3. S 以连续的 14–21 次调用完成相同的前期扫描、候选形成、验证和提交；N=4 将同一共享容量拆为每 Agent 中位约 8 次调用，形成了候选出现晚于可提交窗口的 bottleneck。
4. T 的空 board 首读与 B 的零共享访问，说明当前 prompt 与初始状态没有触发 coordination primitive 的采用；这不是对 primitive 在其他任务、其他启动结构或其他容量下的普遍否定。
5. 若保持总预算 32 而直接扩展到 N=8，平均可用调用会进一步下降，预计在当前约第 7 次才出现候选的行为下更不利于诊断 adapter 差异。该句是基于本 trace 的设计推断，不是已观察到的 N=8 结果。

## 后续决策

1. 暂停继续重复当前完全相同的 S/P/B/T N=4 calibration：每个条件已有 3 个可用样本，轨迹模式稳定。
2. 下一步先进行最小的 P4 capacity sweep（48、64 team permits），保持 target、base prompt、模型和工具配置不变，以检验“提交收尾容量”解释；新 run 必须使用单独的 calibration contract 和目录，不能与本表混合。
3. 在确认容量曲线前，不扩大至 N=8，也不补 M harness。M 会额外引入分派/汇总语义，容易绕开本次观测到的冷启动与 finalization bottleneck，从而混淆解释。
4. capacity sweep 后，再设计具有独立工作前沿的 `repository_v1`，随后以重新冻结的共同合约运行新的 S/P/B/T block；M 仅在该对照稳定后另行引入。

## 可复核性

本记录的状态字段可由各 run 的 `summary.json` 与 `manifest.json` 复核；调用顺序、工具使用与 permit 消耗可由 `events.jsonl` 及上述离线 replay 复核。任何后续版本若修改 prompt、模型、工具 schema、budget、target digest 或 evaluator，必须另起记录，不得追加到本 calibration 表中。

## 后续更新（2026-09-16）

本文“最小 P4 capacity sweep”的后续已在独立记录 [`v0-pbt4-64-capacity-calibration-20260916.md`](v0-pbt4-64-capacity-calibration-20260916.md) 固化。该记录使用 64 permits，并纳入 P4、B4、T4 的各 1 条 trace；它不是本文 32-permit 均衡样本的追加，也不构成正式 matched block。
