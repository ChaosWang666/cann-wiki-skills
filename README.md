# cann-wiki-skills

AscendC Kernel Wiki 知识检索和会话轨迹上传的 LLM Agent skills。

**新手开箱即用**：安装 skills → 运行 `/setup-cann-wiki` → `/exit` 重启 → 开始提问！

---

## 快速开始（5 分钟上手）

### 1. 安装 Skills

```bash
# OpenCode
npx skills@latest add qianbi1999/cann-wiki-skills -a opencode

# Claude Code
npx skills@latest add qianbi1999/cann-wiki-skills -a claude-code
```

### 2. 配置 MCP 连接

在 agent 中运行：
```
/setup-cann-wiki
```

按提示选择 agent 类型和端口（默认 **3000**，如需其他端口可手动输入如 3001）。

### 3. **重启 Agent**（必须！）

```
/exit  # 退出当前会话（OpenCode 和 Claude Code 都支持）
```

然后重新启动 agent。不重启 MCP 工具无法使用。

### 4. 开始使用

```
/cann-ask AscendC 编程模型是什么？
/cann-ask 帮我写一个 Add 算子
/cann-ask Matmul 高阶 API 怎么用？

/session-upload  # 上传当前会话轨迹
```

---

## Skills 说明

| Skill | 命令 | 用途 | 首次使用 |
|-------|------|------|---------|
| **setup-cann-wiki** | `/setup-cann-wiki` | 配置 MCP 连接 | ✓ 必先运行 |
| **cann-ask** | `/cann-ask <问题>` | 检索 Wiki 知识（合成答案 + 引用） | 需要 setup |
| **session-upload** | `/session-upload` | 上传会话轨迹 | 需要 setup |

---

## 辅助脚本

### `scripts/find-session.sh` — 按关键词检索并渲染本地 session

在 Claude Code session JSONL 中检索关键词，命中后调用 `cc_convert.py` 渲染成 Markdown。

```bash
# 默认从 ~/.claude/projects/<encoded-pwd>/ 检索（pwd 路径中 '/' 换成 '-'）
./scripts/find-session.sh "multi-head self-attention"

# 也可指定其他 session 目录
./scripts/find-session.sh "kernel fusion" /path/to/session/dir
```

- 仅检索 `*.jsonl`；目录下没有 jsonl 文件时直接提醒退出
- 命中的 session 会渲染到 `$PWD/sessions-<keyword-slug>/`（已加入 `.gitignore`）

---

## 完整使用示例

### 示例 1：查询知识

**用户输入**：
```
/cann-ask AscendC 编程模型是什么？
```

**Agent 响应**：
```
我来帮你查询 AscendC 编程模型相关知识...

[调用 wiki_search → wiki_get_page → 合成答案]

Answer:

AscendC 编程模型采用 AI Core 三级流水线架构：
- CopyIn: GM → UB 数据搬运
- Compute: UB 上矢量/矩阵计算
- CopyOut: UB → GM 结果回写

[Source: wiki/static/ascendc/guide/concepts/programming-model.md]

完整内容请查看 Wiki 页面...
```

### 示例 2：算子开发

**用户输入**：
```
/cann-ask 帮我写一个 Add 算子
```

**Agent 响应**：
```
[检索 Elementwise 模式 + 矢量算子实践]

Answer:

AscendC 实现 Add 算子有两种方式：

方式一：基础手工实现
- CopyIn/Compute/CopyOut 三阶段流水线
- 手动管理队列和内存

方式二：ElementwiseSch16B 模式（推荐）
- DAG 表达式自动处理流水线
- 代码：auto dag = Placeholder::In0 + Placeholder::In1

[完整代码见 wiki/static/ascendc/guide/practice/vector-programming-basics.md]
```

---

### 示例 3：上传轨迹

**用户输入**：
```
/session-upload
```

**Agent 响应**：
```
检测到 Claude Code agent...
转换会话轨迹...
上传到 raw/sessions/uploaded/<session-id>.md

✓ 上传完成
Session: xxx-xxx-xxx
行数: 818 行
关键词: AscendC (35 次)
```

---

## 架构概览

```
┌────────────────────────────────────┐
│  Agent (Claude Code / OpenCode)    │
│  ├── Skills (本仓库)               │
│  │   ├── setup-cann-wiki       │ ← 配置 MCP 连接
│  │   ├── cann-ask              │ ← 调用 MCP 工具
│  │   └── session-upload           │ ← 调用 MCP 工具
│  └── MCP Config                    │
│      ├── .mcp.json (Claude Code)   │
│      └── .opencode/opencode.json   │
└────────────────┬───────────────────┘
                 │ MCP Protocol
                 ↓
┌────────────────────────────────────┐
│  MCP Server (管理员运维)            │
│  ├── wiki_search                   │
│  ├── wiki_get_page                 │
│  └── wiki_submit_trajectory        │
└────────────────────────────────────┘
```

---

## 目录结构

```
cann-wiki-skills/
├── .claude-plugin/
│   └── plugin.json                  ← Skills 插件配置
├── skills/
│   └── wiki/
│       ├── setup-cann-wiki/
│       │   └── SKILL.md              ← 第一个运行
│       ├── cann-ask/
│       │   └── SKILL.md              ← 知识检索（人类问答入口）
│       └── session-upload/
│           ├── SKILL.md              ← 轨迹上传（检测 + 调度 + 上传）
│           └── scripts/
│               ├── cc_convert.py     ← Claude Code 转换器
│               ├── oc_convert.py     ← OpenCode 转换器
│               └── mcp_upload.py     ← HTTP MCP 上传器（绕过模型 token cap）
├── scripts/
│   └── find-session.sh              ← 按关键词检索并渲染本地 session
├── README.md                         ← 本文件
└── LICENSE
```

---

## License

MIT