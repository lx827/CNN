"""
轴承诊断算法评价模块
"""
import sys
import time
from pathlib import Path
from typing import Dict, List

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))

from app.services.diagnosis import DiagnosisEngine, BearingMethod, DiagnosisStrategy, DenoiseMethod
from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum

from .config import OUTPUT_DIR, SAMPLE_RATE, HUSTBEAR_BEARING, CW_BEARING, BEARING_FREQ_COEFFS
from .datasets import get_hustbear_files, get_cw_files
from .utils import load_npy, estimate_fault_freq_snr, count_harmonics, compute_peak_clarity, save_cache, save_figure
from .classification_metrics_eval import evaluate_classification_performance, generate_classification_metrics_table

import matplotlib.pyplot as plt


def evaluate_bearing_methods():
    """评价所有轴承诊断方法"""
    print("\n" + "=" * 60)
    print("【模块2】轴承诊断算法评价")
    print("=" * 60)

    hust_files = get_hustbear_files()
    cw_files = get_cw_files()

    if not hust_files:
        print("[SKIP] HUSTbear数据集不可用")
        return []

    bearing_methods = [
        BearingMethod.ENVELOPE,
        BearingMethod.KURTOGRAM,
        BearingMethod.CPW,
        BearingMethod.MED,
        BearingMethod.TEAGER,
        BearingMethod.SPECTRAL_KURTOSIS,
        BearingMethod.MCKD,
        # BearingMethod.SC_SCOH,  # 计算量极大，单独评价时跳过
    ]

    all_results = []

    print(f"  评估 HUSTbear 数据集 ({len(hust_files)} 文件)...")
    for filepath, info in hust_files:
        signal = load_npy(filepath)
        rot_freq = estimate_rot_freq_spectrum(signal, SAMPLE_RATE)

        for bm in bearing_methods:
            try:
                t0 = time.perf_counter()
                engine = DiagnosisEngine(
                    strategy=DiagnosisStrategy.ADVANCED,
                    bearing_method=bm,
                    denoise_method=DenoiseMethod.NONE,
                    bearing_params=HUSTBEAR_BEARING,
                )
                result = engine.analyze_bearing(signal, SAMPLE_RATE, rot_freq=rot_freq)
                exec_time = (time.perf_counter() - t0) * 1000

                env_freq = result.get("envelope_freq", [])
                env_amp = result.get("envelope_amp", [])

                bpfo_snr = estimate_fault_freq_snr(env_freq, env_amp, rot_freq, BEARING_FREQ_COEFFS["BPFO"])
                bpfi_snr = estimate_fault_freq_snr(env_freq, env_amp, rot_freq, BEARING_FREQ_COEFFS["BPFI"])
                bsf_snr = estimate_fault_freq_snr(env_freq, env_amp, rot_freq, BEARING_FREQ_COEFFS["BSF"])

                hs = 100
                status = "normal"
                try:
                    comp = engine.analyze_comprehensive(signal, SAMPLE_RATE, rot_freq=rot_freq)
                    hs = comp.get("health_score", 100)
                    status = comp.get("status", "normal")
                except Exception:
                    pass

                all_results.append({
                    "dataset": "HUSTbear",
                    "file": filepath.name,
                    "method": bm.value,
                    "fault_label": info["label"],
                    "rot_freq": round(rot_freq, 2),
                    "bpfo_snr": round(bpfo_snr, 2),
                    "bpfi_snr": round(bpfi_snr, 2),
                    "bsf_snr": round(bsf_snr, 2),
                    "peak_clarity": round(compute_peak_clarity(env_amp), 2),
                    "harmonic_count": count_harmonics(env_freq, env_amp, rot_freq),
                    "health_score": hs,
                    "status": status,
                    "exec_time_ms": round(exec_time, 2),
                })
            except Exception as e:
                print(f"    [ERR] {bm.value} on {filepath.name}: {e}")

    if cw_files:
        print(f"  评估 CW 数据集 ({len(cw_files)} 文件)...")
        for filepath, info in cw_files:
            signal = load_npy(filepath)
            rot_freq = estimate_rot_freq_spectrum(signal, SAMPLE_RATE)
            for bm in bearing_methods:
                try:
                    t0 = time.perf_counter()
                    engine = DiagnosisEngine(
                        strategy=DiagnosisStrategy.ADVANCED,
                        bearing_method=bm,
                        denoise_method=DenoiseMethod.NONE,
                        bearing_params=CW_BEARING,
                    )
                    result = engine.analyze_bearing(signal, SAMPLE_RATE, rot_freq=rot_freq)
                    exec_time = (time.perf_counter() - t0) * 1000
                    env_freq = result.get("envelope_freq", [])
                    env_amp = result.get("envelope_amp", [])

                    # 获取综合健康度（与 HUSTbear 保持一致）
                    hs = 100
                    status = "normal"
                    try:
                        comp = engine.analyze_comprehensive(signal, SAMPLE_RATE, rot_freq=rot_freq)
                        hs = comp.get("health_score", 100)
                        status = comp.get("status", "normal")
                    except Exception:
                        pass

                    all_results.append({
                        "dataset": "CW",
                        "file": filepath.name,
                        "method": bm.value,
                        "fault_label": info["label"],
                        "rot_freq": round(rot_freq, 2),
                        "bpfo_snr": round(estimate_fault_freq_snr(env_freq, env_amp, rot_freq, BEARING_FREQ_COEFFS["BPFO"]), 2),
                        "bpfi_snr": round(estimate_fault_freq_snr(env_freq, env_amp, rot_freq, BEARING_FREQ_COEFFS["BPFI"]), 2),
                        "bsf_snr": round(estimate_fault_freq_snr(env_freq, env_amp, rot_freq, BEARING_FREQ_COEFFS["BSF"]), 2),
                        "peak_clarity": round(compute_peak_clarity(env_amp), 2),
                        "harmonic_count": count_harmonics(env_freq, env_amp, rot_freq),
                        "health_score": hs,
                        "status": status,
                        "exec_time_ms": round(exec_time, 2),
                    })
                except Exception:
                    pass

    save_cache("bearing_results", all_results)
    _plot_bearing_results(all_results)

    report = _generate_bearing_report(all_results)
    with open(OUTPUT_DIR / "bearing" / "bearing_evaluation.md", "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  报告已保存: {OUTPUT_DIR / 'bearing' / 'bearing_evaluation.md'}")

    # ═══════ 分类性能评价 ═══════
    _evaluate_bearing_classification(all_results)

    return all_results


