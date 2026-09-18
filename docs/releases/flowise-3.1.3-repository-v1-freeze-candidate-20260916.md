# Flowise 3.1.3 repository-v1 freeze candidate（2026-09-16）

## 结论

此文档记录可审阅的 Phase 6 freeze candidate，**不是最终冻结批准**。完整性、隔离、计分与 mock smoke gates 均通过；最终 freeze 和任何 live matched block 仍为 `blocked`，因为五个 B 类 targeted validator 尚无 snapshot-matched、离线、Node 24 的依赖环境可运行。

## 冻结输入

- Case ID：`flowise_3_1_3_repository_v1`
- 上游：`https://github.com/FlowiseAI/Flowise.git`
- Vulnerable tag/commit：`flowise@3.1.3` / `09f099dbfda179e439ec677d06ad737375899eef`
- Comparison release/commit：`flowise@3.1.4` / `a65f81bb43ef66d3ce734bf0dff4223ae8041c95`
- Upstream vulnerable Git tree：`4da2b4977634b3bb238155430a79bd3dbef775c8`
- Agent target tree SHA-256：`c612819a833fc8ab3c58fe5085fb80fc0a6c4cb1d86cbb8ed41b0b431e4a1638`
- Evaluator-private tree SHA-256：`9947b7ab43ebe4ff483b8c894bbd07ea4e3b81828c6383bbc88a79ca0312c5e7`
- Case manifest SHA-256：`21926d2634336162aaceb014fdd21893167265c6c1c4c453f5272d55080a91bd`
- Base prompt SHA-256：`a63820831f9ab8864eb318444cfc8ad0b126043161833f145f8840e68c9581ec`
- Finding schema SHA-256：`97ad0335dde33ffd45a2056d7b8e15b79375fbea5a40c2e82d7f774ba7999c48`
- S/P/B/T tool-surface SHA-256：`3522153c128829670809a62908d356d1a7ce270e9ecb642da8833d35959a013e`
- Control-plane verifier SHA-256：`ebca28245c1ef6f08012153abfa074e6f188b64af62c632b2ec6296f08d93512`
- Verification result SHA-256：`6e1a683008af02b7127792e00aed09b5f646ba4e18ee71169c33699b13241a93`
- Test-result record SHA-256：`73b4a87849aba06a3739c91ee60a19ce24f45267339deca676363e9d09ba4178`

Manifest 固定 S1/P4/B4/T4，四条件共用 target、repository-v1 base prompt、repository-v1 finding schema、模型/工具能力边界和 64 个 team-level call permits。B 仅获得 generic persistent store；T 仅获得已冻结 typed task state；M 未定义也未接入。

## Census 与评分边界

| 项目 | 数量 |
| --- | ---: |
| Advisory manifestations | 21 |
| Independent scored roots | 20 |
| A（static-primary） | 15 |
| B（static + targeted local validation） | 5 |
| C（known-unscored） | 2 |
| CI-only scope exclusions | 1 |
| Unresolved（未进入分母） | 2 |
| Proven known near misses | 5 |

主分以 independent semantic root cause 为单位；R01 的 bounded variants 只计 coverage，不形成额外 TP。C、CI-only 与 unresolved 均不进入 scored denominator。Agent 的 verification/reproduction 声明不是 TP 前提，evaluator 不使用 LLM semantic judge。

## Active fronts 与共享安全不变量

- 企业组织、workspace、chatflow、credential、assistant 与历史对象必须绑定到正确 principal/workspace/organization。
- 管理和内部 route 需要显式 permission/role/tenant guard，而非仅认证。
- SSO 身份链接需要 issuer/subject 与 invitation state proof，而非 email 或数据库字段回灌。
- 用户、export 与响应 DTO 不得序列化 credential、hash 或 plaintext secret。
- MCP process execution 的 executable、args、cwd、env 是独立 capability fields，均需 operator policy。
- 模型生成 SQL、可配置 HTTP/model URL、browser loader 与 session key 必须在进入相应 runtime capability 前受 read-only、egress 或 scalar-type guard。
- abort handle 与 public endpoint 必须绑定 operation owner 或显式 public capability。

真实 safe siblings 只对完整证明的窄路径作为 known near miss；局部 middleware、TypeScript 类型、局部 URL deny list、MCP env allowlist 或 SQLite path containment 均不自动构成安全反例。

## 验证覆盖

- `scripts/verify_flowise_3_1_3_repository_v1.py` 通过：重算 target/private/prompt/schema/tool digests，验证 20 个 scored anchors、字段无 `TBD`、21 advisory disposition、A/B/C/near-miss/unresolved 对账和 target leakage scan。
- `python3 -m unittest discover -s experiments/emergent_coordination/tests -t .`：91 passed。
- repository-pilot-v0 target-visible smoke：6 passed，保留旧 pilot compatibility。
- 新 case S/P/B/T mock smoke：通过；四条件以同一 Flowise target、base prompt、schema、64 team permits 运行。另有 CLI selected-case mock smoke 成功。
- `git diff --check`：通过。

上述均是 condition-blind integrity/mock checks。未运行真实模型、正式 live matched block、treatment comparison、M、外网 validator 或完整 exploit。

## 未闭合风险与阻止条件

1. R10、R13、R14、R16、R17 的 B 类 local recipe 已定义且无网络，但尚未在本机执行：target 没有 `node_modules`，本机 Node 为 22，而 Flowise server 需要 Node 24。需要可审计的、snapshot-matched、离线 Node 24 dependency materialization，不能以临时联网安装替代。
2. U01（membership patch/source chain semantic conflict）与 U02（operator-controlled MCP security-check bypass）仍为 unresolved，未计分；在补足明确证据前不得迁入 scored GT。
3. 上游 branding 与版本字符串保留为 residual source-identity leakage；没有为匿名化重写程序语义。target scan 对 GT、advisory、fix、case ID、private evaluator、provenance 和 build-root tokens 通过。

因此下一步是满足或明确处理 B-validator 环境 gate，然后重新运行本 verifier 和完整回归，更新所有 digest；在用户明确批准前，`live_gate` 必须保持 `blocked`。
