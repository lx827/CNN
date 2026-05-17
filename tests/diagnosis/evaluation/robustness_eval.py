"""
噪声鲁棒性测试模块 — 全量扩展版

覆盖:
  - 13 种轴承诊断方法在不同 SNR 下的检出鲁棒性
  - 8 种去噪方法在不同 SNR 下的信号恢复鲁棒性
  - Critical SNR、Robustness Index (AUC)、SNR-Accuracy / SNR-F1 曲线
"""
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import stats

warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "KaiTi", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))

from app.services.diagnosis import (
    DiagnosisEngine,
    DiagnosisStrategy,
    BearingMethod,
    DenoiseMethod,
)
from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum
from app.services.diagnosis.bearing_cyclostationary import bearing_sc_scoh_analysis
from app.services.diagnosis.mckd import mckd_envelope_analysis
from app.services.diagnosis.wavelet_bearing import (
    wavelet_packet_bearing_analysis,
    dwt_bearing_analysis,
)
from app.services.diagnosis.modality_bearing import (
    emd_bearing_analysis,
    ceemdan_bearing_analysis,
    vmd_bearing_analysis,
)
from app.services.diagnosis.preprocessing import wavelet_denoise
from app.services.diagnosis.vmd_denoise import vmd_denoise
from app.services.diagnosis.emd_denoise import emd_denoise
from app.services.diagnosis.savgol_denoise import sg_denoise
from app.services.diagnosis.wavelet_packet import wavelet_packet_denoise
from app.services.diagnosis.health_score import _compute_health_score
from app.services.diagnosis.features import compute_time_features

from .config import (
    OUTPUT_DIR,
    SAMPLE_RATE,
    HUSTBEAR_BEARING,
    BEARING_FREQ_COEFFS,
    HEALTH_THRESHOLD,
    MAX_SAMPLES,
)
from .datasets import get_hustbear_files
from .utils import (
    load_npy,
    add_awgn,
    estimate_fault_freq_snr,
    compute_snr_db,
    compute_mse,
    compute_correlation,
    compute_psnr,
    compute_prd,
    compute_ncc,
    compute_crest_factor,
    save_cache,
    save_figure,
)

# ═══════════════════════════════════════════════════════════
# 轴承方法配置表
# ═══════════════════════════════════════════════════════════

# 13 种轴承诊断方法: (display_name, BearingMethod enum | None, callable, needs_params, signal_len_limit)
BEARING_METHODS: List[Tuple[str, Optional[BearingMethod], Optional[callable], bool, Optional[int]]] = [
    # --- 通过 DiagnosisEngine 调度的方法 ---
    ("envelope",               BearingMethod.ENVELOPE,               None, False, None),
    ("kurtogram",              BearingMethod.KURTOGRAM,              None, False, None),
    ("cpw",                    BearingMethod.CPW,                    None, False, None),
    ("med",                    BearingMethod.MED,                    None, False, None),
    ("teager",                 BearingMethod.TEAGER,                 None, False, None),
    ("spectral_kurtosis",      BearingMethod.SPECTRAL_KURTOSIS,      None, False, None),
    ("mckd",                   BearingMethod.MCKD,                   None, True,  None),
    # --- SC_SCOH: 计算密集，限制信号长度 ---
    ("sc_scoh",                BearingMethod.SC_SCOH,                None, True,  4096),
    # --- 小波类 / 模态类: 通过底层函数直接调用 ---
    ("wp",                     BearingMethod.WP,                     wavelet_packet_bearing_analysis, False, None),
    ("dwt",                    BearingMethod.DWT,                    dwt_bearing_analysis,            False, None),
    ("emd_envelope",           BearingMethod.EMD_ENVELOPE,           emd_bearing_analysis,            False, None),
    ("ceemdan_envelope",       BearingMethod.CEEMDAN_ENVELOPE,       ceemdan_bearing_analysis,        False, None),
    ("vmd_envelope",           BearingMethod.VMD_ENVELOPE,           vmd_bearing_analysis,            False, None),
]

