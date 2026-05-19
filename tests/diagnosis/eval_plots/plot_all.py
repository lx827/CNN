"""
评估图表绘制 — 读 JSON 生成专业 SVG/PNG

用法:
    cd d:/code/CNN/cloud
    . venv/Scripts/activate
    python ../tests/diagnosis/eval_plots/plot_all.py
"""
import json, sys
from pathlib import Path
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "tests" / "output" / "eval_plots"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# ── 全局样式 ──────────────────────────────────────────────
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["SimHei", "Microsoft YaHei", "DejaVu Sans"],
    "axes.unicode_minus": False,
    "font.size": 12,
    "axes.titlesize": 14,
    "axes.labelsize": 13,
    "xtick.labelsize": 11,
    "ytick.labelsize": 11,
    "legend.fontsize": 10,
    "figure.dpi": 200,
    "savefig.dpi": 200,
    "savefig.format": "svg",
    "savefig.bbox": "tight",
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linestyle": "--",
    "axes.spines.top": False,
    "axes.spines.right": False,
})

# ── 配色 ──────────────────────────────────────────────────
C = {
    "red": "#E74C3C",
    "blue": "#2980B9",
    "green": "#27AE60",
    "orange": "#F39C12",
    "purple": "#8E44AD",
    "teal": "#1ABC9C",
    "gray": "#95A5A6",
    "dark": "#2C3E50",
    "light": "#BDC3C7",
    "bg": "#ECF0F1",
}


def load_json(name):
    with open(OUTPUT_DIR / name, encoding="utf-8") as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════
# 实验A: 轴承分类 — 准确率柱状图
# ═══════════════════════════════════════════════════════════
def plot_expA_bearing():
    data = load_json("expA_bearing.json")
    methods = data["methods"]
    names = list(methods.keys())
    accs = [m["accuracy"] for m in methods.values()]

    fig, ax = plt.subplots(figsize=(12, 6))

    colors = [C["red"] if "Ensemble" in n else C["blue"] if n == "MCKD" else C["gray"] for n in names]
    bars = ax.bar(range(len(names)), accs, color=colors, edgecolor="white", linewidth=0.5, width=0.65)

    # 数值标注
    for bar, acc in zip(bars, accs):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5,
                f"{acc:.1f}%", ha="center", va="bottom", fontsize=9, fontweight="bold",
                color=C["dark"] if acc < 90 else C["red"])

    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=30, ha="right", fontsize=10)
    ax.set_ylabel("Accuracy (%)", fontsize=13)
    ax.set_ylim(0, 105)
    ax.set_title("HUSTbear 轴承故障诊断 — 各方法二分类准确率对比", fontsize=14, fontweight="bold", pad=15)

    # 图例
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=C["red"], label="Ensemble 集成方法"),
        Patch(facecolor=C["blue"], label="MCKD (最优单一方法)"),
        Patch(facecolor=C["gray"], label="其他单一方法"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=9)

    ax.yaxis.set_major_locator(mticker.MultipleLocator(10))
    fig.tight_layout()
    for fmt in ["svg", "png"]:
        fig.savefig(OUTPUT_DIR / f"expA_accuracy.{fmt}")
    plt.close(fig)
    print("  [OK] expA_accuracy")


