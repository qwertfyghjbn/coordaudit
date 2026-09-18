# Repository-v1 snapshot × vulnerability census（2026-09-16）

本附录记录候选 snapshot 的 root-cause-level census。公开 advisory 是定位来源，不是评分单位；同一行列出多个 advisory 时，表示它们当前被聚为同一根因或同一根因的 reachable variants。`TBD` 表示 freeze 前仍需核验，不能用猜测补齐。

## 字段约定

- `affected/fix`：是否明确影响该 exact vulnerable commit，以及 fix version/commit。
- `region/class/root cause`：semantic region、vulnerability class 与代码级根因。
- `static evidence`：Agent 仅凭 source 可取得的证据。
- `D`：A=Static-primary，B=Static + targeted local validation，C=Dynamic-dependent。
- `validation/cost`：最小本地验证与 low/medium/high 成本。
- `front/invariant/dup`：能否成为独立 work front、共享不变式、重复关系。
- `sibling/evaluator/leak`：safe sibling/near miss、hidden evaluator 评分依据与公开信息泄漏风险。

所有表默认：target mount 删除 `.git`、advisory、patch、GT、case label 与 provenance；evaluator 允许位置别名、调用链别名和等价的 trust-boundary 论证。

## Flowise 3.1.3

Vulnerable commit：`09f099dbfda179e439ec677d06ad737375899eef`。2,444 tracked files，约 1,854 source files。21 advisory manifestations；20 个 root-cause rows，其中 18 个 A/B scored、1 个 C known-unscored、1 个不属于当前 HTTP repository-audit task scope。

