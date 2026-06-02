---
name: cann-ask
description: "CANN Wiki 知识检索（自然语言提问）。当用户询问 AscendC 相关问题时，必须使用本 skill（不要直接调 MCP），它把任务总目标（task_description，跨轮不变）+ 上轮设备反馈（device_feedback）合成聚焦的自然语言 query、自动派生 phase、单次调用 wiki_search（v5.2 主 Agent 契约），并按新契约渲染 phase_rule（硬约束规则强制抬到最顶）+ 顶层 ai_suggestion（主 Agent 跨 tier 综述，按 agent_status 标注 ok/degraded/disabled）+ tier1/tier2 page bodies（合成带引用的答案）。触发命令：`/cann-ask`。"
---

# CANN 知识问答 Agent

面向 AscendC Kernel 任务（人类问答 & agent loop 多轮检索）的自然语言知识检索。把任务总目标 + 上轮设备反馈合成一句聚焦的自然语言 query，通过 MCP server 单次检索 wiki，按"phase_rule 硬约束规则 + ai_suggestion server 检索建议 + page 正文合成"三层渲染给下游。

## 前置条件

**MCP Server 必须已启动**，endpoint: `http://113.46.4.206:8767/mcp`（streamable-http 传输；由 `/setup-cann-wiki` 配置，地址不一致时先跑该 skill）。验证可调 `wiki_search("测试", limit=1)` 或检查 8767 端口。如果未启动，提示用户先启动。

四个 MCP 工具的详细契约见下方 §"MCP 工具契约详解"。

## MCP 工具契约详解

> ⚠️ **来源唯一性**：本节内容来自 `mcp-server/server.py`、`response_schema.py`、`help_doc.py` 三处汇总。如果 server 端响应与本节描述不一致，先调 `wiki_help()` 拿当前契约，再决定是否更新本 SKILL。

### `wiki_search` —— 三分区知识检索（核心）

**签名**：

```
wiki_search(
  query, phase=None, tags=None, type=None, limit=10,
  intent=None, progress=None, task_description=None,
  call_count=0, seen_ids=None, device_feedback=None
) -> dict
```


**作用**：一次调用同时返回三层知识：tier0 `phase_rule`（踩坑规则，强制注入）+ tier1 `static`（静态事实，传统漏斗）+ tier2 `dynamic`（实践 recipe，单次 Agent）。

#### 入参字段

| 参数 | 类型 | 必填 | 含义 | cann-ask 取值 |
|---|---|---|---|---|
| `query` | str | ✓ | 自然语言查询；空串时 static 区返回 warning | B.1 合成的 30-150 字聚焦提问 |
| `phase` | str\|None | 否 | `correctness` \| `precision` \| `performance` \| `all`；None→correctness。决定 tier0 返回哪篇规则 + 派生 tier1 Q-sort intent（correctness/precision→q1，performance→q2，all→mixed）。**禁止 `all`** —— tier0 一次返三篇正文 token 爆炸 | B.2 从 device_feedback 派生 |
| `tags` | list[str]\|None | 否 | 标签硬过滤（交集）；server 端会与 entry.tags 取交集 | 固定 `[]`（当前不启用 tag 召回） |
| `type` | str\|None | 否 | 限定 `entry.domain`（不是页面类型过滤）；全库 domain 都是 `ascendc`，传了无效 | `null`（不传） |
| `limit` | int | 否 | tier1 返回上限，截到 `min(limit, K3=10)` | 固定 `3` |
| `intent` | str\|None | 否 | `q1` \| `q2` \| `mixed` 显式覆盖；`phase` 给定时由 phase 派生覆盖。非法值 server 返回 warning | 不传（让 phase 派生） |
| `progress` | str\|None | 否 | `phase` 的兼容别名（server 端 `eff_phase = phase if phase is not None else progress`） | 不传（用 phase） |
| `task_description` | str\|None | 否 | 任务描述，**同时传给 tier1 与 tier2 Agent** 做相关性判断（越具体越能过滤无关结果） | caller 缓存的 round-1 原文（跨轮 verbatim） |
| `call_count` | int | 否 | 当前阶段已调用知识库的次数；**仅 `call_count==0` 时返回 tier0 rules 正文**，>0 时 `phase_rule.content_mode="suppressed"` 且 `content=""` | caller 维护的轮次计数器（0 起步） |
| `seen_ids` | list[str]\|None | 否 | 前几轮已召回的知识 ID；本轮 tier1+tier2 候选都剔除，避免重复召回 | caller 累积的 id 列表 |
| `device_feedback` | str\|None | 否 | 前几轮生成代码的上板报错文本（compile/precision/runtime error），注入主 Agent 上下文 | caller 已截断的原文（50-200 字关键段） |


