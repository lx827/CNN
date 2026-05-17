"""
D-S 证据融合评价模块

比较单方法诊断与 D-S 融合诊断的分类性能差异：
- Accuracy: fusion vs best single method
- FAR: fusion vs minimum single method
- FIA: fusion vs best single method

输出:
  ds_fusion/comparison_table.md
  ds_fusion/far_reduction.png
"""
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))

from app.services.diagnosis import (
    DiagnosisEngine, BearingMethod, DiagnosisStrategy, DenoiseMethod,
)
from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum

from .config import (
    OUTPUT_DIR, SAMPLE_RATE, HUSTBEAR_BEARING, BEARING_FREQ_COEFFS,
)
from .datasets import get_hustbear_files, classify_hustbear
from .utils import load_npy, save_cache, save_figure

from .classification_metrics_eval import evaluate_classification_performance

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "KaiTi", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False

# ────────────────────────────────────────────────────────────
# 确保输出目录存在
# ────────────────────────────────────────────────────────────
DS_FUSION_DIR = OUTPUT_DIR / "ds_fusion"
DS_FUSION_DIR.mkdir(parents=True, exist_ok=True)

# ────────────────────────────────────────────────────────────
# 标签映射
# ────────────────────────────────────────────────────────────

# HUSTbear 数据集的 ground truth 类别
GROUND_TRUTH_LABELS = ["healthy", "inner", "outer", "ball", "composite"]

# 轴承诊断 fault_indicators 命名 → 分类标签
INDICATOR_TO_LABEL = {
    "bpfo": "outer",
    "bpfo_stat": "outer",
    "bpfi": "inner",
    "bpfi_stat": "inner",
    "bsf": "ball",
    "bsf_stat": "ball",
    "ftf": "ball",
    "ftf_stat": "ball",
    "envelope_peak_snr": "outer",    # 统计指标偏外圈
    "envelope_kurtosis": "outer",
    "moderate_kurtosis": "outer",
    "high_freq_ratio": "inner",
    "peak_concentration": "outer",
}

# ensemble fault_label → 分类标签
FAULT_LABEL_MAP = {
    "bearing_bpfo": "outer",
    "bearing_bpfi": "inner",
    "bearing_bsf": "ball",
    "bearing_abnormal": "unknown",
    "gear_abnormal": "unknown",
    "unknown": "unknown",
}

# D-S dominant_fault 中文 → 分类标签
DS_DOMINANT_MAP = {
    "轴承外圈故障": "outer",
    "轴承内圈故障": "inner",
    "轴承滚动体故障": "ball",
    "齿轮磨损": "unknown",
    "齿轮裂纹": "unknown",
    "齿轮断齿": "unknown",
    "正常": "healthy",
}

# 单方法诊断使用的轴承方法列表
SINGLE_BEARING_METHODS = [
    BearingMethod.ENVELOPE,
    BearingMethod.KURTOGRAM,
    BearingMethod.CPW,
    BearingMethod.MED,
    BearingMethod.TEAGER,
    BearingMethod.SPECTRAL_KURTOSIS,
    BearingMethod.MCKD,
]


# ────────────────────────────────────────────────────────────
# 标签推断
# ────────────────────────────────────────────────────────────

def _predict_label_from_bearing_result(result: Dict, health_score: int) -> str:
    """从单方法轴承诊断结果推断分类标签。

    规则:
    1. health_score >= 85 → healthy
    2. fault_indicators 中有参数匹配命中(bpfo/bpfi/bsf) → 对应标签
    3. 仅统计指标命中 → 优先外圈(误报偏外圈)
    4. health_score < 85 但无命中 → unknown
    """
    if health_score >= 85:
        return "healthy"

    indicators = result.get("fault_indicators", {}) or {}

    # 参数匹配指标优先
    param_hits = []
    stat_hits = []
    for name, item in indicators.items():
        if not isinstance(item, dict):
            continue
        if item.get("significant"):
            if name.endswith("_stat") or name in {
                "envelope_peak_snr", "envelope_kurtosis",
                "moderate_kurtosis", "envelope_crest_factor",
                "high_freq_ratio", "peak_concentration",
            }:
                stat_hits.append(name)
            else:
                param_hits.append(name)

    # 参数命中 → 直接映射
    if param_hits:
        for name in param_hits:
            mapped = INDICATOR_TO_LABEL.get(name)
            if mapped and mapped != "healthy":
                return mapped

    # 统计命中 → 取首个映射
    if stat_hits:
        for name in stat_hits:
            mapped = INDICATOR_TO_LABEL.get(name)
            if mapped and mapped != "healthy":
                return mapped

    return "unknown"


