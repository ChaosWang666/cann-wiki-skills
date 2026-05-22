---
name: cann-ask
description: "CANN Wiki 知识检索（面向人类提问）。当用户询问 AscendC 相关问题时，必须使用本 skill（不要直接调 MCP），它负责 shape 分类 + query plan 拆分 + 并行检索、自动批量 fetch、合成答案并附内联引用。触发命令：`/cann-ask`。"
---

# CANN 知识问答 Agent

面向人类提问的 AscendC Kernel Wiki 知识检索，通过 MCP Server 找到相关页面，自动 fetch top-3，并合成带引用的答案。

## 前置条件

**MCP Server 必须已启动**，提供以下工具：

| 工具 | 说明 |
|------|------|
| `wiki_search(query, phase?, tags?, type?, limit, intent?, progress?, task_description, call_count?, seen_ids?, device_feedback?)` | 返回**三分区**响应：`{phase_rule, static, dynamic, warning?}`。详见阶段 B.2 |
| `wiki_get_page(ids: list[str])` | **批量** 获取完整页面内容。响应：`{pages: [{id, frontmatter, content, qValue}], errors: [{id, error}]}` |
| `wiki_help()` | 返回 `{server, overview, tiers, tools, text}`，其中 `text` 是契约的 markdown 说明。仅在响应结构与本 SKILL 描述不一致时调用，平常不调 |
| `wiki_submit_trajectory(session_id, content)` | 持久化一次 session 轨迹 Markdown；上传路径由 server `config.yaml` 的 `trajectory.uploaded_dir` 决定 |

MCP endpoint: `http://localhost:3000/mcp`（streamable-http 传输）

如果 MCP Server 未启动，提示用户先启动。要验证状态，可调用 `wiki_search("测试", limit=1)` 或检查 3000 端口。

## 触发方式（必须走本 skill，不要直接调 MCP）

**重要**：当 MCP 工具（`mcp__cann-wiki__wiki_search`、`mcp__cann-wiki__wiki_get_page`）可用时，**始终通过 cann-ask skill 调用，不要直接调它们**。

**为什么必须走 skill：**
- shape 分类 + query plan → 把长问题拆成多条聚焦 sub-query 并行检索，召回率比单条裸 query 高
- 自动批量 fetch + 合成 → 跨页面连贯回答
- 强制内联引用 → 知识可追溯
- 轨迹日志 → 为检索改进提供 Q-Value 反馈

**直接调 MCP 会绕过这些能力 → 回答质量更差。**

---

**触发 cann-ask 的场景：**
- 用户在任何问题中提到 "AscendC" / "Ascend C"
- 用户询问 AscendC kernel 开发、算子、API、模式
- 用户请求对比（如"ElementwiseSch 与手工流水线的差异"）
- 用户请求 how-to（如"如何实现一个新的激活算子"）
- 用户请求列出 / 枚举（如"哪些算子用了 reduction"、"有哪些同步机制"）
- 用户请求排错（如"算子精度对不上怎么排查"、"编译报 xxx 错"）
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

调用方可在 `$ARGUMENTS` 里以下面任一形式附加 agent loop 上下文（不带就视为单次人类问答）：

```
<用户问题/任务描述（必填，整体作为 task_description）>

[CALL_COUNT: <int>]              # 当前轮次，0 起步
[SEEN_IDS: id1, id2, ...]         # 前几轮已召回 id 累积
[DEVICE_FEEDBACK: <报错文本片段>]  # 上一轮上板报错；第一轮不填，第二轮起必填
```

skill 解析后注入 wiki_search 调用（详见阶段 B.2）。

## 工作流

### 阶段 A：问题形态分类（shape）

判断用户问的是哪种形态。**形态决定输出版式和 top-N**（具体的检索措辞由阶段 B 的 query plan 决定，跟形态正交）。

