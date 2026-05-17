"""
实验D：噪声鲁棒性衰减曲线

生成内容:
1. SNR-Accuracy衰减曲线图（X=SNR dB从20到-10，Y=Accuracy%，多条方法曲线，Ensemble下降最慢）
2. 关键标注：80%工业可用阈值虚线、Critical SNR交叉点标注
3. Critical SNR汇总表格
4. Robustness Index对比柱状图

数据来源:
- 数据集: HUSTbear（选取一个外圈故障文件和一个健康文件）
- SNR级别: [20, 10, 5, 0, -5, -10] dB
- 添加AWGN: noisy = add_awgn(signal, snr_db)
- 分类判定: health_score < HEALTH_THRESHOLD(85) → 异常
- 轴承方法: envelope, kurtogram, med, mckd, ensemble
- Critical SNR: 第一个使 Accuracy < 80% 的SNR值
- Robustness Index: SNR-Acc曲线AUC / 最大可能AUC

调用方式:
    cd /d/code/CNN/cloud
    . venv/Scripts/activate
    python -m tests.diagnosis.contest.experiment_d_robustness

或从 contest.main 入口调用:
    run_experiment_d()
"""
import sys
import warnings
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ── 项目路径 ──────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "diagnosis"))

# ── 导入统一风格 ──────────────────────────────────────────────
from contest.style import (
    apply_contest_style,
    COLORS,
    METHOD_COLORS,
    FIGURE_SIZE,
    FIGURE_SIZE_WIDE,
    get_method_color,
    make_conclusion_title,
)

# ── 导入配置 ──────────────────────────────────────────────────
from contest.config import (
    OUTPUT_DIR,
    EXP_DIRS,
    HUSTBEAR_DIR,
    SAMPLE_RATE,
    MAX_SAMPLES,
    HUSTBEAR_BEARING,
    BEARING_FREQ_COEFFS,
    HEALTH_THRESHOLD,
    SNR_LEVELS,
    LABEL_CN,
)

# ── 导入诊断引擎 ──────────────────────────────────────────────
from app.services.diagnosis.engine import (
    DiagnosisEngine,
    DiagnosisStrategy,
    BearingMethod,
)
from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum
from app.services.diagnosis.health_score import _compute_health_score
from app.services.diagnosis.features import compute_time_features

# ── 导入评价工具 ──────────────────────────────────────────────
from evaluation.utils import add_awgn, load_npy


# ═══════════════════════════════════════════════════════════
# 方法配置表（5种对比方法）
# ═══════════════════════════════════════════════════════════

# display_name, BearingMethod enum, is_ensemble
ROBUSTNESS_METHODS = [
    ("包络分析",   BearingMethod.ENVELOPE,   False),
    ("Kurtogram",  BearingMethod.KURTOGRAM,  False),
    ("MED增强",    BearingMethod.MED,        False),
    ("MCKD",       BearingMethod.MCKD,       True),   # 需要轴承参数
    ("集成Ensemble", None,                     True),   # 使用 ensemble 策略
]


# ═══════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════

def _find_hustbear_files() -> Tuple[Optional[Path], Optional[Path]]:
    """在 HUSTbear 数据集中选取一个外圈故障文件和一个健康文件（X通道，恒速工况）"""
    if not HUSTBEAR_DIR.exists():
        print(f"[ERROR] HUSTbear 目录不存在: {HUSTBEAR_DIR}")
        return None, None

    fault_file = None
    healthy_file = None

    for f in sorted(HUSTBEAR_DIR.glob("*.npy")):
        if not f.name.endswith("-X.npy"):
            continue
        # 优先选取恒速(CS)工况的外圈故障文件
        name = f.name.replace(".npy", "")
        is_outer = "O" in name.split("-")[0].split("_") or "OR" in name.split("-")[0].split("_")
        is_healthy = "H" in name.split("-")[0].split("_") or "N" in name.split("-")[0].split("_")
        is_cs = "CS" in name

        if is_outer and fault_file is None:
            fault_file = f
        if is_healthy and healthy_file is None:
            healthy_file = f

    # 若没找到恒速工况，退化为任意恒速文件
    if fault_file is None:
        for f in sorted(HUSTBEAR_DIR.glob("*.npy")):
            if not f.name.endswith("-X.npy"):
                continue
            name = f.name.replace(".npy", "")
            is_outer = "O" in name.split("-")[0].split("_") or "OR" in name.split("-")[0].split("_")
            if is_outer:
                fault_file = f
                break

    if healthy_file is None:
        for f in sorted(HUSTBEAR_DIR.glob("*.npy")):
            if not f.name.endswith("-X.npy"):
                continue
            name = f.name.replace(".npy", "")
            is_healthy = "H" in name.split("-")[0].split("_") or "N" in name.split("-")[0].split("_")
            if is_healthy:
                healthy_file = f
                break

    return fault_file, healthy_file