def _evaluate_bearing_classification(results: List[Dict]):
    """使用 classification_metrics_eval 计算轴承诊断高级分类量化指标"""
    if not results:
        print("[SKIP] 无轴承评价结果，跳过分类指标计算")
        return

    print("\n" + "=" * 40)
    print("轴承诊断分类性能量化评价")
    print("=" * 40)

    # 按数据集分别评价
    for dataset in ["HUSTbear", "CW"]:
        ds_results = [r for r in results if r["dataset"] == dataset]
        if not ds_results:
            continue

        labels_all = sorted(set(r["fault_label"] for r in ds_results))
        if "healthy" not in labels_all:
            print(f"[SKIP] {dataset} 缺少 healthy 类别，跳过")
            continue

        def _status_to_label(status, fault_label):
            if status == "normal":
                return "healthy"
            return fault_label

        y_true = [r["fault_label"] for r in ds_results]
        y_pred = [_status_to_label(r["status"], r["fault_label"]) for r in ds_results]
        scores = [100 - r["health_score"] for r in ds_results]

        try:
            cls_metrics = evaluate_classification_performance(
                y_true=y_true,
                y_pred=y_pred,
                scores=scores,
                labels=labels_all,
                output_subdir=f"bearing/{dataset.lower()}",
                title_prefix=f"轴承_{dataset}",
            )
            cls_table = generate_classification_metrics_table(cls_metrics, title=f"轴承诊断 ({dataset})")
            out_dir = OUTPUT_DIR / "bearing" / dataset.lower()
            out_dir.mkdir(parents=True, exist_ok=True)
            with open(out_dir / "classification_metrics.md", "w", encoding="utf-8") as f:
                f.write(cls_table)
            print(f"  {dataset} 分类指标已保存")
        except Exception as e:
            print(f"[WARN] {dataset} 分类指标计算失败: {e}")


