---
name: setup-cann-wiki
description: "Setup MCP connection for AscendC Wiki skills. Run `/setup-cann-wiki` before first use of cann-ask or session-upload."
---

# Setup AscendC Wiki Skills

Scaffold the MCP configuration that cann-ask and session-upload skills require.

This is a prompt-driven skill. Explore, present what's missing, confirm with user, then write.

## Prerequisites Check

Before setup, check:

1. **MCP Server running?**
   - Try calling `wiki_search("test", limit=1)` MCP tool (a no-op probe)
   - Or check if port 3000 is listening: `curl -sI http://localhost:3000/mcp | head -3` (401/406 are healthy — they mean the streamable-http endpoint is up but the bare request is missing MCP headers)
   - If not running, prompt user to start it first

2. **Agent MCP config exists?**
   - OpenCode: `.opencode/opencode.json`
   - Claude Code: `.mcp.json` or `claude_desktop_config.json`
   - If missing, create it

3. **MCP tools available?**
   - Required v2 tools: `wiki_search`, `wiki_get_page` (batch by `ids`), `wiki_submit_trajectory`
   - `wiki_get_index` still exists but is **[DEPRECATED]** — do not depend on it for health checks or page navigation
   - After config, verify tools appear in agent's MCP tool list

## Process

### Step 1: Check MCP Server Status

Verify MCP Server is running:

1. Check if port 3000 is listening:
   ```bash
   curl -sI http://localhost:3000/mcp | head -3
   ```
   401 / 406 are healthy responses — they mean the streamable-http endpoint is up.

2. Or try calling an MCP tool directly (after agent config):
   ```
   wiki_search("test", limit=1)
   ```

**If server not running**:
- Ask user: "MCP Server is not running. Is the AscendC-Kernel-Wiki repo available?"
- Confirm the repo's `<repo_root>/config.yaml` has `search.mode` set (`local` / `openai-api` / `claude-agent`) — v2 reads business config (mode / model / api_key) only from `config.yaml`; CLI no longer accepts `--retriever` and no `EMBEDDING_MODEL` env is honored.
- Provide startup command:
  ```bash
  # In AscendC-Kernel-Wiki repo root (where wiki/ and raw/ exist)
  cd mcp-server
  IS_SANDBOX=1 python server.py --port 3000 --host 0.0.0.0

  # Non-root users can omit IS_SANDBOX=1
  ```
- Wait for user to start server before continuing

### Step 2: Detect Agent Type

Check which agent the user is using:

| Agent | Config file location | Easiest install |
|-------|---------------------|-----------------|
| OpenCode | `.opencode/opencode.json` in workspace | Edit JSON (see Step 3) |
| Claude Code (CLI) | `.mcp.json` in project root | **`claude mcp add` one-liner** (preferred) |
| Claude Code (Desktop) | `claude_desktop_config.json` in app support | Edit JSON (see Step 3) |
| Cursor | MCP settings in editor | Editor UI |

**Quick detection signals**:
- `command -v claude` → Claude Code CLI is installed
- `command -v opencode` → OpenCode CLI is installed
- File at `.opencode/opencode.json` → OpenCode workspace
- File at `.mcp.json` → Claude Code project already has MCP config
- Running inside Claude Code? Check `~/.claude/projects/<pwd-with-slashes-as-dashes>/` exists

Prefer the agent the user is currently invoking the skill from.

### Step 3: Present Configuration

Show user the configuration needed:

**For OpenCode** (`.opencode/opencode.json`):
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "cann-wiki": {
      "type": "remote",
      "url": "http://localhost:3000/mcp",
      "enabled": true
    }
  }
}
```

**For Claude Code CLI** — preferred one-liner (writes `.mcp.json` for you):

```bash
# Project scope (commits to repo via .mcp.json)
claude mcp add --transport http --scope project cann-wiki http://localhost:3000/mcp

# Or user scope (cross-project, lives in user settings)
claude mcp add --transport http --scope user cann-wiki http://localhost:3000/mcp
```

Equivalent hand-written `.mcp.json` if the user prefers to edit JSON directly:
```json
{
  "mcpServers": {
    "cann-wiki": {
      "type": "http",
      "url": "http://localhost:3000/mcp"
    }
  }
}
```

After running the command (or saving the file), restart your agent (`/exit`) and verify with:
```bash
claude mcp list           # should show cann-wiki as connected (Claude Code)
```

**For Claude Desktop** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "cann-wiki": {
      "command": "python",
      "args": ["path/to/AscendC-Kernel-Wiki/mcp-server/server.py", "--port", "3000"],
      "env": {
        "IS_SANDBOX": "1"
      }
    }
  }
}
```

Notes:
- v2 takes business config (search mode / model / api key) from `<repo_root>/config.yaml` — **do not** add `--retriever` to args or `EMBEDDING_MODEL` to env; both were removed.
- `IS_SANDBOX=1` is only needed for root deployments; non-root users can drop it.

Explain each option:
- **Remote mode**: Connect to already-running MCP server (recommended)
- **Local mode**: Claude Desktop auto-starts MCP server on launch (requires full path to server.py)

### Step 4: Confirm and Write

Ask user:
- Which agent they're using
- Which mode (remote/local)
- MCP Server path if using local mode

Then write the appropriate config file.

### Step 5: Mandatory Restart

**CRITICAL: User MUST restart their agent after config.**

Even if `claude mcp list` shows "Connected", MCP tools will NOT work until restart.

Tell user explicitly:
```
## ⚠️ 配置完成，必须重启！

配置文件已写入，但 MCP 工具需要重启才能生效。

### 必须操作
1. **退出当前 agent 会话**：输入 `/exit`（OpenCode 和 Claude Code 都支持）
2. **重新启动 agent**
3. 验证 MCP 工具可用：
   - Claude Code：运行 `/mcp` 应显示 cann-wiki
   - OpenCode：MCP 工具应出现在工具列表中

### 不重启的后果
- `/mcp` 显示 "No MCP servers configured" (Claude Code)
- wiki 工具无法调用

**请现在执行 `/exit` 重启**。
```

**DO NOT** claim setup is complete without restart.

## Notes

- **MCP Server required** — Cannot use wiki skills without running server. This skill assumes the server speaks v2 schema (`results[]` keyed by `id`, no `path`; `wiki_get_page` takes `ids: list[str]`).
- **Server-side config drives behavior** — Search mode / embedding model / API keys are in `<repo_root>/config.yaml` only; client-side switches are gone in v2.
- **Config is client-level** — Not stored in skill, stored in agent config
- **One setup per agent** — Re-run only if switching agents or MCP endpoint changes
- **Server and client separate** — MCP server runs independently, agent connects to it

## Error Handling

| Scenario | Handling |
|----------|----------|
| MCP Server not running | Prompt startup command, wait for user |
| Config file exists | Ask to update or skip |
| Unknown agent type | Ask user to specify |
| Config write fails | "Permission denied, check write access" |

## Integration

After setup, these skills will work:
- **cann-ask** — Knowledge retrieval via MCP
- **session-upload** — Trajectory upload via MCP