| cluster / advisory | affected / fix | region / class / root cause | static evidence | D / validation / cost | front / invariant / duplication | sibling / evaluator / leak |
|---|---|---|---|---|---|---|
| F313-01 `7x8x-vv46-4579`, `pprx-4prj-35mj` | yes；3.1.4 `9fcb7ffb`/`5ecc3c5c` | enterprise org/workspace；auth/IDOR；membership/resource query 未绑定 principal tenant | route→service→unscoped repository query；角色检查不能替代 object scope | A；构造两 tenant repository test；low | 独立 front；`object.org/workspace == principal scope`；多 endpoint variants | scoped sibling query；按 affected object+missing predicate；high |
| F313-02 `fhxm-xxcx-g6x3` | yes；3.1.4 `ed9e100f` | organization user；secret disclosure；GET serialization 暴露 owner password hash | response DTO/serializer 包含敏感字段且普通 member 可达 | A；直接调用 sanitizer/serializer；low | 独立；`secret never crosses read DTO` | safe response DTO；按 route+field+principal；high |
| F313-03 `ppmg-4cx6-95hh` | yes；无 patched version | chat message/history；auth/IDOR；read/delete route 缺少资源授权 | route dependency 与 sibling route 不一致，ID 直接到 message service | A；两 workspace service/HTTP test；low | 独立；共享 workspace ownership | protected chatflow/message sibling；按 verb+object+guard；high |
| F313-04 `hqvm-7539-v83j`, `27w2-26m5-x82c` | yes；前者 3.1.4 `bb773ffa`，后者未修复 | credential；IDOR；credential ID lookup/decrypt/use 未验证 workspace owner | attacker-controlled credential ID→load/decrypt/third-party enumeration | A；两个 workspace fixture；low | 独立；`credential use binds to workspace`；多 node/endpoint variants | guarded credential service；root discovery + coverage；high |
| F313-05 `vf3j-89vf-r697` | yes；无 patched version | SSO/invitation；auth bypass；email match 绕过 pending invite/token state | SSO callback 的 state transition 未要求有效 invite proof | A；调用 account-link helper；low | 独立；`identity link requires issuer+state proof` | normal invitation acceptance；按 transition/guard；high |
| F313-06 `cffm-583c-vffr` | yes；无 patched version | SSO identity；account takeover；仅 email 匹配、未绑定 IdP issuer/subject | callback identity tuple 被降为 email | A；两个 issuer 相同 email unit test；low | 独立；与 F05 共享 identity invariant 但根因不同 | provider-bound sibling；按 identity key；high |
| F313-07 `rpcc-gw54-mfgx` | yes；无 patched version | BullMQ dashboard；RBAC/tenant leak；只认证、不做 role/tenant scope | `/admin/queues` mount middleware 仅检查登录 | A；低权限 token request；low | 独立；`admin surface needs role+tenant` | admin-only routes；按 middleware chain；high |
| F313-08 `vcwp-f9rq-3887` + `vrr6` MCP executable variant | yes；3.1.4 `f5d16835`/`ababf4c8` | MCP/process；command execution；operator allowlist 仍允许 attacker-selected `npx` package/args | config→spawn command/args；package resolution 是执行 sink | B；stub child-process 或 harmless local package；medium | 独立；`all spawn paths share executable/arg/env policy`；与 F09 variants | fixed allowlist wrapper；按 command construction；high |
| F313-09 `x7x8-95gh-42xm` + `vrr6` cwd variant | yes；3.1.4 `e816d26a`/`ababf4c8` | MCP/path/process；cwd containment bypass；验证与实际 resolution 不一致 | user cwd→resolve/spawn，缺少 canonical containment | A；temp-dir symlink/relative test；low | 独立；与 F08 共享 process policy | safe path helper；按 resolution+boundary；high |
| F313-10 `gggp-6qmf-xwwc` | yes；3.1.4 `db8de568` | OpenAI Realtime；workspace auth；chatflow/tool lookup 不带 workspace | websocket/HTTP input flow ID→unscoped load→tool disclosure/execution | A；cross-workspace service test；low | 独立；传播 F01/F04 ownership 知识 | scoped normal chatflow route；按 lookup predicate；high |
| F313-11 `pwfj-wh95-7mwp` | yes；3.1.4 `4ea39120` | SQL Database Chain；RCE/command construction；不可信配置进入 shell/process/unsafe evaluator | node input/config→dangerous execution sink，可见缺失 policy | B；单 node/helper harness；medium | 独立；共享 dangerous-capability policy | safer SQL node/validator；按 source→sink；high |
| F313-12 `hx55-h48h-7rw9` | yes；3.1.4 `b98ff81b` | chat-model network；SSRF+secret exfil；baseURL 绕过统一 deny policy | user URL 与 provider credential 同时进入 HTTP client | B；mock DNS/HTTP transport；medium | 独立；`all egress paths use canonical URL policy` | protected model node；root + 8-node coverage；high |
| F313-13 `jrcq-qjw5-xx5q` | yes；3.1.4 `441c4e98` | CI workflow；script injection；event metadata 插入 shell | workflow expression→shell script | A；workflow expression inspection；low | 可独立，但不属于当前 HTTP API audit prompt | quoted/env sibling；known-unscored scope registry；high |
| F313-14 `jvx3-mjpw-r4gh` | yes；无 patched version | document-store history；auth/IDOR；history read/delete 不带 workspace | route ID→server-wide history service | A；two-workspace fixture；low | 独立；共享 ownership invariant | scoped document-store endpoints；按 object+guard；high |
| F313-15 `wpvf-4vfx-rgxm` | yes；3.1.4 `de3a9182` | MongoDBMemory；NoSQL/session isolation；session ID 类型未限制并进入 query | request sessionId→Mongo predicate，非 scalar 改变语义 | B；直接调用/query stub；low | 独立；`session identifier is typed scalar and owner-bound` | strict string validator；按 source/query effect；high |
| F313-16 `9cvr-5wv9-2gxr` | yes；3.1.4 `6c989ec8` | document loaders；SSRF；Cheerio/Playwright/Puppeteer 未走 `httpSecurity` | URL input→loader fetch，缺少共用 deny-list call | B；mock resolver/redirect；medium | 独立；与 F12 共享 egress invariant | protected web-fetch node；按 missing guard+sink；high |
| F313-17 `vrr6-xgc3-j99r` secret-export subfinding | yes；3.1.4 `096d2d4c` | export；credential exposure；export serialization 包含 variable plaintext | authenticated export→secret-bearing model→response | A；serializer unit test；low | 独立；omnibus advisory 拆分 | redacted credential export sibling；按 field provenance；high |
| F313-18 `vrr6-xgc3-j99r` dependency/sandbox subfinding | yes；3.1.4 `93c1abdd` 等 | sandbox/dependency；escape；是否可达依赖具体 package/runtime chain | source 显示 capability，但 exploitability 需复杂 runtime chain | C；完整 sandbox/runtime PoC；high | 不进入主 scored GT；与其他 sandbox advisory 去重待核 | version/lockfile evidence；known-unscored；high |
| F313-19 `xhxx-56g3-mx2r` | yes；3.1.4 `dbec8f9f` | TTS abort；auth/DoS；public abort route 可终止非本人 prediction | request identifier→global abort registry，无 owner proof | A；registry unit/两 request test；low | 独立；`operation handle binds to creator` | guarded cancellation routes；按 handle+guard；high |
| F313-20 `8gj2-2cvc-6xx7` | yes；3.1.4 `dbec8f9f` | TTS credential use；auth/capability exposure；public route 使用 private flow credential | public flow/request→credential resolution，无 public/owner check | A；stub TTS provider；low | 独立；共享 credential/capability invariant | normal prediction credential path；按 trust boundary；high |

