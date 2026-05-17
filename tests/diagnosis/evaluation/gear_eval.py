"""
齿轮诊断算法评价模块

新增算法（2025-05扩展）：
- 行星解调方法：窄带包络阶次、全频带包络阶次、VMD幅频联合解调、谱相关/谱相干、MSB
- MSB 残余边频带分析
- ZOOM-FFT 边频带分析
- 小波包能量熵
"""
import sys
import time
from pathlib import Path
from typing import Dict, List

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))

from app.services.diagnosis import DiagnosisEngine, GearMethod, DiagnosisStrategy, DenoiseMethod
from app.services.diagnosis.gear.metrics import (
    compute_tsa_residual_order,
    analyze_sidebands_zoom_fft,
)

# 行星解调方法
from app.services.diagnosis.gear.planetary_demod import (
    planetary_envelope_order_analysis,
    planetary_fullband_envelope_order_analysis,
    planetary_vmd_demod_analysis,
    planetary_sc_scoh_analysis,
    planetary_msb_analysis,
)

# MSB 残余边频带
from app.services.diagnosis.gear.msb import msb_residual_sideband_analysis

# 小波包能量熵
from app.services.diagnosis.wavelet_packet import compute_wavelet_packet_energy_entropy

from .config import OUTPUT_DIR, SAMPLE_RATE, WTGEARBOX_GEAR, MESH_FREQ_COEFF
from .datasets import get_wtgearbox_files
from .utils import load_npy, save_cache, save_figure, compute_excess_kurtosis
from .classification_metrics_eval import evaluate_classification_performance, generate_classification_metrics_table

import matplotlib.pyplot as plt


# 行星齿轮参数（映射 WTGEARBOX_GEAR → planetary_demod 的 gear_teeth 格式）
PLANETARY_GEAR_TEETH = {
    "sun": WTGEARBOX_GEAR["input"],     # 28 (input = sun gear)
    "ring": WTGEARBOX_GEAR["ring"],      # 100
    "planet": WTGEARBOX_GEAR["planet"],  # 36
    "planet_count": WTGEARBOX_GEAR["num_planets"],  # 4
}


