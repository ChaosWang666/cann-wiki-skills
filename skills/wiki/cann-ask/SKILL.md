---
name: cann-ask
description: "CANN Wiki 知识检索（自然语言提问）。当用户询问 AscendC 相关问题时，必须使用本 skill（不要直接调 MCP），它把任务总目标（task_description，跨轮不变）+ 上轮设备反馈（device_feedback）合成聚焦的自然语言 query、自动派生 phase、单次调用 wiki_search，并把返回的 phase_rule 作为硬约束规则强制渲染到答案最顶。触发命令：`/cann-ask`。"
---

# CANN 知识问答 Agent

面向 AscendC Kernel 任务（人类问答 & agent loop 多轮检索）的自然语言知识检索。把任务总目标（task_description，跨轮 verbatim 不变）+ 上轮设备反馈（device_feedback）合成一句聚焦的自然语言 query，通过 MCP server 单次检索 wiki，自动批量 fetch top-3，合成带引用的答案，并把 `phase_rule` 当作硬约束规则强制渲染到答案最顶。

## 前置条件

**MCP Server 必须已启动**，提供以下工具：

| 工具 | 说明 |
|------|------|
| `wiki_search(query, phase?, tags?, type?, limit, task_description, call_count?, seen_ids?, device_feedback?)` | 返回**三分区**响应：`{phase_rule, static, dynamic, warning?}`。详见阶段 B.3 |
| `wiki_get_page(ids: list[str])` | **批量** 获取完整页面内容。响应：`{pages: [{id, frontmatter, content, qValue}], errors: [{id, error}]}` |
| `wiki_help()` | 返回 `{server, overview, tiers, tools, text}`。仅在响应结构与本 SKILL 描述不一致时调用 |
| `wiki_submit_trajectory(session_id, content)` | 持久化一次 session 轨迹 Markdown。本 skill **不直接调**，走 `session-upload` skill |

MCP endpoint: `http://localhost:3000/mcp`（streamable-http 传输）。验证可调 `wiki_search("测试", limit=1)` 或检查 3000 端口。

如果 MCP Server 未启动，提示用户先启动。

## 触发方式（必须走本 skill，不要直接调 MCP）

**重要**：当 MCP 工具（`mcp__cann-wiki__wiki_search`、`mcp__cann-wiki__wiki_get_page`）可用时，**始终通过 cann-ask skill 调用，不要直接调它们**。

**为什么必须走 skill：**
- **task_description / device_feedback / phase 一体化** —— skill 负责跨轮稳定 `task_description`、把 `device_feedback` 揉进自然语言 query、并按 feedback 内容自动派生 `phase`
- **rule 字段强制渲染** —— `wiki_search` 返回的 `phase_rule` 是当前 phase 的硬约束规则；skill 把它抬到答案最顶的 `## ⚠️ 强制规则` section，并把完整 JSON 原样附在答案最末，确保下游 codegen 模型必读必遵
- **自动批量 fetch + 合成带引用的答案** —— 一次 `wiki_get_page` 把 top-3 static + top-2 dynamic 全取回
- **轨迹日志反馈 Q-Value**

**直接调 MCP 会绕过这些能力 → 规则被忽略、phase 错配、跨轮 task_description 漂移、答案无引用。**

---

**触发场景：**
- 用户在任何问题中提到 "AscendC" / "Ascend C"
- 用户询问 AscendC kernel 开发、算子、API、模式
- 用户请求对比、how-to、列出枚举、排错
- 用户显式输入 `/cann-ask` 或说"搜 wiki"
- agent loop（如 bench 算子生成循环）每轮调一次，传入累积上下文（`call_count` / `seen_ids` / `device_feedback`）

**反面模式（不要这么做）：**

```
# 错误：用户问"卷积怎么实现"，agent 把中文意图翻成英文后直接调 MCP
mcp__cann-wiki__wiki_search(query="conv2d implementation", limit=5)  # ❌ 绕过 skill + 中文转英文降召回
```