| shape | 模式 | 示例 |
|------|------|------|
| LOOKUP | 单点事实 | "GELU 的公式是什么？" |
| LIST | 列出 / 枚举多项 | "AscendC 有哪些同步机制？"、"哪些算子用了 reduction？" |
| COMPARISON | 对比分析 | "ElementwiseSch 与手工实现的差异？" |
| HOW-TO | 操作指南 | "如何实现一个新的激活算子？" |
| TROUBLESHOOTING | 排错 / 调试 | "算子精度对不上怎么排查？"、"编译报 xxx 错怎么处理？" |

### 阶段 B：query 计划 + 并行检索

把"长问题塞成一条 query"会让 dense embedding 被多主题稀释、命中率下降。本阶段先抽结构化字段 + 决定 `phase`，再按 shape 拆 2-4 条聚焦 sub-query 并行检索，最后按 tier 分别合并去重。

#### B.1 从用户问题抽取结构化字段 + 决定 phase

> **关键**：所有 sub-query 都应当**保持用户原始语言**（中文用户传中文，英文用户传英文）。Wiki 语料以中文为主，把中文翻成英文会显著降低召回率。除非用户原文出现英文专有名词需保留，否则不要做语言转换。

抽出三组字段（缺则留空，不要硬编）：

| 字段 | 含义 | 例子 |
|------|------|------|
| 核心概念 | 1-3 个实体 / API / 模式名 | `DataCopy`、`ElementwiseSch`、`reduction` |
| 场景约束 | 硬件 / 版本 / 数据类型 / 调度模式 | `910B`、`float16`、`双缓冲` |
| 期望信息 | 哪一类内容 | 定义公式 / API 签名 / 实现示例 / 设计原理 / 错误排查 |

**关键词软触发 `phase`**（决定 tier0 返哪篇踩坑规则 + 偏置 tier1 排序）：

| 关键词命中（在原始 query 文本里扫） | `phase` 取值 |
|---|---|
| 含 "性能"/"优化"/"耗时"/"慢"/"卡顿"/"带宽"/"吞吐" | `performance` |
| 含 "精度"/"数值"/"对不上"/"误差"/"NaN"/"溢出" | `precision` |
| 上两类都没命中（**默认**） | `correctness`（也可省略不传，server 端 None ≡ correctness）|

**禁止**传 `phase=all`——会让 tier0 一次返三篇正文，token 爆炸。

#### B.2 构造 sub-query 并并行检索

按 shape 决定 sub-query 数量（**上限 4**，每条只带 1-2 个核心 token，sub-query 之间**关键词互不重复**）：

| shape | sub-query 数 | 拆分策略 |
|------|------|------|
| LOOKUP | 1 | 窄事实，单查询足够 |
| LIST | 2-3 | 不同子主题 / 不同 angle 各一条 |
| COMPARISON | 2 | 两边各一条 |
| HOW-TO | 2-3 | 概念、API、实现示例 各一条 |
| TROUBLESHOOTING | 2-3 | 症状现象、可能原因、排查/工具 各一条 |

**Guardrail**：用户问题 < ~15 字且未给出场景约束 → 强制 1 条 sub-query，不拆。

并行调用 `wiki_search`（同一 tool 多次 invoke，在同一回合发出）。**所有 sub-query 共享同一个 `phase` + 同一个 `task_description`**（B.1 决定）：

```
wiki_search(
  query:            "<sub-query，保持原始语言>",
  phase:            "correctness" | "precision" | "performance",   # B.1 软触发；省略=correctness
  tags:             ["可选标签过滤"] | null,
  type:             "可选类型过滤" | null,
  limit:            3,
  task_description: "<本次任务全文/目标，必传>",        # 注入 tier2 Agent 上下文
  call_count:       <int>,                              # 见下文"多轮调用约定"
  seen_ids:         [...] | null,                       # 见下文
  device_feedback:  "<上一轮上板报错文本>" | null        # 第一轮可空；第二轮起必传
)
```

**入参约定**：

