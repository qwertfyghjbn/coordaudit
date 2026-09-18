# Issue Tracker

本仓库的 issue 与 PRD 位于 GitHub 仓库 `qwertfyghjbn/coordaudit` 的 GitHub Issues，使用 `gh` CLI 操作。

## 约定

- 创建：`gh issue create --title "..." --body "..."`。
- 查看：`gh issue view <number> --comments`，并同时读取标签。
- 列出：`gh issue list --state open`，需要时按标签过滤。
- 评论：`gh issue comment <number> --body "..."`。
- 修改标签：`gh issue edit <number> --add-label "..."` 或 `--remove-label "..."`。
- 关闭：`gh issue close <number> --comment "..."`。

技能要求“发布到 issue tracker”时，创建 GitHub issue；要求“读取相关 ticket”时，使用 `gh issue view <number> --comments`。
