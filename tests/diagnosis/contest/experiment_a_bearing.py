"""
大创答辩 — 实验A：轴承故障分类对比

生成4张答辩图表：
1. 混淆矩阵对比图（左：单一包络方法，右：Ensemble集成方法）
2. 多方法性能柱状图（Accuracy对比，Ensemble红色高亮）
3. ROC曲线对比图（包络 vs Ensemble，标注AUC值）
4. 指标汇总Markdown表格

用法:
    cd /d/code/CNN/cloud
    . venv/Scripts/activate
    python -m tests.diagnosis.contest.experiment_a_bearing
"""
import sys
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

warnings.filterwarnings("ignore")

# ── 项目路径 ──────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))

# ── 导入诊断引擎 ──────────────────────────────────────────────
from app.services.diagnosis.engine import (
    DiagnosisEngine, DiagnosisStrategy, BearingMethod, DenoiseMethod,
)
from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum

# ── 导入 contest 模块 ──────────────────────────────────────────
from contest.config import (
    HUSTBEAR_DIR, SAMPLE_RATE, MAX_SAMPLES, MAX_PER_CLASS_HUSTBEAR,
    HUSTBEAR_BEARING, HEALTH_THRESHOLD, BEARING_LABELS, LABEL_CN,
    BEARING_METHODS_COMPARE, EXP_DIRS,
)
from contest.style import (
    apply_contest_style, COLORS, CM_COLORS, get_method_color,
    make_conclusion_title, FIGURE_SIZE_WIDE, FIGURE_SIZE, FIGURE_SIZE_TALL,
    FIGURE_DPI,
)

# ── 导入 evaluation 模块的分类指标 ────────────────────────────
from tests.diagnosis.evaluation.classification_metrics_eval import (
    evaluate_classification_performance,
    generate_classification_metrics_table,
)
from tests.diagnosis.evaluation.datasets import classify_hustbear
from tests.diagnosis.evaluation.utils import (
    load_npy, compute_confusion_matrix, compute_multiclass_roc_pr,
)

# ── Matplotlib ────────────────────────────────────────────────
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

apply_contest_style()

OUTPUT_DIR = EXP_DIRS["a_bearing"]


# ═══════════════════════════════════════════════════════════════
# 方法定义
# ═══════════════════════════════════════════════════════════════

# 单一方法映射：(显示名, BearingMethod枚举值)
SINGLE_METHODS = [
    ("FFT阈值",    None),             # FFT 频谱阈值 — 无轴承包络方法，仅频域判断
    ("包络分析",   BearingMethod.ENVELOPE),
    ("Kurtogram",  BearingMethod.KURTOGRAM),
    ("MED增强",    BearingMethod.MED),
    ("MCKD",       BearingMethod.MCKD),
    ("CPW预白化",  BearingMethod.CPW),
    ("Teager",     BearingMethod.TEAGER),
    ("谱峭度重加权", BearingMethod.SPECTRAL_KURTOSIS),
]

# Ensemble 方法单独处理
ENSEMBLE_METHOD = "ensemble"


# ═══════════════════════════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════════════════════════

def get_hustbear_files_contest() -> List[Tuple[Path, Dict]]:
    """获取 HUSTbear 数据集文件（仅 X 通道，每类最多 MAX_PER_CLASS_HUSTBEAR 个）"""
    if not HUSTBEAR_DIR.exists():
        print(f"[SKIP] HUSTbear 目录不存在: {HUSTBEAR_DIR}")
        return []
    from collections import defaultdict
    files_by_class = defaultdict(list)
    for f in sorted(HUSTBEAR_DIR.glob("*.npy")):
        if not f.name.endswith("-X.npy"):
            continue
        info = classify_hustbear(f.name)
        if info["label"] in BEARING_LABELS:
            files_by_class[info["label"]].append((f, info))
    result = []
    for lbl in BEARING_LABELS:
        result.extend(files_by_class[lbl][:MAX_PER_CLASS_HUSTBEAR])
    return result