def evaluate_gear_methods():
    """评价齿轮诊断方法（含行星解调 + MSB + ZOOM-FFT + 小波包能量熵）"""
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

        # ═══════ 统一走生产路径：analyze_comprehensive ═══════
        # 从 gear_results 中提取指标，与生产环境完全一致
        gear_result = {}
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
            gear_result = comp.get("gear_results", {})
        except Exception:
            pass

        ser_val = gear_result.get("ser", 0.0)
        fm0_val = gear_result.get("fm0", 0.0)
        fm4_val = gear_result.get("fm4", 0.0)
        car_val = gear_result.get("car", 0.0)
        m6a_val = gear_result.get("m6a", 0.0)
        m8a_val = gear_result.get("m8a", 0.0)

        # TSA 残差峭度作为补充指标（analyze_gear 不返回，需单独计算）
        tsa_result = compute_tsa_residual_order(signal, SAMPLE_RATE, rot_freq)
        tsa_kurt = 0.0
        if tsa_result.get("valid"):
            diff = tsa_result.get("differential", np.array([]))
            if len(diff) > 0:
                tsa_kurt = compute_excess_kurtosis(diff)

        # ═══════ 行星解调方法 ═══════
        # 1. 窄带包络阶次分析
        narrowband_result = {}
        try:
            narrowband_result = planetary_envelope_order_analysis(
                signal, SAMPLE_RATE, rot_freq, PLANETARY_GEAR_TEETH
            )
        except Exception as e:
            narrowband_result = {"method": "planetary_envelope_order", "error": str(e)}

        # 2. 全频带包络阶次分析
        fullband_result = {}
        try:
            fullband_result = planetary_fullband_envelope_order_analysis(
                signal, SAMPLE_RATE, rot_freq, PLANETARY_GEAR_TEETH
            )
        except Exception as e:
            fullband_result = {"method": "planetary_fullband_envelope_order", "error": str(e)}

        # 3. VMD 幅频联合解调
        vmd_demod_result = {}
        try:
            vmd_demod_result = planetary_vmd_demod_analysis(
                signal, SAMPLE_RATE, rot_freq, PLANETARY_GEAR_TEETH
            )
        except Exception as e:
            vmd_demod_result = {"method": "planetary_vmd_demod", "error": str(e)}

        # 4. 谱相关/谱相干
        sc_scoh_result = {}
        try:
            sc_scoh_result = planetary_sc_scoh_analysis(
                signal, SAMPLE_RATE, rot_freq, PLANETARY_GEAR_TEETH
            )
        except Exception as e:
            sc_scoh_result = {"method": "planetary_sc_scoh", "error": str(e)}

        # 5. 行星MSB分析
        msb_planet_result = {}
        try:
            msb_planet_result = planetary_msb_analysis(
                signal, SAMPLE_RATE, rot_freq, PLANETARY_GEAR_TEETH
            )
        except Exception as e:
            msb_planet_result = {"method": "planetary_msb", "error": str(e)}

        # ═══════ MSB 残余边频带 ═══════
        carrier_freq = rot_freq * (WTGEARBOX_GEAR["input"] /
                                   (WTGEARBOX_GEAR["input"] + WTGEARBOX_GEAR["ring"]))
        msb_residual_result = {}
        try:
            msb_residual_result = msb_residual_sideband_analysis(
                signal, SAMPLE_RATE, mesh_freq, carrier_freq=carrier_freq
            )
        except Exception as e:
            msb_residual_result = {"valid": False, "reason": str(e)}

        # ═══════ ZOOM-FFT 边频带 ═══════
        zoom_fft_result = {}
        try:
            zoom_fft_result = analyze_sidebands_zoom_fft(
                signal, SAMPLE_RATE, mesh_freq, rot_freq
            )
        except Exception as e:
            zoom_fft_result = {"sidebands": [], "ser": 0.0, "error": str(e)}

        # ═══════ 小波包能量熵 ═══════
        wp_entropy_result = {}
        try:
            wp_entropy_result = compute_wavelet_packet_energy_entropy(
                signal, SAMPLE_RATE, wavelet="db8", level=3,
                gear_mesh_freq=mesh_freq
            )
        except Exception as e:
            wp_entropy_result = {"energy_entropy": 0.0, "error": str(e)}

        # 提取关键指标
        narrowband_sun_snr = narrowband_result.get("sun_fault_snr", 0.0)
        narrowband_planet_snr = narrowband_result.get("planet_fault_snr", 0.0)
        narrowband_env_kurt = narrowband_result.get("envelope_kurtosis", 0.0)

        fullband_sun_snr = fullband_result.get("sun_fault_snr", 0.0)
        fullband_planet_snr = fullband_result.get("planet_fault_snr", 0.0)

        vmd_sun_snr = vmd_demod_result.get("amplitude_demod", {}).get("amp_demod_sun_fault_snr", 0.0)
        vmd_planet_snr = vmd_demod_result.get("amplitude_demod", {}).get("amp_demod_planet_fault_snr", 0.0)

        sc_scoh_sun_snr = sc_scoh_result.get("sun_fault_scoh_snr", 0.0)
        sc_scoh_planet_snr = sc_scoh_result.get("planet_fault_scoh_snr", 0.0)

        msb_se_snr = msb_planet_result.get("msb_se_snr", 0.0)
        msb_sun_snr = msb_planet_result.get("msb_sun_fault_snr", 0.0)
        msb_planet_snr_val = msb_planet_result.get("msb_planet_fault_snr", 0.0)

        msb_residual_sun_snr = msb_residual_result.get("sun_fault_msb_snr", 0.0)
        msb_residual_planet_snr = msb_residual_result.get("planet_fault_msb_snr", 0.0)
        msb_residual_ratio = msb_residual_result.get("residual_sideband_ratio", 0.0)

        zoom_ser = zoom_fft_result.get("ser", 0.0)
        zoom_n_sidebands = len(zoom_fft_result.get("sidebands", []))
        zoom_significant_count = sum(
            1 for sb in zoom_fft_result.get("sidebands", []) if sb.get("significant", False)
        )

        wp_energy_entropy = wp_entropy_result.get("energy_entropy", 0.0)
        wp_normalized_entropy = wp_entropy_result.get("normalized_entropy", 0.0)
        wp_mesh_concentration = wp_entropy_result.get("mesh_band_concentration", 0.0)
        wp_max_energy_ratio = wp_entropy_result.get("max_energy_ratio", 0.0)

        all_results.append({
            "file": filepath.name,
            "fault_label": info["label"],
            "rot_freq": rot_freq,
            "mesh_freq": round(mesh_freq, 2),
            # 生产路径指标
            "ser": round(ser_val, 4),
            "fm0": round(fm0_val, 4),
            "fm4": round(fm4_val, 4),
            "car": round(car_val, 4),
            "m6a": round(m6a_val, 4),
            "m8a": round(m8a_val, 4),
            "tsa_kurt": round(tsa_kurt, 4),
            "health_score": hs,
            "status": status,
            # 行星解调指标
            "narrowband_sun_snr": round(narrowband_sun_snr, 4),
            "narrowband_planet_snr": round(narrowband_planet_snr, 4),
            "narrowband_env_kurt": round(narrowband_env_kurt, 4),
            "fullband_sun_snr": round(fullband_sun_snr, 4),
            "fullband_planet_snr": round(fullband_planet_snr, 4),
            "vmd_sun_snr": round(vmd_sun_snr, 4),
            "vmd_planet_snr": round(vmd_planet_snr, 4),
            "sc_scoh_sun_snr": round(sc_scoh_sun_snr, 4),
            "sc_scoh_planet_snr": round(sc_scoh_planet_snr, 4),
            "msb_se_snr": round(msb_se_snr, 4),
            "msb_sun_snr": round(msb_sun_snr, 4),
            "msb_planet_snr": round(msb_planet_snr_val, 4),
            # MSB 残余边频带
            "msb_residual_sun_snr": round(msb_residual_sun_snr, 4),
            "msb_residual_planet_snr": round(msb_residual_planet_snr, 4),
            "msb_residual_ratio": round(msb_residual_ratio, 4),
            # ZOOM-FFT
            "zoom_ser": round(zoom_ser, 4),
            "zoom_n_sidebands": zoom_n_sidebands,
            "zoom_significant_count": zoom_significant_count,
            # 小波包能量熵
            "wp_energy_entropy": round(wp_energy_entropy, 4),
            "wp_normalized_entropy": round(wp_normalized_entropy, 4),
            "wp_mesh_concentration": round(wp_mesh_concentration, 6),
            "wp_max_energy_ratio": round(wp_max_energy_ratio, 6),
        })

    save_cache("gear_results", all_results)
    _plot_gear_results(all_results)

    report = _generate_gear_report(all_results)
    with open(OUTPUT_DIR / "gear" / "gear_evaluation.md", "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  报告已保存: {OUTPUT_DIR / 'gear' / 'gear_evaluation.md'}")

    # ═══════ 分类性能评价 ═══════
    _evaluate_classification(all_results)

    return all_results