# ═══════════════════════════════════════════════════════════
# 实验B: 齿轮诊断 — 准确率柱状图
# ═══════════════════════════════════════════════════════════
def plot_expB_gear():
    data = load_json("expB_gear.json")
    methods = data["methods"]
    names = list(methods.keys())
    accs = [m["accuracy"] for m in methods.values()]

    fig, ax = plt.subplots(figsize=(9, 6))
    colors = [C["red"] if "Ensemble" in n else C["teal"] for n in names]
    bars = ax.bar(range(len(names)), accs, color=colors, edgecolor="white", linewidth=0.5, width=0.5)

    for bar, acc in zip(bars, accs):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5,
                f"{acc:.1f}%", ha="center", va="bottom", fontsize=11, fontweight="bold")

    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, fontsize=12)
    ax.set_ylabel("Accuracy (%)", fontsize=13)
    ax.set_ylim(0, 105)
    ax.set_title("WTgearbox 行星齿轮箱故障诊断 — 二分类准确率", fontsize=14, fontweight="bold", pad=15)
    ax.yaxis.set_major_locator(mticker.MultipleLocator(10))
    fig.tight_layout()
    for fmt in ["svg", "png"]:
        fig.savefig(OUTPUT_DIR / f"expB_accuracy.{fmt}")
    plt.close(fig)
    print("  [OK] expB_accuracy")


# ═══════════════════════════════════════════════════════════
# 实验C: 去噪 — ΔSNR 柱状图
# ═══════════════════════════════════════════════════════════
def plot_expC_denoise():
    data = load_json("expC_denoise.json")
    methods = data["methods"]
    names = list(methods.keys())
    snrs = [m["delta_snr_db"] for m in methods.values()]

    fig, ax = plt.subplots(figsize=(9, 6))

    base_colors = [C["gray"], C["blue"], C["teal"], C["orange"], C["red"]]
    colors = base_colors[:len(names)]
    bars = ax.bar(range(len(names)), snrs, color=colors, edgecolor="white", linewidth=0.5, width=0.55)

    for bar, val in zip(bars, snrs):
        y_pos = bar.get_height() + 0.4 if val >= 0 else bar.get_height() - 1.5
        ax.text(bar.get_x() + bar.get_width() / 2, y_pos,
                f"{val:+.1f} dB", ha="center", va="bottom" if val >= 0 else "top",
                fontsize=11, fontweight="bold")

    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, fontsize=12)
    ax.set_ylabel("ΔSNR (dB)", fontsize=13)
    ax.set_title("各去噪方法效果对比 (HUSTbear 外圈故障, 0dB AWGN)", fontsize=14, fontweight="bold", pad=15)
    ax.axhline(y=0, color=C["light"], linewidth=1, linestyle="-")

    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=C["red"], label="小波+VMD级联 (最优)"),
        Patch(facecolor=C["orange"], label="MED去噪"),
        Patch(facecolor=C["teal"], label="VMD去噪"),
        Patch(facecolor=C["blue"], label="小波去噪"),
    ]
    ax.legend(handles=legend_elements, loc="upper left", fontsize=9)

    fig.tight_layout()
    for fmt in ["svg", "png"]:
        fig.savefig(OUTPUT_DIR / f"expC_denoise.{fmt}")
    plt.close(fig)
    print("  [OK] expC_denoise")


# ═══════════════════════════════════════════════════════════
# 实验D: 鲁棒性 — SNR-检测率 衰减曲线
# ═══════════════════════════════════════════════════════════
def plot_expD_robustness():
    data = load_json("expD_robustness.json")
    snr_levels = data["snr_levels"]
    methods = data["methods"]

    fig, ax = plt.subplots(figsize=(10, 6))

    color_map = {"Ensemble集成": C["red"], "MCKD": C["blue"], "MED增强": C["orange"],
                 "Kurtogram": C["teal"], "包络分析": C["gray"]}
    marker_map = {"Ensemble集成": "s", "MCKD": "D", "MED增强": "o",
                  "Kurtogram": "^", "包络分析": "v"}

    for name, curve in methods.items():
        x = [c["snr_db"] for c in curve]
        y = [100 if c["detected"] else 0 for c in curve]
        c = color_map.get(name, C["gray"])
        m = marker_map.get(name, "o")
        ax.plot(x, y, color=c, marker=m, markersize=10, linewidth=2.5,
                markerfacecolor="white", markeredgewidth=2, label=name, zorder=5)

    ax.set_xlabel("SNR (dB)", fontsize=13)
    ax.set_ylabel("故障检出率 (%)", fontsize=13)
    ax.set_title("噪声鲁棒性对比 — HUSTbear 外圈故障", fontsize=14, fontweight="bold", pad=15)
    ax.set_xticks(snr_levels)
    ax.set_ylim(-5, 115)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.invert_xaxis()
    ax.legend(loc="lower left", fontsize=9, framealpha=0.9)

    # 标注
    ax.annotate("强噪声区", xy=(-5, 10), fontsize=10, color=C["dark"],
                ha="center", bbox=dict(boxstyle="round,pad=0.3", facecolor=C["bg"], alpha=0.8))
    ax.annotate("低噪声区", xy=(20, 95), fontsize=10, color=C["dark"],
                ha="center", bbox=dict(boxstyle="round,pad=0.3", facecolor=C["bg"], alpha=0.8))

    fig.tight_layout()
    for fmt in ["svg", "png"]:
        fig.savefig(OUTPUT_DIR / f"expD_robustness.{fmt}")
    plt.close(fig)
    print("  [OK] expD_robustness")