# ═══════════════════════════════════════════════════════════════
# 预测标签推断
# ═══════════════════════════════════════════════════════════════

def infer_pred_label_from_result(comp_result: Dict[str, Any]) -> str:
    """从 analyze_comprehensive 结果推断预测标签

    规则：
    - health_score >= HEALTH_THRESHOLD → "healthy"
    - health_score < HEALTH_THRESHOLD → 根据 fault_indicators 推断具体故障类型
      - BPFI 显著 → "inner"
      - BPFO 显著 → "outer"
      - BSF 显显著 → "ball"
      - 多个显著 → "composite"
      - 无物理参数显著但有统计显著 → "inner"（内圈最常见）
      - 无任何显著 → "composite"（判定为故障但无法确定类型）
    """
    hs = int(comp_result.get("health_score", 100))
    if hs >= HEALTH_THRESHOLD:
        return "healthy"

    # 从轴承分析中获取 fault_indicators
    bearing = comp_result.get("bearing", {})
    indicators = bearing.get("fault_indicators", {}) or {}

    # 物理参数显著项
    param_hits = []
    for name, item in indicators.items():
        if isinstance(item, dict) and bool(item.get("significant", False)) and not name.endswith("_stat"):
            param_hits.append(name)

    if not param_hits:
        # 无物理参数显著 → 检查统计指标
        stat_hits = [
            name for name, item in indicators.items()
            if isinstance(item, dict) and bool(item.get("significant", False)) and name.endswith("_stat")
        ]
        if stat_hits:
            # 统计指标显著，默认标记为最常见的 inner
            return "inner"
        # 无任何显著指标，但 health_score < 85 → 标记 composite
        return "composite"

    # 物理参数显著 → 按显著项映射故障类型
    fault_map = {
        "BPFI": "inner",
        "BPFO": "outer",
        "BSF": "ball",
        "FTF": "composite",
    }
    mapped = [fault_map.get(h, "composite") for h in param_hits]
    # 多种故障类型 → composite
    unique_types = list(set(mapped))
    if len(unique_types) == 1:
        return unique_types[0]
    return "composite"


def infer_pred_label_ensemble(ensemble_result: Dict[str, Any]) -> str:
    """从 Ensemble (EXPERT策略) 结果推断预测标签

    Ensemble 返回的 fault_label 格式:
    - "unknown" → healthy
    - "bearing_BPFI" → inner
    - "bearing_BPFO" → outer
    - "bearing_BSF" → ball
    - "bearing_BPFI_BPFO" → composite
    - "bearing_abnormal" → composite
    - "gear_abnormal" → composite（轴承实验中忽略齿轮）
    """
    hs = int(ensemble_result.get("health_score", 100))
    if hs >= HEALTH_THRESHOLD:
        return "healthy"

    fault_label = ensemble_result.get("fault_label", "unknown")

    if fault_label == "unknown" or fault_label == "healthy":
        return "healthy"

    # 解析 fault_label
    if "BPFI" in fault_label and "BPFO" in fault_label:
        return "composite"
    if "BPFI" in fault_label:
        return "inner"
    if "BPFO" in fault_label:
        return "outer"
    if "BSF" in fault_label:
        return "ball"

    # bearing_abnormal / gear_abnormal → 标记为 composite
    if "abnormal" in fault_label:
        return "composite"

    return "composite"


# ═══════════════════════════════════════════════════════════════
# 运行所有方法
# ═══════════════════════════════════════════════════════════════

