# -*- coding: utf-8 -*-
"""导出后端 OpenAPI 契约到 docs/api/openapi.json(前后端接口唯一事实源)。

用法(仓库根目录,uv workspace 环境):

    uv run python scripts/export_openapi.py

修改任何后端路由后,运行本命令刷新 openapi.json 并随代码一起提交。
决策(issue #49):不做 CI 校验,采用"手动导出命令"保持新鲜。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# cloud 是 uv workspace 成员(package=false,不做安装),手动加入 sys.path
sys.path.insert(0, str(ROOT / "cloud"))

from app.main import app  # noqa: E402

OUT = ROOT / "docs" / "api" / "openapi.json"


def main():
    spec = app.openapi()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OpenAPI 已导出:{OUT.relative_to(ROOT)}(共 {len(spec['paths'])} 个路径)")


if __name__ == "__main__":
    main()
