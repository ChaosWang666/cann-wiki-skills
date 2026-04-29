---
name: setup-ascendc-wiki
description: "Setup MCP connection for AscendC Wiki skills. Run before first use of wiki-query or session-upload, or if those skills fail due to missing MCP tools."
---

# Setup AscendC Wiki Skills

Scaffold the MCP configuration that wiki-query and session-upload skills require.

This is a prompt-driven skill. Explore, present what's missing, confirm with user, then write.

## Prerequisites Check

Before setup, check:

1. **MCP Server running?**
   - Try calling `wiki_get_index()` MCP tool
   - Or check if port 3000 is listening: `curl -s http://localhost:3000/mcp` (returns MCP protocol info)
   - If not running, prompt user to start it first

2. **Agent MCP config exists?**
   - OpenCode: `.opencode/opencode.json`
   - Claude Code: `.mcp.json` or `claude_desktop_config.json`
   - If missing, create it

3. **MCP tools available?**
   - Required tools: `wiki_search`, `wiki_get_page`, `wiki_get_index`, `wiki_submit_trajectory`
   - After config, verify tools appear in agent's MCP tool list

## Process

### Step 1: Check MCP Server Status

Verify MCP Server is running:

1. Check if port 3000 is listening:
   ```bash
   curl -s http://localhost:3000/mcp
   ```
   (Returns MCP protocol info if running)

2. Or try calling MCP tool directly (after agent config):
   ```
   wiki_get_index()
   ```

**If server not running**:
- Ask user: "MCP Server is not running. Do you have the MCP Server repo?"
- Provide startup command:
  ```bash
  EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5 \
  python server.py --retriever local --port 3000
  ```
- Wait for user to start server before continuing

### Step 2: Detect Agent Type

Check which agent the user is using:

| Agent | Config file location |
|-------|---------------------|
| OpenCode | `.opencode/opencode.json` in workspace |
| Claude Code (Desktop) | `claude_desktop_config.json` in app support |
| Claude Code (CLI) | `.mcp.json` in project root |
| Cursor | MCP settings in editor |

Use glob/read to check which exists.

### Step 3: Present Configuration

Show user the configuration needed:

**For OpenCode** (`.opencode/opencode.json`):
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "ascendc-wiki": {
      "type": "remote",
      "url": "http://localhost:3000/mcp",
      "enabled": true
    }
  }
}
```

**For Claude Code CLI** (`.mcp.json`):
```json
{
  "mcpServers": {
    "ascendc-wiki": {
      "url": "http://localhost:3000/mcp"
    }
  }
}
```

**For Claude Desktop** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "ascendc-wiki": {
      "command": "python",
      "args": ["path/to/mcp-server/server.py", "--retriever", "local"],
      "env": {
        "EMBEDDING_MODEL": "BAAI/bge-small-zh-v1.5"
      }
    }
  }
}
```

Explain each option:
- **Remote mode**: Connect to already-running MCP server
- **Local mode**: Claude Desktop auto-starts MCP server on launch

### Step 4: Confirm and Write

Ask user:
- Which agent they're using
- Which mode (remote/local)
- MCP Server path if using local mode

Then write the appropriate config file.

### Step 5: Verify

After config, prompt user to:
1. Restart their agent
2. Verify MCP tools appear: `wiki_search`, `wiki_get_page`, `wiki_submit_trajectory`

Show success message:

```markdown
## Setup Complete

- MCP connection configured
- Config file: {path}
- Mode: remote/local

### Available Tools
- wiki_search(query, tags?, type?, limit)
- wiki_get_page(path)
- wiki_submit_trajectory(session_id, transcript, source)

### Next Steps
- Restart your agent to load MCP config
- Try: "What is AscendC programming model?"
```

## Notes

- **MCP Server required** — Cannot use wiki skills without running server
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
- **wiki-query** — Knowledge retrieval via MCP
- **session-upload** — Trajectory upload via MCP