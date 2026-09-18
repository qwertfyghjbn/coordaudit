# Flowise repository-v1 S1 live smoke 记录（2026-09-18）

## 结论

`flowise_3_1_3_repository_v1` case 的首次真实 provider 运行（S1、smoke 预算）完整闭环，**smoke 通过**。本次运行闭合了 `run-level-live-gate-open-20260918.md` 所列"剩余步骤"的第 1 步：repository-v1 任务在真实模型、真实预算账本、真实 OS 沙箱下从 model call 到 hidden evaluator 的全链路验证。本记录不构成任何协调效果结论，也不是一次可评分的正式运行。

## 运行标识与配置

- run_id：`single_n1_20260918T124405.776944+0000_c792f2cc`（产物在 `experiments/emergent_coordination/runs/` 下，按惯例不提交）。
- case / 条件：`flowise_3_1_3_repository_v1`，`single`、1 agent。
- 模型：`deepseek-flash`（`LLM_BASE_URL` OpenAI 兼容端点），thinking disabled，provider 侧 resolved model 与 system_fingerprint 均已记入 transcript 的 `model_metadata`。
- 预算（case `smoke_budgets`）：`hard_team_call_permits=8`、`max_provider_retries=0`、`wall_clock_timeout=120s`、`token_stop_threshold=null`；单次输出上限 1024。
- 环境：bwrap 0.6.1 OS 沙箱（live 运行强制开启）；运行前 `compatibility_smoke` 通过（tool-call 往返正常）。
- 代码状态：git `e98b08d` + 工作区未提交的 block-contract schema 演进（`harness/contract.py`、`harness/block_runner.py`、`freeze_block.py`、`manifests/n4_flowise_v1.json`、`tests/test_block_contract.py`）。该批改动只影响 freeze/合同层，不进入 single 模式运行路径；随工作项 0 一并提交。

## 证据登记

| 检查项 | 结果 |
| --- | --- |
| run_validity | `valid`，provider failure attempts = 0 |
| reconciliation | `valid`：62 events / 29 transcript 条目 / 24 artifacts / 8 permits，对账一致 |
| 预算账本 | 8/8 permits 全部 `succeeded`（attempt_number 均为 1，无 retry 消耗） |
| 真实用量 | input 80,978（其中 cached 67,456，命中约 83%）、output 858 tokens；墙钟约 13.4 s（12:44:05.8 → 12:44:19.2） |
| model-visible transcript | 8 对 `model_request`/`model_response` + 13 条 `tool_result`，hash 寻址、含 parent_refs lineage |
| 隔离完整性 | run 内 `runtime/target` 树 digest = `c612819a…4a1638`，与冻结 case manifest 完全一致；`evaluator_private` 位于 run 级可信面，不在 target 内 |
| hidden evaluator | 离线执行完成：positive_recall 0/20、unmatched 0、known near-miss 0、invalid submissions 0 |

## 判读注记

- `stop_reason=model_format_failure` 是 `harness/agent_loop.py:151` 的终态重标（"结束时无已提交 findings payload"），不是格式故障：第 8 次 model call 是正常的 `read_file` tool call（`executeCustomNodeFunction.ts`），permit 耗尽后自然收尾。8-permit 冒烟预算下未走到提交属预期截断。
- 0 findings / 0 TP 不影响 smoke 判定：smoke 的目的是闭环验证，不是得分。
- 高缓存命中率对正式 block 成本估算有利：64-permit 条件的输入侧大头预计走 cached 计价（单次冒烟样本，仅供量级参考）。

## 与正式实验之间剩余的步骤

1. 冻结 block 1：`python3 -m experiments.emergent_coordination.freeze_block --config experiments/emergent_coordination/manifests/n4_flowise_v1.json --block-id <id>`（S1/P4/B4/T4、64 permits）。
2. 逐条件执行 live matched block；任一 infrastructure-invalid condition 触发整块重跑（预注册规则）。
3. hidden evaluator 评分 + versioned release record；完整 trace 即 M4 的预注册入场凭证。
4. （并行、免费）`analysis/analyze_run.py` 的 manager_worker 指标段（M 计划 §6 首优先项）。

本 smoke 不改变 `required_for_tp` 语义；U01/U02 维持 unresolved/unscored。