**正确模式：**

```
/cann-ask 卷积怎么实现   # ✅ 触发 skill 工作流，query 保持中文
```

## 输入

$ARGUMENTS

调用方在 `$ARGUMENTS` 里以下面结构传入（agent loop / 人类问答 通用）：

```
<本轮自由文本问法（人类问答时是用户原话；agent loop 时可省略或写一句简短意图）>

[TASK_DESCRIPTION: <本次任务的总目标>]              # caller 责任：round 1 起逐字节缓存，每轮 verbatim 重传
[CALL_COUNT: <int>]                                # 当前轮次，0 起步
[SEEN_IDS: id1, id2, ...]                          # 前几轮已召回 id 累积
[DEVICE_FEEDBACK: <报错文本片段>]                   # 第一轮不填；第二轮起必填；原文截断由 caller 管（建议 50-200 字关键段，不要塞整个 stack）
```

**关键约束**：
- `TASK_DESCRIPTION` 一旦 round 1 确定，**跨轮逐字节不变**。caller 责任：缓存重传。skill 内**不修改、不重写、不润色**此字段，直接透传给 `wiki_search`。
- `DEVICE_FEEDBACK` 的截断由 caller 在传入前完成；skill 不再做二次裁剪。
- skill 解析上述结构后注入 `wiki_search` 调用（详见阶段 B.3）。
- 单次人类问答（不带 `TASK_DESCRIPTION` / `CALL_COUNT` 等）：把整段 `$ARGUMENTS` 当作 `task_description`，`call_count=0`、`seen_ids=null`、`device_feedback=null`。

## 工作流

**核心**：每次 cann-ask 调用 = 1 次 `wiki_search`。query 是 30-150 字的聚焦自然语言提问（**不**抽实体、**不**挑 tags、**不**拆 sub-query）；`phase` 从 `device_feedback` 自动派生；`tags` 一律 `[]`。

### 阶段 B：构造 query + 决定 phase + 单次检索

#### B.1 构造 query（自然语言，30-150 字软约束）

> **保持用户原始语言**（中文 task 传中文 query，英文 task 传英文）。Wiki 语料以中文为主，翻译会显著降召回。

| 场景 | query 怎么生成 |
|---|---|
| **round 1**（`device_feedback` 为空） | 把 `task_description` paraphrase 成一句聚焦的自然语言提问，**不要整段 dump** —— 把"总目标"重写成"本轮想查清楚什么"。<br>例：`task_description` ≈ "实现 gemm_add_relu，910B，fp16，权重 NZ 排布，要求 ..." → query 写 "在 910B 上用 fp16 实现 gemm_add_relu，矩阵乘融合激活的 tiling 和写法要点是什么"  |
| **round N**（有 `device_feedback`） | 把 `task_description` 的领域上下文 + `device_feedback` 中暴露的具体卡点合成一句聚焦的自然语言提问。<br>例：feedback 含 "DataCopy block size mismatch" → query 写 "gemm_add_relu kernel 中 DataCopy 出现 block size mismatch，常见原因和修复套路有哪些" |

**长度软约束**：query 30-150 字。**不要**把 `task_description` 或 `device_feedback` 整段塞进 `query`（它们已经分别通过 `task_description` 和 `device_feedback` 参数独立传给 server，重复 dump 会稀释 query 的聚焦度）。

#### B.2 自动派生 phase

根据 `device_feedback` 内容判断，给 `wiki_search` 传以下三档之一：

| 信号 | `phase` 取值 |
|---|---|
| `device_feedback` 为空（round 1） | `correctness`（默认） |
| 含编译错误（`error:` / `compilation terminated` / undeclared identifier / 语法错等 stderr 文本） | `correctness` |
| 含精度对比（`max_diff` / `mismatch` / 精度阈值未达标 / NaN / 溢出） | `precision` |
| 含性能数字（`µs` / `cycle` / 带宽 / 利用率 / "慢"/"卡顿" 等性能表述） | `performance` |

