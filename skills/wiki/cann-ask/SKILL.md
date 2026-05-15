---
name: cann-ask
description: "CANN Wiki 知识检索（面向人类提问）。当用户询问 AscendC 相关问题时，必须使用本 skill（不要直接调 MCP），它负责意图分类、自动 fetch top-3、合成答案并附内联引用。触发命令：`/cann-ask`。"
---

# CANN 知识问答 Agent

面向人类提问的 AscendC Kernel Wiki 知识检索，通过 MCP Server 找到相关页面，自动 fetch top-3，并合成带引用的答案。

## 前置条件

**MCP Server 必须已启动**，提供以下工具：

| 工具 | 说明 |
|------|------|
| `wiki_search(query, tags?, type?, limit)` | 返回按知识 `id` 索引的排序摘要（不暴露内部路径）。响应：`{results: [{id, summary, tags, score, qValue}], total, warning?}` |
| `wiki_get_page(ids: list[str])` | **批量** 获取完整页面内容。响应：`{pages: [{id, frontmatter, content, qValue}], errors: [{id, error}]}` |
| `wiki_get_index()` | **【已弃用】** —— 改用 `wiki_search` + `wiki_get_page` |
| `wiki_submit_trajectory(session_id, content)` | 持久化一次 session 轨迹 Markdown；上传路径由 server `config.yaml` 的 `trajectory.uploaded_dir` 决定 |

MCP endpoint: `http://localhost:3000/mcp`（streamable-http 传输）

如果 MCP Server 未启动，提示用户先启动。要验证状态，可调用 `wiki_search("测试", limit=1)` 或检查 3000 端口。

## 触发方式（必须走本 skill，不要直接调 MCP）

**重要**：当 MCP 工具（`mcp__cann-wiki__wiki_search`、`mcp__cann-wiki__wiki_get_page`）可用时，**始终通过 cann-ask skill 调用，不要直接调它们**。

**为什么必须走 skill：**
- 意图分类 → 更好地构造检索 query
- 自动 fetch top-3 + 合成 → 跨页面连贯回答
- 强制内联引用 → 知识可追溯
- 轨迹日志 → 为检索改进提供 Q-Value 反馈

**直接调 MCP 会绕过这些能力 → 回答质量更差。**

---

**触发 cann-ask 的场景：**
- 用户在任何问题中提到 "AscendC" / "Ascend C"
- 用户询问 AscendC kernel 开发、算子、API、模式
- 用户请求对比（如"ElementwiseSch 与手工流水线的差异"）
- 用户请求 how-to（如"如何实现一个新的激活算子"）
- 用户请求覆盖范围（如"哪些算子用了 reduction"）
- 用户显式输入 `/cann-ask` 或说"搜 wiki"

**反面模式（不要这么做）：**
```
# 错误：用户问"卷积怎么实现"，agent 把中文意图翻成英文 query 后直接调 MCP
ToolSearch("select:mcp__cann-wiki__wiki_search")
mcp__cann-wiki__wiki_search(query="conv2d implementation", limit=5)  # ❌ 绕过 skill + 中文转英文导致召回下降
```

**正确模式：**
```
/cann-ask 卷积怎么实现   # ✅ 触发 skill 工作流，query 保持中文
```

## 输入

$ARGUMENTS

## 工作流

### 阶段 A：意图分类

| 类型 | 模式 | 示例 |
|------|------|------|
| LOOKUP | 单点事实查询 | "GELU 的公式是什么？" |
| SYNTHESIS | 跨页面合成 | "AscendC 中有哪些同步机制？" |
| COMPARISON | 对比分析 | "ElementwiseSch 与手工实现的差异？" |
| HOW-TO | 操作指南 | "如何实现一个新的激活算子？" |
| COVERAGE | 覆盖范围 | "哪些算子使用了 reduction 模式？" |

### 阶段 B：MCP 检索

调用 MCP `wiki_search`：

```
wiki_search(
  query: "<用户问题或关键词，保持原始语言>",
  tags: ["可选标签过滤"] | null,
  type: "可选类型过滤" | null,
  limit: 3
)
```

> **关键**：`query` 字段应当**保持用户原始语言**（中文用户传中文，英文用户传英文）。Wiki 语料以中文为主，把中文 query 翻成英文会显著降低召回率。除非用户问题里出现了英文专有名词需要保留，否则不要做语言转换。

服务端打分由配置的 retriever 模式决定（local / openai-api / claude-agent —— 在 server `config.yaml` 中设置）；客户端只会收到一个混合后的 `score`。**不要传 `mode`** —— 这是服务端内部参数。

响应结构（v2 schema）：

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

注意：
- `results[]` 不带 **`path`、`frontmatter`、`title`** —— 这些是服务端内部字段。Title/frontmatter 要调 `wiki_get_page(ids)` 之后才有
- `warning` 是可选字段；在 retriever 失败 / query 为空时出现。**原样转给用户**，不要静默重试或降级
- `score` 已经是混合分（依模式而定），降序排序后不要重新排名

