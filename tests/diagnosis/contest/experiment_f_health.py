"""
实验F：健康度退化轨迹评价

大创答辩专用 — 生成退化轨迹折线图、PHM趋势性指标汇总表格、
健康度阈值标注和Markdown退化趋势报告。

用法:
    cd /d/code/CNN/cloud
    . venv/Scripts/activate
    python -m tests.diagnosis.contest.main

    # 或单独运行
    python tests/diagnosis/contest/experiment_f_health.py
"""
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List

import numpy as np

# ── 项目路径 ──────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "diagnosis"))

# ── 答辩风格与配置 ────────────────────────────────────────────
from contest.style import apply_contest_style, COLORS, FIGURE_SIZE, FIGURE_DPI, make_conclusion_title
from contest.config import (
    OUTPUT_DIR, EXP_DIRS, WTGEARBOX_DIR, WTGEARBOX_GEAR,
    SAMPLE_RATE, MAX_SAMPLES, MAX_PER_CLASS_WTGEARBOX,
    LABEL_CN, GEAR_LABELS,
)

# ── 诊断引擎 ──────────────────────────────────────────────────
from app.services.diagnosis import (
    DiagnosisEngine, DiagnosisStrategy, GearMethod, DenoiseMethod,
)

# ── PHM 指标工具 ──────────────────────────────────────────────
from evaluation.utils import (
    load_npy, compute_monotonicity, compute_trendability,
    compute_prognosability, compute_hi_robustness,
)

import matplotlib.pyplot as plt
import matplotlib as mpl

# ── 常量 ──────────────────────────────────────────────────────

# 伪退化序列：按故障严重度排序
SEVERITY_ORDER = ["healthy", "wear", "crack", "missing", "break"]

# PHM 指标目标值
TARGET_MONOTONICITY = 0.85
TARGET_TRENDABILITY = 0.90
TARGET_PROGNOSABILITY = 0.70

# 健康度阈值线
HEALTH_LINE_GREEN = 85   # 健康 — 绿色虚线
HEALTH_LINE_YELLOW = 60  # 预警 — 黄色虚线
HEALTH_LINE_RED = 40     # 故障 — 红色虚线

# 目标转速（优先选40Hz文件）
TARGET_SPEED = 40.0

# 退化轨迹颜色：healthy=绿色，故障线用红色系渐变
TRAJECTORY_COLORS = {
    "healthy":  COLORS["healthy"],   # "#2ECC71" 绿色
    "wear":     "#F39C12",           # 橙色 — 轻度故障
    "crack":    "#E67E22",           # 深橙色 — 中度故障
    "missing":  "#E74C3C",           # 红色 — 较重故障
    "break":    "#C0392B",           # 深红色 — 严重故障
}

# 阈值线颜色
THRESHOLD_COLORS = {
    HEALTH_LINE_GREEN:  COLORS["normal_line"],   # 绿色虚线
    HEALTH_LINE_YELLOW: COLORS["warn_line"],      # 橙色虚线
    HEALTH_LINE_RED:    COLORS["fault_line"],     # 红色虚线
}

THRESHOLD_LABELS = {
    HEALTH_LINE_GREEN:  f"健康阈值 ({HEALTH_LINE_GREEN}分)",
    HEALTH_LINE_YELLOW: f"预警阈值 ({HEALTH_LINE_YELLOW}分)",
    HEALTH_LINE_RED:    f"故障阈值 ({HEALTH_LINE_RED}分)",
}

# 输出目录
EXP_DIR = EXP_DIRS["f_health"]


# ═══════════════════════════════════════════════════════════════
# 数据加载与分类
# ═══════════════════════════════════════════════════════════════

