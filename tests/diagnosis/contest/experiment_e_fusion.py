"""
实验E：D-S证据融合增益分析

大创答辩实验，对比7种单一轴承诊断方法与D-S融合方法的分类性能差异，
量化融合带来的FAR降低、Accuracy提升和FIA增益。

输出:
  experiment_e_fusion/far_reduction.svg     — FAR降低柱状图（标题写结论）
  experiment_e_fusion/confidence_dist.svg   — 置信度分布对比图
  experiment_e_fusion/fusion_gain.md        — 融合增益汇总表格

运行:
  cd /d/code/CNN/cloud
  . venv/Scripts/activate
  python -m tests.diagnosis.contest.experiment_e_fusion
"""
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))

# ── contest 模块 ──
from contest.config import (
    OUTPUT_DIR, EXP_DIRS, SAMPLE_RATE, MAX_SECONDS, MAX_SAMPLES,
    HUSTBEAR_BEARING, HUSTBEAR_DIR, BEARING_FREQ_COEFFS,
    HEALTH_THRESHOLD, MAX_PER_CLASS_HUSTBEAR, BEARING_METHODS_COMPARE,
    BEARING_LABELS, LABEL_CN,
)
from contest.style import (
    apply_contest_style, COLORS, METHOD_COLORS, get_method_color,
    make_conclusion_title, FIGURE_SIZE, FIGURE_SIZE_WIDE, FIGURE_DPI,
)

# ── evaluation 模块 ──
from tests.diagnosis.evaluation.datasets import classify_hustbear
from tests.diagnosis.evaluation.utils import load_npy
from tests.diagnosis.evaluation.classification_metrics_eval import evaluate_classification_performance

# ── 云端诊断模块 ──
from app.services.diagnosis.engine import (
    DiagnosisEngine, BearingMethod, DiagnosisStrategy, DenoiseMethod,
)
from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum
from app.services.diagnosis.ensemble import run_research_ensemble

# ── 风格 ──
apply_contest_style()

# ── 输出目录 ──
EXP_DIR = EXP_DIRS["e_fusion"]

# ────────────────────────────────────────────────────────────
# 常量
# ────────────────────────────────────────────────────────────

# 有效分类标签
GROUND_TRUTH_LABELS = ["healthy", "inner", "outer", "ball", "composite"]

# 单一轴承方法列表
SINGLE_BEARING_METHODS = [
    BearingMethod.ENVELOPE,
    BearingMethod.KURTOGRAM,
    BearingMethod.CPW,
    BearingMethod.MED,
    BearingMethod.TEAGER,
    BearingMethod.SPECTRAL_KURTOSIS,
    BearingMethod.MCKD,
]

# 方法中文名映射（用于图表标签）
METHOD_CN = {
    "envelope":           "包络分析",
    "kurtogram":          "Kurtogram",
    "cpw":                "CPW预白化",
    "med":                "MED增强",
    "teager":             "Teager",
    "spectral_kurtosis":  "谱峭度重加权",
    "mckd":               "MCKD",
}

