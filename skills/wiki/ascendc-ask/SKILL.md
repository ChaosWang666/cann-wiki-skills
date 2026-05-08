---
name: ascendc-ask
description: "AscendC Wiki knowledge retrieval (human-facing). MUST use this skill (NOT direct MCP calls) when asking AscendC questions — provides intent classification, auto top-3 fetch, synthesis + inline citations. Trigger: `/ascendc-ask`."
---

# AscendC Ask Agent

Human-facing knowledge retrieval for AscendC Kernel Wiki via MCP Server. Finds relevant pages, fetches top-3 automatically, and synthesizes a cited answer.

> **Naming note**: this skill was previously called `wiki-query`. It was renamed to `ascendc-ask` because earlier versions of the AscendC-Kernel-Wiki MCP server had an internal `wiki-query` sub-agent dispatcher of the same name, and the two collided when both were active in one agent. v2 of the server has removed that internal dispatcher (retrievers are now invoked directly), but the rename is preserved as the public entry point so the human-facing trigger stays stable across server versions.

## Prerequisites

**MCP Server must be running** with the following tools available:

| Tool | Description |
|------|-------------|
| `wiki_search(query, tags?, type?, limit)` | Returns ranked summaries keyed by knowledge `id` (no internal paths exposed). Response: `{results: [{id, summary, tags, score, qValue}], total, warning?}` |
| `wiki_get_page(ids: list[str])` | **Batch** fetch full page content. Response: `{pages: [{id, frontmatter, content, qValue}], errors: [{id, error}]}` |
| `wiki_get_index()` | **[DEPRECATED]** — use `wiki_search` + `wiki_get_page` instead |
| `wiki_submit_trajectory(session_id, content)` | Persist a session transcript Markdown; uploaded path is determined by server `config.yaml` (`trajectory.uploaded_dir`) |

MCP endpoint: `http://localhost:3000/mcp` (streamable-http transport)

If MCP Server is not running, prompt user to start it first. To verify server status, try calling `wiki_search("test", limit=1)` or check port 3000.

## Activation (MUST trigger this skill, NOT direct MCP calls)

**CRITICAL**: When MCP tools (`mcp__ascendc-wiki__wiki_search`, `mcp__ascendc-wiki__wiki_get_page`) are available, **ALWAYS use the ascendc-ask skill instead of calling them directly**.

**Why skill is required (not direct MCP):**
- Intent classification → better search query formulation
- Auto top-3 fetch + synthesis → coherent multi-page answers
- Inline citation enforcement → traceable knowledge
- Trajectory logging → Q-Value feedback for retrieval improvement

**Direct MCP calls bypass these features → lower-quality answers.**

---

**Trigger ascendc-ask when:**
- User mentions "AscendC" / "Ascend C" in any question
- User asks about AscendC kernel development, operators, APIs, patterns
- User requests comparison (e.g., "ElementwiseSch vs manual pipeline")
- User requests how-to (e.g., "how to implement activation operator")
- User requests coverage (e.g., "which operators use reduction")
- User explicitly triggers `/ascendc-ask` or says "search wiki"

**Anti-pattern (DO NOT do this):**
```
# Wrong: agent discovers MCP tools via ToolSearch, then calls directly
ToolSearch("select:mcp__ascendc-wiki__wiki_search")
mcp__ascendc-wiki__wiki_search(query="conv2d", limit=5)  # ❌ bypasses skill
```

**Correct pattern:**
```
/ascendc-ask conv2d implementation  # ✅ triggers skill workflow
```

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

Server-side scoring is decided by the configured retriever mode (local / openai-api / claude-agent — set in server `config.yaml`); clients receive a single pre-blended `score`. **Don't pass `mode`** — it is server-internal.

Response shape (v2 schema):

```json
{
  "results": [
    {
      "id": "wiki_static_xxx_md",
      "summary": "...",
      "tags": ["vector", "basic_api"],
      "score": 0.85,
      "qValue": 0.73
    }
  ],
  "total": 15,
  "warning": "..."
}
```

Notes:
- `results[]` carries **no `path`, no `frontmatter`, no `title`** — those are server internals. Title/frontmatter become available only after `wiki_get_page(ids)`.
- `warning` is optional; present on retriever failure / empty query. **Surface it to the user verbatim** instead of silently retrying or downgrading.
- `score` is already blended (mode-dependent); sort by it desc and don't re-rank.

