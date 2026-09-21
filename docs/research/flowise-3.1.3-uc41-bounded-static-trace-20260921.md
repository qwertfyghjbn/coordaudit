# UC41 Host-header 路径静态裁决（2026-09-21）

结论：**validated positive**，仅针对 `flow-execution → ChatflowTool` 的凭证外发链。issue #6687 所述 `evaluations → EvaluationRunner` 链在本仓库 `flowise@3.1.3` snapshot 已修复，不能作为此 positive 的证据。

## 已关闭的 evaluations 链

`controllers/evaluations/index.ts:32,56` 两个入口均用 `process.env.APP_URL` 构造 `baseURL`。`services/evaluations/index.ts:174` 将该值传入 `EvaluationRunner`；其 `evaluation/EvaluationRunner.ts:144` 的 `axios.post` 确实是出站 sink，且带可选 bearer key，但请求 Host 不进入此 sink 的目标。issue #6687 的 affected range 自述止于 3.1.2，3.1.3 为 fixed。此链在目标 snapshot 中是 false positive。

## 3.1.3 中独立存在的 flow-execution 链

1. Source：`server/src/utils/buildChatflow.ts:1004-1005` 使用 `req.get('x-forwarded-proto') || req.protocol` 与 `req.get('host')` 拼接 `baseURL`。外部 prediction 请求的 API-key 校验在 :1030-1035；通过后值进入 `executeFlow` (:1065)。`upsertVector.ts:252-253` 也构造同类值，但本裁决不依赖 upsert 路径。
2. Propagation：`executeFlow` 将 `baseURL` 传至节点初始化（`buildChatflow.ts:595` → `utils/index.ts:657`）。`components/nodes/tools/ChatflowTool/ChatflowTool.ts:176` 在节点未配置固定 `baseURL` 时使用 `options.baseURL`。
3. Sink：同一节点 :188-198 从节点凭证取 `chatflowApiKey` 并生成 `Authorization: Bearer`；:376 将 baseURL 拼进 `$apiURL`；:358-371 的 NodeVM `node-fetch` 发送 POST。`components/src/utils.ts:1754-1759` 将其替换为 `secureFetch`，最终在 `components/src/httpSecurity.ts` 的 `secureFetch` 中发出网络请求。
4. Guard：`isValidURL` 只校验 HTTP(S) 语法（`components/src/validator.ts:22-31`），不要求同源或 operator-owned host。`secureFetch` 的 DNS/IP deny list、逐跳 redirect 校验和 IP pinning 默认阻止 loopback、RFC1918 与 metadata IP，因此**不能**据此宣称默认配置允许内网 SSRF。它允许未落 deny list 的攻击者公网主机；没有 trusted-base 重建或公网目标 allowlist。Host 仍决定最终 URL，且 bearer header 随首个请求发送。

成立前提：调用者能通过父 flow 的访问校验并触发已配置的 ChatflowTool；该节点未固定 `baseURL`，引用的子 flow 配有 API key；攻击者能把父请求的 Host 指向其可接收请求的公网服务。影响是该子 flow bearer key 外发及一次由服务器发起的公网 POST。这里的 positive 基于静态 source→sink 与 guard 证据，不依赖 issue 所述旧版本动态 PoC，也未做任何外部网络请求。

边界：这是与 evaluations 不同的实现位置和 precondition。默认 deny list 对内网地址有效；节点显式固定 baseURL 时 Host 不影响目标。最终 GT 应给此实现单独 root，并把 issue #6687 仅作为发现线索，不当成 3.1.3 适用性证明。
