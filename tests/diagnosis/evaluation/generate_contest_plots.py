"""
大创竞赛专用图表生成脚本

基于已有评估缓存生成 8 类核心竞赛图表，优化投影展示效果。
"""
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# 统一学术风格配置
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["font.size"] = 14
plt.rcParams["axes.titlesize"] = 16
plt.rcParams["axes.labelsize"] = 14
plt.rcParams["xtick.labelsize"] = 12
plt.rcParams["ytick.labelsize"] = 12
plt.rcParams["legend.fontsize"] = 12
plt.rcParams["figure.dpi"] = 300
plt.rcParams["savefig.dpi"] = 300
plt.rcParams["figure.facecolor"] = "white"
plt.rcParams["axes.facecolor"] = "white"
plt.rcParams["axes.grid"] = True
plt.rcParams["grid.alpha"] = 0.3

# 统一配色方案（色盲友好 + 投影高对比）
COLORS = {
    "primary": "#2E5AAC",      # 深蓝
    "secondary": "#D9534F",    # 红
    "tertiary": "#5CB85C",     # 绿
    "quaternary": "#F0AD4E",   # 橙黄
    "quinary": "#6C4AB6",      # 紫
    "senary": "#17A2B8",       # 青
    "healthy": "#5CB85C",      # 健康-绿
    "fault": "#D9534F",        # 故障-红
    "neutral": "#777777",      # 灰
}

PALETTE = [COLORS["primary"], COLORS["secondary"], COLORS["tertiary"],
           COLORS["quaternary"], COLORS["quinary"], COLORS["senary"]]


def _load_cache(name: str) -> Any:
    """加载缓存 JSON"""
    path = Path(__file__).resolve().parent.parent.parent.parent / "tests" / "diagnosis" / "output" / "evaluation" / "cache" / f"{name}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════
# 实验a: 混淆矩阵对比（单方法 vs 集成诊断）
# ═══════════════════════════════════════════════════════════
def plot_experiment_a_confusion_matrix(output_dir: Path):
    """生成混淆矩阵对比图：单方法(envelope) vs 集成诊断"""
    cache_single = _load_cache("classification_metrics_轴承_包络分析")
    cache_ensemble = _load_cache("classification_metrics_轴承_ensemble")

    if not cache_single or not cache_ensemble:
        print("[SKIP] 实验a: 缺少混淆矩阵缓存")
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    for ax, cache, title in [
        (axes[0], cache_single, "单方法诊断 (包络分析)"),
        (axes[1], cache_ensemble, "集成诊断 (多算法融合)")
    ]:
        cm = np.array(cache["confusion_matrix"])
        labels = list(cache.get("roc_curves", {}).keys())
        if not labels:
            labels = [f"类{i}" for i in range(cm.shape[0])]

        # 归一化
        row_sums = cm.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1
        cm_norm = cm / row_sums

        im = ax.imshow(cm_norm, cmap="Blues", vmin=0, vmax=1)
        ax.set_xticks(range(len(labels)))
        ax.set_yticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha="right")
        ax.set_yticklabels(labels)
        ax.set_title(title, fontweight="bold")
        ax.set_xlabel("预测标签")
        ax.set_ylabel("真实标签")

        for i in range(len(labels)):
            for j in range(len(labels)):
                text_color = "white" if cm_norm[i, j] > 0.5 else "black"
                ax.text(j, i, f"{cm[i, j]}\n({cm_norm[i, j]:.1%})",
                        ha="center", va="center", color=text_color, fontsize=11)

        plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    plt.tight_layout()
    _ensure_dir(output_dir)
    fig.savefig(output_dir / "experiment_a_confusion_matrix.png", bbox_inches="tight")
    plt.close(fig)
    print(f"  [实验a] 混淆矩阵对比已保存")


