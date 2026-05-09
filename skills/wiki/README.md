# Wiki Skills

Skills for AscendC Kernel Wiki knowledge retrieval and session feedback.

| Skill | Purpose |
|-------|---------|
| cann-ask | MCP search by knowledge id, batch fetch top-3 contents, synthesize cited answers |
| session-upload | Upload session transcript (`.md`) into the ingest pipeline |

Both target the **v2** MCP Server (`wiki_search` / batch `wiki_get_page(ids)` / `wiki_submit_trajectory`). `wiki_get_index` is deprecated and not relied on by either skill.