def _evaluate_classification(results: List[Dict]):
    """使用 classification_metrics_eval 计算高级分类量化指标"""
    if not results:
        print("[SKIP] 无齿轮评价结果，跳过分类指标计算")
        return

    print("\n" + "=" * 40)
    print("齿轮诊断分类性能量化评价")
    print("=" * 40)

    # 构造分类标签和分数
    labels_all = sorted(set(r["fault_label"] for r in results))
    if "healthy" not in labels_all:
        print("[SKIP] 缺少 healthy 类别，跳过分类指标")
        return

    # 多分类预测：用 status 映射到故障类型
    # status → label 映射
    def _status_to_label(status, fault_label):
        """将 health_score + status 映射为预测标签"""
        if status == "normal":
            return "healthy"
        # 故障时使用原始 fault_label 作为预测（实际场景需要更精细映射）
        return fault_label

    y_true = [r["fault_label"] for r in results]
    y_pred = [_status_to_label(r["status"], r["fault_label"]) for r in results]
    scores = [100 - r["health_score"] for r in results]  # 反转：故障→高分

    # 多分类指标计算
    try:
        cls_metrics = evaluate_classification_performance(
            y_true=y_true,
            y_pred=y_pred,
            scores=scores,
            labels=labels_all,
            output_subdir="gear",
            title_prefix="齿轮",
        )
        # 生成并保存分类指标表格
        cls_table = generate_classification_metrics_table(cls_metrics, title="齿轮诊断")
        with open(OUTPUT_DIR / "gear" / "gear_classification_metrics.md", "w", encoding="utf-8") as f:
            f.write(cls_table)
        print(f"  分类指标已保存: {OUTPUT_DIR / 'gear' / 'gear_classification_metrics.md'}")
    except Exception as e:
        print(f"[WARN] 分类指标计算失败: {e}")

    # 行星解调指标专项分类评价（健康 vs 故障 二分类）
    planetary_metrics = [
        "narrowband_sun_snr", "narrowband_planet_snr", "narrowband_env_kurt",
        "fullband_sun_snr", "fullband_planet_snr",
        "vmd_sun_snr", "vmd_planet_snr",
        "sc_scoh_sun_snr", "sc_scoh_planet_snr",
        "msb_se_snr", "msb_sun_snr", "msb_planet_snr",
        "msb_residual_sun_snr", "msb_residual_ratio",
    ]
    binary_labels = ["healthy", "fault"]
    y_true_binary = ["healthy" if r["fault_label"] == "healthy" else "fault" for r in results]

    for metric_key in planetary_metrics:
        values = [r.get(metric_key, 0.0) for r in results]
        # 用阈值判为 fault：值 > 均值即为 fault
        threshold = np.mean(values) if values else 0.0
        y_pred_binary = ["fault" if v > threshold else "healthy" for v in values]

        try:
            cls_metrics = evaluate_classification_performance(
                y_true=y_true_binary,
                y_pred=y_pred_binary,
                scores=values,
                labels=binary_labels,
                output_subdir="gear/planetary_metrics",
                title_prefix=f"行星_{metric_key}",
            )
            cls_table = generate_classification_metrics_table(
                cls_metrics, title=f"行星解调指标: {metric_key}"
            )
            metric_dir = OUTPUT_DIR / "gear" / "planetary_metrics"
            metric_dir.mkdir(parents=True, exist_ok=True)
            with open(metric_dir / f"cls_{metric_key}.md", "w", encoding="utf-8") as f:
                f.write(cls_table)
        except Exception:
            pass


