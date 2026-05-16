"""
齿轮诊断算法评价模块
"""
import sys
import time
from pathlib import Path
from typing import Dict, List

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))

from app.services.diagnosis import DiagnosisEngine, GearMethod, DiagnosisStrategy, DenoiseMethod
from app.services.diagnosis.gear import compute_fm0_order, compute_ser_order, _evaluate_gear_faults
from app.services.diagnosis.gear.metrics import (
    compute_tsa_residual_order,
    compute_fm4,
    compute_m6a,
    compute_m8a,
    compute_car,
)
from app.services.diagnosis.features import compute_time_features
from app.services.diagnosis.order_tracking import _compute_order_spectrum, _compute_order_spectrum_multi_frame

from .config import OUTPUT_DIR, SAMPLE_RATE, WTGEARBOX_GEAR, MESH_FREQ_COEFF
from .datasets import get_wtgearbox_files
from .utils import load_npy, save_cache, save_figure

import matplotlib.pyplot as plt


def evaluate_gear_methods():
    """评价齿轮诊断方法"""
    print("\n" + "=" * 60)
    print("【模块3】齿轮诊断算法评价")
    print("=" * 60)

    wt_files = get_wtgearbox_files()
    if not wt_files:
        print("[SKIP] WTgearbox数据集不可用")
        return []

    all_results = []
    print(f"  评估 WTgearbox 数据集 ({len(wt_files)} 文件)...")

    for filepath, info in wt_files:
        signal = load_npy(filepath)
        parts = filepath.name.replace(".npy", "").split("-")
        main_parts = parts[0].split("_")
        try:
            rot_freq = float(main_parts[-1])
        except ValueError:
            rot_freq = 30.0
        mesh_freq = MESH_FREQ_COEFF * rot_freq

        # TSA
        tsa_result = compute_tsa_residual_order(signal, SAMPLE_RATE, rot_freq)
        tsa_kurt = 0.0
        fm4_val = 0.0
        if tsa_result.get("valid"):
            diff = tsa_result.get("differential", np.array([]))
            if len(diff) > 0:
                tsa_kurt = float(np.mean(diff**4) / (np.var(diff)**2 + 1e-12))
                fm4_val = compute_fm4(diff)

        # 阶次谱
        try:
            order_axis, order_spectrum, _, _ = _compute_order_spectrum_multi_frame(
                signal, SAMPLE_RATE, samples_per_rev=1024, max_order=50
            )
        except Exception:
            try:
                order_axis, order_spectrum = _compute_order_spectrum(
                    signal, SAMPLE_RATE, rot_freq, samples_per_rev=1024
                )
            except Exception:
                order_axis, order_spectrum = np.array([]), np.array([])

        mesh_order = MESH_FREQ_COEFF
        ser_val = compute_ser_order(order_axis, order_spectrum, mesh_order) if len(order_axis) > 0 else 0.0

        fm0_val = 0.0
        if tsa_result.get("valid"):
            tsa_sig = tsa_result.get("tsa_signal", np.array([]))
            if len(tsa_sig) > 0 and len(order_axis) > 0 and len(order_spectrum) > 0:
                try:
                    fm0_val = compute_fm0_order(tsa_sig, order_axis, order_spectrum, mesh_order)
                except Exception:
                    fm0_val = compute_fm0(tsa_sig, mesh_freq, SAMPLE_RATE)

        car_val = compute_car(signal, SAMPLE_RATE, rot_freq, n_harmonics=3)
        m6a_val = compute_m6a(diff) if tsa_result.get("valid") and len(diff) > 0 else 0.0
        m8a_val = compute_m8a(diff) if tsa_result.get("valid") and len(diff) > 0 else 0.0

        hs = 100
        status = "normal"
        try:
            engine = DiagnosisEngine(
                strategy=DiagnosisStrategy.ADVANCED,
                gear_method=GearMethod.ADVANCED,
                denoise_method=DenoiseMethod.NONE,
                gear_teeth=WTGEARBOX_GEAR,
            )
            comp = engine.analyze_comprehensive(signal, SAMPLE_RATE, rot_freq=rot_freq)
            hs = comp.get("health_score", 100)
            status = comp.get("status", "normal")
        except Exception:
            pass

        all_results.append({
            "file": filepath.name,
            "fault_label": info["label"],
            "rot_freq": rot_freq,
            "mesh_freq": round(mesh_freq, 2),
            "ser": round(ser_val, 4),
            "fm0": round(fm0_val, 4),
            "fm4": round(fm4_val, 4),
            "car": round(car_val, 4),
            "m6a": round(m6a_val, 4),
            "m8a": round(m8a_val, 4),
            "tsa_kurt": round(tsa_kurt, 4),
            "health_score": hs,
            "status": status,
        })

    save_cache("gear_results", all_results)
    _plot_gear_results(all_results)

    report = _generate_gear_report(all_results)
    with open(OUTPUT_DIR / "gear" / "gear_evaluation.md", "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  报告已保存: {OUTPUT_DIR / 'gear' / 'gear_evaluation.md'}")
    return all_results


