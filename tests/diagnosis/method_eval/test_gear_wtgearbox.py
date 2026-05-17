"""
测试 3：WTgearbox 齿轮评估

WTgearbox 行星齿轮箱数据集，恒速工况 20~55 Hz。
评估 2 种齿轮诊断方法 + Ensemble 对故障的检测能力。

- 单一方法：二分类（健康 vs 故障，基于 fault_indicators）
- Ensemble：五类分类（基于 D-S 融合）+ 二分类

运行方式：
    d:\code\CNN\cloud\venv\Scripts\python.exe tests\diagnosis\method_eval\test_gear_wtgearbox.py
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
# 导入配置
# ═══════════════════════════════════════════════════════════
from method_eval.config import (
    WTGEARBOX_DIR, SAMPLE_RATE, MAX_SAMPLES,
    GEAR_PARAMS,
    WTGEARBOX_LABELS, LABEL_CN,
    HEALTH_THRESHOLD, ENSEMBLE_PROFILE, ENSEMBLE_MAX_SECONDS,
    EXP_DIRS,
)
from method_eval.label_mapper import (
    infer_gear_label_from_ensemble,
    infer_binary_label,
)
from method_eval.visualizer import apply_style
from method_eval.plot_generator import save_confusion_matrix_results, save_accuracy_bar_results
from method_eval.visualizer import plot_confusion_matrix, plot_method_comparison_bar

apply_style()

# ═══════════════════════════════════════════════════════════
# 导入诊断引擎
# ═══════════════════════════════════════════════════════════
from app.services.diagnosis.engine import (
    DiagnosisEngine, GearMethod, DiagnosisStrategy, DenoiseMethod,
)
from app.services.diagnosis.ensemble import run_research_ensemble

# ═══════════════════════════════════════════════════════════
# 导入评价工具
# ═══════════════════════════════════════════════════════════
from evaluation.datasets import classify_wtgearbox
from evaluation.utils import load_npy, compute_confusion_matrix
from evaluation.classification_metrics_eval import (
    evaluate_classification_performance,
    generate_classification_metrics_table,
)

# ═══════════════════════════════════════════════════════════
# 输出目录
# ═══════════════════════════════════════════════════════════
OUTPUT_DIR = EXP_DIRS["gear_wtgearbox"]

# 从文件名提取转速频率
def _extract_rot_freq(filename: str) -> float:
    name = filename.replace(".npy", "")
    parts = name.split("-")
    main_parts = parts[0].split("_")
    try:
        return float(main_parts[-1])
    except ValueError:
        return 30.0


# ═══════════════════════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════════════════════

def get_wtgearbox_files() -> List[Tuple[Path, Dict]]:
    if not WTGEARBOX_DIR.exists():
        print(f"[ERROR] WTgearbox 目录不存在: {WTGEARBOX_DIR}")
        return []
    files = []
    for f in sorted(WTGEARBOX_DIR.glob("*.npy")):
        if not f.name.endswith("-c1.npy"):
            continue
        info = classify_wtgearbox(f.name)
        if info["label"] in WTGEARBOX_LABELS:
            files.append((f, info))
    return files


# ═══════════════════════════════════════════════════════════
# 单一方法 — 二分类
# ═══════════════════════════════════════════════════════════

def run_single_method_binary(
    method_name: str,
    gm_value: str,
    files: List[Tuple[Path, Dict]],
) -> Dict[str, Any]:
    """单一齿轮方法二分类评估

    预测规则：fault_indicators 中有 warning/critical → fault，否则 healthy
    """
    print(f"\n  ▶ {method_name} (二分类)")

    y_true = []
    y_pred = []
    exec_times = []

    gm_enum = GearMethod(gm_value)

    for filepath, info in files:
        try:
            signal = load_npy(filepath, MAX_SAMPLES)
            rot_freq = _extract_rot_freq(filepath.name)

            t0 = time.perf_counter()
            engine = DiagnosisEngine(
                strategy=DiagnosisStrategy.ADVANCED,
                gear_method=gm_enum,
                denoise_method=DenoiseMethod.NONE,
                gear_teeth=GEAR_PARAMS,
            )
            result = engine.analyze_gear(signal, SAMPLE_RATE, rot_freq=rot_freq)
            elapsed = (time.perf_counter() - t0) * 1000

            # 基于 fault_indicators 判断
            indicators = result.get("fault_indicators", {}) or {}
            has_fault = any(
                isinstance(v, dict) and (v.get("warning") or v.get("critical"))
                for v in indicators.values()
            )

            pred = "fault" if has_fault else "healthy"
            true = "fault" if info["label"] != "healthy" else "healthy"

            y_true.append(true)
            y_pred.append(pred)
            exec_times.append(elapsed)

        except Exception as e:
            print(f"    [ERR] {filepath.name}: {e}")
            true = "fault" if info["label"] != "healthy" else "healthy"
            y_true.append(true)
            y_pred.append("healthy")
            exec_times.append(0.0)

    acc = sum(1 for t, p in zip(y_true, y_pred) if t == p) / len(y_true)
    avg_time = np.mean(exec_times)
    print(f"    Acc={acc:.2%}  耗时={avg_time:.0f}ms")

    return {"y_true": y_true, "y_pred": y_pred, "exec_times": exec_times, "accuracy": acc}


# ═══════════════════════════════════════════════════════════
# Ensemble — 五类 + 二分类
# ═══════════════════════════════════════════════════════════

def run_ensemble_all(
    files: List[Tuple[Path, Dict]],
) -> Dict[str, Any]:
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
            rot_freq = _extract_rot_freq(filepath.name)

            t0 = time.perf_counter()
            result = run_research_ensemble(
                signal, SAMPLE_RATE,
                bearing_params=None,
                gear_teeth=GEAR_PARAMS,
                denoise_method="none",
                rot_freq=rot_freq,
                profile=ENSEMBLE_PROFILE,
                max_seconds=ENSEMBLE_MAX_SECONDS,
            )
            elapsed = (time.perf_counter() - t0) * 1000
            hs = int(result.get("health_score", 100))

            # 五类
            pred_5 = infer_gear_label_from_ensemble(result, WTGEARBOX_LABELS)
            y_true_5.append(info["label"])
            y_pred_5.append(pred_5)

            # 二分类
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

def test_gear_wtgearbox() -> Dict[str, Any]:
    print("\n" + "=" * 70)
    print("  测试 3：WTgearbox 齿轮评估")
    print(f"  数据集: {WTGEARBOX_DIR}")
    print(f"  输出:   {OUTPUT_DIR}")
    print("=" * 70)

    # ── 1. 加载数据 ──
    files = get_wtgearbox_files()
    if not files:
        print("[ABORT] 无可用数据"); return {}

    n_total = len(files)
    n_healthy = sum(1 for _, i in files if i["label"] == "healthy")
    n_fault = n_total - n_healthy
    print(f"\n  文件: {n_total} 个 (健康={n_healthy}, 故障={n_fault})")
    for lbl in WTGEARBOX_LABELS:
        n = sum(1 for _, i in files if i["label"] == lbl)
        print(f"    {LABEL_CN.get(lbl, lbl)}: {n} 个")

    # ── 2. 单一方法 — 二分类 ──
    binary_results = {}
    for gm_value in ["standard", "advanced"]:
        name_map = {"standard": "标准边频分析", "advanced": "高级综合"}
        r = run_single_method_binary(name_map[gm_value], gm_value, files)
        binary_results[name_map[gm_value]] = r

    # ── 3. Ensemble ──
    ensemble_result = run_ensemble_all(files)

    # ═══════════════════════════════════════════════════════
    # 4. 五类报告（Ensemble）
    # ═══════════════════════════════════════════════════════
    print("\n  ── 生成五类报告 (Ensemble) ──")
    metrics_5 = evaluate_classification_performance(
        y_true=ensemble_result["y_true_5"],
        y_pred=ensemble_result["y_pred_5"],
        scores=[100 - hs for hs in ensemble_result["health_scores"]],
        labels=WTGEARBOX_LABELS,
        output_subdir=str(OUTPUT_DIR),
        title_prefix="WTgearbox_Ensemble_5类",
    )
    cm_5 = np.array(metrics_5["confusion_matrix"])
    plot_confusion_matrix(cm_5, WTGEARBOX_LABELS, "Ensemble (齿轮5类)",
                          ensemble_result["accuracy_5"],
                          str(OUTPUT_DIR / "confusion_ensemble_5class.svg"), True)

    # 保存数据到 JSON（用于独立绘图）
    save_confusion_matrix_results(
        cm_5, WTGEARBOX_LABELS, "Ensemble (齿轮5类)",
        ensemble_result["accuracy_5"],
        OUTPUT_DIR / "results_ensemble_confusion.json", True,
    )
    table_5 = generate_classification_metrics_table(metrics_5, "WTgearbox Ensemble 五类")
    with open(OUTPUT_DIR / "ensemble_5class_metrics.md", "w", encoding="utf-8") as f:
        f.write(table_5)

    # ═══════════════════════════════════════════════════════
    # 5. 二分类对比
    # ═══════════════════════════════════════════════════════
    print("  ── 生成二分类对比报告 ──")

    method_names = list(binary_results.keys()) + ["Ensemble"]
    acc_list = [binary_results[m]["accuracy"] for m in binary_results] + [ensemble_result["accuracy_2"]]

    plot_method_comparison_bar(
        method_names=method_names, metrics={"accuracy": acc_list},
        metric_label="accuracy", title="WTgearbox 齿轮 健康 vs 故障二分类",
        output_path=str(OUTPUT_DIR / "binary_accuracy_comparison.svg"),
        highlight_indices=[len(method_names) - 1], ylim=(0.5, 1.05),
    )

    # 保存数据到 JSON（用于独立绘图）
    save_accuracy_bar_results(
        method_names, acc_list, "WTgearbox 齿轮 健康 vs 故障二分类",
        OUTPUT_DIR / "results_accuracy_bar.json",
        highlight_indices=[len(method_names) - 1], ylim=(0.5, 1.05),
    )

    # Markdown
    lines = [
        "# WTgearbox 齿轮评估", "",
        f"> 样本: {n_total} 个 (健康={n_healthy}, 故障={n_fault})", "",
        "| 方法 | 二分类 Accuracy | 平均耗时(ms) |",
        "|------|----------------|-------------|",
    ]
    for name in binary_results:
        avg_t = np.mean(binary_results[name]["exec_times"])
        lines.append(f"| {name} | {binary_results[name]['accuracy']:.2%} | {avg_t:.0f} |")
    avg_t_e = np.mean(ensemble_result["exec_times"])
    lines.append(f"| **Ensemble** | **{ensemble_result['accuracy_2']:.2%}** | **{avg_t_e:.0f}** |")
    lines.extend(["", "## Ensemble 五类分类", "", f"> 五类准确率: {ensemble_result['accuracy_5']:.2%}", "", table_5])

    with open(OUTPUT_DIR / "report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # ═══════════════════════════════════════════════════════
    # 6. 摘要
    # ═══════════════════════════════════════════════════════
    print(f"\n{'=' * 70}")
    print("  测试 3 完成！")
    print(f"{'=' * 70}")
    print("\n  二分类准确率:")
    for name in binary_results:
        print(f"    {name}: {binary_results[name]['accuracy']:.2%}")
    print(f"    Ensemble: {ensemble_result['accuracy_2']:.2%} ★")
    print(f"\n  Ensemble 五类准确率: {ensemble_result['accuracy_5']:.2%}")
    print(f"\n  图表目录: {OUTPUT_DIR}")

    return {"binary_results": binary_results, "ensemble_result": ensemble_result}


if __name__ == "__main__":
    test_gear_wtgearbox()