# ═══════════════════════════════════════════════════════════
# 综合对比图 — 跨数据集
# ═══════════════════════════════════════════════════════════
def plot_cross_dataset():
    """跨数据集对比：HUSTbear + CW + WTgearbox 最优方法"""
    # 如果 CW 数据存在就加载
    cw_path = OUTPUT_DIR / "expA_bearing.json"
    gear_path = OUTPUT_DIR / "expB_gear.json"

    if not cw_path.exists() or not gear_path.exists():
        print("  [SKIP] cross_dataset: 需要 expA + expB 数据")
        return

    a_data = load_json("expA_bearing.json")
    b_data = load_json("expB_gear.json")

    # 提取 MCKD 和 Ensemble
    methods_a = a_data["methods"]
    methods_b = b_data["methods"]

    datasets = ["HUSTbear (恒速轴承)", "WTgearbox (行星齿轮)"]
    mckd_vals = [methods_a.get("MCKD", {}).get("accuracy", 0),
                 methods_b.get("高级综合", {}).get("accuracy", 0)]
    ens_vals = [methods_a.get("Ensemble集成", {}).get("accuracy", 0),
                methods_b.get("Ensemble集成", {}).get("accuracy", 0)]

    fig, ax = plt.subplots(figsize=(8, 5.5))
    x = np.arange(len(datasets))
    w = 0.3

    bars1 = ax.bar(x - w/2, mckd_vals, w, color=C["blue"], edgecolor="white", label="最优单一方法")
    bars2 = ax.bar(x + w/2, ens_vals, w, color=C["red"], edgecolor="white", label="Ensemble集成")

    for bar, val in zip(bars1, mckd_vals):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1.5, f"{val:.1f}%",
                ha="center", fontsize=10, fontweight="bold")
    for bar, val in zip(bars2, ens_vals):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1.5, f"{val:.1f}%",
                ha="center", fontsize=10, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(datasets, fontsize=12)
    ax.set_ylabel("Accuracy (%)", fontsize=13)
    ax.set_ylim(0, 105)
    ax.set_title("跨数据集诊断性能对比", fontsize=14, fontweight="bold", pad=15)
    ax.legend(fontsize=10)
    ax.yaxis.set_major_locator(mticker.MultipleLocator(10))

    fig.tight_layout()
    for fmt in ["svg", "png"]:
        fig.savefig(OUTPUT_DIR / f"cross_dataset.{fmt}")
    plt.close(fig)
    print("  [OK] cross_dataset")


def main():
    print("=" * 60)
    print("生成答辩图表")
    print(f"输出: {OUTPUT_DIR}")
    print("=" * 60)

    plot_expA_bearing()
    plot_expB_gear()
    plot_expC_denoise()
    plot_expD_robustness()
    plot_cross_dataset()

    print(f"\n全部图表已保存到 {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