#### 返回结构

**顶层信封**（v5.2 — 主 Agent 编排,顶层 4 个诊断字段）：

```json
{
  "phase_rule": {
    "phase":             "correctness | precision | performance | all",
    "content_mode":      "inject | suppressed",       // call_count==0 → inject; >0 → suppressed
    "content":           "str",                        // 规则正文 markdown(suppressed 时为 "")
    "description":       "str",                        // ★ 强制约束告警语 —— cann-ask 把它抬到答案最顶
    "estimated_tokens":  "int",
    "rule_refs":         "list[{phase, version, full_page_id}]"
  },
  "ai_suggestion": "str | null",                       // 主 Agent 跨 tier 综述,内嵌 [id:xxx] 引用
  "agent_status":  "\"ok\" | \"degraded\" | \"disabled\"",
  "agent_turns":   "int | null",                       // 主 Agent 跑了几轮 retrieve(static)
  "sub_queries":   "list[str] | null",                 // 主 Agent 设计的所有 sub-query
  "static":  { "results": [...], "total": "int", "no_useful_results": "bool", "warning": "str | null" },
  "dynamic": { "results": [...], "total": "int", "no_useful_results": "bool", "warning": "str | null" },
  "warning":  "str (可选)  // 顶层跨层告警汇总,无告警时不出现"
}
```


**顶层诊断字段语义**（来自 `mcp-server/response_schema.py:25-28`,authoritative）：

| 字段 | 含义 |
|---|---|
| `ai_suggestion` | 主 Agent 跨 tier 合成的检索建议;**单一来源**,不再分 tier1/tier2;内嵌 `[id:xxx]` 引用可指 tier1 或 tier2 ID |
| `agent_status` | `"ok"` = 主 Agent 跑通,综述与两 tier results 都可信;`"degraded"` = 主 Agent 失败/超时,results 来自纯漏斗兜底;`"disabled"` = 本次未走 Agent（cfg 关闭 / query 为空 / phase_err / invalid intent） |
| `agent_turns` | 主 Agent 调 `retrieve(static)` 工具的轮数（`disabled` 时通常为 `None`） |
| `sub_queries` | 主 Agent 设计的所有 sub-query 列表(透明化检索路径,debug 用) |

**`phase_rule`（tier0 踩坑规则）字段**：

| 字段 | 类型 | 含义 |
|---|---|---|
| `phase` | str | 当前阶段（`correctness`/`precision`/`performance`） |
| `content_mode` | `"inject"` \| `"suppressed"` | `inject` = 返回规则正文；`suppressed` = 抑制（`call_count>0` 时） |
| `content` | str | 规则正文 markdown（`suppressed` 时为 `""`） |
| `description` | str | **强制约束告警语**，告诉下游模型这些规则必须严格遵守。**cann-ask 的核心职责是把它抬到答案最顶 `## ⚠️ 强制规则` section** |
| `estimated_tokens` | int | 规则正文 token 估计（`suppressed` 时 `0`） |
| `rule_refs` | list[{phase, version, full_page_id}] | 规则的完整页 ID 列表（可用 `wiki_get_page` 取全文） |

**`static`（tier1）/ `dynamic`（tier2）同构信封字段**（v5.2 简化 —— ai_suggestion / Agent 状态已抬到顶层）：