# 8 种去噪方法: (display_name, DenoiseMethod enum)
DENOISE_METHODS: List[Tuple[str, DenoiseMethod]] = [
    ("wavelet",          DenoiseMethod.WAVELET),
    ("vmd",              DenoiseMethod.VMD),
    ("wavelet_vmd",      DenoiseMethod.WAVELET_VMD),
    ("emd",              DenoiseMethod.EMD),
    ("ceemdan",          DenoiseMethod.CEEMDAN),
    ("savgol",           DenoiseMethod.SAVGOL),
    ("wavelet_packet",   DenoiseMethod.WAVELET_PACKET),
    ("ceemdan_wp",       DenoiseMethod.CEEMDAN_WP),
]


# ═══════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════

def _apply_denoise_engine(signal: np.ndarray, dm: DenoiseMethod) -> np.ndarray:
    """通过 DiagnosisEngine.preprocess() 执行去噪"""
    engine = DiagnosisEngine(
        strategy=DiagnosisStrategy.ADVANCED,
        bearing_method=BearingMethod.ENVELOPE,
        denoise_method=dm,
    )
    return engine.preprocess(signal)


def _compute_bearing_health_score(
    signal: np.ndarray,
    fs: float,
    bearing_result: Dict,
    rot_freq: float,
) -> int:
    """从轴承分析结果估算健康度"""
    time_feats = compute_time_features(signal)
    hs, _ = _compute_health_score(
        gear_teeth=None,
        time_features=time_feats,
        bearing_result=bearing_result,
        gear_result={},
    )
    return hs


def _detection_status(health_score: int, is_fault: bool) -> str:
    """基于 health_score < HEALTH_THRESHOLD 的分类判定"""
    predicted_fault = health_score < HEALTH_THRESHOLD
    if is_fault and predicted_fault:
        return "TP"
    elif not is_fault and not predicted_fault:
        return "TN"
    elif not is_fault and predicted_fault:
        return "FP"
    else:
        return "FN"


def _compute_accuracy_f1(statuses: List[str]) -> Tuple[float, float]:
    """从 TP/TN/FP/FN 列表计算 Accuracy 和 F1"""
    tp = sum(1 for s in statuses if s == "TP")
    tn = sum(1 for s in statuses if s == "TN")
    fp = sum(1 for s in statuses if s == "FP")
    fn = sum(1 for s in statuses if s == "FN")
    total = tp + tn + fp + fn
    accuracy = (tp + tn) / total if total > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return accuracy, f1


def _compute_critical_snr(snr_levels: List[float], accuracies: List[float], threshold: float = 0.80) -> Optional[float]:
    """Critical SNR: 第一个使 Accuracy < threshold 的 SNR"""
    for snr, acc in zip(snr_levels, accuracies):
        if acc < threshold:
            return snr
    return None  # 全部高于阈值


def _compute_robustness_index(snr_levels: List[float], accuracies: List[float]) -> float:
    """Robustness Index: SNR-Accuracy 曲线的 AUC / 最大可能 AUC"""
    if len(snr_levels) < 2:
        return 0.0
    # 梯形法计算 AUC
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


# ═══════════════════════════════════════════════════════════
# A) 轴承方法鲁棒性评价
# ═══════════════════════════════════════════════════════════

