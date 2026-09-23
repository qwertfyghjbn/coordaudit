# Flowise 3.1.3 repository-v1 N=4 calibration trace review（2026-09-20）

## 状态与结论

本记录固化 `n4m-flowise-calibration-v1-96p` 的五条最终绑定 live trace：S1、P4、B4、T4 与 M4。五个 run 的 `run_validity` 和 reconciliation 均为 `valid`，provider failure attempts 均为 0；但该 block 的 `status: complete` 只表示五个 condition 都有可对账的运行产物，不表示 coordination effect 已可识别。

主要结论是机制诊断，而不是架构优劣结论：

- S1 在第 42 次模型调用主动提交两个 finding，公开 evaluator 结果为 `1/20 TP`，另有 1 个 `unmatched_review`。
- P4、B4、T4 在 96 个 hard team permits 耗尽时仍未进入 submission；三者没有产生有效 finding。
- B4 暴露了 shared store，但实际 shared 工具调用为 0。
- T4 只有 4 次空的 `list_tasks`，没有 task 创建、claim、complete 或 evidence adoption；其跨 Agent 重复工作比例最高（42.1%）。
- M4 的 manager 用 `worker_1..3` 派单，而 runtime 接受的是 `agent_002..004`；三次派单均被拒绝，worker 没有模型调用。manager 独自探索至 v2 hard finalization，随后以 v3 reserved final synthesis 完成空提交。

因此，P4/B4/T4 的 0 TP 主要反映共享 team budget 下的探索/收尾容量与 completion 触发问题；M4 还叠加了 manager-worker identity contract mismatch。当前 trace 不支持把结果解释为 coordination adapter 的因果差异。

## 冻结合同与证据边界

冻结合同为 [`block_manifest.json`](../../experiments/emergent_coordination/runs/n4m-flowise-calibration-v1-96p/block_manifest.json)，manifest hash 为 `0443f8467df45ea206a79ff201f542a618ec1218f4a3812fc586e39ac8b12dca`。合同固定：`deepseek-flash`、thinking disabled、temperature `0.0`、4096 output ceiling、96 hard team call permits、96 max steps、1200 秒 wall-clock、一次普通 provider retry。

S1/P4/B4/T4 使用 `completion_v2 + convergent_v2 + all_agents_terminal_v1`；M4 使用 `completion_v3 + team_completion_v3`、1 个 reserved final-synthesis permit 与 60 秒 finalization deadline。本文只读取公开的 run manifest、summary、metrics、evaluation、events 和 model-visible transcript，不读取或披露 evaluator-private ground truth、provenance 或 hidden anchors。

## 最终绑定运行

| 条件 | run | permits | 终止路径 | evaluator 结果 | 公开协调观察 |
| --- | --- | ---: | --- | --- | --- |
| S1 | `formal_s1_completion-v2` | 42/96 | 第 42 步主动提交 | 1/20 TP；1 unmatched review | 无协调工具 |
| P4 | `formal_p4_completion-v2` | 96/96 | 四个 Agent 均 `budget_exhausted` | 0/20 TP | 无通信；重复工作 31.5% |
| B4 | `formal_b4_completion-v2` | 96/96 | 四个 Agent 均 `budget_exhausted` | 0/20 TP | shared create/list/mkdir/read 全为 0；重复工作 20.8% |
| T4 | `formal_t4_completion-v2` | 96/96 | 四个 Agent 均 `budget_exhausted` | 0/20 TP | 4 次空 `list_tasks`；无 task lifecycle；重复工作 42.1% |
| M4 | `manager_worker_n4_20260920T042731.219124+0000_d3e5f569` | 92/96 | manager 空提交后完成 v3 barrier | 0/20 TP；1 invalid submission | worker 0 次调用；manager 独占 92 次调用 |

逐条件的最终并列结果见 [`block_comparison.json`](../../experiments/emergent_coordination/runs/n4m-flowise-calibration-v1-96p/block_comparison.json)。对应公开 metrics 为各 run 目录下的 `metrics.json`；初次 CLI 运行中 `completion_generation=null` 的四条产物保留为诊断记录，不纳入本表绑定。

## Trace review

### S1：主动收敛并完成提交

S1 产生 41 次 exploration 调用，随后在 step 41 表达已有足够证据，step 42 成功提交。两个公开 finding 都是 access-control 类候选，涉及公开 TTS credential 使用和 OAuth2 credential callback/refresh 的租户边界；公开 evaluator 只说明其中一个命中 positive，不能由公开文件确定是哪一个。