**禁止** `phase=all` —— 会让 tier0 一次返三篇规则正文，token 爆炸。

#### B.3 单次调用 wiki_search

```
wiki_search(
  query:            "<B.1 合成的自然语言提问，30-150 字>",
  phase:            "correctness" | "precision" | "performance",   # B.2 派生
  tags:             [],                                            # 显式空数组，server 走全量召回；当前不启用 tag 过滤
  type:             null,                                          # 不要传，见末尾警告
  limit:            3,
  task_description: "<caller 缓存的 round-1 原文，跨轮 verbatim>",
  call_count:       <int>,                                         # caller 传入的 CALL_COUNT；单次人类问答 = 0
  seen_ids:         [...] | null,                                  # caller 传入的 SEEN_IDS；单次人类问答 = null
  device_feedback:  "<caller 已截断的上轮报错原文>" | null            # 第一轮可空；第二轮起必填
)
```

**入参约定**：

| 参数 | 取值来源 | 必填 | 备注 |
|---|---|---|---|
| `query` | B.1 自然语言合成 | ✓ | 30-150 字聚焦提问；保持原始语言 |
| `phase` | B.2 派生 | ✓ | `correctness` / `precision` / `performance`；**禁止** `all` |
| `tags` | 固定 `[]` | ✓ | 显式空数组，未来若启用 tag 召回再填 |
| `type` | 不传 | 否 | 当前 server 端 `type→domain`（全库 `ascendc`），是 domain 过滤不是页面类型过滤；不要用 |
| `limit` | 固定 3 | 否 | static 召回数上限 |
| `task_description` | caller 缓存的 round-1 原文 | ✓ | **跨轮 verbatim 不变**；skill 不改写 |
| `call_count` | caller 传入 | 否 | 0 起步；单次人类问答 = 0 |
| `seen_ids` | caller 传入 | 否 | 单次人类问答 = null |
| `device_feedback` | caller 已截断的上轮报错原文 | round 1 可空；round 2+ 必填 | 50-200 字关键段；不塞整 stack |

**`intent` / `progress` / `mode` 不传** —— server 内部参数，由 `phase` 自动派生。

> ⚠️ `call_count == 0` 才会返 tier0 规则正文。第二轮起 `phase_rule.content_mode = "suppressed"` 且 `content = ""`，渲染时整段跳过（参见阶段 D）。

**响应结构（三分区）** —— 知识 `id` 形式 `{type}:{slug}`（例 `operator:relu`、`api_reference:include-datacopy-intf`、`recipe:simd-perf-memory-access`、`rule:correctness`），**不是**路径：

```json
{
  "phase_rule": {
    "phase": "correctness",
    "content_mode": "inject" | "suppressed",
    "content": "<规则正文>",
    "estimated_tokens": 0,
    "rule_refs": [{"phase", "version", "full_page_id": "rule:correctness"}],
    "description": "⚠️ 强制约束：phase_rule 中列出的踩坑规则是当前阶段的硬性要求，生成 AscendC kernel 时必须逐条严格遵守；违反将导致编译失败、精度不达标或性能劣化。"
  },
  "static":  { "results": [{"id": "<type>:<slug>", "summary", "score", "tags", ...}], "total": int },
  "dynamic": { "results": [{"id": "<type>:<slug>", "summary", "scenario", "score", "tags", ...}], "total": int, "warning"?: str },
  "warning"?: str
}
```

客户端只需读上面列出的字段。其余字段全部**忽略**：
- `path`（按 id 引用，不暴露路径）
- `branch` / `extra.q*`（server 内部状态，客户端不读）
- `citations` / `neighbors_top3` / `community_id`（图谱探索，cann-ask 单轮不展开）
- `steps_outline` / `cautions`（正文里都有，单独渲染会重复）

