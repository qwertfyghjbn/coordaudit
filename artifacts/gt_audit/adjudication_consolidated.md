# 历史 unmatched candidate 裁决汇总（2026-09-21）

- 覆盖 cluster：40（源自 63 个 flowise repository-v1 runs 的 94 条 unmatched finding）
- 分类统计：{"validated_novel_tp": 11, "canonical_tp_overlap": 9, "false_positive": 17, "inconclusive": 2, "validated_novel_tp_conditional": 1}

以上是**历史 unmatched 分母**，分类之和为 40。机器可读合并表另纳入公开 issue #6687 的 UC41（不来自历史 run），所以 `adjudication_consolidated.json` 的跨来源候选宇宙为 41，统计为 inconclusive 3、其余分类不变。不得将 UC41 计为 94 条历史 finding 的 cluster。

裁决方法：condition-blind 独立静态复核（不读 run transcript，只读 snapshot 代码）；跨批冲突由主裁决人裁定并记录 lead_resolution。

| UC | 最终分类 | GT overlap | 严重度(若TP) |
|---|---|---|---|
| UC01 | validated_novel_tp | - | high（refresh：未认证跨租户 credential 变更；callback：medium-high 条件性覆写） |
| UC02 | validated_novel_tp | - | medium（私有 flow 反馈内容未认证泄露；写入为数据污染 low-medium） |
| UC03 | canonical_tp_overlap | R04_generic_credential_lookup_scope | high（未认证跨租户 credential 能力使用） |
| UC04 | validated_novel_tp | - | medium |
| UC05 | false_positive | - | low |
| UC06 | false_positive | - | - |
| UC07 | false_positive | - | low |
| UC08 | validated_novel_tp | - | medium |
| UC09 | inconclusive | KU02（NodeVM 依赖逃逸，known-unscored dynamic-dependent）同能力面 | high（若逃逸成立则宿主 RCE） |
| UC10 | validated_novel_tp | R17（document loader egress 无 URL policy，GHSA-9cvr）不变量同族；Unstructured 不在 R17 冻结 variant 集（Cheerio/Playwright/Puppeteer）内，判为新 variant 而非 canonical overlap | medium-high（与 R17 同级：内网探测/IMDS 面SSRF，响应进文档管道可能回显） |
| UC11 | false_positive | - | n/a（无跨越边界的路径） |
| UC12 | canonical_tp_overlap | R08_sso_email_only_identity | critical（账户接管） |
| UC13 | canonical_tp_overlap | R07_sso_invited_token_proof + R08_sso_email_only_identity | - |
| UC14 | canonical_tp_overlap | R01 (enterprise active-org binding；census 明确 SSO-config call chains 为 R01 variants) | medium（跨租户配置探测/操纵；非直接 secret 外泄） |
| UC15 | validated_novel_tp | - | medium（支付标识符跨租户泄露） |
| UC16 | canonical_tp_overlap | R01 (enterprise active-org binding) | high（任意组织元数据/计费标识跨租户篡改） |
| UC17 | canonical_tp_overlap | R01 (enterprise active-org binding；OrganizationUserController.update 即 census 指定的 variant anchor) | high（跨租户添加/改写/移除成员；ENTERPRISE 下 delete 连带软删用户与个人 workspace） |
| UC18 | canonical_tp_overlap | R01 (enterprise active-org binding；census 明确 role call chains 为 R01 variants) | high（跨租户删除角色，破坏目标租户 RBAC 结构） |
| UC19 | validated_novel_tp | none（与 R01 的 org-binding 谓词不同：User 实体无 organization 参数，缺失的是 permission check 本身） | medium-high（无授权建号 + 密码预占式账号接管前置；新建账号默认无 org/workspace，直接提权有限） |
| UC20 | canonical_tp_overlap | R01 (enterprise active-org binding；borderline：census 未逐条列举 workspace-user 链，但同谓词) | high（跨租户成员注入可实现完整租户接管） |
| UC21 | false_positive | - | low（hardening 残留） |
| UC22 | false_positive | - | none |
| UC23 | validated_novel_tp | none（R02 为用户密码序列化，R04-R06 为 credential lookup，均不覆盖 API key 材料泄露） | high（持久 bearer 凭证泄露给只读角色） |
| UC24 | false_positive | - | high |
| UC25 | false_positive | - | low |
| UC26 | validated_novel_tp_conditional | - | low |
| UC27 | validated_novel_tp | none（R15 为 routes/upsert-history 路由缺权限，属不同路由/不同 root；class-similar 但非同链） | medium-high（零权限文档注入/RAG 投毒；带 items 时跨 workspace 写入） |
| UC28 | validated_novel_tp | none（R03 为 chat-message 路由、R15 为 upsert-history 权限；documentstore 读取无 GT root 覆盖） | high（跨租户知识库内容检索/外泄） |
| UC29 | false_positive | - | none |
| UC30 | false_positive | - | medium |
| UC31 | false_positive | - | none |
| UC32 | false_positive | - | none |
| UC33 | false_positive | - | none |
| UC34 | false_positive | - | high |
| UC35 | false_positive | n/a | - |
| UC36 | validated_novel_tp | none（R09 为 BullMQ dashboard，属不同子系统） | high（宿主机容器执行/停摆；部署依赖性强） |
| UC37 | false_positive | - | medium |
| UC38 | canonical_tp_overlap | R20 | high |
| UC39 | false_positive | - | low（hardening） |
| UC40 | inconclusive | - | medium |

## 新 root 候选（validated_novel_tp）

UC01 OAuth2 免认证 credential 改写（callback+refresh）、UC02 feedback 免认证跨 flow 读写、UC04 get-upload-file 免认证跨租户文件读、UC08 dataset rows 跨 workspace 删除、UC10 Unstructured loader SSRF（R17 不变量同族新 variant）、UC15 organization read IDOR（Stripe 标识）、UC19 user 创建零权限、UC23 apikey 原文泄露给 apikeys:view、UC27 documentstore upsert/refresh 零权限、UC28 documentstore vector query 无 workspace 谓词、UC36 nvidia-nim 九路由零权限。

## 等价实现扩展（canonical_tp_overlap）

R01 += UC14/16/17/18/20；R04 += UC03（TTS body credentialId）；R07/R08 anchor 修复 += UC12/13；R17 += UC10（亦可作新 variant）；R20 += UC38（predictions isPublic）。

## 条件候选 / 不确定

UC26（净化后结构披露，conditional）、UC40（listenerId capability 错位，hardening）、UC09（NodeVM 同 KU02 能力面，known-unscored）。
