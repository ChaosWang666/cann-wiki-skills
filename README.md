# ascendc-wiki-skills

AscendC Kernel Wiki 知识检索和会话轨迹上传的 LLM Agent skills。

**新手开箱即用**：安装 skills → 运行 `/setup-ascendc-wiki` → `/exit` 重启 → 开始提问！

---

## 快速开始（5 分钟上手）

### 1. 安装 Skills

```bash
# Claude Code（推荐）
npx skills@latest add qianbi1999/ascendc-wiki-skills -a claude-code

# OpenCode
npx skills@latest add qianbi1999/ascendc-wiki-skills -a opencode
```

### 2. 配置 MCP 连接

在 agent 中运行：
```
/setup-ascendc-wiki
```

按提示选择 agent 类型和端口（默认 **3000**，如需其他端口可手动输入如 3001）。

### 3. **重启 Agent**（必须！）

```
/exit  # 退出当前会话（OpenCode 和 Claude Code 都支持）
```

然后重新启动 agent。不重启 MCP 工具无法使用。

### 4. 开始使用

```
/wiki-query AscendC 编程模型是什么？
/wiki-query 帮我写一个 Add 算子
/wiki-query Matmul 高阶 API 怎么用？

/session-upload  # 上传当前会话轨迹
```

---

## Skills 说明

| Skill | 命令 | 用途 | 首次使用 |
|-------|------|------|---------|
| **setup-ascendc-wiki** | `/setup-ascendc-wiki` | 配置 MCP 连接 | ✓ 必先运行 |
| **wiki-query** | `/wiki-query <问题>` | 检索 Wiki 知识 | 需要 setup |
| **session-upload** | `/session-upload` | 上传会话轨迹 | 需要 setup |

---

## 完整使用示例

### 示例 1：查询知识

```
用户: /wiki-query AscendC 编程模型是什么？

Agent:
我来帮你查询 AscendC 编程模型相关知识...

[调用 wiki_search → wiki_get_page → 合成答案]

## Answer

AscendC 编程模型采用 **AI Core 三级流水线**架构：
- **CopyIn**: GM → UB 数据搬运
- **Compute**: UB 上矢量/矩阵计算
- **CopyOut**: UB → GM 结果回写

[Source: wiki/static/ascendc/guide/concepts/programming-model.md]

💡 完整内容请查看 Wiki 页面...
```

### 示例 2：算子开发

```
用户: /wiki-query 帮我写一个 Add 算子

Agent:
[检索 Elementwise 模式 + 矢量算子实践]

## Answer

AscendC 实现 Add 算子有两种方式：

### 方式一：基础手工实现
```cpp
class KernelAdd {
    // CopyIn/Compute/CopyOut 三阶段
};
```

### 方式二：ElementwiseSch16B 模式（推荐）
```cpp
// DAG 表达式自动处理流水线
auto dag = Placeholder::In0 + Placeholder::In1;
```

[完整代码示例见 wiki/static/ascendc/guide/practice/vector-programming-basics.md]
```

### 示例 3：上传轨迹

```
用户: /session-upload

Agent:
检测到 Claude Code agent...
转换会话轨迹...
上传到 raw/sessions/uploaded/<session-id>.md

✓ 上传完成
- Session: xxx-xxx-xxx
- 行数: 818 行
- 关键词: AscendC ✓ (35 次)
```

---

## Troubleshooting 常见问题

### 问题 1: MCP 工具未找到

```
用户: /wiki-query xxx
错误: wiki_search not found
```

**原因**: 未运行 setup 或未重启

**解决**:
1. 确认已运行 `/setup-ascendc-wiki`
2. **输入 `/exit` 重启 agent**（最重要！）
3. 验证：运行 `/mcp` 应显示 ascendc-wiki

---

### 问题 2: MCP 连接失败

```
错误: MCP server not responding
```

**原因**: MCP Server 未运行