**tier 由响应分区直接决定**（不要从 id 文本猜）：
- `phase_rule` → tier0
- `static.results[i].id` → tier1
- `dynamic.results[i].id` → tier2

**score 仅在各自 tier 内部降序**，两 tier 之间不可比（打分器不同），不要跨 tier 合并排序。
**warning 原样透传**（顶层 + `dynamic.warning` 都要收），不重试不降级。

### 阶段 C：批量 fetch 页面

**单次批量调用** —— 把 `static.results` top-3 和 `dynamic.results` top-2 的 id 合并到一个 list，一次 `wiki_get_page(ids=[...])` 取回所有正文（**不要**分两次调，也不要按 id 循环）：

```python
static_ids  = [r["id"] for r in response["static"]["results"][:3]]
dynamic_ids = [r["id"] for r in response["dynamic"]["results"][:2]]
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
- **tier 判定走响应分区映射**（`static` → tier1 / `dynamic` → tier2），不要从 `id` 文本或 `path` 反推
- `qValue` 是 server 端管理的状态，**客户端不读不展示**
- `errors[]` 是软失败列表 —— 个别 id 失败不阻塞 `pages[]` 其余项。若未解析 id 影响了覆盖范围，在答案中提一句

### 阶段 D：合成答案

按下面顺序输出。**每段都基于 `wiki_get_page` 返回的页面正文写实质内容**（不是只抄 summary）。完整版式见下方"输出格式"样例。

1. **`## ⚠️ 强制规则`**（tier0 phase_rule）—— **核心职责，必须最顶部渲染**，详见下方"rule_description 渲染细则"
2. **`## 📚 相关文档`**（tier1 static）—— 基于页面正文写结构化答案，带 `[Source: <id>]` 内联引用
3. **`## 🔧 实践 recipe`**（tier2 dynamic）—— 每条 recipe 用 `### {scenario}` 三级标题（`scenario` 取自 search 响应），下接正文。`dynamic` 整体为空时**整段隐藏**，不留空标题
4. **References** —— 单一列表，tier 前缀 📚（tier1）/ 🔧（tier2），title 取 `wiki_get_page` 的 `frontmatter.title`
5. **Warning callout**（若有）—— `> ⚠️ Server warning: {...}`，原样透传不重试
6. **phase_rule JSON 附末** —— 详见下方"rule_description 渲染细则"
7. **footer** —— 见阶段 E

**引用规则**：每个事实必须**内联**引用 `[Source: <id>]`，紧跟事实写而不放到末尾；多来源 `[Source: <id1>, <id2>]`；id 取 `wiki_get_page` 返回值，不要编造路径。

#### rule_description 渲染细则（核心职责）

`phase_rule.description` 是 server 标注的硬约束告警语（例："⚠️ 强制约束：phase_rule 中列出的踩坑规则是当前阶段的硬性要求……必须逐条严格遵守……"）。该字段是给下游 codegen 模型看的"必读"信号 —— **抬到答案最顶部、最显眼的位置渲染，是 cann-ask 的核心职责**。

**渲染规则**：

- **`content_mode == "inject"`** → 严格渲染如下结构到答案最顶（在 `## 📚 相关文档` 之前）：

  ```markdown
  ## ⚠️ 强制规则

  {phase_rule.description}

  {phase_rule.content}
  ```

  `phase_rule.content` 原样贴出（通常已是规则编号列表，不要二次摘要）。
- **`content_mode == "suppressed"`** → 整段 `## ⚠️ 强制规则` section **不渲染**（不要渲染只有 description 没有 content 的"空规则告警"，会变成噪声）

