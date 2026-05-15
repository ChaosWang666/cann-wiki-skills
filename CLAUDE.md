# cann-wiki-skills

面向 Claude Code 和 OpenCode 的 CANN Wiki 知识检索与轨迹上传 skills。面向用户的 skill 位于 `skills/wiki/`。MCP server、knowledge engine 和 AscendC Kernel Wiki 内容位于相邻的 `AscendC-Kernel-Wiki` 仓（对本仓而言是只读上游）。

## Agent skills

### Issue tracker

GitHub Issues 位于 `qianbi1999/cann-wiki-skills`，通过 `gh` CLI 访问。详见 `docs/agents/issue-tracker.md`。

### Triage labels

五个角色的规范化标签词汇表（`needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human`、`wontfix`）。详见 `docs/agents/triage-labels.md`。

### Domain docs

单 context 仓：根目录一份 `CONTEXT.md` + `docs/adr/`。详见 `docs/agents/domain.md`。
