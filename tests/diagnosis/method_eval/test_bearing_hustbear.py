"""
测试 1：HUSTbear 轴承评估

评估 11 种轴承诊断方法 + Ensemble 集成。
- 单一方法：二分类评估（健康 vs 故障）
- Ensemble：五类分类 + 二分类评估（基于 D-S 融合）

运行方式：
    cd /d/code/CNN/cloud
    venv\Scripts\python.exe -m tests.diagnosis.method_eval.test_bearing_hustbear
"""
import sys
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

warnings.filterwarnings("ignore")

# ═══════════════════════════════════════════════════════════
# 路径设置
# ═══════════════════════════════════════════════════════════
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CLOUD_PATH = PROJECT_ROOT / "cloud"
sys.path.insert(0, str(CLOUD_PATH))
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "diagnosis"))

# ═══════════════════════════════════════════════════════════
# 导入配置和工具
# ═══════════════════════════════════════════════════════════
from method_eval.config import (
    HUSTBEAR_DIR, SAMPLE_RATE, MAX_SAMPLES,
    BEARING_PARAMS,
    HUSTBEAR_LABELS, LABEL_CN,
    BEARING_METHODS,
    HEALTH_THRESHOLD, ENSEMBLE_PROFILE, ENSEMBLE_MAX_SECONDS,
    EXP_DIRS,
)
from method_eval.label_mapper import (
    infer_bearing_label_from_ensemble,
    infer_binary_label,
)
from method_eval.visualizer import (
    apply_style, plot_confusion_matrix, plot_method_comparison_bar,
    plot_recall_heatmap, plot_radar_chart,
)

apply_style()

# ═══════════════════════════════════════════════════════════
# 导入诊断引擎
# ═══════════════════════════════════════════════════════════
from app.services.diagnosis.engine import (
    DiagnosisEngine, BearingMethod, DiagnosisStrategy, DenoiseMethod,
)
from app.services.diagnosis.ensemble import run_research_ensemble
from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum

# ═══════════════════════════════════════════════════════════
# 导入评价工具
# ═══════════════════════════════════════════════════════════
from evaluation.datasets import classify_hustbear
from evaluation.utils import load_npy
from evaluation.classification_metrics_eval import (
    evaluate_classification_performance,
    generate_classification_metrics_table,
)

# ═══════════════════════════════════════════════════════════
# 输出目录
# ═══════════════════════════════════════════════════════════
OUTPUT_DIR = EXP_DIRS["bearing_hustbear"]

# 过滤掉有 bug 的方法
SKIP_METHODS = {"wp"}  # 小波包有 bug

# 快速验证模式：只跑 3 个代表性方法 + Ensemble
# 全量模式：跑全部方法（取消注释下面一行）
# BEARING_METHODS_ACTIVE = [(n, v) for n, v in BEARING_METHODS if v not in SKIP_METHODS]
BEARING_METHODS_ACTIVE = [
    ("标准包络", "envelope"),
    ("Kurtogram", "kurtogram"),
    ("CPW预白化", "cpw"),
]


# ═══════════════════════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════════════════════

def get_hustbear_files() -> List[Tuple[Path, Dict]]:
    """获取 HUSTbear 数据集所有 X 通道文件"""
    if not HUSTBEAR_DIR.exists():
        print(f"[ERROR] HUSTbear 目录不存在: {HUSTBEAR_DIR}")
        return []

    files = []
    for f in sorted(HUSTBEAR_DIR.glob("*.npy")):
        if not f.name.endswith("-X.npy"):
            continue
        info = classify_hustbear(f.name)
        if info["label"] in HUSTBEAR_LABELS:
            files.append((f, info))

    return files


# ═══════════════════════════════════════════════════════════
# 单一方法 — 二分类
# ═══════════════════════════════════════════════════════════

