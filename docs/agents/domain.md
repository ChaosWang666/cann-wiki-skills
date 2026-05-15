# Domain Docs

工程类 skill 在探索代码库时，应该如何使用本仓的领域文档。

## 探索代码前，先读这些

- 仓库根目录的 **`CONTEXT.md`**，或
- 根目录的 **`CONTEXT-MAP.md`**（若存在）—— 它指向每个 context 各自的 `CONTEXT.md`。读跟你当前主题相关的那几个。
- **`docs/adr/`** —— 读涉及你即将动的区域的 ADR。多 context 仓里，也要检查 `src/<context>/docs/adr/` 下 context 专属决策。

如果上面这些文件都不存在，**保持静默**。不要标记缺失，不要主动建议预先创建。生产端 skill（`/grill-with-docs`）会在术语或决策被真正解析时按需创建。

## 文件结构

单 context 仓（大部分仓都是这种）：

```
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-event-sourced-orders.md
│   └── 0002-postgres-for-write-model.md
└── src/
```

多 context 仓（根目录有 `CONTEXT-MAP.md`）：

```
/
├── CONTEXT-MAP.md
├── docs/adr/                          ← 系统级决策
└── src/
    ├── ordering/
    │   ├── CONTEXT.md
    │   └── docs/adr/                  ← 该 context 专属决策
    └── billing/
        ├── CONTEXT.md
        └── docs/adr/
```

## 使用术语表里的词汇

当输出涉及某个领域概念（issue 标题、重构提案、假设、测试名），使用 `CONTEXT.md` 中定义的术语。不要漂移到术语表明确避免的同义词上。

如果你需要的概念不在术语表里，那是个信号 —— 要么你在使用项目不用的语言（重新考虑），要么是个真实缺口（记下来给 `/grill-with-docs`）。

## 与 ADR 冲突要显式标注

如果输出与现有 ADR 冲突，明示而不是静默覆盖：

> _Contradicts ADR-0007（event-sourced orders）—— 但值得重开讨论，因为……_
