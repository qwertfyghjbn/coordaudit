# CoordAudit：P4/B4/T4 64-permit Capacity Calibration 与 Trace 对照（2026-09-16）

## 结论状态

本记录固化 `repository_pilot_v0` 上一次 P4、B4、T4 的 64-permit 非正式 calibration。它不是正式 matched block：未包含 S1，且它使用 2048 output ceiling，而正式 N=4 合约为 32 permits 与 1024 output ceiling。T4 另有一次已恢复 provider failure，状态为 `valid_with_infrastructure_warning`；因此本记录只用于容量与机制诊断，不作 coordination adapter 的因果比较。

64 permits 足以让 P4、B4、T4 进入提交阶段，但没有观察到 B 的 shared store 或 T 的 task lifecycle 形成跨 Agent 分工。三组都高度重复地审计同一组文件，并在 evaluator 去重后得到同样的 3 个已验证 finding。当前小 target 已不适合用更多同构重复来区分 coordination primitive 的效应。

## 共同配置与纳入 run

- target：`repository_pilot_v0`；不公开 hidden evaluator、ground truth、source case 或 provenance。
- 模型：`deepseek-flash`，thinking disabled，temperature 0，单次 output ceiling 2048。
- 运行边界：4 Agent、64 个共享 hard team call permits、`max_steps=64`、600 秒、最多 1 次 harness retry、`token_stop_threshold=null`、OS sandbox 必需。
- 相同 base audit prompt、Agent-visible target、finding schema；唯一预期 condition 差异为 P/B/T coordination adapter 及其必要 prompt/tool schema。

| 条件 | run ID | 有效性 | attempted / succeeded calls | 提交 Agent | 原始 finding / evaluator 去重后 | evaluator 已验证 |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| P4 | `parallel_n4_20260916T011228.651309+0000_7ac3bfa6` | `valid` | 64 / 64 | 1 / 4 | 3 / 3 | 3 |
| B4 | `raw_blackboard_n4_20260916T011316.622124+0000_737ae5cf` | `valid` | 64 / 64 | 2 / 4 | 6 / 3 | 3 |
| T4 | `structured_team_n4_20260916T011411.853173+0000_ab3bc254` | `valid_with_infrastructure_warning` | 60 / 59 | 4 / 4 | 12 / 3 | 3 |

原始 artifact 位于 `experiments/emergent_coordination/runs/calibration/pbt4-64-calibration-20260916/`，默认不提交。上述数字可由各 run 的 `summary.json`、`metrics.json`、events 与 model-visible transcript 复核。

## Trace 对照

离线使用 `analysis/replay_completion_path.py` 和 evidence-lineage replay；不调用 provider、不读取 private evaluator、也不把 replay 写回 run directory。

| 观察项 | P4 | B4 | T4 |
| --- | ---: | ---: | ---: |
| 首次明确文件证据 | 全部 Agent 第 2 步 | 全部 Agent 第 2 步 | 全部 Agent 第 2 步 |
| 首次类别假设 | 全部第 7 步 | 3 个第 7 步、1 个第 11 步 | 3 个第 7 步、1 个第 9 步 |
| 首次提交的全队 permit 序号 | 57 | 51 | 42 |
| 文件读取跨 Agent 重复率 | 75.0% | 73.3% | 74.7% |
| `run_shell` 实际调用 | 56 | 56 | 36 |
| schema/ceiling 异常 | 0 malformed、0 ceiling hit | 0 malformed、0 ceiling hit | 0 malformed、0 ceiling hit |

P4 中 3 个未提交 Agent 已有候选信号和文件证据，却继续进行局部验证，随后因全队 permits 耗尽停止。B4 也有 2 个 Agent 在同一状态下耗尽。这个模式支持“32 permits 时的瓶颈主要在候选后的收尾容量”，但不表示每个 Agent 在固定步数后必然提交：P4/B4 内部仍受并发顺序和验证循环影响。

T4 的 4 个 Agent 都提交得更早，且本地 shell 验证少于 P4/B4；这只是一个待复现实验行为差异。它不能归因为结构化协作：4 个 Agent 在第 1 步同时 `list_tasks`，另有 2 次在提交前重读；6 次结果全为空。没有 `create_task`、`claim_task`、`release_task`、`complete_task`、task-result observation 或 evidence adoption。所有 finding 的 evidence lineage 都来自提交 Agent 自己读到的文件。

B4 的 shared-store 工具暴露正常，但实际 `shared_list`、`shared_read`、`shared_mkdir`、`shared_create` 均为 0。因此 B4 的额外提交只是独立 Agent 重复提交同一组 finding，并非通过 blackboard 交换信息。

T4 的唯一 provider error 出现在 `agent_002` 第 6 步，随后 retry 成功并消耗了一个额外 permit。其他 3 个 Agent 无此错误仍先后提交，且 T4 最终剩余 4 个未使用 permits；这个恢复性故障不能解释 T4 全员提交，但该 run 必须保留 `valid_with_infrastructure_warning` 标记并与 `valid` 样本分开解释。

## 指标语义修正

本次 trace 暴露出旧 `metrics.json` 的命名歧义：旧 `structured_team.available=false` 实际表示“没有任务生命周期事件”，不是“task 工具未暴露”。同样，B 的 `blackboard.available` 不能用来推断 store 是否可用。

分析器现升级为 metrics schema v2：

- `available`：对应 coordination tool capability 是否向 Agent 暴露；B4/T4 分别为 true。
- `model_tool_invocations`：模型实际选择的工具调用数，从携带模型参数的 dispatch event 计数；避免将同一次调用的工具侧结果事件重复计数。
- `tool_activity_observed`：是否有实际 coordination-tool 调用。
- `lifecycle_activity_observed`：仅 T 中是否有 create/claim/conflict/release/complete/result-observation；`list_tasks` 不算生命周期。
- `task_list_reads`：T 中 `list_tasks` 的实际调用数以及空/非空结果数。本次为 6 / 6 / 0（调用 / 空 / 非空）。

这些字段仍是观察指标：工具调用、空 board 或时间相邻不证明协作、采纳、领导或意图；跨 Agent evidence adoption 仍要求 finding 显式复用已观察 completed task 的同一 `evidence_ref`。

## 后续决策

1. 暂停在 `repository_pilot_v0` 上机械追加 B4/T4 64-permit 重复；它只会继续测量同一 3-finding 饱和任务上的独立收尾差异。
2. 在扩展 target 前，保留这条“容量足以提交、primitive 未被采用、重复工作仍高”的诊断基线。
3. 下一 target 应提供至少 4 条能独立取得可评分证据的 work fronts；重新冻结 target、prompt/tool schema、budget 与 evaluator 后，再运行新的 P4/B4/T4 diagnostic gate。
4. 不以预填 task、预设 leader 或其他协议化启动状态修改主 T4；那会形成一个需要单独标识和比较的新 coordination condition。

## 与既有 calibration 的关系

本记录是 [`v0-n4-balanced-calibration-20260916.md`](v0-n4-balanced-calibration-20260916.md) 中 32-permit 均衡诊断之后的容量延伸，而非其样本追加。两个记录的 output ceiling、hard permit 数量和纳入条件不同，必须分别解释。