def run_all_methods() -> Dict[str, Dict[str, Any]]:
    """对所有样本运行所有方法，收集 y_true, y_pred, health_score

    Returns:
        {method_name: {"y_true": [...], "y_pred": [...], "scores": [...], "exec_times": [...]}}
    """
    files = get_hustbear_files_contest()
    if not files:
        print("[ERROR] 无可用数据文件，退出")
        return {}

    print(f"\n{'=' * 60}")
    print(f"【实验A】轴承故障分类对比 — HUSTbear 数据集")
    print(f"  样本数: {len(files)}")
    print(f"  类别: {BEARING_LABELS}")
    print(f"  每类上限: {MAX_PER_CLASS_HUSTBEAR}")
    print(f"{'=' * 60}")

    results = {}

    # ── 运行单一方法 ──────────────────────────────────────
    for display_name, bm_enum in SINGLE_METHODS:
        print(f"\n  ▶ 运行方法: {display_name}")
        y_true_list = []
        y_pred_list = []
        score_list = []
        time_list = []

        for filepath, info in files:
            signal = load_npy(filepath)
            rot_freq = estimate_rot_freq_spectrum(signal, SAMPLE_RATE)

            try:
                t0 = time.perf_counter()

                if bm_enum is None:
                    # FFT阈值方法：使用 envelope 作为基础，仅频域判断
                    engine = DiagnosisEngine(
                        strategy=DiagnosisStrategy.STANDARD,
                        bearing_method=BearingMethod.ENVELOPE,
                        denoise_method=DenoiseMethod.NONE,
                        bearing_params=HUSTBEAR_BEARING,
                    )
                else:
                    engine = DiagnosisEngine(
                        strategy=DiagnosisStrategy.ADVANCED,
                        bearing_method=bm_enum,
                        denoise_method=DenoiseMethod.NONE,
                        bearing_params=HUSTBEAR_BEARING,
                    )

                comp = engine.analyze_comprehensive(signal, SAMPLE_RATE, rot_freq=rot_freq)
                elapsed = (time.perf_counter() - t0) * 1000

                pred = infer_pred_label_from_result(comp)
                hs = int(comp.get("health_score", 100))

                y_true_list.append(info["label"])
                y_pred_list.append(pred)
                score_list.append(100 - hs)  # 反转：故障分数越高→越可能故障
                time_list.append(elapsed)

            except Exception as e:
                print(f"    [ERR] {filepath.name}: {e}")
                y_true_list.append(info["label"])
                y_pred_list.append("healthy")
                score_list.append(0.0)
                time_list.append(0.0)

        results[display_name] = {
            "y_true": y_true_list,
            "y_pred": y_pred_list,
            "scores": score_list,
            "exec_times": time_list,
        }

        # 计算准确率
        correct = sum(1 for yt, yp in zip(y_true_list, y_pred_list) if yt == yp)
        acc = correct / len(y_true_list) if y_true_list else 0.0
        avg_time = np.mean(time_list) if time_list else 0.0
        print(f"    Accuracy: {acc:.2%}  平均耗时: {avg_time:.1f} ms")

    # ── 运行 Ensemble 方法 ────────────────────────────────
    print(f"\n  ▶ 运行方法: 集成Ensemble (EXPERT策略)")
    y_true_list = []
    y_pred_list = []
    score_list = []
    time_list = []

    for filepath, info in files:
        signal = load_npy(filepath)
        rot_freq = estimate_rot_freq_spectrum(signal, SAMPLE_RATE)

        try:
            t0 = time.perf_counter()
            engine = DiagnosisEngine(
                strategy=DiagnosisStrategy.EXPERT,
                bearing_method=BearingMethod.ENVELOPE,  # EXPERT 模式会跑全方法
                denoise_method=DenoiseMethod.NONE,
                bearing_params=HUSTBEAR_BEARING,
            )
            ensemble_result = engine.analyze_research_ensemble(
                signal, SAMPLE_RATE, rot_freq=rot_freq,
                profile="runtime", max_seconds=5.0,
            )
            elapsed = (time.perf_counter() - t0) * 1000

            pred = infer_pred_label_ensemble(ensemble_result)
            hs = int(ensemble_result.get("health_score", 100))

            y_true_list.append(info["label"])
            y_pred_list.append(pred)
            score_list.append(100 - hs)
            time_list.append(elapsed)

        except Exception as e:
            print(f"    [ERR] {filepath.name}: {e}")
            y_true_list.append(info["label"])
            y_pred_list.append("healthy")
            score_list.append(0.0)
            time_list.append(0.0)

    results[ENSEMBLE_METHOD] = {
        "y_true": y_true_list,
        "y_pred": y_pred_list,
        "scores": score_list,
        "exec_times": time_list,
    }

    correct = sum(1 for yt, yp in zip(y_true_list, y_pred_list) if yt == yp)
    acc = correct / len(y_true_list) if y_true_list else 0.0
    avg_time = np.mean(time_list) if time_list else 0.0
    print(f"    Accuracy: {acc:.2%}  平均耗时: {avg_time:.1f} ms")

    return results