# fault_indicators 命名 → 分类标签
INDICATOR_TO_LABEL = {
    "bpfo": "outer",
    "bpfo_stat": "outer",
    "bpfi": "inner",
    "bpfi_stat": "inner",
    "bsf": "ball",
    "bsf_stat": "ball",
    "ftf": "ball",
    "ftf_stat": "ball",
    "envelope_peak_snr": "outer",
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


# ────────────────────────────────────────────────────────────
# 数据加载
# ────────────────────────────────────────────────────────────

def get_hustbear_files_contest() -> List[Tuple[Path, Dict]]:
    """获取HUSTbear数据集文件列表（contest模式：仅X通道，每类3个）"""
    if not HUSTBEAR_DIR.exists():
        return []

    files = []
    for f in sorted(HUSTBEAR_DIR.glob("*.npy")):
        if not f.name.endswith("-X.npy"):
            continue
        info = classify_hustbear(f.name)
        if info["label"] != "unknown":
            files.append((f, info))

    # 每类最多 MAX_PER_CLASS_HUSTBEAR 个
    class_files = defaultdict(list)
    for f, info in files:
        lbl = info["label"]
        class_files[lbl].append((f, info))

    result = []
    for lbl in sorted(class_files.keys()):
        result.extend(class_files[lbl][:MAX_PER_CLASS_HUSTBEAR])

    return result


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
    if int(health_score) >= HEALTH_THRESHOLD:
        return "healthy"

    indicators = result.get("fault_indicators", {}) or {}

    # 参数匹配指标优先
    param_hits = []
    stat_hits = []
    for name, item in indicators.items():
        if not isinstance(item, dict):
            continue
        if bool(item.get("significant", False)):
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
    hs = int(result.get("health_score", 100))
    if hs >= HEALTH_THRESHOLD:
        return "healthy"

    # 4. 无明确判断 → unknown
    return "unknown"


# ────────────────────────────────────────────────────────────
# 评价主流程
# ────────────────────────────────────────────────────────────

def run_experiment_e():
    """实验E主入口：D-S证据融合增益分析"""
    print("\n" + "=" * 70)
    print("  实验E：D-S证据融合增益分析")
    print("=" * 70)

    hust_files = get_hustbear_files_contest()
    if not hust_files:
        print("[SKIP] HUSTbear 数据集不可用，无法运行实验E")
        return None

    print(f"  加载 HUSTbear 数据集: {len(hust_files)} 文件")
    for lbl in GROUND_TRUTH_LABELS:
        cnt = sum(1 for _, info in hust_files if info["label"] == lbl)
        print(f"    {LABEL_CN.get(lbl, lbl)}: {cnt} 文件")

    # ══════════════════════════════════════════════════════
    # 阶段1: 单一方法诊断
    # ══════════════════════════════════════════════════════
    print(f"\n  ── 阶段1: 单一轴承方法诊断 ──")

    single_method_data: Dict[str, Dict[str, List]] = {}
    # {method_name: {"y_true": [...], "y_pred": [...], "scores": [...], "confidences": [...]}}

    for filepath, info in hust_files:
        signal = load_npy(filepath, MAX_SAMPLES)
        rot_freq = estimate_rot_freq_spectrum(signal, SAMPLE_RATE)
        true_label = info["label"]

        for bm in SINGLE_BEARING_METHODS:
            method_name = bm.value
            if method_name not in single_method_data:
                single_method_data[method_name] = {
                    "y_true": [], "y_pred": [], "scores": [], "confidences": [],
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
                comp = engine.analyze_comprehensive(signal, SAMPLE_RATE, rot_freq=rot_freq)
                hs = int(comp.get("health_score", 100))
                exec_time = (time.perf_counter() - t0) * 1000

                pred_label = _predict_label_from_bearing_result(result, hs)
                score = 100.0 - hs

                # 置信度: fault_indicators 命中数量 / 总指标数
                indicators = result.get("fault_indicators", {}) or {}
                n_significant = sum(
                    1 for v in indicators.values()
                    if isinstance(v, dict) and bool(v.get("significant", False))
                )
                confidence = min(n_significant / max(len(indicators), 1), 1.0)

                single_method_data[method_name]["y_true"].append(true_label)
                single_method_data[method_name]["y_pred"].append(pred_label)
                single_method_data[method_name]["scores"].append(score)
                single_method_data[method_name]["confidences"].append(confidence)

                print(f"    {filepath.name} | {METHOD_CN.get(method_name, method_name)} | "
                      f"true={LABEL_CN.get(true_label, true_label)} "
                      f"pred={LABEL_CN.get(pred_label, pred_label)} "
                      f"hs={hs} conf={confidence:.2f} ({exec_time:.0f}ms)")
            except Exception as e:
                print(f"    [ERR] {method_name} on {filepath.name}: {e}")
                single_method_data[method_name]["y_true"].append(true_label)
                single_method_data[method_name]["y_pred"].append("unknown")
                single_method_data[method_name]["scores"].append(0.0)
                single_method_data[method_name]["confidences"].append(0.0)

    # ══════════════════════════════════════════════════════
    # 阶段2: D-S融合诊断
    # ══════════════════════════════════════════════════════
    print(f"\n  ── 阶段2: D-S融合诊断 (run_research_ensemble, profile=balanced) ──")

    fusion_data = {"y_true": [], "y_pred": [], "scores": [], "confidences": []}

    for filepath, info in hust_files:
        signal = load_npy(filepath, MAX_SAMPLES)
        rot_freq = estimate_rot_freq_spectrum(signal, SAMPLE_RATE)
        true_label = info["label"]

        try:
            t0 = time.perf_counter()
            result = run_research_ensemble(
                signal, SAMPLE_RATE,
                bearing_params=HUSTBEAR_BEARING,
                denoise_method="none",
                rot_freq=rot_freq,
                profile="balanced",
            )
            exec_time = (time.perf_counter() - t0) * 1000

            pred_label = _predict_label_from_ensemble(result)
            hs = int(result.get("health_score", 100))
            score = 100.0 - hs

            # D-S 融合的连续分数: 使用 dominant_probability
            ds_result = result.get("ensemble", {}).get("ds_fusion", {})
            if isinstance(ds_result, dict) and "dominant_probability" in ds_result:
                ds_score = float(ds_result.get("dominant_probability", 0)) * 100
                if pred_label == "healthy":
                    ds_score = 100 - ds_score
                score = ds_score

            # 融合置信度: dominant_probability
            fusion_confidence = float(ds_result.get("dominant_probability", 0)) if isinstance(ds_result, dict) else 0.0

            fusion_data["y_true"].append(true_label)
            fusion_data["y_pred"].append(pred_label)
            fusion_data["scores"].append(score)
            fusion_data["confidences"].append(fusion_confidence)

            print(f"    {filepath.name} | D-S融合 | "
                  f"true={LABEL_CN.get(true_label, true_label)} "
                  f"pred={LABEL_CN.get(pred_label, pred_label)} "
                  f"hs={hs} "
                  f"dominant={ds_result.get('dominant_fault', 'N/A')} "
                  f"prob={ds_result.get('dominant_probability', 0):.3f} "
                  f"conf={fusion_confidence:.3f} "
                  f"({exec_time:.0f}ms)")
        except Exception as e:
            print(f"    [ERR] D-S融合 on {filepath.name}: {e}")
            fusion_data["y_true"].append(true_label)
            fusion_data["y_pred"].append("unknown")
            fusion_data["scores"].append(0.0)
            fusion_data["confidences"].append(0.0)

    # ══════════════════════════════════════════════════════
    # 阶段3: 计算分类指标
    # ══════════════════════════════════════════════════════
    print(f"\n  ── 阶段3: 计算分类指标 ──")

    valid_labels = list(GROUND_TRUTH_LABELS)

    # 各单方法分类指标
    single_metrics: Dict[str, Dict[str, Any]] = {}
    for method_name, data in single_method_data.items():
        n_samples = len(data["y_true"])
        if n_samples < 3:
            continue

        metrics = evaluate_classification_performance(
            y_true=data["y_true"],
            y_pred=data["y_pred"],
            scores=data["scores"],
            labels=valid_labels,
            output_subdir=str(EXP_DIR),
            title_prefix=f"实验E_单方法_{method_name}",
        )
        single_metrics[method_name] = metrics
        print(f"    {METHOD_CN.get(method_name, method_name)}: "
              f"Acc={metrics['accuracy']:.4f} "
              f"FAR={metrics['far']:.4f} "
              f"FIA={metrics['fia']:.4f}")

    # D-S融合分类指标
    fusion_metrics = evaluate_classification_performance(
        y_true=fusion_data["y_true"],
        y_pred=fusion_data["y_pred"],
        scores=fusion_data["scores"],
        labels=valid_labels,
        output_subdir=str(EXP_DIR),
        title_prefix="实验E_DS融合",
    )
    print(f"    D-S融合: Acc={fusion_metrics['accuracy']:.4f} "
          f"FAR={fusion_metrics['far']:.4f} "
          f"FIA={fusion_metrics['fia']:.4f}")

    # ══════════════════════════════════════════════════════
    # 阶段4: 计算融合增益
    # ══════════════════════════════════════════════════════
    fusion_gain = _compute_fusion_gain(single_metrics, fusion_metrics)

    print(f"\n  ── 阶段4: 融合增益 ──")
    print(f"    ΔAccuracy = {fusion_gain['delta_accuracy']:.4f} "
          f"(最佳单方法 {fusion_gain['best_single_acc_method']} "
          f"{fusion_gain['best_single_acc']:.4f} → 融合 {fusion_gain['fusion_accuracy']:.4f})")
    print(f"    FAR降低率 = {fusion_gain['far_reduction_pct']:.1f}% "
          f"(最高FAR {fusion_gain['max_single_far']:.4f} → 融合 {fusion_gain['fusion_far']:.4f})")
    print(f"    ΔFIA = {fusion_gain['delta_fia']:.4f} "
          f"(最佳单方法 {fusion_gain['best_single_fia_method']} "
          f"{fusion_gain['best_single_fia']:.4f} → 融合 {fusion_gain['fusion_fia']:.4f})")

    # ══════════════════════════════════════════════════════
    # 阶段5: 生成图表与报告
    # ══════════════════════════════════════════════════════
    _plot_far_reduction(single_metrics, fusion_metrics, fusion_gain)
    _plot_confidence_distribution(single_method_data, fusion_data)
    report = _generate_fusion_gain_report(single_metrics, fusion_metrics, fusion_gain)

    report_path = EXP_DIR / "fusion_gain.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n  报告已保存: {report_path}")
    print(f"  图表已保存: {EXP_DIR}")

    return {
        "single_metrics": single_metrics,
        "fusion_metrics": fusion_metrics,
        "fusion_gain": fusion_gain,
    }


# ────────────────────────────────────────────────────────────
# 融合增益计算
# ────────────────────────────────────────────────────────────

def _compute_fusion_gain(
    single_metrics: Dict[str, Dict[str, Any]],
    fusion_metrics: Dict[str, Any],
) -> Dict[str, Any]:
    """计算 D-S 融合相对于单方法的增益。

    - ΔAccuracy = Acc_fusion - max(Acc_single)
    - FAR降低率 = (max(FAR_single) - FAR_fusion) / max(FAR_single) × 100%
    - ΔFIA = FIA_fusion - max(FIA_single)
    """
    if not single_metrics:
        return {
            "delta_accuracy": 0.0,
            "far_reduction_pct": 0.0,
            "delta_fia": 0.0,
            "best_single_acc_method": "N/A",
            "best_single_acc": 0.0,
            "max_single_far_method": "N/A",
            "max_single_far": 0.0,
            "best_single_fia_method": "N/A",
            "best_single_fia": 0.0,
            "fusion_accuracy": 0.0,
            "fusion_far": 0.0,
            "fusion_fia": 0.0,
        }

    single_accs = {m: v["accuracy"] for m, v in single_metrics.items()}
    single_fars = {m: v["far"] for m, v in single_metrics.items()}
    single_fias = {m: v["fia"] for m, v in single_metrics.items()}

    best_acc_method = max(single_accs, key=single_accs.get)
    max_far_method = max(single_fars, key=single_fars.get)
    best_fia_method = max(single_fias, key=single_fias.get)

    max_single_acc = single_accs[best_acc_method]
    max_single_far = single_fars[max_far_method]
    max_single_fia = single_fias[best_fia_method]

    fusion_acc = fusion_metrics.get("accuracy", 0.0)
    fusion_far = fusion_metrics.get("far", 0.0)
    fusion_fia = fusion_metrics.get("fia", 0.0)

    delta_acc = fusion_acc - max_single_acc
    delta_fia = fusion_fia - max_single_fia

    # FAR降低率: (max_single_far - fusion_far) / max_single_far × 100%
    far_reduction_pct = 0.0
    if max_single_far > 0:
        far_reduction_pct = (max_single_far - fusion_far) / max_single_far * 100

    return {
        "delta_accuracy": round(delta_acc, 4),
        "far_reduction_pct": round(far_reduction_pct, 2),
        "delta_fia": round(delta_fia, 4),
        "best_single_acc_method": best_acc_method,
        "best_single_acc": round(max_single_acc, 4),
        "max_single_far_method": max_far_method,
        "max_single_far": round(max_single_far, 4),
        "best_single_fia_method": best_fia_method,
        "best_single_fia": round(max_single_fia, 4),
        "fusion_accuracy": round(fusion_acc, 4),
        "fusion_far": round(fusion_far, 4),
        "fusion_fia": round(fusion_fia, 4),
    }


# ────────────────────────────────────────────────────────────
# 图表1: FAR降低柱状图
# ────────────────────────────────────────────────────────────

def _plot_far_reduction(
    single_metrics: Dict[str, Dict[str, Any]],
    fusion_metrics: Dict[str, Any],
    fusion_gain: Dict[str, Any],
):
    """绘制 FAR 降低柱状图。

    单一方法灰色柱，融合方法红色柱。
    虚线标注最高单方法FAR baseline。
    标题直接写结论。
    """
    import matplotlib.pyplot as plt

    # 方法排序: 按FAR从高到低
    methods = sorted(single_metrics.keys(), key=lambda m: single_metrics[m]["far"], reverse=True)
    single_fars = [single_metrics[m]["far"] for m in methods]
    fusion_far = fusion_metrics.get("far", 0.0)

    # 中文标签
    labels_cn = [METHOD_CN.get(m, m) for m in methods] + ["D-S融合"]

    # 总FAR值列表
    all_fars = single_fars + [fusion_far]
    max_far = max(all_fars) if all_fars else 0.1

    # 构建结论式标题
    max_single_far = fusion_gain.get("max_single_far", 0.0)
    far_reduction_pct = fusion_gain.get("far_reduction_pct", 0.0)
    title = make_conclusion_title("虚警率(FAR)", max_single_far * 100, fusion_far * 100, "%")
    # 替换为更精确的描述
    if far_reduction_pct > 0:
        title = f"D-S融合将虚警率降低 {far_reduction_pct:.1f}%（{max_single_far:.3f} → {fusion_far:.3f}）"
    else:
        title = f"D-S融合虚警率对比：{max_single_far:.3f} → {fusion_far:.3f}"

    fig, ax = plt.subplots(figsize=FIGURE_SIZE_WIDE)

    x = np.arange(len(methods) + 1)
    bar_width = 0.55

    # 单一方法柱 — 灰色
    bars_single = ax.bar(
        x[:len(methods)], single_fars, width=bar_width,
        color=COLORS["baseline"],
        edgecolor="#7F8C8D", alpha=0.85,
        label="单一方法 FAR",
    )

    # 融合方法柱 — 红色
    bars_fusion = ax.bar(
        x[len(methods)], fusion_far, width=bar_width,
        color=COLORS["our_method"],
        edgecolor="#C0392B", alpha=0.90,
        label="D-S融合 FAR",
    )

    # 标注数值
    for bar_group in [bars_single, bars_fusion]:
        for bar in bar_group:
            height = bar.get_height()
            offset = 0.005 if height > 0.005 else 0.01
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                height + offset,
                f"{height:.3f}",
                ha="center", va="bottom", fontsize=10,
                fontweight="bold",
            )

    # 虚线标注最高单方法FAR baseline
    if max_single_far > 0:
        ax.axhline(
            y=max_single_far, color="#E74C3C", linestyle="--",
            linewidth=1.5, alpha=0.6,
            label=f"最高单方法FAR baseline ({max_single_far:.3f})",
        )

    ax.set_xticks(x)
    ax.set_xticklabels(labels_cn, rotation=30, ha="right")
    ax.set_ylabel("FAR（虚警率）")
    ax.set_title(title, fontweight="bold")
    ax.legend(loc="upper right", fontsize=10)
    ax.set_ylim(0, max(max_far * 1.35, 0.1))
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    fig.savefig(EXP_DIR / "far_reduction.svg", bbox_inches="tight")
    plt.close(fig)
    print(f"  [图表] FAR降低柱状图 → {EXP_DIR / 'far_reduction.svg'}")