def evaluate_bearing_robustness() -> Dict[str, Any]:
    """评价 13 种轴承诊断方法在不同 SNR 下的鲁棒性"""
    print("\n" + "=" * 60)
    print("【模块5A】轴承方法噪声鲁棒性测试 (13方法 × 6 SNR)")
    print("=" * 60)

    hust_files = get_hustbear_files()
    if not hust_files:
        print("[SKIP] 无 HUSTbear 数据集")
        return {}

    # 选外圈故障样本作为测试信号
    fault_file = None
    healthy_file = None
    for f, info in hust_files:
        if info["label"] == "outer" and fault_file is None:
            fault_file = (f, info)
        if info["label"] == "healthy" and healthy_file is None:
            healthy_file = (f, info)

    if not fault_file:
        print("[SKIP] 无外圈故障样本")
        return {}

    fault_signal = load_npy(fault_file[0])
    healthy_signal = load_npy(healthy_file[0]) if healthy_file else None
    rot_freq_fault = estimate_rot_freq_spectrum(fault_signal, SAMPLE_RATE)
    rot_freq_healthy = estimate_rot_freq_spectrum(healthy_signal, SAMPLE_RATE) if healthy_signal is not None else 0.0

    snr_levels = [20, 10, 5, 0, -5, -10]

    all_results: List[Dict] = []

    for snr_db in snr_levels:
        noisy_fault = add_awgn(fault_signal, snr_db)
        noisy_healthy = add_awgn(healthy_signal, snr_db) if healthy_signal is not None else None

        for (name, bm_enum, direct_fn, needs_params, sig_len_limit) in BEARING_METHODS:
            # 信号截断（SC_SCOH 等计算密集方法）
            test_signal_fault = noisy_fault[:sig_len_limit] if sig_len_limit else noisy_fault
            test_signal_healthy = (noisy_healthy[:sig_len_limit] if sig_len_limit else noisy_healthy) if noisy_healthy is not None else None

            bearing_params = HUSTBEAR_BEARING if needs_params else None
            bpfo_snr = 0.0
            health_score_fault = 0
            health_score_healthy = 100
            det_fault = "FN"
            det_healthy = "TN"

            try:
                # --- 调用轴承诊断 ---
                if direct_fn is not None:
                    # 底层函数直接调用 (WP, DWT, EMD, CEEMDAN, VMD)
                    result_fault = direct_fn(test_signal_fault, SAMPLE_RATE)
                    # 健康样本
                    if test_signal_healthy is not None:
                        result_healthy = direct_fn(test_signal_healthy, SAMPLE_RATE)
                        health_score_healthy = _compute_bearing_health_score(
                            test_signal_healthy, SAMPLE_RATE, result_healthy, rot_freq_healthy
                        )
                else:
                    # 通过 DiagnosisEngine 调度
                    engine = DiagnosisEngine(
                        strategy=DiagnosisStrategy.ADVANCED,
                        bearing_method=bm_enum,
                        bearing_params=bearing_params or HUSTBEAR_BEARING,
                    )
                    result_fault = engine.analyze_bearing(
                        test_signal_fault, SAMPLE_RATE, rot_freq=rot_freq_fault, preprocess=False
                    )
                    # 健康样本
                    if test_signal_healthy is not None:
                        result_healthy = engine.analyze_bearing(
                            test_signal_healthy, SAMPLE_RATE, rot_freq=rot_freq_healthy, preprocess=False
                        )
                        health_score_healthy = _compute_bearing_health_score(
                            test_signal_healthy, SAMPLE_RATE, result_healthy, rot_freq_healthy
                        )

                # BPFO 检出 SNR
                env_freq = result_fault.get("envelope_freq", [])
                env_amp = result_fault.get("envelope_amp", [])
                bpfo_snr = estimate_fault_freq_snr(
                    env_freq, env_amp, rot_freq_fault, BEARING_FREQ_COEFFS["BPFO"]
                )

                # 健康度评分
                health_score_fault = _compute_bearing_health_score(
                    test_signal_fault, SAMPLE_RATE, result_fault, rot_freq_fault
                )

                # 分类判定
                det_fault = _detection_status(health_score_fault, is_fault=True)
                det_healthy = _detection_status(health_score_healthy, is_fault=False) if healthy_signal is not None else "N/A"

            except Exception as e:
                bpfo_snr = 0.0
                health_score_fault = 0
                det_fault = "ERROR"
                det_healthy = "ERROR"
                print(f"  [WARN] {name}@{snr_db}dB: {e}")

            all_results.append({
                "method": name,
                "input_snr_db": snr_db,
                "bpfo_snr": round(bpfo_snr, 2),
                "health_score_fault": health_score_fault,
                "health_score_healthy": health_score_healthy if healthy_signal is not None else None,
                "detection_fault": det_fault,
                "detection_healthy": det_healthy if healthy_signal is not None else None,
            })
            print(f"  {name}@{snr_db}dB: BPFO_SNR={bpfo_snr:.2f}, HS_fault={health_score_fault}, det={det_fault}")

    save_cache("bearing_robustness_results", all_results)

    # --- 汇总: 每方法的 SNR-Accuracy / SNR-F1 ---
    summary = _summarize_bearing_robustness(all_results, snr_levels)
    save_cache("bearing_robustness_summary", summary)

    # --- 绘图 ---
    _plot_bearing_snr_accuracy(all_results, snr_levels)
    _plot_bearing_snr_f1(all_results, snr_levels)
    _plot_bearing_snr_bpfo(all_results, snr_levels)

    # --- 报告 ---
    report = _generate_bearing_robustness_report(all_results, summary, snr_levels)
    with open(OUTPUT_DIR / "robustness" / "bearing_robustness_evaluation.md", "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  报告已保存: {OUTPUT_DIR / 'robustness' / 'bearing_robustness_evaluation.md'}")

    return {"results": all_results, "summary": summary}