| 字段 | 类型 | 含义 |
|---|---|---|
| `results` | list[dict] | 检索结果项数组（详见下方 results 字段） |
| `total` | int | 召回总数（可能 > `len(results)`，仅返回 top-`limit`） |
| `no_useful_results` | bool | 主 Agent 判定本区无可用结果（true 时建议提示用户重述 query / 补充 device_feedback） |
| `warning` | str \| None | 本区告警（原样透传，不重试） |


**`static.results[i]` 字段**：

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | str | 知识 ID `{type}:{slug}`（例 `api_reference:datacopy-intf`）。**唯一锚点**，要正文必须 `wiki_get_page(ids=[id])` |
| `summary` | str | 简短摘要 |
| `score` | float | **本次 query 的相关性**（`rerank_score`，兜底到 `rrf_score`） |
| `tags` | list[str] | 页面标签 |
| `branch` | str | 固定 `"traditional"`（tier1 漏斗标识） |
| `extra` | dict | 内部分数：`{qValue, qDraft, qRefine, qIntent, rerankRank, rerankScore, rrfScore}`。`qValue` = **历史有用度**（Q-sort 主键）。客户端通常不读不展示 |

**`dynamic.results[i]` 字段**：

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | str | 知识 ID（例 `recipe:simd-perf-memory-access`） |
| `summary` | str | 简短摘要 |
| `scenario` | str | 适用场景描述（cann-ask 渲染时用作 `### {scenario}` 子标题） |
| `steps_outline` | list[str] | 修复步骤大纲（可能为空） |
| `cautions` | list[str] | 注意事项（可能为空） |
| `score` | float | 相关性 |
| `tags` | list[str] | 页面标签 |
| `branch` | str | 固定 `"dynamic"`（tier2 漏斗标识；与 tier1 的 `"traditional"` 对应） |
| `citations` | list[str] | 引用的其他知识 ID |
| `community_id` | str \| None | 社区聚类 ID（图谱探索用，cann-ask 单轮不展开） |
| `neighbors_top3` | list[str] | top-3 邻居 ID（cann-ask 单轮不展开） |

**重要不变量**：
- **`path` 字段已彻底移除** —— `id` 是唯一锚点，要正文必须 `wiki_get_page(ids=[id])`。不要从 id 文本猜路径
- **tier 由响应分区决定** —— `phase_rule`→tier0 / `static.results`→tier1 / `dynamic.results`→tier2。不要从 id 文本前缀反推
- **score 仅在各自 tier 内部降序** —— 两 tier 之间不可比（打分器不同），不要跨 tier 合并排序

#### 多轮约定

首次 `call_count=0` 取 tier0 规则；后续轮次：
- `call_count` 递增（每轮 +1）
- `seen_ids` 累积前几轮所有 `static.results[i].id` + `dynamic.results[i].id`，去重
- `device_feedback` 传最近一次上板报错（caller 已截断）

→ 规则不重复返回、已用知识不重复召回、tier2 据上板反馈调整召回。

### `wiki_get_page` —— 按 ID 批量取正文

**签名**：`wiki_get_page(ids: list[str]) -> dict`

**作用**：批量取知识正文（rule 全页 / static 页 / recipe 正文都通用）。**必须批量调用，不要循环。**

#### 入参字段

| 参数 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `ids` | list[str] | ✓ | 知识 ID 列表；来自 `wiki_search` 各分区的 `.id` 或 `phase_rule.rule_refs[].full_page_id` |

#### 返回结构

```json
{
  "pages": [
    {
      "id":          "api_reference:datacopy-intf",
      "frontmatter": {"title": "...", "tags": [...], ...},
      "content":     "完整 markdown 正文（含 frontmatter section）",
      "qValue":      0.73,
      "source":      "..."
    }
  ],
  "errors": [
    {"id": "operator:nonexistent", "error": "id not found"}
  ]
}
```