def classify_wtgearbox(filename: str) -> Dict:
    """WTgearbox 文件分类 — 提取故障标签和转速频率"""
    name = filename.replace(".npy", "")
    parts = name.split("-")
    main_part = parts[0]            # e.g. "Rc_R1_40"
    channel_part = parts[1] if len(parts) > 1 else "c1"

    fault_parts = main_part.split("_")
    category = fault_parts[0]       # He/Br/Mi/Rc/We

    mapping = {"He": "healthy", "Br": "break", "Mi": "missing", "Rc": "crack", "We": "wear"}

    # 提取转速频率值 (Hz)
    try:
        rot_freq = float(fault_parts[-1])
    except ValueError:
        rot_freq = 30.0  # 默认值

    return {
        "label": mapping.get(category, "unknown"),
        "fault": mapping.get(category),
        "channel": channel_part,
        "rot_freq": rot_freq,
    }


def get_wtgearbox_files() -> List:
    """获取 WTgearbox 数据集文件列表（仅 c1 通道，优先40Hz）"""
    if not WTGEARBOX_DIR.exists():
        print("[WARN] WTgearbox 数据集路径不存在")
        return []

    files = []
    for f in sorted(WTGEARBOX_DIR.glob("*.npy")):
        # 仅选 c1 通道
        if not f.name.endswith("-c1.npy"):
            continue
        info = classify_wtgearbox(f.name)
        if info["label"] != "unknown" and info["label"] in SEVERITY_ORDER:
            files.append((f, info))
    return files


def select_files_per_class(files, max_per_class=MAX_PER_CLASS_WTGEARBOX):
    """
    每类最多取 max_per_class 个文件，优先选 40Hz 转速。

    返回: dict[label] = [(filepath, info, rot_freq), ...]
    """
    class_files = defaultdict(list)

    # 先按 label 分组
    for filepath, info in files:
        label = info["label"]
        rot_freq = info.get("rot_freq", 30.0)
        class_files[label].append((filepath, info, rot_freq))

    selected = {}
    for label in SEVERITY_ORDER:
        if label not in class_files:
            continue

        # 优先选 40Hz 文件
        target_speed_files = [f for f in class_files[label] if f[2] == TARGET_SPEED]
        other_files = [f for f in class_files[label] if f[2] != TARGET_SPEED]

        chosen = target_speed_files[:max_per_class]
        if len(chosen) < max_per_class:
            remaining = max_per_class - len(chosen)
            chosen.extend(other_files[:remaining])

        selected[label] = chosen

    return selected


# ═══════════════════════════════════════════════════════════════
# 退化序列构造
# ═══════════════════════════════════════════════════════════════

def construct_degradation_sequence(selected_files: Dict) -> List[Dict]:
    """
    对每个严重度等级的文件运行综合诊断，获取健康度分数，
    构成退化序列。

    严重度排序: healthy(0) → wear(1) → crack(2) → missing(3) → break(4)
    """
    degradation_data = []

    for severity_idx, label in enumerate(SEVERITY_ORDER):
        if label not in selected_files:
            print(f"  [WARN] {label} 类型无样本，跳过")
            continue

        files_for_label = selected_files[label]
        print(f"  分析 {label} ({LABEL_CN.get(label, label)}, "
              f"严重度等级 {severity_idx}): {len(files_for_label)} 个样本...")

        health_scores = []
        for filepath, info, rot_freq in files_for_label:
            signal = load_npy(filepath, max_samples=MAX_SAMPLES)
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
            print(f"    {filepath.name}: rot_freq={rot_freq}Hz, "
                  f"health_score={hs}")

        mean_hs = float(np.mean(health_scores))
        std_hs = float(np.std(health_scores)) if len(health_scores) > 1 else 0.0

        degradation_data.append({
            "severity_idx": severity_idx,
            "label": label,
            "label_cn": LABEL_CN.get(label, label),
            "health_scores": health_scores,
            "mean_hs": mean_hs,
            "std_hs": std_hs,
            "n_samples": len(health_scores),
        })

    # 检查单调性方向：严重度增加 → 健康度应下降
    for i in range(1, len(degradation_data)):
        prev_hs = degradation_data[i - 1]["mean_hs"]
        curr_hs = degradation_data[i]["mean_hs"]
        if curr_hs > prev_hs:
            print(f"  [WARN] 非单调: {degradation_data[i-1]['label']}="
                  f"{prev_hs:.1f} → {degradation_data[i]['label']}="
                  f"{curr_hs:.1f} (健康度反而上升)")

    return degradation_data