## Flowise 3.1.2 delta

Vulnerable commit：`4114b3b506e7bbee155141175a2ba48e426919dd`。2,235 tracked files，约 1,660 source files。它继承上表 21 个 advisory，并额外受 32 个在 `3.1.3` 修复的 advisory 影响，总数 53。下表只列 delta；sandbox/validator family 的精确 cluster 边界仍是 freeze blocker。

| cluster family / advisory | affected / fix | region / root cause and static evidence | D / validation / cost | front / invariant / duplication | sibling / evaluator / leak |
|---|---|---|---|---|---|
| F312-D01 `9gvv`, `wg86`, `rqh4`, `3769` | yes；3.1.3，`a82edce8`/`3086cb7e` 等 | NodeVM/vm2 capability policy：Puppeteer allowlist、sandbox global 与 caller-supplied `nodeVMOptions` 扩权；source 可见 capability merge→VM | A/B；最小 VM harness；medium | 至少 2–3 roots，当前不能按 4 advisory 计 4 分；共享 `caller cannot widen sandbox` | fixed option construction；high |
| F312-D02 `x58f`, `52fh` | yes；3.1.3 `c79fe56a`/`d1e876d8` | Python validator normalization：method allow/deny 与 Unicode/attribute resolution 不等价 | B；validator unit payload；low | 1–2 roots，variant coverage；`normalize before policy` | accepted safe pandas calls；high |
| F312-D03 `vmv7`, `4j8x`, `5xvg`, `c5hr`, `4878`, `w7x8`, `x6vm` | yes；3.1.3 `c79fe56a`/`d1e876d8`/相关 backports | CSV/Airtable Python source construction 与 generated-code validation gaps；多入口共享但并非必然同一 root | B，部分 prompt-injection variant C；stub Pyodide/validator；medium | 至少 3 roots；必须做 function-level equivalence audit | safe literal/AST validation；root+coverage；high |
| F312-D04 `x3hf` | yes；3.1.3 | SQLite Record Manager；unsafe expression/query construction→execution sink | B；单 node harness；medium | 独立 execution front | parameterized/safe node；source→sink；high |
| F312-D05 `g32j` | yes；3.1.3 | TypeORM DataSource；attacker configuration reaches dynamic load/execute capability | B；constructor/helper test；medium | 独立；dangerous capability invariant | restricted DataSource creation；high |
| F312-D06 `p5w8` | yes；3.1.3 | flow deletion；resource type confusion，permission type 与 loaded object type 未一致 | A；service test；low | 独立 authz front | typed sibling delete；object type+guard；high |
| F312-D07 `wp74` | yes；3.1.3 | files；cross-workspace IDOR，list/delete repository query 未 scope | A；two-workspace test；low | 独立；ownership invariant | protected file route；high |
| F312-D08 `88pr` | yes；3.1.3 `571b5d62` | S3 Directory loader；object key→local path，无 canonical containment | A/B；temp-dir test；low | 独立 path front | `getSafeFilePath` sibling/patch；high |
| F312-D09 `2364` | yes；3.1.3 | organization default source；IDOR，customer/org predicate 缺失 | A；repository test；low | 独立；tenant invariant | scoped org endpoints；high |
| F312-D10 `g98q`, `xc48` | yes；3.1.3，MCP hardening commits | Custom MCP command/env policy；config 与 `npm_config_yes` 可扩大 install/exec | B；stub spawn/env test；medium | MCP process family，与 F313-08/09 做 root+variant | centralized wrapper；high |
| F312-D11 `chm3` | yes；3.1.3 | vector store credential IDOR；credential ID 未绑定 workspace | A；two-workspace test；low | F313-04 的 entry variant，不新增主 root 分 | credential service sibling；coverage only；high |
| F312-D12 `wch5` | yes；3.1.3 | OAuth metadata；cross-workspace credential metadata lookup | A；service test；low | 可独立 disclosure root，共享 credential invariant | redacted/scoped credential route；high |
| F312-D13 `c6xh` | yes；3.1.3 | network；IPv4-mapped IPv6 使 address classification 与 connect target 不一致 | B；pure URL/IP classifier unit；low | 独立 egress-policy root | canonical IP sibling；high |
| F312-D14 `fm2f` | yes；3.1.3 | execution update；mutation endpoint missing authorization | A；two-user execution test；low | 独立 authz front | guarded execution read/delete；high |
| F312-D15 `fr6g` | yes；3.1.3 | upsert history server-wide disclosure | A；repository query test；low | 与 F313-14 可能同 root/不同 endpoint，coverage 待定 | scoped history sibling；high |
| F312-D16 `r745` | yes；3.1.3 `da8b251a` | OAuth refresh；unauthenticated refresh URL/credential path造成 SSRF/secret exfil | B；mock HTTP transport；medium | 独立 OAuth+egress front | fixed provider endpoint allowlist；high |
| F312-D17 `6vh2` | yes；3.1.3 `23b997ee` | prediction override；ungated spread 允许 property injection/安全策略覆盖 | A；merge-helper unit；low | 独立；`caller cannot widen policy` | allowlisted config sibling；high |
| F312-D18 `gmmw` | yes；3.1.3 | Stripe subscription；billing object 未绑定 tenant/admin role | A；service test；low | 独立 billing authz front | admin-scoped sibling；high |
| F312-D19 `8r8h` | yes；3.1.3 | variables；RBAC permission 与 workspace resource query 不一致 | A；two-role test；low | 独立；tenant+secret invariant | credential/variable sibling；high |
| F312-D20 `qgvm` | yes；3.1.3 | OAuth token refresh；unauth endpoint 可取任意连接 token | A；handler/service test；low | 独立 capability exposure | authenticated owner refresh；high |
| F312-D21 `rwrp` | yes；3.1.3 `8842d52e` 等 | credential redaction；nested/alternate secret fields 未被 serializer/logger 清除 | A；serializer fixture；low | 独立 secret-handling front | common sanitizer；field-sensitive evaluator；high |