| 字段 | 类型 | 含义 |
|---|---|---|
| `pages[i].id` | str | 知识 ID（与请求 ids 对应） |
| `pages[i].frontmatter` | dict | 已解析的 YAML frontmatter（含 `title`/`tags`/...）；cann-ask 渲染 References 时取 `frontmatter.title` |
| `pages[i].content` | str | 完整 markdown 正文（含 frontmatter section） |
| `pages[i].qValue` | float | server 端 Q 值；**客户端不读不展示** |
| `pages[i].source` | str (可选) | 来源标识（debug 用） |
| `errors[i]` | dict | 软失败列表；个别 id 失败不阻塞 `pages[]` 其余项；若未解析 id 影响覆盖范围，在答案中提一句 |

### `wiki_get_index` —— [已弃用]

server 已弃用,不要调用,改用 `wiki_search + wiki_get_page`。响应携带 `{deprecated: true}` 字段。

### `wiki_help` —— 拿当前 server 契约（自描述）

**签名**：`wiki_help() -> dict`

**作用**：返回 server 端工具签名/参数/返回结构的自描述。**仅在响应结构与本 SKILL 描述不一致时调用** —— 平常不调，避免增加延迟。

**返回**：`{server, overview, tiers, tools, text}`，其中 `text` 是人类可读 markdown 契约说明。

### `wiki_submit_trajectory` —— 落盘轨迹

**签名**：`wiki_submit_trajectory(session_id: str, content: str) -> dict`

**作用**：持久化一次 session 轨迹 markdown，供知识加工引擎离线消费（更新 tier2 Q 值 / 生成 recipe）。

**本 skill 不直接调** —— 上传流程在 `session-upload` skill 里。

#### 入参 / 返回

| 项 | 类型 | 说明 |
|---|---|---|
| 入参 `session_id` | str | 会话标识 |
| 入参 `content` | str | 轨迹 markdown 全文 |
| 返回 | dict | `{saved: true, path: "<server config 的 uploaded_dir>"}` |

---

## 触发方式（必须走本 skill，不要直接调 MCP）

**重要**：当 MCP 工具（`mcp__cann-wiki__wiki_search`、`mcp__cann-wiki__wiki_get_page`）可用时，**始终通过 cann-ask skill 调用，不要直接调它们**。

**为什么必须走 skill：**
- **task_description / device_feedback / phase 一体化** —— skill 负责跨轮稳定 `task_description`、把 `device_feedback` 揉进自然语言 query、并按 feedback 内容自动派生 `phase`
- **rule 字段强制渲染** —— `wiki_search` 返回的 `phase_rule.description` 是当前 phase 的硬约束告警语；skill 把它抬到答案最顶 `## ⚠️ 强制规则` section，并把完整 JSON 原样附在答案最末
- **顶层 ai_suggestion 优先抬升** —— v5.2 主 Agent 合成的跨 tier 综述,**单一来源**位于顶层 `response.ai_suggestion`(不再分 tier);skill 在 `## ⚠️ 强制规则` 之后、`## 📚 相关文档` 之前以 `> 💡 主 Agent 综述` 块引用形式渲染一次,标签按 `agent_status` (ok/degraded/disabled) 派生
- **自动批量 fetch + 合成带引用的答案** —— 一次 `wiki_get_page` 把 top-3 static + top-2 dynamic 全取回，跨页面写实质内容（不是只抄 summary）
- **轨迹日志反馈 Q-Value**