def _plot_gear_results(results: List[Dict]):
    if not results:
        return

    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    metrics = [("ser", "SER"), ("fm0", "FM0"), ("fm4", "FM4"), ("car", "CAR")]
    for idx, (key, title) in enumerate(metrics):
        ax = axes[idx // 2, idx % 2]
        healthy_vals = [r[key] for r in results if r["fault_label"] == "healthy"]
        fault_vals = [r[key] for r in results if r["fault_label"] != "healthy"]
        if healthy_vals and fault_vals:
            bp = ax.boxplot([healthy_vals, fault_vals], labels=["健康", "故障"], patch_artist=True)
            bp["boxes"][0].set_facecolor("lightgreen")
            bp["boxes"][1].set_facecolor("salmon")
            ax.set_title(title)
            ax.grid(axis="y", alpha=0.3)
    save_figure(fig, "metrics_boxplot.png", "gear")

    fig, ax = plt.subplots(figsize=(8, 5))
    healthy_hs = [r["health_score"] for r in results if r["fault_label"] == "healthy"]
    fault_hs = [r["health_score"] for r in results if r["fault_label"] != "healthy"]
    if healthy_hs and fault_hs:
        ax.hist(healthy_hs, bins=10, alpha=0.6, label="健康", color="green")
        ax.hist(fault_hs, bins=10, alpha=0.6, label="故障", color="red")
        ax.axvline(x=85, color="black", linestyle="--", label="阈值=85")
        ax.set_xlabel("健康度")
        ax.set_ylabel("频数")
        ax.set_title("WTgearbox 健康度分布")
        ax.legend()
        ax.grid(axis="y", alpha=0.3)
    save_figure(fig, "health_score_distribution.png", "gear")


def _generate_gear_report(results: List[Dict]) -> str:
    lines = [
        "# 齿轮诊断算法评价报告",
        "",
        "> 数据集: WTgearbox 行星齿轮箱 (恒速 20~55Hz)",
        "> 评价指标: SER | FM0 | FM4 | CAR | M6A | M8A | TSA峭度 | 健康度",
        "",
        "## 1. 方法概述",
        "",
        "| 指标 | 用途 | 健康基准 | 故障趋势 |",
        "|------|------|---------|---------|",
        "| SER | 边频带能量比 | 低 | 升高 |",
        "| FM0 | 粗故障检测 | 低 | 升高 |",
        "| FM4 | 局部故障(点蚀/裂纹) | ~3 | >3 |",
        "| CAR | 倒频谱幅值比 | 低 | 升高 |",
        "| M6A/M8A | 表面损伤高阶矩 | 低 | 升高 |",
        "| TSA Kurt | 残差峭度 | 低 | 升高 |",
        "",
        "## 2. 指标统计对比 (健康 vs 故障)",
        "",
    ]
    metrics = ["ser", "fm0", "fm4", "car", "m6a", "m8a", "tsa_kurt"]
    lines.append("| 指标 | 健康均值 | 健康标准差 | 故障均值 | 故障标准差 | 分离度 |")
    lines.append("|------|----------|-----------|----------|-----------|--------|")
    for key in metrics:
        h_vals = [r[key] for r in results if r["fault_label"] == "healthy"]
        f_vals = [r[key] for r in results if r["fault_label"] != "healthy"]
        if h_vals and f_vals:
            h_mean, h_std = np.mean(h_vals), np.std(h_vals)
            f_mean, f_std = np.mean(f_vals), np.std(f_vals)
            sep = f_mean - h_mean
            lines.append(f"| {key.upper()} | {h_mean:.4f} | {h_std:.4f} | {f_mean:.4f} | {f_std:.4f} | {sep:.4f} |")
        else:
            lines.append(f"| {key.upper()} | N/A | N/A | N/A | N/A | N/A |")

    lines.extend(["", "## 3. 分类性能", ""])
    healthy_hs = [r["health_score"] for r in results if r["fault_label"] == "healthy"]
    fault_hs = [r["health_score"] for r in results if r["fault_label"] != "healthy"]
    if healthy_hs and fault_hs:
        det_rate = sum(1 for h in fault_hs if h < 85) / len(fault_hs)
        fa_rate = sum(1 for h in healthy_hs if h < 85) / len(healthy_hs)
        sep = np.mean(healthy_hs) - np.mean(fault_hs)
        lines.append(f"- 故障检出率: {det_rate:.2%}")
        lines.append(f"- 健康误报率: {fa_rate:.2%}")
        lines.append(f"- 分离度: {sep:.2f}")

    lines.extend(["", "## 4. 各故障类型健康度", "",
                  "| 故障类型 | 样本数 | 平均健康度 | 标准差 |",
                  "|----------|--------|-----------|--------|"])
    labels = sorted(set(r["fault_label"] for r in results))
    for lbl in labels:
        hs = [r["health_score"] for r in results if r["fault_label"] == lbl]
        lines.append(f"| {lbl} | {len(hs)} | {np.mean(hs):.1f} | {np.std(hs):.1f} |")

    lines.extend(["", "## 5. 结论与建议", "", "### 5.1 指标有效性排序", ""])
    sep_scores = {}
    for key in metrics:
        h_vals = [r[key] for r in results if r["fault_label"] == "healthy"]
        f_vals = [r[key] for r in results if r["fault_label"] != "healthy"]
        if h_vals and f_vals:
            sep_scores[key] = abs(np.mean(f_vals) - np.mean(h_vals))
    sorted_metrics = sorted(sep_scores.items(), key=lambda x: x[1], reverse=True)
    for i, (key, score) in enumerate(sorted_metrics, 1):
        lines.append(f"{i}. **{key.upper()}** (分离度={score:.4f})")

    lines.extend(["",
        "### 5.3 场景推荐",
        "",
        "| 场景 | 推荐指标 | 理由 |",
        "|------|---------|------|",
        "| 快速筛查 | SER + FM0 | 计算快，趋势明显 |",
        "| 早期损伤 | FM4 + TSA Kurt | 对局部缺陷敏感 |",
        "| 趋势跟踪 | CAR + NA4 | 随损伤扩展单调上升 |",
        "| 全面分析 | 全部指标 + 行星解调 | 覆盖各类故障模式 |",
        "",
    ])
    return "\n".join(lines)