def _predict_label_from_ensemble(result: Dict) -> str:
    """从 ensemble (D-S 融合) 结果推断分类标签。

    优先使用 D-S 融合主导故障标签，其次使用 fault_label。
    """
    # 1. D-S dominant_fault
    ds_result = result.get("ensemble", {}).get("ds_fusion", {})
    if isinstance(ds_result, dict) and "dominant_fault" in ds_result:
        dominant = ds_result.get("dominant_fault", "")
        dominant_prob = float(ds_result.get("dominant_probability", 0))
        uncertainty = float(ds_result.get("uncertainty", 1))
        if dominant_prob > 0.05 and uncertainty < 0.5:
            mapped = DS_DOMINANT_MAP.get(dominant)
            if mapped and mapped != "unknown":
                return mapped

    # 2. fault_label
    fault_label = result.get("fault_label", "")
    mapped = FAULT_LABEL_MAP.get(fault_label)
    if mapped and mapped != "unknown":
        return mapped

    # 3. health_score 判断
    hs = result.get("health_score", 100)
    if hs >= 85:
        return "healthy"

    # 4. 无明确判断 → unknown
    return "unknown"


# ────────────────────────────────────────────────────────────
# 评价流程
# ────────────────────────────────────────────────────────────

def evaluate_ds_fusion():
    """D-S 证据融合评价主入口"""
    print("\n" + "=" * 60)
    print("【模块】D-S 证据融合评价")
    print("=" * 60)

    hust_files = get_hustbear_files()
    if not hust_files:
        print("[SKIP] HUSTbear 数据集不可用，无法进行 D-S 融合评价")
        return []

    print(f"  加载 HUSTbear 数据集: {len(hust_files)} 文件")

    # ── 收集单方法诊断结果 ──
    single_method_data: Dict[str, Dict[str, List]] = {}
    # {method_name: {"y_true": [...], "y_pred": [...], "scores": [...]}}

    for filepath, info in hust_files:
        signal = load_npy(filepath)
        rot_freq = estimate_rot_freq_spectrum(signal, SAMPLE_RATE)
        true_label = info["label"]

        for bm in SINGLE_BEARING_METHODS:
            method_name = bm.value
            if method_name not in single_method_data:
                single_method_data[method_name] = {
                    "y_true": [], "y_pred": [], "scores": [],
                }

            try:
                t0 = time.perf_counter()
                engine = DiagnosisEngine(
                    strategy=DiagnosisStrategy.EXPERT,
                    bearing_method=bm,
                    denoise_method=DenoiseMethod.NONE,
                    bearing_params=HUSTBEAR_BEARING,
                )
                result = engine.analyze_bearing(signal, SAMPLE_RATE, rot_freq=rot_freq)
                # 获取综合健康度
                comp = engine.analyze_comprehensive(signal, SAMPLE_RATE, rot_freq=rot_freq)
                hs = comp.get("health_score", 100)
                exec_time = (time.perf_counter() - t0) * 1000

                pred_label = _predict_label_from_bearing_result(result, hs)
                # 连续分数: 反转健康度 (100 - hs)，越高越可能故障
                score = 100.0 - hs

                single_method_data[method_name]["y_true"].append(true_label)
                single_method_data[method_name]["y_pred"].append(pred_label)
                single_method_data[method_name]["scores"].append(score)

                print(f"    {filepath.name} | {method_name} | true={true_label} "
                      f"pred={pred_label} hs={hs} ({exec_time:.0f}ms)")
            except Exception as e:
                print(f"    [ERR] {method_name} on {filepath.name}: {e}")
                single_method_data[method_name]["y_true"].append(true_label)
                single_method_data[method_name]["y_pred"].append("unknown")
                single_method_data[method_name]["scores"].append(0.0)

    # ── 收集 ensemble (D-S 融合) 诊断结果 ──
    fusion_data = {"y_true": [], "y_pred": [], "scores": []}

    print(f"\n  运行 D-S 融合诊断 (run_research_ensemble)...")
    for filepath, info in hust_files:
        signal = load_npy(filepath)
        rot_freq = estimate_rot_freq_spectrum(signal, SAMPLE_RATE)
        true_label = info["label"]

        try:
            t0 = time.perf_counter()
            from app.services.diagnosis.ensemble import run_research_ensemble
            result = run_research_ensemble(
                signal, SAMPLE_RATE,
                bearing_params=HUSTBEAR_BEARING,
                denoise_method="none",
                rot_freq=rot_freq,
                profile="balanced",
            )
            exec_time = (time.perf_counter() - t0) * 1000

            pred_label = _predict_label_from_ensemble(result)
            hs = result.get("health_score", 100)
            score = 100.0 - hs

            # D-S 融合的连续分数: 使用 dominant_probability 作为故障强度
            ds_result = result.get("ensemble", {}).get("ds_fusion", {})
            if isinstance(ds_result, dict) and "dominant_probability" in ds_result:
                # dominant_probability 范围 0~1，映射到 0~100
                ds_score = float(ds_result.get("dominant_probability", 0)) * 100
                # 如果是 healthy，分数反转
                if pred_label == "healthy":
                    ds_score = 100 - ds_score
                score = ds_score

            fusion_data["y_true"].append(true_label)
            fusion_data["y_pred"].append(pred_label)
            fusion_data["scores"].append(score)

            print(f"    {filepath.name} | DS-Fusion | true={true_label} "
                  f"pred={pred_label} hs={hs} "
                  f"dominant={ds_result.get('dominant_fault', 'N/A')} "
                  f"prob={ds_result.get('dominant_probability', 0):.3f} "
                  f"({exec_time:.0f}ms)")
        except Exception as e:
            print(f"    [ERR] DS-Fusion on {filepath.name}: {e}")
            fusion_data["y_true"].append(true_label)
            fusion_data["y_pred"].append("unknown")
            fusion_data["scores"].append(0.0)

    # ── 计算各方法的分类指标 ──
    print(f"\n  计算分类指标...")

    # 有效标签集合 (过滤掉 unknown 预测，替换为最接近的)
    valid_labels = list(GROUND_TRUTH_LABELS)

    # 各单方法分类指标
    single_metrics: Dict[str, Dict[str, Any]] = {}
    for method_name, data in single_method_data.items():
        y_true = data["y_true"]
        y_pred = data["y_pred"]
        scores = data["scores"]

        # 过滤: unknown 映射为 true_label（保守假设: 无法分类视为错误）
        # 但为了公平比较，unknown 不计入 FIA
        n_samples = len(y_true)
        if n_samples < 3:
            continue

        metrics = evaluate_classification_performance(
            y_true=y_true,
            y_pred=y_pred,
            scores=scores,
            labels=valid_labels,
            output_subdir=str(DS_FUSION_DIR),
            title_prefix=f"单方法_{method_name}",
        )
        single_metrics[method_name] = metrics
        print(f"    {method_name}: Acc={metrics['accuracy']:.4f} "
              f"FAR={metrics['far']:.4f} FIA={metrics['fia']:.4f}")

    # D-S 融合分类指标
    fusion_metrics = evaluate_classification_performance(
        y_true=fusion_data["y_true"],
        y_pred=fusion_data["y_pred"],
        scores=fusion_data["scores"],
        labels=valid_labels,
        output_subdir=str(DS_FUSION_DIR),
        title_prefix="DS融合",
    )
    print(f"    DS-Fusion: Acc={fusion_metrics['accuracy']:.4f} "
          f"FAR={fusion_metrics['far']:.4f} FIA={fusion_metrics['fia']:.4f}")

    # ── 计算融合增益 ──
    fusion_gain = _compute_fusion_gain(single_metrics, fusion_metrics)

    # ── 生成图表与报告 ──
    _plot_far_reduction(single_metrics, fusion_metrics)
    report = _generate_comparison_table(single_metrics, fusion_metrics, fusion_gain)

    report_path = DS_FUSION_DIR / "comparison_table.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n  报告已保存: {report_path}")
    print(f"  图表已保存: {DS_FUSION_DIR / 'far_reduction.png'}")

    # 保存完整结果缓存
    all_results = {
        "single_metrics": single_metrics,
        "fusion_metrics": fusion_metrics,
        "fusion_gain": fusion_gain,
    }
    save_cache("ds_fusion_eval", all_results)

    return all_results


