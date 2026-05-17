"""
测试 2：CW 变速轴承 3 类评估

CW 数据集全部为变速工况（升速/降速/升降/降升），转速范围 9.8~29.0 Hz。
评估 11 种轴承诊断方法 + Ensemble 在变速工况下的表现。

- 单一方法：二分类（健康 vs 故障）
- Ensemble：三分类 + 二分类（基于 D-S 融合）

运行方式：
    d:\code\CNN\cloud\venv\Scripts\python.exe tests\diagnosis\method_eval\test_bearing_cw.py
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
    CW_DIR, SAMPLE_RATE, MAX_SAMPLES,
    BEARING_PARAMS,
    CW_LABELS, LABEL_CN,
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
from evaluation.datasets import classify_cw
from evaluation.utils import load_npy, compute_confusion_matrix
from evaluation.classification_metrics_eval import (
    evaluate_classification_performance,
    generate_classification_metrics_table,
)

# ═══════════════════════════════════════════════════════════
# 输出目录
# ═══════════════════════════════════════════════════════════
OUTPUT_DIR = EXP_DIRS["bearing_cw"]

SKIP_METHODS = {"wp"}
# 全量模式
BEARING_METHODS_ACTIVE = [(n, v) for n, v in BEARING_METHODS if v not in SKIP_METHODS]
# 快速验证模式：取消注释下面一行
# BEARING_METHODS_ACTIVE = [("标准包络", "envelope"), ("DWT", "dwt"), ("EMD", "emd_envelope")]


# ═══════════════════════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════════════════════

def get_cw_files() -> List[Tuple[Path, Dict]]:
    """获取 CW 数据集所有文件"""
    if not CW_DIR.exists():
        print(f"[ERROR] CW 目录不存在: {CW_DIR}")
        return []
    files = []
    for f in sorted(CW_DIR.glob("*.npy")):
        info = classify_cw(f.name)
        if info["label"] in CW_LABELS:
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
    """单一方法二分类评估（变速工况）"""
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
            result = engine.analyze_bearing(signal, SAMPLE_RATE, rot_freq=rot_freq)
            elapsed = (time.perf_counter() - t0) * 1000

            indicators = result.get("fault_indicators", {}) or {}
            has_fault = any(
                isinstance(v, dict) and v.get("significant") and not k.endswith("_stat")
                for k, v in indicators.items()
            )

            pred = "fault" if has_fault else "healthy"
            true = "fault" if info["label"] != "healthy" else "healthy"

            y_true.append(true)
            y_pred.append(pred)
            health_scores.append(100 if not has_fault else 50)
            exec_times.append(elapsed)

        except Exception as e:
            print(f"    [ERR] {filepath.name}: {e}")
            true = "fault" if info["label"] != "healthy" else "healthy"
            y_true.append(true)
            y_pred.append("healthy")
            health_scores.append(100)
            exec_times.append(0.0)

    acc = sum(1 for t, p in zip(y_true, y_pred) if t == p) / len(y_true)
    avg_time = np.mean(exec_times)
    print(f"    Acc={acc:.2%}  耗时={avg_time:.0f}ms")

    return {"y_true": y_true, "y_pred": y_pred, "health_scores": health_scores,
            "exec_times": exec_times, "accuracy": acc}


# ═══════════════════════════════════════════════════════════
# Ensemble — 三分类 + 二分类
# ═══════════════════════════════════════════════════════════

def run_ensemble_all(
    files: List[Tuple[Path, Dict]],
) -> Dict[str, Any]:
    """Ensemble 集成诊断（变速工况）"""
    print(f"\n  ▶ Ensemble 集成 (D-S 融合)")

    y_true_3 = []
    y_pred_3 = []
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

            # 三分类预测
            pred_3 = infer_bearing_label_from_ensemble(result, CW_LABELS)
            y_true_3.append(info["label"])
            y_pred_3.append(pred_3)

            # 二分类预测
            true_2 = "fault" if info["label"] != "healthy" else "healthy"
            pred_2 = infer_binary_label(hs)
            y_true_2.append(true_2)
            y_pred_2.append(pred_2)

            health_scores.append(hs)
            exec_times.append(elapsed)

        except Exception as e:
            print(f"    [ERR] {filepath.name}: {e}")
            y_true_3.append(info["label"])
            y_pred_3.append("healthy")
            true_2 = "fault" if info["label"] != "healthy" else "healthy"
            y_true_2.append(true_2)
            y_pred_2.append("healthy")
            health_scores.append(100)
            exec_times.append(0.0)

    acc_3 = sum(1 for t, p in zip(y_true_3, y_pred_3) if t == p) / len(y_true_3)
    acc_2 = sum(1 for t, p in zip(y_true_2, y_pred_2) if t == p) / len(y_true_2)
    avg_time = np.mean(exec_times)
    print(f"    三类Acc={acc_3:.2%}  二分类Acc={acc_2:.2%}  耗时={avg_time:.0f}ms")

    return {
        "y_true_3": y_true_3, "y_pred_3": y_pred_3,
        "y_true_2": y_true_2, "y_pred_2": y_pred_2,
        "health_scores": health_scores, "exec_times": exec_times,
        "accuracy_3": acc_3, "accuracy_2": acc_2,
    }


# ═══════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════

def test_bearing_cw() -> Dict[str, Any]:
    """测试 2 入口"""
    print("\n" + "=" * 70)
    print("  测试 2：CW 变速轴承 3 类评估")
    print(f"  数据集: {CW_DIR}")
    print(f"  输出:   {OUTPUT_DIR}")
    print(f"  方法:   {len(BEARING_METHODS_ACTIVE)} 种轴承 + Ensemble")
    print("=" * 70)

    # ── 1. 加载数据 ──
    files = get_cw_files()
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

    # ── 3. Ensemble — 三分类 + 二分类 ──
    ensemble_result = run_ensemble_all(files)

    # ═══════════════════════════════════════════════════════
    # 4. 生成报告 — 三分类（Ensemble）
    # ═══════════════════════════════════════════════════════
    print("\n  ── 生成三分类报告 (Ensemble) ──")
    metrics_3 = evaluate_classification_performance(
        y_true=ensemble_result["y_true_3"],
        y_pred=ensemble_result["y_pred_3"],
        scores=[100 - hs for hs in ensemble_result["health_scores"]],
        labels=CW_LABELS,
        output_subdir=str(OUTPUT_DIR),
        title_prefix="CW_Ensemble_3类",
    )

    cm_3 = np.array(metrics_3["confusion_matrix"])
    plot_confusion_matrix(cm_3, CW_LABELS, "Ensemble (3类变速)",
                          ensemble_result["accuracy_3"],
                          str(OUTPUT_DIR / "confusion_ensemble_3class.svg"),
                          highlight=True)

    table_3 = generate_classification_metrics_table(metrics_3, "CW Ensemble 三分类")
    with open(OUTPUT_DIR / "ensemble_3class_metrics.md", "w", encoding="utf-8") as f:
        f.write(table_3)

    # ═══════════════════════════════════════════════════════
    # 5. 生成报告 — 二分类对比
    # ═══════════════════════════════════════════════════════
    print("  ── 生成二分类对比报告 ──")

    method_names = list(binary_results.keys()) + ["Ensemble"]
    acc_list = [binary_results[m]["accuracy"] for m in binary_results] + [ensemble_result["accuracy_2"]]

    plot_method_comparison_bar(
        method_names=method_names,
        metrics={"accuracy": acc_list},
        metric_label="accuracy",
        title="CW 变速轴承 健康 vs 故障二分类",
        output_path=str(OUTPUT_DIR / "binary_accuracy_comparison.svg"),
        highlight_indices=[len(method_names) - 1],
        ylim=(0.5, 1.05),
    )

    # Markdown 报告
    lines = [
        "# CW 变速轴承评估（健康 vs 故障）",
        "",
        f"> 样本: {n_total} 个 (健康={n_healthy}, 故障={n_fault})",
        f"> 工况: 全部变速 (9.8~29.0 Hz)",
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
        "## Ensemble 三分类指标",
        "",
        f"> 三分类准确率: {ensemble_result['accuracy_3']:.2%}",
        "",
        table_3,
    ])

    with open(OUTPUT_DIR / "report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # ═══════════════════════════════════════════════════════
    # 6. 打印摘要
    # ═══════════════════════════════════════════════════════
    print(f"\n{'=' * 70}")
    print("  测试 2 完成！")
    print(f"{'=' * 70}")
    print("\n  二分类准确率:")
    for name in binary_results:
        print(f"    {name}: {binary_results[name]['accuracy']:.2%}")
    print(f"    Ensemble: {ensemble_result['accuracy_2']:.2%} ★")
    print(f"\n  Ensemble 三分类准确率: {ensemble_result['accuracy_3']:.2%}")
    print(f"\n  图表目录: {OUTPUT_DIR}")

    return {
        "binary_results": binary_results,
        "ensemble_result": ensemble_result,
    }


if __name__ == "__main__":
    test_bearing_cw()