def run_single_method_binary(
    method_name: str,
    bm_value: str,
    files: List[Tuple[Path, Dict]],
) -> Dict[str, Any]:
    """运行单一轴承诊断方法，做二分类评估

    预测规则：health_score >= HEALTH_THRESHOLD → healthy，否则 fault
    """
    print(f"\n  ▶ {method_name} (二分类)")

    y_true = []
    y_pred = []
    health_scores = []
    exec_times = []

    bm_enum = BearingMethod(bm_value)

    for filepath, info in files:
        try:
            signal = load_npy(filepath, MAX_SAMPLES)
            rot_freq = estimate_rot_freq_spectrum(signal, SAMPLE_RATE)

            t0 = time.perf_counter()
            engine = DiagnosisEngine(
                strategy=DiagnosisStrategy.ADVANCED,
                bearing_method=bm_enum,
                denoise_method=DenoiseMethod.NONE,
                bearing_params=BEARING_PARAMS,
            )
            comp = engine.analyze_comprehensive(signal, SAMPLE_RATE, rot_freq=rot_freq)
            elapsed = (time.perf_counter() - t0) * 1000

            hs = int(comp.get("health_score", 100))
            true_binary = "fault" if info["label"] != "healthy" else "healthy"
            pred_binary = infer_binary_label(hs)

            y_true.append(true_binary)
            y_pred.append(pred_binary)
            health_scores.append(hs)
            exec_times.append(elapsed)

        except Exception as e:
            print(f"    [ERR] {filepath.name}: {e}")
            true_binary = "fault" if info["label"] != "healthy" else "healthy"
            y_true.append(true_binary)
            y_pred.append("healthy")
            health_scores.append(100)
            exec_times.append(0.0)

    acc = sum(1 for t, p in zip(y_true, y_pred) if t == p) / len(y_true)
    avg_time = np.mean(exec_times)
    print(f"    Acc={acc:.2%}  耗时={avg_time:.0f}ms")

    return {"y_true": y_true, "y_pred": y_pred, "health_scores": health_scores,
            "exec_times": exec_times, "accuracy": acc}


# ═══════════════════════════════════════════════════════════
# Ensemble — 五类分类 + 二分类
# ═══════════════════════════════════════════════════════════

def run_ensemble_all(
    files: List[Tuple[Path, Dict]],
) -> Dict[str, Any]:
    """运行 Ensemble 集成诊断"""
    print(f"\n  ▶ Ensemble 集成 (D-S 融合)")

    y_true_5 = []
    y_pred_5 = []
    y_true_2 = []
    y_pred_2 = []
    health_scores = []
    exec_times = []

    for filepath, info in files:
        try:
            signal = load_npy(filepath, MAX_SAMPLES)
            rot_freq = estimate_rot_freq_spectrum(signal, SAMPLE_RATE)

            t0 = time.perf_counter()
            result = run_research_ensemble(
                signal, SAMPLE_RATE,
                bearing_params=BEARING_PARAMS,
                gear_teeth=None,
                denoise_method="none",
                rot_freq=rot_freq,
                profile=ENSEMBLE_PROFILE,
                max_seconds=ENSEMBLE_MAX_SECONDS,
            )
            elapsed = (time.perf_counter() - t0) * 1000
            hs = int(result.get("health_score", 100))

            # 五类预测（D-S 融合）
            pred_5 = infer_bearing_label_from_ensemble(result, HUSTBEAR_LABELS)
            y_true_5.append(info["label"])
            y_pred_5.append(pred_5)

            # 二分类预测
            true_2 = "fault" if info["label"] != "healthy" else "healthy"
            pred_2 = infer_binary_label(hs)
            y_true_2.append(true_2)
            y_pred_2.append(pred_2)

            health_scores.append(hs)
            exec_times.append(elapsed)

        except Exception as e:
            print(f"    [ERR] {filepath.name}: {e}")
            y_true_5.append(info["label"])
            y_pred_5.append("healthy")
            true_2 = "fault" if info["label"] != "healthy" else "healthy"
            y_true_2.append(true_2)
            y_pred_2.append("healthy")
            health_scores.append(100)
            exec_times.append(0.0)

    acc_5 = sum(1 for t, p in zip(y_true_5, y_pred_5) if t == p) / len(y_true_5)
    acc_2 = sum(1 for t, p in zip(y_true_2, y_pred_2) if t == p) / len(y_true_2)
    avg_time = np.mean(exec_times)
    print(f"    五类Acc={acc_5:.2%}  二分类Acc={acc_2:.2%}  耗时={avg_time:.0f}ms")

    return {
        "y_true_5": y_true_5, "y_pred_5": y_pred_5,
        "y_true_2": y_true_2, "y_pred_2": y_pred_2,
        "health_scores": health_scores, "exec_times": exec_times,
        "accuracy_5": acc_5, "accuracy_2": acc_2,
    }


# ═══════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════

