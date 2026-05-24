"""
绘制评估对比图 — 基于最新 JSON 数据生成专业对比图表

用法:
    cd d:/code/CNN/cloud
    . venv/Scripts/activate
    python ../tests/diagnosis/eval_plots/plot_comparison.py
"""
import json
from pathlib import Path
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "tests" / "output" / "eval_plots"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
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
    "axes.titlesize": 15,
    "axes.labelsize": 13,
    "xtick.labelsize": 11,
    "ytick.labelsize": 11,
    "legend.fontsize": 10,
    "figure.dpi": 200,
    "savefig.dpi": 200,
    "savefig.format": "svg",
    "savefig.bbox": "tight",
    "axes.grid": True,
    "grid.alpha": 0.2,
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
    "gray": "#7F8C8D",
    "dark": "#2C3E50",
    "light": "#BDC3C7",
    "bg": "#ECF0F1",
    "gold": "#F1C40F",
}

METHOD_COLORS = {
    "VMD": "#27AE60",
    "DWT": "#2980B9",
    "标准包络": "#7F8C8D",
    "EMD": "#1ABC9C",
    "MED增强": "#F39C12",
    "MCKD": "#E67E22",
    "Teager": "#8E44AD",
    "谱峭度重加权": "#3498DB",
    "Kurtogram": "#95A5A6",
    "CPW预白化": "#BDC3C7",
    "Ensemble": "#E74C3C",
    "标准边频分析": "#7F8C8D",
    "高级综合": "#2980B9",
}


def load_json(name):
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════
# 图1: HUSTbear 恒速轴承 — 各方法准确率对比
# ═══════════════════════════════════════════════════════════
def plot_hust_bearing():
    data = load_json("42_hust_binary.json")
    methods = data["methods"]

    # 按准确率降序排列（过滤跳过的方法）
    sorted_items = sorted(
        [(k, v) for k, v in methods.items() if isinstance(v.get("accuracy"), (int, float))],
        key=lambda x: x[1]["accuracy"], reverse=True
    )
    names = [item[0] for item in sorted_items]
    accs = [item[1]["accuracy"] for item in sorted_items]
    times = [item[1]["avg_time_ms"] for item in sorted_items]

    fig, ax = plt.subplots(figsize=(14, 6))

    # 颜色映射
    colors = [METHOD_COLORS.get(n, C["gray"]) for n in names]
    bars = ax.bar(range(len(names)), accs, color=colors, edgecolor="white",
                  linewidth=0.5, width=0.7, zorder=3)

    # 数值标注 — 放在柱顶上方
    for bar, acc in zip(bars, accs):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.2,
                f"{acc:.1f}%", ha="center", va="bottom", fontsize=9.5,
                fontweight="bold", color=C["dark"])

    # 耗时标注 — 放在柱内底部
    for bar, t in zip(bars, times):
        if bar.get_height() > 15:
            ax.text(bar.get_x() + bar.get_width() / 2, 3,
                    f"{t:.0f}ms", ha="center", va="bottom", fontsize=7,
                    color="white", fontweight="bold", alpha=0.85)

    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=35, ha="right", fontsize=10.5)
    ax.set_ylabel("Accuracy (%)", fontsize=13, labelpad=10)
    ax.set_ylim(0, 108)
    ax.set_xlim(-0.6, len(names) - 0.4)
    ax.set_title("HUSTbear 恒速轴承故障诊断 — 各方法二分类准确率对比\n"
                 "(99样本: 健康11 + 故障88, X通道, 5秒截断)",
                 fontsize=14, fontweight="bold", pad=18)

    # 图例
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=C["green"], label="VMD (最佳)"),
        Patch(facecolor=C["red"], label="Ensemble 集成"),
        Patch(facecolor=C["blue"], label="DWT 小波"),
        Patch(facecolor=C["orange"], label="MED增强"),
        Patch(facecolor=C["teal"], label="EMD 经验模态"),
        Patch(facecolor=C["gray"], label="其他方法"),
    ]
    ax.legend(handles=legend_elements, loc="upper right", fontsize=9,
              ncol=2, framealpha=0.9)

    ax.yaxis.set_major_locator(mticker.MultipleLocator(10))
    ax.yaxis.set_minor_locator(mticker.MultipleLocator(5))

    # 添加平均线
    avg_acc = np.mean(accs)
    ax.axhline(y=avg_acc, color=C["dark"], linewidth=1, linestyle="--", alpha=0.5, zorder=1)
    ax.text(len(names) - 0.3, avg_acc + 2, f"均值 {avg_acc:.1f}%",
            fontsize=8, color=C["dark"], ha="right", alpha=0.7)

    fig.tight_layout()
    for fmt in ["svg", "png"]:
        fig.savefig(OUTPUT_DIR / f"comparison_hust_bearing.{fmt}")
    plt.close(fig)
    print("  [OK] comparison_hust_bearing")