# ═══════════════════════════════════════════════════════════
# 实验b: 方法性能柱状图
# ═══════════════════════════════════════════════════════════
def plot_experiment_b_performance_bar(output_dir: Path):
    """生成方法性能柱状图：Accuracy / Macro-F1 / FDR / Kappa"""
    methods = []
    accuracy = []
    macro_f1 = []
    fdr = []
    kappa = []

    # 加载所有轴承方法的分类指标
    method_names = {
        "classification_metrics_轴承_包络分析": "包络分析",
        "classification_metrics_轴承_kurtogram": "Kurtogram",
        "classification_metrics_轴承_cpw预白化": "CPW",
        "classification_metrics_轴承_med增强": "MED",
        "classification_metrics_轴承_teager": "Teager",
        "classification_metrics_轴承_谱峭度重加权": "谱峭度",
        "classification_metrics_轴承_mckd": "MCKD",
        "classification_metrics_轴承_ensemble": "集成诊断",
    }

    for cache_name, display_name in method_names.items():
        cache = _load_cache(cache_name)
        if cache:
            methods.append(display_name)
            accuracy.append(cache.get("accuracy", 0) * 100)
            macro_f1.append(cache.get("macro_f1", 0) * 100)
            fdr.append(cache.get("fdr", 0) * 100)
            kappa.append(cache.get("cohen_kappa", 0) * 100)

    if not methods:
        print("[SKIP] 实验b: 缺少方法性能缓存")
        return

    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(methods))
    width = 0.2

    bars1 = ax.bar(x - 1.5*width, accuracy, width, label="Accuracy", color=COLORS["primary"])
    bars2 = ax.bar(x - 0.5*width, macro_f1, width, label="Macro-F1", color=COLORS["tertiary"])
    bars3 = ax.bar(x + 0.5*width, fdr, width, label="FDR (检出率)", color=COLORS["quaternary"])
    bars4 = ax.bar(x + 1.5*width, kappa, width, label="Kappa", color=COLORS["quinary"])

    ax.set_ylabel("百分比 (%)")
    ax.set_title("轴承诊断方法性能对比 (HUSTbear数据集)", fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(methods, rotation=15, ha="right")
    ax.legend(loc="upper left", ncol=4)
    ax.set_ylim(0, 110)

    # 数值标签
    for bars in [bars1, bars2, bars3, bars4]:
        for bar in bars:
            height = bar.get_height()
            ax.annotate(f"{height:.0f}", xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 3), textcoords="offset points", ha="center", va="bottom",
                        fontsize=8)

    plt.tight_layout()
    _ensure_dir(output_dir)
    fig.savefig(output_dir / "experiment_b_performance_bar.png", bbox_inches="tight")
    plt.close(fig)
    print(f"  [实验b] 方法性能柱状图已保存")


# ═══════════════════════════════════════════════════════════
# 实验c: ROC 曲线
# ═══════════════════════════════════════════════════════════
def plot_experiment_c_roc_curves(output_dir: Path):
    """生成 ROC 曲线对比图"""
    cache_ensemble = _load_cache("classification_metrics_轴承_ensemble")
    if not cache_ensemble:
        print("[SKIP] 实验c: 缺少集成诊断 ROC 缓存")
        return

    fig, ax = plt.subplots(figsize=(8, 7))

    roc_data = cache_ensemble.get("roc_curves", {})
    for idx, (lbl, roc) in enumerate(roc_data.items()):
        fpr = roc.get("fpr", [0, 1])
        tpr = roc.get("tpr", [0, 1])
        auc_val = roc.get("auc", 0.5)
        color = PALETTE[idx % len(PALETTE)]
        ax.plot(fpr, tpr, label=f"{lbl} (AUC={auc_val:.3f})", color=color, linewidth=2)

    ax.plot([0, 1], [0, 1], "k--", alpha=0.4, label="随机分类 (AUC=0.5)")
    ax.set_xlabel("False Positive Rate (虚警率)")
    ax.set_ylabel("True Positive Rate (检出率)")
    ax.set_title("集成诊断 ROC 曲线 (HUSTbear)", fontweight="bold")
    ax.legend(loc="lower right")
    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1])

    plt.tight_layout()
    _ensure_dir(output_dir)
    fig.savefig(output_dir / "experiment_c_roc_curves.png", bbox_inches="tight")
    plt.close(fig)
    print(f"  [实验c] ROC 曲线已保存")