# ────────────────────────────────────────────────────────────
# 融合增益计算
# ────────────────────────────────────────────────────────────

def _compute_fusion_gain(
    single_metrics: Dict[str, Dict[str, Any]],
    fusion_metrics: Dict[str, Any],
) -> Dict[str, Any]:
    """计算 D-S 融合相对于单方法的增益。

    - ΔAccuracy = Acc_fusion - max(Acc_single)
    - ΔFAR = FAR_fusion - min(FAR_single)  (负值=改进)
    - ΔFIA = FIA_fusion - max(FIA_single)
    """
    if not single_metrics:
        return {
            "delta_accuracy": 0.0,
            "delta_far": 0.0,
            "delta_fia": 0.0,
            "best_single_acc_method": "N/A",
            "min_single_far_method": "N/A",
            "best_single_fia_method": "N/A",
        }

    # 各单方法极值
    single_accs = {m: v["accuracy"] for m, v in single_metrics.items()}
    single_fars = {m: v["far"] for m, v in single_metrics.items()}
    single_fias = {m: v["fia"] for m, v in single_metrics.items()}

    best_acc_method = max(single_accs, key=single_accs.get)
    min_far_method = min(single_fars, key=single_fars.get)
    best_fia_method = max(single_fias, key=single_fias.get)

    max_single_acc = single_accs[best_acc_method]
    min_single_far = single_fars[min_far_method]
    max_single_fia = single_fias[best_fia_method]

    fusion_acc = fusion_metrics.get("accuracy", 0.0)
    fusion_far = fusion_metrics.get("far", 0.0)
    fusion_fia = fusion_metrics.get("fia", 0.0)

    delta_acc = fusion_acc - max_single_acc
    delta_far = fusion_far - min_single_far
    delta_fia = fusion_fia - max_single_fia

    # FAR 减少百分比 (相对于 min_single_far)
    far_reduction_pct = 0.0
    if min_single_far > 0:
        far_reduction_pct = (min_single_far - fusion_far) / min_single_far * 100

    return {
        "delta_accuracy": round(delta_acc, 4),
        "delta_far": round(delta_far, 4),
        "delta_fia": round(delta_fia, 4),
        "best_single_acc_method": best_acc_method,
        "best_single_acc": round(max_single_acc, 4),
        "min_single_far_method": min_far_method,
        "min_single_far": round(min_single_far, 4),
        "best_single_fia_method": best_fia_method,
        "best_single_fia": round(max_single_fia, 4),
        "fusion_accuracy": round(fusion_acc, 4),
        "fusion_far": round(fusion_far, 4),
        "fusion_fia": round(fusion_fia, 4),
        "far_reduction_pct": round(far_reduction_pct, 2),
    }