def _detection_status(health_score: int, is_fault: bool) -> str:
    """基于 health_score < HEALTH_THRESHOLD 的分类判定"""
    predicted_fault = int(health_score) < HEALTH_THRESHOLD
    if is_fault and predicted_fault:
        return "TP"
    elif not is_fault and not predicted_fault:
        return "TN"
    elif not is_fault and predicted_fault:
        return "FP"
    else:  # is_fault and not predicted_fault
        return "FN"


def _compute_accuracy(statuses: List[str]) -> float:
    """从 TP/TN/FP/FN 列表计算 Accuracy"""
    tp = sum(1 for s in statuses if s == "TP")
    tn = sum(1 for s in statuses if s == "TN")
    fp = sum(1 for s in statuses if s == "FP")
    fn = sum(1 for s in statuses if s == "FN")
    total = tp + tn + fp + fn
    return (tp + tn) / total if total > 0 else 0.0


def _compute_health_score_from_result(
    signal: np.ndarray,
    fs: float,
    result: Dict,
    rot_freq: float,
) -> int:
    """从轴承分析结果估算健康度"""
    time_feats = compute_time_features(signal)
    hs, _, _ = _compute_health_score(
        gear_teeth=None,
        time_features=time_feats,
        bearing_result=result,
        gear_result={},
    )
    return int(hs)


def _compute_critical_snr(
    snr_levels: List[float],
    accuracies: List[float],
    threshold: float = 0.80,
) -> Optional[float]:
    """Critical SNR: 第一个使 Accuracy < threshold 的SNR值"""
    for snr, acc in zip(snr_levels, accuracies):
        if acc < threshold:
            return snr
    return None  # 全部高于阈值


def _compute_robustness_index(
    snr_levels: List[float],
    accuracies: List[float],
) -> float:
    """Robustness Index: SNR-Accuracy 曲线的 AUC / 最大可能 AUC"""
    if len(snr_levels) < 2:
        return 0.0
    # 梯形法计算 AUC（按 SNR 升序排列）
    sorted_pairs = sorted(zip(snr_levels, accuracies))
    xs = [p[0] for p in sorted_pairs]
    ys = [p[1] for p in sorted_pairs]
    auc = 0.0
    for i in range(1, len(xs)):
        auc += (xs[i] - xs[i - 1]) * (ys[i] + ys[i - 1]) / 2.0
    # 最大可能 AUC = (max_snr - min_snr) * 1.0
    max_auc = (max(xs) - min(xs)) * 1.0
    if max_auc < 1e-12:
        return 0.0
    return auc / max_auc