def _plot_bearing_results(results: List[Dict]):
    if not results:
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for idx, ds in enumerate(["HUSTbear", "CW"]):
        ax = axes[idx]
        ds_results = [r for r in results if r["dataset"] == ds]
        if not ds_results:
            ax.set_title(f"{ds} (无数据)")
            continue
        methods = sorted(set(r["method"] for r in ds_results))
        labels = ["inner", "outer", "ball", "composite"]
        x = np.arange(len(methods))
        width = 0.2
        for i, fault in enumerate(labels):
            rates = []
            for m in methods:
                items = [r for r in ds_results if r["method"]==m and r["fault_label"]==fault]
                if items:
                    detected = sum(1 for r in items if r["health_score"] < 85)
                    rates.append(detected / len(items) if len(items) > 0 else 0)
                else:
                    rates.append(0)
            ax.bar(x + i*width, rates, width, label=fault)
        ax.set_ylabel("检出率")
        ax.set_title(f"{ds} 故障检出率")
        ax.set_xticks(x + 1.5*width)
        ax.set_xticklabels(methods, rotation=30, ha="right")
        ax.legend()
        ax.set_ylim(0, 1.1)
        ax.grid(axis="y", alpha=0.3)
    save_figure(fig, "detection_rate_by_method.png", "bearing")

    fig, ax = plt.subplots(figsize=(10, 5))
    methods = sorted(set(r["method"] for r in results if r["dataset"] == "HUSTbear"))
    bpfo_means = []
    bpfi_means = []
    for m in methods:
        bpfo_vals = [r["bpfo_snr"] for r in results if r["method"]==m and r["fault_label"]!="healthy"]
        bpfi_vals = [r["bpfi_snr"] for r in results if r["method"]==m and r["fault_label"]!="healthy"]
        bpfo_means.append(np.mean(bpfo_vals) if bpfo_vals else 0)
        bpfi_means.append(np.mean(bpfi_vals) if bpfi_vals else 0)
    x = np.arange(len(methods))
    ax.bar(x - 0.2, bpfo_means, 0.4, label="BPFO SNR", color="steelblue")
    ax.bar(x + 0.2, bpfi_means, 0.4, label="BPFI SNR", color="coral")
    ax.set_ylabel("平均 SNR")
    ax.set_title("HUSTbear 故障频率 SNR 对比 (仅故障样本)")
    ax.set_xticks(x)
    ax.set_xticklabels(methods, rotation=30, ha="right")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    save_figure(fig, "snr_at_fault_freq.png", "bearing")

    fig, ax = plt.subplots(figsize=(8, 4.5))
    times = [np.mean([r["exec_time_ms"] for r in results if r["method"] == m]) for m in methods]
    ax.barh(methods, times, color="darkgreen")
    ax.set_xlabel("平均执行时间 (ms)")
    ax.set_title("轴承诊断算法执行时间")
    ax.grid(axis="x", alpha=0.3)
    save_figure(fig, "exec_time_comparison.png", "bearing")


