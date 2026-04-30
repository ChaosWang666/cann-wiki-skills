---
name: wiki-query
description: "AscendC Wiki knowledge retrieval — Semantic search via MCP, auto-fetch top-3 pages, synthesize answers with citations. Use when asking AscendC kernel/operator/API questions."
---

# Wiki Query Agent

Retrieve knowledge from AscendC Kernel Wiki via MCP Server. Uses semantic vector search to find relevant pages, automatically fetches top-3 for synthesis.

## Prerequisites

**MCP Server must be running** with the following tools available:

| Tool | Description |
|------|-------------|
| `wiki_search(query, tags?, type?, limit)` | Semantic search, returns pages ranked by similarity + Q-Value |
| `wiki_get_page(path)` | Get full page content with frontmatter |
| `wiki_get_index()` | Get wiki index (optional, for navigation) |
| `wiki_submit_trajectory(session_id, transcript, source)` | Upload session transcript for feedback |

MCP endpoint: `http://localhost:3000/mcp` (streamable-http transport)

If MCP Server is not running, prompt user to start it first. To verify server status, try calling `wiki_get_index()` or check port 3000.

## Activation

When user:
- Asks about AscendC kernel development, operators, APIs, patterns
- Requests comparison analysis (e.g., "ElementwiseSch vs manual pipeline")
- Requests how-to guides (e.g., "how to implement a new activation operator")
- Requests coverage queries (e.g., "which operators use reduction pattern")
- Explicitly triggers `/wiki-query` or mentions "search wiki", "query knowledge base"

## Input

$ARGUMENTS

## Workflow

### Phase A: Intent Classification

| Type | Pattern | Example |
|------|---------|---------|
| LOOKUP | Single fact lookup | "What is GELU's formula?" |
| SYNTHESIS | Multi-page synthesis | "What sync mechanisms exist in AscendC?" |
| COMPARISON | Compare analysis | "ElementwiseSch vs manual implementation?" |
| HOW-TO | Operation guide | "How to implement a new activation operator?" |
| COVERAGE | Coverage query | "Which operators use reduction pattern?" |

### Phase B: MCP Search

Call MCP `wiki_search`:

```
wiki_search(
  query: "<user question or keywords>",
  tags: ["optional tag filter"] | null,
  type: "optional type filter" | null,
  limit: 3
)
```

Returns results ranked by `0.7 × similarity + 0.3 × qValue`:

```json
{
  "results": [
    {
      "path": "guide/concepts/programming-model.md",
      "title": "Programming Model",
      "type": "concept",
      "tags": ["multi_core"],
      "summary": "...",
      "source": "...",
      "qValue": 0.73,
      "similarity": 0.85
    }
  ],
  "total": 15
}
```

### Phase C: Batch Fetch Pages

Automatically call `wiki_get_page` for top-3 results:

```
for each path in results[:3]:
  wiki_get_page(path)
```

Returns full content:

```json
{
  "path": "...",
  "frontmatter": {...},
  "content": "Full markdown content",
  "source": "...",
  "qValue": 0.73
}
```

**Strategy**:
- Default: top-3 pages
- If results < 3: fetch all available
- For SYNTHESIS/COMPARISON with ≥3 results: optionally expand to top-5

### Phase D: Synthesize Answer

Combine multi-page info into structured answer:

**Citation rules (MUST follow):**
1. **Every fact must cite its source inline** — format: `[Source: wiki/path/to/page.md]`
2. Place citation immediately after the fact/section, not at the end
3. For multi-source facts: `[Source: wiki/path1.md, wiki/path2.md]`

**Example (correct):**
```markdown
### 对齐要求 [Source: wiki/static/ascendc/guide/api/vector-compute.md]

DataCopy 搬运长度必须 **32 字节对齐**。

| 要求 | 说明 |
| DataCopy 长度 | 32B 对齐 |
```

**Example (incorrect):**
```markdown
### 对齐要求

DataCopy 搬运长度必须 **32 字节对齐**。

---

**References:**
- wiki/static/ascendc/guide/api/vector-compute.md
```

**Content structure:**
- COMPARISON → comparison table (each row cites its source)
- HOW-TO → step list + code examples (cite source for each step)
- Use tables, code blocks, structured format
- End with References summary (optional, but inline citations are mandatory)

### Phase E: File-Back Decision

Evaluate if answer should be persisted as new wiki page. File-back if **≥3 criteria met**:
- [ ] Synthesized 3+ wiki pages
- [ ] Produced novel comparison/analysis
- [ ] Question likely to be repeated (high generality)
- [ ] Fills gap in wiki coverage
- [ ] Provides guide not covered by existing practice pages

If file-back:
- Determine page type (concept/practice/pattern)
- Create wiki page with frontmatter
- Update `wiki/index.md` and `wiki/log.md`

### Phase F: Trajectory Upload Prompt

At answer end, include a brief footer:

```
💡 Use `/session-upload` to save this session to Wiki
```

When user invokes session-upload skill, call MCP `wiki_submit_trajectory`:

```
wiki_submit_trajectory(
  session_id: "<UUID v4>",
  transcript: "<JSONL conversation history>",
  source: "<agent name>"
)
```

**Transcript format** (exclude tool return results):

```jsonl
{"role":"user","content":"..."}
{"role":"assistant","content":"...","tool_calls":["wiki_search","wiki_get_page"]}
{"role":"tool","name":"wiki_search","args":{"query":"...","limit":3}}
{"role":"tool","name":"wiki_get_page","args":{"path":"..."}}
```

Trajectory stored at `raw/sessions/uploaded/{session_id}.jsonl`.

## Output Format

```markdown
## Answer

[Structured content with [Source: wiki/path/to/page.md] citations]

---

**References:**
- wiki/path1.md
- wiki/path2.md
- wiki/path3.md

💡 Use `/session-upload` to save this session to Wiki
```

## Notes

- **MCP Server required** — Prompt user to start if not running
- **Cite specifically** — Page path + Q-Value, not vague "from Wiki"
- **Don't fabricate** — If wiki has no relevant content, state clearly
- **Auto top-3** — No manual selection, improves efficiency
- **Q-Value managed by MCP** — No local tracking
- **Transcript excludes tool returns** — Only conversation + tool metadata
- **Graceful degradation** — If MCP unreachable, prompt error without blocking local functions

## Error Handling

| Scenario | Handling |
|----------|----------|
| MCP Server not running | Prompt startup command |
| wiki_search empty results | "No relevant content", suggest keyword adjustment |
| wiki_get_page failed | "Invalid path or deleted" |
| wiki_submit_trajectory failed | "Network error, retry later" |
| Network timeout | "Timeout, check MCP Server status" |