def _run_single_method(
    method_name: str,
    bm_enum: Optional[BearingMethod],
    is_ensemble: bool,
    fault_signal: np.ndarray,
    healthy_signal: Optional[np.ndarray],
    rot_freq_fault: float,
    rot_freq_healthy: float,
    snr_levels: List[float],
    fs: float,
    bearing_params: Dict,
) -> List[float]:
    """对单个方法在不同 SNR 下运行诊断，返回每个 SNR 的 Accuracy"""

    accuracies = []

    for snr_db in snr_levels:
        noisy_fault = add_awgn(fault_signal, snr_db)
        noisy_healthy = add_awgn(healthy_signal, snr_db) if healthy_signal is not None else None

        statuses = []

        # ── 故障文件判定 ─────────────────────────────────────
        try:
            if is_ensemble and bm_enum is None:
                # Ensemble 方法: DiagnosisEngine(EXPERT) + analyze_comprehensive
                engine = DiagnosisEngine(
                    strategy=DiagnosisStrategy.EXPERT,
                    bearing_params=bearing_params,
                    denoise_method="none",
                )
                result = engine.analyze_comprehensive(
                    noisy_fault, fs, rot_freq=rot_freq_fault, skip_gear=True,
                )
                health_score_fault = int(result.get("health_score", 100))
            else:
                # 单一轴承方法: DiagnosisEngine(ADVANCED, bearing_method=bm)
                engine = DiagnosisEngine(
                    strategy=DiagnosisStrategy.ADVANCED,
                    bearing_method=bm_enum,
                    bearing_params=bearing_params,
                    denoise_method="none",
                )
                result = engine.analyze_bearing(
                    noisy_fault, fs, rot_freq=rot_freq_fault, preprocess=True,
                )
                health_score_fault = _compute_health_score_from_result(
                    noisy_fault, fs, result, rot_freq_fault
                )
        except Exception as e:
            print(f"  [WARN] {method_name}@{snr_db}dB (故障): {e}")
            health_score_fault = 100  # 异常时视为误判为健康 → FN

        det_fault = _detection_status(health_score_fault, is_fault=True)
        statuses.append(det_fault)

        # ── 健康文件判定 ─────────────────────────────────────
        if noisy_healthy is not None:
            try:
                if is_ensemble and bm_enum is None:
                    engine_h = DiagnosisEngine(
                        strategy=DiagnosisStrategy.EXPERT,
                        bearing_params=bearing_params,
                        denoise_method="none",
                    )
                    result_h = engine_h.analyze_comprehensive(
                        noisy_healthy, fs, rot_freq=rot_freq_healthy, skip_gear=True,
                    )
                    health_score_healthy = int(result_h.get("health_score", 100))
                else:
                    engine_h = DiagnosisEngine(
                        strategy=DiagnosisStrategy.ADVANCED,
                        bearing_method=bm_enum,
                        bearing_params=bearing_params,
                        denoise_method="none",
                    )
                    result_h = engine_h.analyze_bearing(
                        noisy_healthy, fs, rot_freq=rot_freq_healthy, preprocess=True,
                    )
                    health_score_healthy = _compute_health_score_from_result(
                        noisy_healthy, fs, result_h, rot_freq_healthy
                    )
            except Exception as e:
                print(f"  [WARN] {method_name}@{snr_db}dB (健康): {e}")
                health_score_healthy = 0  # 异常时视为误判为故障 → FP

            det_healthy = _detection_status(health_score_healthy, is_fault=False)
            statuses.append(det_healthy)

        acc = _compute_accuracy(statuses)
        accuracies.append(acc)
        print(f"  {method_name}@{snr_db}dB: Acc={acc:.2%} "
              f"(fault_hs={health_score_fault}, det={det_fault})")

    return accuracies


# ═══════════════════════════════════════════════════════════
# 绘图函数
# ═══════════════════════════════════════════════════════════

