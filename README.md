# CoordAudit

`CoordAudit`（Coordination Architecture Attribution for Multi-Agent Vulnerability Auditing）是一个独立的多 Agent 漏洞审计协调架构归因项目。

## 当前状态

已完成第一次行为保持迁移：CoordAudit runtime、`repository_pilot_v0`、hidden evaluator、测试和专属研究文档已复制到本项目。原仓库的 source 副本将在本迁移验证完成后以跨仓指针替代。

- 原仓库：`/home/lqs/llm_audit_system_learning`
- 本地新项目：`/home/lqs/coordaudit`
- 迁移候选清单：[`MIGRATION_INVENTORY.md`](MIGRATION_INVENTORY.md)
- 原仓库文档修改清单：[`SOURCE_DOCS_UPDATE_CHECKLIST.md`](SOURCE_DOCS_UPDATE_CHECKLIST.md)

## 为什么独立成仓

这个拆分合理，且建议现在完成，原因如下：

1. 原仓库的核心是漏洞审计 benchmark、系统学习结果和 canonical 报告；CoordAudit 已经包含可执行 harness、协调条件、预算、事件、grader 和专用 repository benchmark，生命周期不同。
2. 协调条件本身是实验 treatment。独立版本控制可以冻结 prompt、tool schema、coordination adapter、budget 与 evaluator，降低和 benchmark 维护混在一起造成的归因污染。
3. 现有 `experiments/`、`docs/research/` 和 N=4 规划尚未被原仓库 Git 跟踪；现在拆分比产生正式结果后再拆成本低。
4. 新项目可以让 Agent runtime 成为一个更深的 module：调用者只通过统一实验配置使用它，S/P/B/T adapter 位于明确 seam 后面，从而提高 locality 和复现实验的 leverage。

## 范围

本项目应拥有：

- CoordAudit agent runtime、model gateway、tools 与 coordination adapters；
- `repository_pilot_v0` 及其隐藏 evaluator；
- S/P/B/T/M 条件的 manifests、运行日志、指标和报告；
- CoordAudit 自己的研究说明、N=4 pilot 计划和后续 ADR。

本项目不应拥有：

- 原仓库完整 `datasets/`；
- OpenAnt、DeepAudit、IRIS 的实现、结果或脚本；
- 已收口的 `Architecture Attribution Experiment` 报告与 artifacts；
- 原仓库 `canonical_results.tsv`；
- `.env_deepseek`、密钥、Agent 本地状态或 Python cache。

## 迁移原则

- 先复制并验证，再从原仓库删除；不得直接移动后再修复。
- 首次迁移保持行为不变，不同时重构 harness interface。
- `repository_pilot_v0` 必须自包含；它只通过 provenance 引用上游 case ID，不在运行时读取兄弟仓库的 `datasets/`。
- hidden ground truth 与 Agent-visible target 保持物理隔离。
- 原仓库中旧的 `Architecture Attribution Experiment` 保持不动；CoordAudit 是另一条研究线。
- 正式迁移前后分别冻结文件哈希，并运行同一组 mock、grader、leak 和 repository semantic tests。

## 已完成验证

迁移后，在本项目根执行并通过：

```text
python3 -m unittest discover -s experiments/emergent_coordination/tests -t . -v  # 35 tests
cd experiments/emergent_coordination/repositories/repository_pilot_v0 && python3 -m unittest discover -s tests -v  # 6 tests
```

此外，`single`、`parallel`、`raw_blackboard`、`structured_team` 四个 N=4 mock CLI 均已完成运行。它们只验证迁移后的生命周期和 adapter 可达性，不构成安全效果或 coordination 效果结论。

## 下一步 gate

首次迁移保持现有 Python package 布局；N=4 P0 加固（OS sandbox、调用前预算许可、可关联事件、严格 grader/dedup 与 coordination 指标）必须作为后续独立变更实施。
