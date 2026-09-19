# Flowise repository-v1 S1 completion finding 复核与容量决策（2026-09-19）

## 结论

本记录复核 `convergent_v1` completion calibration 的 S1 提交。运行本身有效，Agent 成功提交了两条 OAuth2 相关 finding；但两条 finding 的证据引用都只有 `evt_00000228`，该 evidence 只对应 `packages/server/src/utils/constants.ts`，没有覆盖实际 OAuth2 route 或全局认证 middleware。因此它们是格式有效、初步方向合理的候选 finding，不是已经完成证据闭环的安全结论。

原始运行：

- run：`single_n1_20260919T003239.655288+0000_bcbf7ec3`
- case：`flowise_3_1_3_repository_v1`
- policy：`convergent_v1`
- model/provider：`deepseek-flash` / `openai_compatible`
- output ceiling：2048
- hard team permits：64
- validity：`valid`
- reconciliation：`valid`
- 调用：57 次；提交：1 次；提交 finding：2 条；未触发 output ceiling

离线复核产物位于该 run 的 `completion_path_replay.json` 与 `evidence_lineage_replay.json`。复核未读取 evaluator private、ground truth 或 provenance。

## Finding 1：refresh endpoint

标题：`Unauthenticated OAuth2 credential refresh endpoint allows arbitrary credential mutation by ID`

代码路径支持以下事实：

1. `/api/v1/oauth2-credential/refresh` 位于 whitelist；
2. 全局认证 middleware 对 whitelist 直接 `next()`；
3. `POST /refresh/:credentialId` 按请求路径中的 ID 查询 credential，没有 workspace/ownership 条件；
4. 成功后解密、调用 token endpoint 并更新 credential。

因此“未认证调用者可以在知道 credential ID、且该 credential 具备可用 refresh token 的前提下触发跨 workspace credential 变更”是可信方向。

需要收窄的部分：

- “任意 credential”不是无条件成立，仍需要知道或猜到 ID，并满足 provider 接受 refresh 请求；
- 响应暴露的是 token metadata，不是 access token 本身；
- 当前 Agent evidence 没有读取 route 和 middleware 文件，不能仅凭 `evt_00000228` 完成 source-to-sink 证据闭环。

当前判断：`candidate / likely valid`，建议保留为高优先级人工复核项，但暂不作为已验证 TP。

## Finding 2：callback endpoint

标题：`Unauthenticated OAuth2 callback endpoint performs server-side token exchange and mutates credentials`

代码路径支持以下事实：

1. callback 位于 whitelist；
2. `state` 被直接当作 credential ID；
3. callback 没有 session/state 绑定或 ownership 校验；
4. 在有效 authorization code 通过 provider 校验后，服务端会更新 credential token data。

但原提交的“未认证调用者可以任意驱动任意 credential 变更”表述过强。攻击者还需要提供一个能被该 credential 的 OAuth client/redirect/token endpoint 接受的有效 authorization code。更准确的安全表述是：

> callback 缺少 OAuth state 绑定和 credential ownership 校验，存在 OAuth login-CSRF / 跨租户 callback 注入风险，可能条件性覆盖 credential token。

当前判断：`conditional risk / needs targeted validation`，建议降为 medium 候选；不能与 refresh endpoint 一样直接按确定性的 arbitrary mutation 计分。

## 两条 finding 的关系

两条不是同一个 endpoint：第一条是 refresh-token flow，第二条是 authorization-code callback flow；可以作为两个 variant 保留。但它们共享同一根因：公开 whitelist 与未绑定 workspace/ownership 的 credential lookup。若后续报告需要减少重复，应将它们归入同一个 OAuth2 access-control 根因下的两个 endpoint variant。

## 是否继续做 96/128-permit S1

不建议立即连续运行 96 和 128 两个样本。64-permit 的 completion path 已经在第 57 次调用成功提交，剩余 7 个 permits；因此继续增加 permits 不能再验证“能否从审查进入提交”这一问题。

更合适的容量实验是：

1. 先做一次独立的 96-permit S1 diagnostic，`max_steps=96`，保持 target、provider/model、2048 ceiling、base prompt、finding schema 和 `convergent_v1` 不变；最后 8 次调用仍保留为 finalization reserve。
2. 预注册 96-run 的成功标准：至少出现新的 route-level evidence refs，或产生 evaluator-verified positive；只有“调用更多但仍重复读取 constants、仍是 unmatched finding”不算容量收益。
3. 只有 96-run 在 finalization 前仍持续产生新证据，或在 96 permits 仍因容量耗尽而未完成提交，才追加 128-permit S1。
4. 96/128 都必须使用新的 calibration run ID/seed，不能并入已冻结的 64-permit formal matched block，也不能把不同 permit 数量的结果直接比较为 coordination effect。

成本上，当前 64-run 观测到约 3.99M input tokens 和 15.6K output tokens。若行为近似线性，96 相比 64 约增加 32 次调用，128 约增加 64 次调用；由于长 transcript 会持续增长，实际输入成本可能高于简单线性估计。当前两条 finding 仍未形成 TP，优先价值应放在补齐 route/middleware evidence 与人工复核，而不是直接投入 128 permits。

## 复核边界

`unmatched_review` 只表示 finding 没有自动匹配到标注 positive 或 known near-miss；它不是自动判定为 false positive。两条 finding 仍需 condition-blind 的人工复核，不能把本次 `0/20` 直接解释为模型确认错误。