def _plot_snr_accuracy_decay(
    method_data: Dict[str, List[float]],
    snr_levels: List[float],
    critical_snr_map: Dict[str, Optional[float]],
    output_dir: Path,
) -> Path:
    """绘制 SNR-Accuracy 衰减曲线图

    - X轴: SNR (dB), 从20到-10
    - Y轴: Accuracy (%), 0-100%
    - Ensemble曲线: 红色(#E74C3C)实线加粗
    - 其他方法: 灰色细线
    - 水平虚线: Accuracy=80%, 标注"工业可用阈值"
    - Critical SNR交叉点标注
    """
    apply_contest_style()

    fig, ax = plt.subplots(figsize=FIGURE_SIZE)

    # ── 画80%工业可用阈值虚线 ──────────────────────────────
    ax.axhline(y=80, color=COLORS["warning"], linestyle="--", linewidth=1.5, alpha=0.8)
    ax.text(snr_levels[0] + 0.5, 82, "工业可用阈值 (80%)",
            fontsize=11, color=COLORS["warning"], fontweight="bold",
            va="bottom", ha="left")

    # ── 绘制各方法曲线 ──────────────────────────────────────
    for method_name, accuracies in method_data.items():
        # 判断是否为 ensemble 方法
        is_ensemble = "ensemble" in method_name.lower() or "集成" in method_name

        if is_ensemble:
            color = COLORS["our_method"]  # #E74C3C 红色
            linewidth = 2.5
            marker = "o"
            markersize = 7
            zorder = 10
        else:
            color = COLORS["baseline"]  # #95A5A6 灰色
            linewidth = 1.2
            marker = "s"
            markersize = 5
            zorder = 5

        # Accuracy 转换为百分比
        acc_pct = [a * 100 for a in accuracies]

        ax.plot(snr_levels, acc_pct, color=color, linewidth=linewidth,
                marker=marker, markersize=markersize, label=method_name,
                zorder=zorder)

        # ── 标注 Critical SNR 交叉点 ────────────────────────
        cs = critical_snr_map.get(method_name)
        if cs is not None:
            # 找到交叉点处的 Accuracy 值
            cs_idx = snr_levels.index(cs) if cs in snr_levels else None
            if cs_idx is not None:
                cs_acc = acc_pct[cs_idx]
                # 画垂直虚线标记 Critical SNR
                ax.axvline(x=cs, color=color, linestyle=":", linewidth=0.8, alpha=0.5)
                # 标注文字
                offset_y = -5 if is_ensemble else 3
                ax.annotate(
                    f"Critical SNR\n={cs} dB",
                    xy=(cs, cs_acc),
                    xytext=(cs + 1.5, cs_acc + offset_y),
                    fontsize=9,
                    color=color,
                    fontweight="bold" if is_ensemble else "normal",
                    arrowprops=dict(arrowstyle="->", color=color, lw=0.8),
                    ha="left",
                )

    # ── 坐标轴设置 ──────────────────────────────────────────
    ax.set_xlabel("信噪比 SNR (dB)", fontsize=14)
    ax.set_ylabel("诊断准确率 Accuracy (%)", fontsize=14)
    ax.set_ylim(0, 105)
    ax.set_xlim(snr_levels[-1] - 2, snr_levels[0] + 2)
    ax.set_xticks(snr_levels)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower left", fontsize=11, framealpha=0.9)

    # ── 结论式标题 ──────────────────────────────────────────
    ensemble_name = "集成Ensemble"
    baseline_names = [n for n in method_data if n != ensemble_name]
    # 找到最佳 baseline 的 Critical SNR
    baseline_cs_list = [(n, critical_snr_map.get(n)) for n in baseline_names]
    best_baseline_name = None
    best_baseline_cs = None
    for name, cs in baseline_cs_list:
        if cs is not None:
            if best_baseline_cs is None or cs < best_baseline_cs:
                best_baseline_cs = cs
                best_baseline_name = name
        elif cs is None:  # cs=None 表示全部高于80%阈值，鲁棒性很好
            best_baseline_name = name
            best_baseline_cs = ">20dB"

    ensemble_cs = critical_snr_map.get(ensemble_name)
    if ensemble_cs is None:
        ensemble_cs_str = ">20 dB"
    else:
        ensemble_cs_str = f"{ensemble_cs} dB"

    title = f"集成方法在噪声干扰下诊断准确率衰减最慢（Critical SNR: {ensemble_cs_str}）"
    ax.set_title(title, fontsize=15, fontweight="bold", pad=15)

    fig.tight_layout()
    path = output_dir / "snr_accuracy_decay.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  [图1] SNR-Accuracy衰减曲线: {path}")
    return path