# ═══════════════════════════════════════════════════════════
# 图2: 跨数据集综合对比 — 两大轴承数据集核心方法
# ═══════════════════════════════════════════════════════════
def plot_cross_dataset_full():
    """综合跨数据集对比：HUSTbear + Ottawa(变速)"""
    hust = load_json("42_hust_binary.json")
    cw = load_json("43_cw_binary.json")

    # 提取所有方法在各数据集上的准确率
    datasets = ["HUSTbear\n恒速轴承\n(99样本)", "Ottawa\n变速轴承\n(36样本)"]

    # 共同轴承方法（在两个轴承数据集上都有的方法）
    bearing_methods = ["VMD", "DWT", "标准包络", "EMD", "MED增强", "MCKD",
                       "Teager", "谱峭度重加权", "Kurtogram", "CPW预白化", "Ensemble"]

    # 构建数据矩阵
    data_matrix = {}
    for m in bearing_methods:
        row = []
        for ds_name, ds_data in [("hust", hust), ("cw", cw)]:
            val = ds_data["methods"].get(m, {}).get("accuracy", None)
            row.append(val)
        data_matrix[m] = row

    # 过滤：至少在一个数据集上有值
    valid_methods = {m: row for m, row in data_matrix.items()
                     if any(v is not None for v in row)}

    fig, ax = plt.subplots(figsize=(12, 7))

    n_methods = len(valid_methods)
    n_datasets = 2
    x = np.arange(n_datasets)
    total_width = 0.85
    bar_width = total_width / n_methods

    method_names = list(valid_methods.keys())
    method_rows = list(valid_methods.values())

    # 为每个方法分配颜色
    custom_colors = [
        C["green"],   # VMD
        C["blue"],    # DWT
        C["gray"],    # 标准包络
        C["teal"],    # EMD
        C["orange"],  # MED增强
        "#E67E22",    # MCKD
        C["purple"],  # Teager
        "#3498DB",    # 谱峭度重加权
        "#95A5A6",    # Kurtogram
        "#BDC3C7",    # CPW预白化
        C["red"],     # Ensemble
    ]

    for i, (mname, mrow) in enumerate(zip(method_names, method_rows)):
        offset = (i - (n_methods - 1) / 2) * bar_width
        positions = x + offset
        bars = ax.bar(positions, [v if v is not None else 0 for v in mrow],
                      bar_width * 0.85, color=custom_colors[i],
                      edgecolor="white", linewidth=0.3,
                      label=mname, zorder=3)

        # 标注数值 — 从右向左写，字体加大
        for j, (bar, val) in enumerate(zip(bars, mrow)):
            if val is not None and val > 0:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 1.0,
                        f"{val:.1f}", ha="center", va="bottom",
                        fontsize=8, fontweight="bold", color=C["dark"],
                        rotation=270)

    ax.set_xticks(x)
    ax.set_xticklabels(datasets, fontsize=11)
    ax.set_ylabel("Accuracy (%)", fontsize=13, labelpad=10)
    ax.set_ylim(0, 115)
    ax.set_title("两大轴承数据集诊断准确率全景对比", fontsize=15, fontweight="bold", pad=20)

    # 图例放到顶部
    ax.legend(loc="lower center", fontsize=9, ncol=6,
              framealpha=0.9, bbox_to_anchor=(0.5, 1.02))

    ax.yaxis.set_major_locator(mticker.MultipleLocator(10))
    ax.yaxis.set_minor_locator(mticker.MultipleLocator(5))
    ax.set_xlim(-0.5, n_datasets - 0.5)

    fig.tight_layout()
    fig.subplots_adjust(top=0.88)
    for fmt in ["svg", "png"]:
        fig.savefig(OUTPUT_DIR / f"comparison_cross_dataset.{fmt}")
    plt.close(fig)
    print("  [OK] comparison_cross_dataset")


