"""
健康度趋势与预后性评价模块

从 WTgearbox 数据集构造伪退化序列，评价健康度评分的 PHM 趋势指标，
并验证 sigmoid/cascade 连续扣分函数的单调性。

输出:
    - health_trend/monotonicity_report.md
    - health_trend/hi_trajectory.png (健康度轨迹曲线)
    - health_trend/deduction_monotonicity.png (扣分单调性验证)
"""
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))

from app.services.diagnosis import (
    DiagnosisEngine, GearMethod, DiagnosisStrategy, DenoiseMethod,
)
from app.services.diagnosis.health_score_continuous import (
    sigmoid_deduction, cascade_deduction, multi_threshold_deduction,
)
from app.services.diagnosis.health_score import _compute_health_score

from .config import (
    OUTPUT_DIR, SAMPLE_RATE, WTGEARBOX_GEAR, MESH_FREQ_COEFF,
)
from .datasets import get_wtgearbox_files
from .utils import (
    load_npy, save_cache, save_figure,
    compute_monotonicity, compute_trendability,
    compute_prognosability, compute_hi_robustness,
)

import matplotlib.pyplot as plt

# 伪退化序列：按故障严重度排序
# healthy → wear → crack → missing → break
SEVERITY_ORDER = ["healthy", "wear", "crack", "missing", "break"]

# PHM 指标目标值
TARGET_MONOTONICITY = 0.85
TARGET_TRENDABILITY = 0.90
TARGET_PROGNOSABILITY = 0.70


def evaluate_health_trend():
    """健康度趋势与预后性评价主入口"""
    print("\n" + "=" * 60)
    print("【模块6】健康度趋势与预后性评价")
    print("=" * 60)

    # 创建输出子目录
    trend_dir = OUTPUT_DIR / "health_trend"
    trend_dir.mkdir(parents=True, exist_ok=True)

    wt_files = get_wtgearbox_files()
    if not wt_files:
        print("[SKIP] WTgearbox 数据集不可用")
        return {}

    # ═══════ Step 1: 构造伪退化序列 ═══════
    degradation_data = _construct_degradation_sequence(wt_files)
    if not degradation_data:
        print("[SKIP] 伪退化序列构造失败（样本不足）")
        return {}

    # ═══════ Step 2: 计算 PHM 指标 ═══════
    phm_metrics = _compute_phm_metrics(degradation_data)

    # ═══════ Step 3: 验证扣分单调性 ═══════
    deduction_results = _validate_deduction_monotonicity()

    # ═══════ Step 4: 保存结果与图表 ═══════
    _save_trajectory_plot(degradation_data, trend_dir)
    _save_deduction_monotonicity_plot(deduction_results, trend_dir)
    report = _generate_report(degradation_data, phm_metrics, deduction_results)
    with open(trend_dir / "monotonicity_report.md", "w", encoding="utf-8") as f:
        f.write(report)

    save_cache("health_trend_degradation", degradation_data)
    save_cache("health_trend_phm_metrics", phm_metrics)
    save_cache("health_trend_deduction_results", deduction_results)

    print(f"  报告已保存: {trend_dir / 'monotonicity_report.md'}")
    print(f"  PHM 指标:")
    print(f"    Monotonicity     = {phm_metrics['monotonicity']:.4f}  (目标 ≥ {TARGET_MONOTONICITY})")
    print(f"    Trendability     = {phm_metrics['trendability']:.4f}  (目标 |r| ≥ {TARGET_TRENDABILITY})")
    print(f"    Prognosability   = {phm_metrics['prognosability']:.4f}  (目标 ≥ {TARGET_PROGNOSABILITY})")
    print(f"    HI Robustness    = {phm_metrics['hi_robustness']:.4f}")

    return {
        "degradation_data": degradation_data,
        "phm_metrics": phm_metrics,
        "deduction_results": deduction_results,
    }


# ═══════════════════════════════════════════════════════════
# Step 1: 伪退化序列构造
# ═══════════════════════════════════════════════════════════