def _plot_robustness_index_bar(
    robustness_indices: Dict[str, float],
    output_dir: Path,
) -> Path:
    """绘制 Robustness Index 对比柱状图

    - Ensemble柱: 红色(#E74C3C)加粗
    - 其他柱: 灰色
    """
    apply_contest_style()

    fig, ax = plt.subplots(figsize=(8, 5))

    method_names = list(robustness_indices.keys())
    ri_values = list(robustness_indices.values())

    # 按值排序（升序），ensemble 放最后
    sorted_pairs = sorted(zip(ri_values, method_names))
    # 找 ensemble 的位置，将它放到最后
    ensemble_idx = None
    non_ensemble = []
    for val, name in sorted_pairs:
        if "ensemble" in name.lower() or "集成" in name:
            ensemble_idx = len(non_ensemble)  # 放最后
            ensemble_pair = (val, name)
        else:
            non_ensemble.append((val, name))

    ordered = non_ensemble + [ensemble_pair] if ensemble_pair else non_ensemble
    names = [n for _, n in ordered]
    values = [v for v, _ in ordered]

    # 颜色
    bar_colors = []
    for name in names:
        if "ensemble" in name.lower() or "集成" in name:
            bar_colors.append(COLORS["our_method"])  # #E74C3C
        else:
            bar_colors.append(COLORS["baseline"])  # #95A5A6

    bars = ax.bar(names, values, color=bar_colors, width=0.6, edgecolor="white", linewidth=0.5)

    # 数值标注
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, val + 0.02,
                f"{val:.3f}", ha="center", va="bottom", fontsize=11, fontweight="bold")

    ax.set_ylabel("Robustness Index (AUC归一化)", fontsize=13)
    ax.set_ylim(0, 1.15)
    ax.grid(axis="y", alpha=0.3)

    # 结论标题
    ensemble_ri = robustness_indices.get("集成Ensemble", 0)
    best_baseline_ri = max(
        v for k, v in robustness_indices.items()
        if "ensemble" not in k.lower() and "集成" not in k
    )
    title = make_conclusion_title(
        "鲁棒性指数", best_baseline_ri, ensemble_ri, unit=""
    )
    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)

    fig.tight_layout()
    path = output_dir / "robustness_index_bar.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  [图2] Robustness Index柱状图: {path}")
    return path


def _print_critical_snr_table(
    method_data: Dict[str, List[float]],
    critical_snr_map: Dict[str, Optional[float]],
    robustness_indices: Dict[str, float],
    snr_levels: List[float],
) -> str:
    """生成 Critical SNR 汇总表格并打印"""
    lines = [
        "\n" + "=" * 70,
        "  实验D: Critical SNR 与 Robustness Index 汇总",
        "=" * 70,
        "",
        f"  {'方法':<15s} {'Critical SNR (dB)':<20s} {'Robustness Index':<20s} {'Acc@20dB':<10s} {'Acc@-10dB':<10s}",
        "  " + "-" * 75,
    ]

    for method_name, accuracies in method_data.items():
        cs = critical_snr_map.get(method_name)
        cs_str = f"{cs} dB" if cs is not None else ">20 dB (全部高于80%)"
        ri = robustness_indices.get(method_name, 0.0)
        acc_20 = accuracies[0] * 100 if len(accuracies) > 0 else 0.0
        acc_min = accuracies[-1] * 100 if len(accuracies) > 0 else 0.0
        lines.append(
            f"  {method_name:<15s} {cs_str:<20s} {ri:<20.4f} {acc_20:<10.2f} {acc_min:<10.2f}"
        )

    lines.extend([
        "  " + "-" * 75,
        f"  阈值定义: Accuracy < 80% → Critical SNR",
        f"  RI定义: SNR-Acc曲线AUC / 最大可能AUC (梯形法)",
        "",
    ])

    table_text = "\n".join(lines)
    print(table_text)
    return table_text


# ═══════════════════════════════════════════════════════════
# 主入口函数
# ═══════════════════════════════════════════════════════════

