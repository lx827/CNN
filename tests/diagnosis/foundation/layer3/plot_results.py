"""
Layer 3 集成层 — 独立绘图脚本

读取 layer3/output/*.json 生成对比图，无需重跑分析。
"""
import json
from pathlib import Path
import numpy as np

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

OUTPUT_DIR = Path(__file__).parent / "output"
PLOT_DIR = OUTPUT_DIR / "plots"


def load_json(name):
    p = OUTPUT_DIR / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return json.loads(p.read_bytes())


def plot_engine():
    data = load_json("engine_integration.json")
    if not data:
        return
    categories = [k for k in data.keys() if k != "summary"]
    cat_passed = []
    cat_total = []
    for cat in categories:
        items = data[cat]
        cat_passed.append(sum(1 for it in items if it.get("passed", False)))
        cat_total.append(len(items))

    fig, ax = plt.subplots(figsize=(8, 4))
    x = np.arange(len(categories))
    failed = [t - p for t, p in zip(cat_total, cat_passed)]
    ax.bar(x, cat_passed, color='#52C41A', label='通过')
    ax.bar(x, failed, bottom=cat_passed, color='#FF4D4F', label='失败')
    ax.set_xticks(x)
    ax.set_xticklabels([c.replace('_', '\n') for c in categories], fontsize=9)
    ax.set_ylabel("测试数")
    ax.set_title("Layer 3: engine.py — 引擎集成")
    ax.legend()
    for i, (t, p) in enumerate(zip(cat_total, cat_passed)):
        ax.text(i, t + 0.1, f"{p}/{t}", ha='center', fontsize=9)
    ax.set_ylim(0, max(cat_total) * 1.3)
    plt.tight_layout()
    fig.savefig(PLOT_DIR / "engine_integration.png", dpi=150)
    plt.close(fig)
    print("  [OK] engine_integration.png")


def plot_ensemble():
    data = load_json("ensemble_integration.json")
    if not data:
        return
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    # 左图：profile 对比
    profile_items = [it for it in data.get("ensemble_profiles", []) if "hs" in it]
    if profile_items:
        labels = [it["test"].replace("ensemble_profile_", "") for it in profile_items]
        values = [it["hs"] for it in profile_items]
        colors = ['#52C41A' if it.get("passed") else '#FF4D4F' for it in profile_items]
        axes[0].bar(labels, values, color=colors)
        axes[0].set_ylabel("健康度")
        axes[0].set_title("不同 profile 健康度")
        axes[0].set_ylim(0, 110)

    # 右图：健康 vs 故障区分度
    disc = data.get("ensemble_discrimination", [])
    for it in disc:
        if "healthy_hs" in it:
            axes[1].barh(["健康", "故障"], [it["healthy_hs"], it["fault_hs"]], color=['#52C41A', '#FF4D4F'])
            axes[1].set_xlabel("健康度")
            axes[1].set_title(f"区分度: hs_diff={it.get('hs_diff', 0):.1f}")
            axes[1].text(it["healthy_hs"] + 1, 0, f"lik={it['healthy_likelihood']:.3f}", va='center')
            axes[1].text(it["fault_hs"] + 1, 1, f"lik={it['fault_likelihood']:.3f}", va='center')

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "ensemble_integration.png", dpi=150)
    plt.close(fig)
    print("  [OK] ensemble_integration.png")


def plot_analyzer():
    data = load_json("analyzer_integration.json")
    if not data:
        return
    fig, ax = plt.subplots(figsize=(8, 4))
    labels = []
    values = []
    colors = []
    for cat, items in data.items():
        if cat == "summary":
            continue
        for it in items:
            if "health_score" in it:
                labels.append(it["test"].replace("analyzer_", ""))
                values.append(it["health_score"])
                colors.append('#52C41A' if it.get("passed") else '#FF4D4F')

    if labels:
        x = np.arange(len(labels))
        ax.bar(x, values, color=colors)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=9)
        ax.set_ylabel("健康度")
        ax.set_title("Layer 3: analyzer.py — 各场景健康度")
        ax.axhline(y=80, color='orange', linestyle='--', label='warning')
        ax.axhline(y=50, color='red', linestyle='--', label='fault')
        ax.legend()
        ax.set_ylim(0, 110)
        ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "analyzer_integration.png", dpi=150)
    plt.close(fig)
    print("  [OK] analyzer_integration.png")


def plot_summary():
    summary_data = {}
    for json_name in ["engine_integration", "ensemble_integration", "analyzer_integration"]:
        data = load_json(f"{json_name}.json")
        if data and "summary" in data:
            summary_data[json_name.replace("_integration", "")] = data["summary"]

    if not summary_data:
        return

    fig, ax = plt.subplots(figsize=(7, 4))
    labels = list(summary_data.keys())
    totals = [v.get("total", 0) for v in summary_data.values()]
    passed = [v.get("passed", 0) for v in summary_data.values()]
    failed = [v.get("failed", v.get("total", 0) - v.get("passed", 0)) for v in summary_data.values()]

    x = range(len(labels))
    ax.bar(x, passed, color='#52C41A', label='通过')
    ax.bar(x, failed, bottom=passed, color='#FF4D4F', label='失败')
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("测试数")
    ax.set_title("Layer 3: 集成层 — 测试通过率")
    ax.set_ylim(0, max(totals) * 1.5)
    ax.legend()

    for i, (t, p) in enumerate(zip(totals, passed)):
        ax.text(i, t + 0.2, f"{p}/{t}", ha='center')

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "layer3_summary.png", dpi=150)
    plt.close(fig)
    print("  [OK] layer3_summary.png")


def main():
    if not HAS_MPL:
        print("matplotlib 未安装，跳过绘图")
        return

    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    print("Layer 3: 集成层 — 生成对比图")
    print("=" * 40)

    plot_engine()
    plot_ensemble()
    plot_analyzer()
    plot_summary()

    print(f"\n图表保存在: {PLOT_DIR}")


if __name__ == "__main__":
    main()