# ═══════════════════════════════════════════════════════════
# 实验d: 鲁棒性衰减曲线 (SNR vs Accuracy)
# ═══════════════════════════════════════════════════════════
def plot_experiment_d_robustness(output_dir: Path):
    """生成鲁棒性衰减曲线"""
    cache = _load_cache("robustness_results")
    if not cache:
        print("[SKIP] 实验d: 缺少鲁棒性缓存")
        return

    # 按方法分组
    methods_data = {}
    for item in cache:
        m = item["method"]
        if m not in methods_data:
            methods_data[m] = {"snr": [], "bpfo_snr": []}
        methods_data[m]["snr"].append(item["input_snr_db"])
        methods_data[m]["bpfo_snr"].append(item["bpfo_snr"])

    fig, ax = plt.subplots(figsize=(10, 6))
    for idx, (method, data) in enumerate(sorted(methods_data.items())):
        # 按 SNR 排序
        pairs = sorted(zip(data["snr"], data["bpfo_snr"]))
        snrs, bpfo_snrs = zip(*pairs) if pairs else ([], [])
        color = PALETTE[idx % len(PALETTE)]
        ax.plot(snrs, bpfo_snrs, marker="o", label=method, color=color, linewidth=2, markersize=8)

    ax.set_xlabel("输入 SNR (dB)")
    ax.set_ylabel("BPFO 谱峰 SNR (dB)")
    ax.set_title("轴承诊断鲁棒性衰减曲线", fontweight="bold")
    ax.legend(loc="upper right")
    ax.invert_xaxis()  # 低 SNR 在右侧，更符合退化直觉

    plt.tight_layout()
    _ensure_dir(output_dir)
    fig.savefig(output_dir / "experiment_d_robustness_snr.png", bbox_inches="tight")
    plt.close(fig)
    print(f"  [实验d] 鲁棒性衰减曲线已保存")