由于 D01–D03 仍包含多个可能独立或重复的 code-level roots，当前 `38 roots / 27 A / 10 B / 1 C` 只是 provisional selection estimate，不可直接作为正式 GT denominator。

## Langflow 1.8.1

Vulnerable commit：`a2e166048e4f39b5932f638440f8d82f1e40bd4e`。4,629 tracked files，约 3,708 source files。16 advisories，14 scored root causes；Smart Transform 的直接 unsafe-eval root 属 B，依赖外部模型成功遵循间接 prompt injection 的 exploitation variant 属 C/known-unscored。

| cluster / advisory | affected / fix | region / class / root cause | static evidence | D / validation / cost | front / invariant / duplication | sibling / evaluator / leak |
|---|---|---|---|---|---|---|
| L-01 `79ph-745m-6wxq`, `9whx-c884-c68q` | yes；`41d34b20...` create，`792808b1...` bulk delete | knowledge base/path；name→filesystem，无 canonical containment | path construction→mkdir/write/delete | A；temp-dir path test；low | 独立；同 containment root 的两个入口 | `_validate_kb_path_containment` patch；root+coverage；high |
| L-02 `jxw3-mjmx-3pqm` | yes；1.10.1 `094694d3...` | auth secret；weak key derivation；`random.seed(secret)` 生成 Fernet key | deterministic PRNG source→credential encryption | B；两次 derivation/decrypt unit；low | 独立 crypto front | SHA-256 derivation patch；high |
| L-03 `v8hw-mh8c-jxfc` | yes；exact fix TBD | Agentic Assistant；code execution；LLM output 的“validation”调用 `create_class/exec` | endpoint→model output→extract→validation→exec | B；fake model response/helper test；medium | 独立；`validation must not execute untrusted code` | compile/AST-only sibling；source→sink；high |
| L-04 `qrpv-q767-xqq2` | yes；1.9.1 `2c9f498d...` | responses/flow；IDOR；UUID branch 不应用 user predicate | UUID input→`session.get(Flow,id)`，与 name branch 对照 | A；two-user DB test；low | 独立 ownership front | endpoint-name scoped branch；high |
| L-05 `vwmf-pq79-vjvx`, `v5ff-9q35-q26f` | yes；`73b6612e...` 及后续 public-flow hardening | public playground；RCE；unauth route 接收 caller graph/code 而非只用 stored public flow | public body `data`→graph instantiate→exec | A；fake component graph helper；medium | 同 public execution root/variants | stored-flow-only sibling；root+coverage；high |
| L-06 `7grx-3xcx-2xv5` | yes；`04b4af6e...` | files/image；IDOR；download image 缺 `get_flow` auth/owner dependency | route dependency 与所有 sibling file routes 不同 | A；two-user route test；low | 独立；传播“auth is per-route”知识 | download/upload/list siblings；high |
| L-07 `g2j9-7rj2-gm6c` | yes；`d50eda2a...` | v2 storage；arbitrary write；multipart filename 绕过 URL-param validator，storage service 自身无 containment | filename→LocalStorage path/write | A；temp-dir upload helper；low | 独立 storage abstraction front | validated v1 path/containment patch；high |
| L-08 `rcjh-r59h-gq37` | yes；`07c3e67a71a61c0a5dd0bdbdb95601dd2f816628` | shareable playground/storage；file read；public execution path 解析本地/S3 文件但无 owner/public policy | public flow input→storage key/path→read | A；fake storage service；medium | 独立；共享 storage/ownership invariant | authenticated flow build sibling；high |
| L-09 `ccv6-r384-xp75` | yes；1.9.2 `cb06a666...` | BaseFileComponent/archive；file read/RCE；tar symlink/hardlink 与 extraction/path policy 不完备 | archive member→extract/read/execute | B；small archive fixture；low | 独立 archive front | reject-link regression tests；high |
| L-10 `x223-p2gf-v735` | yes；1.9.1 `99da6d05...` | deprecated upload；missing auth/limits/info leak | unauth route→save file；无 flow dependency/size guard | A；一两个 HTTP requests；low | 独立 upload boundary | modern upload route；high |
| L-11 `9fpm-3445-2vx4` | yes；1.10.3 `94859df3...`，main `1641b28f...` | Smart Transform；unsafe eval；LLM output 只做字符串格式检查后以 full builtins `eval` | prompt/data→model text→`eval`→invoke | B；stub model returning lambda；low；间接 prompt-following variant C | 独立 code-exec front | AST+restricted builtins patch；root scored，dynamic variant unscored；high |
| L-12 `w584-2h2r-2hvf` | yes；1.10.1 `e7c33dba...` | validate_code；RCE；编译后 `exec(FunctionDef)` 会执行 decorator/default expressions | request code→AST node→compile+exec | A；direct helper call；low | 独立；与 L03/L11 共享 no-exec validation invariant | compile-only patch；high |
| L-13 `cf6m-vc3m-7cgm` | yes；1.9.1 `cb6f7508...` | webhook；auth bypass；默认 `WEBHOOK_AUTH_ENABLE=False` 返回 flow owner | unauth request→owner identity→execute flow | A；settings/helper test；low | 独立 policy-default front | true-default/authenticated sibling；high |
| L-14 `4f6c-2vvp-gw82` | yes；1.10.3 `1f39a4b9...`/backport | MCP install；trust-header/locality bypass；无条件信任 leftmost XFF | header→client IP→local-only config write | A；TestClient header request；low | 独立 proxy-trust front | `request.client.host` default；high |