def test_bearing_hustbear() -> Dict[str, Any]:
    """测试 1 入口"""
    print("\n" + "=" * 70)
    print("  测试 1：HUSTbear 轴承评估")
    print(f"  数据集: {HUSTBEAR_DIR}")
    print(f"  输出:   {OUTPUT_DIR}")
    print("=" * 70)

    # ── 1. 加载数据 ──
    files = get_hustbear_files()
    if not files:
        print("[ABORT] 无可用数据"); return {}

    n_total = len(files)
    n_healthy = sum(1 for _, i in files if i["label"] == "healthy")
    n_fault = n_total - n_healthy
    print(f"\n  文件: {n_total} 个 (健康={n_healthy}, 故障={n_fault})")

    # ── 2. 单一方法 — 二分类 ──
    binary_results = {}
    for display_name, bm_value in BEARING_METHODS_ACTIVE:
        r = run_single_method_binary(display_name, bm_value, files)
        binary_results[display_name] = r

    # ── 3. Ensemble — 五类 + 二分类 ──
    ensemble_result = run_ensemble_all(files)

    # ═══════════════════════════════════════════════════════
    # 4. 生成报告 — 五类分类（Ensemble）
    # ═══════════════════════════════════════════════════════
    print("\n  ── 生成五类分类报告 (Ensemble) ──")
    metrics_5 = evaluate_classification_performance(
        y_true=ensemble_result["y_true_5"],
        y_pred=ensemble_result["y_pred_5"],
        scores=[100 - hs for hs in ensemble_result["health_scores"]],
        labels=HUSTBEAR_LABELS,
        output_subdir=str(OUTPUT_DIR),
        title_prefix="HUSTbear_Ensemble_5类",
    )

    # Ensemble 五类混淆矩阵
    from evaluation.utils import compute_confusion_matrix
    cm_5 = np.array(metrics_5["confusion_matrix"])
    plot_confusion_matrix(cm_5, HUSTBEAR_LABELS, "Ensemble (5类)",
                          ensemble_result["accuracy_5"],
                          str(OUTPUT_DIR / "confusion_ensemble_5class.svg"),
                          highlight=True)

    # 五类 Markdown 表
    table_5 = generate_classification_metrics_table(metrics_5, "HUSTbear Ensemble 五类分类")
    with open(OUTPUT_DIR / "ensemble_5class_metrics.md", "w", encoding="utf-8") as f:
        f.write(table_5)

    # ═══════════════════════════════════════════════════════
    # 5. 生成报告 — 二分类对比（所有方法）
    # ═══════════════════════════════════════════════════════
    print("  ── 生成二分类对比报告 ──")
    binary_labels = ["healthy", "fault"]

    # 收集所有二分类准确率
    method_names = list(binary_results.keys()) + ["Ensemble"]
    acc_list = [binary_results[m]["accuracy"] for m in binary_results] + [ensemble_result["accuracy_2"]]

    # 柱状图
    plot_method_comparison_bar(
        method_names=method_names,
        metrics={"accuracy": acc_list},
        metric_label="accuracy",
        title="HUSTbear 健康 vs 故障二分类 — 各方法准确率",
        output_path=str(OUTPUT_DIR / "binary_accuracy_comparison.svg"),
        highlight_indices=[len(method_names) - 1],
        ylim=(0.5, 1.05),
    )

    # 二分类 Markdown 表
    lines = [
        "# HUSTbear 轴承二分类评估（健康 vs 故障）",
        "",
        f"> 样本: {n_total} 个 (健康={n_healthy}, 故障={n_fault})",
        "",
        "| 方法 | Accuracy | 平均耗时(ms) |",
        "|------|----------|-------------|",
    ]
    for name in binary_results:
        avg_t = np.mean(binary_results[name]["exec_times"])
        lines.append(f"| {name} | {binary_results[name]['accuracy']:.2%} | {avg_t:.0f} |")
    avg_t_e = np.mean(ensemble_result["exec_times"])
    lines.append(f"| **Ensemble** | **{ensemble_result['accuracy_2']:.2%}** | **{avg_t_e:.0f}** |")

    lines.extend([
        "",
        "## Ensemble 五类分类指标",
        "",
        f"> 五类准确率: {ensemble_result['accuracy_5']:.2%}",
        "",
        table_5,
    ])

    with open(OUTPUT_DIR / "report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # ═══════════════════════════════════════════════════════
    # 6. 打印摘要
    # ═══════════════════════════════════════════════════════
    print(f"\n{'=' * 70}")
    print("  测试 1 完成！")
    print(f"{'=' * 70}")
    print("\n  二分类准确率:")
    for name in binary_results:
        print(f"    {name}: {binary_results[name]['accuracy']:.2%}")
    print(f"    Ensemble: {ensemble_result['accuracy_2']:.2%} ★")
    print(f"\n  Ensemble 五类准确率: {ensemble_result['accuracy_5']:.2%}")
    print(f"\n  图表目录: {OUTPUT_DIR}")

    return {
        "binary_results": binary_results,
        "ensemble_result": ensemble_result,
    }


if __name__ == "__main__":
    test_bearing_hustbear()