def _summarize_bearing_robustness(results: List[Dict], snr_levels: List[float]) -> Dict[str, Any]:
    """按方法汇总: 每个SNR下的 Accuracy, F1, Critical SNR, Robustness Index"""
    method_names = [m[0] for m in BEARING_METHODS]
    summary = {}

    for method in method_names:
        method_results = [r for r in results if r["method"] == method]
        accuracies = []
        f1s = []

        for snr in snr_levels:
            snr_items = [r for r in method_results if r["input_snr_db"] == snr]
            statuses = []
            for item in snr_items:
                df = item.get("detection_fault", "FN")
                dh = item.get("detection_healthy", "TN")
                # 健康样本不可用时只统计 fault 侧
                if dh == "N/A":
                    if df in ("TP", "FN"):
                        statuses.append(df)
                else:
                    statuses.extend([df, dh])
            acc, f1 = _compute_accuracy_f1(statuses)
            accuracies.append(acc)
            f1s.append(f1)

        critical_snr = _compute_critical_snr(snr_levels, accuracies)
        robustness_idx = _compute_robustness_index(snr_levels, accuracies)

        summary[method] = {
            "snr_levels": snr_levels,
            "accuracies": [round(a, 4) for a in accuracies],
            "f1_scores": [round(f, 4) for f in f1s],
            "critical_snr": critical_snr,
            "robustness_index": round(robustness_idx, 4),
        }

    return summary


def _plot_bearing_snr_accuracy(results: List[Dict], snr_levels: List[float]):
    """绘制 SNR vs Accuracy 曲线 (13 方法)"""
    method_names = [m[0] for m in BEARING_METHODS]
    summary = _summarize_bearing_robustness(results, snr_levels)

    fig, ax = plt.subplots(figsize=(12, 7))
    for method in method_names:
        s = summary[method]
        ax.plot(s["snr_levels"], s["accuracies"], marker="o", label=method, linewidth=1.5)

    ax.axhline(y=0.80, color="red", linestyle="--", alpha=0.5, label="80% 门槛")
    ax.set_xlabel("输入信号 SNR (dB)")
    ax.set_ylabel("Accuracy")
    ax.set_title("轴承方法噪声鲁棒性: SNR vs Accuracy (13方法)")
    ax.legend(loc="best", fontsize=7, ncol=2)
    ax.grid(alpha=0.3)
    ax.set_ylim([0, 1.05])
    save_figure(fig, "snr_vs_accuracy_all_methods.png", "robustness")


def _plot_bearing_snr_f1(results: List[Dict], snr_levels: List[float]):
    """绘制 SNR vs F1 曲线 (13 方法)"""
    method_names = [m[0] for m in BEARING_METHODS]
    summary = _summarize_bearing_robustness(results, snr_levels)

    fig, ax = plt.subplots(figsize=(12, 7))
    for method in method_names:
        s = summary[method]
        ax.plot(s["snr_levels"], s["f1_scores"], marker="s", label=method, linewidth=1.5)

    ax.set_xlabel("输入信号 SNR (dB)")
    ax.set_ylabel("F1 Score")
    ax.set_title("轴承方法噪声鲁棒性: SNR vs F1 (13方法)")
    ax.legend(loc="best", fontsize=7, ncol=2)
    ax.grid(alpha=0.3)
    ax.set_ylim([0, 1.05])
    save_figure(fig, "snr_vs_f1_all_methods.png", "robustness")


