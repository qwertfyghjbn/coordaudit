# Flowise 3.1.3 repository-v1 M4 修订记录（2026-09-18）

## 结论

对已最终冻结的 `flowise_3_1_3_repository_v1` 做最小修订：把 **M4（manager_worker，1 manager + 3 workers）声明为第五个 matched condition**。修订理由是预注册的 M4/M8/M16 manager-worker 计划（2026-09-17 冻结，早于本 case 最终冻结 2026-09-18），定位为 centralized-control baseline——不构成 treatment-aware 选择。除 `tool_surface_sha256` 与三处声明字段外，**一切摘要与预算不变**；M4 的运行仍受其预注册进入条件约束（见"边界"）。

## 变更清单

| 文件 | 变更 |
| --- | --- |
| `manifests/flowise_3_1_3_repository_v1.json` | `supported_modes` += `manager_worker`；`matched_conditions` += `{"id":"M4","mode":"manager_worker","agent_count":4}`；`leakage_notes` 的 "No M condition" 表述更新为 M4 定义声明；`tool_surface_sha256` 重算 |
| `scripts/verify_flowise_3_1_3_repository_v1.py` | `_MODES` += `manager_worker`；工具面 canonical 形状改为五 mode，其中 manager_worker 为双 role 结构 `{"manager": …, "worker": …}`（`tools_for_mode` 对该 mode 强制 role；任一 role 面变动即影响摘要） |
| `tests/test_repository_v1_contract.py` | 新增 `test_m4_amendment_matches_preregistered_manager_worker_plan`：M4 与 P4/B4/T4 同 N；四个旧 mode 的工具面摘要 pin 到修订前值（证明 M 加入未改变其他条件工具面）；target/prompt/schema 摘要与 64 permits 不变断言 |
| `tests/test_repository_v1_case_selection.py` | 工具面复算公式同步为五 mode 双 role 形状（与 manifest 摘要变更耦合的必要更新） |

## 摘要对照

| 摘要 | 修订前 | 修订后 |
| --- | --- | --- |
| `tool_surface_sha256` | `3522153c128829670809a62908d356d1a7ce270e9ecb642da8833d35959a013e` | `fd50774151b621069f3a82aeaf76a3355227318efafcec085c5ca58d72c2e1f0` |
| `target_tree_sha256` | `c612819a…e4a1638` | 不变 |
| `base_prompt_sha256` | `a6382083…8c9581ec` | 不变 |
| `finding_schema_sha256` | `97ad0335…7999c48` | 不变 |
| `hard_team_call_permits` | 64 | 不变（M4 共享同一池，manager 是 N 个 slot 之一） |

分 mode 工具面 pin 值（进契约测试）：single/parallel `a23e7c51…8ee26b`、raw_blackboard `e52063f3…00380e`、structured_team `81707c84…c29d9`（四个旧面与修订前一致）；manager_worker/manager `bb01685c…8fd0ec1`（9 tools）、manager_worker/worker `e0e28fd3…706711`（8 tools）。

## 验证

- verifier：`passed`（`live_gate: open`、`dependency_environment: verified`、计数不变）。
- unittest：完整工作区 105 passed；另以 stash 验证仅含本修订范围的提交态套件自洽通过。
- 五条件 mock smoke：S1/P4/B4/T4 + **manager_worker/4**（flowise case 首次）全部通过。
- 五条件块冻结端到端：`n4m_flowise_v1` 族（contract.py 预注册）在修订后的 case 上冻结成功——S1/P4/B4/T4/M4、64 permits、`live_gate: open`；M4 条件 hash 为双 role 结构（manager/worker 各含 system_prompt/user_prompt/tool_schema），两个 role 的 tool_schema 摘要与上述 pin 值一致。修订前该冻结被 `_check_case_contract_consistency` 拒绝（有专门的预修订回归测试）。

## 边界

1. **M4 的运行仍受预注册进入条件约束**：S/P/B/T block 产出完整 trace 之前，M4 不进入任何已执行 block；本修订只解除"case 未声明 M4"这一层。
2. `analyze_run` 的 manager_worker 指标段仍未实现（M 计划 §6 第一优先项），在 M4 进入正式 block 前完成。
3. 工作区同时存在五条件合同层（`contract.py` 的 `n4m_flowise_v1` 族、`block_runner` 双 role 条件 hash 与 case 一致性校验、`test_block_contract` 五条件测试、四条件 block-1 合同 `manifests/n4_flowise_v1.json`），与本修订互锁验证通过；该层属 block 合同工作（原计划 #4），不在本次提交范围内。
