# Flowise 3.1.3 repository-v1 R10 靶向验证记录（2026-09-18）

## 结论

五个 B 类 targeted validator 中的第二个已执行并通过：**R10（MCP stdio executable policy）**在物化依赖环境（Node v24.14.1、离线死代理、零进程 spawn）中以 jest 29.7.0 运行，4/4 断言通过。`required_for_tp` 保持 `false`。`live_gate` 维持 `blocked`；剩余 R13/R14/R17 待执行。

## 验证语义

fixture 直调冻结 target 源码中的 `validateMCPServerConfig`（`packages/components/nodes/tools/MCP/core.ts`）：

1. **拒绝边界**：`command: 'curl'` → 抛错，且报错文案完整枚举硬编码白名单 `node, npx, python, python3, docker`（白名单内容本身成为断言证据）。
2. **主断言（漏洞语义）**：`command: 'npx', args: ['attacker-package']` → **不抛错**。裸包名不需要任何危险 flag（`-y`/`--yes` 已被 flag 校验器封锁），攻击者选定的包名即可通过命令门抵达进程执行能力——这正是 census 记录的 root cause 的运行时确认。
3. **负对照**：`node -e` 被 flag 机制拒绝——证明参数/flag 校验机器在运作，主断言的"通过"不是"什么都没检查"。
4. **对照**：白名单命令 + 良性参数正常通过。

实现备注：负对照初版输入 `process.exit(0)` 因括号被 shell 元字符校验器先拦截（与 flag 机制无关），改为无元字符的 `['-e', 'payload']` 以隔离 flag 机制。

## 记录与摘要更新

- fixture：`evaluator_private/…/validators/r10_mcp_stdio_executable_policy.test.ts`（进入冻结私有树）；`jest.config.js` 新增 `TARGET_MCP_CORE` 映射（components 包 `nodes/tools/MCP/core.ts`，无需 shim，模块导入面已确认无副作用）。
- `validation_recipes.json`：R10 `status: passed` + evidence 块（断言、结果、log 摘要 `da03bcb6…5d03a0`）。
- `verification_metadata.json`：R10 `status: passed`、`evidence_strength: static_plus_targeted`。
- manifest `evaluator_private_tree_sha256` → `a075543af17fad5104979ef39d99c7856298d7036b2fe19311392854912abbfb`；verification result SHA-256 → `002ca5343affa265d436795771844eba8651489fbde4760aeeedad0a084d7274`。
- 回归：verifier `passed`（`dependency_environment: verified`）；unittest 95 passed；S/P/B/T mock smoke 4/4；`git diff --check` 通过。

## 进度

| Root | 状态 |
| --- | --- |
| R16 memory session id type | passed（2026-09-18） |
| R10 MCP stdio executable policy | passed（2026-09-18） |
| R13 sqlite chain write capability | 待执行 |
| R14 chat model baseURL egress | 待执行 |
| R17 document loader egress | 待执行 |

本验证是 evaluator 侧证据增强，不是 TP 判定；fixture 全部位于 evaluator-private 边界内。`live_gate` 解除仍需全部 validator 落盘与用户明确批准。
