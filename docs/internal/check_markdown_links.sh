#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHONIOENCODING=utf-8 uv run --project "$ROOT" python -I - "$ROOT" <<'PY'
from pathlib import Path
from urllib.parse import unquote
import re
import sys

root = Path(sys.argv[1]).resolve()
markdown = sorted((root / "docs").rglob("*.md"))
for name in ("AGENTS.md", "README.md", "GLOSSARY.md"):
    path = root / name
    if path.exists():
        markdown.append(path)

errors = []
checked_links = 0
required_headings = (
    "数学目的",
    "适用与不适用场景",
    "输入、输出与单位",
    "必要前提",
    "Pipeline 组合",
    "错误与不可判定语义",
    "复杂度与内存",
    "参考文献",
    "验证向量与验证状态",
)

def visible_text(text):
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return re.sub(r"`[^`\n]*`", "", text)

for path in markdown:
    text = path.read_text(encoding="utf-8")
    visible = visible_text(text)
    rel = path.relative_to(root).as_posix()
    if "docs/backend/app/" in visible:
        errors.append(f"{rel}: 引用了已撤销的 docs/backend/app/ 镜像目录")
    for match in re.finditer(r"!?\[[^\]]*\]\(([^)]+)\)", visible):
        raw = match.group(1).strip()
        if raw.startswith("<") and raw.endswith(">"):
            raw = raw[1:-1]
        if not raw or raw.startswith(("#", "/", "http://", "https://", "mailto:", "tel:", "data:")) or re.match(r"^[A-Za-z]:/", raw):
            continue
        target_part = raw.split("#", 1)[0].split("?", 1)[0]
        if not target_part:
            continue
        checked_links += 1
        target = (path.parent / unquote(target_part)).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            errors.append(f"{rel}: 链接越出仓库: {raw}")
            continue
        if not target.exists():
            errors.append(f"{rel}: 失效链接: {raw}")

for family in ("bearing", "order", "gear", "decomposition", "numeric", "composite"):
    path = root / "docs" / "algorithms" / family / "INDEX.md"
    if not path.exists():
        errors.append(f"缺少算法族入口: docs/algorithms/{family}/INDEX.md")
        continue
    text = path.read_text(encoding="utf-8")
    headings = set(re.findall(r"^##\s+(.+?)\s*$", text, flags=re.M))
    for heading in required_headings:
        if heading not in headings:
            errors.append(f"docs/algorithms/{family}/INDEX.md: 缺少二级标题“{heading}”")

if (root / "docs" / "backend" / "app").exists():
    errors.append("docs/backend/app/ 镜像目录仍存在")
for name in ("AGENTS.md", "docs/INDEX.md", "docs/algorithms/INDEX.md", "docs/backend/INDEX.md"):
    if not (root / name).exists():
        errors.append(f"缺少导航文档: {name}")

print(f"Markdown files: {len(markdown)}")
print(f"Relative links: {checked_links}")
print(f"Algorithm structures: 6 entries x {len(required_headings)} required sections")
if errors:
    print(f"FAILED: {len(errors)} issue(s)")
    for error in errors:
        print(f"- {error}")
    raise SystemExit(1)
print("PASS: relative links, algorithm structures, and mirror cleanup")
PY