**phase_rule JSON 附末**：无论 `content_mode` 是 `inject` 还是 `suppressed`，**都要**把完整 `phase_rule` JSON 原样附在答案最末的独立 ```json fenced block 里：

```json
{ "phase_rule": { ... server 返回原文 ... } }
```

用途：trajectory 上报、phase_rule 命中统计、eval 侧解析。

### 阶段 E：footer 提示上传轨迹

答案末尾加一句：`💡 用 `/session-upload` 把本次会话上传到 Wiki`。上传流程在 `session-upload` skill 里，本 skill 不直接调 `wiki_submit_trajectory`。

## 输出格式

```markdown
## ⚠️ 强制规则

⚠️ 强制约束：phase_rule 中列出的踩坑规则是当前阶段的硬性要求，生成 AscendC kernel 时必须逐条严格遵守；违反将导致编译失败、精度不达标或性能劣化。

1. float/uint32 互转必须经 int32 中转，禁止直接 static_cast。
2. DataCopy 后必须 EnQue/DeQue 配对，避免读未同步数据。
3. ...

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

```json
{
  "phase_rule": {
    "phase": "correctness",
    "content_mode": "inject",
    "content": "...",
    "estimated_tokens": 0,
    "rule_refs": [{"phase": "correctness", "version": "...", "full_page_id": "rule:correctness"}],
    "description": "⚠️ 强制约束：phase_rule 中列出的踩坑规则是当前阶段的硬性要求……"
  }
}
```

💡 用 `/session-upload` 把本次会话上传到 Wiki
```

## 注意事项

- **自然语言 query，单次检索** —— 一次 cann-ask = 一次 `wiki_search`；query 是 30-150 字的聚焦自然语言提问，**不**抽实体、**不**挑 tags、**不**拆 sub-query
- **task_description 跨轮 verbatim 不变** —— caller 责任：round 1 起逐字节缓存重传；skill 内**不修改、不重写、不润色**
- **phase 从 device_feedback 自动派生** —— round 1 默认 `correctness`；round N 按 feedback 内容映射到 `correctness` / `precision` / `performance`。**禁止** `phase=all`
- **tags 暂置空 `[]`** —— server 走全量召回；未来若启用 tag 召回再填
- **rule_description 强制抬升** —— `phase_rule.content_mode == "inject"` 时渲染 `## ⚠️ 强制规则` section 到答案最顶；`suppressed` 时整段跳过；完整 `phase_rule` JSON 无论何种 content_mode 都附在答案最末
- **query 保持原始语言** —— wiki 以中文为主，翻译降召回
- **三分区响应** —— `wiki_search` 顶层是 `{phase_rule, static, dynamic, warning?}`，阶段 D 分别渲染，不要合并成一个列表
- **tier 由响应分区决定** —— 不要从 id 文本前缀（`{type}:{slug}`）反推
- **按 id 引用** —— 不暴露 `path`；批量 fetch 时 `static_top_3 + dynamic_top_2` 合并到**一次** `wiki_get_page` 调用
- **device_feedback 截断由 caller 管** —— skill 不再做二次裁剪
- **不要编造** —— 两 tier 都空或 `warning` 非空时明确告知，不猜。MCP 不可达时报错，不阻塞本地功能

## 错误处理

| 场景 | 处理 |
|------|------|
| MCP Server 未启动 | 提示启动命令 |
| `wiki_search` 响应缺三分区字段 | 调 `wiki_help()` 拿当前契约，告诉用户 server 版本不匹配；不要强解析 |
| `wiki_search` 结果为空（`static` 和 `dynamic` 都空），或响应携带 `warning` | 把 warning 文本原样转给用户；建议调整 query 措辞 |
| `wiki_get_page` 部分失败 | 列出 `errors[]` 中未解析的 id；用 `pages[]` 继续合成 |
| `phase_rule.content_mode == "suppressed"` | graceful 跳过顶部 `## ⚠️ 强制规则` section；JSON 附末仍保留 |
| `wiki_submit_trajectory` 失败 | 不在本 skill 处理，走 `session-upload` skill |
| 网络超时 | "超时，检查 MCP Server 状态" |
