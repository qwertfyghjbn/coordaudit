# Flowise 3.1.3 repository-v1 R14/R17 靶向验证记录（2026-09-18）

## 结论

五个 B 类 targeted validator 中的第三、四个已执行并通过：**R14（chat model baseURL egress policy）**与 **R17（document loader egress policy）**在物化依赖环境（Node v24.14.1、离线死代理）中运行，分别 2/2 与 1/1 断言通过；四个已执行 validator 合跑 10/10 通过。`required_for_tp` 保持 `false`。`live_gate` 维持 `blocked`；仅剩 R13 待执行。

## R14 验证语义（ChatLocalAI init）

fixture 以 `nodeData.inputs.basePath = http://169.254.169.254/latest/meta-data/` 驱动真实 init：

1. **主断言（漏洞语义）**：返回的 ChatOpenAI 实例 `clientConfig.baseURL` **逐字等于**攻击者 URL——用户可配置 basePath 无任何校验直达带凭据客户端的请求基址。实现备注：该版 `@langchain/openai` 把 `configuration` 规整进 `clientConfig`（探针确认字段形状后修正断言路径）；客户端惰性，构造期零网络。
2. **反向断言**：对共享 deny-list 策略（`components/src/httpSecurity` 的 `checkDenyList`，与真实调用方同一模块实例）挂 spy，init 全程**零调用**——"策略存在但此路径不经过"成为可记录证据。
3. **对照**：无 basePath 时不注入 baseURL。

## R17 验证语义（Playwright loader）

fixture jest.mock `PlaywrightWebBaseLoader`（完整 mock 浏览器传输，无浏览器二进制、零网络），驱动真实 init（`outputs.output='document'`）：

1. **主断言**：导航构造器**恰好一次**收到逐字的攻击者 URL `http://169.254.169.254/latest/meta-data/`；返回 Document 的 `metadata.source` 等于攻击者 URL——数据确实流经导航路径。
2. **反向断言**：导航 config 只含 `launchOptions`，序列化后无任何 deny/policy/redirect 字段；deny-list 策略 spy **零调用**。

实现备注：初版断言误判了 init 的默认返回（默认 output 返回拼接字符串，非 Document 数组），改为显式 `output: 'document'`。components barrel import（`'../../../src'`）经 `components-src.shim.ts` 重导出真实 `src/utils` 模块解析（非 mock）；components node_modules 加入 `modulePaths` 保证 mock 说明符与冻结源码解析到同一模块实例。

## 记录与摘要更新

- fixture：`validators/r14_chat_model_baseurl_egress_policy.test.ts`、`validators/r17_document_loader_egress_policy.test.ts`、`validators/components-src.shim.ts`（均进入冻结私有树）。
- `validation_recipes.json` / `verification_metadata.json`：R14、R17 → `passed`、`static_plus_targeted`；log 摘要 R14 `e463e1b1…1f64`、R17 `5d184d04…fbb5`；全套合跑 log `ee687c5d…9f03`（10/10）。
- manifest `evaluator_private_tree_sha256` → `3fa5aba9361ad6c5e0dd9746c93fd8873bcf2bede5fec847aa660a3650e3d03c`；verification result SHA-256 → `d603c67fb192ee65915ccab193283716277c0f3312b248e1330bf09ae0ae5ba9`。
- 回归：verifier `passed`（`dependency_environment: verified`）；unittest 95 passed；S/P/B/T mock smoke 4/4；`git diff --check` 通过。

## 进度

| Root | 状态 |
| --- | --- |
| R16 memory session id type | passed（2026-09-18） |
| R10 MCP stdio executable policy | passed（2026-09-18） |
| R14 chat model baseURL egress | passed（2026-09-18） |
| R17 document loader egress | passed（2026-09-18） |
| R13 sqlite chain write capability | 待执行（唯一剩余） |

本验证是 evaluator 侧证据增强，不是 TP 判定；fixture 全部位于 evaluator-private 边界内。`live_gate` 解除仍需 R13 落盘与用户明确批准。
