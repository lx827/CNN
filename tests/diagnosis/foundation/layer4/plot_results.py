"""
Layer 4 测试结果绘图 — 只读 JSON，不重跑分析
"""
import json
from pathlib import Path
import numpy as np

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

OUTPUT_DIR = Path(__file__).parent / "output"
PLOT_DIR = OUTPUT_DIR / "plots"
PLOT_DIR.mkdir(parents=True, exist_ok=True)


def load_json(name):
    p = OUTPUT_DIR / name
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def plot_engine_deep():
    if not HAS_MPL:
        print("[跳过] matplotlib 未安装")
        return
    data = load_json("engine_deep.json")
    if not data:
        print("[跳过] engine_deep.json 不存在")
        return

    items = []
    for cat, vals in data.items():
        if cat == "summary":
            continue
        for v in vals:
            items.append((v["test"], v.get("passed", False)))

    if not items:
        return

    labels, passed = zip(*items)
    colors = ["#2ecc71" if p else "#e74c3c" for p in passed]

    fig, ax = plt.subplots(figsize=(8, max(4, len(items) * 0.4)))
    y = range(len(items))
    ax.barh(y, [1] * len(items), color=colors)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlim(0, 1)
    ax.set_xticks([])
    ax.set_title("Layer 4: engine.py 深层功能 — 测试结果")
    ax.invert_yaxis()

    s = data.get("summary", {})
    ax.text(0.98, 0.02, f"通过: {s.get('passed', 0)}/{s.get('total', 0)}",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=11,
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.8))

    out = PLOT_DIR / "layer4_engine_deep.png"
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"[保存] {out}")


def main():
    plot_engine_deep()


if __name__ == "__main__":
    main()