### Phase C: Batch Fetch Pages

Single batch call (do **not** loop per-id):

```python
ids = [r["id"] for r in results[:3]]
wiki_get_page(ids=ids)
```

Returns:

```json
{
  "pages": [
    {
      "id": "wiki_static_xxx_md",
      "frontmatter": {...},
      "content": "Full markdown content (frontmatter section included)",
      "qValue": 0.73
    }
  ],
  "errors": [
    {"id": "wiki_static_yyy_md", "error": "id not found"}
  ]
}
```

- `frontmatter` is server-parsed (no need to re-parse).
- `errors[]` is a soft-failure list — bad ids do not block the rest of `pages[]`. Mention unresolved ids in the answer if they reduce coverage.

**Strategy**:
- Default: top-3 ids
- If results < 3: fetch all available
- For SYNTHESIS/COMPARISON with ≥3 results: optionally expand to top-5

### Phase D: Synthesize Answer

Combine multi-page info into structured answer:

**Citation rules (MUST follow):**
1. **Every fact must cite its source inline** — format: `[Source: <id>]` using the knowledge id returned by `wiki_get_page`
2. Place citation immediately after the fact/section, not at the end
3. For multi-source facts: `[Source: <id1>, <id2>]`

**Example (correct):**
```markdown
### Alignment Requirements [Source: wiki_static_ascendc_guide_api_vector-compute_md]

DataCopy transfer length must be **32-byte aligned**.

| Requirement | Description |
| DataCopy length | 32B aligned |
```

**Example (incorrect):**
```markdown
### Alignment Requirements

DataCopy transfer length must be **32-byte aligned**.

---

**References:**
- wiki_static_ascendc_guide_api_vector-compute_md
```

**Content structure:**
- COMPARISON → comparison table (each row cites its source)
- HOW-TO → step list + code examples (cite source for each step)
- Use tables, code blocks, structured format
- End with References summary listing `<id> — <frontmatter.title>` per page (titles come from `wiki_get_page`, not search)

### Phase E: Trajectory Upload Prompt

At answer end, include a brief footer:

```
💡 Use `/session-upload` to save this session to Wiki
```

Upload itself is owned by the `session-upload` skill — see its SKILL.md for the full pipeline. The tool signature is:

```
wiki_submit_trajectory(
  session_id: "<session id>",
  content:    "<entire Markdown body of the converted transcript>"
)
```

Only two parameters: `session_id` and `content` (no `source` / `transcript` aliases). The server stores the bytes verbatim at `<server config trajectory.uploaded_dir>/{session_id}.md`; downstream sanitization / extraction is handled by the knowledge engine's monitor process, not this tool.

## Output Format

```markdown
## Answer

[Structured content with [Source: <id>] citations]

---

**References:**
- <id1> — <frontmatter.title from wiki_get_page>
- <id2> — ...
- <id3> — ...

💡 Use `/session-upload` to save this session to Wiki
```

## Notes

- **MCP Server required** — Prompt user to start if not running
- **Cite by id** — Use the knowledge `id` returned by `wiki_get_page`; do not invent paths
- **Don't fabricate** — If `results[]` is empty or `warning` is set, state clearly; do not guess
- **Auto top-3 batch** — Single `wiki_get_page(ids=[...])` call, no per-id loop
- **Q-Value managed by MCP** — No local tracking
- **No manual file-back** — v2 has removed in-skill wiki page authoring; to feed answers back into the wiki, use `/session-upload` and let `knowledge_engine`'s ingest pipeline handle it
- **Graceful degradation** — If MCP unreachable, prompt error without blocking local functions

## Error Handling

| Scenario | Handling |
|----------|----------|
| MCP Server not running | Prompt startup command |
| `wiki_search` empty results or response carries `warning` | Surface the warning text to user verbatim; suggest keyword/tag adjustment |
| `wiki_get_page` partial failures | List unresolved ids from `errors[]`; continue synthesis from `pages[]` |
| `wiki_submit_trajectory` failed | Surface server `message` payload to user (don't swallow it) |
| Network timeout | "Timeout, check MCP Server status" |