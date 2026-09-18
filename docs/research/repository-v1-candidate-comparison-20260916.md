# Repository-v1 大型真实仓库候选比较（2026-09-16）

## 结论

当前最适合先冻结并制作 hidden evaluator 的 snapshot 是 **Flowise 3.1.3**（`09f099dbfda179e439ec677d06ad737375899eef`）。它在约 1,854 个源码文件内提供 18 个可计分的独立语义根因、约 10–13 个有效活跃前沿，以及 workspace/tenant、credential ownership、process execution、egress policy、session identity 等可跨模块传播的安全不变式。它比 Flowise 3.1.2 更少受重复 sandbox advisory 主导，也不像 n8n 2.38.1 那样容易先测到搜索空间和预算上限。

**Langflow 1.8.1** 和 **Open WebUI 0.11.0** 是另外两个 primary candidates。前者的 safe sibling 和跨模块共享语义最好，但 fix 分散、部分 advisory 尚缺逐项 fix-commit 映射；后者的有效源码规模最合适，授权、OAuth、SSRF 与图结构不变式也很强，但 `0.11.0..0.11.1` 混入大量非安全提交，evaluator 制作费用略高。

**n8n 2.38.1** 的 root-cause 结构本身足够强，但约 21,345 个源码文件对 64-permit team budget 是显著干扰，因此先作为 scale-stress candidate。**Flowise 3.1.2** 同样进入 scale-stress：它的 53 个 advisory manifestation 去重后仍很多，但 sandbox/Python-validator 变体密集，annotation 与评分去重风险高。

本报告不依据任何 S/P/B/T/M 实跑相对成绩排序；排序只使用 condition-blind 属性。

## 证据来源与方法

