# T-Pilot 2 implementation audit 与零网络定值（2026-09-28）

本记录对应 [设计 §15](../T_PILOT_2_DESIGN.md) 的数值前置、§15-4 provider failure 审计、§15-5 墙钟执行点审计。审计对象是工作树中的 `team_synthesis_v1`；正式运行使用本目录的冻结合同与 prompt packet。

## 数值定值

| 参数 | 冻结值 | 零网络依据 |
| --- | ---: | --- |
| `synthesis_reserve_permits` | **3** | §12 的 R={2,3,4} × read cap={1,2} × V1–V5 矩阵：V4 `read → invalid → submit` 消耗 3 次独立 provider call；R=2 降级，R=3 成功。R=3 是满足最低能力合同的最小值。 |
| `synthesis_read_file_cap` | **1** | 最低能力合同含 1 次必要读取；cap=1 支持 V3/V4。第二次读取被 `synthesis_read_cap` 硬闸拒绝并记录；V5 是能力边界，不是本 pilot 的最低合同。 |
| `synthesis_window_seconds` | **60** | 设计 §6.1 的保守公式：4 × 5 s + 2 × 1 s + 10 s = 32 s，向上取 60 s。mock V1–V5 的本地执行远低于 60 s；总运行上限仍为 1200 s，search 截止为 1140 s。 |

静态 permit 分割是 189 次 search/finalization + 3 次 team synthesis，仍在团队 192 次总额内。共享 finalization 触发阈值仍为 remaining≤32。read cap 是独立工具闸，拒绝调用不消耗额外 provider permit，但触发它的 model call 已消费 permit。

## §15-4 provider failure 审计

| 项 | 实现与实测结论 |
| --- | --- |
| (a) 一次失败后是否立即降级 | **否**。失败调用结算为 `timeout` 或 `provider_error`；若 reserve 与窗口还有余量，phase 留在 active。 |
| (b) outer loop 能否继续 | **能**。下一轮获取新的 `team_synthesis` permit，`retry_of=null`，不发生 SDK 或 harness 隐式重试。失败一次、随后成功的注入测试得到 2 次 provider call 和完成的 C_final。 |
| (c) 失败是否消费 reserve | **是**。失败调用在 provider dispatch 前已获 permit，ledger 的 `call_kind=team_synthesis` 和 `synthesis_calls_used` 均增加 1，绝不退款。最后一个 permit 若失败，降级原因为 `provider_failure`。 |
| (d) ADR-0002 如何累计 | search 与 finalizer 共用一个团队 permit ledger。两次失败注入得到 `infrastructure_invalid`；单次 synthesis 失败得到 warning，若尚有余量可恢复。 |
| (e) schema-invalid 与 provider-failure 是否分路径 | **是**。schema-invalid 的 provider call 结算为 `succeeded`，另发 `team_findings_submission_rejected` 并在下一次 model request 中给字段错误；provider 失败结算为 `timeout/provider_error`，无 submission 事件。两者都逐次消耗 permit。 |

## §15-5 墙钟执行点审计

`AgentRunner._complete_with_permit` 在每个 search provider request（含 harness retry）申请 permit 前调用 `BudgetTracker.check_search_wall_clock()`；启用 synthesis 时上限为运行总墙钟减 W，即 1140 s。`TeamSynthesisRunner.run` 在每次 synthesis request 前、每次 provider response 后调用 `check_synthesis_window()`，分别核对自 phase 打开起 60 s 与总运行 1200 s。边界注入测试使两个检查均拒绝越界；超时响应不能被接纳为 C_final。provider 请求本身仍使用 provider 的单次 timeout，因此边界后的结果会被拒绝，已经在途的请求不会被强制中断。

## 输入、intake 与产物核对

- search 初始 model-visible `messages` 和 `tools` 与 T-Pilot 1 冻结 packet 对四个 agent 逐字相同；new finalizer 工具只在 `team_finalizer` 会话出现。
- `team_completion` 先于 `raw_candidate_set_frozen`，后者先于首次 synthesis request。`raw_candidate_set.json` 同时保存控制侧全记录与匿名 model snapshot；快照只含候选字段、最小 `evidence_ref → path` 映射、匿名 contributor 及终态。
- finalizer 只可读取 raw 候选列出的 source/sink/guard/evidence 路径；读次数上限 1。`submit_team_findings` 的 intake 要求每条 final finding 非空 `derived_from`、每 raw 恰好一个 decision、merge 全成员双向一致、retain 字段保持原样、decision 与 final finding 的 evidence ref 均可见。
- 正常、降级、空 raw 路径保留 C_raw 与 C_final 产物。运行根目录的 `evaluation_raw.json`、`evaluation_final.json`、`synthesis_delta.json` 分别代表 C_raw、C_final、机械 Δ；`evaluation.json` 与 raw pass 字节相同，run manifest 明示 alias。

## 零网络闸门

`test_t_pilot_2_synthesis.py`：8 passed，36 subtests passed（数值矩阵、intake、failure、deadline、完整 T4 mock、合同与污染扫描）。`test_team_completion_harness_preflight.py`：6 passed，覆盖 S/P/B/T 与 M4 的真实 harness mock；repository pilot smoke：6 passed。完整套件最终结果记录在 `final_prereg_v1.json`。

这些检查验证机器合同与可观测性；true merge、false merge、valid drop 和 correction 的语义正确性仍按设计 §9 的盲评顺序在 live 产物上裁决，机械 intake 不替代代码级真值判断。