# ═══════════════════════════════════════════════════════════
# 图3: 准确率 vs 耗时 水平棒棒糖图（HUSTbear）
# ═══════════════════════════════════════════════════════════
def plot_accuracy_vs_time():
    data = load_json("42_hust_binary.json")
    methods = data["methods"]

    # 按准确率降序排列（过滤跳过的方法）
    sorted_items = sorted(
        [(k, v) for k, v in methods.items() if isinstance(v.get("accuracy"), (int, float))],
        key=lambda x: x[1]["accuracy"], reverse=True
    )
    names = [item[0] for item in sorted_items]
    accs = [item[1]["accuracy"] for item in sorted_items]
    times = [item[1]["avg_time_ms"] for item in sorted_items]

    fig, ax = plt.subplots(figsize=(10, 8))
    y = np.arange(len(names))

    # 颜色按速度分级
    colors = []
    for t in times:
        if t < 300:
            colors.append(C["green"])   # 快速
        elif t < 1000:
            colors.append(C["blue"])    # 中等
        else:
            colors.append(C["orange"])  # 慢速

    # 水平棒棒糖图
    ax.hlines(y=y, xmin=0, xmax=accs, color=colors, linewidth=2.5, alpha=0.5, zorder=1)
    ax.scatter(accs, y, s=120, c=colors, edgecolors="white", linewidth=1.5, zorder=3)

    # 标注
    for i, (name, acc, t) in enumerate(zip(names, accs, times)):
        # 准确率
        ax.text(acc + 2.0, i, f"{acc:.1f}%", va="center", ha="left",
                fontsize=10, fontweight="bold", color=C["dark"])
        # 耗时
        ax.text(acc + 14, i, f"{t:.0f}ms", va="center", ha="left",
                fontsize=9, color=C["gray"])

    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=11)
    ax.set_xlabel("Accuracy (%)", fontsize=13, labelpad=10)
    ax.set_xlim(0, 105)
    ax.set_title("HUSTbear 轴承诊断 — 准确率与计算效率对比\n（绿色=快速<300ms  蓝色=中速  橙色=慢速>1500ms）",
                 fontsize=14, fontweight="bold", pad=18)

    # 速度分级参考线
    ax.axvline(x=70, color=C["light"], linewidth=1, linestyle=":", alpha=0.5)
    ax.text(70, len(names) - 0.3, "70% 基准", fontsize=8, color=C["gray"], ha="center")

    ax.grid(True, axis="x", alpha=0.25, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    for fmt in ["svg", "png"]:
        fig.savefig(OUTPUT_DIR / f"comparison_acc_vs_time.{fmt}")
    plt.close(fig)
    print("  [OK] comparison_acc_vs_time")


# ═══════════════════════════════════════════════════════════
# 图4: 轴承方法在恒速 vs 变速下的表现对比
# ═══════════════════════════════════════════════════════════
def plot_const_vs_varying():
    hust = load_json("42_hust_binary.json")
    cw = load_json("43_cw_binary.json")

    # 共同方法
    common = set(hust["methods"].keys()) & set(cw["methods"].keys())
    common = sorted(common, key=lambda m: hust["methods"][m]["accuracy"], reverse=True)

    fig, ax = plt.subplots(figsize=(13, 7))

    x = np.arange(len(common))
    w = 0.35

    hust_accs = [hust["methods"][m]["accuracy"] for m in common]
    cw_accs = [cw["methods"][m]["accuracy"] for m in common]

    bars1 = ax.bar(x - w/2, hust_accs, w, color=C["blue"], edgecolor="white",
                   linewidth=0.5, label="恒速 (HUSTbear, 99样本)", zorder=3)
    bars2 = ax.bar(x + w/2, cw_accs, w, color=C["orange"], edgecolor="white",
                   linewidth=0.5, label="变速 (Ottawa, 36样本)", zorder=3)

    # 标注数值
    for bar, val in zip(bars1, hust_accs):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1.0,
                f"{val:.1f}", ha="center", va="bottom", fontsize=7.5,
                fontweight="bold", color=C["blue"], rotation=90)
    for bar, val in zip(bars2, cw_accs):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1.0,
                f"{val:.1f}", ha="center", va="bottom", fontsize=7.5,
                fontweight="bold", color=C["orange"], rotation=90)

    ax.set_xticks(x)
    ax.set_xticklabels(common, rotation=30, ha="right", fontsize=10)
    ax.set_ylabel("Accuracy (%)", fontsize=13, labelpad=10)
    ax.set_ylim(0, 110)
    ax.set_title("恒速 vs 变速 — 各方法工况鲁棒性对比",
                 fontsize=14, fontweight="bold", pad=18)
    ax.legend(fontsize=11, loc="upper right")
    ax.yaxis.set_major_locator(mticker.MultipleLocator(10))

    fig.tight_layout()
    for fmt in ["svg", "png"]:
        fig.savefig(OUTPUT_DIR / f"comparison_const_vs_varying.{fmt}")
    plt.close(fig)
    print("  [OK] comparison_const_vs_varying")


