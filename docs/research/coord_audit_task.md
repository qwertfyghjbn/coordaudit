# CoordAudit：多智能体漏洞审计协调架构归因

## 状态

`CoordAudit` 是 **Coordination Architecture Attribution for Multi-Agent Vulnerability Auditing** 的简称，即“多智能体漏洞审计协调架构归因”。

当前处于研究设计阶段：先行调研已完成，尚未开始正式实验，未纳入 `canonical_results.tsv`，也不应被表述为已有系统评测结论。

## 研究任务目标

在同一代码审计 harness、模型、工具权限、输入可见性和全局资源预算下，比较不同运行时协调架构对多智能体漏洞审计的影响。核心不是证明“多 Agent 更强”，而是归因下列差异：

- independent parallel 带来的额外采样收益；
- runtime coordination 带来的任务分工、知识传播和重复劳动减少；
- 共享状态导致的错误采纳、群体锚定和通信开销；
- raw generic shared store 是否会被同质审计 Agent 自发用来形成 mailbox、任务认领、owner、leader、delegation 和 verification 等协议；
- 工程化结构化 backlog / atomic claim 相对自发协议的收益与 scaffold tax。

## 拟比较条件

所有条件复用同一 Agent loop；只替换 coordination adapter。

| 条件 | 最小定义 |
|---|---|
| `S1` | 单个强审计 Agent。 |
| `P16/P32` | 多 Agent 独立并行，运行中不通信，只在末端聚合。 |
| `M16/M32` | 预设 manager-worker / star，由 manager 分派。 |
| `R16` | 固定角色 SOP，例如 Explorer → Tracer → Reproducer → Reviewer。 |
| `G16` | 固定稀疏通信图。 |
| `B16/B32` | 仅有 generic persistent KV/filesystem；不提供 message、task、claim、owner 或 protocol schema。 |
| `T16/T32` | structured shared backlog，具有 durable task、atomic claim、ownership 与 peer messaging。 |

`B` 应至少区分两种处理：`B-opaque` 不告知其他 Agent 或共享语义；`B-aware` 只告知存在持久共享存储，但不提供协议、目录约定或协调 API。两者都不得泄入 `T` 的 task/claim 语义。

## 初始实验边界

- 主实验使用 **fixed global token/tool budget**：manager、worker、reviewer、通信、重试和失败调用均计入同一总预算，用以识别计算效率而非新增算力。
- 补充实验使用 **fixed per-agent budget**：用于评估真实横向扩容的规模回报，不与主实验的 coordination gain 混称。
- `repository-v1` 以有效并行 work front 而非仅漏洞数定规模。N16 初始目标为 12–20 条 work front，包含 hidden vulnerabilities、near misses 与共享语义依赖；至少两个 repository-level benchmark。
- 第一阶段优先完成 `S1/P16/M16/R16/B16/T16` 的 N16 对照；确认 task supply、trace 与预算计量有效后，再扩展 `G16` 和 N32。
- Agent 在盲评阶段不得读取 `ground_truth.json`、`case.yaml` 标签或答案型 README；沿用仓库既有的 clean-input 和冻结评测约束。

## 一等结果与解释边界

除了 verified target finding / false positive / near miss 外，记录 task claim、ownership conflict、duplicate work、知识与错误的 lineage、独立复现、handoff、通信量、token/tool 消耗、leader concentration 与协议形成时间。

不得把以下现象直接解释为 coordination gain：更多总 inference compute、额外模型调用、预设的 manager/role/claim API、共享源码可得性差异，或仅来自最终 majority vote 的 improvement。

## 与现有工作和仓库的关系

- 完整先行调研、prior-art collision、taxonomy、实施参考和实验设计建议见 [multi_agent_coordination_prior_art.md](multi_agent_coordination_prior_art.md)。
- 这是继现有 `Architecture Attribution` 后的**独立研究任务**，但它不是该已收口实验线的追溯性结果。
- 任何未来正式结果应在冻结 protocol、seed、预算 manifest 与 benchmark 版本后，作为本项目新的实验线进入 `reports/`；在此之前，本文档只记录研究目标和设计边界。
