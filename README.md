# ascendc-wiki-skills

LLM Agent skills for AscendC Kernel Wiki knowledge retrieval and session trajectory upload.

## Quick Install

```bash
npx skills@latest add qianbi1999/ascendc-wiki-skills
```

安装时会让你选择 agent 平台（多选），默认选中 Claude Code / OpenCode / Codex。

**指定特定 agent：**
```bash
# 只安装到 Claude Code
npx skills@latest add qianbi1999/ascendc-wiki-skills -a claude-code

# 只安装到 OpenCode
npx skills@latest add qianbi1999/ascendc-wiki-skills -a opencode

# 安装到多个 agent
npx skills@latest add qianbi1999/ascendc-wiki-skills -a claude-code,opencode
```

Select **setup-ascendc-wiki** first, then wiki-query and session-upload.

## Important: Run Setup First!

**Before using wiki-query or session-upload, run `/setup-ascendc-wiki` to configure MCP connection.**

The setup skill will:
1. Check if MCP Server is running
2. Detect your agent type (OpenCode/Claude Code/Cursor)
3. Create MCP configuration file
4. Verify MCP tools are available

## Skills

| Skill | Description | Must run setup first |
|-------|-------------|---------------------|
| **setup-ascendc-wiki** | Configure MCP connection | No (run this first) |
| **wiki-query** | Semantic search Wiki via MCP | Yes |
| **session-upload** | Upload session transcript | Yes |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Your Agent (OpenCode/Claude Code/Cursor)                   │
│  ├── MCP config: .opencode/opencode.json or .mcp.json       │
│  └── Skills: setup-ascendc-wiki, wiki-query, session-upload │
└───────────────────────────┬─────────────────────────────────┘
                            │ MCP Protocol
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  MCP Server (separate repo)                                  │
│  ├── Port: localhost:3000                                   │
│  ├── Tools: wiki_search, wiki_get_page, wiki_submit_trajectory │
│  └── Retriever: local (sentence-transformers) or llm        │
└─────────────────────────────────────────────────────────────┘
```

**Key insight**: MCP Server and Skills are **separate**:
- **MCP Server** runs independently (user manages it)
- **Skills** are installed in agent (tell agent how to use MCP tools)
- **Setup skill** bridges them by configuring MCP connection

## MCP Server Setup

The MCP Server must be running before agent can use it.

### Start MCP Server

在 AscendC-Kernel-Wiki 仓库根目录启动：

```bash
cd mcp-server
IS_SANDBOX=1 python server.py --port 3000 --host 0.0.0.0
```

启动成功输出：
```
[mcp 2026-04-29 23:55:00] 服务启动: 0.0.0.0:3000 heartbeat=1800s
```

**注意：**
- `IS_SANDBOX=1`：root 用户必须显式声明，否则 Claude CLI 拒绝执行
- 非 root 用户可省略 `IS_SANDBOX=1`
- 服务必须在仓库根（与 `wiki/`、`raw/` 平级）启动

## Usage Flow

```
1. Install skills: npx skills@latest add qianbi1999/ascendc-wiki-skills
2. Start MCP Server: cd mcp-server && IS_SANDBOX=1 python server.py --port 3000
3. Run setup: /setup-ascendc-wiki
4. Restart agent
5. Use wiki-query: "What is AscendC programming model?"
6. Upload trajectory: /session-upload
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| wiki_search not found | Run `/setup-ascendc-wiki` first |
| MCP connection failed | Check MCP Server is running, try calling `wiki_get_index()` |
| Config not loaded | Restart agent after setup |
| Skills not triggering | Check skill activation keywords |

## Structure

```
ascendc-wiki-skills/
├── .claude-plugin/
│   └── plugin.json
├── skills/
│   └── wiki/
│       ├── setup-ascendc-wiki/
│       │   └── SKILL.md          ← Run this first
│       ├── wiki-query/
│       │   └── SKILL.md
│       └── session-upload/
│           └── SKILL.md
├── README.md
└── LICENSE
```

## License

MIT