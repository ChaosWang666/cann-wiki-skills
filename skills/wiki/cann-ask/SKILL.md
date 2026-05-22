---
name: cann-ask
description: "CANN Wiki 知识检索（面向人类提问）。当用户询问 AscendC 相关问题时，必须使用本 skill（不要直接调 MCP），它负责 shape 分类 + 按 SCHEMA 词表锚定 tags + query plan 拆分 + 并行检索、自动批量 fetch、合成答案并附内联引用。触发命令：`/cann-ask`。"
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

### 阶段 B：锚定 SCHEMA + 并行检索

**核心约束：wiki_search 是 schema-driven 检索，不是 free-text 关键词搜索。** 不要把用户问题整段塞进 `query`——wiki 文档侧索引只有 几十到 100 字符的精炼摘要，长 query 会让 TFIDF 的低 IDF 词稀释具体技术词、让 embedding 的多主题向量偏离单主题页面。

正确流程：**先按 `wiki/SCHEMA.md` 的标签词表挑 `tags`**（决定候选池范围）→ 决定 `phase`（决定 tier0 规则 + 排序倾向）→ 用极短稀有标识符做 `query`（决定召回排序）→ 并发 2-4 路 sub-query → 按 tier 分别合并。

#### B.1 锚定 SCHEMA（挑 tags + 决定 phase）

> **关键**：所有 sub-query 都应当**保持用户原始语言**（中文用户传中文，英文用户传英文）。Wiki 语料以中文为主，翻译会显著降召回。

**Step 1 — 抽实体**（1-3 个，缺则留空，不要硬编）：

| 字段 | 含义 | 例子 |
|------|------|------|
| 核心概念 | API / 算子 / 模式 / 工具名 | `DataCopy`、`ElementwiseSch`、`reduction`、`msprof` |
| 场景约束 | 硬件 / 数据类型 / 调度模式 | `910B`、`float16`、`双缓冲` |
| 期望信息 | 哪一类内容 | 定义公式 / API 签名 / 实现示例 / 设计原理 / 排错步骤 |

**Step 2 — 用 SCHEMA 词表挑 `tags`**（**必传 2-4 个，必须从 SCHEMA 权威词表挑，不允许自由发挥**）：

权威词表在 wiki 仓的 `wiki/SCHEMA.md` 第 7 节"标签体系"。**本轮第一次调本 skill 时**先 `Read` 该文件拿现场词表（路径示例：`AscendC-Kernel-Wiki/wiki/SCHEMA.md`；位置不确定就 `Glob "**/wiki/SCHEMA.md"`），后续同一会话内可直接用上次记住的词表。13 个类目作为助记：

> 编程概念 ｜ 编程范式 ｜ API ｜ 代码模式 ｜ 算子分类 ｜ 数据类型 ｜ 硬件/架构 ｜ 工具链 ｜ 调试调优 ｜ 教程/参考 ｜ 框架 ｜ 工程化 ｜ 页面类型标记(`api_reference`/`practice`/`concept`/`toolchain`，想限定页面类型时混进 `tags`)

**Step 3 — 实体 → tags 映射示例**（show, don't tell）：

| 用户问 | tags（只从词表挑） | phase |
|---|---|---|
| "gemm_add_relu 怎么写" | `matmul`,`elementwise`,`fp16` | correctness |
| "DataCopy 32 字节对齐" | `datacopy_api`,`memory_hierarchy` | correctness |
| "msprof 怎么看 cube 利用率" | `msprof`,`performance`,`tooling` | performance |
| "relu fp16 实现" | `activation`,`fp16`,`simd` | correctness |
| "精度对不上怎么排查" | `troubleshooting`,`debug` | precision |
| "ElementwiseSch 双缓冲" | `elementwise`,`double_buffer`,`tiling` | correctness |
| "Matmul API 签名" | `matmul_api`,`api_reference` | correctness |
| "msopgen 怎么生成算子工程" | `msopgen`,`getting_started` | correctness |

