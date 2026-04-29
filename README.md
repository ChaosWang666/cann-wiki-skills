# ascendc-wiki-skills

LLM Agent skills for AscendC Kernel Wiki knowledge retrieval and session trajectory upload.

## Quick Install

```bash
npx skills@latest add qianbi1999/ascendc-wiki-skills
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

### Option 1: Remote Mode (Recommended)

Start MCP Server separately:
```bash
# In MCP Server repo
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5 \
python server.py --retriever local --port 3000
```

Then run `/setup-ascendc-wiki` in your agent. Setup will configure agent to connect to `http://localhost:3000/mcp`.

### Option 2: Local Mode (Claude Desktop only)

Claude Desktop can auto-start MCP server on launch. Setup skill will configure this if you choose local mode.

## Usage Flow

```
1. Install skills: npx skills@latest add qianbi1999/ascendc-wiki-skills
2. Run setup: /setup-ascendc-wiki
3. Start MCP Server (if remote mode)
4. Restart agent
5. Use wiki-query: "What is AscendC programming model?"
6. Upload trajectory: `/skills` → `session-upload`
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