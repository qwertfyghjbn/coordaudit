# Flowise 3.1.3 T4 completion-budget diagnostic（192 permits）

## 研究问题与冻结边界

本次只回答：**在 completion 已经确认充足的前提下，扩大 exploration budget 是否会改变 T4 对 task-board coordination infrastructure 的自然采用行为？**

这是 T4-only diagnostic，不是架构 benchmark。相对已完成的 `n4-flowise-completion-calibration-v2-96p` T4 trace，唯一实验变量是共享 `hard_team_call_permits` 从 96 改为 192。`team_finalization_reserve=32`、`max_steps=96`、模型、seed、base prompt、T4 tool surface、completion/team-completion policy、retry 与 wall-clock 均保持冻结；S1/P4/B4/M4 不在本 block 中。

## Frozen identity

- block：`t4-flowise-completion-budget-diagnostic-v1-192p`
- contract：`t4_flowise_completion_budget_diagnostic_v1`
- manifest hash：`2ccf1f268b6b26f81ecacf4cbe073f1a29c2ff615de4485774f00b6569a1b945`
- condition：T4（structured_team，4 agents）
- model：`deepseek-flash`，thinking disabled，temperature 0，output ceiling 4096
- seed identity：`n4-flowise-completion-calibration-v2-96p`（与 96p T4 paired）
- permits：192 shared attempted-model-call permits
- finalization：`team_remaining_permits_v1`，reserve 32
- completion：`convergent_v2` + `all_agents_terminal_v1`
- `max_steps=96`，provider retry=1，wall-clock=1200s
- target/evaluator digests 与 96p calibration 相同；运行时由 frozen block manifest 绑定

## Run validity

Run `formal_t4_completion-budget-diagnostic-v1` 完成且可解释：`run_validity=valid`、`reconciliation=valid`、provider failure attempts=0、in-flight=0。

| 指标 | T4@96（paired reference） | T4@192 |
|---|---:|---:|
| attempted model calls | 75 | 170 |
| permits remaining | 21 | 22 |
| team finalization | 触发一次，call index 65，remaining 32 | 触发一次，call index 161，remaining 32 |
| finalization active agents | 4 | 4 |
| submitted agents | 4/4 | 4/4 |
| team completion | clean_complete | clean_complete |
| terminal reasons | 4×submitted | 4×submitted |
| merged findings | 4 | 4 |
| evaluator TP | 0 | 0 |

## Task-board adoption

两条 trace 的 task-board 行为完全相同：

- `list_tasks`：4 次，均返回空 board（每个 agent 一次）；
- `create_task`、`claim_task`、`complete_task`、`release_task`：均为 0；
- task evidence / cross-agent task adoption：0。

因此，在这个 matched single-seed diagnostic 中，把共享 exploration budget 从 96 扩至 192 没有观察到 T4 对 task-board infrastructure 自然采用的改变。增加预算主要增加了开放式探索调用（170 vs 75），并没有诱发 task creation、claim 或 completion。

这不是“task board 机制无效”的因果结论：本次只观察一个冻结 seed/model trace，且 finding/TP 不是研究问题的 primary outcome。它只说明，在 completion lifecycle 已正常、且 T4 有更多探索预算的条件下，当前 prompt/tool affordance 下仍未自然采用 task-board protocol。

## 结论

T4@192 成功复用了已校准的 completion lifecycle：finalization 在 team remaining=32 deterministic 触发，四个 active agents 均获得并完成 submission opportunity；没有回到旧的 `finalization_start=null` / budget-exhausted pathology。

在严格冻结的其余语义下，192 permits 相比 96 permits **没有改变 task-board 的自然采用行为**。若下一步研究如何提高 task-board adoption，应另立 preregistered adoption experiment（例如 prompt/bootstrap 变量）；不应把本次 192p 结果解释为 T4 架构优劣或 coordination effectiveness。
