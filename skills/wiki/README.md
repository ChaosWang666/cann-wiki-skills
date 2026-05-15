# Wiki Skills

面向 AscendC Kernel Wiki 的知识检索与会话反馈 skills。

| Skill | 用途 |
|-------|------|
| cann-ask | 按知识 id 调 MCP 检索，批量 fetch top-3 内容，合成带引用的答案 |
| session-upload | 把会话轨迹（`.md`）送入 ingest 管线 |

两个 skill 都对接 **v2** MCP Server（`wiki_search` / 批量 `wiki_get_page(ids)` / `wiki_submit_trajectory`）。`wiki_get_index` 已弃用，两个 skill 都不依赖它。