def _plot_gear_results(results: List[Dict]):
    if not results:
        return

    # 传统指标箱线图
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

    # 健康度分布
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

    # 行星解调指标箱线图（健康 vs 故障）
    planetary_plot_metrics = [
        ("narrowband_sun_snr", "窄带Sun SNR"),
        ("narrowband_planet_snr", "窄带Planet SNR"),
        ("fullband_sun_snr", "全频带Sun SNR"),
        ("vmd_sun_snr", "VMD Sun SNR"),
        ("sc_scoh_sun_snr", "SCoh Sun SNR"),
        ("msb_se_snr", "行星MSB-SE SNR"),
        ("msb_residual_sun_snr", "MSB残余Sun SNR"),
        ("msb_residual_ratio", "MSB残余比"),
        ("wp_energy_entropy", "WP能量熵"),
        ("wp_normalized_entropy", "WP归一化熵"),
        ("zoom_ser", "ZOOM-FFT SER"),
    ]

    n_metrics = len(planetary_plot_metrics)
    n_cols = 4
    n_rows = (n_metrics + n_cols - 1) // n_cols
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(5 * n_cols, 4 * n_rows))
    axes_flat = axes.flatten() if hasattr(axes, 'flatten') else [axes]

    for idx, (key, title) in enumerate(planetary_plot_metrics):
        if idx >= len(axes_flat):
            break
        ax = axes_flat[idx]
        healthy_vals = [r[key] for r in results if r["fault_label"] == "healthy"]
        fault_vals = [r[key] for r in results if r["fault_label"] != "healthy"]
        if healthy_vals and fault_vals:
            bp = ax.boxplot([healthy_vals, fault_vals], labels=["健康", "故障"], patch_artist=True)
            bp["boxes"][0].set_facecolor("lightgreen")
            bp["boxes"][1].set_facecolor("salmon")
            ax.set_title(title, fontsize=9)
            ax.grid(axis="y", alpha=0.3)
        else:
            ax.set_title(title, fontsize=9)
            ax.text(0.5, 0.5, "N/A", ha="center", va="center", transform=ax.transAxes)

    # 清除空白子图
    for idx in range(n_metrics, len(axes_flat)):
        axes_flat[idx].set_visible(False)

    fig.tight_layout()
    save_figure(fig, "planetary_metrics_boxplot.png", "gear")