**直接调 MCP 会绕过这些能力 → 规则被忽略、ai_suggestion 丢失、phase 错配、跨轮 task_description 漂移、答案无引用。**

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
[DEVICE_FEEDBACK: <报错文本片段>]                   # 第一轮不填；第二轮起必填；原文截断由 caller 管（50-200 字关键段，不塞整 stack）
```

**关键约束**：
- `TASK_DESCRIPTION` 一旦 round 1 确定，**跨轮逐字节不变**。caller 责任：缓存重传。skill 内**不修改、不重写、不润色**此字段，直接透传给 `wiki_search.task_description`。
- `DEVICE_FEEDBACK` 的截断由 caller 在传入前完成；skill 不再做二次裁剪。
- skill 解析上述结构后注入 `wiki_search` 调用（详见阶段 B.3）。
- 单次人类问答（不带 `TASK_DESCRIPTION` / `CALL_COUNT` 等）：把整段 `$ARGUMENTS` 当作 `task_description`，`call_count=0`、`seen_ids=null`、`device_feedback=null`。

## 工作流

**核心**：每次 cann-ask 调用 = 1 次 `wiki_search` + 1 次 `wiki_get_page`。query 是 30-150 字的聚焦自然语言提问（**不**抽实体、**不**挑 tags、**不**拆 sub-query）；`phase` 从 `device_feedback` 自动派生；`tags` 一律 `[]`；tier2 由 server 主 Agent 自动预跑(v5.2 已无 `include_dynamic` 客户端开关)。

### 阶段 B：构造 query + 决定 phase + 单次检索

#### B.1 构造 query（自然语言，30-150 字软约束）

> **保持用户原始语言**（中文 task 传中文 query，英文 task 传英文）。Wiki 语料以中文为主，翻译会显著降召回。

| 场景 | query 怎么生成 |
|---|---|
| **round 1**（`device_feedback` 为空） | 把 `task_description` paraphrase 成一句聚焦的自然语言提问，**不要整段 dump** —— 把"总目标"重写成"本轮想查清楚什么"。<br>例：`task_description` ≈ "实现 gemm_add_relu，910B，fp16，权重 NZ 排布，要求 ..." → query 写 "在 910B 上用 fp16 实现 gemm_add_relu，矩阵乘融合激活的 tiling 和写法要点是什么" |
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
  tags:             [],                                            # 显式空数组，server 走全量召回
  type:             null,                                          # server 端 type→domain (全库 ascendc)，无效
  limit:            3,
  task_description: "<caller 缓存的 round-1 原文，跨轮 verbatim>",
  call_count:       <int>,                                         # caller 传入；单次人类问答 = 0
  seen_ids:         [...] | null,                                  # caller 传入；单次人类问答 = null
  device_feedback:  "<caller 已截断的上轮报错原文>" | null,           # 第一轮可空；第二轮起必填
)
```

各入参语义详见 §"MCP 工具契约详解" → wiki_search 入参表。

> ℹ️ **tier2 由 server 预跑** —— v5.2 移除了 `include_dynamic` 参数,主 Agent 一次同时编排 tier1 + tier2;客户端不再控制。若 `dynamic.results == []`,通常是主 Agent 判定本区无可用 recipe(看 `dynamic.no_useful_results`)而非未跑。

> ⚠️ `call_count == 0` 才返 tier0 规则正文；第二轮起 `phase_rule.content_mode = "suppressed"` 且 `content = ""`，渲染时整段跳过（参见阶段 D）。

### 阶段 C：批量 fetch 页面

**单次批量调用** —— 把 `static.results` top-3 和 `dynamic.results` top-2 的 id 合并到一个 list，一次 `wiki_get_page(ids=[...])` 取回所有正文（**不要**分两次调，也不要按 id 循环）：

```python
static_ids  = [r["id"] for r in response["static"]["results"][:3]]
dynamic_ids = [r["id"] for r in response["dynamic"]["results"][:2]]  # round 1 通常为空
wiki_get_page(ids=static_ids + dynamic_ids)
```

返回字段语义详见 §"MCP 工具契约详解" → wiki_get_page 返回结构。

- `frontmatter.title` → 阶段 D References 列表的 title
- `content` → 阶段 D 各 tier section 主体的实质内容来源（不是只抄 summary）
- `errors[]` 软失败 → 个别 id 解析失败时在答案末尾提一句

### 阶段 D：合成答案

按下面顺序输出。**每段都基于 `wiki_get_page` 返回的页面正文写实质内容**（不是只抄 summary）。完整版式见下方"输出格式"样例。