# ═══════════════════════════════════════════════════════════
# 实验e: 去噪效果对比
# ═══════════════════════════════════════════════════════════
def plot_experiment_e_denoise(output_dir: Path):
    """生成去噪效果对比图：SNR 改善量"""
    cache = _load_cache("denoise_results")
    if not cache:
        print("[SKIP] 实验e: 缺少去噪缓存")
        return

    # 按方法和噪声等级分组，计算平均 SNR 改善
    method_noise_snr = {}
    for item in cache:
        m = item["method"]
        noise = item.get("noise_snr", "unknown")
        improvement = item.get("snr_improvement_db", 0)
        key = (m, noise)
        if key not in method_noise_snr:
            method_noise_snr[key] = []
        method_noise_snr[key].append(improvement)

    # 只取有明确噪声等级的
    methods = sorted(set(k[0] for k in method_noise_snr.keys()))
    noise_levels = sorted(set(k[1] for k in method_noise_snr.keys() if k[1] != "unknown"),
                          key=lambda x: int(x.replace("dB", "")))

    if not noise_levels:
        print("[SKIP] 实验e: 无有效噪声等级")
        return

    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(noise_levels))
    width = 0.8 / len(methods)

    for idx, method in enumerate(methods):
        values = []
        for nl in noise_levels:
            vals = method_noise_snr.get((method, nl), [0])
            values.append(np.mean(vals))
        color = PALETTE[idx % len(PALETTE)]
        ax.bar(x + idx * width - (len(methods)-1)*width/2, values, width,
               label=method, color=color)

    ax.set_xlabel("输入噪声等级")
    ax.set_ylabel("SNR 改善量 (dB)")
    ax.set_title("去噪方法 SNR 改善对比", fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(noise_levels)
    ax.legend(loc="upper right", ncol=3)
    ax.axhline(y=0, color="black", linestyle="--", alpha=0.5)

    plt.tight_layout()
    _ensure_dir(output_dir)
    fig.savefig(output_dir / "experiment_e_denoise_comparison.png", bbox_inches="tight")
    plt.close(fig)
    print(f"  [实验e] 去噪效果对比已保存")


# ═══════════════════════════════════════════════════════════
# 实验f: 箱线图（健康 vs 故障指标分布）
# ═══════════════════════════════════════════════════════════
def plot_experiment_f_boxplot(output_dir: Path):
    """生成齿轮诊断指标箱线图"""
    cache = _load_cache("gear_results")
    if not cache:
        print("[SKIP] 实验f: 缺少齿轮缓存")
        return

    # 选取有区分度的指标
    metrics = [
        ("ser", "SER (边频带能量比)"),
        ("fm4", "FM4 (局部故障指标)"),
        ("car", "CAR (倒频谱幅值比)"),
        ("tsa_kurt", "TSA 残差峭度"),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    axes_flat = axes.flatten()

    for idx, (key, title) in enumerate(metrics):
        ax = axes_flat[idx]
        healthy_vals = [r[key] for r in cache if r["fault_label"] == "healthy"]
        fault_vals = [r[key] for r in cache if r["fault_label"] != "healthy"]

        if not healthy_vals or not fault_vals:
            ax.set_title(f"{title} (无数据)")
            continue

        bp = ax.boxplot([healthy_vals, fault_vals], tick_labels=["健康", "故障"],
                        patch_artist=True, widths=0.5)
        bp["boxes"][0].set_facecolor(COLORS["healthy"])
        bp["boxes"][1].set_facecolor(COLORS["fault"])
        bp["medians"][0].set_color("black")
        bp["medians"][1].set_color("black")
        ax.set_title(title, fontweight="bold")
        ax.set_ylabel("指标值")

    plt.suptitle("齿轮诊断指标分布对比 (WTgearbox)", fontsize=16, fontweight="bold", y=1.02)
    plt.tight_layout()
    _ensure_dir(output_dir)
    fig.savefig(output_dir / "experiment_f_boxplot.png", bbox_inches="tight")
    plt.close(fig)
    print(f"  [实验f] 箱线图已保存")


# ═══════════════════════════════════════════════════════════
# 实验g: 健康度退化轨迹
# ═══════════════════════════════════════════════════════════
def plot_experiment_g_health_degradation(output_dir: Path):
    """生成健康度退化轨迹（基于 gear_results 的伪退化序列）"""
    cache = _load_cache("gear_results")
    if not cache:
        print("[SKIP] 实验g: 缺少齿轮缓存")
        return

    # 按故障类型分组，按转速排序构造退化序列
    from collections import defaultdict
    fault_sequences = defaultdict(list)
    for r in cache:
        fault_sequences[r["fault_label"]].append(r)

    fig, ax = plt.subplots(figsize=(10, 6))

    for idx, (label, items) in enumerate(sorted(fault_sequences.items())):
        # 按转速排序
        items_sorted = sorted(items, key=lambda x: x.get("rot_freq", 0))
        x_vals = list(range(1, len(items_sorted) + 1))
        y_vals = [r["health_score"] for r in items_sorted]
        color = COLORS["healthy"] if label == "healthy" else COLORS["fault"]
        marker = "o" if label == "healthy" else "s"
        linestyle = "--" if label == "healthy" else "-"
        ax.plot(x_vals, y_vals, marker=marker, linestyle=linestyle, label=label,
                color=color, linewidth=2, markersize=8, alpha=0.8)

    ax.axhline(y=85, color="gray", linestyle="--", alpha=0.7, label="预警阈值=85")
    ax.axhline(y=60, color="red", linestyle="--", alpha=0.7, label="报警阈值=60")
    ax.set_xlabel("样本序号")
    ax.set_ylabel("健康度评分")
    ax.set_title("齿轮箱健康度退化轨迹", fontweight="bold")
    ax.legend(loc="lower left", ncol=2)
    ax.set_ylim(0, 105)

    plt.tight_layout()
    _ensure_dir(output_dir)
    fig.savefig(output_dir / "experiment_g_health_degradation.png", bbox_inches="tight")
    plt.close(fig)
    print(f"  [实验g] 健康度退化轨迹已保存")


# ═══════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════
def main():
    output_dir = Path(__file__).resolve().parent.parent.parent.parent / "tests" / "output" / "contest_plots"
    _ensure_dir(output_dir)

    print("=" * 60)
    print("大创竞赛图表生成")
    print("=" * 60)

    plot_experiment_a_confusion_matrix(output_dir)
    plot_experiment_b_performance_bar(output_dir)
    plot_experiment_c_roc_curves(output_dir)
    plot_experiment_d_robustness(output_dir)
    plot_experiment_e_denoise(output_dir)
    plot_experiment_f_boxplot(output_dir)
    plot_experiment_g_health_degradation(output_dir)

    print("=" * 60)
    print(f"全部图表已保存至: {output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