S1 没有 output-ceiling hit、provider failure 或 invalid submission。它在 42/96 permits 时停止，说明该轨迹的瓶颈不是硬预算耗尽，而是 Agent 自主选择提交。

### P4：独立并行但全员未到提交阶段

四个 Agent 分别获得约 22–26 次调用，工具活动主要是 `list_files`、`run_shell` 和少量 `read_file`。没有任何 Agent 进入 finalization，也没有 `submit_findings`。96 个 team permits 在探索阶段全部消耗，导致每个 Agent 都在形成完整 evidence payload 之前结束。

### B4：能力可用但未被采用

B4 的 `blackboard.available=true` 仅证明 generic shared store 被暴露；实际 `shared_create`、`shared_list`、`shared_mkdir`、`shared_read` 均为 0，`content_exchange_observed=false`。因此该 trace 没有可观察的跨 Agent 内容交换。重复工作比例为 20.8%，不能解释为 blackboard 带来的收益。

### T4：task surface 暴露但没有 task lifecycle

四个 Agent 各调用一次 `list_tasks`，四次返回均为空；`create_task`、`claim_task`、`complete_task`、`release_task` 全为 0。没有 task-result observation，也没有 evidence adoption。T4 仍在独立探索中耗尽 96 permits，重复工作比例达到 42.1%，是五个条件中最高的。

### M4：派单 identity mismatch 与 finalization binding

manager 的前三次 `manager_create_task` 使用 `worker_1`、`worker_2`、`worker_3`，runtime 返回 `worker-only operation`；manager 随后 `manager_list_tasks` 得到空列表。三个 worker 均没有 provider call，最终在 `team_completion_v3` barrier 被取消。

manager 之后独自进行了 86 次 exploration call，在 step 89 进入 `convergent_v2` hard finalization。step 90 尝试用 `read_file` 补证据时被 hard finalization gate 拒绝，因为此前主要使用 `run_shell`，没有可用于 finding schema 的 evidence refs。step 91 提交空 payload，step 92 使用唯一 reserved final-synthesis call 完成 v3 synthesis。该 run 的 `team_completion_v3` 机械状态为 `completed`，但 snapshot 没有 worker report、没有 evidence refs，不能解释为成功的 manager-worker 协作。

## 解释边界与后续门槛

1. `run_validity=valid` 不等于 finding 成功，也不等于协调机制有效；它只表示 provider、sandbox、事件/转录对账和预算 ledger 没有达到 infrastructure-invalid 阈值。
2. 在 96 个 team permits 下，N=4 每个 Agent 的实际调用数约为 S1 达到提交所需调用数的一半；P4/B4/T4 的 0 TP 不能单独归因于搜索质量或 coordination capability。
3. `convergent_v2` 的 finalization start 是 per-Agent step gate（本 block 中为 step 89），而不是 team-permit-aware trigger；这使 P4/B4/T4 在共享预算耗尽前无法进入收尾窗口。
4. M4 必须先修复 prompt/tool identity 对齐，并加入派单 identity preflight；否则 manager-worker trace 不能作为有效的 centralized-control baseline。
5. 若要继续比较 coordination condition，需先公开并冻结 team-level completion/submission owner 语义，保证每个 condition 在共同 hard team budget 下都有可比较的提交机会，然后重跑完整五条件 block。当前结果应作为 calibration/机制诊断保存，不写入 coordination effect 的正式结论表。

原始 run 产物位于 `experiments/emergent_coordination/runs/n4m-flowise-calibration-v1-96p/`，默认不提交；本文是其 versioned public trace review，不替代原始 evidence。

## M4 接口修复状态（2026-09-20）

针对上述 identity contract mismatch，已修复 manager-facing 接口：manager user prompt 现在显式列出 `agent_002..agent_N`，system prompt 和 `manager_create_task`/`manager_reassign_task` schema 都要求使用 canonical worker ID，并明确禁止 `worker_1` 这类别名。`ManagerBoard` 仍保持严格的 canonical-ID 校验，不把错误别名静默归一化。

新增 prompt 回归测试，并通过 M4 实际 harness preflight、manager-worker 单元/契约测试以及 S/P/B/T mock smoke。原 calibration block 保持不可变；已冻结修复后的候选 block [`n4m-flowise-calibration-v1-96p-m4-interface-v2`](../../experiments/emergent_coordination/runs/n4m-flowise-calibration-v1-96p-m4-interface-v2/block_manifest.json)，manifest hash 为 `5b6ee39e0862ae957f1021655c4a73741208d0003ec0f7d1c0f9a8701df74070`。该 block 仅完成合同冻结，尚未重跑正式五条件 live block。