def _construct_degradation_sequence(wt_files) -> List[Dict]:
    """
    从 WTgearbox 数据集按严重度排序构造伪退化序列。

    严重度排序: healthy → wear → crack → missing → break
    对每个严重度等级的所有样本运行 DiagnosisEngine(EXPERT),
    收集平均健康度作为该等级的 HI 值。
    """
    from collections import defaultdict

    # 按故障类型分组
    class_files = defaultdict(list)
    for filepath, info in wt_files:
        label = info["label"]
        if label in SEVERITY_ORDER:
            class_files[label].append((filepath, info))

    # 检查是否有足够类型覆盖
    present_labels = set(class_files.keys())
    missing_labels = set(SEVERITY_ORDER) - present_labels
    if missing_labels:
        print(f"  [WARN] 缺少故障类型: {missing_labels}")

    # 每类最多取 3 个文件（同一转速优先）
    # 选择 40Hz 转速作为基准（中等转速，典型工况）
    TARGET_SPEED = 40.0

    degradation_data = []
    for severity_idx, label in enumerate(SEVERITY_ORDER):
        if label not in class_files:
            # 缺失类型：用插值或跳过
            print(f"  [WARN] {label} 类型无样本，跳过")
            continue

        files_for_label = class_files[label]
        # 优先选择 40Hz 转速文件
        target_files = []
        other_files = []
        for filepath, info in files_for_label:
            parts = filepath.name.replace(".npy", "").split("-")
            main_parts = parts[0].split("_")
            try:
                rot_freq = float(main_parts[-1])
            except ValueError:
                rot_freq = 30.0
            if rot_freq == TARGET_SPEED:
                target_files.append((filepath, info, rot_freq))
            else:
                other_files.append((filepath, info, rot_freq))

        # 最多取 3 个文件
        selected = target_files[:3]
        if len(selected) < 3:
            remaining = 3 - len(selected)
            selected.extend(other_files[:remaining])

        if not selected:
            continue

        print(f"  分析 {label} (严重度 {severity_idx}): {len(selected)} 个样本...")
        health_scores = []
        for filepath, info, rot_freq in selected:
            signal = load_npy(filepath)
            try:
                engine = DiagnosisEngine(
                    strategy=DiagnosisStrategy.EXPERT,
                    gear_method=GearMethod.ADVANCED,
                    denoise_method=DenoiseMethod.NONE,
                    gear_teeth=WTGEARBOX_GEAR,
                )
                result = engine.analyze_comprehensive(
                    signal, SAMPLE_RATE, rot_freq=rot_freq,
                )
                hs = result.get("health_score", 100)
            except Exception as e:
                print(f"    [ERR] {filepath.name}: {e}")
                hs = 100  # 分析失败默认为健康
            health_scores.append(hs)

        mean_hs = float(np.mean(health_scores))
        std_hs = float(np.std(health_scores)) if len(health_scores) > 1 else 0.0

        degradation_data.append({
            "severity_idx": severity_idx,
            "label": label,
            "health_scores": health_scores,
            "mean_hs": mean_hs,
            "std_hs": std_hs,
            "n_samples": len(health_scores),
        })

    # 检查单调性方向：严重度增加 → 健康度应下降
    # 如果不是严格单调下降，记录但不中断
    for i in range(1, len(degradation_data)):
        prev_hs = degradation_data[i - 1]["mean_hs"]
        curr_hs = degradation_data[i]["mean_hs"]
        if curr_hs > prev_hs:
            print(f"  [WARN] 非单调: {degradation_data[i-1]['label']}={prev_hs:.1f} → "
                  f"{degradation_data[i]['label']}={curr_hs:.1f} (健康度反而上升)")

    return degradation_data


# ═══════════════════════════════════════════════════════════
# Step 2: PHM 指标计算
# ═══════════════════════════════════════════════════════════

