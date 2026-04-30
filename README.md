# ascendc-wiki-skills

AscendC Kernel Wiki 知识检索和会话轨迹上传的 LLM Agent skills。

## 快速安装

```bash
# 安装到 Claude Code
npx skills@latest add qianbi1999/ascendc-wiki-skills -a claude-code

# 安装到 OpenCode
npx skills@latest add qianbi1999/ascendc-wiki-skills -a opencode
```

指定 `-a` 参数的好处：直接通过 `/setup-ascendc-wiki`、`/wiki-query`、`/session-upload` 使用 skill。
（Claude Code 有 TUI 补全，OpenCode 需手动输入完整名称）

安装后运行 `/setup-ascendc-wiki` 配置 MCP 连接。

## 重要提示：先运行 Setup！

**使用 wiki-query 或 session-upload 前，必须先运行 `/setup-ascendc-wiki` 配置 MCP 连接。**

Setup skill 会：
1. 检查 MCP Server 是否运行
2. 检测你的 agent 类型（OpenCode/Claude Code/Cursor）
3. 创建 MCP 配置文件
4. 验证 MCP 工具是否可用

## Skills

| Skill | 描述 | 需要先运行 setup |
|-------|------|------------------|
| **setup-ascendc-wiki** | 配置 MCP 连接 | 否（第一个运行） |
| **wiki-query** | 通过 MCP 语义检索 Wiki | 是 |
| **session-upload** | 上传会话轨迹 | 是 |

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│  你的 Agent（OpenCode/Claude Code/Cursor）                   │
│  ├── MCP 配置：.opencode/opencode.json 或 .mcp.json          │
│  └── Skills：setup-ascendc-wiki, wiki-query, session-upload │
└───────────────────────────┬─────────────────────────────────┘
                            │ MCP 协议
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  MCP Server（独立仓库）                                       │
│  ├── 端口：localhost:3000                                    │
│  ├── 工具：wiki_search, wiki_get_page, wiki_submit_trajectory │
│  └── 检索器：子 Agent + wiki-query skill                      │
└─────────────────────────────────────────────────────────────┘
```

**核心概念**：MCP Server 和 Skills 是**分离的**：
- **MCP Server** 独立运行（用户管理）
- **Skills** 安装在 agent 中（告诉 agent 如何使用 MCP 工具）
- **Setup skill** 通过配置 MCP 连接桥接两者

## MCP Server 启动

Agent 使用前，MCP Server 必须先运行。

在 AscendC-Kernel-Wiki 仓库根目录启动：

```bash
cd mcp-server
IS_SANDBOX=1 python server.py --port 3000 --host 0.0.0.0
```

启动成功输出：
```
[mcp 2026-04-29 23:55:00] 服务启动: 0.0.0.0:3000 heartbeat=1800s
```

**注意：**
- `IS_SANDBOX=1`：root 用户必须显式声明，否则 Claude CLI 拒绝执行
- 非 root 用户可省略 `IS_SANDBOX=1`
- 服务必须在仓库根（与 `wiki/`、`raw/` 平级）启动

## 使用流程

```
1. 安装 skills（见上方快速安装）
2. 启动 MCP Server：cd mcp-server && IS_SANDBOX=1 python server.py --port 3000
3. 运行 setup：/setup-ascendc-wiki
4. 重启 agent
5. 使用 wiki-query："AscendC 编程模型是什么？"
6. 上传轨迹：/session-upload
```

## 常见问题

| 问题 | 解决方案 |
|------|----------|
| wiki_search 未找到 | 先运行 `/setup-ascendc-wiki` |
| MCP 连接失败 | 检查 MCP Server 是否运行，尝试调用 `wiki_get_index()` |
| 配置未加载 | setup 后重启 agent |
| Skills 未触发 | 检查 skill 激活关键词 |

## 目录结构

```
ascendc-wiki-skills/
├── .claude-plugin/
│   └── plugin.json
├── skills/
│   └── wiki/
│       ├── setup-ascendc-wiki/
│       │   └── SKILL.md          ← 第一个运行
│       ├── wiki-query/
│       │   └── SKILL.md
│       └── session-upload/
│           └── SKILL.md
├── README.md
└── LICENSE
```

## License

MIT