## n8n historical snapshot matrix

| snapshot | exact commit | relevant advisory set | simultaneous roots | note |
|---|---|---:|---:|---|
| 2.35.3 | `0dccd14a44a4e590b8641a12a95c9c76f8d525dc` | 28 + 1 documented capability | 23–25 provisional | 多 9 个 finding family，但 evaluator/search cost 最高 |
| 2.37.6 | `455dae49f98093929d770285524dce0726e47f14` | 19 + 1 documented capability | 18 | 与 2.38.1 基本同集；fix branch 为 2.37.7/2.38.2 |
| 2.38.1 | `ee7aca5845c9db2188150591eceebe20c1314643` | 19 + 1 documented capability | 18 | 推荐的 n8n scale snapshot；次日 2.38.2 clean pair |
| 2.39.5 | `8e7bbabd9a44798261332b686a7b1c111c3b5759` | 0 + 1 documented capability | 0 | reject；不能用仓库规模代替 fronts |

### n8n 2.38.1 / 2.37.6 shared census

Fixed security bundle：`8c8b059e03b73dcf30bcbf744702af9d844c14fe`；2.38.2 release：`7bd63f41c2f1f2bc2576c0728dbe2e68ed61e0f1`。单项 fix commit 尚未从 bundle 拆分，evaluator 必须依赖 vulnerable source + regression tests，而不是整个 diff。