1. **`## ⚠️ 强制规则`**（tier0 phase_rule）—— **核心职责，必须最顶部渲染**，详见下方"rule_description 渲染细则"
2. **顶层 ai_suggestion 块**（v5.2 单一跨 tier 综述）—— 若 `response.ai_suggestion` 非空,在 `## 📚 相关文档` 之前以 `> 💡 **主 Agent 综述**` 块引用渲染一次,保留 `[id:xxx]` 引用原样。标签按 `response.agent_status` 派生(`ok` / `degraded` 兜底序 / `disabled` Agent off)。详见下方"ai_suggestion 渲染细则"
3. **`## 📚 相关文档`**（tier1 static）—— 基于 `wiki_get_page` 返回的 static page 正文写结构化答案，带 `[Source: <id>]` 内联引用
4. **`## 🔧 实践 recipe`**（tier2 dynamic）—— 内含子结构：
   - 若 `dynamic.results` 为空：**整段隐藏**，不留空标题
   - 主体：每条 recipe 用 `### {scenario}` 三级标题（取自 `dynamic.results[i].scenario`），下接基于 recipe page 正文的实质内容
5. **References** —— 单一列表，tier 前缀 📚（tier1）/ 🔧（tier2），title 取 `wiki_get_page` 的 `frontmatter.title`
6. **告警 / 状态汇总**（按需）—— 顶层 `warning` / `static.warning` / `dynamic.warning` / `no_useful_results=true` 提示 / `agent_status==degraded`/`disabled` 提示，详见下方"告警状态渲染细则"
7. **诊断 JSON 附末** —— `phase_rule` + `agent_status` + `agent_turns` + `sub_queries`,详见下方"rule_description 渲染细则"
8. **footer** —— 见阶段 E

**引用规则**：每个事实必须**内联**引用 `[Source: <id>]`，紧跟事实写而不放到末尾；多来源 `[Source: <id1>, <id2>]`；id 取 `wiki_get_page` 返回值（与 `static.results[i].id` / `dynamic.results[i].id` 一致），不要编造路径。

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

**诊断 JSON 附末**：无论 `content_mode` 是 `inject` 还是 `suppressed`，**都要**把完整 `phase_rule` + v5.2 顶层诊断字段（`agent_status`/`agent_turns`/`sub_queries`）原样附在答案最末的独立 ```json fenced block 里：

```json
{
  "phase_rule":    { ... server 返回原文 ... },
  "agent_status":  "ok" | "degraded" | "disabled",
  "agent_turns":   <int | null>,
  "sub_queries":   [...] | null
}
```

用途：trajectory 上报、phase_rule 命中统计、主 Agent 行为审计、eval 侧解析。

#### ai_suggestion 渲染细则

v5.2 主 Agent 把跨 tier 综述抬到**顶层** `response.ai_suggestion`（单一来源,内嵌 `[id:<完整ID>]` 引用,可指 tier1 或 tier2 ID）。**优先级高 —— 是 server 端"读过 top-N 之后的提炼"，比 cann-ask 这边只看 summary 更准。**

**渲染规则**：

- 若 `response.ai_suggestion` 非空 → 在 `## ⚠️ 强制规则` 之后、`## 📚 相关文档` 之前**渲染一次**(不再分 tier1/tier2 重复渲染)：

  ```markdown
  > 💡 **{label}**
  >
  > {response.ai_suggestion 原文，保留 [id:xxx] 内联引用不改写}
  ```

  `{label}` 按 `response.agent_status` 派生：

  | `agent_status` | `{label}` |
  |---|---|
  | `"ok"` | `主 Agent 综述`（主 Agent 跨 tier 合成,可信） |
  | `"degraded"` | `检索建议`（主 Agent 兜底序,相关性可能下降） |
  | `"disabled"` | `检索建议`（Agent off,纯漏斗序） |

- 若 `response.ai_suggestion` 为 `null` / 空字符串 → 整个 `> 💡` 块不渲染
- 渲染位置：**强制规则之后、tier 主体之前**,让下游 codegen 模型先读到精炼建议,主体的 page-body 合成在下方作为补充细节
- **`[id:xxx]` 引用原样保留**，与 References 列表 ID 对齐，不要改成 `[Source: xxx]` 或其他变体

#### 告警状态渲染细则

按下面顺序在 References 之后追加（有则渲染，无则跳过）：

