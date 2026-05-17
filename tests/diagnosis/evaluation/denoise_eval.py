"""
去噪算法评价模块

新增方法:
- wavelet_packet: 小波包能量熵降噪
- ceemdan_wp: CEEMDAN + 小波包级联
- eemd: EEMD 降噪

新增指标 (所有方法):
- PSNR: 峰值信噪比
- PRD: 百分比均方根差
- NCC: 归一化互相关
- Crest Factor Improvement: 峰值因子改善度
"""
import sys
import os
import time
from pathlib import Path
from typing import Dict, List

import numpy as np

# 确保能导入cloud模块
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))

from app.services.diagnosis.preprocessing import (
    wavelet_denoise,
    minimum_entropy_deconvolution,
    cascade_wavelet_vmd,
    cascade_wavelet_lms,
)
from app.services.diagnosis.vmd_denoise import vmd_denoise
from app.services.diagnosis.emd_denoise import emd_denoise
from app.services.diagnosis.wavelet_packet import wavelet_packet_denoise
from app.services.diagnosis.savgol_denoise import sg_denoise

from .config import OUTPUT_DIR, SAMPLE_RATE, MAX_SAMPLES
from .datasets import get_hustbear_files
from .utils import (
    load_npy,
    compute_snr_db,
    compute_mse,
    compute_correlation,
    compute_excess_kurtosis,
    add_awgn,
    save_cache,
    save_figure,
    compute_psnr,
    compute_prd,
    compute_ncc,
    compute_crest_factor,
)

import matplotlib.pyplot as plt


def evaluate_denoise_methods():
    """评价所有去噪算法"""
    print("\n" + "=" * 60)
    print("【模块1】去噪算法评价")
    print("=" * 60)

    hust_files = get_hustbear_files()
    healthy_file = None
    fault_file = None
    for f, info in hust_files:
        if info["label"] == "healthy" and healthy_file is None:
            healthy_file = (f, info)
        elif info["label"] == "outer" and fault_file is None:
            fault_file = (f, info)
        if healthy_file and fault_file:
            break

    if not healthy_file or not fault_file:
        print("[SKIP] 数据集不可用")
        return []

    results = []
    test_cases = [
        ("healthy", load_npy(healthy_file[0])),
        ("outer_fault", load_npy(fault_file[0])),
    ]

    denoise_methods = {
        "wavelet": lambda sig: wavelet_denoise(sig, wavelet="db8"),
        "vmd": lambda sig: vmd_denoise(sig, K=5, alpha=2000),
        "med": lambda sig: minimum_entropy_deconvolution(sig, filter_len=64, max_iter=30)[0],
        "wavelet_vmd": lambda sig: cascade_wavelet_vmd(sig)[0],
        "wavelet_lms": lambda sig: cascade_wavelet_lms(sig)[0],
        "emd": lambda sig: emd_denoise(sig, method="emd")[0],
        "ceemdan": lambda sig: emd_denoise(sig, method="ceemdan")[0],
        "savgol": lambda sig: sg_denoise(sig, window_length=51),
        # ── 新增方法 ──
        "wavelet_packet": lambda sig: wavelet_packet_denoise(sig, wavelet="db8", level=3)[0],
        "ceemdan_wp": lambda sig: _cascade_ceemdan_wp(sig),
        "eemd": lambda sig: emd_denoise(sig, method="eemd")[0],
    }

    for case_name, signal in test_cases:
        noisy_5db = add_awgn(signal, 5.0)
        noisy_0db = add_awgn(signal, 0.0)
        noisy_neg5db = add_awgn(signal, -5.0)

        for method_name, method_fn in denoise_methods.items():
            for snr_label, noisy_sig in [("5dB", noisy_5db), ("0dB", noisy_0db), ("-5dB", noisy_neg5db)]:
                try:
                    t0 = time.perf_counter()
                    denoised = method_fn(noisy_sig)
                    exec_time = (time.perf_counter() - t0) * 1000

                    if len(denoised) != len(signal):
                        denoised = np.interp(np.arange(len(signal)), np.arange(len(denoised)), denoised)

                    # ── 原有指标 ──
                    snr_before = compute_snr_db(signal, noisy_sig)
                    snr_after = compute_snr_db(signal, denoised)
                    mse_val = compute_mse(signal, denoised)
                    corr = compute_correlation(signal, denoised)

                    kurt_before = compute_excess_kurtosis(signal)
                    kurt_after = compute_excess_kurtosis(denoised)

                    # ── 新增指标 ──
                    psnr = compute_psnr(signal, denoised)
                    prd = compute_prd(signal, denoised)
                    ncc = compute_ncc(signal, denoised)
                    crest_before = compute_crest_factor(noisy_sig)
                    crest_after = compute_crest_factor(denoised)
                    crest_improvement = crest_before - crest_after

                    results.append({
                        "case": case_name,
                        "method": method_name,
                        "noise_snr": snr_label,
                        "snr_before_db": round(snr_before, 2),
                        "snr_after_db": round(snr_after, 2),
                        "snr_improvement_db": round(snr_after - snr_before, 2),
                        "mse": round(mse_val, 6),
                        "correlation": round(corr, 4),
                        "exec_time_ms": round(exec_time, 2),
                        "kurtosis_before": round(kurt_before, 2),
                        "kurtosis_after": round(kurt_after, 2),
                        "psnr": round(psnr, 2),
                        "prd": round(prd, 4),
                        "ncc": round(ncc, 4),
                        "crest_before": round(crest_before, 4),
                        "crest_after": round(crest_after, 4),
                        "crest_improvement": round(crest_improvement, 4),
                    })
                except Exception as e:
                    print(f"  [ERR] {method_name} @ {case_name}/{snr_label}: {e}")

    save_cache("denoise_results", results)
    _plot_denoise_results(results)

    report = _generate_denoise_report(results)
    with open(OUTPUT_DIR / "denoise" / "denoise_evaluation.md", "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  报告已保存: {OUTPUT_DIR / 'denoise' / 'denoise_evaluation.md'}")
    return results