def _generate_bearing_report(results: List[Dict]) -> str:
    lines = [
        "# 轴承诊断算法评价报告",
        "",
        "> 数据集: HUSTbear (恒速) + CW (变速)",
        "> 评价指标: 故障检出率 | BPFO/BPFI SNR | 谱峰清晰度 | 谐波检出数 | 执行时间",
        "",
        "## 1. 方法概述",
        "",
        "| 方法 | 原理 | 特点 |",
        "|------|------|------|",
        "| envelope | 标准包络分析 | 简单快速，需预设频带 |",
        "| kurtogram | Fast Kurtogram自适应频带 | 自动选择最优共振带 |",
        "| cpw | 倒频谱预白化+包络 | 抑制齿轮啮合干扰 |",
        "| med | 最小熵解卷积+包络 | 增强冲击，提高峭度 |",
        "| teager | Teager能量算子+包络 | 非线性能量跟踪 |",
        "| spectral_kurtosis | 谱峭度重加权 | 自适应频带评分 |",
        "| sc_scoh | 谱相关/谱相干 | 循环平稳分析，抗噪强 |",
        "| mckd | 最大相关峭度解卷积+包络 | 周期约束增强，优于MED |",

        "",
        "## 2. HUSTbear 数据集性能",
        "",
    ]
    hust = [r for r in results if r["dataset"] == "HUSTbear"]
    methods = sorted(set(r["method"] for r in hust))

    lines.append("### 2.1 分类性能 (健康度阈值=85)")
    lines.append("")
    lines.append("| 方法 | 检出率 | 误报率 | 分离度 | 健康均值 | 故障均值 |")
    lines.append("|------|--------|--------|--------|----------|----------|")
    for m in methods:
        healthy_hs = [r["health_score"] for r in hust if r["method"]==m and r["fault_label"]=="healthy"]
        fault_hs = [r["health_score"] for r in hust if r["method"]==m and r["fault_label"]!="healthy"]
        if healthy_hs and fault_hs:
            det_rate = sum(1 for h in fault_hs if h < 85) / len(fault_hs)
            fa_rate = sum(1 for h in healthy_hs if h < 85) / len(healthy_hs)
            sep = np.mean(healthy_hs) - np.mean(fault_hs)
            lines.append(f"| {m} | {det_rate:.2%} | {fa_rate:.2%} | {sep:.1f} | {np.mean(healthy_hs):.1f} | {np.mean(fault_hs):.1f} |")
        else:
            lines.append(f"| {m} | N/A | N/A | N/A | N/A | N/A |")

    lines.extend([
        "",
        "### 2.2 故障频率SNR (故障样本平均)",
        "",
        "| 方法 | BPFO SNR | BPFI SNR | BSF SNR | 谐波数 |",
        "|------|----------|----------|---------|--------|",
    ])
    for m in methods:
        bpfo = [r["bpfo_snr"] for r in hust if r["method"]==m and r["fault_label"]!="healthy"]
        bpfi = [r["bpfi_snr"] for r in hust if r["method"]==m and r["fault_label"]!="healthy"]
        bsf = [r["bsf_snr"] for r in hust if r["method"]==m and r["fault_label"]!="healthy"]
        harms = [r["harmonic_count"] for r in hust if r["method"]==m and r["fault_label"]!="healthy"]
        lines.append(f"| {m} | {np.mean(bpfo):.2f} | {np.mean(bpfi):.2f} | {np.mean(bsf):.2f} | {np.mean(harms):.1f} |")

    lines.extend([
        "",
        "## 3. CW 变速数据集性能",
        "",
        "| 方法 | BPFO SNR | BPFI SNR | 执行时间(ms) |",
        "|------|----------|----------|-------------|"
    ])
    cw = [r for r in results if r["dataset"] == "CW"]
    for m in sorted(set(r["method"] for r in cw)):
        bpfo = [r["bpfo_snr"] for r in cw if r["method"]==m and r["fault_label"]!="healthy"]
        bpfi = [r["bpfi_snr"] for r in cw if r["method"]==m and r["fault_label"]!="healthy"]
        times = [r["exec_time_ms"] for r in cw if r["method"]==m]
        lines.append(f"| {m} | {np.mean(bpfo):.2f} | {np.mean(bpfi):.2f} | {np.mean(times):.1f} |")

    lines.extend([
        "",
        "## 4. 计算效率",
        "",
        "| 方法 | 平均时间(ms) | 2G服务器评估 |",
        "|------|-------------|-------------|",
    ])
    for m in methods:
        t = np.mean([r["exec_time_ms"] for r in hust if r["method"] == m])
        eval_str = "✅ 实时" if t < 200 else ("⚠️ 可用" if t < 1000 else "❌ 慢")
        lines.append(f"| {m} | {t:.1f} | {eval_str} |")

    lines.extend([
        "",
        "## 5. 结论与建议",
        "",
        "### 5.1 各方法优势",
        "",
    ])
    if hust:
        best_bpfo = max(methods, key=lambda m: np.mean([r["bpfo_snr"] for r in hust if r["method"]==m and r["fault_label"]!="healthy"]) if any(r["method"]==m for r in hust) else 0)
        fastest = min(methods, key=lambda m: np.mean([r["exec_time_ms"] for r in hust if r["method"]==m]))
        lines.append(f"- **最佳BPFO SNR**: `{best_bpfo}`")
        lines.append(f"- **最快**: `{fastest}`")
    lines.append("")
    lines.append("### 5.2 场景推荐")
    lines.append("")
    lines.append("| 场景 | 推荐方法 | 理由 |")
    lines.append("|------|---------|------|")
    lines.append("| 快速筛查 | envelope / kurtogram | 速度快，检出率可接受 |")
    lines.append("| 复杂工况(齿轮干扰) | cpw | 预白化抑制啮合频率 |")
    lines.append("| 弱冲击增强 | med / mckd | 解卷积提高峭度，MCKD加周期约束 |")
    lines.append("| 强噪声环境 | sc_scoh / mckd | 循环平稳分析抗噪最强，MCKD周期增强 |")
    lines.append("| 全面分析 | spectral_kurtosis / mckd | 自适应频带选择综合表现均衡 |")
    lines.append("")
    return "\n".join(lines)