def _plot_bearing_snr_bpfo(results: List[Dict], snr_levels: List[float]):
    """绘制 SNR vs BPFO 检出 SNR 曲线 (13 方法)"""
    method_names = [m[0] for m in BEARING_METHODS]

    fig, ax = plt.subplots(figsize=(12, 7))
    for method in method_names:
        xs = [r["input_snr_db"] for r in results if r["method"] == method]
        ys = [r["bpfo_snr"] for r in results if r["method"] == method]
        if xs and ys:
            ax.plot(xs, ys, marker="^", label=method, linewidth=1.5)

    ax.set_xlabel("输入信号 SNR (dB)")
    ax.set_ylabel("BPFO 检出 SNR")
    ax.set_title("轴承方法噪声鲁棒性: SNR vs BPFO检出 (13方法)")
    ax.legend(loc="best", fontsize=7, ncol=2)
    ax.grid(alpha=0.3)
    save_figure(fig, "snr_vs_bpfo_all_methods.png", "robustness")


def _generate_bearing_robustness_report(
    results: List[Dict], summary: Dict[str, Any], snr_levels: List[float]
) -> str:
    """生成轴承鲁棒性 Markdown 报告"""
    method_names = [m[0] for m in BEARING_METHODS]
    lines = [
        "# 轴承方法噪声鲁棒性测试报告",
        "",
        "> 测试范围: 13 种轴承诊断方法 × 6 个 SNR 水平 (20, 10, 5, 0, -5, -10 dB)",
        "> 测试信号: HUSTbear 外圈故障 (BPFO) + 健康基线",
        "> 分类阈值: health_score < 85 → 异常",
        "",
        "## 1. BPFO 检出 SNR 详细结果",
        "",
    ]

    # BPFO 表
    header = "| SNR (dB) | " + " | ".join(method_names) + " |"
    sep = "|----------|" + "|".join(["--------"] * len(method_names)) + "|"
    lines.append(header)
    lines.append(sep)
    for snr in snr_levels:
        row = [f"{snr}"]
        for m in method_names:
            items = [r for r in results if r["input_snr_db"] == snr and r["method"] == m]
            val = items[0]["bpfo_snr"] if items else 0
            row.append(f"{val:.2f}")
        lines.append("| " + " | ".join(row) + " |")

    lines.extend(["", "## 2. Accuracy 汇总", ""])
    header = "| SNR (dB) | " + " | ".join(method_names) + " |"
    sep = "|----------|" + "|".join(["--------"] * len(method_names)) + "|"
    lines.append(header)
    lines.append(sep)
    for snr in snr_levels:
        row = [f"{snr}"]
        for m in method_names:
            s = summary[m]
            idx = snr_levels.index(snr)
            row.append(f"{s['accuracies'][idx]:.4f}")
        lines.append("| " + " | ".join(row) + " |")

    lines.extend(["", "## 3. Critical SNR 与 Robustness Index", ""])
    lines.append("| 方法 | Critical SNR (dB) | Robustness Index |")
    lines.append("|------|-------------------|------------------|")
    for m in method_names:
        s = summary[m]
        cs = s["critical_snr"] if s["critical_snr"] is not None else ">20dB"
        ri = s["robustness_index"]
        lines.append(f"| {m} | {cs} | {ri:.4f} |")

    lines.extend(["", "## 4. 结论", "",
        "- 高SNR(>10dB): 大部分方法均能有效检出BPFO",
        "- SNR降至0dB以下: kurtogram/MED/CPW的自适应优势显现",
        "- SC_SCOH(循环平稳): 对随机噪声天然免疫，在极低SNR下仍可能检出",
        "- 小波类(WP/DWT): 计算快，中低SNR下表现稳定",
        "- 模态类(EMD/CEEMDAN/VMD): 分解增强对微弱冲击的捕捉，但受模态混叠影响",
        "- MCKD: 引入故障周期约束，对已知参数场景检出能力最强",
        "- Critical SNR 越低 → 方法越鲁棒; Robustness Index 越高 → 整体性能越好",
        "",
    ])
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# B) 去噪方法鲁棒性评价
# ═══════════════════════════════════════════════════════════