def _compute_phm_metrics(degradation_data: List[Dict]) -> Dict[str, float]:
    """
    在伪退化序列上计算 PHM 趋势指标。

    - Monotonicity: HI 序列单调性 (目标 ≥ 0.85)
    - Trendability: HI 与时间(严重度等级)的 Pearson |r| (目标 ≥ 0.90)
    - Prognosability: 终端分散度指标 (目标 ≥ 0.70)
    - HI Robustness: HI 对随机波动的鲁棒性
    """
    if len(degradation_data) < 3:
        print("  [WARN] 退化序列长度不足 (<3)，PHM 指标不可靠")

    # 提取 HI 序列（平均健康度）和时间点（严重度索引）
    hi_series = [d["mean_hs"] for d in degradation_data]
    time_points = [float(d["severity_idx"]) for d in degradation_data]

    # 收集各类别的全部健康度用于 Prognosability
    # start_values: healthy 类别的全部 HS
    # end_values: 最严重类别的全部 HS
    start_values = []
    end_values = []
    for d in degradation_data:
        if d["label"] == SEVERITY_ORDER[0]:  # healthy
            start_values = d["health_scores"]
        if d["label"] == SEVERITY_ORDER[-1]:  # break
            end_values = d["health_scores"]

    # 如果没有 start/end 对应类别，用第一个和最后一个
    if not start_values and degradation_data:
        start_values = degradation_data[0]["health_scores"]
    if not end_values and degradation_data:
        end_values = degradation_data[-1]["health_scores"]

    # Prognosability 需要 start 和 end 对齐
    # 如果长度不一致，截断到较短的长度
    min_len = min(len(start_values), len(end_values))
    if min_len > 0:
        start_aligned = start_values[:min_len]
        end_aligned = end_values[:min_len]
        prognosability = compute_prognosability(start_aligned, end_aligned)
    else:
        prognosability = 0.0

    monotonicity = compute_monotonicity(hi_series)
    trendability = compute_trendability(hi_series, time_points)

    # HI Robustness: 使用全部样本的健康度值
    all_hs = []
    for d in degradation_data:
        all_hs.extend(d["health_scores"])
    hi_robustness = compute_hi_robustness(all_hs, noise_std=5.0)

    # 补充计算: Spearman 秩相关（单调趋势的秩版本）
    from scipy import stats as sp_stats
    if len(hi_series) >= 3:
        spearman_r, spearman_p = sp_stats.spearmanr(hi_series, time_points)
    else:
        spearman_r, spearman_p = 0.0, 1.0

    # 补充计算: 线性回归斜率（每严重度等级的健康度下降量）
    if len(hi_series) >= 2:
        slope, intercept = np.polyfit(time_points, hi_series, 1)
    else:
        slope, intercept = 0.0, 0.0

    return {
        "monotonicity": round(monotonicity, 4),
        "trendability": round(trendability, 4),
        "prognosability": round(prognosability, 4),
        "hi_robustness": round(hi_robustness, 4),
        "spearman_r": round(float(spearman_r), 4),
        "spearman_p": round(float(spearman_p), 6),
        "linear_slope": round(float(slope), 2),
        "linear_intercept": round(float(intercept), 2),
        "hi_series": hi_series,
        "time_points": time_points,
        "n_severity_levels": len(degradation_data),
    }


# ═══════════════════════════════════════════════════════════
# Step 3: 扣分函数单调性验证
# ═══════════════════════════════════════════════════════════