# ═══════════════════════════════════════════════════════════
# 图5: 去噪效果对比
# ═══════════════════════════════════════════════════════════
def plot_denoise():
    data = load_json("47_denoise.json")
    methods = data["methods"]

    # 方法顺序固定（11种去噪 + MED增强对比）
    method_names = [
        "无去噪", "小波去噪", "VMD去噪", "小波+VMD级联", "小波+LMS",
        "EMD去噪", "CEEMDAN去噪", "SAVGOL平滑", "小波包去噪",
        "CEEMDAN+小波包", "EEMD去噪", "MED增强",
    ]
    outer = [methods[m]["外圈故障"] for m in method_names]
    healthy = [methods[m]["健康"] for m in method_names]

    fig, ax = plt.subplots(figsize=(16, 7))

    x = np.arange(len(method_names))
    w = 0.35

    bars1 = ax.bar(x - w/2, outer, w, label="外圈故障", color=C["blue"],
                   edgecolor="white", linewidth=0.5, zorder=3)
    bars2 = ax.bar(x + w/2, healthy, w, label="健康样本", color=C["orange"],
                   edgecolor="white", linewidth=0.5, zorder=3)

    # 数值标注
    for bar, val in zip(bars1, outer):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                f"{val:+.2f}", ha="center", va="bottom", fontsize=8.5,
                fontweight="bold", color=C["blue"])
    for bar, val in zip(bars2, healthy):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                f"{val:+.2f}", ha="center", va="bottom", fontsize=8.5,
                fontweight="bold", color=C["orange"])

    ax.axhline(y=0, color=C["dark"], linewidth=0.8, linestyle="-", zorder=1)
    ax.set_xticks(x)
    ax.set_xticklabels(method_names, fontsize=10, rotation=15, ha="right")
    ax.set_ylabel("ΔSNR (dB)", fontsize=13, labelpad=10)
    ax.set_title("去噪效果对比 — 外圈故障 vs 健康样本\n（0dB AWGN 噪声背景）",
                 fontsize=14, fontweight="bold", pad=18)
    ax.legend(fontsize=11, loc="upper right")
    ax.yaxis.set_major_locator(mticker.MultipleLocator(2))
    ax.grid(True, axis="y", alpha=0.25, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    for fmt in ["svg", "png"]:
        fig.savefig(OUTPUT_DIR / f"comparison_denoise.{fmt}")
    plt.close(fig)
    print("  [OK] comparison_denoise")


# ═══════════════════════════════════════════════════════════
# 图6: 鲁棒性评估热力图
# ═══════════════════════════════════════════════════════════
def plot_robustness():
    data = load_json("46_robustness.json")
    snr_levels = data["snr_levels"]
    methods_data = data["methods"]

    method_names = list(methods_data.keys())
    # 构建检出率矩阵：行=方法，列=SNR
    dr_matrix = []
    fpr_matrix = []
    for mname in method_names:
        dr_row = [item.get("detection_rate", 1.0 if item.get("detected") else 0.0) for item in methods_data[mname]]
        fpr_row = [item.get("false_positive_rate", 0.0) for item in methods_data[mname]]
        dr_matrix.append(dr_row)
        fpr_matrix.append(fpr_row)
    dr_matrix = np.array(dr_matrix)
    fpr_matrix = np.array(fpr_matrix)

    fig, ax = plt.subplots(figsize=(10, 7))

    # 连续色标热力图：检出率 0%~100% (RdYlGn: 红→黄→绿)
    cmap = plt.cm.RdYlGn
    im = ax.imshow(dr_matrix, cmap=cmap, aspect="auto", vmin=0, vmax=1)
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("检出率 (Detection Rate)", fontsize=12)

    ax.set_xticks(np.arange(len(snr_levels)))
    ax.set_yticks(np.arange(len(method_names)))
    ax.set_xticklabels([f"{s} dB" for s in snr_levels], fontsize=11)
    ax.set_yticklabels(method_names, fontsize=11)

    # 每个格子里标注检出率 + 误报率
    for i in range(len(method_names)):
        for j in range(len(snr_levels)):
            dr = dr_matrix[i, j]
            fpr = fpr_matrix[i, j]
            text = f"{dr:.0%}\nFP:{fpr:.0%}"
            # 根据背景色亮度决定文字颜色
            color = "white" if dr < 0.35 or dr > 0.85 else "black"
            ax.text(j, i, text, ha="center", va="center", fontsize=9,
                    fontweight="bold", color=color)

    ax.set_title("鲁棒性评估 — 强噪声环境下的故障检出率\n"
                 f"（5样本 × {methods_data[method_names[0]][0].get('total_fault_tests', 0) // 5}次/MC，绿色=高检出率 红色=低检出率）",
                 fontsize=13, fontweight="bold", pad=18)

    fig.tight_layout()
    for fmt in ["svg", "png"]:
        fig.savefig(OUTPUT_DIR / f"comparison_robustness.{fmt}", dpi=150)
    plt.close(fig)
    print("  [OK] comparison_robustness")


# ═══════════════════════════════════════════════════════════
# 图7: 齿轮专门指标在WTgearbox上的表现
# ═══════════════════════════════════════════════════════════
def plot_gear_metrics():
    data = load_json("44c_wtg_gear_metrics.json")

    methods = sorted(data.items(), key=lambda x: x[1]["accuracy"], reverse=True)
    names = [m[0] for m in methods]
    accs = [m[1]["accuracy"] for m in methods]

    fig, ax = plt.subplots(figsize=(12, 8))

    colors = []
    for a in accs:
        if a >= 85:
            colors.append(C["green"])
        elif a >= 75:
            colors.append(C["blue"])
        else:
            colors.append(C["orange"])

    bars = ax.barh(range(len(names)), accs, color=colors, edgecolor="white",
                   linewidth=0.5, zorder=3)

    for i, (bar, val) in enumerate(zip(bars, accs)):
        ax.text(val + 1.0, i, f"{val:.1f}%", va="center", ha="left",
                fontsize=10, fontweight="bold", color=C["dark"])

    ax.axvline(x=50, color=C["light"], linewidth=1, linestyle=":", alpha=0.5)
    ax.text(50, len(names) - 0.3, "随机猜测基准", fontsize=8, color=C["gray"], ha="center")

    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=11)
    ax.set_xlabel("Accuracy (%)", fontsize=13, labelpad=10)
    ax.set_xlim(0, 105)
    ax.set_title("齿轮专门诊断指标 — WTgearbox 行星齿轮箱（80样本）\n" +
                 "（绿色≥85% 蓝色≥75% 橙色<75%）",
                 fontsize=14, fontweight="bold", pad=18)
    ax.grid(True, axis="x", alpha=0.25, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    for fmt in ["svg", "png"]:
        fig.savefig(OUTPUT_DIR / f"comparison_gear_metrics.{fmt}")
    plt.close(fig)
    print("  [OK] comparison_gear_metrics")


def main():
    print("=" * 60)
    print("生成对比图表")
    print(f"输出: {OUTPUT_DIR}")
    print("=" * 60)

    plot_hust_bearing()
    plot_cross_dataset_full()
    plot_accuracy_vs_time()
    plot_const_vs_varying()
    plot_denoise()
    plot_robustness()
    plot_gear_metrics()

    print(f"\n全部对比图表已保存到 {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