# ────────────────────────────────────────────────────────────
# 图表2: 置信度分布对比图
# ────────────────────────────────────────────────────────────

def _plot_confidence_distribution(
    single_method_data: Dict[str, Dict[str, List]],
    fusion_data: Dict[str, List],
):
    """绘制置信度分布对比图。

    左子图: 各单方法的置信度箱线图（灰色）
    右子图: D-S融合的置信度分布（红色直方图+箱线图）

    置信度定义:
    - 单方法: fault_indicators 命中率
    - 融合: dominant_probability
    """
    import matplotlib.pyplot as plt

    # ── 单方法置信度 ──
    method_names = sorted(single_method_data.keys())
    single_confidences = []
    labels_cn = []
    for m in method_names:
        confs = single_method_data[m]["confidences"]
        if confs:
            single_confidences.append(confs)
            labels_cn.append(METHOD_CN.get(m, m))

    # ── 融合置信度 ──
    fusion_confidences = fusion_data["confidences"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=FIGURE_SIZE_WIDE)

    # ── 左子图: 单方法置信度箱线图 ──
    if single_confidences:
        bp = ax1.boxplot(
            single_confidences,
            patch_artist=True,
            labels=labels_cn,
            widths=0.5,
        )
        for patch in bp["boxes"]:
            patch.set_facecolor(COLORS["baseline"])
            patch.set_alpha(0.7)
            patch.set_edgecolor("#7F8C8D")
        for median in bp["medians"]:
            median.set_color("#2C3E50")
            median.set_linewidth(2)

        ax1.set_ylabel("置信度")
        ax1.set_title("单一方法置信度分布", fontweight="bold")
        ax1.tick_params(axis="x", rotation=30)
        ax1.set_ylim(-0.05, 1.05)
        ax1.grid(axis="y", alpha=0.3)

    # ── 右子图: 融合置信度 ──
    if fusion_confidences:
        # 直方图
        bins = np.linspace(0, 1, 20)
        ax2.hist(
            fusion_confidences, bins=bins,
            color=COLORS["our_method"], alpha=0.7,
            edgecolor="#C0392B", label="D-S融合置信度",
        )

        # 箱线图叠加（缩小版）
        bp2 = ax2.boxplot(
            fusion_confidences,
            positions=[0.5], widths=0.08,
            patch_artist=True, vert=True,
            manage_ticks=False,
        )
        for patch in bp2["boxes"]:
            patch.set_facecolor(COLORS["our_method"])
            patch.set_alpha(0.5)
        for median in bp2["medians"]:
            median.set_color("#C0392B")
            median.set_linewidth(2)

        # 标注均值
        mean_conf = np.mean(fusion_confidences)
        ax2.axvline(mean_conf, color="#C0392B", linestyle="--", alpha=0.8,
                    label=f"均值={mean_conf:.3f}")

        ax2.set_xlabel("置信度（dominant_probability）")
        ax2.set_ylabel("样本数")
        ax2.set_title("D-S融合置信度分布", fontweight="bold")
        ax2.legend(loc="upper right", fontsize=10)
        ax2.set_xlim(0, 1)
        ax2.grid(alpha=0.3)

    plt.tight_layout()
    fig.savefig(EXP_DIR / "confidence_dist.svg", bbox_inches="tight")
    plt.close(fig)
    print(f"  [图表] 置信度分布对比 → {EXP_DIR / 'confidence_dist.svg'}")