| 参数 | 取值来源 | 必填 | 备注 |
|---|---|---|---|
| `query` | B.2 拆出的 sub-query | ✓ | |
| `phase` | B.1 关键词软触发 | 可省略 | 4 条 sub-query 用同一 phase；省略=correctness；**禁止** `phase=all`(token 爆炸) |
| `tags` / `type` | 用户给的硬过滤 | 否 | 一般不传 |
| `limit` | 由 shape 决定 | 否 | 默认 3 |
| `task_description` | 用户原始问题（或调用方传入的任务描述） | **✓ 必传** | 4 条 sub-query 共享同一份；用来让 tier2 Agent 理解整体任务 |
| `call_count` | 调用方维护的轮次计数器 | 否 | 见下文 |
| `seen_ids` | 上一轮已召回的 id 累计 | 否 | 见下文 |
| `device_feedback` | 上一轮上板测试报错文本（compile / precision / runtime error） | **第一轮可空；第二轮起必传** | 让 tier2 Agent 优先召回能解决该问题的 recipe |

**`intent` / `progress` / `mode` 不传** —— server 内部参数，由 `phase` 自动派生。

**多轮调用约定**（cann-ask 既支持人类单次问答，也支持 agent loop 调用方多轮检索）：

- **单次人类问答**：调用方未提供轮次上下文 → `call_count=0`、`seen_ids=null`、`device_feedback=null`。4 条 sub-query 都用同一组值，并行发。
- **Agent loop 多轮**：调用方（bench / agent）跨次 cann-ask 调用维护状态：
  - `call_count`：本算子任务从 0 起，每轮 +1；同一轮内 4 条 sub-query 共用同一个 `call_count`
  - `seen_ids`：累积前几轮 4 条 sub-query 返回的所有 `static.results[i].id` + `dynamic.results[i].id`，去重
  - `device_feedback`：上一轮 `try_kernel` 的报错文本片段（截 50-200 字关键段，不要塞整个 stack）；第一轮没有就传 null
  - 调用 cann-ask 时把上述状态作为 `$ARGUMENTS` 的结构化部分传入（见 §输入），skill 解析后注入 4 条 sub-query

> ⚠️ `call_count==0` 才会返 tier0 规则正文。第二轮起 `phase_rule.content_mode="suppressed"` 且 `content=""`，渲染时 graceful 跳过。

**响应结构（三分区）** —— 知识 `id` 是 `{type}:{slug}` 形式（例 `operator:relu`、`api_reference:include-datacopy-intf`、`recipe:simd-perf-memory-access`、`rule:correctness`），**不是**路径：

```json
{
  "phase_rule": { "content_mode": "inject"|"suppressed", "content": "<规则正文>", "phase": "...",
                  "rule_refs": [{"phase","version","full_page_id":"rule:correctness"}], ... },
  "static":  { "results": [{"id":"<type>:<slug>","summary","score","tags", ...}], "total": int },
  "dynamic": { "results": [{"id":"<type>:<slug>","summary","scenario","score","tags", ...}], "total": int, "warning"?: str },
  "warning"?: str
}
```

客户端只需读上面列出的字段。其余字段全部**忽略**：
- `path`（按 id 引用，不暴露路径）
- `branch` / `extra.q*`（server 内部状态，客户端不读）
- `citations` / `neighbors_top3` / `community_id`（图谱探索，cann-ask 单轮不展开）
- `steps_outline` / `cautions`（正文里都有，单独渲染会重复）

**tier 由响应分区直接决定**（不要从 id 文本猜）：
- `phase_rule.rule_refs[].full_page_id` → tier0
- `static.results[i].id` → tier1
- `dynamic.results[i].id` → tier2

合并 + 批量 fetch 时把这个映射记下来（id → tier），阶段 D 渲染时直接查表。