| cluster / advisory | affected / fix | region / root cause and static evidence | D / validation / cost | front / invariant / duplication | sibling / evaluator / leak |
|---|---|---|---|---|---|
| N-01 `cw9w-vv67-hf73` | yes；2.38.2 bundle；metadata wording conflict retained | OAuth；refresh token 未绑定 consented resource，substitution 后签发别的 audience | A；token-service unit；low | 独立；`token binds to client+resource+grant` | authorization-code path；high |
| N-02 `fm93-2x43-6676`, `qgpw-8g46-w95v` | yes；2.38.2 bundle | Git sandbox；relative remote/base-dir 与 `branch.*.remote` 使 Git 解析到 sandbox 外 local repo | A；temp repos；medium | 同 Git path-policy root 的两个 variants | canonical repo allow policy；root+coverage；high |
| N-03 `6xcw-7xm6-48c6` | yes；2.38.2 | expression sandbox；shared builtin mutation/code-printer injection 越过隔离 | B；sandbox unit payload；medium | 独立 sandbox root | frozen/recreated globals；high |
| N-04 `hvrx-jc5j-pg3w` | yes；2.38.2 | source control；cross-project auth；push mutation 未限制 project/workflow/credential ownership | A；two-project service test；low | 独立 project-isolation front | guarded CRUD sibling；high |
| N-05 `pf83-w3f9-8m37` | yes；2.38.2 | OIDC；disabled feature endpoints 仍注册并签发 session | A；route/config test；low | 独立 feature-gate front | enabled-only registration sibling；high |
| N-06 `34ff-336r-5q23` | yes；2.38.2 | model search/network；domain restriction 未应用于 alternate endpoint | A；mock fetch；low | 独立 egress-policy front | guarded model endpoint；high |
| N-07 `7hgx-277f-7vmg` | yes；2.38.2 | subworkflow；caller policy bypass；Agent Tool path 未执行共享 authorization | A；policy helper test；low | 独立 execution auth front | normal subworkflow call；high |
| N-08 `j535-v25q-vx3q` | yes；2.38.2 | Git clone；ReDoS；default blocked-file regex 对 attacker path 非线性 | B；single regex timing/regression；low | 独立 availability front | bounded matcher patch；medium-high |
| N-09 `5m98-cgcr-xx3q` | yes；2.38.2 | GitHub trigger；webhook secret fail-open；422 reuse path 未保存 secret，verification 退化 | A；state-machine/service test；low | 独立 webhook invariant | fresh registration path；high |
| N-10 `f2cp-m7mv-8jpv` | yes；2.38.2 | Elasticsearch；path injection；identifier 未编码进入 request path | A；request-builder unit；low | 独立 path/HTTP front | encoded sibling node；high |
| N-11 `q5wm-mgqx-fv2f` | yes；2.38.2 | AI credential setup；SSRF；fetched content 提供的 probe URL 未重新验证 | B；mock fetch+redirect；medium | 独立 egress front | canonical URL guard；high |
| N-12 `679f-58pq-4v2c` | yes；2.38.2 | workflow summary；prototype pollution；attacker keys 写入普通 object/merge | B；direct function payload；low | 独立 data-structure front | null-prototype/map sibling；high |
| N-13 `cqr2-h44g-v75v` | yes；2.38.2 | project roles；PII disclosure；role endpoint 缺 per-project scope | A；two-project service test；low | 独立；共享 project isolation | scoped member-list sibling；high |
| N-14 `pq6c-vh67-xpm3` | yes；2.38.2 | log streaming/credential；decrypt generic-auth credential 无 owner/project check | A；two-project credential test；low | 独立；credential invariant | normal credential-use service；high |
| N-15 `65xw-2v52-jhxc` | yes；2.38.2 | active workflows；cross-user disclosure；query 缺 userId/project filter | A；repository test；low | 独立；project isolation | scoped list sibling；high |
| N-16 `35jj-42hp-8gmq` | yes；2.38.2 | approval gate；resume token reuse；token 未一次性绑定 gate/session | B；two websocket/helper resumes；medium | 独立 capability-token front | one-time token sibling；high |
| N-17 `hw8v-xxg5-vvvx` | yes；2.38.2 | expression sandbox；class-field sanitizer rebinding 保留执行能力 | B；sandbox unit payload；medium | 与 N03 共享 invariant、不同代码根因 | AST transform regression；high |
| N-18 `hh89-3r9w-qj3j` | yes；2.38.2 | OAuth DCR；unauth persistent resource creation 无 quota/lifecycle | A；一两个 local requests；low | 独立 resource-boundary front | authenticated/rate-limited creation；high |

