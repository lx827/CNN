# 文档检查工具

在仓库根运行：

```bash
bash docs/internal/check_markdown_links.sh
```

检查范围：

- `docs/**/*.md` 以及根 `AGENTS.md`、`README.md`、`GLOSSARY.md` 的本地相对链接；
- 轴承、阶次、齿轮、分解和数值算法入口的必需契约章节；
- 已撤销 `docs/backend/app/` 镜像目录及其引用。

本检查不执行算法测试，也不比较 Markdown 与函数签名。函数签名以源码 docstring 为准，外部 API 另由 OpenAPI 和路由测试验证。

`check_doc_coverage.py`、`check_api_docs.py` 是旧逐文件签名覆盖规则的遗留工具，保留源码仅供迁移追溯，不再是维护依据，不应运行来阻断模块契约体系。旧生成报告已随镜像规则撤销。
