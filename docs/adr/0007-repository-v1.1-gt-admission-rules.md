# ADR-0007：repository-v1.1 GT 纳入规则（2026-09-21）

状态：**本版本规范性规则，已冻结**。适用于 `flowise_3_1_3_repository_v1_1` 的 GT 内容裁决；不改变 repository-v1 的任何资产或历史得分。

## TM4：不可猜 capability

服务端铸造、高熵、保密、不可枚举的 capability token 可以独立构成访问控制边界；缺少传统登录态本身不构成漏洞。仅当代码证据显示 token 可预测、泄露、scope 错误、错误复用，或持有 token 后可越过其授予的权限时，才可裁为 positive。必须记录 token 的铸造、传播、消费及其授权对象；不能把普通资源 UUID 自动当作 capability，也不能仅凭 UUID 可猜测作出 positive。

本版本裁决：UC25、UC33 为 false positive；UC40 保留 inconclusive/known-unscored（未见 listenerId 泄露路径）；R22/UC02 保留 positive，因为 chatflow UUID 并非授予读取全部反馈或改写任意反馈的 bearer capability，反馈接口也未按 chatId/反馈属主限制作用域。R23/UC04 保留 positive，但仅限已知 chatflowId、chatId、fileName 的访问场景：三者是资源定位符，代码未铸造、验证或绑定独立的文件读取 capability；不得宣称这些值可枚举或无需获知。UC24 的白名单前缀绕过仍为 false positive。

## TM6：净化后的结构披露

sanitized output 只有在跨越明确的 confidentiality boundary，且具体泄露安全敏感信息或形成现实攻击链时才纳入 positive。普通 schema、节点结构和不敏感配置 metadata 的披露不足以自动构成漏洞。裁决必须指出残留的具体敏感字段或可达攻击链，不能用“可能含敏感信息”代替证据。

UC26：`getSinglePublicChatbotConfig` 可查询 private flow，但 `sanitizeFlowDataForPublicEndpoint` 删除 credential 引用、password/file/folder 输入和认证 header；现有裁决仅证明残留结构/普通配置，没有指出具体敏感字段或攻击链。本版本 **不纳入 canonical GT**，在 known-unscored registry 记为 `excluded_under_TM6`。将来若发现具体敏感字段，需要在后续版本重新裁决。

## CR1：agent-run-derived GT 与循环性

历史 agent run 派生的候选，经 condition-blind adjudication、独立代码级验证，以及 source→sink/guard 证据三项通过后，可以进入未来版本 GT；来源必须持久标记为 `agent_run_derived`。产生该候选的历史 run 保留 evaluator-v1 original score，允许在新 evaluator 完成后作只读 retrospective rescore。该 retrospective score 只陈述 finding 与新版 GT 的关系，**不能**作为 independent benchmark generalization evidence。独立泛化证据须来自 GT 冻结后未参与构造的全新 runs。

## 版本边界

上述规则从 repository-v1.1 GT 内容冻结起生效。修改纳入规则或重新裁决 UC26/UC40，须创建后续 GT 版本并重算身份摘要。