def _cascade_ceemdan_wp(signal: np.ndarray) -> np.ndarray:
    """CEEMDAN + 小波包级联降噪

    第一步: CEEMDAN 降噪 → 抑制模态混叠，分离噪声模态
    第二步: 小波包能量熵降噪 → 频带能量筛选重构，进一步去除残余噪声
    """
    step1, info1 = emd_denoise(signal, method="ceemdan", ensemble_size=30)
    step2, info2 = wavelet_packet_denoise(step1, wavelet="db8", level=3)
    return step2


def _plot_denoise_results(results: List[Dict]):
    if not results:
        return
    methods = sorted(set(r["method"] for r in results))

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    cases = [("healthy", "健康信号"), ("outer_fault", "外圈故障")]
    snr_levels = ["5dB", "0dB", "-5dB"]

    for idx, (case_key, case_title) in enumerate(cases):
        ax = axes[idx]
        x = np.arange(len(methods))
        width = 0.25
        for i, snr in enumerate(snr_levels):
            vals = []
            for m in methods:
                items = [r for r in results if r["case"]==case_key and r["noise_snr"]==snr and r["method"]==m]
                vals.append(items[0]["snr_improvement_db"] if items else 0)
            ax.bar(x + i*width, vals, width, label=snr)
        ax.set_ylabel("SNR Improvement (dB)")
        ax.set_title(f"{case_title}")
        ax.set_xticks(x + width)
        ax.set_xticklabels(methods, rotation=30, ha="right")
        ax.legend()
        ax.grid(axis="y", alpha=0.3)

    axes[2].axis("off")
    save_figure(fig, "snr_comparison.png", "denoise")

    fig, ax = plt.subplots(figsize=(8, 4.5))
    times = [np.mean([r["exec_time_ms"] for r in results if r["method"]==m]) for m in methods]
    ax.barh(methods, times, color="steelblue")
    ax.set_xlabel("平均执行时间 (ms)")
    ax.set_title("去噪算法执行时间对比")
    ax.grid(axis="x", alpha=0.3)
    save_figure(fig, "exec_time_comparison.png", "denoise")

    # ── 新增: PSNR 对比图 ──
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for idx, (case_key, case_title) in enumerate(cases):
        ax = axes[idx]
        x = np.arange(len(methods))
        width = 0.25
        for i, snr in enumerate(snr_levels):
            vals = []
            for m in methods:
                items = [r for r in results if r["case"]==case_key and r["noise_snr"]==snr and r["method"]==m]
                vals.append(items[0]["psnr"] if items else 0)
            ax.bar(x + i*width, vals, width, label=snr)
        ax.set_ylabel("PSNR (dB)")
        ax.set_title(f"PSNR — {case_title}")
        ax.set_xticks(x + width)
        ax.set_xticklabels(methods, rotation=30, ha="right")
        ax.legend()
        ax.grid(axis="y", alpha=0.3)
    save_figure(fig, "psnr_comparison.png", "denoise")

    # ── 新增: PRD + NCC 对比图 ──
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for idx, (metric, ylabel, title_prefix) in enumerate([
        ("prd", "PRD (%)", "PRD"),
        ("ncc", "NCC", "NCC"),
    ]):
        ax = axes[idx]
        x = np.arange(len(methods))
        width = 0.25
        for i, snr in enumerate(snr_levels):
            vals = []
            for m in methods:
                items = [r for r in results if r["case"]=="outer_fault" and r["noise_snr"]==snr and r["method"]==m]
                vals.append(items[0][metric] if items else 0)
            ax.bar(x + i*width, vals, width, label=snr)
        ax.set_ylabel(ylabel)
        ax.set_title(f"{title_prefix} — 外圈故障")
        ax.set_xticks(x + width)
        ax.set_xticklabels(methods, rotation=30, ha="right")
        ax.legend()
        ax.grid(axis="y", alpha=0.3)
    save_figure(fig, "prd_ncc_comparison.png", "denoise")


