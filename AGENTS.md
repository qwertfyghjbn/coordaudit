# CoordAudit Repository Guidelines

## 项目范围

本仓库用于 CoordAudit：在固定 audit loop、模型、工具权限、输入可见性与全局预算下，比较 runtime coordination adapter。它不是原 `vuln-audit-system-eval` 的 canonical benchmark corpus，也不承载旧 `Architecture Attribution Experiment` 的结果。

## 核心因果约束

- `S`、`P`、`B`、`T` 必须使用同一 base audit prompt、模型配置、Agent-visible target、finding schema 和 team-level budget。
- `B` 只能暴露 generic persistent store；不得提供 message、task、claim、owner、leader、mailbox、lock、lease、CAS 或 protocol 示例。
- `T` 可以提供 typed task、atomic claim 和受记录的结果/消息；不得把这些能力泄给 B 或 P。
- hidden evaluator、ground truth、source case 标签和 provenance 不得进入 Agent mount、tool output 或 prompt。

## 迁移与测试

- 首次迁移只修复路径、provenance 和项目配置；不要同时重构 harness 行为。
- 修改 coordination、budget、sandbox、grader 或 event schema 后，至少运行 harness tests、repository smoke tests 与 S/P/B/T mock smoke。
- 运行产物写入 `experiments/emergent_coordination/runs/`，默认不提交。正式结果另存 versioned artifact/report，并记录 model、prompt、tool schema、budget 和 benchmark digest。

## 代码与文档

- Python imports 当前保留 `experiments.emergent_coordination` 以降低首次迁移风险；包名重构必须作为单独变更。
- 所有文档以中文为主；跨仓引用使用 remote、commit、case ID 与 hash，避免把 `/home/lqs/...` 当作可移植运行依赖。

## Agent skills

### Issue tracker

本仓库的 issue 与 PRD 使用 GitHub Issues：`qwertfyghjbn/coordaudit`。参见 `docs/agents/issue-tracker.md`。

### Triage labels

使用默认的五个 triage 标签。参见 `docs/agents/triage-labels.md`。

### Domain docs

本仓库为 single-context：根级 `CONTEXT.md` 与 `docs/adr/` 是领域语言和决策的来源。参见 `docs/agents/domain.md`。