# ────────────────────────────────────────────────────────────
# FAR 降低柱状图
# ────────────────────────────────────────────────────────────

def _plot_far_reduction(
    single_metrics: Dict[str, Dict[str, Any]],
    fusion_metrics: Dict[str, Any],
):
    """绘制 FAR 虚警率降低对比柱状图。

    每个单方法的 FAR 与 D-S 融合的 FAR 并排显示，
    直观对比融合带来的虚警率改善。
    """
    methods = sorted(single_metrics.keys())
    single_fars = [single_metrics[m]["far"] for m in methods]
    fusion_far = fusion_metrics.get("far", 0.0)

    fig, ax = plt.subplots(figsize=(12, 6))

    x = np.arange(len(methods) + 1)
    labels = methods + ["D-S 融合"]
    far_values = single_fars + [fusion_far]

    # 单方法柱 (蓝色系)
    bars_single = ax.bar(
        x[:len(methods)], single_fars, width=0.55,
        color=["steelblue"] * len(methods),
        edgecolor="navy", alpha=0.85,
        label="单方法 FAR",
    )
    # D-S 融合柱 (绿色)
    bars_fusion = ax.bar(
        x[len(methods)], fusion_far, width=0.55,
        color="seagreen", edgecolor="darkgreen", alpha=0.9,
        label="D-S 融合 FAR",
    )

    # 标注数值
    for bar_group in [bars_single, bars_fusion]:
        for bar in bar_group:
            height = bar.get_height()
            if height > 0.005:
                ax.text(
                    bar.get_x() + bar.get_width() / 2.0,
                    height + 0.01,
                    f"{height:.3f}",
                    ha="center", va="bottom", fontsize=9,
                )
            else:
                ax.text(
                    bar.get_x() + bar.get_width() / 2.0,
                    0.01,
                    f"{height:.3f}",
                    ha="center", va="bottom", fontsize=9,
                )

    # 标注最低单方法 FAR 和 融合 FAR 的差异箭头
    if len(methods) > 0:
        min_far_idx = np.argmin(single_fars)
        min_far_val = single_fars[min_far_idx]
        fusion_idx = len(methods)
        # 画一条虚线标注最低单方法 FAR
        ax.axhline(y=min_far_val, color="orange", linestyle="--", alpha=0.6,
                    label=f"最低单方法 FAR ({methods[min_far_idx]}={min_far_val:.3f})")

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_ylabel("FAR (虚警率)")
    ax.set_title("D-S 证据融合虚警率 (FAR) 降低对比\nHUSTbear 轴承数据集")
    ax.legend(loc="upper right", fontsize=9)
    ax.set_ylim(0, max(max(far_values, default=0.1) * 1.3, 0.1))
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    save_figure(fig, "far_reduction.png", "ds_fusion")


