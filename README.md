# AscendC Wiki Skills

LLM Agent skills for AscendC Kernel Wiki knowledge retrieval and session trajectory upload.

## Quick Install

```bash
npx skills@latest add qianbi1999/ascendc-wiki-skills
```

Select skills you want and target agent.

## Skills Included

| Skill | Description | Trigger |
|-------|-------------|---------|
| **wiki-query** | Semantic search Wiki via MCP, auto-fetch top-3 pages, synthesize answers | AscendC questions, `/wiki-query` |
| **session-upload** | Upload session transcript for experience feedback loop | `/session-upload`, "upload trajectory" |

## Prerequisites

### MCP Server Required

Both skills require MCP Server running with these tools:

| Tool | Purpose |
|------|---------|
| `wiki_search` | Semantic search |
| `wiki_get_page` | Get full page content |
| `wiki_submit_trajectory` | Upload session transcript |

### MCP Server Setup

```bash
# Local embedding mode (recommended)
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5 \
python server.py --retriever local --port 3000
```

Configure your agent's MCP connection:

**Claude Code** (`.mcp.json`):
```json
{
  "mcpServers": {
    "ascendc-wiki": {
      "url": "http://localhost:3000/mcp"
    }
  }
}
```

**OpenCode** (`opencode.json`):
```json
{
  "mcp": {
    "ascendc-wiki": {
      "type": "remote",
      "url": "http://localhost:3000/mcp",
      "enabled": true
    }
  }
}
```

## Usage

### wiki-query

Ask AscendC questions:
```
"What is AscendC programming model?"
"How to implement GELU operator?"
"ElementwiseSch vs manual pipeline?"
```

### session-upload

Upload trajectory:
```
/session-upload
```

## Workflow

```
User Question
     ↓
wiki-query skill
     ↓
MCP wiki_search → top-3 pages
     ↓
MCP wiki_get_page (batch)
     ↓
Synthesized Answer
     ↓
/session-upload
     ↓
session-upload skill
     ↓
MCP wiki_submit_trajectory
     ↓
raw/sessions/uploaded/{uuid}.jsonl
```

## Structure

```
ascendc-wiki-skills/
├── .claude-plugin/
│   └── plugin.json       # Skill list for installer
├── skills/
│   └── wiki/
│       ├── wiki-query/
│       │   └── SKILL.md
│       └── session-upload/
│           └── SKILL.md
├── README.md
└── LICENSE
```

## License

MIT