# ═══════════════════════════════════════════════════════════════
# PHM 指标计算
# ═══════════════════════════════════════════════════════════════

def compute_phm_metrics(degradation_data: List[Dict]) -> Dict[str, float]:
    """
    在伪退化序列上计算 PHM 趋势指标。

    - Monotonicity: HI 序列单调性 (目标 ≥ 0.85)
    - Trendability: HI 与时间的 Pearson |r| (目标 ≥ 0.90)
    - Prognosability: 终端分散度指标 (目标 ≥ 0.70)
    - HI Robustness: HI 对随机波动的鲁棒性
    """
    if len(degradation_data) < 3:
        print("  [WARN] 退化序列长度不足 (<3)，PHM 指标不可靠")

    # 提取 HI 序列（平均健康度）和时间点（严重度索引）
    hi_series = [d["mean_hs"] for d in degradation_data]
    time_points = [float(d["severity_idx"]) for d in degradation_data]

    # Prognosability: start=healthy, end=break
    start_values = []
    end_values = []
    for d in degradation_data:
        if d["label"] == SEVERITY_ORDER[0]:  # healthy
            start_values = d["health_scores"]
        if d["label"] == SEVERITY_ORDER[-1]:  # break
            end_values = d["health_scores"]

    # 兜底：若无对应类别，用第一个和最后一个
    if not start_values and degradation_data:
        start_values = degradation_data[0]["health_scores"]
    if not end_values and degradation_data:
        end_values = degradation_data[-1]["health_scores"]

    # 对齐长度
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

    # Spearman 秩相关
    from scipy import stats as sp_stats
    if len(hi_series) >= 3:
        spearman_r, spearman_p = sp_stats.spearmanr(hi_series, time_points)
    else:
        spearman_r, spearman_p = 0.0, 1.0

    # 线性回归斜率
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


# ═══════════════════════════════════════════════════════════════
# 退化轨迹图绘制
# ═══════════════════════════════════════════════════════════════