def _generate_denoise_report(results: List[Dict]) -> str:
    lines = [
        "# 去噪算法评价报告",
        "",
        "> 评价标准：SNR Improvement | PSNR | PRD | NCC | Crest Factor Improvement | MSE | 相关系数 | 执行时间 | 峭度保持",
        "",
        "## 1. 方法概述",
        "",
        "| 方法 | 原理 | 适用场景 |",
        "|------|------|---------|",
        "| wavelet | 小波阈值去噪 (db8) | 脉冲型噪声，保留冲击特征 |",
        "| vmd | 变分模态分解降噪 | 共振频带明确的信号 |",
        "| med | 最小熵解卷积 | 增强周期性冲击，轴承专用 |",
        "| wavelet_vmd | 小波+VMD级联 | 强高斯白噪声场景 |",
        "| wavelet_lms | 小波+LMS级联 | 强脉冲型干扰场景 |",
        "| emd | 经验模态分解 | 自适应模态，非平稳信号 |",
        "| ceemdan | 完备集成EMD | 抗模态混叠，变速工况 |",
        "| savgol | Savitzky-Golay平滑 | 高斯噪声，保留峰形，实时 |",
        "| wavelet_packet | 小波包能量熵降噪 | 频带能量筛选，齿轮故障频带重分布 |",
        "| ceemdan_wp | CEEMDAN+小波包级联 | 模态混叠抑制+频带筛选，变速工况齿轮 |",
        "| eemd | 集成经验模态分解 | 抗模态混叠，CEEMDAN轻量替代 |",

        "",
        "## 2. SNR Improvement 对比",
        "",
    ]
    for case in ["healthy", "outer_fault"]:
        case_title = "健康信号" if case == "healthy" else "外圈故障信号"
        lines.append(f"### {case_title}")
        lines.append("")
        lines.append("| 方法 | 5dB噪声 | 0dB噪声 | -5dB噪声 |")
        lines.append("|------|---------|---------|----------|")
        methods = sorted(set(r["method"] for r in results if r["case"] == case))
        for m in methods:
            row = [m]
            for snr in ["5dB", "0dB", "-5dB"]:
                items = [r for r in results if r["case"]==case and r["method"]==m and r["noise_snr"]==snr]
                val = items[0]["snr_improvement_db"] if items else 0
                row.append(f"{val:+.2f} dB")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

    lines.extend([
        "## 3. PSNR 对比",
        "",
    ])
    for case in ["healthy", "outer_fault"]:
        case_title = "健康信号" if case == "healthy" else "外圈故障信号"
        lines.append(f"### {case_title}")
        lines.append("")
        lines.append("| 方法 | 5dB噪声 | 0dB噪声 | -5dB噪声 |")
        lines.append("|------|---------|---------|----------|")
        methods = sorted(set(r["method"] for r in results if r["case"] == case))
        for m in methods:
            row = [m]
            for snr in ["5dB", "0dB", "-5dB"]:
                items = [r for r in results if r["case"]==case and r["method"]==m and r["noise_snr"]==snr]
                val = items[0]["psnr"] if items else 0
                row.append(f"{val:.2f}")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

    lines.extend([
        "## 4. PRD 对比 (越低越好)",
        "",
    ])
    for case in ["healthy", "outer_fault"]:
        case_title = "健康信号" if case == "healthy" else "外圈故障信号"
        lines.append(f"### {case_title}")
        lines.append("")
        lines.append("| 方法 | 5dB噪声 | 0dB噪声 | -5dB噪声 |")
        lines.append("|------|---------|---------|----------|")
        methods = sorted(set(r["method"] for r in results if r["case"] == case))
        for m in methods:
            row = [m]
            for snr in ["5dB", "0dB", "-5dB"]:
                items = [r for r in results if r["case"]==case and r["method"]==m and r["noise_snr"]==snr]
                val = items[0]["prd"] if items else 0
                row.append(f"{val:.4f}%")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

    lines.extend([
        "## 5. NCC 对比 (越接近1越好)",
        "",
    ])
    for case in ["healthy", "outer_fault"]:
        case_title = "健康信号" if case == "healthy" else "外圈故障信号"
        lines.append(f"### {case_title}")
        lines.append("")
        lines.append("| 方法 | 5dB噪声 | 0dB噪声 | -5dB噪声 |")
        lines.append("|------|---------|---------|----------|")
        methods = sorted(set(r["method"] for r in results if r["case"] == case))
        for m in methods:
            row = [m]
            for snr in ["5dB", "0dB", "-5dB"]:
                items = [r for r in results if r["case"]==case and r["method"]==m and r["noise_snr"]==snr]
                val = items[0]["ncc"] if items else 0
                row.append(f"{val:.4f}")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

    lines.extend([
        "## 6. Crest Factor Improvement 对比",
        "",
        "> Crest Improvement = crest_before - crest_after; 正值表示去噪降低了峰值因子",
        "",
    ])
    for case in ["healthy", "outer_fault"]:
        case_title = "健康信号" if case == "healthy" else "外圈故障信号"
        lines.append(f"### {case_title}")
        lines.append("")
        lines.append("| 方法 | 5dB噪声 | 0dB噪声 | -5dB噪声 |")
        lines.append("|------|---------|---------|----------|")
        methods = sorted(set(r["method"] for r in results if r["case"] == case))
        for m in methods:
            row = [m]
            for snr in ["5dB", "0dB", "-5dB"]:
                items = [r for r in results if r["case"]==case and r["method"]==m and r["noise_snr"]==snr]
                val = items[0]["crest_improvement"] if items else 0
                row.append(f"{val:+.4f}")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

    lines.extend([
        "## 7. 计算效率对比",
        "",
        "| 方法 | 平均执行时间 (ms) | 2G服务器适用性 |",
        "|------|------------------|---------------|",
    ])
    methods = sorted(set(r["method"] for r in results))
    for m in methods:
        t = np.mean([r["exec_time_ms"] for r in results if r["method"] == m])
        suitability = "✅" if t < 500 else ("⚠️" if t < 2000 else "❌")
        lines.append(f"| {m} | {t:.1f} | {suitability} |")

    lines.extend([
        "",
        "## 8. 结论与建议",
        "",
    ])
    if results:
        best_snr = max(results, key=lambda r: r["snr_improvement_db"])
        fastest = min(results, key=lambda r: r["exec_time_ms"])
        best_psnr = max(results, key=lambda r: r["psnr"])
        best_ncc = max(results, key=lambda r: r["ncc"])
        lowest_prd = min(results, key=lambda r: r["prd"])
        lines.append(f"- **SNR提升最佳**: `{best_snr['method']}` ({best_snr['snr_improvement_db']:+.2f} dB)")
        lines.append(f"- **PSNR最佳**: `{best_psnr['method']}` ({best_psnr['psnr']:.2f} dB)")
        lines.append(f"- **NCC最佳**: `{best_ncc['method']}` ({best_ncc['ncc']:.4f})")
        lines.append(f"- **PRD最低**: `{lowest_prd['method']}` ({lowest_prd['prd']:.4f}%)")
        lines.append(f"- **速度最快**: `{fastest['method']}` ({fastest['exec_time_ms']:.1f} ms)")
    lines.append("")
    lines.append("### 场景推荐")
    lines.append("")
    lines.append("| 场景 | 推荐方法 | 理由 |")
    lines.append("|------|---------|------|")
    lines.append("| 高斯白噪声为主 | wavelet_vmd | 级联策略SNR提升最大 |")
    lines.append("| 需要保留冲击细节 | wavelet | 软阈值对冲击友好 |")
    lines.append("| 轴承故障增强 | med | 专门增强周期性冲击 |")
    lines.append("| 实时性要求高 | savgol | O(N)复杂度，极快 |")
    lines.append("| 非平稳/变速信号 | ceemdan | 自适应模态分解 |")
    lines.append("| 齿轮频带能量重分布 | wavelet_packet | 全频带覆盖，能量熵筛选 |")
    lines.append("| 变速齿轮综合降噪 | ceemdan_wp | 抗模态混叠+频带筛选 |")
    lines.append("| EEMD轻量替代 | eemd | 抗模态混叠，比CEEMDAN快 |")
    lines.append("| 快速平滑预处理 | savgol | 多项式拟合，无相位失真 |")
    lines.append("")
    return "\n".join(lines)