def _validate_deduction_monotonicity() -> Dict:
    """
    验证 sigmoid_deduction / cascade_deduction 在特征值递增时单调递增。

    测试场景:
    1. sigmoid_deduction: value 从 0→30, threshold=5, max=15
    2. cascade_deduction (轴承峭度): thresholds=[5,8,12,20], deductions=[15,22,30,40]
    3. cascade_deduction (齿轮峭度): thresholds=[10,12,20], deductions=[15,25,40]
    4. multi_threshold_deduction: thresholds=[7,10,15], deductions=[5,10,15]
    5. 峰值因子 cascade: thresholds=[7,10,15], deductions=[5,10,15]
    """
    results = {}

    # ─── sigmoid 单调性 ───
    sig_values = np.linspace(0, 30, 61)
    sig_deductions = [sigmoid_deduction(v, threshold=5.0, max_deduction=15.0) for v in sig_values]
    # 检查单调递增
    sig_monotonic = all(
        sig_deductions[i] <= sig_deductions[i + 1] + 1e-10
        for i in range(len(sig_deductions) - 1)
    )
    results["sigmoid"] = {
        "values": list(sig_values),
        "deductions": sig_deductions,
        "monotonic": sig_monotonic,
        "max_deduction": max(sig_deductions),
        "min_deduction": min(sig_deductions),
    }

    # ─── 轴承峭度 cascade 单调性 ───
    kurt_bearing_values = np.linspace(0, 30, 61)
    kurt_bearing_deds = [
        cascade_deduction(v, [5, 8, 12, 20], [15, 22, 30, 40])
        for v in kurt_bearing_values
    ]
    kurt_bearing_mono = all(
        kurt_bearing_deds[i] <= kurt_bearing_deds[i + 1] + 1e-10
        for i in range(len(kurt_bearing_deds) - 1)
    )
    results["cascade_bearing_kurtosis"] = {
        "values": list(kurt_bearing_values),
        "deductions": kurt_bearing_deds,
        "monotonic": kurt_bearing_mono,
        "max_deduction": max(kurt_bearing_deds),
        "min_deduction": min(kurt_bearing_deds),
    }

    # ─── 齿轮峭度 cascade 单调性 ───
    kurt_gear_values = np.linspace(0, 30, 61)
    kurt_gear_deds = [
        cascade_deduction(v, [10, 12, 20], [15, 25, 40])
        for v in kurt_gear_values
    ]
    kurt_gear_mono = all(
        kurt_gear_deds[i] <= kurt_gear_deds[i + 1] + 1e-10
        for i in range(len(kurt_gear_deds) - 1)
    )
    results["cascade_gear_kurtosis"] = {
        "values": list(kurt_gear_values),
        "deductions": kurt_gear_deds,
        "monotonic": kurt_gear_mono,
        "max_deduction": max(kurt_gear_deds),
        "min_deduction": min(kurt_gear_deds),
    }

    # ─── 峰值因子 cascade 单调性 ───
    crest_values = np.linspace(0, 20, 41)
    crest_deds = [
        cascade_deduction(v, [7, 10, 15], [5, 10, 15])
        for v in crest_values
    ]
    crest_mono = all(
        crest_deds[i] <= crest_deds[i + 1] + 1e-10
        for i in range(len(crest_deds) - 1)
    )
    results["cascade_crest_factor"] = {
        "values": list(crest_values),
        "deductions": crest_deds,
        "monotonic": crest_mono,
        "max_deduction": max(crest_deds),
        "min_deduction": min(crest_deds),
    }

    # ─── 齿轮峰值因子 cascade 单调性 ───
    crest_gear_values = np.linspace(0, 20, 41)
    crest_gear_deds = [
        cascade_deduction(v, [12, 15], [10, 15])
        for v in crest_gear_values
    ]
    crest_gear_mono = all(
        crest_gear_deds[i] <= crest_gear_deds[i + 1] + 1e-10
        for i in range(len(crest_gear_deds) - 1)
    )
    results["cascade_gear_crest_factor"] = {
        "values": list(crest_gear_values),
        "deductions": crest_gear_deds,
        "monotonic": crest_gear_mono,
        "max_deduction": max(crest_gear_deds),
        "min_deduction": min(crest_gear_deds),
    }

    # ─── 综合判定 ───
    all_monotonic = all(r["monotonic"] for r in results.values())
    results["summary"] = {
        "all_monotonic": all_monotonic,
        "n_tests": len(results) - 1,  # 排除 summary 本身
        "n_passed": sum(1 for k, r in results.items() if k != "summary" and r["monotonic"]),
    }

    return results


# ═══════════════════════════════════════════════════════════
# Step 4: 图表生成
# ═══════════════════════════════════════════════════════════