def plot_degradation_trajectory(degradation_data: List[Dict],
                                phm_metrics: Dict) -> Path:
    """
    绘制退化轨迹折线图:
    - X轴: 严重度等级 (0=healthy, 1=wear, 2=crack, 3=missing, 4=break)
    - Y轴: 健康度分数
    - 5条折线对应5种齿轮状态（颜色渐变）
    - 标注健康度阈值线（85/60/40分）
    - 标注预警点"距离故障发生仍有XX等级"
    - 中文标签，标题写结论
    """
    if not degradation_data:
        print("[WARN] 无退化数据，跳过绘图")
        return None

    apply_contest_style()

    # 提取绘图数据
    severity_indices = [d["severity_idx"] for d in degradation_data]
    mean_hs = [d["mean_hs"] for d in degradation_data]
    std_hs = [d["std_hs"] for d in degradation_data]
    labels_cn = [d["label_cn"] for d in degradation_data]

    fig, ax = plt.subplots(figsize=FIGURE_SIZE)

    # ── 1. 阈值线（先画，在最底层） ──────────────────────────
    for threshold_val, color in THRESHOLD_COLORS.items():
        ax.axhline(
            y=threshold_val, color=color, linestyle="--",
            linewidth=1.8, alpha=0.7,
            label=THRESHOLD_LABELS[threshold_val],
        )

    # ── 2. 退化轨迹折线（逐段绘制，颜色渐变） ───────────────
    # 每个段（相邻两点）独立绘制，颜色由终点决定
    for i in range(len(degradation_data)):
        label = degradation_data[i]["label"]
        color = TRAJECTORY_COLORS[label]
        xi = severity_indices[i]
        yi = mean_hs[i]
        si = std_hs[i]

        # 绘制当前点（带误差棒）
        ax.errorbar(
            xi, yi, yerr=si if si > 0 else None,
            marker="o", markersize=10, capsize=5,
            linewidth=0,  # 不连线，只画点
            color=color, zorder=5,
            label=f"{labels_cn[i]} ({yi:.0f}分)",
        )

    # 连线：逐段绘制（起点颜色 → 终点颜色渐变）
    for i in range(len(degradation_data) - 1):
        x_pair = [severity_indices[i], severity_indices[i + 1]]
        y_pair = [mean_hs[i], mean_hs[i + 1]]
        # 终点颜色
        end_label = degradation_data[i + 1]["label"]
        color = TRAJECTORY_COLORS[end_label]
        ax.plot(
            x_pair, y_pair, linewidth=2.5, color=color,
            alpha=0.85, zorder=3,
        )

    # ── 3. 标准差阴影区间 ────────────────────────────────────
    upper = [m + s for m, s in zip(mean_hs, std_hs)]
    lower = [m - s for m, s in zip(mean_hs, std_hs)]
    ax.fill_between(
        severity_indices, lower, upper,
        alpha=0.15, color="#BDC3C7", zorder=1,
    )

    # ── 4. 线性趋势线 ────────────────────────────────────────
    slope = phm_metrics.get("linear_slope", 0)
    intercept = phm_metrics.get("linear_intercept", 0)
    if len(severity_indices) >= 2:
        trend_x = np.linspace(
            min(severity_indices), max(severity_indices), 50
        )
        trend_y = slope * trend_x + intercept
        ax.plot(
            trend_x, trend_y, "--", color="#FF5722",
            linewidth=1.5, alpha=0.6, zorder=2,
            label=f"线性趋势 (斜率={slope:.1f})",
        )

    # ── 5. 预警点标注 ────────────────────────────────────────
    # 找到健康度首次低于 85 分的等级
    warn_level = None
    for d in degradation_data:
        if d["mean_hs"] < HEALTH_LINE_GREEN:
            warn_level = d["severity_idx"]
            break

    if warn_level is not None and warn_level > 0:
        # 距离最严重等级还有几级
        max_severity = max(severity_indices)
        remaining = max_severity - warn_level
        ax.annotate(
            f"预警点：距离严重故障仍有 {remaining} 个等级",
            xy=(warn_level, HEALTH_LINE_GREEN),
            xytext=(warn_level + 0.3, HEALTH_LINE_GREEN + 8),
            fontsize=11, color="#F39C12", fontweight="bold",
            arrowprops=dict(arrowstyle="->", color="#F39C12", lw=1.5),
            zorder=10,
        )

    # ── 6. 每个数据点旁标注数值 ──────────────────────────────
    for xi, yi, label in zip(severity_indices, mean_hs, degradation_data):
        color = TRAJECTORY_COLORS[label["label"]]
        ax.annotate(
            f"{yi:.0f}", (xi, yi),
            textcoords="offset points", xytext=(0, 14),
            ha="center", fontsize=11, color=color,
            fontweight="bold", zorder=10,
        )

    # ── 7. 轴标签与标题 ──────────────────────────────────────
    # X轴: 中文严重度等级
    ax.set_xticks(severity_indices)
    ax.set_xticklabels(labels_cn, fontsize=13)
    ax.set_xlabel("故障严重度等级", fontsize=14)
    ax.set_ylabel("健康度评分", fontsize=14)

    # 标题：写结论
    mono = phm_metrics["monotonicity"]
    trend = phm_metrics["trendability"]

    if mono >= TARGET_MONOTONICITY and trend >= TARGET_TRENDABILITY:
        title = make_conclusion_title(
            "健康度退化轨迹单调性",
            0,  # baseline 用 0 表示无趋势
            mono,
            unit="",
        )
        title = (
            f"健康度随故障严重度单调退化（Monotonicity={mono:.2f}, "
            f"Trendability={trend:.2f}）"
        )
    else:
        title = (
            f"健康度退化轨迹评价（Monotonicity={mono:.2f}, "
            f"Trendability={trend:.2f}）"
        )

    ax.set_title(title, fontsize=16, fontweight="bold")

    # Y 轴范围
    ax.set_ylim([0, 105])
    ax.legend(loc="upper right", fontsize=10, framealpha=0.9)

    plt.tight_layout()

    # 保存
    output_path = EXP_DIR / "health_degradation_trajectory.png"
    fig.savefig(output_path, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  退化轨迹图已保存: {output_path}")
    return output_path


# ═══════════════════════════════════════════════════════════════
# Markdown 退化趋势报告
# ═══════════════════════════════════════════════════════════════

def generate_markdown_report(
    degradation_data: List[Dict],
    phm_metrics: Dict[str, float],
) -> str:
    """生成 Markdown 格式的退化趋势报告"""

    lines = [
        "# 实验F：健康度退化轨迹评价",
        "",
        "> 数据集: WTgearbox 行星齿轮箱 (恒速 40Hz 基准)",
        "> 退化序列: healthy → wear → crack → missing → break",
        "> 评价维度: Monotonicity | Trendability | Prognosability | HI Robustness",
        "",
        "## 1. 退化序列健康度",
        "",
        "| 严重度等级 | 故障类型 | 中文名 | 样本数 | 平均健康度 | 标准差 |",
        "|-----------|---------|--------|--------|-----------|--------|",
    ]

    for d in degradation_data:
        lines.append(
            f"| {d['severity_idx']} | {d['label']} | "
            f"{d['label_cn']} | {d['n_samples']} "
            f"| {d['mean_hs']:.1f} | {d['std_hs']:.1f} |"
        )

    # ═══════ PHM 指标汇总 ═══════
    lines.extend([
        "",
        "## 2. PHM 趋势性指标汇总",
        "",
        "| 指标 | 数值 | 目标 | 达标 | 说明 |",
        "|------|------|------|------|------|",
    ])

    mono = phm_metrics["monotonicity"]
    trend = phm_metrics["trendability"]
    progn = phm_metrics["prognosability"]
    robust = phm_metrics["hi_robustness"]
    spear_r = phm_metrics["spearman_r"]
    slope = phm_metrics["linear_slope"]

    mono_pass = "✓" if mono >= TARGET_MONOTONICITY else "✗"
    trend_pass = "✓" if trend >= TARGET_TRENDABILITY else "✗"
    progn_pass = "✓" if progn >= TARGET_PROGNOSABILITY else "✗"

    lines.append(
        f"| Monotonicity | {mono:.4f} | ≥ {TARGET_MONOTONICITY} "
        f"| {mono_pass} | HI 序列单调性（方向一致性） |"
    )
    lines.append(
        f"| Trendability | {trend:.4f} | ≥ {TARGET_TRENDABILITY} "
        f"| {trend_pass} | HI 与严重度等级的 Pearson |r| |"
    )
    lines.append(
        f"| Prognosability | {progn:.4f} | ≥ {TARGET_PROGNOSABILITY} "
        f"| {progn_pass} | 终端分散度（可预测性） |"
    )
    lines.append(
        f"| HI Robustness | {robust:.4f} | — | — "
        f"| HI 对随机波动的鲁棒性 |"
    )
    lines.append(
        f"| Spearman ρ | {spear_r:.4f} | — | — "
        f"| 秩单调相关系数 |"
    )
    lines.append(
        f"| 线性斜率 | {slope:.2f} | — | — "
        f"| 每严重度等级的健康度下降量 |"
    )

    # ═══════ 健康度阈值说明 ═══════
    lines.extend([
        "",
        "## 3. 健康度阈值分级",
        "",
        "| 阈值 | 含义 | 颜色 | 预警动作 |",
        "|------|------|------|---------|",
        f"| {HEALTH_LINE_GREEN} 分 | 健康状态 | 绿色 | 无需预警 |",
        f"| {HEALTH_LINE_YELLOW} 分 | 预警状态 | 黄色 | 加强巡检 |",
        f"| {HEALTH_LINE_RED} 分 | 故障状态 | 红色 | 立即停机检查 |",
    ])

    # ═══════ 预警距离 ═══════
    warn_level = None
    for d in degradation_data:
        if d["mean_hs"] < HEALTH_LINE_GREEN:
            warn_level = d["severity_idx"]
            break

    if warn_level is not None and warn_level > 0:
        max_severity = max(d["severity_idx"] for d in degradation_data)
        remaining = max_severity - warn_level
        lines.extend([
            "",
            "## 4. 预警点分析",
            "",
            f"- 首次低于健康阈值 ({HEALTH_LINE_GREEN}分) 的等级: "
            f"等级 {warn_level}",
            f"- **距离严重故障仍有 {remaining} 个等级**",
            f"- 预警距离提供 {remaining * abs(slope):.0f} 分的健康度缓冲区间",
        ])
    else:
        lines.extend([
            "",
            "## 4. 预警点分析",
            "",
            "- 所有等级的健康度均 ≥ 85分，未触发预警阈值",
            "- 建议检查诊断引擎参数或增加更多工况数据",
        ])

    # ═══════ 结论 ═══════
    lines.extend([
        "",
        "## 5. 结论",
        "",
    ])

    if mono >= TARGET_MONOTONICITY:
        lines.append(
            f"- **Monotonicity 达标** ({mono:.4f} ≥ {TARGET_MONOTONICITY}): "
            f"健康度随故障严重度单调退化，适合趋势监控"
        )
    else:
        lines.append(
            f"- **Monotonicity 未达标** ({mono:.4f} < {TARGET_MONOTONICITY}): "
            f"建议优化扣分权重或增加门控条件"
        )

    if trend >= TARGET_TRENDABILITY:
        lines.append(
            f"- **Trendability 达标** ({trend:.4f} ≥ {TARGET_TRENDABILITY}): "
            f"HI 与退化等级强相关，线性趋势明显"
        )
    else:
        lines.append(
            f"- **Trendability 未达标** ({trend:.4f} < {TARGET_TRENDABILITY}): "
            f"建议调整扣分阈值或增加特征维度"
        )

    if progn >= TARGET_PROGNOSABILITY:
        lines.append(
            f"- **Prognosability 达标** ({progn:.4f} ≥ {TARGET_PROGNOSABILITY}): "
            f"终端分散度低，预后预测可靠"
        )
    else:
        lines.append(
            f"- **Prognosability 未达标** ({progn:.4f} < {TARGET_PROGNOSABILITY}): "
            f"建议增加同工况样本数以降低终端分散"
        )

    # 趋势监控适用性
    if mono >= TARGET_MONOTONICITY and trend >= TARGET_TRENDABILITY:
        lines.append("")
        lines.append(
            "**综合判定: 适合趋势监控** — HI 指标满足单调性和趋势性要求，"
            "可用于在线健康度退化趋势跟踪和预警阈值设定。"
        )
    elif mono >= 0.6 and trend >= 0.7:
        lines.append("")
        lines.append(
            "**综合判定: 有限适用** — HI 趋势性尚可但不够稳定，"
            "建议结合多指标融合或加权平滑后使用。"
        )
    else:
        lines.append("")
        lines.append(
            "**综合判定: 不适合趋势监控** — HI 单调性/趋势性不足，"
            "仅适合单点故障检测，不建议用于退化预测。"
        )

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════

def run_experiment_f():
    """实验F：健康度退化轨迹评价 — 主入口"""

    print("\n" + "=" * 60)
    print("  【实验F】 健康度退化轨迹评价")
    print("=" * 60)

    # ── Step 1: 加载 WTgearbox 文件 ──────────────────────────
    print("\n  Step 1: 加载 WTgearbox 数据集")
    wt_files = get_wtgearbox_files()
    if not wt_files:
        print("[SKIP] WTgearbox 数据集不可用")
        return {}

    print(f"  共加载 {len(wt_files)} 个 c1 通道文件")
    selected_files = select_files_per_class(wt_files)
    for label, files in selected_files.items():
        print(f"    {label}: {len(files)} 个样本")

    # ── Step 2: 构造退化序列 ──────────────────────────────────
    print("\n  Step 2: 运行综合诊断，构造退化序列")
    degradation_data = construct_degradation_sequence(selected_files)
    if not degradation_data:
        print("[SKIP] 退化序列构造失败（样本不足）")
        return {}

    # 打印退化序列摘要
    print("\n  退化序列摘要:")
    for d in degradation_data:
        print(f"    等级{d['severity_idx']} ({d['label_cn']}): "
              f"均值={d['mean_hs']:.1f}, "
              f"标准差={d['std_hs']:.1f}, "
              f"样本数={d['n_samples']}")

    # ── Step 3: 计算 PHM 指标 ─────────────────────────────────
    print("\n  Step 3: 计算 PHM 趋势性指标")
    phm_metrics = compute_phm_metrics(degradation_data)

    mono = phm_metrics["monotonicity"]
    trend = phm_metrics["trendability"]
    progn = phm_metrics["prognosability"]
    robust = phm_metrics["hi_robustness"]

    print(f"    Monotonicity     = {mono:.4f}  (目标 ≥ {TARGET_MONOTONICITY})")
    print(f"    Trendability     = {trend:.4f}  (目标 ≥ {TARGET_TRENDABILITY})")
    print(f"    Prognosability   = {progn:.4f}  (目标 ≥ {TARGET_PROGNOSABILITY})")
    print(f"    HI Robustness    = {robust:.4f}")
    print(f"    Spearman ρ       = {phm_metrics['spearman_r']:.4f}")
    print(f"    线性斜率         = {phm_metrics['linear_slope']:.2f}")

    # ── Step 4: 绘制退化轨迹图 ────────────────────────────────
    print("\n  Step 4: 绘制退化轨迹图")
    plot_path = plot_degradation_trajectory(degradation_data, phm_metrics)

    # ── Step 5: 生成 Markdown 报告 ────────────────────────────
    print("\n  Step 5: 生成 Markdown 退化趋势报告")
    report = generate_markdown_report(degradation_data, phm_metrics)
    report_path = EXP_DIR / "health_degradation_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  报告已保存: {report_path}")

    # ── Step 6: PHM 指标表格单独保存 ──────────────────────────
    phm_table_path = EXP_DIR / "phm_metrics_table.md"
    with open(phm_table_path, "w", encoding="utf-8") as f:
        f.write(_generate_phm_table_only(phm_metrics))
    print(f"  PHM 指标表格已保存: {phm_table_path}")

    # ── 汇总 ──────────────────────────────────────────────────
    print("\n  实验F完成!")
    print(f"  输出目录: {EXP_DIR}")

    return {
        "degradation_data": degradation_data,
        "phm_metrics": phm_metrics,
        "plot_path": str(plot_path) if plot_path else None,
        "report_path": str(report_path),
        "phm_table_path": str(phm_table_path),
    }


