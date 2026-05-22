---
name: setup-cann-wiki
description: "为 CANN Wiki 系列 skill 配置 MCP 连接。首次使用 cann-ask 或 session-upload 前先运行 `/setup-cann-wiki`。"
---

# Setup CANN Wiki Skills

为 cann-ask 和 session-upload skills 搭建所需的 MCP 配置。

这是一个 prompt 驱动的 skill：先探测，呈现缺什么，与用户确认后再写入。

## 前置检查

setup 之前，检查：

1. **MCP Server 在跑吗？**
   - 尝试调用 `wiki_search("test", limit=1)` MCP 工具（无副作用的探测）
   - 或检查 3000 端口是否在监听：`curl -sI http://localhost:3000/mcp | head -3`（401/406 都是健康响应 —— 说明 streamable-http endpoint 已起，只是裸请求缺 MCP header）
   - 没在跑 → 提示用户先启动

2. **Agent MCP 配置文件存在吗？**
   - OpenCode：`.opencode/opencode.json`
   - Claude Code：`.mcp.json` 或 `claude_desktop_config.json`
   - 缺失就创建

3. **MCP 工具可用吗？**
   - 必需的工具：`wiki_search`、`wiki_get_page`（按 `ids` 批量）、`wiki_help`、`wiki_submit_trajectory`
   - 配置完成后，确认这四个工具出现在 agent 的 MCP 工具列表里

## 流程

### Step 1：检查 MCP Server 状态

确认 MCP Server 在运行：

1. 检查 3000 端口是否监听：
   ```bash
   curl -sI http://localhost:3000/mcp | head -3
   ```
   401 / 406 都是健康响应 —— 说明 streamable-http endpoint 已起。

2. **拉一次 server 自描述**（HTTP，无需 MCP 配置就能跑）：
   ```bash
   curl -s http://localhost:3000/help | head -40
   ```
   返回 markdown 说明（默认）；`curl -s 'http://localhost:3000/help?format=json'` 拿结构化 JSON。把工具列表 echo 给用户看一眼，确认包含 `wiki_search` / `wiki_get_page` / `wiki_help` / `wiki_submit_trajectory`。对不上就先停下，提示用户检查 server。

3. 或者（agent 配置完成后）直接调用 MCP 工具：
   ```
   wiki_search("test", limit=1)         # 探活：成功即返三分区响应
   wiki_help()                          # 拉 server 自描述的结构化版
   ```

**如果 server 没跑**：
- 问用户："MCP Server 没在运行。AscendC-Kernel-Wiki 仓库可用吗？"
- 确认该仓库的 `<repo_root>/config.yaml` 配置了 `search.mode`（`local` / `openai-api` / `claude-agent`）；业务配置（mode / model / api_key）只从 `config.yaml` 读取，不走 CLI 参数或环境变量。
- 给出启动命令：
  ```bash
  # 在 AscendC-Kernel-Wiki 仓根目录（有 wiki/ 和 raw/ 的地方）
  cd mcp-server
  IS_SANDBOX=1 python server.py --port 3000 --host 0.0.0.0

  # 非 root 用户可以不带 IS_SANDBOX=1
  ```
- 等用户启动后再继续

### Step 2：检测 Agent 类型

确认用户在用哪个 agent：

| Agent | 配置文件位置 | 最便捷的安装方式 |
|-------|--------------|------------------|
| OpenCode | workspace 下的 `.opencode/opencode.json` | 编辑 JSON（见 Step 3） |
| Claude Code (CLI) | 项目根下的 `.mcp.json` | **`claude mcp add` 一行命令**（首选） |
| Claude Code (Desktop) | app support 下的 `claude_desktop_config.json` | 编辑 JSON（见 Step 3） |
| Cursor | 编辑器内 MCP 设置 | 编辑器 UI |

**快速检测信号**：
- `command -v claude` → 装了 Claude Code CLI
- `command -v opencode` → 装了 OpenCode CLI
- `.opencode/opencode.json` 存在 → OpenCode workspace
- `.mcp.json` 存在 → Claude Code 项目已有 MCP 配置
- 当前在 Claude Code 里？ 检查 `~/.claude/projects/<把斜杠换成横杠的-pwd>/` 是否存在

优先选用户当前调用本 skill 所在的 agent。

### Step 3：呈现配置

向用户展示所需配置：

