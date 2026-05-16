"""
去噪算法评价模块
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

from .config import OUTPUT_DIR, SAMPLE_RATE, MAX_SAMPLES
from .datasets import get_hustbear_files
from .utils import (
    load_npy,
    compute_snr_db,
    compute_mse,
    compute_correlation,
    add_awgn,
    save_cache,
    save_figure,
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

                    snr_before = compute_snr_db(signal, noisy_sig)
                    snr_after = compute_snr_db(signal, denoised)
                    mse_val = compute_mse(signal, denoised)
                    corr = compute_correlation(signal, denoised)

                    kurt_before = float(np.mean(signal**4) / (np.var(signal)**2 + 1e-12))
                    kurt_after = float(np.mean(denoised**4) / (np.var(denoised)**2 + 1e-12))

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


def _generate_denoise_report(results: List[Dict]) -> str:
    lines = [
        "# 去噪算法评价报告",
        "",
        "> 评价标准：SNR Improvement (dB) | MSE | 相关系数 | 执行时间 | 峭度保持",
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
        "## 3. 计算效率对比",
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
        "## 4. 结论与建议",
        "",
    ])
    if results:
        best_snr = max(results, key=lambda r: r["snr_improvement_db"])
        fastest = min(results, key=lambda r: r["exec_time_ms"])
        lines.append(f"- **SNR提升最佳**: `{best_snr['method']}` ({best_snr['snr_improvement_db']:+.2f} dB)")
        lines.append(f"- **速度最快**: `{fastest['method']}` ({fastest['exec_time_ms']:.1f} ms)")
    lines.append("")
    lines.append("### 场景推荐")
    lines.append("")
    lines.append("| 场景 | 推荐方法 | 理由 |")
    lines.append("|------|---------|------|")
    lines.append("| 高斯白噪声为主 | wavelet_vmd | 级联策略SNR提升最大 |")
    lines.append("| 需要保留冲击细节 | wavelet | 软阈值对冲击友好 |")
    lines.append("| 轴承故障增强 | med | 专门增强周期性冲击 |")
    lines.append("| 实时性要求高 | wavelet | 单方法最快 |")
    lines.append("")
    return "\n".join(lines)