2.35.3 的额外 9 个 advisory family 尚只完成 candidate-level 聚类，未达到 freeze 标准；在 source-level mapping 完成前，`23–25 roots / 18 A / 9 B / 1 C` 只能用于 scale selection，不能用于评分。

## Open WebUI 0.11.0

Vulnerable commit：`f9590b8017199e56d5e953657e6498e3cef1d246`。5,031 tracked files 中约 3,840 为 SVG，主要 source files 约 995。17 advisories、16 roots，均明确由 `0.11.1` 修复；fixed release commit `d3e8bf3405e848cfba377814d0aa7ba7290e414d`，但单 advisory fix commit 仍 TBD。

| cluster / advisory | affected / fix | region / root cause and static evidence | D / validation / cost | front / invariant / duplication | sibling / evaluator / leak |
|---|---|---|---|---|---|
| O-01 `wvm9-9g5j-623f` | yes；0.11.1，item commit TBD | OAuth role；token-exchange path 未执行 denied-role policy | A；auth helper test；low | 独立；role transition invariant | normal callback sibling；high |
| O-02 `34r3-9m95-vq73` | yes；0.11.1 | Azure channel；authenticated SSRF；server fetch 接受用户目标/平台 URL | B；mock transport；medium | 独立 egress front | common URL validator；high |
| O-03 `v39v-59xw-j98g` | yes；0.11.1 | calendar alerts；global integrity；非 numeric alert 值进入 shared suppression state | A；single function/request；low | 独立 global-state front | typed schema sibling；medium-high |
| O-04 `8r35-5x5r-hv74` | yes；0.11.1 | folders；cycle DoS；parent update 未检查 ancestor cycle | B；small graph fixture；low | 独立；graph acyclicity invariant | descendant/ancestor helper；high |
| O-05 `p78m-89r6-pgf7` | yes；0.11.1 | tool server；credential leak；bearer-auth request 仍转发 browser session cookies | A；request-builder test；low | 独立 credential-boundary front | cookie-less external fetch；high |
| O-06 `pcvc-8vrv-8q6w` | yes；0.11.1 | knowledge tool；ACL；tool retrieval 未重用 user-visible KB authorization | A；two-user/vector stub；low | 独立；resource visibility invariant | KB list/read sibling；high |
| O-07 `fmqh-xp37-5hr8` | yes；0.11.1 | channels/messages；IDOR；member可覆盖他人 message，update 未绑定 author | A；two-member service test；low | 独立 ownership front | normal edit/delete sibling；high |
| O-08 `wpmr-8h3q-fwj7` | yes；0.11.1 | OAuth identity；SQLite wildcard matching把 subject 当 pattern | A；DB lookup unit；low | 独立；issuer+subject exact invariant | exact comparison backend；high |
| O-09 `jmc6-2wr8-h3wj` | yes；0.11.1 | terminal iframe；same-origin XSS；sandbox 固定允许 `allow-same-origin` 与 attacker content 同源 | A；DOM/config inspection；low | 独立 browser boundary | cross-origin/no-same-origin sibling；high |
| O-10 `4v28-j6q3-5m4r` | yes；0.11.1 | Playwright loader；SSRF；只验证初始 DNS，connect 时可 rebind | B；controlled resolver stub；medium | 独立；egress invariant | pinned IP/revalidation helper；high |
| O-11 `3pf7-q2g3-wj28` | yes；0.11.1 | folders/chats；IDOR；chat completion mutation 接受他人 folder ID | A；two-user test；low | 独立；folder ownership | guarded folder CRUD；high |
| O-12 `wjwr-xfp9-r66p` | yes；0.11.1 | notes/role sync；stale authorization；admin demotion 不撤销 broad notes access | A；role-transition test；low | 独立；permissions follow current role | fresh-login/normal member sibling；high |
| O-13 `2724-6cpj-gf3v` | yes；0.11.1 | external knowledge；IDOR；delete cascade 未验证 connection owner/admin | A；two-user service test；low | 独立 knowledge ownership | read/update sibling；high |
| O-14 `3cgp-3cqx-j8w2`, `jqhh-cjmq-vmv6` | yes；0.11.1 | chat graph；cycle DoS；delete/history traversal 假设 tree 且无 visited set/cycle rejection | B；small cyclic graph fixture；low | 同 chat-graph root 的两个 reachable operations | bounded traversal/visited set；root+coverage；high |
| O-15 `3g9q-v48f-hh9w` | yes；0.11.1 | OIDC back-channel logout；unauth fetch DoS；每次请求触发 uncached issuer/network work | A；mock fetch request；low | 独立 unauth resource front | cached/authenticated OIDC path；medium-high |
| O-16 `5x7x-4c3c-qf5w` | yes；0.11.1 | generic fetch；SSRF；redirect target 不重新经过 host/IP policy | B；mock redirect；low | 独立；与 O02/O10 共享 egress invariant | no-redirect/revalidate sibling；high |

