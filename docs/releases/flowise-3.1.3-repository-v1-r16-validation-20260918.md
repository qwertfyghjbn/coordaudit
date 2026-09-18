# Flowise 3.1.3 repository-v1 R16 靶向验证记录（2026-09-18）

## 结论

五个 B 类 targeted validator 中的第一个已执行并通过：**R16（memory session identifier 类型不强制）**在物化依赖环境（Node v24.14.1、离线死代理、无数据库）中以 jest 29.7.0 运行，3/3 断言通过。`validation_recipes.json` 与 `verification_metadata.json` 已从 `not_run` 更新为 `passed`；`required_for_tp` 保持 `false`。`live_gate` 维持 `blocked`，剩余 R10/R13/R14/R17 待执行。

## 验证语义

fixture 直调冻结 target 源码中的 `getMemorySessionId`（`packages/server/src/utils/index.ts`）：

1. **主断言（漏洞语义）**：`overrideConfig.sessionId` 传入对象 `{ $ne: null }`（NoSQL 注入形状）→ 返回值与该对象引用全等（`toBe`），`typeof` 非 `string`——非标量标识符原样直达 memory backend 查询键。
2. **次断言**：`incomingInput.chatId` 传入 `{ $gt: '' }` → 同样原样返回，不检查类型。
3. **对照**：字符串 sessionId 正常透传，证明函数按设计意图工作、断言不是对损坏行为的误读。

## fixture 与运行

- 位置：`evaluator_private/flowise_3_1_3_repository_v1/validators/`（进入冻结私有树，受 manifest 摘要保护）：`r16_memory_session_id_type.test.ts`、`jest.config.js`、`flowise-components.shim.ts`。
- 复用 server 包冻结的 jest 解析约定（`uuid` ESM→CJS 重定向、`typeorm`→手动 mock）；`flowise-components` 经 shim 重导出**真实源码模块**（包入口 `dist/src/index` 未构建，shim 仅做模块解析，不 mock 任何行为）。
- 运行对象是物化环境中的 workspace 副本（安装前树摘要已证明与冻结 target 一致）；冻结 target 本身保持零依赖。
- 运行条件：死代理（`HTTP(S)_PROXY=http://127.0.0.1:9`）、`LOG_PATH` 指向 /tmp，环境树无写入；日志留存于 `artifacts/…_dependency_env/logs/r16-validation.log`（SHA-256 `334303b0…7538d`）。

## 记录与摘要更新

- `validation_recipes.json`：R16 `status: passed` + evidence 块（fixture、断言、结果、log 摘要）。
- `verification_metadata.json`：R16 `status: passed`、`evidence_strength: static_plus_targeted`；environment 块更新为已物化环境；其余四条 reason 更新为"环境已就绪、validator 待执行"。
- 契约测试 `test_private_phase4_recipes_cover_every_B_root_without_network` 的状态断言从"全部 not_run"改为词表 `not_run | passed | failed`（recipe 生命周期本义；覆盖与无网络约束断言不变）。
- manifest `evaluator_private_tree_sha256` → `943743c406078016a7106d2038a9765eee47c6a8c5a8e4d72b70f4687992765b`；verification result SHA-256 → `ca5f2f843d475fd3ecb168507a94f424ff9161f80d7734f59db059a64fa8bdeb`。
- 回归：verifier `passed`（`dependency_environment: verified`）；unittest 95 passed；S/P/B/T mock smoke 4/4 通过；`git diff --check` 通过。

## 边界声明

本验证是 evaluator 侧证据增强，不是 TP 判定（`required_for_tp: false` 不变）；fixture 全部位于 evaluator-private 边界内，未进入 Agent mount。`live_gate` 解除仍需全部 validator 落盘与用户明确批准。
