# 0006. Repository-v1 以静态安全推理为主，只要求针对性本地验证

## 状态

Accepted

## 决策

Repository-v1 的 Agent 任务边界是 evidence-grounded repository audit：静态跨文件程序理解和安全推理是主任务，当可利用性依赖一个关键运行时语义时，Agent 可执行最小的 targeted local validation。正式 scored ground truth 主要由 Static-primary 与 Static-plus-validation finding 构成；Dynamic-dependent finding 原则上只进入 known-unscored registry 或后续动态实验。Agent 成功完整复现不是 TP 的必要条件，hidden evaluator 应允许 source/sink/guard、affected object、trust boundary、exploitation reasoning 与 patch/safe-sibling 对照形成的冻结静态证据进行确定性匹配。

## 理由

强制每个 finding 提供 executable oracle 会把实验重心从 runtime coordination 下的 repository security audit 转向 exploitation、构建环境与外部服务编排，并系统性排除可由源码充分证明的授权、租户隔离与信任边界缺陷。纯静态模式匹配又会弱化 hypothesis 验证、反证、修正和证据交接这些 coordination opportunity。静态优先与针对性验证的边界保留了两者，且对 S/P/B/T/M 使用同一任务和工具能力。

## 后果

- Benchmark census 必须把候选 finding 分为 Static-primary、Static-plus-validation 和 Dynamic-dependent，并单独记录验证费用。
- Advisory、CVE 和 reachable entry 必须按 root cause 聚类；主评分以 independent semantic finding 为单位，variant/coverage 另行记录。
- Agent reproduction claim 与 evaluator verification 继续分离；targeted reproduction 可提高 evidence strength，但不自动产生 TP。
- Target 选择只使用 condition-blind 属性，不得根据哪个仓库更容易让某个 coordination condition 表现更好进行筛选。
