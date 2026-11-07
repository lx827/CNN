# Issue 跟踪器：GitHub

本仓库的 issue 和 spec 存放在 GitHub Issues 中，所有操作使用 `gh` CLI。

## 约定

- **创建 issue**：`gh issue create --title "..." --body "..."`。多行正文用 heredoc。
- **读取 issue**：`gh issue view <number> --json number,title,body,labels,comments`。
- **列出 issue**：`gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`，配合 `--label` 和 `--state` 过滤。
- **设为父 issue 的子 issue**：`gh issue create --parent <parent> ...`，或事后 `gh issue edit <parent> --add-sub-issue <child>`（`gh` 2.94+）。旧版 `gh`：`gh api --method POST repos/<owner>/<repo>/issues/<parent>/sub_issues -F sub_issue_id=<child-db-id>`（数据库 id）。不支持子 issue 时，在子 issue 正文顶部写 `Part of #<parent>`。
- **评论**：`gh issue comment <number> --body "..."`
- **添加 / 移除标签**：`gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **关闭**：`gh issue close <number> --comment "..."`

仓库从 `git remote -v` 推断；在 clone 内运行时 `gh` 自动识别。

## Pull requests 作为分诊入口

**PRs as a request surface: no.** _（若本仓库将外部 PR 视为功能请求，改为 `yes`；`/triage` 会读取此标志。）_

设为 `yes` 时，PR 与 issue 使用相同的标签和状态，用 `gh pr` 等价命令：

- **读取 PR**：`gh pr view <number> --comments`，`gh pr diff <number>` 看 diff。
- **列出待分诊的外部 PR**：`gh api --paginate 'repos/{owner}/{repo}/pulls?state=open' --jq '.[] | select(.author_association | IN("OWNER","MEMBER","COLLABORATOR") | not) | {number, title, author: .user.login, author_association, labels: [.labels[].name]}'`。
- **评论 / 打标签 / 关闭**：`gh pr comment`、`gh pr edit --add-label`/`--remove-label`、`gh pr close`。

GitHub 的 issue 和 PR 共用一个编号空间，`#42` 可能是任一种：先用 `gh pr view 42`，失败再 `gh issue view 42`。

## 当 skill 说 "publish to the issue tracker"

创建一个 GitHub issue。

## 当 skill 说 "fetch the relevant ticket"

按上文 **读取 issue** 执行。

## Wayfinding 操作

供 `/wayfinder` 使用。**map** 是一个 issue，其 **child** issue 作为工单。

- **Map**：一个标签为 `wayfinder:map` 的 issue，正文含 Notes / Decisions-so-far / Fog。`gh issue create --label wayfinder:map`。
- **子工单**：作为 GitHub sub-issue 挂到 map 上（见上文）。sub-issue 不可用时，把子项加入 map 正文的任务列表，并在子工单正文顶部写 `Part of #<map>`。标签：`wayfinder:<type>`（`research`/`prototype`/`grilling`/`task`）。认领后把工单 assign 给驱动的开发者。
- **Blocking**：GitHub 原生 issue 依赖（UI 可见的权威表示）。添加依赖：`gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`，其中 `<blocker-db-id>` 是阻塞方的数据库 id（`gh api repos/<owner>/<repo>/issues/<n> --jq .id`，不是 `#number` 也不是 `node_id`）。GitHub 通过 `issue_dependencies_summary.blocked_by` 报告（仅开放阻塞者，实时门槛）。依赖不可用时，回退为子工单正文顶部的 `Blocked by: #<n>, #<n>` 行。所有阻塞者关闭后工单才解除阻塞。
- **Frontier 查询**：列出 map 的开放子工单（`gh issue list --state open`，限定 map 的 sub-issue / 任务列表），去掉有开放阻塞者（`issue_dependencies_summary.blocked_by > 0` 或 `Blocked by` 行中有开放 issue）或有 assignee 的；按 map 顺序取第一个。
- **认领**：`gh issue edit <n> --add-assignee @me`，这是会话的第一个写操作。
- **解决**：`gh issue comment <n> --body "<answer>"`，然后 `gh issue close <n>`，最后把上下文指针（gist + 链接）追加到 map 的 Decisions-so-far。