**score 仅在各自 tier 内部降序，两 tier 之间不可比**（打分器不同），不要跨 tier 合并排序。
**warning 原样透传**（顶层 + `dynamic.warning` 都要收），不重试不降级。

#### B.3 合并各 sub-query 结果（三分区分别合并）

`phase`、`static`、`dynamic` 各自独立合并，**不要跨 tier 排序**（score 不可比）：

- **`phase_rule`**：所有 sub-query 共享同一 `phase`，返回内容也一致 —— **取第一条 sub-query 的 `phase_rule`** 即可，本地去重。`content_mode == "suppressed"`（第二轮起常见）整段跳过不渲染
- **`static.results`**：跨 sub-query 按 `id` 去重，同 id **取 max(score)**（不取 sum，避免高频通用页面被叠加抬权），按合并分降序，**取 shape 决定的 top-N**：LOOKUP / HOW-TO / TROUBLESHOOTING 取 **top-3**；LIST / COMPARISON 取 **top-5**
- **`dynamic.results`**：跨 sub-query 同样按 `id` 去重 + max(score) 排序，**固定 top-2**（recipe 结构化字段密度高，2 条通常足够，多了反而稀释焦点）
- **id→tier 映射**：合并时一并记录每个 id 来自哪个分区（`static` / `dynamic`），阶段 C/D 用这个映射决定渲染分段。**不要从 id 文本前缀猜 tier**，response 已经分好了
- **warning**：收集所有 sub-query 的（顶层 `warning` + `dynamic.warning`），去重后**原样**透传给用户（阶段 D 末尾 callout 处展示），不静默忽略

### 阶段 C：批量 fetch 页面

**单次批量调用** —— 把 `static` top-N 和 `dynamic` top-2 的 id **合并到一个 list**，一次 `wiki_get_page(ids=[...])` 取回所有正文（**不要**分两次调，也不要按 id 循环）：

```python
# top_n_static 由 B.3 按 shape 决定：LOOKUP/HOW-TO/TROUBLESHOOTING=3，LIST/COMPARISON=5
# top_n_dynamic 固定 = 2
static_ids  = [r["id"] for r in merged_static[:top_n_static]]
dynamic_ids = [r["id"] for r in merged_dynamic[:2]]
wiki_get_page(ids=static_ids + dynamic_ids)
```

返回：

```json
{
  "pages": [
    {
      "id":          "api_reference:include-datacopy-intf",
      "frontmatter": {"title": "...", "tags": [...], ...},
      "content":     "完整 markdown 内容（含 frontmatter 部分）",
      "qValue":      0.73
    }
  ],
  "errors": [
    {"id": "operator:nonexistent", "error": "id not found"}
  ]
}
```

- `frontmatter` 已由服务端解析（无需自行 re-parse）；阶段 D 渲染 References 时取 `frontmatter.title`
- **tier 判定走 B.3 记下的 id→tier 映射**，不要从 `id` 文本或 `path` 反推
- `qValue` 是 server 端管理的状态，**客户端不读不展示**
- `errors[]` 是软失败列表 —— 个别 id 失败不阻塞 `pages[]` 其余项。若未解析 id 影响了覆盖范围，在答案中提一句

### 阶段 D：合成答案

按下面顺序输出。**每段都基于 `wiki_get_page` 返回的页面正文写实质内容**（不是只抄 summary）。完整版式见下方"输出格式"样例。

1. **顶部规则块** —— `phase_rule.content_mode == "inject"` 时，把 `phase_rule.content` 原样贴在最顶（块引用形式）；`suppressed` 时整段跳过。
2. **`## 📚 相关文档`**（tier1 static）—— 按 shape 选版式：LOOKUP 一句话；LIST/COMPARISON 表格；HOW-TO 步骤+代码；TROUBLESHOOTING "症状→原因→修复"三段。
3. **`## 🔧 实践 recipe`**（tier2 dynamic）—— 每条 recipe 用 `### {scenario}` 三级标题（`scenario` 取自 search 响应），下接正文。`dynamic` 整体为空时**整段隐藏**，不留空标题。
4. **References** —— 单一列表，tier 前缀 📚（tier1）/ 🔧（tier2），title 取 `wiki_get_page` 的 `frontmatter.title`。
5. **Warning callout**（若有）—— `> ⚠️ Server warning: {...}`，原样透传不重试。
6. **footer** —— 见阶段 E。

