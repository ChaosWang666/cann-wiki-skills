# cann-wiki-skills

CANN Wiki knowledge-retrieval and trajectory-upload skills for Claude Code and
OpenCode. The user-facing skills live under `skills/wiki/`. The MCP server,
knowledge engine, and AscendC Kernel Wiki content live in a sibling
`AscendC-Kernel-Wiki` repo (treated as read-only upstream from this repo).

## Agent skills

### Issue tracker

GitHub Issues at `qianbi1999/cann-wiki-skills`, accessed via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical five-role vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context repo: one `CONTEXT.md` + `docs/adr/` at the root. See `docs/agents/domain.md`.