- Snapshot 与 fix commit 取自各 upstream repository 的 tag/commit graph；文件数由 `git ls-tree -r` 对对应 commit 机械计数。
- Candidate census 以 [Flowise advisories](https://github.com/FlowiseAI/Flowise/security/advisories)、[Langflow advisories](https://github.com/langflow-ai/langflow/security/advisories)、[n8n advisories](https://github.com/n8n-io/n8n/security/advisories) 与 [Open WebUI advisories](https://github.com/open-webui/open-webui/security/advisories) 的 affected range 为起点，再与 vulnerable source、fix PR/commit、release diff 和 regression test 交叉核验。
- [VulnGym](https://github.com/Tencent/VulnGym) 只用于补充 vulnerable commit、entry point、critical operation 与已复核 trace；没有要求 finding 必须已进入 VulnGym。
- Advisory description 可能错误、过度声明或把多个问题合并。本报告以 snapshot 中实际 source 和 patch behavior 为最终依据；存在冲突时明确保留为未闭合项。

## 更新后的 benchmark 边界

- 主任务是 evidence-grounded repository audit：静态跨文件程序理解、安全推理和证据交接。
- A（Static-primary）与 B（Static + targeted local validation）进入 scored GT；C（Dynamic-dependent）默认进入 known-unscored registry。
- TP 不要求完整 exploit 或动态复现。满足冻结的 source/sink/guard、affected object、trust boundary、利用推理与 patch/safe-sibling 证据即可匹配。
- targeted validation 只用于消除一个关键语义歧义。成功验证可记录 evidence strength，但不改变 finding 身份。
- 主分按 independent semantic root cause；同一根因的多个入口另计 variant/coverage。

这项边界已写入 [ADR 0006](../adr/0006-repository-v1-static-first-validation-boundary.md)，相关领域术语已写入根级 `CONTEXT.md`。

## 计数口径

- `advisory count`：明确覆盖该 vulnerable commit/version 的公开 advisory manifestation；不会直接作为得分分母。
- `root-cause count`：对 advisory、入口和变体做代码级去重后的数量。
- `A/B/C`：本表按 root-cause cluster 计数，而不是 advisory 编号；`scope-excluded` 单列。
- `semantic regions`：需要不同入口、数据模型或安全区域知识的模块群。
- `active fronts`：在 64 permits 下可独立推进并形成可评分证据的估计区间，不等于文件数、目录数或 advisory 数。
- `source files`：主要程序语言文件的机械计数，仅描述导航负担，不表示漏洞密度。

## 总体比较

| candidate | exact vulnerable commit | tracked / source files | affected advisories | dedup root causes | A / B / C | semantic regions | active fronts | validation | evaluator | leakage | disposition |
|---|---|---:|---:|---:|---:|---:|---:|---|---|---|---|
| Flowise 3.1.3 | `09f099dbfda179e439ec677d06ad737375899eef` | 2,444 / 1,854 | 21 | 20；18 scored，1 C，1 task-scope excluded | 13 / 5 / 1，另 1 个 A scope-excluded | 11 | 10–13 | low–medium | medium | medium-high | **primary #1** |
| Langflow 1.8.1 | `a2e166048e4f39b5932f638440f8d82f1e40bd4e` | 4,629 / 3,708 | 16 | 14 scored；另有 1 个 dynamic exploitation variant unscored | 10 / 4 / 0 | 9 | 10–12 | low–medium | medium-high | high | **primary #2** |
| Open WebUI 0.11.0 | `f9590b8017199e56d5e953657e6498e3cef1d246` | 5,031 / 995 | 17 | 16 | 11 / 5 / 0 | 8 | 11–14 | low–medium | medium-high | medium-high | **primary #3 / reserve** |
| n8n 2.38.1 | `ee7aca5845c9db2188150591eceebe20c1314643` | 27,648 / 21,345 | 19 relevant；另 1 个 documented dangerous capability | 18 | 12 / 6 / 0 | 11 | 14–17 | medium | medium | medium-high | **secondary / scale-stress** |
| n8n 2.37.6 | `455dae49f98093929d770285524dce0726e47f14` | 27,227 / 21,039 | 同一组 19 relevant | 18 | 12 / 6 / 0 | 11 | 14–17 | medium | medium | medium-high | secondary；与 2.38.1 二选一 |
| n8n 2.35.3 | `0dccd14a44a4e590b8641a12a95c9c76f8d525dc` | 26,398 / 20,406 | 28 relevant；另 1 个 documented capability | 23–25（provisional） | 18 / 9 / 1（provisional） | 14–16 | 17–22 | medium-high | high | medium-high | scale-stress only |
| Flowise 3.1.2 | `4114b3b506e7bbee155141175a2ba48e426919dd` | 2,235 / 1,660 | 53 | 38（provisional） | 27 / 10 / 1 root；advisory manifestation 35 / 17 / 1 | 16–18 | 18–24 | medium | high | high | scale-stress；不作首个 case |
| Flowise 3.1.3 之后的 3.1.4 | `a65f81bb43ef66d3ce734bf0dff4223ae8041c95` | 未作为 vulnerable target 计数 | 仍有未修复项，但不形成干净 patch pair | 未冻结 | 未冻结 | 未冻结 | 未冻结 | — | high | high | reject for current freeze |
| n8n 2.39.5 | `8e7bbabd9a44798261332b686a7b1c111c3b5759` | 28,218 / 21,758 | 0 个当前相关已确认漏洞；另 1 个明确设计能力 | 0 | 0 / 0 / 0 | 0 | 0 | — | — | — | reject |

`n8n` 的 “Execute Command Node” advisory 描述的是管理员可禁用、文档化的危险能力，不能把它伪装成 ordinary vulnerability GT，故不计入 relevant count。

## Primary candidates

### 1. Flowise 3.1.3

这是当前最佳单 snapshot：

- 15 个 advisory 在 `3.1.4` 修复，6 个在当前公开元数据中仍无 patched version；后者不能只靠 patch 建 GT，但其中 chat-message authorization、SSO identity binding、BullMQ RBAC、credential ownership 和 upsert-history ownership 都有强静态证据。
- 去重后的主前沿包括 enterprise tenant scoping、chat history、credential ownership、SSO state/IdP binding、queue RBAC、MCP process policy、OpenAI Realtime workspace scoping、SQL-chain execution、两类 egress policy、Mongo session identity、secret export 和 TTS boundary。
- 共享不变式至少有四类：`resource.workspaceId/orgId must match principal`、`credential decrypt/use must bind to owner/workspace`、`all process-launch paths share executable/cwd/env policy`、`all outbound URL paths share resolution/redirect/deny policy`。
- 知识传播机会明确：一个 Agent 从安全 sibling 提炼 workspace-scoped repository helper 后，能帮助另一个 Agent 检查 Realtime、credential、history 与 TTS；MCP allowlist 的发现也能传播到 cwd/env/argument 变体。
- 不会被一次 grep 覆盖：根因跨 enterprise controller、server route/service、component node、document loader、memory backend 和 export path。

主要风险是公开 advisory 描述非常具体，且一个 `GHSA-vrr6-xgc3-j99r` 混合多个子 finding。冻结时必须把它拆成 root-cause/variant，而不是作为一个或多个任意分值的 omnibus finding。

### 2. Langflow 1.8.1

Langflow 的优点不是 CVE 数，而是 safe-sibling 密度与共享语义质量：

- `download_image` 可与其他使用 `Depends(get_flow)` 的文件 route 比较；UUID flow lookup 可与 endpoint-name scoped branch 比较；KB path 可与 containment helper/patch 比较；trust-header 可与真实 TCP peer 比较。
- 14 个 root-cause cluster 分布在 knowledge-base containment、flow ownership、public execution、storage abstraction、code validation、webhook policy、upload boundary、secret derivation 和 proxy trust。
- Agent A 发现 “route protection is dependency-local, no global auth middleware” 后，可直接帮助 Agent B 审计 image、upload、responses 与 public playground；Agent A 发现 storage service 缺少 containment 后，可帮助检查 v1/v2 API 与 archive extraction。

不足是修复不集中在一个 release pair：部分 fix 位于 `1.8.2/1.9.x/1.10.x` 或 mainline/backport。当前已核到的 exact fix commit 包括：

- KB bulk-delete：`792808b1d5e6597a4a7ab20a59d536c3fe07849f`
- KB create：`41d34b204803dc2b7de9734bdd238cac87c32585`
- deprecated upload：`99da6d05879758b7757521e88d5aee0aff55d41f`
- responses IDOR：`2c9f498d664a3c32698b57d7c5e752625291060e`
- webhook default：`cb6f7508dda83ead9c3e4417e96e4b5bd9a260c3`
- BaseFile archive handling：`cb06a666d0f00a86d40599a91713fc615d7ea313`
- public-flow attacker data RCE：`73b6612e3ef25fdae0a752d75b0fabd47328d4f0`
- image ownership：`04b4af6e0f0d71bae10b9d4ce7b30e3377a25cae`
- v2 storage traversal：`d50eda2a480ed55a92f794fdbb9e4da89f62e7c8`
- public file read：`07c3e67a71a61c0a5dd0bdbdb95601dd2f816628`
- Fernet derivation：`094694d3f20c1da499f4d8dbac15c510609e3026`
- validate-code `exec`：`e7c33dbaade20b5295c7fa26bf83cc1ff68fba02`
- Smart Transform：mainline `1641b28f33e2c47b9a0c6855922d44d1b8418b9d`，1.10.3 backport `94859df33acd70b2a1f816e26d68f5e89a7e5639`
- X-Forwarded-For trust：`1f39a4b9d62c9dfa1b21fa7f85e23a180c351b72`

因此它适合 primary，但 freeze 前需完成剩余 two-way mapping：每个 GT 都要从 vulnerable location 指向 exact fix commit 和 regression test。

### 3. Open WebUI 0.11.0

这是本轮额外发现的更优候选。总文件数 5,031 看似偏大，但其中 3,840 个是 SVG，实际主要源码只有约 995 个，明显比 n8n 更适合 64 permits。

- 17 个 advisory 全部明确覆盖 `v0.11.0`，修复版本为 `0.11.1`；fixed release commit 为 `d3e8bf3405e848cfba377814d0aa7ba7290e414d`。
- 独立前沿包括 OAuth role/subject、tool-server cookie forwarding、knowledge ACL、channel/message ownership、folder ownership、stale admin permission、external knowledge deletion、三类 SSRF policy、same-origin terminal XSS、OIDC fetch exposure和 cyclic graph DoS。
- 共享不变式清晰：`resource owner/group membership`、`OAuth issuer+subject+role transition`、`URL resolution+redirect+DNS revalidation`、`folder/chat graph must remain acyclic`。
- Active-front 密度高：源码规模不大，但前沿跨 auth、knowledge、channels、folders、tools、OAuth、network fetch 和 chat graph。

不足是 `v0.11.0..v0.11.1` 有约 460 个 commit，不能把整个 release diff 当 evaluator oracle。必须从 advisory、具体 fix PR/commit 和 regression test 逐条回溯；这也是它暂排第三而非第一的原因。

## Secondary / scale-stress candidates

### n8n 2.38.1（优先于 2.37.6）

`2.38.1` 与 `2.38.2` 构成最干净的 n8n pair：vulnerable commit 为 `ee7aca5845c9db2188150591eceebe20c1314643`，fixed release commit 为 `7bd63f41c2f1f2bc2576c0728dbe2e68ed61e0f1`，主要安全 bundle 为 `8c8b059e03b73dcf30bcbf744702af9d844c14fe`。

19 个相关 advisory 可去重为约 18 个 root causes，覆盖 OAuth resource binding、project isolation、Git/source-control boundary、OIDC gating、webhook fail-open、workflow caller policy、expression sandbox、SSRF、path injection、prototype pollution、credential ownership、resume-token reuse 与 registration resource exhaustion。安全结构完全满足 coordination opportunity。

但它仍不是首个 P/B/T4 64-permit case：

- 约 21,345 个源码文件使 entry-point discovery 本身吞噬预算；
- 一个 bundle commit 同时修复大量问题，patch proximity 容易污染 evaluator 构造；
- 若 64 permits 下所有 condition 都只触达 2–3 个区域，实验测到的是 budget/search ceiling，不是 coordination adapter。

建议先以 Flowise/Langflow/Open WebUI 校准新规模，再把 n8n 2.38.1 用作 scale-stress。`2.37.6` 漏洞集合基本相同且文件略少，但缺少 `2.38.1 -> 2.38.2` 的一日 clean pair 优势，因此不同时纳入。

### n8n 2.35.3

它在 2.38.1 的 19 个相关 finding 之外，还加入 workflow credential exfiltration、query injection、Git RCE、AI-expression prototype leakage、mail-node file read/SSRF、credential error leakage、Insights authorization 等约 9 个 manifestation。其 active fronts 更多，但 evaluator、去重与搜索成本同步增加。它适合作为后续 128+ permit 或层级任务分解实验，不适合首个 64-permit case。

### Flowise 3.1.2

重新核验后的 snapshot-level 数量是 **53**，不是沿用旧 census：其中 32 个在 3.1.3 修复、15 个在 3.1.4 修复、6 个当前无 patched version。3.1.3 只受后两组影响，故不能把这 32 个继续计入 Flowise 3.1.3。

3.1.2 的问题不在于 work front 不足，而在于过多：Python validator、CSV/Airtable Agent 和 NodeVM/vm2 advisory 中有大量同根变体。当前 provisional clustering 为约 38 个 root causes，其中 27 A、10 B、1 C；冻结前仍需对 sandbox/validator 的 10 余个 advisory 做 code-level equivalence audit。因此它适合 scale-stress 或第二阶段“root-cause + variant coverage”实验，不宜作为第一个大型 case。

## Reject / defer

- **n8n 2.39.5**：当前 census 中没有形成多前沿的相关漏洞集合；巨大仓库不等于有效 case。
- **Flowise 3.1.4**：没有形成像 3.1.3→3.1.4 那样清楚的当前 vulnerable/fixed pair，且会丢失 15 个已修复前沿。
- **OpenClaw、CyberGym/SEC-bench 大型 C/C++ target**：继续 defer。它们适合后续动态、patch 或 scale stress，但本轮未发现一个单 snapshot 在 static discoverability、共享不变式和 evaluator 成本上优于前三名。
- **MLflow / Paperclip**：本轮公开 snapshot census 未证明同时存在至少四个独立 root causes、四个有效前沿和足够的跨模块共享语义；不因历史 CVE 数或项目知名度晋级。

## Evaluator 设计建议

每个 scored GT 冻结以下字段：

1. `root_cause_id` 与可选 `variant_id`；
2. vulnerable source location、source/sink/guard 与 affected object；
3. principal、tenant/workspace/project 等 trust-boundary requirement；
4. 至少一个 safe sibling 或 patch comparison；
5. 可接受的 exploitation reasoning，而不是固定 PoC 文本；
6. A/B/C、targeted-validation recipe 与 validation cost；
7. 允许匹配的位置别名、调用链别名和变体覆盖规则。

TP 判定不要求 `reproduced=true`。Targeted test、单函数调用或最小 HTTP request 只写入 `verification_status`/`evidence_strength`。同一根因多入口建议分成：

`root-cause discovery score + bounded variant/coverage score`

避免 advisory 数量放大主分，也避免只发现一个入口就自动获得所有 coverage。

## 冻结前 gate

建议先制作三套 evaluator，不运行 treatment comparison：

1. Flowise 3.1.3：完成 18 个 scored cluster 的 source location、fix/sibling 与 matcher；
2. Langflow 1.8.1：补齐所有 fix commit 的完整 SHA，并把 public-flow/file-storage 重叠关系做 source-level 去重；
3. Open WebUI 0.11.0：把 0.11.1 大 release diff 拆到单 advisory fix commits。

随后只做 condition-blind calibration：检查 64 permits 是否能触达至少 4 个 region、target mount 是否不含 advisory/patch/provenance、targeted validation 是否可在无外网本地完成、evaluator 是否对静态充分证据给 TP。冻结 digest 之后才运行 S/P/B/T/M。

## 尚未闭合的数据

- Flowise 3.1.2 的 sandbox/Python-validator advisory 仍有 2–4 个 cluster 边界需要逐函数 diff 确认；表中 root/A/B/C 为 provisional，不能直接成为最终分母。
- Langflow 仍有少数 fix 只定位到 PR/release 或尚未定位，需要与 vulnerable→fixed regression test 对齐。
- Open WebUI 0.11.0 的 17 个 advisory 已确认 affected range，但尚未全部定位到单独 fix commit；目前只有 fixed release commit。
- n8n `GHSA-cw9w...` 的文字与 machine-readable patched range 曾出现 2.38.1/2.38.2 不一致；源码 diff 显示 2.38.1→2.38.2 确有 resource-binding change，冻结时仍需保留该冲突记录。
- 当前仓库领域模型只正式定义了 S/P/B/T；`M` 的 manager authority、可见 transcript、工具能力与 team-level budget accounting 尚未在 `CONTEXT.md`/ADR 中定义。Target 可以 condition-blind 选择，但不能在 M 未定义前声称 S/P/B/T/M 是完整 matched block。

逐 root-cause 的 snapshot census 见 [附录](repository-v1-snapshot-census-20260916.md)。
