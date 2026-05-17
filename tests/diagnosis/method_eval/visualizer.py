"""
可视化模块

提供评估结果的图表绘制功能：
1. 混淆矩阵图（默认 Blues 风格）
2. 多方法性能柱状图
3. 召回率热力图
4. 雷达图（综合能力对比）
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from typing import Dict, List, Optional, Tuple

from .config import STYLE, LABEL_CN


# ═══════════════════════════════════════════════════════════
# 全局风格设置
# ═══════════════════════════════════════════════════════════
def apply_style():
    """应用统一绘图风格"""
    plt.rcParams.update({
        "font.family": STYLE["font.family"],
        "font.size": STYLE["font.size"],
        "axes.titlesize": STYLE["axes.titlesize"],
        "axes.labelsize": STYLE["axes.labelsize"],
        "figure.dpi": STYLE["figure.dpi"],
        "savefig.bbox": STYLE["savefig.bbox"],
        "axes.unicode_minus": False,
    })

apply_style()

COLORS = STYLE["colors"]


# ═══════════════════════════════════════════════════════════
# 1. 混淆矩阵（默认 Blues 风格）
# ═══════════════════════════════════════════════════════════

def plot_confusion_matrix(
    cm: np.ndarray,
    labels: List[str],
    method_name: str,
    accuracy: float,
    output_path: str,
    highlight: bool = False,
):
    """绘制混淆矩阵图（默认 Blues 风格，清晰可读）

    参数:
        cm: 混淆矩阵 (n×n)，原始计数
        labels: 标签列表（英文）
        method_name: 方法名称
        accuracy: 准确率
        output_path: 保存路径
        highlight: 是否高亮标题（Ensemble 用红色）
    """
    n = len(labels)
    labels_cn = [LABEL_CN.get(l, l) for l in labels]

    # 归一化
    cm_norm = cm.astype(float) / cm.sum(axis=1, keepdims=True)
    cm_norm = np.nan_to_num(cm_norm)

    fig, ax = plt.subplots(figsize=(8, 6))

    # 默认 Blues 配色
    im = ax.imshow(cm_norm, cmap="Blues", interpolation="nearest", vmin=0, vmax=1)

    # 标注数值（归一化百分比 + 原始计数）
    for i in range(n):
        for j in range(n):
            val_norm = cm_norm[i, j]
            val_raw = int(cm[i, j])
            # 数值较大时用白色文字，否则用黑色
            text_color = "white" if val_norm > 0.5 else "black"
            ax.text(j, i, f"{val_norm:.0%}\n({val_raw})",
                    ha="center", va="center", fontsize=10,
                    color=text_color, fontweight="bold" if i == j else "normal")

    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(labels_cn, rotation=45, ha="right")
    ax.set_yticklabels(labels_cn)
    ax.set_xlabel("预测标签", fontsize=12)
    ax.set_ylabel("真实标签", fontsize=12)

    title_color = COLORS["our_method"] if highlight else "#333333"
    ax.set_title(
        f"{method_name}\n准确率 = {accuracy:.1%}",
        fontsize=14, fontweight="bold", color=title_color,
    )

    # 添加颜色条
    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("归一化比例", fontsize=10)

    plt.tight_layout()
    fig.savefig(output_path, dpi=STYLE["figure.dpi"])
    plt.close(fig)
    print(f"  [图] 混淆矩阵已保存: {output_path}")


# ═══════════════════════════════════════════════════════════
# 2. 多方法性能柱状图
# ═══════════════════════════════════════════════════════════

def plot_method_comparison_bar(
    method_names: List[str],
    metrics: Dict[str, List[float]],
    metric_label: str,
    title: str,
    output_path: str,
    highlight_indices: Optional[List[int]] = None,
    ylim: Optional[Tuple[float, float]] = None,
):
    """绘制多方法性能对比柱状图

    参数:
        method_names: 方法名称列表
        metrics: 指标字典 {metric_name: [values]}
        metric_label: 要绘制的指标名（如 "accuracy"）
        title: 图表标题
        output_path: 保存路径
        highlight_indices: 要高亮的方法索引（Ensemble）
        ylim: Y轴范围
    """
    values = metrics[metric_label]
    n = len(method_names)

    # 颜色
    bar_colors = []
    for i in range(n):
        if highlight_indices and i in highlight_indices:
            bar_colors.append(COLORS["our_method"])  # 红色高亮
        else:
            bar_colors.append(COLORS["baseline"])  # 灰色

    fig, ax = plt.subplots(figsize=(max(10, n * 1.2), 6))

    bars = ax.bar(range(n), values, color=bar_colors, edgecolor="white",
                  linewidth=0.5, width=0.7)

    # 标注数值
    for i, (bar, val) in enumerate(zip(bars, values)):
        is_highlight = highlight_indices and i in highlight_indices
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                f"{val:.1%}" if val <= 1 else f"{val:.1f}",
                ha="center", va="bottom", fontsize=10, fontweight="bold",
                color=COLORS["our_method"] if is_highlight else "#333333")

    ax.set_xticks(range(n))
    ax.set_xticklabels(method_names, rotation=30, ha="right", fontsize=11)

    # Y 轴标签
    y_label_map = {
        "accuracy": "准确率 (Accuracy)",
        "macro_f1": "Macro-F1",
        "macro_auc_roc": "Macro-AUC-ROC",
    }
    ax.set_ylabel(y_label_map.get(metric_label, metric_label), fontsize=12)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.grid(axis="y", alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    if ylim:
        ax.set_ylim(ylim)

    # Legend
    legend_elements = [
        mpatches.Patch(facecolor=COLORS["baseline"], label="单一方法"),
    ]
    if highlight_indices:
        legend_elements.append(
            mpatches.Patch(facecolor=COLORS["our_method"], label="Ensemble 集成")
        )
    ax.legend(handles=legend_elements, loc="upper left", fontsize=10)

    plt.tight_layout()
    fig.savefig(output_path, dpi=STYLE["figure.dpi"])
    plt.close(fig)
    print(f"  [图] 柱状图已保存: {output_path}")


# ═══════════════════════════════════════════════════════════
# 3. 召回率热力图
# ═══════════════════════════════════════════════════════════

def plot_recall_heatmap(
    methods: List[str],
    labels: List[str],
    recall_matrix: np.ndarray,
    output_path: str,
):
    """绘制每类故障的召回率热力图"""
    labels_cn = [LABEL_CN.get(l, l) for l in labels]
    n_methods = len(methods)
    n_labels = len(labels)

    fig, ax = plt.subplots(figsize=(max(8, n_labels * 1.5), max(6, n_methods * 0.6)))

    im = ax.imshow(recall_matrix, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")

    for i in range(n_methods):
        for j in range(n_labels):
            val = recall_matrix[i, j]
            text_color = "white" if val > 0.7 else "black"
            ax.text(j, i, f"{val:.0%}", ha="center", va="center",
                    fontsize=10, color=text_color, fontweight="bold")

    ax.set_xticks(range(n_labels))
    ax.set_xticklabels(labels_cn, fontsize=11)
    ax.set_yticks(range(n_methods))
    ax.set_yticklabels(methods, fontsize=10)
    ax.set_xlabel("故障类型", fontsize=12)
    ax.set_ylabel("诊断方法", fontsize=12)
    ax.set_title("各方法对每类故障的召回率（Recall）", fontsize=14, fontweight="bold")

    cbar = plt.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("召回率", fontsize=10)

    plt.tight_layout()
    fig.savefig(output_path, dpi=STYLE["figure.dpi"])
    plt.close(fig)
    print(f"  [图] 召回率热力图已保存: {output_path}")


# ═══════════════════════════════════════════════════════════
# 4. 雷达图（综合能力对比）
# ═══════════════════════════════════════════════════════════

def plot_radar_chart(
    method_names: List[str],
    dimensions: List[str],
    data: np.ndarray,
    output_path: str,
    highlight_indices: Optional[List[int]] = None,
    title: str = "诊断方法综合能力对比",
):
    """绘制雷达图"""
    n_methods = len(method_names)
    n_dims = len(dimensions)

    angles = np.linspace(0, 2 * np.pi, n_dims, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(10, 8), subplot_kw=dict(polar=True))

    for i in range(n_methods):
        values = data[i].tolist()
        values += values[:1]

        is_highlight = highlight_indices and i in highlight_indices
        color = COLORS["our_method"] if is_highlight else COLORS["baseline"]
        linewidth = 2.5 if is_highlight else 1.2
        alpha = 0.9 if is_highlight else 0.4

        ax.plot(angles, values, color=color, linewidth=linewidth, alpha=alpha,
                label=method_names[i])
        ax.fill(angles, values, color=color, alpha=alpha * 0.2)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(dimensions, fontsize=11)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(["0.2", "0.4", "0.6", "0.8", "1.0"], fontsize=9)
    ax.set_title(title, fontsize=14, fontweight="bold", pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=10)

    plt.tight_layout()
    fig.savefig(output_path, dpi=STYLE["figure.dpi"])
    plt.close(fig)
    print(f"  [图] 雷达图已保存: {output_path}")