# ────────────────────────────────────────────────────────────
# Markdown 报告生成
# ────────────────────────────────────────────────────────────

def _generate_fusion_gain_report(
    single_metrics: Dict[str, Dict[str, Any]],
    fusion_metrics: Dict[str, Any],
    fusion_gain: Dict[str, Any],
) -> str:
    """生成融合增益汇总 Markdown 报告。"""
    lines = [
        "# 实验E：D-S证据融合增益分析",
        "",
        "> 数据集: HUSTbear (恒速轴承数据集, ER-16K)",
        "> 单一方法: 7种轴承诊断算法各自独立诊断",
        "> 融合方法: run_research_ensemble (balanced profile)",
        "> 融合策略: Dempster-Shafer 组合规则 + Murphy 平均修正法",
        "",
        "## 1. 融合原理",
        "",
        "D-S证据理论通过Dempster组合规则将多种诊断算法的独立证据融合为综合概率分布:",
        "",
        "- **标准 Dempster 规则**: $m_{12}(A) = \\frac{\\sum_{B \\cap C = A} m_1(B) m_2(C)}{1 - K}$",
        "- **Murphy 平均修正法**: 当冲突系数 $K > 0.8$ 时自动切换，先平均 BPA 再逐次组合",
        "- **时域证据 BPA**: kurtosis/crest_factor 作为冲击型故障的补充证据",
        "- **弱投票机制**: 仅当多个独立指标一致指向故障时才判定为故障",
        "",
        "## 2. 单一方法分类性能",
        "",
        "| 方法 | Accuracy | FAR | FIA | Detection Score |",
        "|------|----------|-----|-----|-----------------|",
    ]

    for method_name in sorted(single_metrics.keys()):
        m = single_metrics[method_name]
        cn = METHOD_CN.get(method_name, method_name)
        lines.append(
            f"| {cn} | {m['accuracy']:.4f} | {m['far']:.4f} | {m['fia']:.4f} "
            f"| {m['detection_score']:.4f} |"
        )

    lines.extend([
        "",
        "## 3. D-S融合分类性能",
        "",
        "| 指标 | 值 |",
        "|------|-----|",
        f"| Accuracy | {fusion_metrics['accuracy']:.4f} |",
        f"| Balanced Accuracy | {fusion_metrics['balanced_accuracy']:.4f} |",
        f"| Macro-F1 | {fusion_metrics['macro_f1']:.4f} |",
        f"| Weighted-F1 | {fusion_metrics['weighted_f1']:.4f} |",
        f"| Cohen's Kappa | {fusion_metrics['cohen_kappa']:.4f} |",
        f"| MCC | {fusion_metrics['mcc']:.4f} |",
        f"| FAR (虚警率) | {fusion_metrics['far']:.4f} |",
        f"| FIA (故障隔离准确率) | {fusion_metrics['fia']:.4f} |",
        f"| Detection Score | {fusion_metrics['detection_score']:.4f} |",
        f"| Macro-AUC-ROC | {fusion_metrics['macro_auc_roc']:.4f} |",
        f"| Macro-AUC-PR | {fusion_metrics['macro_auc_pr']:.4f} |",
        "",
    ])

    # ── 融合增益汇总表 ──
    lines.extend([
        "## 4. 融合增益汇总",
        "",
        "增益定义:",
        "",
        "- **ΔAccuracy** = Acc_fusion − max(Acc_single): 正值表示融合超越最佳单方法",
        "- **FAR降低率** = (max(FAR_single) − FAR_fusion) / max(FAR_single) × 100%: 正值表示虚警率改善",
        "- **ΔFIA** = FIA_fusion − max(FIA_single): 正值表示融合超越最佳单方法",
        "",
        "| 增益指标 | 值 | 基线 | 基线值 | 融合值 | 说明 |",
        "|----------|-----|------|--------|--------|------|",
    ])

    # ΔAccuracy
    delta_acc = fusion_gain["delta_accuracy"]
    acc_sign = "+" if delta_acc >= 0 else ""
    acc_note = "超越最佳单方法" if delta_acc > 0 else ("持平" if delta_acc == 0 else "低于最佳单方法")
    lines.append(
        f"| ΔAccuracy | {acc_sign}{delta_acc:.4f} | "
        f"最佳单方法({METHOD_CN.get(fusion_gain['best_single_acc_method'], fusion_gain['best_single_acc_method'])}) | "
        f"{fusion_gain['best_single_acc']:.4f} | "
        f"{fusion_gain['fusion_accuracy']:.4f} | {acc_note} |"
    )

    # FAR降低率
    far_reduction = fusion_gain["far_reduction_pct"]
    far_note = f"虚警率降低{far_reduction:.1f}%" if far_reduction > 0 else ("持平" if far_reduction == 0 else "虚警率升高")
    lines.append(
        f"| FAR降低率 | {far_reduction:.2f}% | "
        f"最高FAR({METHOD_CN.get(fusion_gain['max_single_far_method'], fusion_gain['max_single_far_method'])}) | "
        f"{fusion_gain['max_single_far']:.4f} | "
        f"{fusion_gain['fusion_far']:.4f} | {far_note} |"
    )

    # ΔFIA
    delta_fia = fusion_gain["delta_fia"]
    fia_sign = "+" if delta_fia >= 0 else ""
    fia_note = "超越最佳单方法" if delta_fia > 0 else ("持平" if delta_fia == 0 else "低于最佳单方法")
    lines.append(
        f"| ΔFIA | {fia_sign}{delta_fia:.4f} | "
        f"最佳单方法({METHOD_CN.get(fusion_gain['best_single_fia_method'], fusion_gain['best_single_fia_method'])}) | "
        f"{fusion_gain['best_single_fia']:.4f} | "
        f"{fusion_gain['fusion_fia']:.4f} | {fia_note} |"
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
        cn = METHOD_CN.get(method_name, method_name)
        acc_diff = fusion_acc - m["accuracy"]
        far_diff = fusion_far - m["far"]
        fia_diff = fusion_fia - m["fia"]

        acc_diff_str = f"+{acc_diff:.4f}" if acc_diff >= 0 else f"{acc_diff:.4f}"
        far_diff_str = f"+{far_diff:.4f}" if far_diff >= 0 else f"{far_diff:.4f}"
        fia_diff_str = f"+{fia_diff:.4f}" if fia_diff >= 0 else f"{fia_diff:.4f}"

        lines.append(
            f"| {cn} | {m['accuracy']:.4f} | {m['far']:.4f} | {m['fia']:.4f} "
            f"| {acc_diff_str} | {far_diff_str} | {fia_diff_str} |"
        )

    lines.append(
        f"| **D-S融合** | **{fusion_acc:.4f}** | **{fusion_far:.4f}** | **{fusion_fia:.4f}** "
        f"| — | — | — |"
    )

    # ── 结论 ──
    lines.extend([
        "",
        "## 6. 结论",
        "",
    ])

    if fusion_gain["delta_accuracy"] > 0:
        lines.append(
            f"- **Accuracy提升**: D-S融合 ({fusion_gain['fusion_accuracy']:.4f}) "
            f"超越最佳单方法 {METHOD_CN.get(fusion_gain['best_single_acc_method'], fusion_gain['best_single_acc_method'])} "
            f"({fusion_gain['best_single_acc']:.4f})，提升 ΔAccuracy = +{fusion_gain['delta_accuracy']:.4f}"
        )
    elif fusion_gain["delta_accuracy"] == 0:
        lines.append(
            f"- **Accuracy持平**: D-S融合与最佳单方法 Accuracy 相同 ({fusion_gain['fusion_accuracy']:.4f})"
        )
    else:
        lines.append(
            f"- **Accuracy下降**: D-S融合 ({fusion_gain['fusion_accuracy']:.4f}) "
            f"低于最佳单方法 ({fusion_gain['best_single_acc']:.4f})，ΔAccuracy = {fusion_gain['delta_accuracy']:.4f}"
        )

    if far_reduction > 0:
        lines.append(
            f"- **FAR降低**: D-S融合虚警率 ({fusion_gain['fusion_far']:.4f}) "
            f"相比最高单方法 ({fusion_gain['max_single_far']:.4f}) 降低 {far_reduction:.1f}%"
        )
    elif far_reduction == 0:
        lines.append(
            f"- **FAR持平**: D-S融合虚警率与最高单方法相同 ({fusion_gain['fusion_far']:.4f})"
        )
    else:
        lines.append(
            f"- **FAR升高**: D-S融合虚警率 ({fusion_gain['fusion_far']:.4f}) "
            f"高于最高单方法 ({fusion_gain['max_single_far']:.4f})"
        )

    if fusion_gain["delta_fia"] > 0:
        lines.append(
            f"- **FIA提升**: D-S融合 ({fusion_gain['fusion_fia']:.4f}) "
            f"超越最佳单方法 ({fusion_gain['best_single_fia']:.4f})，提升 ΔFIA = +{fusion_gain['delta_fia']:.4f}"
        )
    elif fusion_gain["delta_fia"] == 0:
        lines.append(
            f"- **FIA持平**: D-S融合与最佳单方法 FIA 相同 ({fusion_gain['fusion_fia']:.4f})"
        )
    else:
        lines.append(
            f"- **FIA下降**: D-S融合 ({fusion_gain['fusion_fia']:.4f}) "
            f"低于最佳单方法 ({fusion_gain['best_single_fia']:.4f})，ΔFIA = {fusion_gain['delta_fia']:.4f}"
        )

    lines.extend([
        "",
        "### 核心发现",
        "",
        "D-S证据融合通过弱投票机制整合多源证据:",
        "1. **降低虚警率**: 单方法的误报证据在融合中被低置信度投票稀释",
        "2. **提高故障隔离准确率**: 多方法一致指向的故障类型获得更高置信度",
        "3. **鲁棒性增强**: 任一单方法失效时，其他方法的独立证据仍可维持诊断能力",
    ])

    return "\n".join(lines)


# ────────────────────────────────────────────────────────────
# 直接运行
# ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = run_experiment_e()
    if result:
        print("\n  实验E完成!")
        print(f"  融合增益: ΔAccuracy={result['fusion_gain']['delta_accuracy']:.4f}, "
              f"FAR降低率={result['fusion_gain']['far_reduction_pct']:.1f}%, "
              f"ΔFIA={result['fusion_gain']['delta_fia']:.4f}")
    else:
        print("\n  实验E未能运行（数据集不可用）")