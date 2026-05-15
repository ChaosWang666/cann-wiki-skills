# Issue tracker: GitHub

本仓的 issue 和 PRD 都以 GitHub issues 形式存在。所有操作走 `gh` CLI。

## 约定

- **创建 issue**：`gh issue create --title "..." --body "..."`。多行 body 用 heredoc。
- **读取 issue**：`gh issue view <number> --comments`，用 `jq` 过滤 comments 并同时获取 labels。
- **列出 issues**：`gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`，按需加 `--label`、`--state` 等过滤。
- **评论 issue**：`gh issue comment <number> --body "..."`
- **加 / 去 label**：`gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **关闭**：`gh issue close <number> --comment "..."`

`gh` 在 clone 内执行时会自动从 `git remote -v` 推断仓库，不需要手动指定。

## 当 skill 说"发布到 issue tracker"时

创建一个 GitHub issue。

## 当 skill 说"拉取相关 ticket"时

运行 `gh issue view <number> --comments`。