def _save_trajectory_plot(degradation_data: List[Dict], trend_dir: Path):
    """
    绘制健康度轨迹曲线:
    - X轴: 严重度等级 (0=healthy, 1=wear, 2=crack, 3=missing, 4=break)
    - Y轴: 平均健康度 ± 标准差
    - 叠加线性回归趋势线
    """
    if not degradation_data:
        return

    labels = [d["label"] for d in degradation_data]
    severity_indices = [d["severity_idx"] for d in degradation_data]
    mean_hs = [d["mean_hs"] for d in degradation_data]
    std_hs = [d["std_hs"] for d in degradation_data]

    fig, ax = plt.subplots(figsize=(10, 6))

    # 健康度轨迹 ± 标准差阴影
    ax.errorbar(
        severity_indices, mean_hs, yerr=std_hs,
        marker="o", markersize=8, capsize=4,
        linewidth=2, color="#2196F3",
        label="健康度轨迹 (mean ± std)",
    )

    # 填充标准差区间
    upper = [m + s for m, s in zip(mean_hs, std_hs)]
    lower = [m - s for m, s in zip(mean_hs, std_hs)]
    ax.fill_between(severity_indices, lower, upper, alpha=0.2, color="#2196F3")

    # 线性回归趋势线
    if len(severity_indices) >= 2:
        slope, intercept = np.polyfit(severity_indices, mean_hs, 1)
        trend_x = np.linspace(min(severity_indices), max(severity_indices), 50)
        trend_y = slope * trend_x + intercept
        ax.plot(trend_x, trend_y, "--", color="#FF5722", linewidth=1.5,
                label=f"线性趋势 (slope={slope:.1f})")

    # 健康阈值线
    ax.axhline(y=85, color="#4CAF50", linestyle=":", alpha=0.6, label="健康阈值 (85)")
    ax.axhline(y=60, color="#FFC107", linestyle=":", alpha=0.6, label="警告阈值 (60)")

    # X轴标签
    ax.set_xticks(severity_indices)
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_xlabel("故障严重度等级")
    ax.set_ylabel("健康度评分")
    ax.set_title("WTgearbox 伪退化序列 — 健康度轨迹")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(alpha=0.3)
    ax.set_ylim([0, 105])

    # 在每个点旁标注数值
    for i, (xi, yi) in enumerate(zip(severity_indices, mean_hs)):
        ax.annotate(f"{yi:.0f}", (xi, yi), textcoords="offset points",
                    xytext=(0, 12), ha="center", fontsize=9, color="#1565C0")

    plt.tight_layout()
    fig.savefig(trend_dir / "hi_trajectory.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  图表已保存: {trend_dir / 'hi_trajectory.png'}")


def _save_deduction_monotonicity_plot(deduction_results: Dict, trend_dir: Path):
    """
    绘制扣分函数单调性验证图:
    多个子图展示各 sigmoid/cascade 函数的连续扣分曲线，
    确认特征值递增时扣分单调递增（无跳变/回退）。
    """
    test_keys = [k for k in deduction_results if k != "summary"]
    n_tests = len(test_keys)
    if n_tests == 0:
        return

    # 排列子图
    n_cols = min(3, n_tests)
    n_rows = (n_tests + n_cols - 1) // n_cols

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(5 * n_cols, 4 * n_rows))
    if n_tests == 1:
        axes = np.array([axes])
    axes_flat = axes.flatten()

    for idx, key in enumerate(test_keys):
        ax = axes_flat[idx]
        data = deduction_results[key]
        values = data["values"]
        deductions = data["deductions"]
        monotonic = data["monotonic"]

        color = "#4CAF50" if monotonic else "#F44336"
        status_text = "PASS ✓ 单调递增" if monotonic else "FAIL ✗ 非单调"

        ax.plot(values, deductions, linewidth=2, color=color)
        ax.set_title(f"{key}\n{status_text}", fontsize=10, color=color)
        ax.set_xlabel("特征值")
        ax.set_ylabel("扣分值")
        ax.grid(alpha=0.3)

        # 标注关键阈值
        if key == "cascade_bearing_kurtosis":
            thresholds = [5, 8, 12, 20]
        elif key == "cascade_gear_kurtosis":
            thresholds = [10, 12, 20]
        elif key == "cascade_crest_factor":
            thresholds = [7, 10, 15]
        elif key == "cascade_gear_crest_factor":
            thresholds = [12, 15]
        elif key == "sigmoid":
            thresholds = [5]
        else:
            thresholds = []

        for th in thresholds:
            ax.axvline(x=th, color="#9E9E9E", linestyle="--", alpha=0.5)
            ax.annotate(f"θ={th}", (th, ax.get_ylim()[1] * 0.95),
                        fontsize=8, color="#757575", ha="center")

    # 隐藏空白子图
    for idx in range(n_tests, len(axes_flat)):
        axes_flat[idx].set_visible(False)

    # 添加总结文字
    summary = deduction_results.get("summary", {})
    all_mono = summary.get("all_monotonic", False)
    n_passed = summary.get("n_passed", 0)
    n_tests_total = summary.get("n_tests", 0)
    overall_text = f"总结: {n_passed}/{n_tests_total} 通过" + (
        " — 全部单调 ✓" if all_mono else " — 存在非单调 ✗"
    )
    fig.suptitle(f"扣分函数单调性验证\n{overall_text}", fontsize=12, y=1.02)

    plt.tight_layout()
    fig.savefig(trend_dir / "deduction_monotonicity.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  图表已保存: {trend_dir / 'deduction_monotonicity.png'}")


