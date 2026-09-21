# Flowise patch-diff mining — 候选漏洞清单

- 生成日期（as_of）: 2026-09-21
- snapshot: `flowise@3.1.3` = `09f099dbfda179e439ec677d06ad737375899eef`（2026-06-25）
- origin/main HEAD: `9291856d1ea4a4ceea9f8fef8ce14f4f6c81e8eb`（2026-08-13）
- 扫描范围：snapshot 之后 origin/main 全部 28 个 commit（其中 20 个触及 server/components 代码），全部经 stat + diff 逐条分诊；已知 fix 列表（15 个前缀）全部出现于该区间并已排除，未发现列表外遗漏。
- 方法：blobless 全历史 clone（`/tmp/flowise-git`），按 commit message 关键词初筛 + diff 内容二次筛选；snapshot 适用性逐条对照本地工作副本 `experiments/emergent_coordination/repositories/flowise_3_1_3_repository_v1/`。
- 明细数据：`patch_mining_ledger.json`（同目录）。

## 新增候选（不在 21 GHSA / 已知 fix 列表）—— 共 8 个

| # | commit | 日期 | 标题 | 子系统 | snapshot 状态 |
|---|--------|------|------|--------|---------------|
| 1 | `4b805e05` | 2026-08-07 | fix: flowise-707 (#6712) | enterprise/sso | vulnerable |
| 2 | `754f3d47` | 2026-07-31 | fix: flowise-708 (#6679) | enterprise/sso | vulnerable |
| 3 | `0b74fc07` | 2026-08-07 | fix: flowise-603 (#6708) | openai-assistants / TTS | vulnerable |
| 4 | `abe4a860` | 2026-08-10 | Fix Flowise 746 Chat Message Route (#6719) | routes/chat-messages | vulnerable |
| 5 | `1939b5f3` | 2026-08-07 | add: permissions for bullmq endpoint (#6713) | index.ts /admin/queues | vulnerable |
| 6 | `269a4937` | 2026-08-07 | fix: upsert history permissions (#6680) | routes/upsert-history | vulnerable |
| 7 | `e816d26a` | 2026-07-24 | Fix Flowise-552 Add Allow List Execution Path (#6658) | components/MCP | vulnerable |
| 8 | `9d3059fd` | 2026-07-22 | Fix Flowise 849 SSO And Role (#6634) | enterprise login-method / role | vulnerable |

### 逐条说明

1. **`4b805e05` — SSO 身份绑定（email 碰撞接管）【新增】**
   修复前 SSO 登录仅凭 IdP 断言的 email 匹配账号（`readUserByEmail`）。修复给 User 增加 `ssoProvider`/`ssoSubjectId` 列并在不匹配时 403（`SSO_IDENTITY_MISMATCH`），首次登录绑定。攻击者控制一个能断言受害者 email 的 IdP 身份（第二个 IdP、自建 OIDC、租户管理员加恶意 IdP、或 IdP 不校验 email 所有权）即可登录受害者账号。snapshot 中无该列无该检查（已对照 user.entity.ts / SSOBase.ts）。

2. **`754f3d47` — SSO 自动激活 INVITED 用户【新增】**
   修复前：SSO 登录命中 `status=INVITED` 的用户时直接 `accountService.register(...)` 激活账号。邀请的完成本应证明对受邀邮箱的控制（tempToken 邮件链接），SSO 断言不等价。攻击者无需控制受邀邮箱即可激活受邀账号并继承其 workspace/角色。snapshot SSOBase.ts L81-92 仍是自动激活版本。

3. **`0b74fc07` — 跨 workspace 凭据使用（openai-assistants / TTS voices）【新增】**
   `req.query.credential` 攻击者可控；service 里 `Credential.findOneBy({ id: credentialId })` 无 workspaceId 谓词 → 解密并使用任意 workspace 的 OpenAI/ElevenLabs 密钥（列表/上传/voices 回显给攻击者）。修复补 workspaceId 谓词 + `assertCredentialInWorkspace`，并给 upload/voices 路由补 `checkAnyPermission`（置于 multer 之前）。snapshot 中三处 findOneBy 均只有 id；路由无权限中间件。

4. **`abe4a860` — chat-messages 路由缺 RBAC + abort 无 workspace 校验【新增】**
   `/api/v1/chat-messages` 的 GET/DELETE、`/internal-chat-messages` GET、`PUT .../abort/:chatflowid/:chatid` 均无 `checkAnyPermission`；且 abort 链路（controller→service→`abortControllerPool.abort(`${chatflowid}_${chatId}`)`）无任何 workspace/所有权断言 → 低权限角色可读/删 chat 历史（workspace 内 RBAC 绕过），任意认证用户可跨 workspace 中止他人进行中的预测流（DoS）。snapshot 路由与服务均已确认无防护。

5. **`1939b5f3` — BullMQ 队列面板缺权限【新增】**
   `/admin/queues` 之前仅 `rateLimiter + verifyTokenForBullMQDashboard`，无 RBAC；修复插入 `checkPermission('admin:queues')`（新 admin 权限，默认非管理员无）。非管理员可查看 job 载荷（可含敏感输入）并操作/清空队列。snapshot index.ts L350 确认无权限中间件。

6. **`269a4937` — upsert-history 路由缺 RBAC【新增】**
   GET/PATCH `/api/v1/upsert-history` 无权限中间件（修复加 `chatflows:view,documentStores:view` / `chatflows:update,documentStores:upsert-config`）。已有 workspace 作用域，故为 workspace 内 RBAC 绕过（读取/删除 upsert 审计记录）。snapshot 路由确认无中间件。

7. **`e816d26a` — custom MCP stdio 参数校验由 blocklist 改 default-deny allowlist【新增（f5d16835 的后续硬化，独立 commit）】**
   旧实现为 regex 黑名单（绝对路径前缀、`../`、`~/`、危险扩展名、`--file` 族 flag、null byte、长度上限），原则上可绕过（不匹配任何模式的相对脚本路径、无扩展名脚本等）。新实现要求 `args[0]` 精确命中 `CUSTOM_MCP_ALLOWED_ABSOLUTE_SCRIPT_PATHS`，未配置即禁用执行。sink 为 stdio 子进程 spawn。snapshot 中仍是黑名单版本且无任何 allowlist 环境变量。

8. **`9d3059fd` — SSO testConfig 缺平台/跨组织校验 + role 组织变更拒绝【新增】**
   `POST /api/v1/login-methods/test`（仅 `sso:manage`）修复前无 `assertEnterprisePlatform()`（OSS/CLOUD 上可调用企业端点）且无 `assertQueryOrganizationMatchesActiveOrg(user, req.body.organizationId)`（A 组织管理员可对 B 组织 id 做 SSO 配置测试，携带攻击者影响的出站请求端点）。role.service 增加显式 organizationId 不匹配 404；注意 snapshot 已有 `newRole.organizationId = oldRole.organizationId` 强制回写，该部分在 snapshot 中实际已被中和（属 defense-in-depth）。testConfig 部分确认 snapshot 无守卫。

## 已排除的非候选（snapshot 之后）

- `fe285d0b`（flowise-627）：package.json/pnpm-lock/Dockerfile，纯依赖升级。
- `ba4c6509`：SECURITY.md sunset notice，纯文档。
- `a65f81bb` / `9291856d`：版本号 / README。
- `f20d0941`（flowise-766）：**仅注释与 .env.example**——从注释掉的 `TOOL_FUNCTION_EXTERNAL_DEP` 示例中移除 puppeteer/playwright 并加警告（launch() 把 executablePath/args 直通 child_process.spawn = 沙箱逃逸）。无功能变更，故不入候选，但作为 KU02 家族的佐证记录。
- `441c4e98`：GitHub workflow（已知列表内）。

## snapshot 之前 6 个月的 security fix 家族（仅 ledger，不入 GT）

代表性条目（完整 36 条见 JSON）：跨 workspace chatflow 泄露 `f7d86912`、凭据泄露 `97b96f60`、Vector Store/generate-tool-desc/API Keys 补权限（`b93ccf31`/`03c853cb`/`e135b294`）、SSRF deny-list 三部曲（`efffd12f`/`8c2b2ffe`/`219b0400`）、路径遍历三部曲（`0140ba4a`/`b44affdf`/`aff06479`）、MCP 配置安全（`7176dcb4`/`b4665df8`）、Pyodide/vm2 沙箱（`a24acac5`/`0c8236ac`/`0e528779`）、TTS CORS 通配符（`d2acf4ce`）、email 变更确认流（`6d668fbb`）、受邀 workspace 访问（`b7a2005f`）、公开 chatflow flowData 消毒（`8799c7a3`）、参数覆盖绕过（`c8282c97`）。这些在 snapshot 中预期为 fixed/not_present。

## 已知未修复项在 origin/main 的现状

- **CUSTOM_MCP_SECURITY_CHECK 旁路**：仍在。`CustomMCP.ts:176`、`SupergatewayMCP.ts:109` 保留 `!== 'false'` 门控；但被门控的校验已升级为 default-deny allowlist（`CUSTOM_MCP_ALLOWED_COMMANDS` + `CUSTOM_MCP_ALLOWED_ABSOLUTE_SCRIPT_PATHS`，cwd 一律拒绝，env 变量白名单）。触发旁路需 operator 显式设 `false`，届时全部校验（含 allowlist）一并跳过。
- **NodeVM 依赖逃逸（KU02）**：部分收敛。`availableDependencies`（60 项）已不含 puppeteer/playwright，并加了警告注释（f20d0941）；但 `TOOL_FUNCTION_EXTERNAL_DEP` / `ALLOW_BUILTIN_DEP` 的 operator 自扩展机制未变（by design）。
- **MCP tool description 混淆（KU01）**：main 已修——`get_tools()` 现对每个工具过 `sanitizeMCPToolName`/`sanitizeMCPToolDescription`（带长度上限）；snapshot 无任何消毒。
- **GHSA-pprx patch 语义冲突（U01）**：本轮未复核（需 lockfile 级语义对比，超出本次范围）；snapshot 后仅有 `fe285d0b` 纯依赖升级。