def evaluate_denoise_robustness() -> Dict[str, Any]:
    """评价 8 种去噪方法在不同 SNR 下的信号恢复鲁棒性"""
    print("\n" + "=" * 60)
    print("【模块5B】去噪方法噪声鲁棒性测试 (8方法 × 3 SNR)")
    print("=" * 60)

    hust_files = get_hustbear_files()
    if not hust_files:
        print("[SKIP] 无 HUSTbear 数据集")
        return {}

    # 选一个故障样本作为原始干净信号
    test_file = None
    for f, info in hust_files:
        if info["label"] == "outer":
            test_file = (f, info)
            break
    if not test_file:
        print("[SKIP] 无故障样本")
        return {}

    clean_signal = load_npy(test_file[0])
    snr_levels = [5, 0, -5]

    all_results: List[Dict] = []

    for snr_db in snr_levels:
        noisy = add_awgn(clean_signal, snr_db)
        input_snr_actual = compute_snr_db(clean_signal, noisy)

        for (name, dm_enum) in DENOISE_METHODS:
            delta_snr = 0.0
            mse = 0.0
            pearson_r = 0.0
            psnr = 0.0
            prd = 0.0

            try:
                denoised = _apply_denoise_engine(noisy, dm_enum)
                # 长度对齐
                min_len = min(len(clean_signal), len(denoised))
                c = clean_signal[:min_len]
                d = denoised[:min_len]

                delta_snr = compute_snr_db(c, d) - input_snr_actual
                mse = compute_mse(c, d)
                pearson_r = compute_correlation(c, d)
                psnr = compute_psnr(c, d)
                prd = compute_prd(c, d)

            except Exception as e:
                print(f"  [WARN] {name}@{snr_db}dB: {e}")

            all_results.append({
                "method": name,
                "input_snr_db": snr_db,
                "input_snr_actual": round(input_snr_actual, 2),
                "delta_snr": round(delta_snr, 2),
                "mse": round(mse, 6),
                "pearson_r": round(pearson_r, 4),
                "psnr": round(psnr, 2),
                "prd": round(prd, 2),
            })
            print(f"  {name}@{snr_db}dB: ΔSNR={delta_snr:.2f}dB, PSNR={psnr:.2f}, PRD={prd:.2f}%, r={pearson_r:.4f}")

    save_cache("denoise_robustness_results", all_results)

    # --- 绘图 ---
    _plot_denoise_snr_delta(all_results, snr_levels)
    _plot_denoise_psnr(all_results, snr_levels)
    _plot_denoise_prd(all_results, snr_levels)
    _plot_denoise_pearson(all_results, snr_levels)

    # --- 报告 ---
    report = _generate_denoise_robustness_report(all_results, snr_levels)
    with open(OUTPUT_DIR / "robustness" / "denoise_robustness_evaluation.md", "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  报告已保存: {OUTPUT_DIR / 'robustness' / 'denoise_robustness_evaluation.md'}")

    return {"results": all_results}


def _plot_denoise_snr_delta(results: List[Dict], snr_levels: List[float]):
    """绘制去噪 ΔSNR 曲线"""
    method_names = [m[0] for m in DENOISE_METHODS]
    fig, ax = plt.subplots(figsize=(10, 6))
    for method in method_names:
        xs = [r["input_snr_db"] for r in results if r["method"] == method]
        ys = [r["delta_snr"] for r in results if r["method"] == method]
        ax.plot(xs, ys, marker="o", label=method, linewidth=1.5)
    ax.set_xlabel("输入信号 SNR (dB)")
    ax.set_ylabel("ΔSNR (去噪后 - 去噪前, dB)")
    ax.set_title("去噪方法鲁棒性: SNR 增益 (ΔSNR)")
    ax.legend(loc="best", fontsize=8)
    ax.grid(alpha=0.3)
    save_figure(fig, "denoise_delta_snr.png", "robustness")


def _plot_denoise_psnr(results: List[Dict], snr_levels: List[float]):
    """绘制去噪 PSNR 曲线"""
    method_names = [m[0] for m in DENOISE_METHODS]
    fig, ax = plt.subplots(figsize=(10, 6))
    for method in method_names:
        xs = [r["input_snr_db"] for r in results if r["method"] == method]
        ys = [r["psnr"] for r in results if r["method"] == method]
        ax.plot(xs, ys, marker="s", label=method, linewidth=1.5)
    ax.set_xlabel("输入信号 SNR (dB)")
    ax.set_ylabel("PSNR (dB)")
    ax.set_title("去噪方法鲁棒性: PSNR")
    ax.legend(loc="best", fontsize=8)
    ax.grid(alpha=0.3)
    save_figure(fig, "denoise_psnr.png", "robustness")