**引用规则**：每个事实必须**内联**引用 `[Source: <id>]`，紧跟事实写而不放到末尾；多来源 `[Source: <id1>, <id2>]`；id 取 `wiki_get_page` 返回值，不要编造路径。

### 阶段 E：footer 提示上传轨迹

答案末尾加一句：`💡 用 `/session-upload` 把本次会话上传到 Wiki`。上传流程在 `session-upload` skill 里，本 skill 不直接调 `wiki_submit_trajectory`。

## 输出格式

```markdown
> ⚠️ **correctness 必读规则**（每次查询强制注入；详见 `wiki_get_page(["rule:correctness"])` 取全文）
>
> 1. float/uint32 互转必须经 int32 中转，禁止直接 static_cast。
> 2. DataCopy 后必须 EnQue/DeQue 配对，避免读未同步数据。
> 3. ...

## 📚 相关文档

[基于 tier1 static 页面正文的结构化答案，带 [Source: <id>] 引用]

## 🔧 实践 recipe

### {scenario_1}

[基于 tier2 recipe 页面正文的实质内容] [Source: recipe:simd-perf-memory-access]

---

**References:**
- 📚 api_reference:include-datacopy-intf — <frontmatter.title>
- 📚 synthesis:api-reference-master-index — <frontmatter.title>
- 🔧 recipe:simd-perf-memory-access — <frontmatter.title>

> ⚠️ Server warning: ...  （仅在 server 返回 warning 时出现）

💡 用 `/session-upload` 把本次会话上传到 Wiki
```

## 注意事项

- **三分区响应** —— `wiki_search` 顶层是 `{phase_rule, static, dynamic, warning?}`，阶段 D 分别渲染，不要合并成一个列表。
- **phase / task_description 全 sub-query 共享** —— 4 条 sub-query 用同一组值；`task_description` **必传**。
- **多轮状态由调用方维护** —— `call_count` / `seen_ids` / `device_feedback` 是调用方传进来的（人类单次问答都为空 / null；agent loop 调用方自己累积）。`device_feedback` 第一轮可空，第二轮起必传。
- **tier 由响应分区决定**，不要从 id 文本前缀（`{type}:{slug}`）反推。
- **query 保持原始语言** —— wiki 以中文为主，翻译降召回。
- **按 id 引用** —— 不暴露 `path`；批量 fetch 时 `static_top_N + dynamic_top_2` 合并到**一次** `wiki_get_page` 调用。
- **不要编造** —— 两 tier 都空或 `warning` 非空时明确告知，不猜。MCP 不可达时报错，不阻塞本地功能。

## 错误处理

| 场景 | 处理 |
|------|------|
| MCP Server 未启动 | 提示启动命令 |
| `wiki_search` 响应缺三分区字段 | 调 `wiki_help()` 拿当前契约，告诉用户 server 版本不匹配；不要强解析 |
| `wiki_search` 结果为空（`static` 和 `dynamic` 都空），或响应携带 `warning` | 把 warning 文本原样转给用户；建议调整关键词 / 标签 |
| `wiki_get_page` 部分失败 | 列出 `errors[]` 中未解析的 id；用 `pages[]` 继续合成 |
| `phase_rule.content_mode == "suppressed"` | graceful 跳过顶部规则块（不应在 cann-ask 单轮场景出现，但仍要兼容） |
| `wiki_submit_trajectory` 失败 | 把服务端 `message` 原样转给用户（不要吞掉） |
| 网络超时 | "超时，检查 MCP Server 状态" |