| 场景 | 触发 | 渲染 |
|---|---|---|
| 顶层告警 | `response.warning` 非空 | `> ⚠️ **Server warning**: {warning}` |
| tier1 告警 | `static.warning` 非空 | `> ⚠️ **Tier1 warning**: {static.warning}` |
| tier2 告警 | `dynamic.warning` 非空 | `> ⚠️ **Tier2 warning**: {dynamic.warning}` |
| tier1 无可用 | `static.no_useful_results == true` | `> ℹ️ Tier1 主 Agent 判定本区无可用结果，建议重述 query` |
| tier2 无可用 | `dynamic.no_useful_results == true` | `> ℹ️ Tier2 主 Agent 判定本区无可用 recipe，建议补充 device_feedback 关键信息` |
| 主 Agent 兜底 | `response.agent_status == "degraded"` | `> ⚠️ 主 Agent 失败/超时，两 tier results 来自漏斗兜底序，相关性可能下降 (turns: {agent_turns})` |
| Agent off | `response.agent_status == "disabled"` | `> ℹ️ 本次未走主 Agent (server cfg / 输入异常);results 为纯漏斗序` |

**原样透传**，不重试不降级。v5.2 把原 per-tier 的 `agent_filtered` / `degraded` bool 合并为顶层 `agent_status` 枚举,因此 tier1/tier2 共享同一个 Agent 状态。

### 阶段 E：footer 提示上传轨迹

答案末尾加一句：`💡 用 `/session-upload` 把本次会话上传到 Wiki`。上传流程在 `session-upload` skill 里，本 skill 不直接调 `wiki_submit_trajectory`。

## 输出格式

```markdown
## ⚠️ 强制规则

⚠️ 强制约束：phase_rule 中列出的踩坑规则是当前阶段的硬性要求，生成 AscendC kernel 时必须逐条严格遵守；违反将导致编译失败、精度不达标或性能劣化。

1. float/uint32 互转必须经 int32 中转，禁止直接 static_cast。
2. DataCopy 后必须 EnQue/DeQue 配对，避免读未同步数据。
3. ...

> 💡 **主 Agent 综述**
>
> 关于 910C 上 fp16 gemm_add_relu，推荐先看 [id:api_reference:matmul-api] 的 tiling 模式，再结合 [id:practice:fp16-fusion-pattern] 的融合写法；针对 DataCopy block size mismatch，[id:recipe:datacopy-block-align] 给出的对齐校验步骤最直接可用。

## 📚 相关文档

[基于 tier1 static 页面正文的结构化答案，带 [Source: <id>] 引用]

## 🔧 实践 recipe

### {scenario_1}

[基于 tier2 recipe 页面正文的实质内容] [Source: recipe:simd-perf-memory-access]

---

**References:**
- 📚 api_reference:matmul-api — <frontmatter.title>
- 📚 practice:fp16-fusion-pattern — <frontmatter.title>
- 📚 synthesis:api-reference-master-index — <frontmatter.title>
- 🔧 recipe:datacopy-block-align — <frontmatter.title>
- 🔧 recipe:simd-perf-memory-access — <frontmatter.title>

> ⚠️ **Server warning**: ...  （仅在 server 返回 warning 时出现）
> ℹ️ Tier2 LLM 判定本区无可用 recipe，建议补充 device_feedback 关键信息  （仅在 no_useful_results=true 时）

```json
{
  "phase_rule": {
    "phase": "correctness",
    "content_mode": "inject",
    "content": "...",
    "description": "⚠️ 强制约束：phase_rule 中列出的踩坑规则是当前阶段的硬性要求……",
    "estimated_tokens": 0,
    "rule_refs": [{"phase": "correctness", "version": "...", "full_page_id": "rule:correctness"}]
  },
  "agent_status": "ok",
  "agent_turns": 2,
  "sub_queries": ["gemm_add_relu fp16 tiling", "DataCopy block align"]
}
```

💡 用 `/session-upload` 把本次会话上传到 Wiki
```

## 注意事项