# ────────────────────────────────────────────────────────────
# 比较表 Markdown 生成
# ────────────────────────────────────────────────────────────

def _generate_comparison_table(
    single_metrics: Dict[str, Dict[str, Any]],
    fusion_metrics: Dict[str, Any],
    fusion_gain: Dict[str, Any],
) -> str:
    """生成 D-S 融合 vs 单方法比较表 Markdown 文档。"""
    lines = [
        "# D-S 证据融合评价报告",
        "",
        "> 数据集: HUSTbear (恒速轴承数据集, ER-16K)",
        "> 融合策略: Dempster-Shafer 组合规则 + Murphy 平均修正法",
        "> 单方法: 7 种轴承诊断算法各自独立诊断",
        "> 融合方法: run_research_ensemble (balanced profile)",
        "",
        "## 1. 融合原理",
        "",
        "D-S 证据理论通过 Dempster 组合规则将多种诊断算法的独立证据融合为综合概率分布:",
        "",
        "- **标准 Dempster 规则**: $m_{12}(A) = \\frac{\\sum_{B \\cap C = A} m_1(B) m_2(C)}{1 - K}$",
        "- **Murphy 平均修正法**: 当冲突系数 $K > 0.8$ 时自动切换，先平均 BPA 再逐次组合",
        "- **时域证据 BPA**: kurtosis/crest_factor 作为冲击型故障的补充证据",
        "",
        "## 2. 单方法分类性能",
        "",
        "| 方法 | Accuracy | FAR | FIA | Detection Score |",
        "|------|----------|-----|-----|-----------------|",
    ]

    for method_name in sorted(single_metrics.keys()):
        m = single_metrics[method_name]
        lines.append(
            f"| {method_name} | {m['accuracy']} | {m['far']} | {m['fia']} "
            f"| {m['detection_score']} |"
        )

    lines.extend([
        "",
        "## 3. D-S 融合分类性能",
        "",
        "| 指标 | 值 |",
        "|------|-----|",
        f"| Accuracy | {fusion_metrics['accuracy']} |",
        f"| Balanced Accuracy | {fusion_metrics['balanced_accuracy']} |",
        f"| Macro-F1 | {fusion_metrics['macro_f1']} |",
        f"| Weighted-F1 | {fusion_metrics['weighted_f1']} |",
        f"| Cohen's Kappa | {fusion_metrics['cohen_kappa']} |",
        f"| MCC | {fusion_metrics['mcc']} |",
        f"| FAR (虚警率) | {fusion_metrics['far']} |",
        f"| FIA (故障隔离准确率) | {fusion_metrics['fia']} |",
        f"| Detection Score | {fusion_metrics['detection_score']} |",
        f"| Macro-AUC-ROC | {fusion_metrics['macro_auc_roc']} |",
        f"| Macro-AUC-PR | {fusion_metrics['macro_auc_pr']} |",
        "",
    ])

    # ── 融合增益表 ──
    lines.extend([
        "## 4. 融合增益 (Fusion Gain)",
        "",
        "增益定义:",
        "",
        "- **ΔAccuracy** = Acc_fusion − max(Acc_single): 正值表示融合超越最佳单方法",
        "- **ΔFAR** = FAR_fusion − min(FAR_single): 负值表示融合降低虚警率(改进)",
        "- **ΔFIA** = FIA_fusion − max(FIA_single): 正值表示融合超越最佳单方法",
        "",
        "| 增益指标 | 值 | 基线方法 | 基线值 | 融合值 | 说明 |",
        "|----------|-----|----------|--------|--------|------|",
    ])

    # ΔAccuracy
    delta_acc = fusion_gain["delta_accuracy"]
    acc_sign = "+" if delta_acc >= 0 else ""
    acc_note = "超越最佳单方法" if delta_acc > 0 else ("持平" if delta_acc == 0 else "低于最佳单方法")
    lines.append(
        f"| ΔAccuracy | {acc_sign}{delta_acc} | "
        f"{fusion_gain['best_single_acc_method']} | "
        f"{fusion_gain['best_single_acc']} | "
        f"{fusion_gain['fusion_accuracy']} | {acc_note} |"
    )

    # ΔFAR
    delta_far = fusion_gain["delta_far"]
    far_sign = "+" if delta_far >= 0 else ""
    far_note = "虚警率降低(改进)" if delta_far < 0 else ("持平" if delta_far == 0 else "虚警率升高(退化)")
    if fusion_gain.get("far_reduction_pct", 0) != 0:
        far_note += f" ({fusion_gain['far_reduction_pct']:.1f}% 降低)"
    lines.append(
        f"| ΔFAR | {far_sign}{delta_far} | "
        f"{fusion_gain['min_single_far_method']} | "
        f"{fusion_gain['min_single_far']} | "
        f"{fusion_gain['fusion_far']} | {far_note} |"
    )

    # ΔFIA
    delta_fia = fusion_gain["delta_fia"]
    fia_sign = "+" if delta_fia >= 0 else ""
    fia_note = "超越最佳单方法" if delta_fia > 0 else ("持平" if delta_fia == 0 else "低于最佳单方法")
    lines.append(
        f"| ΔFIA | {fia_sign}{delta_fia} | "
        f"{fusion_gain['best_single_fia_method']} | "
        f"{fusion_gain['best_single_fia']} | "
        f"{fusion_gain['fusion_fia']} | {fia_note} |"
    )

    # ── 逐方法对比 ──
    lines.extend([
        "",
        "## 5. 逐方法对比",
        "",
        "| 方法 | Accuracy | FAR | FIA | Acc差值 | FAR差值 | FIA差值 |",
        "|------|----------|-----|-----|---------|---------|---------|",
    ])

    fusion_acc = fusion_metrics["accuracy"]
    fusion_far = fusion_metrics["far"]
    fusion_fia = fusion_metrics["fia"]

    for method_name in sorted(single_metrics.keys()):
        m = single_metrics[method_name]
        acc_diff = round(fusion_acc - m["accuracy"], 4)
        far_diff = round(fusion_far - m["far"], 4)
        fia_diff = round(fusion_fia - m["fia"], 4)

        acc_diff_str = f"+{acc_diff}" if acc_diff >= 0 else str(acc_diff)
        far_diff_str = f"+{far_diff}" if far_diff >= 0 else str(far_diff)
        fia_diff_str = f"+{fia_diff}" if fia_diff >= 0 else str(fia_diff)

        lines.append(
            f"| {method_name} | {m['accuracy']} | {m['far']} | {m['fia']} "
            f"| {acc_diff_str} | {far_diff_str} | {fia_diff_str} |"
        )

    # 融合行
    lines.append(
        f"| **D-S 融合** | **{fusion_acc}** | **{fusion_far}** | **{fusion_fia}** "
        f"| — | — | — |"
    )

    # ── D-S 融合内部统计 ──
    lines.extend([
        "",
        "## 6. D-S 融合内部统计",
        "",
        "| 指标 | 值 | 说明 |",
        "|------|-----|------|",
        f"| 冲突系数阈值 | 0.8 | K > 0.8 时切换 Murphy 平均法 |",
        f"| 证据门控 | kurt>5 或 crest>10 | 无时域冲击证据时统计指标降权 |",
        f"| 弱证据阈值 | confidence 0.2~0.55 | 部分质量给故障，更多给 Θ |",
        f"| 极弱证据阈值 | confidence < 0.2 | Θ 占主导 |",
        "",
    ])

    # ── 结论 ──
    lines.extend([
        "## 7. 结论",
        "",
    ])

    if fusion_gain["delta_accuracy"] > 0:
        lines.append(
            f"- Accuracy 提升: D-S 融合 ({fusion_gain['fusion_accuracy']}) "
            f"超越最佳单方法 {fusion_gain['best_single_acc_method']} "
            f"({fusion_gain['best_single_acc']})，提升 {fusion_gain['delta_accuracy']}"
        )
    elif fusion_gain["delta_accuracy"] == 0:
        lines.append(
            f"- Accuracy 持平: D-S 融合与最佳单方法 {fusion_gain['best_single_acc_method']} "
            f"Accuracy 相同 ({fusion_gain['fusion_accuracy']})"
        )
    else:
        lines.append(
            f"- Accuracy 下降: D-S 融合 ({fusion_gain['fusion_accuracy']}) "
            f"低于最佳单方法 {fusion_gain['best_single_acc_method']} "
            f"({fusion_gain['best_single_acc']})，下降 {abs(fusion_gain['delta_accuracy'])}"
        )

    if fusion_gain["delta_far"] < 0:
        lines.append(
            f"- FAR 改进: D-S 融合虚警率 ({fusion_gain['fusion_far']}) "
            f"低于最低单方法 {fusion_gain['min_single_far_method']} "
            f"({fusion_gain['min_single_far']})，降低 {abs(fusion_gain['delta_far'])} "
            f"({fusion_gain.get('far_reduction_pct', 0):.1f}%)"
        )
    elif fusion_gain["delta_far"] == 0:
        lines.append(
            f"- FAR 持平: D-S 融合与最低单方法 {fusion_gain['min_single_far_method']} "
            f"FAR 相同 ({fusion_gain['fusion_far']})"
        )
    else:
        lines.append(
            f"- FAR 退化: D-S 融合虚警率 ({fusion_gain['fusion_far']}) "
            f"高于最低单方法 {fusion_gain['min_single_far_method']} "
            f"({fusion_gain['min_single_far']})，升高 {fusion_gain['delta_far']}"
        )

    if fusion_gain["delta_fia"] > 0:
        lines.append(
            f"- FIA 提升: D-S 融合 ({fusion_gain['fusion_fia']}) "
            f"超越最佳单方法 {fusion_gain['best_single_fia_method']} "
            f"({fusion_gain['best_single_fia']})，提升 {fusion_gain['delta_fia']}"
        )
    elif fusion_gain["delta_fia"] == 0:
        lines.append(
            f"- FIA 持平: D-S 融合与最佳单方法 {fusion_gain['best_single_fia_method']} "
            f"FIA 相同 ({fusion_gain['fusion_fia']})"
        )
    else:
        lines.append(
            f"- FIA 下降: D-S 融合 ({fusion_gain['fusion_fia']}) "
            f"低于最佳单方法 {fusion_gain['best_single_fia_method']} "
            f"({fusion_gain['best_single_fia']})，下降 {abs(fusion_gain['delta_fia'])}"
        )

    lines.extend([
        "",
        "### 核心发现",
        "",
        "D-S 证据融合通过弱投票机制整合多源证据，理论上应:",
        "1. **降低虚警率**: 单方法的误报证据在融合中被低置信度投票稀释",
        "2. **提高故障隔离准确率**: 多方法一致指向的故障类型获得更高融合质量",
        "3. **保持检出率**: 只要多数方法检出故障，融合不会遗漏",
        "",
        "实际表现取决于:",
        "- 数据集中各类故障的分布比例",
        "- 各单方法对不同故障类型的敏感度差异",
        "- D-S BPA 分配参数（confidence 阈值、质量分配比例）",
        "",
    ])

    return "\n".join(lines)


# ────────────────────────────────────────────────────────────
# 入口
# ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    evaluate_ds_fusion()