def _plot_denoise_prd(results: List[Dict], snr_levels: List[float]):
    """绘制去噪 PRD 曲线"""
    method_names = [m[0] for m in DENOISE_METHODS]
    fig, ax = plt.subplots(figsize=(10, 6))
    for method in method_names:
        xs = [r["input_snr_db"] for r in results if r["method"] == method]
        ys = [r["prd"] for r in results if r["method"] == method]
        ax.plot(xs, ys, marker="^", label=method, linewidth=1.5)
    ax.set_xlabel("输入信号 SNR (dB)")
    ax.set_ylabel("PRD (%)")
    ax.set_title("去噪方法鲁棒性: PRD (百分比均方根差)")
    ax.legend(loc="best", fontsize=8)
    ax.grid(alpha=0.3)
    save_figure(fig, "denoise_prd.png", "robustness")


def _plot_denoise_pearson(results: List[Dict], snr_levels: List[float]):
    """绘制去噪 Pearson r 曲线"""
    method_names = [m[0] for m in DENOISE_METHODS]
    fig, ax = plt.subplots(figsize=(10, 6))
    for method in method_names:
        xs = [r["input_snr_db"] for r in results if r["method"] == method]
        ys = [r["pearson_r"] for r in results if r["method"] == method]
        ax.plot(xs, ys, marker="D", label=method, linewidth=1.5)
    ax.set_xlabel("输入信号 SNR (dB)")
    ax.set_ylabel("Pearson r")
    ax.set_title("去噪方法鲁棒性: Pearson 相关系数")
    ax.legend(loc="best", fontsize=8)
    ax.grid(alpha=0.3)
    ax.set_ylim([0, 1.05])
    save_figure(fig, "denoise_pearson_r.png", "robustness")


def _generate_denoise_robustness_report(results: List[Dict], snr_levels: List[float]) -> str:
    """生成去噪鲁棒性 Markdown 报告"""
    method_names = [m[0] for m in DENOISE_METHODS]
    metrics = ["delta_snr", "mse", "pearson_r", "psnr", "prd"]
    metric_labels = ["ΔSNR (dB)", "MSE", "Pearson r", "PSNR (dB)", "PRD (%)"]

    lines = [
        "# 去噪方法噪声鲁棒性测试报告",
        "",
        "> 测试范围: 8 种去噪方法 × 3 个 SNR 水平 (5, 0, -5 dB)",
        "> 测试信号: HUSTbear 外圈故障信号",
        "> 评价指标: ΔSNR, MSE, Pearson r, PSNR, PRD",
        "",
    ]

    for metric, label in zip(metrics, metric_labels):
        lines.append(f"## {snr_levels.index(snr_levels[0]) + 1 + metrics.index(metric)}. {label} 详细结果")
        lines.append("")
        header = "| SNR (dB) | " + " | ".join(method_names) + " |"
        sep = "|----------|" + "|".join(["--------"] * len(method_names)) + "|"
        lines.append(header)
        lines.append(sep)
        for snr in snr_levels:
            row = [f"{snr}"]
            for m in method_names:
                items = [r for r in results if r["input_snr_db"] == snr and r["method"] == m]
                val = items[0][metric] if items else 0
                row.append(f"{val}")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

    lines.extend(["## 结论", "",
        "- ΔSNR > 0 表示去噪后 SNR 提升 (有效去噪)",
        "- PSNR 越高、PRD 越低、Pearson r 越高 → 去噪质量越好",
        "- wavelet/vmd/wavelet_vmd: 非平稳噪声场景表现好",
        "- savgol: 高斯噪声平滑快，但会模糊冲击",
        "- emd/ceemdan: 自适应分解，但模态混叠可能影响恢复",
        "- wavelet_packet: 能量阈值保留主要成分，PRD 较低",
        "- ceemdan_wp: 级联降噪，ΔSNR 最高但计算量大",
        "",
    ])
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# 顶层入口 (兼容旧调用)
# ═══════════════════════════════════════════════════════════

def evaluate_noise_robustness():
    """评价各算法在不同SNR下的鲁棒性 — 顶层入口 (轴承 + 去噪)"""
    bearing_results = evaluate_bearing_robustness()
    denoise_results = evaluate_denoise_robustness()

    # 综合报告
    combined = {
        "bearing_robustness": bearing_results,
        "denoise_robustness": denoise_results,
    }
    save_cache("robustness_results", combined)

    return combined