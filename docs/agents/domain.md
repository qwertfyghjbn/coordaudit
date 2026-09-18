# 领域文档布局

本仓库采用 single-context 布局。

在探索或修改实现前，先阅读：

- 根级 `CONTEXT.md`，其中定义 CoordAudit 的术语与因果约束；
- `docs/adr/` 中与当前工作相关的 ADR。

输出中的领域概念必须采用 `CONTEXT.md` 的术语，特别是 coordination condition、hard team call budget、Agent-visible target、work front、hidden evaluator 与 infrastructure-invalid run。若建议与 ADR 冲突，必须明确指出冲突，而非静默覆盖。
