# 域文档

工程 skill 在探索代码库时应如何消费本仓库的领域文档。

## 探索前先读

- 仓库根目录的 **`GLOSSARY.md`**；或
- 若存在根目录 **`GLOSSARY-MAP.md`**：它指向每个上下文一个的 `GLOSSARY.md`，读取与当前话题相关的那些；
- **`docs/adr/`**：阅读涉及你即将工作区域的 ADR。多上下文仓库还需检查 `src/<context>/docs/adr/` 中的上下文级决策。

若这些文件不存在，**静默继续**。不要提示缺失，也不要预先建议创建。`/domain-modeling` skill（经 `/grill-with-docs` 和 `/improve-codebase-architecture` 触达）会在术语或决策真正落定时惰性创建它们。

## 文件结构

单一上下文仓库（本仓库采用此布局）：

```
/
├── GLOSSARY.md
├── docs/adr/
│   ├── 0001-xxx.md
│   └── 0002-yyy.md
└── src/
```

多上下文仓库（根目录存在 `GLOSSARY-MAP.md` 时）：

```
/
├── GLOSSARY-MAP.md
├── docs/adr/                          ← 系统级决策
└── src/
    ├── ordering/
    │   ├── GLOSSARY.md
    │   └── docs/adr/                  ← 上下文级决策
    └── billing/
        ├── GLOSSARY.md
        └── docs/adr/
```

## 使用词汇表的术语

当你的输出涉及领域概念（issue 标题、重构提案、假设、测试名）时，使用 `GLOSSARY.md` 中定义的术语，不要漂移到词汇表明确规避的同义词。

若所需概念尚不在词汇表中，这是一个信号：要么你在发明项目不用的语言（请重新考虑），要么存在真实缺口（记下来交给 `/domain-modeling`）。

## 标记 ADR 冲突

若你的输出与现有 ADR 矛盾，显式指出而不是静默覆盖：

> _与 ADR-0007（xxx）矛盾，但值得重新讨论，因为……_
