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

    t, p, f = _count_tests(data)
    ax.text(0.98, 0.02, f"通过: {p}/{t}", transform=ax.transAxes, ha="right",
            va="bottom", fontsize=11, bbox=dict(boxstyle="round", facecolor="white", alpha=0.8))

    fig.tight_layout()
    fig.savefig(PLOT_DIR / "layer4_engine_deep.svg")
    plt.close(fig)
    print("  [OK] layer4_engine_deep.svg")


def _count_tests(data) -> tuple:
    total, passed, failed = 0, 0, 0
    if isinstance(data, list):
        for item in data:
            t, p, f = _count_tests(item)
            total += t; passed += p; failed += f
    elif isinstance(data, dict):
        if "passed" in data and isinstance(data["passed"], bool):
            total = 1
            if data["passed"]: passed = 1
            else: failed = 1
        for v in data.values():
            t, p, f = _count_tests(v)
            total += t; passed += p; failed += f
    return total, passed, failed


def plot_summary():
    if not HAS_MPL:
        return
    summary = {}
    for json_name in ["engine_deep", "engine_deep_real"]:
        data = load_json(f"{json_name}.json")
        if data:
            t, p, f = _count_tests(data)
            if t > 0:
                label = json_name.replace("engine_", "").replace("_", "\n")
                summary[label] = {"total": t, "passed": p, "failed": f}
    if not summary: return

    fig, ax = plt.subplots(figsize=(7, 4))
    labels = list(summary.keys())
    totals = [v["total"] for v in summary.values()]
    passed = [v["passed"] for v in summary.values()]
    failed = [v["failed"] for v in summary.values()]
    x = range(len(labels))
    ax.bar(x, passed, color='#52C41A', label='通过')
    ax.bar(x, failed, bottom=passed, color='#FF4D4F', label='失败')
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylabel("测试数")
    ax.set_title("Layer 4: 深层逻辑 — 测试通过率汇总", fontsize=12, fontweight='bold')
    ax.set_ylim(0, max(totals) * 1.3 if totals else 10)
    ax.legend()
    for i, (t, p_val) in enumerate(zip(totals, passed)):
        ax.text(i, t + max(totals) * 0.03, f"{p_val}/{t}", ha='center', fontsize=10, fontweight='bold')
    plt.tight_layout()
    fig.savefig(PLOT_DIR / "layer4_summary.svg")
    plt.close(fig)
    print("  [OK] layer4_summary.svg")


def main():
    plot_engine_deep()
    plot_summary()


if __name__ == "__main__":
    main()