# ═══════════════════════════════════════════════════════════════
# 图1：混淆矩阵对比图（包络 vs Ensemble 并排）
# ═══════════════════════════════════════════════════════════════

def plot_confusion_matrix_comparison(results: Dict[str, Dict]):
    """绘制混淆矩阵对比图：左=包络分析，右=Ensemble"""
    envelope_data = results.get("包络分析", {})
    ensemble_data = results.get(ENSEMBLE_METHOD, {})

    if not envelope_data or not ensemble_data:
        print("[SKIP] 混淆矩阵对比图：缺少数据")
        return

    # 计算混淆矩阵
    cn_labels = [LABEL_CN[l] for l in BEARING_LABELS]
    cm_env = compute_confusion_matrix(envelope_data["y_true"], envelope_data["y_pred"], BEARING_LABELS)
    cm_ens = compute_confusion_matrix(ensemble_data["y_true"], ensemble_data["y_pred"], BEARING_LABELS)

    # 归一化
    cm_env_norm = cm_env.astype(float) / cm_env.sum(axis=1, keepdims=True)
    cm_env_norm = np.nan_to_num(cm_env_norm)
    cm_ens_norm = cm_ens.astype(float) / cm_ens.sum(axis=1, keepdims=True)
    cm_ens_norm = np.nan_to_num(cm_ens_norm)

    # 计算准确率
    acc_env = sum(1 for yt, yp in zip(envelope_data["y_true"], envelope_data["y_pred"]) if yt == yp) / len(envelope_data["y_true"])
    acc_ens = sum(1 for yt, yp in zip(ensemble_data["y_true"], ensemble_data["y_pred"]) if yt == yp) / len(ensemble_data["y_true"])

    # 生成结论标题
    title = make_conclusion_title("轴承故障分类准确率", acc_env * 100, acc_ens * 100, unit="%")

    fig, axes = plt.subplots(1, 2, figsize=FIGURE_SIZE_WIDE)
    fig.suptitle(title, fontsize=18, fontweight="bold", y=1.02)

    for idx, (ax, cm_norm, cm_raw, label, acc, color_map) in enumerate([
        (axes[0], cm_env_norm, cm_env, "包络分析", acc_env, CM_COLORS),
        (axes[1], cm_ens_norm, cm_ens, "集成Ensemble", acc_ens, CM_COLORS),
    ]):
        # 自定义颜色：正确=深蓝，错误=浅灰白
        display = np.zeros((*cm_norm.shape, 3))
        for i in range(cm_norm.shape[0]):
            for j in range(cm_norm.shape[1]):
                if i == j:
                    # 正确分类：深蓝色，强度按比例
                    intensity = min(float(cm_norm[i, j]), 1.0)
                    # 解析 CM_COLORS["correct"] → RGB
                    r, g, b = _hex_to_rgb(CM_COLORS["correct"])
                    display[i, j] = (r * intensity, g * intensity, b * intensity)
                else:
                    # 错误分类：浅灰白，强度按比例
                    intensity = min(float(cm_norm[i, j]), 1.0)
                    r, g, b = _hex_to_rgb(CM_COLORS["incorrect"])
                    display[i, j] = (r + (1 - r) * intensity, g + (1 - g) * intensity, b + (1 - b) * intensity)

        ax.imshow(display, interpolation="nearest")

        # 标注数值
        for i in range(len(cn_labels)):
            for j in range(len(cn_labels)):
                val_norm = cm_norm[i, j]
                val_raw = cm_raw[i, j]
                text_color = "white" if i == j and float(val_norm) > 0.3 else "black"
                ax.text(j, i, f"{val_norm:.2f}\n({val_raw})",
                        ha="center", va="center", fontsize=11,
                        color=text_color, fontweight="bold" if i == j else "normal")

        ax.set_xticks(range(len(cn_labels)))
        ax.set_yticks(range(len(cn_labels)))
        ax.set_xticklabels(cn_labels, rotation=45, ha="right")
        ax.set_yticklabels(cn_labels)
        ax.set_xlabel("预测标签")
        ax.set_ylabel("真实标签")
        ax.set_title(f"{label}\nAccuracy = {acc:.1%}", fontsize=14)

    plt.tight_layout()
    path = OUTPUT_DIR / "fig1_confusion_matrix_comparison.png"
    fig.savefig(path, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  [图1] 混淆矩阵对比图已保存: {path}")


# ═══════════════════════════════════════════════════════════════
# 图2：多方法性能柱状图（Accuracy对比）
# ═══════════════════════════════════════════════════════════════

def plot_accuracy_bar(results: Dict[str, Dict]):
    """绘制所有方法的 Accuracy 柱状图，Ensemble 红色高亮"""
    method_names = []
    accuracies = []
    bar_colors = []

    for display_name, _ in SINGLE_METHODS:
        data = results.get(display_name, {})
        if not data:
            continue
        correct = sum(1 for yt, yp in zip(data["y_true"], data["y_pred"]) if yt == yp)
        acc = correct / len(data["y_true"]) if data["y_true"] else 0.0
        method_names.append(display_name)
        accuracies.append(acc * 100)
        bar_colors.append(COLORS["baseline"])  # 灰色

    # Ensemble 红色
    ens_data = results.get(ENSEMBLE_METHOD, {})
    if ens_data:
        correct = sum(1 for yt, yp in zip(ens_data["y_true"], ens_data["y_pred"]) if yt == yp)
        acc = correct / len(ens_data["y_true"]) if ens_data["y_true"] else 0.0
        method_names.append("集成Ensemble")
        accuracies.append(acc * 100)
        bar_colors.append(COLORS["our_method"])  # 红色

    if not method_names:
        print("[SKIP] 柱状图：无数据")
        return

    # 找到 baseline 最高和 ensemble 的值用于标题
    baseline_best = max(accuracies[:-1]) if len(accuracies) > 1 else accuracies[0]
    ensemble_acc = accuracies[-1]
    title = make_conclusion_title("轴承故障分类准确率", baseline_best, ensemble_acc, unit="%")

    fig, ax = plt.subplots(figsize=FIGURE_SIZE)

    bars = ax.bar(range(len(method_names)), accuracies, color=bar_colors, edgecolor="white", linewidth=0.5, width=0.7)

    # 在柱子上标注数值
    for i, (bar, val) in enumerate(zip(bars, accuracies)):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5,
                f"{val:.1f}%", ha="center", va="bottom",
                fontsize=11, fontweight="bold",
                color=COLORS["our_method"] if method_names[i] == "集成Ensemble" else "#333333")

    ax.set_xticks(range(len(method_names)))
    ax.set_xticklabels(method_names, rotation=30, ha="right")
    ax.set_ylabel("Accuracy (%)")
    ax.set_ylim(0, 105)
    ax.set_title(title, fontsize=16, fontweight="bold")
    ax.grid(axis="y", alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # 添加 legend 标注颜色含义
    legend_elements = [
        mpatches.Patch(facecolor=COLORS["baseline"], label="单一方法"),
        mpatches.Patch(facecolor=COLORS["our_method"], label="集成Ensemble（我们方法）"),
    ]
    ax.legend(handles=legend_elements, loc="upper left", fontsize=12)

    plt.tight_layout()
    path = OUTPUT_DIR / "fig2_accuracy_bar.png"
    fig.savefig(path, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  [图2] Accuracy柱状图已保存: {path}")


# ═══════════════════════════════════════════════════════════════
# 图3：ROC曲线对比图（包络 vs Ensemble）
# ═══════════════════════════════════════════════════════════════

def plot_roc_comparison(results: Dict[str, Dict]):
    """绘制 ROC 曲线对比图：包络分析 vs 集成Ensemble，标注 AUC"""
    envelope_data = results.get("包络分析", {})
    ensemble_data = results.get(ENSEMBLE_METHOD, {})

    if not envelope_data or not ensemble_data:
        print("[SKIP] ROC对比图：缺少数据")
        return

    fig, axes = plt.subplots(1, 2, figsize=FIGURE_SIZE_WIDE)

    for idx, (ax, data, method_label) in enumerate([
        (axes[0], envelope_data, "包络分析"),
        (axes[1], ensemble_data, "集成Ensemble"),
    ]):
        roc_data = compute_multiclass_roc_pr(
            data["y_true"], data["scores"], BEARING_LABELS
        )

        # 绘制各类 ROC 曲线
        for lbl in BEARING_LABELS:
            roc = roc_data["roc"].get(lbl, {})
            fpr = roc.get("fpr", [0, 1])
            tpr = roc.get("tpr", [0, 1])
            auc_val = roc.get("auc", 0.5)
            cn_lbl = LABEL_CN.get(lbl, lbl)

            # 包络用灰色线，Ensemble 用彩色线
            if method_label == "包络分析":
                line_color = COLORS["baseline"]
                line_alpha = 0.7
            else:
                line_color = get_method_color(lbl)
                line_alpha = 1.0

            ax.plot(fpr, tpr, label=f"{cn_lbl} (AUC={auc_val:.3f})",
                    color=line_color, alpha=line_alpha, linewidth=2)

        # 对角线（随机）
        ax.plot([0, 1], [0, 1], "--", color=COLORS["diagonal"], alpha=0.5, label="随机基线")

        # Macro AUC 标注
        macro_auc = roc_data.get("macro_auc_roc", 0.5)
        ax.text(0.55, 0.35, f"Macro-AUC = {macro_auc:.3f}",
                fontsize=13, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="gray", alpha=0.9))

        ax.set_xlabel("FPR (虚警率)")
        ax.set_ylabel("TPR (检出率)")
        ax.set_title(f"{method_label} ROC曲线", fontsize=14)
        ax.legend(loc="lower right", fontsize=9)
        ax.set_xlim([0, 1])
        ax.set_ylim([0, 1])
        ax.grid(alpha=0.3)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    # 总标题
    env_macro = compute_multiclass_roc_pr(
        envelope_data["y_true"], envelope_data["scores"], BEARING_LABELS
    ).get("macro_auc_roc", 0.5)
    ens_macro = compute_multiclass_roc_pr(
        ensemble_data["y_true"], ensemble_data["scores"], BEARING_LABELS
    ).get("macro_auc_roc", 0.5)
    fig.suptitle(
        make_conclusion_title("ROC-AUC", env_macro, ens_macro),
        fontsize=16, fontweight="bold", y=1.02
    )

    plt.tight_layout()
    path = OUTPUT_DIR / "fig3_roc_comparison.png"
    fig.savefig(path, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  [图3] ROC对比图已保存: {path}")


# ═══════════════════════════════════════════════════════════════
# 图4辅助：指标汇总Markdown表格
# ═══════════════════════════════════════════════════════════════

def generate_metrics_table(results: Dict[str, Dict]) -> str:
    """生成所有方法的分类指标汇总 Markdown 表格"""
    lines = [
        "# 实验A：轴承故障分类对比 — 指标汇总",
        "",
        f"> 数据集: HUSTbear (ER-16K轴承, 采样率 {SAMPLE_RATE} Hz)",
        f"> 每类样本: {MAX_PER_CLASS_HUSTBEAR}  |  健康度阈值: {HEALTH_THRESHOLD}",
        f"> 类别: {', '.join(BEARING_LABELS)}",
        "",
        "## 方法对比汇总表",
        "",
        "| 方法 | Accuracy | Balanced Acc | Macro-F1 | Kappa | MCC | FDR | FAR | Macro-AUC | 平均耗时(ms) |",
        "|------|----------|-------------|----------|-------|-----|-----|-----|-----------|-------------|",
    ]

    all_method_names = [dn for dn, _ in SINGLE_METHODS] + [ENSEMBLE_METHOD]

    for method_name in all_method_names:
        data = results.get(method_name, {})
        if not data:
            continue

        # 使用 evaluation 模块的分类指标计算
        metrics = evaluate_classification_performance(
            data["y_true"], data["y_pred"], data["scores"],
            BEARING_LABELS,
            output_subdir=str(OUTPUT_DIR),
            title_prefix=f"轴承_{method_name}",
        )

        display_name = method_name
        if method_name == ENSEMBLE_METHOD:
            display_name = "集成Ensemble"

        lines.append(
            f"| {display_name} "
            f"| {metrics['accuracy']:.2%} "
            f"| {metrics['balanced_accuracy']:.2%} "
            f"| {metrics['macro_f1']:.2%} "
            f"| {metrics['cohen_kappa']:.4f} "
            f"| {metrics['mcc']:.4f} "
            f"| {metrics['fdr']:.2%} "
            f"| {metrics['far']:.2%} "
            f"| {metrics['macro_auc_roc']:.4f} "
            f"| {np.mean(data['exec_times']):.1f} |"
        )

    # 添加各方法的详细分类指标
    lines.extend([
        "",
        "## 各方法详细分类指标",
        "",
    ])

    for method_name in all_method_names:
        data = results.get(method_name, {})
        if not data:
            continue
        display_name = method_name if method_name != ENSEMBLE_METHOD else "集成Ensemble"
        metrics = evaluate_classification_performance(
            data["y_true"], data["y_pred"], data["scores"],
            BEARING_LABELS,
            output_subdir=str(OUTPUT_DIR),
            title_prefix=f"轴承_{method_name}",
        )
        table_str = generate_classification_metrics_table(metrics, f"轴承-{display_name}")
        lines.append(table_str)
        lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

def _hex_to_rgb(hex_str: str) -> Tuple[float, float, float]:
    """Hex颜色 → RGB (0-1范围)"""
    hex_str = hex_str.lstrip("#")
    r = int(hex_str[0:2], 16) / 255.0
    g = int(hex_str[2:4], 16) / 255.0
    b = int(hex_str[4:6], 16) / 255.0
    return (r, g, b)


# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════

def run_experiment_a():
    """实验A入口（供 main.py 调度）"""
    return main()

def main():
    """实验A主流程"""
    print("\n" + "=" * 60)
    print("  实验A：轴承故障分类对比")
    print("  生成4张答辩图表 + 1份Markdown指标汇总")
    print("=" * 60)

    # 1. 运行所有方法，收集预测结果
    results = run_all_methods()
    if not results:
        print("[ERROR] 无结果数据，退出")
        return

    # 2. 绘制混淆矩阵对比图
    print("\n  ▶ 生成图1: 混淆矩阵对比图")
    plot_confusion_matrix_comparison(results)

    # 3. 绘制 Accuracy 柱状图
    print("  ▶ 生成图2: Accuracy柱状图")
    plot_accuracy_bar(results)

    # 4. 绘制 ROC 曲线对比图
    print("  ▶ 生成图3: ROC曲线对比图")
    plot_roc_comparison(results)

    # 5. 生成指标汇总 Markdown 表格
    print("  ▶ 生成图4: 指标汇总Markdown表格")
    table_str = generate_metrics_table(results)
    table_path = OUTPUT_DIR / "metrics_summary.md"
    with open(table_path, "w", encoding="utf-8") as f:
        f.write(table_str)
    print(f"  [表4] 指标汇总已保存: {table_path}")

    print("\n" + "=" * 60)
    print("  实验A完成！所有文件保存至:")
    print(f"  {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()