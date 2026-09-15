# 原仓库文档与配置修改清单

目标仓库：`/home/lqs/llm_audit_system_learning`

状态：待实际迁移完成后执行。本清单本身不授权删除源文件。

## P0：迁移完成后必须修改

| 文件 | 修改内容 | 原因 |
|---|---|---|
| `README.md` | 从“本仓库正在设计 CoordAudit”与仓库树中移除本地 `experiments/emergent_coordination`；改为外部项目链接和一句范围说明 | 防止读者把两个仓库当作同一运行/结果线 |
| `CONTEXT.md` | 保留 `CoordAudit`、`Raw Shared-Store Condition` 作为跨仓术语，但注明 protocol、implementation 与当前结果由独立项目维护；旧 `Architecture Attribution Experiment` 三个术语保持不变 | 既保住历史语境，又把实现权威来源移到正确仓库 |
| `docs/research/coord_audit_task.md` | 迁出后替换为短 tombstone，链接新项目对应文档；远端 URL 未确定前不要提交本机绝对路径 | 保持旧引用可解释，同时确立新权威来源 |
| `docs/research/multi_agent_coordination_prior_art.md` | 迁出后替换为短 tombstone 或从原仓库删除，并更新所有入口 | 避免两份长期漂移的研究设计文档 |
| `N4_PILOT_PLAN.md` | 迁入 `docs/plans/`；原仓库删除或只留指针 | 计划描述的是新项目 harness，不属于 benchmark corpus |
| `docs/adr/0002-separate-coordaudit-repository.md`（新增） | 记录 CoordAudit 独立成仓的决策、范围、跨仓 provenance 和不迁移旧 Architecture Attribution 的理由 | 防止未来再次把两条归因线合并 |

## P0：配置而非 docs

| 文件 | 修改内容 | 原因 |
|---|---|---|
| `.gitignore` | 删除 `experiments/emergent_coordination/runs/*` 规则；相同规则在新项目建立 | 原仓库不再拥有该 runtime output |
| Git 状态/提交说明 | 在删除前记录源文件 hashes；迁移提交明确列出新项目 remote/commit | 当前 `experiments/` 与研究文档未跟踪，仅记原仓库 HEAD 无法复现 |

## P1：检查后修改

| 文件/范围 | 动作 | 判断标准 |
|---|---|---|
| `reports/README.md` | 如其中声称所有未来实验都写入本仓库 `reports/`，增加外部实验项目例外 | 只在实际存在冲突表述时修改 |
| `llm_audit_system_learning_method.md` | 增加 benchmark export/provenance 的跨仓规则 | 新项目未来需要从本仓库导入新 benchmark 时再补 |
| `agent_eval_learning_rules.md` | 保持原盲评原则；如新项目复制了适配版本，增加“权威来源/适用范围”说明 | 避免两边规则无版本关系地漂移 |
| `reports/cross_system/overall_report.md` | CoordAudit 形成冻结正式结果后再增加外部链接；pilot 阶段不加入结论 | feasibility 不得进入 canonical 结论 |
| `reports/cross_system/canonical_scope_manifest.md` | 仅在未来明确纳入 CoordAudit 正式结果时修改 | 当前无需修改 canonical scope |
| `reports/cross_system/canonical_results.tsv` | pilot 阶段明确不修改 | 廉价模型 N=4 feasibility 不是正式性能结果 |

## 明确不修改

以下内容属于已经完成的 `Architecture Attribution Experiment`，不是 CoordAudit：

```text
docs/adr/0001-architecture-attribution-as-independent-experiment-line.md
reports/systems/architecture-attribution/**
artifacts/architecture_attribution/**
```

ADR 0001 不应被 CoordAudit 的拆仓决定覆盖或改写。新 ADR 只记录新的仓库级决策。

原仓库 `AGENTS.md` 已明确该仓库是 benchmark 与文档工作区、不是应用代码仓库；在 CoordAudit runtime 移出后这段描述反而更准确，因此无需为本次拆分强制修改。新项目应另建适合可运行 Python 实验仓库的 `AGENTS.md`。

## 新项目需要新增或改写的 docs

| 文件 | 内容 |
|---|---|
| `README.md` | 项目范围、S/P/B/T 因果区别、安装与真实命令、artifact 约定 |
| `CONTEXT.md` | CoordAudit、Raw Shared-Store Condition、Structured Task-Claim Condition、Matched Experiment Block 等权威术语 |
| `AGENTS.md` | Python 实验仓库规范、hidden oracle 隔离、B/T capability 禁止泄漏、测试命令 |
| `docs/adr/0001-separate-coordaudit-repository.md` | 新项目为何独立成仓，以及与原 Architecture Attribution 的关系 |
| `docs/research/coord_audit_task.md` | 从原仓库迁入并改写路径/状态 |
| `docs/research/multi_agent_coordination_prior_art.md` | 从原仓库迁入，成为唯一权威副本 |
| `docs/plans/N4_PILOT_PLAN.md` | 从原仓库迁入并改写 CLI、路径与输出位置 |

## 链接更新策略

1. 新项目尚无远端时，原仓库 docs 不写 `/home/lqs/coordaudit` 作为永久链接。
2. 建立远端后，tombstone 指向固定仓库路径；重要 provenance 再记录 commit hash。
3. 新项目引用原 benchmark 来源时使用原仓库 remote + commit + case ID + content hash，不使用易失的本机绝对路径。
4. 删除源文档前运行一次链接和文本引用扫描：

```text
rg -n 'CoordAudit|emergent_coordination|N4_PILOT_PLAN|multi_agent_coordination_prior_art' .
```

## 完成判据

- 原仓库 README、CONTEXT、AGENTS 不再把 CoordAudit runtime 表述为本仓库资产。
- 原仓库仍完整描述并保留旧 Architecture Attribution 结果。
- CoordAudit 的权威设计文档只有新项目一份。
- canonical results 在 pilot 阶段不发生语义变化。
- 所有跨仓引用都带稳定 remote；关键 benchmark provenance 额外带 commit/hash。