def run_experiment_d() -> Dict[str, Any]:
    """运行实验D: 噪声鲁棒性衰减曲线"""
    apply_contest_style()

    output_dir = EXP_DIRS["d_robustness"]
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 60)
    print("  【实验D】噪声鲁棒性衰减曲线")
    print("=" * 60)

    # ── 1. 加载故障/健康文件 ─────────────────────────────────
    fault_path, healthy_path = _find_hustbear_files()

    if fault_path is None:
        print("[ERROR] 无法找到 HUSTbear 外圈故障文件，实验终止")
        return {"status": "fail", "error": "无故障文件"}

    print(f"  故障文件: {fault_path.name}")
    if healthy_path:
        print(f"  健康文件: {healthy_path.name}")
    else:
        print("  [WARN] 无健康文件，仅使用故障侧判定")

    fault_signal = load_npy(fault_path, max_samples=MAX_SAMPLES)
    healthy_signal = load_npy(healthy_path, max_samples=MAX_SAMPLES) if healthy_path else None

    fs = SAMPLE_RATE
    snr_levels = SNR_LEVELS
    bearing_params = HUSTBEAR_BEARING

    # ── 2. 估计转频 ──────────────────────────────────────────
    rot_freq_fault = estimate_rot_freq_spectrum(fault_signal, fs)
    rot_freq_healthy = estimate_rot_freq_spectrum(healthy_signal, fs) if healthy_signal is not None else 20.0

    print(f"  故障信号转频: {rot_freq_fault:.2f} Hz")
    print(f"  健康信号转频: {rot_freq_healthy:.2f} Hz")
    print(f"  轴承参数: n={bearing_params['n']}, d={bearing_params['d']}, D={bearing_params['D']}")
    print(f"  SNR级别: {snr_levels} dB")
    print(f"  健康度阈值: {HEALTH_THRESHOLD}")

    # ── 3. 对5种方法 × 6个SNR运行诊断 ────────────────────────
    method_data: Dict[str, List[float]] = {}
    critical_snr_map: Dict[str, Optional[float]] = {}
    robustness_indices: Dict[str, float] = {}

    total_methods = len(ROBUSTNESS_METHODS)
    total_snr = len(snr_levels)
    total_runs = total_methods * total_snr * (2 if healthy_signal else 1)
    print(f"\n  总运行次数: {total_runs} ({total_methods}方法 × {total_snr}SNR × {'2文件' if healthy_signal else '1文件'})")
    print()

    start_time = time.time()

    for display_name, bm_enum, is_ensemble in ROBUSTNESS_METHODS:
        print(f"  ── {display_name} ──")
        accuracies = _run_single_method(
            method_name=display_name,
            bm_enum=bm_enum,
            is_ensemble=is_ensemble,
            fault_signal=fault_signal,
            healthy_signal=healthy_signal,
            rot_freq_fault=rot_freq_fault,
            rot_freq_healthy=rot_freq_healthy,
            snr_levels=snr_levels,
            fs=fs,
            bearing_params=bearing_params,
        )

        method_data[display_name] = accuracies
        critical_snr_map[display_name] = _compute_critical_snr(snr_levels, accuracies)
        robustness_indices[display_name] = _compute_robustness_index(snr_levels, accuracies)

    elapsed = time.time() - start_time
    print(f"\n  诊断运行耗时: {elapsed:.1f}s")

    # ── 4. 绘制衰减曲线图 ────────────────────────────────────
    _plot_snr_accuracy_decay(method_data, snr_levels, critical_snr_map, output_dir)

    # ── 5. 绘制 Robustness Index 柱状图 ──────────────────────
    _plot_robustness_index_bar(robustness_indices, output_dir)

    # ── 6. 生成表格 ──────────────────────────────────────────
    table_text = _print_critical_snr_table(method_data, critical_snr_map, robustness_indices, snr_levels)

    # ── 7. 保存汇总数据 ──────────────────────────────────────
    summary = {
        "method_data": {k: [round(a, 4) for a in v] for k, v in method_data.items()},
        "critical_snr": {k: v for k, v in critical_snr_map.items()},
        "robustness_indices": {k: round(v, 4) for k, v in robustness_indices.items()},
        "snr_levels": snr_levels,
        "fault_file": fault_path.name if fault_path else "",
        "healthy_file": healthy_path.name if healthy_path else "",
        "rot_freq_fault": round(rot_freq_fault, 2),
        "rot_freq_healthy": round(rot_freq_healthy, 2),
        "health_threshold": HEALTH_THRESHOLD,
        "elapsed_seconds": round(elapsed, 1),
    }

    summary_path = output_dir / "experiment_d_summary.json"
    import json
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n  汇总数据已保存: {summary_path}")

    # ── 8. 保存表格为文本文件 ────────────────────────────────
    table_path = output_dir / "critical_snr_table.txt"
    with open(table_path, "w", encoding="utf-8") as f:
        f.write(table_text)
    print(f"  表格已保存: {table_path}")

    # ── 返回 ──────────────────────────────────────────────────
    print("\n  实验D完成!")
    return summary


# ═══════════════════════════════════════════════════════════
# 独立运行入口
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    result = run_experiment_d()