def _generate_phm_table_only(phm_metrics: Dict) -> str:
    """单独生成 PHM 指标汇总表格（用于答辩PPT引用）"""
    mono = phm_metrics["monotonicity"]
    trend = phm_metrics["trendability"]
    progn = phm_metrics["prognosability"]
    robust = phm_metrics["hi_robustness"]

    mono_pass = "✓" if mono >= TARGET_MONOTONICITY else "✗"
    trend_pass = "✓" if trend >= TARGET_TRENDABILITY else "✗"
    progn_pass = "✓" if progn >= TARGET_PROGNOSABILITY else "✗"

    lines = [
        "# PHM 趋势性指标汇总",
        "",
        "| 指标 | 数值 | 目标 | 达标 | 说明 |",
        "|------|------|------|------|------|",
        f"| Monotonicity | {mono:.4f} | ≥ {TARGET_MONOTONICITY} "
        f"| {mono_pass} | HI 序列单调性 |",
        f"| Trendability | {trend:.4f} | ≥ {TARGET_TRENDABILITY} "
        f"| {trend_pass} | Pearson |r| |",
        f"| Prognosability | {progn:.4f} | ≥ {TARGET_PROGNOSABILITY} "
        f"| {progn_pass} | 终端分散度 |",
        f"| HI Robustness | {robust:.4f} | — | — | 随机波动鲁棒性 |",
    ]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 独立运行入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    apply_contest_style()
    result = run_experiment_f()
    if result:
        print("\n实验F结果摘要:")
        for key, val in result.items():
            if key not in ("degradation_data", "phm_metrics"):
                print(f"  {key}: {val}")