# ═══════════════════════════════════════════════════════════
# 报告生成
# ═══════════════════════════════════════════════════════════

def _generate_report(
    degradation_data: List[Dict],
    phm_metrics: Dict[str, float],
    deduction_results: Dict,
) -> str:
    """生成健康度趋势与预后性评价报告 (Markdown)"""
    lines = [
        "# 健康度趋势与预后性评价报告",
        "",
        "> 数据集: WTgearbox 行星齿轮箱 (恒速 40Hz 基准)",
        "> 伪退化序列: healthy → wear → crack → missing → break",
        "> 评价维度: Monotonicity | Trendability | Prognosability | HI Robustness | 扣分单调性",
        "",
        "## 1. 伪退化序列",
        "",
        "### 1.1 严重度排序",
        "",
        "| 严重度 | 故障类型 | 说明 |",
        "|--------|----------|------|",
        "| 0 | healthy (He) | 健康 |",
        "| 1 | wear (We) | 磨损 — 表面损伤渐进 |",
        "| 2 | crack (Rc) | 齿根裂纹 — 局部缺陷 |",
        "| 3 | missing (Mi) | 缺齿 — 中度故障 |",
        "| 4 | break (Br) | 断齿 — 严重故障 |",
        "",
        "### 1.2 各等级健康度",
        "",
        "| 严重度 | 故障类型 | 样本数 | 平均健康度 | 标准差 |",
        "|--------|----------|--------|-----------|--------|",
    ]

    for d in degradation_data:
        lines.append(
            f"| {d['severity_idx']} | {d['label']} | {d['n_samples']} "
            f"| {d['mean_hs']:.1f} | {d['std_hs']:.1f} |"
        )

    # ═══════ PHM 指标 ═══════
    lines.extend([
        "",
        "## 2. PHM 趋势指标",
        "",
        "| 指标 | 值 | 目标 | 达标 | 说明 |",
        "|------|-----|------|------|------|",
    ])

    mono = phm_metrics["monotonicity"]
    trend = phm_metrics["trendability"]
    progn = phm_metrics["prognosability"]
    robust = phm_metrics["hi_robustness"]
    spear_r = phm_metrics["spearman_r"]
    spear_p = phm_metrics["spearman_p"]
    slope = phm_metrics["linear_slope"]

    mono_pass = "✓" if mono >= TARGET_MONOTONICITY else "✗"
    trend_pass = "✓" if trend >= TARGET_TRENDABILITY else "✗"
    progn_pass = "✓" if progn >= TARGET_PROGNOSABILITY else "✗"

    lines.append(
        f"| Monotonicity | {mono:.4f} | ≥ {TARGET_MONOTONICITY} | {mono_pass} "
        f"| HI 序列单调性（方向一致性） |"
    )
    lines.append(
        f"| Trendability | {trend:.4f} | |r| ≥ {TARGET_TRENDABILITY} | {trend_pass} "
        f"| HI 与严重度等级的 Pearson |r| |"
    )
    lines.append(
        f"| Prognosability | {progn:.4f} | ≥ {TARGET_PROGNOSABILITY} | {progn_pass} "
        f"| 终端分散度（可预测性） |"
    )
    lines.append(
        f"| HI Robustness | {robust:.4f} | — | — "
        f"| HI 对随机波动的鲁棒性 |"
    )
    lines.append(
        f"| Spearman ρ | {spear_r:.4f} | — | — "
        f"| 秩单调相关系数 (p={spear_p:.4f}) |"
    )
    lines.append(
        f"| 线性斜率 | {slope:.2f} | — | — "
        f"| 每严重度等级的健康度下降量 |"
    )

    # ═══════ 扣分单调性 ═══════
    lines.extend([
        "",
        "## 3. 扣分函数单调性验证",
        "",
        "验证 sigmoid_deduction / cascade_deduction 在特征值递增时单调递增，"
        "确保健康度不会因特征恶化而意外上升。",
        "",
    ])

    summary = deduction_results.get("summary", {})
    all_mono = summary.get("all_monotonic", False)
    n_passed = summary.get("n_passed", 0)
    n_total = summary.get("n_tests", 0)

    lines.append(f"**结果: {n_passed}/{n_total} 测试通过** — "
                 f"{'全部单调 ✓' if all_mono else '存在非单调 ✗'}")
    lines.append("")
    lines.append("| 测试项 | 单调性 | 最大扣分 | 最小扣分 |")
    lines.append("|--------|--------|----------|----------|")

    for key in deduction_results:
        if key == "summary":
            continue
        data = deduction_results[key]
        mono_text = "✓ 单调" if data["monotonic"] else "✗ 非单调"
        lines.append(
            f"| {key} | {mono_text} | {data['max_deduction']:.2f} | {data['min_deduction']:.4f} |"
        )

    # ═══════ 结论与建议 ═══════
    lines.extend([
        "",
        "## 4. 结论与建议",
        "",
    ])

    if mono >= TARGET_MONOTONICITY:
        lines.append("- **Monotonicity 达标**: 健康度随故障严重度单调下降，适合趋势监控")
    else:
        lines.append(f"- **Monotonicity 未达标** ({mono:.4f} < {TARGET_MONOTONICITY}): "
                      "建议优化扣分权重或增加门控条件")

    if trend >= TARGET_TRENDABILITY:
        lines.append("- **Trendability 达标**: HI 与退化等级强相关，线性趋势明显")
    else:
        lines.append(f"- **Trendability 未达标** ({trend:.4f} < {TARGET_TRENDABILITY}): "
                      "建议调整扣分阈值或增加特征维度")

    if progn >= TARGET_PROGNOSABILITY:
        lines.append("- **Prognosability 达标**: 终端分散度低，预后预测可靠")
    else:
        lines.append(f"- **Prognosability 未达标** ({progn:.4f} < {TARGET_PROGNOSABILITY}): "
                      "建议增加同工况样本数以降低终端分散")

    if all_mono:
        lines.append("- **扣分函数全部单调**: sigmoid/cascade 连续扣分无跳变/回退，"
                      "健康度评分在特征恶化时稳定下降")
    else:
        lines.append("- **扣分函数存在非单调**: 需检查对应阈值/斜率参数")

    # 趋势适用性建议
    lines.extend([
        "",
        "### 4.1 趋势监控适用性判定",
        "",
    ])

    if mono >= TARGET_MONOTONICITY and trend >= TARGET_TRENDABILITY:
        lines.append("**判定: 适合趋势监控** — HI 指标满足单调性和趋势性要求，"
                      "可用于在线健康度退化趋势跟踪和预警阈值设定。")
    elif mono >= 0.6 and trend >= 0.7:
        lines.append("**判定: 有限适用** — HI 趋势性尚可但不够稳定，"
                      "建议结合多指标融合或加权平滑后使用。")
    else:
        lines.append("**判定: 不适合趋势监控** — HI 单调性/趋势性不足，"
                      "仅适合单点故障检测，不建议用于退化预测。")

    # 预后预测适用性
    if progn >= TARGET_PROGNOSABILITY:
        lines.append("**判定: 适合预后预测** — 终端分散度低，RUL 预估可行。")
    else:
        lines.append("**判定: 预后预测需谨慎** — 终端分散度较高，"
                      "RUL 预估不确定性大，建议增加历史数据基线。")

    lines.extend([
        "",
        "### 4.2 场景推荐",
        "",
        "| 场景 | 适用性 | 推荐做法 |",
        "|------|--------|---------|",
        "| 在线趋势监控 | 单调性+趋势性 | 健康度滑动平均 + 阈值预警 |",
        "| RUL 预测 | 预后性+趋势性 | 双参数指数退化模型 |",
        "| 单点故障检测 | 健康阈值 < 85 | 健康度二分类 + 严重度标签 |",
        "| 定期巡检 | 全指标 | 扣分明细分析 + 维护建议 |",
        "",
    ])

    return "\n".join(lines)