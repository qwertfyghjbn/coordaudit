# T4 board-bootstrap adoption diagnostic（192 permits）

## 研究问题

本 block 只比较 prompt intervention：在 completion lifecycle 已经充足、共享预算固定为 192 的条件下，使用显式 minimal task-board workflow 是否会改变 T4 的 task-board adoption、coordination quality 和 task effectiveness。

它不是自然采用实验，也不是架构优劣 benchmark。

## 冻结 identity

- block：`t4-board-bootstrap-adoption-v1-192p`
- contract：`t4_flowise_board_bootstrap_adoption_v1`
- manifest hash：`e048f3e29d31fb33b8ebc3f7f7a3ebf4c0a540adaa6e76f630b961620651dd78`
- condition：T4，`structured_team`，4 agents
- model：`deepseek-flash`，thinking disabled，temperature 0，output ceiling 4096
- seed：`n4-flowise-completion-calibration-v2-96p`
- shared permits：192
- finalization：`team_remaining_permits_v1`，reserve 32
- completion：`convergent_v2` + `all_agents_terminal_v1`
- `max_steps=96`，provider retry=1，wall-clock=1200s
- prompt profile：`repository_v1_t4_board_bootstrap`
- tool schema hash 与 T4-base@192 相同；target/evaluator digests 相同；只有 system prompt hash 改变

## Run validity and lifecycle guardrails

Run `formal_t4-board-bootstrap-adoption-v1`：

- `run_validity=valid`
- `reconciliation=valid`
- provider failures=0
- attempted calls=168，remaining permits=24
- team finalization 在 call index 161、remaining=32 时触发一次
- 4/4 agents submitted，team `clean_complete`

因此 prompt intervention 没有破坏 completion lifecycle。

## Matched comparison

| 指标 | T4-base@192 | T4-board-bootstrap@192 |
|---|---:|---:|
| attempted calls | 170 | 168 |
| finalization trigger | call 161 / remaining 32 | call 161 / remaining 32 |
| submitted agents | 4/4 | 4/4 |
| team completion | clean | clean |
| `list_tasks` | 4 | 4 |
| `create_task` | 0 | 4 |
| `claim_task` | 0 | 4 |
| `complete_task` | 0 | 0 |
| `release_task` | 0 | 0 |
| file duplicate ratio | 0.469 | 0.542 |
| merged findings | 4 | 7 |
| evaluator TP | 0 | 1 |

Finding/TP 仅作 secondary observation，不能据此声称 prompt 提高了审计能力。

## Adoption

adoption 明确发生了：每个 agent 都执行了 `list_tasks`，各自创建并 claim 了一个任务。

但没有任何 agent 完成任务；最终四个 task artifact 都停留在 `claimed`，`result=null`、`evidence_refs=[]`。因此 adoption 是“create/claim adoption”，不是完整的 create/claim/complete workflow adoption。

## Coordination quality

质量较差。四个任务都集中在 server-side HTTP/API routes/controllers，内容高度重叠：

- `agent_001`：server-side attacker-reachable routes
- `agent_002`：server routes/controllers
- `agent_003`：server-side HTTP routes/controllers
- `agent_004`：server routes/controllers

没有形成互补 ownership；重复率反而从 0.469 上升到 0.542。任务板被用于声明工作，但没有被用于有效的分工、交接或去重。

## Task effectiveness

没有观察到 task-board mediated evidence reuse：因为没有 `complete_task`，没有任务结果或 evidence refs 被写回 board。bootstrap run 的 finding payload 自身包含 evidence refs，且少量 evidence ref 在不同提交间重复，但这些并非通过 task completion 产生，不能归因于 task board。

## 结论

这个 prompt 成功解决了第一层 adoption barrier：模型开始创建和认领任务；但没有解决第二层 coordination barrier：任务选择仍然高度重叠，且模型在提交 finding 前没有完成任务。

因此本轮支持以下分解：

1. 原先的零 task adoption 部分来自 prompt 缺少明确 bootstrap 指令；
2. 仅要求 create/claim 不能形成 ownership 或互补分工；
3. completion/submission objective 仍然压过了 `complete_task`，导致 task effectiveness 为零；
4. 不能把 1 TP、7 findings 或重复率变化解释成架构或审计能力提升。

后续若继续研究，应单独设计“任务完成/交接”prompt intervention，并预注册 ownership/互补性判据；不要在本 block 上追加调参或补跑。