**解决**:
联系管理员启动 MCP Server，或确认端口配置正确（默认 **3000**）

---

### 问题 3: Setup 后仍提示 "No MCP servers"

```
用户: /mcp
输出: No MCP servers configured
```

**原因**: 未重启或配置文件位置错误

**解决**:
1. 输入 `/exit` 退出并重启 agent
2. 检查配置文件：
   - Claude Code: 项目根 `.mcp.json`
   - OpenCode: `.opencode/opencode.json`

---

### 问题 4: Wiki-query 无结果

```
用户: /wiki-query xxx
输出: 未找到相关内容
```

**原因**: 查询词不匹配或 Wiki 无此内容

**解决**:
1. 尝试不同关键词（英文/中文）
2. 使用更具体的术语（如 "Matmul 高阶 API" 而非 "矩阵乘法"）
3. 检查 Wiki 是否有相关页面

---

### 问题 5: Session-upload 失败

```
错误: No agent transcript found
```

**原因**: Agent transcript 路径未找到

**解决**:
1. Claude Code: 确认在项目目录下运行（非 ~/memory）
2. OpenCode: 确认 `opencode session list` 有活跃会话

---

### 问题 6: 配置被覆盖

```
警告: .mcp.json already exists
```

**解决**: Setup 会询问是否更新，选择 Yes 覆盖或 No 保留

---

## Skill 开发者指南

### 目录结构

```
ascendc-wiki-skills/
├── skills/
│   └── wiki/
│       ├── setup-ascendc-wiki/SKILL.md
│       ├── wiki-query/SKILL.md
│       └── session-upload/SKILL.md
└── README.md
```

### SKILL.md 格式

每个 skill 文件包含：

1. **YAML frontmatter**（必须）
```yaml
---
name: skill-name
description: "Skill description for agent"
---
```

2. **Skill 内容**（Markdown）
- Prerequisites
- Step-by-step workflow
- Error handling
- Notes

### 修改 Skill

```bash
# 1. 编辑 SKILL.md
vim skills/wiki/wiki-query/SKILL.md

# 2. 测试
npx skills@latest add . -a claude-code

# 3. 提交
git add -A && git commit -m "Update skill" && git push
```

### 添加新 Skill

```bash
# 1. 创建目录
mkdir -p skills/wiki/new-skill

# 2. 创建 SKILL.md（包含 frontmatter）
cat > skills/wiki/new-skill/SKILL.md << 'EOF'
---
name: new-skill
description: "Description"
---

# New Skill
...
EOF

# 3. 提交并推送
git add -A && git commit -m "Add new-skill" && git push
```

### Skill 调试技巧

1. **查看 agent 如何执行**: 观察 terminal 输出的工具调用链
2. **检查 MCP tool 参数**: 确认参数名和类型匹配 MCP server 定义
3. **测试单独步骤**: 将 skill 步骤拆分成独立命令测试

---

## 架构概览

```
┌────────────────────────────────────┐
│  Agent (Claude Code / OpenCode)    │
│  ├── Skills (本仓库)               │
│  │   ├── setup-ascendc-wiki       │ ← 配置 MCP 连接
│  │   ├── wiki-query               │ ← 调用 MCP 工具
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

**关键概念**:
- **用户只需安装 Skills** → 配置 → 使用
- **MCP Server 由管理员运维**（用户无需关心）

---

## 目录结构

```
ascendc-wiki-skills/
├── .claude-plugin/
│   └── plugin.json                  ← Skills 插件配置
├── skills/
│   └── wiki/
│       ├── setup-ascendc-wiki/
│       │   └── SKILL.md              ← 第一个运行
│       ├── wiki-query/
│       │   └── SKILL.md              ← 知识检索
│       └── session-upload/
│           └── SKILL.md              ← 轨迹上传
├── README.md                         ← 本文件
└── LICENSE
```

---

## License

MIT