## Coordination opportunity 判定

| snapshot | independent fronts ≥4 | roots ≥4 | regions ≥4 | shared invariants 2–4+ | knowledge propagation | grep-resistant | verdict |
|---|---|---|---|---|---|---|---|
| Flowise 3.1.3 | yes，10–13 | yes，18 scored | yes，11 | tenant、credential、process、egress、session | 强 | yes | primary |
| Langflow 1.8.1 | yes，10–12 | yes，14 | yes，9 | route-local auth、storage containment、no-exec validation、proxy trust | 很强 | yes | primary |
| Open WebUI 0.11.0 | yes，11–14 | yes，16 | yes，8 | ACL、OAuth identity、egress、graph acyclicity | 强 | yes | primary/reserve |
| n8n 2.38.1 | yes，14–17 | yes，18 | yes，11 | project isolation、credential ownership、sandbox、egress、capability token | 强 | yes | security-qualified，budget-scale deferred |
| Flowise 3.1.2 | yes，18–24 | yes，provisional 38 | yes，16–18 | 同 3.1.3 加 sandbox normalization | 强，但重复聚类未闭合 | yes | scale-stress only |

## 冻结状态

- `freeze-ready after annotation`：Flowise 3.1.3。
- `requires fix-map completion`：Langflow 1.8.1、Open WebUI 0.11.0。
- `requires budget-scale calibration`：n8n 2.38.1。
- `requires root-equivalence audit`：Flowise 3.1.2、n8n 2.35.3。
- `reject`：n8n 2.39.5；当前无足够 simultaneous vulnerable roots。