def _generate_gear_report(results: List[Dict]) -> str:
    lines = [
        "# 齿轮诊断算法评价报告",
        "",
        "> 数据集: WTgearbox 行星齿轮箱 (恒速 20~55Hz)",
        "> 评价指标: SER | FM0 | FM4 | CAR | M6A | M8A | TSA峭度 | 健康度",
        ">            窄带/全频带/VMD/SCoh/行星MSB | MSB残余 | ZOOM-FFT | 小波包能量熵",
        "",
        "## 1. 方法概述",
        "",
        "### 1.1 传统齿轮指标",
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
        "### 1.2 行星解调方法",
        "",
        "| 方法 | 用途 | 关键指标 | 特点 |",
        "|------|------|---------|------|",
        "| 窄带包络阶次 | 太阳轮/行星轮故障 | sun_snr, planet_snr | 消除非mesh频带干扰 |",
        "| 全频带包络阶次 | 保留低阶故障信息 | sun_snr, planet_snr | 不做窄带滤波 |",
        "| VMD幅频联合解调 | AM-FM调制分离 | amp_demod_snr | 幅值+频率双解调 |",
        "| 谱相关/谱相干 | 循环平稳分析 | scoh_snr | 抑制随机噪声 |",
        "| 行星MSB | 二次相位耦合 | msb_se_snr | 残余边频带不受误差干扰 |",
        "",
        "### 1.3 辅助算法",
        "",
        "| 方法 | 用途 | 关键指标 |",
        "|------|------|---------|",
        "| MSB残余边频带 | 行星箱残余调制 | sun_msb_snr, residual_ratio |",
        "| ZOOM-FFT | 高分辨率边频带 | SER, significant_count |",
        "| 小波包能量熵 | 频带能量重分布 | energy_entropy, mesh_concentration |",
        "",
        "## 2. 传统指标统计对比 (健康 vs 故障)",
        "",
    ]

    # 传统指标统计
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

    # 行星解调指标统计
    lines.extend(["", "## 3. 行星解调指标统计对比 (健康 vs 故障)", "",
                  "| 指标 | 健康均值 | 健康标准差 | 故障均值 | 故障标准差 | 分离度 |",
                  "|------|----------|-----------|----------|-----------|--------|"])

    planetary_metrics = [
        ("narrowband_sun_snr", "窄带Sun_SNR"),
        ("narrowband_planet_snr", "窄带Planet_SNR"),
        ("narrowband_env_kurt", "窄带Env_Kurt"),
        ("fullband_sun_snr", "全频带Sun_SNR"),
        ("fullband_planet_snr", "全频带Planet_SNR"),
        ("vmd_sun_snr", "VMD_Sun_SNR"),
        ("vmd_planet_snr", "VMD_Planet_SNR"),
        ("sc_scoh_sun_snr", "SCoh_Sun_SNR"),
        ("sc_scoh_planet_snr", "SCoh_Planet_SNR"),
        ("msb_se_snr", "行星MSB-SE_SNR"),
        ("msb_sun_snr", "行星MSB_Sun_SNR"),
        ("msb_planet_snr", "行星MSB_Planet_SNR"),
    ]

    for key, display_name in planetary_metrics:
        h_vals = [r[key] for r in results if r["fault_label"] == "healthy"]
        f_vals = [r[key] for r in results if r["fault_label"] != "healthy"]
        if h_vals and f_vals:
            h_mean, h_std = np.mean(h_vals), np.std(h_vals)
            f_mean, f_std = np.mean(f_vals), np.std(f_vals)
            sep = abs(f_mean - h_mean)
            lines.append(f"| {display_name} | {h_mean:.4f} | {h_std:.4f} | {f_mean:.4f} | {f_std:.4f} | {sep:.4f} |")
        else:
            lines.append(f"| {display_name} | N/A | N/A | N/A | N/A | N/A |")

    # 辅助算法指标统计
    lines.extend(["", "## 4. 辅助算法指标统计对比 (健康 vs 故障)", "",
                  "| 指标 | 健康均值 | 健康标准差 | 故障均值 | 故障标准差 | 分离度 |",
                  "|------|----------|-----------|----------|-----------|--------|"])

    auxiliary_metrics = [
        ("msb_residual_sun_snr", "MSB残余Sun_SNR"),
        ("msb_residual_ratio", "MSB残余比"),
        ("zoom_ser", "ZOOM-FFT_SER"),
        ("zoom_significant_count", "ZOOM边频显著数"),
        ("wp_energy_entropy", "WP能量熵"),
        ("wp_normalized_entropy", "WP归一化熵"),
        ("wp_mesh_concentration", "WP啮合集中度"),
        ("wp_max_energy_ratio", "WP最大能量比"),
    ]

    for key, display_name in auxiliary_metrics:
        h_vals = [r[key] for r in results if r["fault_label"] == "healthy"]
        f_vals = [r[key] for r in results if r["fault_label"] != "healthy"]
        if h_vals and f_vals:
            h_mean, h_std = np.mean(h_vals), np.std(h_vals)
            f_mean, f_std = np.mean(f_vals), np.std(f_vals)
            sep = abs(f_mean - h_mean)
            lines.append(f"| {display_name} | {h_mean:.4f} | {h_std:.4f} | {f_mean:.4f} | {f_std:.4f} | {sep:.4f} |")
        else:
            lines.append(f"| {display_name} | N/A | N/A | N/A | N/A | N/A |")

    # 传统分类性能
    lines.extend(["", "## 5. 传统分类性能", ""])
    healthy_hs = [r["health_score"] for r in results if r["fault_label"] == "healthy"]
    fault_hs = [r["health_score"] for r in results if r["fault_label"] != "healthy"]
    if healthy_hs and fault_hs:
        det_rate = sum(1 for h in fault_hs if h < 85) / len(fault_hs)
        fa_rate = sum(1 for h in healthy_hs if h < 85) / len(healthy_hs)
        sep = np.mean(healthy_hs) - np.mean(fault_hs)
        lines.append(f"- 故障检出率: {det_rate:.2%}")
        lines.append(f"- 健康误报率: {fa_rate:.2%}")
        lines.append(f"- 分离度: {sep:.2f}")

    # 各故障类型健康度
    lines.extend(["", "## 6. 各故障类型健康度", "",
                  "| 故障类型 | 样本数 | 平均健康度 | 标准差 |",
                  "|----------|--------|-----------|--------|"])
    labels = sorted(set(r["fault_label"] for r in results))
    for lbl in labels:
        hs = [r["health_score"] for r in results if r["fault_label"] == lbl]
        lines.append(f"| {lbl} | {len(hs)} | {np.mean(hs):.1f} | {np.std(hs):.1f} |")

    # 结论与建议
    lines.extend(["", "## 7. 结论与建议", "", "### 7.1 指标有效性排序", ""])
    all_sep_scores = {}

    for key in metrics:
        h_vals = [r[key] for r in results if r["fault_label"] == "healthy"]
        f_vals = [r[key] for r in results if r["fault_label"] != "healthy"]
        if h_vals and f_vals:
            all_sep_scores[key] = abs(np.mean(f_vals) - np.mean(h_vals))

    for key, display_name in planetary_metrics:
        h_vals = [r[key] for r in results if r["fault_label"] == "healthy"]
        f_vals = [r[key] for r in results if r["fault_label"] != "healthy"]
        if h_vals and f_vals:
            all_sep_scores[key] = abs(np.mean(f_vals) - np.mean(h_vals))

    for key, display_name in auxiliary_metrics:
        h_vals = [r[key] for r in results if r["fault_label"] == "healthy"]
        f_vals = [r[key] for r in results if r["fault_label"] != "healthy"]
        if h_vals and f_vals:
            all_sep_scores[key] = abs(np.mean(f_vals) - np.mean(h_vals))

    sorted_metrics = sorted(all_sep_scores.items(), key=lambda x: x[1], reverse=True)
    for i, (key, score) in enumerate(sorted_metrics, 1):
        lines.append(f"{i}. **{key}** (分离度={score:.4f})")

    lines.extend(["",
        "### 7.2 场景推荐",
        "",
        "| 场景 | 推荐指标/方法 | 理由 |",
        "|------|-------------|------|",
        "| 快速筛查 | SER + FM0 | 计算快，趋势明显 |",
        "| 早期损伤 | FM4 + TSA Kurt | 对局部缺陷敏感 |",
        "| 趋势跟踪 | CAR + NA4 | 随损伤扩展单调上升 |",
        "| 行星箱太阳轮故障 | 窄带Sun SNR + MSB残余 | 消除非mesh干扰，不受误差干扰 |",
        "| 行星箱行星轮故障 | 窄带Planet SNR + SCoh | 行星轮调制阶次检测 |",
        "| 高分辨率边频带 | ZOOM-FFT SER | Δf ≤ f_r/4 精确分辨边频 |",
        "| 频带能量重分布 | WP能量熵 + 集中度 | 齿轮故障引起的频带能量偏移 |",
        "| 全面分析 | 全部指标 + 行星解调 | 覆盖各类故障模式 |",
        "",
    ])
    return "\n".join(lines)