**Step 4 — `phase` 软触发**（决定 tier0 返哪篇规则 + 偏置 tier1 排序）：

| 关键词命中（在原始 query 文本里扫） | `phase` 取值 |
|---|---|
| 含 "性能"/"优化"/"耗时"/"慢"/"卡顿"/"带宽"/"吞吐" | `performance` |
| 含 "精度"/"数值"/"对不上"/"误差"/"NaN"/"溢出" | `precision` |
| 上两类都没命中（**默认**） | `correctness`（可省略不传，server 端 None ≡ correctness）|

**禁止**传 `phase=all`——会让 tier0 一次返三篇正文，token 爆炸。

> ⚠️ **`type` MCP 参数当前不要用**：server 端把 `type` 映射到 `entry.domain`（全库都是 `ascendc`），实际是 domain 硬过滤，不是页面类型过滤。要过滤页面类型，请混用 `tags` 里"页面类型标记"那一栏（`api_reference`/`practice`/`concept`/`toolchain`），或靠 ID 前缀（`{type}:{slug}`）后置过滤。

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
  query:            "<极短稀有标识符，1-3 token，保持原始语言>",   # 算子名/API名/错误码这种具体词，不要塞整段任务描述
  phase:            "correctness" | "precision" | "performance",   # B.1 Step 4 软触发；省略=correctness
  tags:             ["从 SCHEMA 词表挑，2-4 个"],                   # 必传，B.1 Step 2/3
  type:             null,                                          # 不要传，见 B.1 末尾警告
  limit:            3,
  task_description: "<本次任务全文/目标，必传>",                    # 注入 tier2 Agent 上下文
  call_count:       <int>,                                         # 见下文"多轮调用约定"
  seen_ids:         [...] | null,                                  # 见下文
  device_feedback:  "<上一轮上板报错文本>" | null                   # 第一轮可空；第二轮起必传
)
```

**入参约定**：

| 参数 | 取值来源 | 必填 | 备注 |
|---|---|---|---|
| `query` | B.2 拆出的 sub-query | ✓ | **极短**——只放 1-3 个稀有标识符（算子名/API名/错误码/模式名），不塞整段问题；长 query 在 TFIDF/embedding 两路都会被低 IDF 词稀释 |
| `phase` | B.1 Step 4 软触发 | 可省略 | 4 条 sub-query 用同一 phase；省略=correctness；**禁止** `phase=all`(token 爆炸) |
| `tags` | B.1 Step 2/3 从 SCHEMA 词表挑 | **✓ 必传** | 2-4 个；**只能从 §B.1 Step 2 词表挑**，不允许自由发挥；server 端是硬过滤（任一 tag 命中即保留） |
| `type` | 不传 | 否 | 当前 server 端 `type→domain`(全库 `ascendc`)，不是页面类型过滤；要过滤页面类型走 `tags` 的"页面类型标记"那一栏 |
| `limit` | 由 shape 决定 | 否 | 默认 3 |
| `task_description` | 用户原始问题（或调用方传入的任务描述） | **✓ 必传** | 4 条 sub-query 共享同一份；让 tier2 Agent 理解整体任务（**这里**塞富上下文，不在 query 里塞） |
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

- **schema-driven 而非 keyword-driven** —— 检索成败的关键是 §B.1 选对 `tags`（候选池范围）+ `query` 用极短稀有标识符（召回排序信号）。把用户问题整段塞 `query` 会让 TFIDF/embedding 都被稀释；富上下文（task / device_feedback）走 `task_description` 给 tier2 Agent，不要混进 `query`。
- **`tags` 必传** —— 2-4 个，只从 §B.1 Step 2 的 SCHEMA 词表里挑，不允许自由发挥；server 端是硬过滤。
- **`type` 不要用** —— server 端是 `domain` 过滤不是页面类型过滤；要过滤页面类型走 `tags` 的"页面类型标记"。
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