### 阶段 C：批量 fetch 页面

单次批量调用（**不要**按 id 循环）：

```python
ids = [r["id"] for r in results[:3]]
wiki_get_page(ids=ids)
```

返回：

```json
{
  "pages": [
    {
      "id": "wiki_static_xxx_md",
      "frontmatter": {...},
      "content": "完整 markdown 内容（含 frontmatter 部分）",
      "qValue": 0.73
    }
  ],
  "errors": [
    {"id": "wiki_static_yyy_md", "error": "id not found"}
  ]
}
```

- `frontmatter` 已由服务端解析（无需自行 re-parse）
- `errors[]` 是软失败列表 —— 个别 id 失败不阻塞 `pages[]` 其余项。若未解析 id 影响了覆盖范围，在答案中提一句

**策略**：
- 默认：top-3 ids
- 若结果数 < 3：能拿多少拿多少
- 对 SYNTHESIS / COMPARISON 类型且结果 ≥ 3：可选扩展到 top-5

### 阶段 D：合成答案

把多页信息整合成结构化答案：

**引用规则（必须遵守）：**
1. **每个事实必须内联引用其来源** —— 格式：`[Source: <id>]`，使用 `wiki_get_page` 返回的知识 id
2. 引用紧跟在事实 / 小节后面，不放到末尾
3. 多来源事实：`[Source: <id1>, <id2>]`

**示例（正确）：**
```markdown
### 对齐要求 [Source: wiki_static_ascendc_guide_api_vector-compute_md]

DataCopy 传输长度必须 **32 字节对齐**。

| 要求 | 说明 |
| DataCopy 长度 | 32B 对齐 |
```

**示例（错误）：**
```markdown
### 对齐要求

DataCopy 传输长度必须 **32 字节对齐**。

---

**参考：**
- wiki_static_ascendc_guide_api_vector-compute_md
```

**内容结构：**
- COMPARISON → 对比表（每行附来源）
- HOW-TO → 步骤列表 + 代码示例（每步附来源）
- 多用表格、代码块、结构化格式
- 末尾的 References 列出 `<id> — <frontmatter.title>`（title 来自 `wiki_get_page`，不来自 search）

### 阶段 E：提示上传轨迹

在答案末尾加一句简短 footer：

```
💡 用 `/session-upload` 把本次会话上传到 Wiki
```

上传本身由 `session-upload` skill 负责 —— 完整流程见其 SKILL.md。工具签名：

```
wiki_submit_trajectory(
  session_id: "<session id>",
  content:    "<转换后的完整 Markdown 轨迹>"
)
```

只有两个参数：`session_id` 和 `content`（没有 `source` / `transcript` 等别名）。服务端把字节原样存到 `<server config trajectory.uploaded_dir>/{session_id}.md`；后续的脱敏 / 抽取由 knowledge engine 的 monitor 进程处理，本工具不管。

## 输出格式

```markdown
## Answer

[结构化内容，带 [Source: <id>] 引用]

---

**References:**
- <id1> — <frontmatter.title from wiki_get_page>
- <id2> — ...
- <id3> — ...

💡 用 `/session-upload` 把本次会话上传到 Wiki
```

## 注意事项

- **MCP Server 必需** —— 未启动时提示用户启动
- **query 语言对齐** —— 用户用什么语言提问，传给 `wiki_search` 的 `query` 就用什么语言；不要主动翻译（wiki 语料以中文为主，翻译会降低召回率）
- **按 id 引用** —— 用 `wiki_get_page` 返回的知识 `id`；不要自行编造路径
- **不要编造** —— 若 `results[]` 为空或 `warning` 非空，明确告知；不要猜测
- **自动 top-3 批量** —— 单次 `wiki_get_page(ids=[...])` 调用，不要按 id 循环
- **Q-Value 由 MCP 管理** —— 本地不追踪
- **不再手动回写文件** —— v2 已去掉 skill 内的 wiki 页面编辑能力；要把答案回喂到 wiki，用 `/session-upload`，由 `knowledge_engine` 的 ingest 管线处理
- **优雅降级** —— MCP 不可达时报错，不阻塞本地功能

## 错误处理

| 场景 | 处理 |
|------|------|
| MCP Server 未启动 | 提示启动命令 |
| `wiki_search` 结果为空，或响应携带 `warning` | 把 warning 文本原样转给用户；建议调整关键词 / 标签 |
| `wiki_get_page` 部分失败 | 列出 `errors[]` 中未解析的 id；用 `pages[]` 继续合成 |
| `wiki_submit_trajectory` 失败 | 把服务端 `message` 原样转给用户（不要吞掉） |
| 网络超时 | "超时，检查 MCP Server 状态" |
