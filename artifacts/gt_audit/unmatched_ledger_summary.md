# Unmatched candidate ledger — flowise_3_1_3_repository_v1

- generated_at: 2026-09-21T05:21:09.109679+00:00
- runs scanned: 115 (flowise: 63, excluded non-flowise: 52)
- unmatched/known_near_miss findings: 94 (known_near_miss: 0)
- deduplicated clusters: 40

范围说明：这 40 个 cluster 仅由 63 个 flowise 历史 run 的 94 条 unmatched finding 聚类而成；公开 issue #6687 的 UC41 不在本 ledger，见 `adjudication_consolidated.json` 的 41 个跨来源候选分母。

| id | claim | file:function | n | conds |
| UC01 | Unauthenticated OAuth2 credential endpoints (GET /api/v1/oauth2-credential/callback, POST /refresh/:credentialId) are whitelisted and mutate/read arbitrary credentials via attacker-controlled state or credentialId without workspace/ownership scoping (cross-tenant credential token injection/overwrite). | `server/src/routes/oauth2/index.ts:router.get('/callback')` | 20 | B/P/S/T |
| UC02 | Unauthenticated /api/v1/feedback endpoints (whitelisted) allow reading all chat-message feedback for any chatflow (GET) and modifying arbitrary feedback records (PUT /:id) without authentication or ownership checks (cross-tenant IDOR). | `server/src/controllers/feedback/index.ts:getAllChatMessageFeedback` | 12 | S/T |
| UC03 | Unauthenticated whitelisted POST /api/v1/text-to-speech/generate accepts an arbitrary credentialId and consumes any stored TTS credential without ownership/workspace check (credential abuse). | `server/src/controllers/text-to-speech/index.ts:generateTextToSpeech` | 9 | P/S/T |
| UC04 | Unauthenticated whitelisted GET /api/v1/get-upload-file streams uploaded files for any chatflowId/chatId/fileName without public/ownership verification (cross-tenant file read IDOR). | `server/src/routes/get-upload-file/index.ts:router.get('/', getUploadFileController.streamUploadedFile)` | 8 | B/P/S/T |
| UC05 | Webhook endpoint /api/v1/webhook/:id is unauthenticated by default (no signature auth, no bound API key) and resolves chatflows without workspace scoping, allowing execution of arbitrary webhook-triggered chatflows. | `server/src/routes/webhook/index.ts:router.all('/:id', ...)` | 5 | S/T |
| UC06 | Whitelisted openai-assistants file-download endpoint (GET /api/v1/openai-assistants-file/:fileName) passes attacker-controlled fileName to storage without the isUnsafeFilePath/UUID validation used by its sibling endpoint (path traversal file read). | `server/src/controllers/openai-assistants/index.ts:getFileFromAssistant` | 4 | S/T |
| UC07 | Public POST /api/v1/attachments/:chatflowId/:chatId allows unauthenticated file upload into arbitrary chatflow storage when uploads are enabled (missing ownership/API-key check). | `server/src/routes/attachments/index.ts:router.post` | 2 | S/T |
| UC08 | PATCH /api/v1/datasets/rows (patchDeleteRows) deletes dataset rows by id without verifying the parent dataset belongs to the caller workspace (cross-workspace IDOR). | `server/src/controllers/dataset/index.ts:patchDeleteRows` | 2 | S |
| UC09 | Attacker-authored JavaScript from CustomTool executes in the NodeVM fallback of executeJavaScriptCode with only vm2 isolation (insufficient sandboxing / code execution). | `components/nodes/tools/CustomTool/core.ts:DynamicStructuredTool._call` | 1 | T |
| UC10 | Unstructured document loader performs server-side requests to an attacker-controlled API URL, bypassing the SSRF guard (SSRF via loader config). | `components/nodes/documentloaders/Unstructured/UnstructuredFile.ts:init` | 1 | T |
| UC11 | Code injection into the E2B sandbox bootstrap via unvalidated sandbox variable names in executeJavaScriptCode. | `components/src/utils.ts:executeJavaScriptCode` | 1 | T |
| UC12 | GitHub SSO accepts unverified email, enabling account takeover (GithubSSO.setSSOConfig / SSOBase.verifyAndLogin). | `server/src/enterprise/sso/GithubSSO.ts:GithubSSO.setSSOConfig` | 1 | T |
| UC13 | SSO login auto-provisions accounts and selects a workspace without tenant binding (verifyAndLogin). | `server/src/enterprise/sso/SSOBase.ts:verifyAndLogin` | 1 | S |
| UC14 | Cross-tenant SSO secret disclosure: enterprise login-method testConfig returns config with secrets and is missing an organization guard. | `server/src/enterprise/controllers/login-method.controller.ts:LoginMethodController.testConfig` | 1 | T |
| UC15 | Organization read endpoint allows cross-organization IDOR exposing Stripe customerId/subscriptionId. | `server/src/enterprise/controllers/organization.controller.ts:read` | 1 | S |
| UC16 | Cross-tenant organization update via organization.controller.update missing organization guard. | `server/src/enterprise/controllers/organization.controller.ts:OrganizationController.update` | 1 | T |
| UC17 | Cross-tenant organization-user create/update/delete missing organization guard (IDOR on org membership). | `server/src/enterprise/controllers/organization-user.controller.ts:OrganizationUserController.create/update/delete` | 1 | T |
| UC18 | Cross-tenant role deletion via role.controller.delete missing organization guard. | `server/src/enterprise/controllers/role.controller.ts:RoleController.delete` | 1 | T |
| UC19 | Arbitrary user creation via user.controller.create without required permission (unauthenticated-by-permission user creation). | `server/src/enterprise/routes/user.route.ts:userRouter` | 1 | T |
| UC20 | Cross-tenant workspace membership manipulation via workspace-user create/update/delete missing tenant guards. | `server/src/enterprise/controllers/workspace-user.controller.ts:WorkspaceUserController.create/update/delete` | 1 | T |
| UC21 | Custom MCP server authorize/connect path performs server-side requests to user-supplied URLs (MCPToolkit.createClient) with deny-list opt-out (SSRF). | `server/src/services/custom-mcp-servers/index.ts:authorizeCustomMcpServer` | 1 | T |
| UC22 | TTS CORS preflight is allowed for any origin when chatflowId is absent from the body (getCorsOptions misconfiguration). | `server/src/utils/XSS.ts:getCorsOptions` | 1 | S |
| UC23 | API key secret hash and raw API key disclosed to any user holding only apikeys:view permission. | `server/src/services/apikey/index.ts:getAllApiKeys` | 1 | T |
| UC24 | Authentication middleware whitelist uses prefix (startsWith) matching, allowing unauthenticated access to any route whose path begins with a whitelisted prefix. | `server/src/index.ts:App.config (auth middleware)` | 1 | S |
| UC25 | Unauthenticated chatflow disclosure via /chatflows/apikey/:apikey with unvalidated keyonly parameter. | `server/src/routes/chatflows/index.ts:router.get(['/apikey/', '/apikey/:apikey'], chatflowsController.getChatflowByApiKey)` | 1 | T |
| UC26 | Unauthenticated disclosure of private chatflow flowData via the public-chatbotConfig endpoint (no isPublic check). | `server/src/controllers/chatflows/index.ts:getSinglePublicChatbotConfig` | 1 | S |
| UC27 | Document store upsert/refresh routes omit the RBAC permission checks present on sibling documentstore routes. | `server/src/routes/documentstore/index.ts:router` | 1 | S |
| UC28 | Document store vector-store query/config/tool-desc endpoints lack workspace scoping (cross-tenant IDOR read of document stores). | `server/src/routes/documentstore/index.ts:router.post('/vectorstore/query', ...)` | 1 | S |
| UC29 | Public chatflow domain validation defaults to allow when no allowlist is configured (validateChatflowDomain). | `server/src/utils/domainValidation.ts:validateChatflowDomain` | 1 | S |
| UC30 | Unauthenticated fetch-links endpoint performs server-side URL fetch (webCrawl/xmlScrape) guarded only by a DNS-based deny list (SSRF). | `server/src/controllers/fetch-links/index.ts:getAllLinks` | 1 | S |
| UC31 | Unauthenticated MCP endpoint DELETE route bypasses Bearer-token authentication. | `server/src/routes/mcp-endpoint/index.ts:router.delete('/:chatflowId', ...)` | 1 | T |
| UC32 | MCP endpoint executes any chatflow with isInternal=true, bypassing flow API-key validation (chatflowCallback). | `server/src/services/mcp-endpoint/index.ts:chatflowCallback` | 1 | T |
| UC33 | MCP endpoint chatflow lookup is not workspace-scoped (IDOR surface), though token check mitigates. | `server/src/services/mcp-server/index.ts:getChatflowByIdAndVerifyToken` | 1 | T |
| UC34 | Global auth/whitelist middleware evaluates req.path after sanitizeMiddleware rewrites req.url with sanitizeHtml(decodeURI(...)), enabling auth-whitelist bypass via encoded/mutated paths. | `server/src/utils/XSS.ts:sanitizeMiddleware` | 1 | T |
| UC35 | POST /api/v1/node-custom-function reachable with only chatflows:create/update passes workspace variables (incl. runtime env secrets) into the JS sandbox because the skipVariables flag is never enforced in getVars (secret disclosure to low-privileged users). | `server/src/controllers/nodes/index.ts:executeCustomFunction` | 1 | T |
| UC36 | Missing authorization checks on NVIDIA NIM container-management routes (startContainer etc.). | `server/src/routes/nvidia-nim/index.ts:router` | 1 | S |
| UC37 | Unauthenticated prediction endpoint applies attacker-controlled overrideConfig to flow node inputs (API override abuse). | `server/src/controllers/predictions/index.ts:createPrediction` | 1 | T |
| UC38 | Public prediction endpoint executes any chatflow regardless of its isPublic flag. | `server/src/controllers/predictions/index.ts:createPrediction` | 1 | S |
| UC39 | Webhook async callbackUrl SSRF: dispatchCallback performs server-side requests to user-supplied URLs where only the protocol is validated and the SSRF deny-list is disabled by default (HTTP_SECURITY_CHECK=false). | `server/src/controllers/webhook/index.ts:createWebhook` | 1 | T |
| UC40 | Webhook-listener SSE stream accepts a client-supplied listenerId without verifying ownership of the associated chatflow, allowing subscription to other users webhook events. | `server/src/controllers/webhook-listener/index.ts:streamListener` | 1 | T |