- **自然语言 query，单次检索** —— 一次 cann-ask = 1 次 `wiki_search` + 1 次 `wiki_get_page`；query 是 30-150 字的聚焦自然语言提问，**不**抽实体、**不**挑 tags、**不**拆 sub-query
- **task_description 跨轮 verbatim 不变** —— caller 责任：round 1 起逐字节缓存重传；skill 内**不修改、不重写、不润色**
- **phase 从 device_feedback 自动派生** —— round 1 默认 `correctness`；round N 按 feedback 内容映射到 `correctness` / `precision` / `performance`。**禁止** `phase=all`
- **tags 暂置空 `[]`** —— server 走全量召回；未来若启用 tag 召回再填
- **tier2 由 server 预跑** —— v5.2 已无 `include_dynamic` 客户端开关;主 Agent 一次同时编排 tier1+tier2;`dynamic.results == []` 看 `dynamic.no_useful_results` 判断是"无可用"而非"未跑"
- **rule_description 强制抬升** —— `phase_rule.content_mode == "inject"` 时渲染 `## ⚠️ 强制规则` section 到答案最顶；`suppressed` 时整段跳过；完整 `phase_rule` + `agent_status`/`agent_turns`/`sub_queries` JSON 无论何种 content_mode 都附在答案最末
- **顶层 ai_suggestion 单次渲染** —— v5.2 主 Agent 跨 tier 综述抬到顶层 `response.ai_suggestion`,在强制规则之后、tier 主体之前以 `> 💡 主 Agent 综述` 块引用渲染**一次**;标签按 `agent_status` 派生(ok / degraded 兜底序 / disabled Agent off);`[id:xxx]` 引用原样保留
- **告警状态机器可判** —— `agent_status` (ok/degraded/disabled) + per-tier `no_useful_results` + `warning` 由 server 标注；按 §"告警状态渲染细则" 透传，不重试不降级
- **path 字段已彻底下沉** —— `id` 是唯一锚点，绝不暴露 / 使用 `path`；批量 fetch 时 `static_top_3 + dynamic_top_2` 合并到**一次** `wiki_get_page` 调用
- **score 仅 tier 内可比** —— `static.score` 与 `dynamic.score` 用不同打分器，不要跨 tier 合并排序
- **tier 由响应分区决定** —— 不要从 id 文本前缀（`{type}:{slug}`）反推
- **query 保持原始语言** —— wiki 以中文为主，翻译降召回
- **device_feedback 截断由 caller 管** —— skill 不再做二次裁剪
- **不要编造** —— 两 tier 都空或 `warning` 非空时明确告知，不猜。MCP 不可达时报错，不阻塞本地功能

## 错误处理

| 场景 | 处理 |
|------|------|
| MCP Server 未启动 | 提示启动命令 |
| `wiki_search` 响应缺 v5.2 顶层字段（`phase_rule`/`ai_suggestion`/`agent_status`/`static`/`dynamic`） | 调 `wiki_help()` 拿当前契约，告诉用户 server 版本不匹配；不要强解析 |
| `wiki_search` 结果为空（`static` 和 `dynamic` 都空），或响应携带 `warning` | 把 warning 文本原样转给用户；建议调整 query 措辞 |
| `static.no_useful_results == true` | 渲染 `> ℹ️ Tier1 主 Agent 判定本区无可用结果...` 告警；results 不删（让用户判断） |
| `response.agent_status == "degraded"` | 渲染 `> ⚠️ 主 Agent 失败/超时...` 告警；两 tier results 都来自漏斗兜底序,不删 |
| `response.agent_status == "disabled"` | 渲染 `> ℹ️ 本次未走主 Agent (server cfg / 输入异常)...` 告警；results 为纯漏斗序,不删 |
| `wiki_get_page` 部分失败 | 列出 `errors[]` 中未解析的 id；用 `pages[]` 继续合成 |
| `phase_rule.content_mode == "suppressed"` | graceful 跳过顶部 `## ⚠️ 强制规则` section；JSON 附末仍保留 |
| `wiki_submit_trajectory` 失败 | 不在本 skill 处理，走 `session-upload` skill |
| 网络超时 | "超时，检查 MCP Server 状态" |