**OpenCode**（`.opencode/opencode.json`）：
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "cann-wiki": {
      "type": "remote",
      "url": "http://localhost:3000/mcp",
      "enabled": true
    }
  }
}
```

**Claude Code CLI** —— 首选一行命令（自动写 `.mcp.json`）：

```bash
# 项目级（通过 .mcp.json 提交进仓）
claude mcp add --transport http --scope project cann-wiki http://localhost:3000/mcp

# 或用户级（跨项目，存在用户配置里）
claude mcp add --transport http --scope user cann-wiki http://localhost:3000/mcp
```

也可以手写等价的 `.mcp.json`：
```json
{
  "mcpServers": {
    "cann-wiki": {
      "type": "http",
      "url": "http://localhost:3000/mcp"
    }
  }
}
```

执行完命令（或保存文件）后，重启 agent（`/exit`），用以下命令验证：
```bash
claude mcp list           # 应该看到 cann-wiki 处于 connected 状态（Claude Code）
```

**Claude Desktop**（`claude_desktop_config.json`）：
```json
{
  "mcpServers": {
    "cann-wiki": {
      "command": "python",
      "args": ["path/to/AscendC-Kernel-Wiki/mcp-server/server.py", "--port", "3000"],
      "env": {
        "IS_SANDBOX": "1"
      }
    }
  }
}
```

注意：
- 业务配置（search mode / model / api key）只从 `<repo_root>/config.yaml` 读取，不要给 args 加 `--retriever` 也不要给 env 加 `EMBEDDING_MODEL`。
- `IS_SANDBOX=1` 只在 root 部署时需要；非 root 可以不带。

解释每种模式：
- **Remote 模式**：连接已经在跑的 MCP server（推荐）
- **Local 模式**：Claude Desktop 启动时自动起 MCP server（需要 server.py 的完整路径）

### Step 4：确认并写入

询问用户：
- 在用哪个 agent
- 哪种模式（remote / local）
- 用 local 模式时 MCP Server 的路径

然后写入对应的配置文件。

### Step 5：必须重启

**关键：配置后用户必须重启 agent。**

即使 `claude mcp list` 显示 "Connected"，不重启 MCP 工具就是不能用。

明确告诉用户：
```
## ⚠️ 配置完成，必须重启！

配置文件已写入，但 MCP 工具需要重启才能生效。

### 必须操作
1. **退出当前 agent 会话**：输入 `/exit`（OpenCode 和 Claude Code 都支持）
2. **重新启动 agent**
3. 验证 MCP 工具可用：
   - Claude Code：运行 `/mcp` 应显示 cann-wiki
   - OpenCode：MCP 工具应出现在工具列表中

### 不重启的后果
- `/mcp` 显示 "No MCP servers configured" (Claude Code)
- wiki 工具无法调用

**请现在执行 `/exit` 重启**。
```

**不要**在用户没重启前声称 setup 完成。

## 注意事项

- **MCP Server 必需** —— Server 不跑就用不了 wiki skills。本 skill 仅做存活探测 + 工具集核对，响应细节由 `cann-ask` 处理。
- **行为由 server 端配置决定** —— Search mode / embedding model / API key 只在 `<repo_root>/config.yaml` 里，没有客户端开关。
- **配置是客户端级别的** —— 不存在 skill 里，存在 agent 配置里
- **每个 agent 配一次** —— 仅在切换 agent 或 MCP endpoint 变化时重跑
- **Server 与 client 独立** —— MCP server 独立运行，agent 主动连接
- **端口非 3000 也无需额外设环境变量** —— `session-upload` 的上传脚本会自动从你这里写的 `.mcp.json` / `.opencode/opencode.json` 里 `cann-wiki` 条目的 `url` 拾起端口；cann-ask 走 agent 内置 MCP 客户端，本来就跟随这份配置。

## 错误处理

| 场景 | 处理 |
|------|------|
| MCP Server 没在跑 | 提示启动命令，等用户操作 |
| 配置文件已存在 | 询问是更新还是跳过 |
| 未知 agent 类型 | 询问用户具体类型 |
| 配置写入失败 | "权限不足，检查写权限" |

## 集成

setup 完成后，下列 skill 可用：
- **cann-ask** —— 通过 MCP 检索知识
- **session-upload** —— 通过 MCP 上传轨迹
