# T4 sequenced-bootstrap finding validation

## 范围与口径

本验证针对 immutable run `formal_t4-sequenced-bootstrap-v1-corrected`，使用同一 target digest `c612819a833fc8ab3c58fe5085fb80fc0a6c4cb1d86cbb8ed41b0b431e4a1638` 和 commit `49725612fff8539b681e8084f29ecb4de5ca8d5f`。

这里区分两个结果：

1. **formal scored TP**：当前冻结 `repository-v1` evaluator 的 category、canonical source/sink anchor、guard 和语义匹配结果；
2. **independent semantic adjudication**：对 agent 提交的 source→sink 链做静态安全复核。Repository-v1 是 static-first，动态 exploit 不是 TP 的必要条件。

不修改原始 manifest、trace 或 hidden ground truth，也不把本次复核结果回写为旧 run 的 TP。

## 结果

| finding | formal evaluator | 独立语义复核 | 结论 |
|---|---|---|---|
| agent_001 `node-custom-function` 变量泄露 | unmatched | **FP** | 引用代码显示 `skipVariables` 被实际检查；当前推理与自身 sink anchor 矛盾 |
| agent_002 webhook `callbackUrl` SSRF | unmatched | **inconclusive / hardening concern** | callbackUrl 来自 chatflow 配置而非 webhook 请求；`HTTP_SECURITY_CHECK=false` 是显式全局 opt-out，未证明当前 audit threat boundary 下的攻击者可控输入 |
| agent_003 未认证 TTS 任意 credential 使用 | unmatched | **semantic TP**（R04-style credential IDOR） | body credentialId → `getCredentialData` 的 id-only lookup，无 workspace/ownership guard |
| agent_004 GitHub 未验证邮箱 SSO | unmatched | **semantic TP**（R08-style cross-IdP identity confusion） | GitHub 未验证邮箱 fallback → `readUserByEmail` → session issuance，缺少 issuer/subject binding |

## 关键证据

### agent_001：FP

同一条 evidence chain 显示：

- `executeCustomNodeFunction` 设置 `skipVariables: !canViewVariables`；
- `getVars` 在 `options.skipVariables` 为真时直接返回空数组。

因此标题“skipVariables flag never enforced”未被代码支持。参见 [executeCustomNodeFunction.ts](/home/lqs/coordaudit/experiments/emergent_coordination/runs/t4-sequenced-bootstrap-v1-corrected-192p/formal_t4-sequenced-bootstrap-v1-corrected/runtime/private/agent_001/target/packages/server/src/utils/executeCustomNodeFunction.ts:49) 和 [utils.ts](/home/lqs/coordaudit/experiments/emergent_coordination/runs/t4-sequenced-bootstrap-v1-corrected-192p/formal_t4-sequenced-bootstrap-v1-corrected/runtime/private/agent_001/target/packages/components/src/utils.ts:982)。

### agent_002：不进入 TP

代码确实存在：async webhook 读取 chatflow Start-node 的 `callbackUrl`，controller 只检查 `http/https`，随后调用 `secureAxiosRequest`；当 `HTTP_SECURITY_CHECK=false` 时默认 deny list 被移除。但 callbackUrl 是已保存的 chatflow 配置，不是公开 webhook body 中的攻击者 URL。该 finding 更适合记录为配置/部署 hardening concern，不能从这条 trace 单独确认 benchmark TP。

### agent_003：语义 TP

关键链条为：

- `/api/v1/text-to-speech/generate` 位于 whitelist；
- 无 `chatflowId` 时直接采用 body 的 `credentialId`；
- options 使用空 `orgId`；
- `getCredentialData` 使用 `findOneBy({ id: selectedCredentialId })`，没有 workspace predicate。

参见 [controller](/home/lqs/coordaudit/experiments/emergent_coordination/runs/t4-sequenced-bootstrap-v1-corrected-192p/formal_t4-sequenced-bootstrap-v1-corrected/runtime/private/agent_003/target/packages/server/src/controllers/text-to-speech/index.ts:70)、[constants.ts](/home/lqs/coordaudit/experiments/emergent_coordination/runs/t4-sequenced-bootstrap-v1-corrected-192p/formal_t4-sequenced-bootstrap-v1-corrected/runtime/private/agent_003/target/packages/server/src/utils/constants.ts:44) 和 [components utils](/home/lqs/coordaudit/experiments/emergent_coordination/runs/t4-sequenced-bootstrap-v1-corrected-192p/formal_t4-sequenced-bootstrap-v1-corrected/runtime/private/agent_003/target/packages/components/src/utils.ts:651)。

这是有效的 credential capability/ownership 缺失，但提交没有携带当前 R04 canonical helper anchor，因此冻结 evaluator 不计分。

### agent_004：语义 TP

GitHub strategy 先找 `primary && verified`，找不到时退回 `emails[0].email`，随后传入 `verifyAndLogin`；`verifyAndLogin` 以 `readUserByEmail` 选择账户并签发登录态，没有 issuer/subject 绑定。参见 [GithubSSO.ts](/home/lqs/coordaudit/experiments/emergent_coordination/runs/t4-sequenced-bootstrap-v1-corrected-192p/formal_t4-sequenced-bootstrap-v1-corrected/runtime/private/agent_004/target/packages/server/src/enterprise/sso/GithubSSO.ts:46) 和 [SSOBase.ts](/home/lqs/coordaudit/experiments/emergent_coordination/runs/t4-sequenced-bootstrap-v1-corrected-192p/formal_t4-sequenced-bootstrap-v1-corrected/runtime/private/agent_004/target/packages/server/src/enterprise/sso/SSOBase.ts:56)。

这与 R08 的 cross-IdP email-only identity 根因一致；但当前冻结 GT 要求的函数名/anchor 与实际 snapshot 的 `verifyAndLogin` 不一致，因此 formal matcher 返回 unmatched，不能通过伪造函数名追认 TP。

## 最终判断

当前 frozen run 的正式 scored TP 仍是 **0/4**。这反映的是 canonical anchor contract，不是四条都为假。

独立静态复核结果为：

- 1 条 FP（agent_001）；
- 1 条 inconclusive/hardening（agent_002）；
- 2 条语义上成立但未被当前 frozen matcher 计分（agent_003、agent_004）。

若希望将后两条计入 benchmark，下一步应新建 versioned ground-truth/contract amendment，补齐正确的 snapshot anchors，再在不修改旧 run 的前提下重新评分。
