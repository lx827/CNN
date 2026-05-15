"""
行星齿轮箱专用诊断算法模块

包含：
- Level 2: 窄带包络阶次分析 (Narrowband Envelope Order Analysis)
  对 mesh_order 频带做窄带滤波 → Hilbert 包络 → 阶次谱，搜索 sun/planet/carrier 故障阶次
- Level 3: VMD 幅频联合解调 (VMD Joint Amplitude-Frequency Demodulation)
  VMD 分解 → 敏感 IMF 选择 → 幅值解调谱 + 频率解调谱
- 评估函数：将解调结果映射到 fault_indicators
"""
import numpy as np
from scipy.signal import hilbert as scipy_hilbert
from typing import Dict, Optional, Tuple

from ..signal_utils import (
    bandpass_filter,
    lowpass_filter,
    prepare_signal,
)
from ..order_tracking import _compute_order_spectrum, _compute_order_spectrum_multi_frame
from ..gear.metrics import _order_band_amplitude


def _local_background(oa, os, center, half_bw=0.5, side_bw=1.5):
    """
    局部背景估计：用目标阶次两侧 ±(half_bw+side_bw) ~ ±half_bw 的幅值均值作为背景。

    相比全局中位数，局部背景避免了窄带滤波后>5阶区域几乎无能量导致的SNR虚高问题。
    sun_fault_order=3.125 的局部背景 = 1.625~2.625 和 3.625~4.625 阶次的幅值均值。
    """
    side_low_start = center - half_bw - side_bw
    side_low_end = center - half_bw
    side_high_start = center + half_bw
    side_high_end = center + half_bw + side_bw
    mask = ((oa >= side_low_start) & (oa <= side_low_end)) | \
           ((oa >= side_high_start) & (oa <= side_high_end))
    if np.any(mask):
        return float(np.mean(os[mask]))
    # fallback: 全局中位数（排除<0.5阶DC区域）
    valid = oa > 0.5
    if np.any(valid):
        return float(np.median(os[valid]))
    return float(np.median(os))


def _band_median_background(oa, os, max_order=5.0):
    """
    频带内中位数背景：对阶次谱在 0.5~max_order 阶范围内取中位数。

    适用于窄带滤波后的阶次谱（>max_order 阶区域几乎无能量）。
    """
    mask = (oa > 0.5) & (oa <= max_order)
    if np.any(mask):
        return float(np.median(os[mask]))
    valid = oa > 0.5
    if np.any(valid):
        return float(np.median(os[valid]))
    return float(np.median(os))


def _envelope_order_spectrum(
    signal: np.ndarray,
    fs: float,
    rot_freq: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    对信号做 Hilbert 包络 → 去DC → 阶次谱

    Returns:
        (order_axis, envelope_order_spectrum)
    """
    # Hilbert 包络
    analytic = scipy_hilbert(signal)
    envelope = np.abs(analytic)
    # 去DC（包络均值对应 carrier 基线，需移除以显露调制成分）
    envelope = envelope - np.mean(envelope)

    # 对包络做阶次谱
    order_axis, order_spectrum = _compute_order_spectrum(
        envelope, fs, rot_freq, samples_per_rev=1024
    )
    return order_axis, order_spectrum


def planetary_envelope_order_analysis(
    signal: np.ndarray,
    fs: float,
    rot_freq: float,
    gear_teeth: Dict,
) -> Dict:
    """
    Level 2: 行星齿轮箱窄带包络阶次分析

    核心思路（Feng & Zuo 2012 / ALGORITHMS.md 2.7.3）：
    行星箱故障不应围绕 mesh_order 做边频带分析，
    而是对 mesh_order 频带做窄带滤波+包络，在包络阶次谱中
    搜索 sun_fault_order / planet_fault_order / carrier_order 峰值。

    Args:
        signal: 原始振动信号
        fs: 采样率
        rot_freq: 估计转频 Hz
        gear_teeth: 齿轮参数 {sun, ring, planet, planet_count}

    Returns:
        {
            "method": "planetary_envelope_order",
            "sun_fault_snr": float,
            "planet_fault_snr": float,
            "carrier_snr": float,
            "sun_fault_significant": bool,
            "planet_fault_significant": bool,
            "carrier_significant": bool,
            "sun_fault_amp": float,
            "planet_fault_amp": float,
            "carrier_amp": float,
            "background_median": float,
            "mesh_band_snr": float,     # mesh_order 带内包络谱 SNR
            "envelope_kurtosis": float,  # 包络信号峭度
        }
    """
    z_sun = int(gear_teeth.get("sun") or 0)
    z_ring = int(gear_teeth.get("ring") or 0)
    planet_count = int(gear_teeth.get("planet_count") or 0)

    if planet_count < 3 or z_sun <= 0 or z_ring <= 0:
        return {"method": "planetary_envelope_order", "error": "not_planetary"}

    # 特征阶次
    mesh_order = round(z_ring * z_sun / (z_sun + z_ring), 4)  # 21.875
    carrier_order = round(z_sun / (z_sun + z_ring), 4)        # 0.21875
    sun_fault_order = round(z_ring / (z_sun + z_ring) * planet_count, 4)  # 3.125
    planet_fault_order = round(z_ring / (z_sun + z_ring), 4)  # 0.78125

    arr = prepare_signal(signal)
    mesh_freq = rot_freq * mesh_order

    # 信号截断至5秒（2GB服务器内存限制）
    max_samples = int(fs * 5)
    if len(arr) > max_samples:
        arr = arr[:max_samples]

    # === Step 1: 窄带滤波 ===
    # 对 mesh_order ± bandwidth 阶次的频带做带通滤波
    # bandwidth = 4 阶次（覆盖 mesh_order 两侧约 2 个 carrier 周期）
    bandwidth_hz = rot_freq * 4.0
    f_low = max(10.0, mesh_freq - bandwidth_hz)
    f_high = min(fs / 2.0 - 10.0, mesh_freq + bandwidth_hz)

    if f_low >= f_high or f_high <= 0:
        return {"method": "planetary_envelope_order", "error": "invalid_bandpass"}

    band_signal = bandpass_filter(arr, fs, f_low, f_high, order=4)

    # === Step 2: Hilbert 包络 ===
    envelope = np.abs(scipy_hilbert(band_signal))
    envelope = envelope - np.mean(envelope)

    # 包络峭度（辅助指标）
    if len(envelope) > 4:
        e_mean = np.mean(envelope)
        e_var = np.var(envelope)
        envelope_kurtosis = float(np.mean((envelope - e_mean) ** 4) / (e_var ** 2 + 1e-12) - 3)
    else:
        envelope_kurtosis = 0.0

    # === Step 3: 对包络做阶次谱 ===
    try:
        env_order_axis, env_order_spectrum = _compute_order_spectrum(
            envelope, fs, rot_freq, samples_per_rev=1024
        )
    except Exception:
        # 阶次谱计算失败时退回全信号包络阶次谱
        try:
            env_order_axis, env_order_spectrum = _envelope_order_spectrum(arr, fs, rot_freq)
        except Exception:
            return {"method": "planetary_envelope_order", "error": "order_spectrum_failed"}

    # === Step 4: 搜索特征故障阶次峰值 ===
    env_oa = np.asarray(env_order_axis)
    env_os = np.asarray(env_order_spectrum)

    # 窄带方法：包络阶次谱只在滤波频带内有能量，>5阶几乎为零
    # 用滤波频带内（0.5~5阶）的中位数作为背景
    background = _band_median_background(env_oa, env_os, max_order=5.0)
    background = max(background, 1e-12)

    # 各特征阶次的幅值
    sun_fault_amp = _order_band_amplitude(env_oa, env_os, sun_fault_order, 0.3)
    planet_fault_amp = _order_band_amplitude(env_oa, env_os, planet_fault_order, 0.3)
    carrier_amp = _order_band_amplitude(env_oa, env_os, carrier_order, 0.3)
    mesh_amp = _order_band_amplitude(env_oa, env_os, mesh_order, 1.0)

    # SNR（相对于频带内背景）
    sun_fault_snr = sun_fault_amp / background
    planet_fault_snr = planet_fault_amp / background
    carrier_snr = carrier_amp / background
    mesh_band_snr = mesh_amp / background

    # 调制深度比（故障阶次相对于 mesh 阶次的幅值比）
    # 行星箱的 sun_fault_order 是固有调制阶次，健康时也有，
    # 但故障时调制深度会增加 → 这个比值的变化才有区分力
    sun_modulation_depth = sun_fault_amp / max(mesh_amp, 1e-12)
    planet_modulation_depth = planet_fault_amp / max(mesh_amp, 1e-12)
    carrier_modulation_depth = carrier_amp / max(mesh_amp, 1e-12)

    # 显著性判定
    SNR_THRESHOLD_WARNING = 3.0
    SNR_THRESHOLD_CRITICAL = 5.0

    return {
        "method": "planetary_envelope_order",
        "mesh_order": mesh_order,
        "carrier_order": carrier_order,
        "sun_fault_order": sun_fault_order,
        "planet_fault_order": planet_fault_order,
        "sun_fault_snr": round(sun_fault_snr, 4),
        "planet_fault_snr": round(planet_fault_snr, 4),
        "carrier_snr": round(carrier_snr, 4),
        "mesh_band_snr": round(mesh_band_snr, 4),
        "sun_fault_amp": round(sun_fault_amp, 4),
        "planet_fault_amp": round(planet_fault_amp, 4),
        "carrier_amp": round(carrier_amp, 4),
        "mesh_amp": round(mesh_amp, 4),
        "background_median": round(background, 4),
        "sun_modulation_depth": round(sun_modulation_depth, 4),
        "planet_modulation_depth": round(planet_modulation_depth, 4),
        "carrier_modulation_depth": round(carrier_modulation_depth, 4),
        "sun_fault_significant": sun_fault_snr > SNR_THRESHOLD_WARNING,
        "planet_fault_significant": planet_fault_snr > SNR_THRESHOLD_WARNING,
        "carrier_significant": carrier_snr > SNR_THRESHOLD_WARNING,
        "sun_fault_warning": sun_fault_snr > SNR_THRESHOLD_WARNING,
        "sun_fault_critical": sun_fault_snr > SNR_THRESHOLD_CRITICAL,
        "planet_fault_warning": planet_fault_snr > SNR_THRESHOLD_WARNING,
        "planet_fault_critical": planet_fault_snr > SNR_THRESHOLD_CRITICAL,
        "carrier_warning": carrier_snr > SNR_THRESHOLD_WARNING,
        "carrier_critical": carrier_snr > SNR_THRESHOLD_CRITICAL,
        "envelope_kurtosis": round(envelope_kurtosis, 4),
        "bandpass_f_low": round(f_low, 2),
        "bandpass_f_high": round(f_high, 2),
    }


def planetary_fullband_envelope_order_analysis(
    signal: np.ndarray,
    fs: float,
    rot_freq: float,
    gear_teeth: Dict,
) -> Dict:
    """
    Level 2b: 全频带包络阶次分析（不做窄带滤波）

    对完整信号做 Hilbert 包络 → 阶次谱，搜索故障阶次。
    适用于窄带滤波可能丢失低阶故障信息的场景。

    与窄带版本的区别：不做 bandpass_filter，直接对全信号包络做阶次谱。
    """
    z_sun = int(gear_teeth.get("sun") or 0)
    z_ring = int(gear_teeth.get("ring") or 0)
    planet_count = int(gear_teeth.get("planet_count") or 0)

    if planet_count < 3 or z_sun <= 0 or z_ring <= 0:
        return {"method": "planetary_fullband_envelope_order", "error": "not_planetary"}

    mesh_order = round(z_ring * z_sun / (z_sun + z_ring), 4)
    carrier_order = round(z_sun / (z_sun + z_ring), 4)
    sun_fault_order = round(z_ring / (z_sun + z_ring) * planet_count, 4)
    planet_fault_order = round(z_ring / (z_sun + z_ring), 4)

    arr = prepare_signal(signal)
    max_samples = int(fs * 5)
    if len(arr) > max_samples:
        arr = arr[:max_samples]

    # Hilbert 包络
    envelope = np.abs(scipy_hilbert(arr))
    envelope = envelope - np.mean(envelope)

    # 包络阶次谱
    try:
        env_order_axis, env_order_spectrum = _compute_order_spectrum(
            envelope, fs, rot_freq, samples_per_rev=1024
        )
    except Exception:
        return {"method": "planetary_fullband_envelope_order", "error": "order_spectrum_failed"}

    env_oa = np.asarray(env_order_axis)
    env_os = np.asarray(env_order_spectrum)

    # 全频带方法：全局中位数作为背景（包络阶次谱全频带都有能量）
    global_bg = float(np.median(env_os[env_oa > 0.5])) if np.any(env_oa > 0.5) else 1e-12
    background = max(global_bg, 1e-12)

    sun_fault_amp = _order_band_amplitude(env_oa, env_os, sun_fault_order, 0.3)
    planet_fault_amp = _order_band_amplitude(env_oa, env_os, planet_fault_order, 0.3)
    carrier_amp = _order_band_amplitude(env_oa, env_os, carrier_order, 0.3)
    mesh_amp = _order_band_amplitude(env_oa, env_os, mesh_order, 1.0)

    sun_fault_snr = sun_fault_amp / background
    planet_fault_snr = planet_fault_amp / background
    carrier_snr = carrier_amp / background

    # 调制深度比
    sun_modulation_depth = sun_fault_amp / max(mesh_amp, 1e-12)
    planet_modulation_depth = planet_fault_amp / max(mesh_amp, 1e-12)
    carrier_modulation_depth = carrier_amp / max(mesh_amp, 1e-12)

    # 包络峭度
    if len(envelope) > 4:
        e_mean = np.mean(envelope)
        e_var = np.var(envelope)
        envelope_kurtosis = float(np.mean((envelope - e_mean) ** 4) / (e_var ** 2 + 1e-12) - 3)
    else:
        envelope_kurtosis = 0.0

    SNR_THRESHOLD_WARNING = 3.0
    SNR_THRESHOLD_CRITICAL = 5.0

    return {
        "method": "planetary_fullband_envelope_order",
        "mesh_order": mesh_order,
        "carrier_order": carrier_order,
        "sun_fault_order": sun_fault_order,
        "planet_fault_order": planet_fault_order,
        "sun_fault_snr": round(sun_fault_snr, 4),
        "planet_fault_snr": round(planet_fault_snr, 4),
        "carrier_snr": round(carrier_snr, 4),
        "sun_fault_amp": round(sun_fault_amp, 4),
        "planet_fault_amp": round(planet_fault_amp, 4),
        "carrier_amp": round(carrier_amp, 4),
        "mesh_amp": round(mesh_amp, 4),
        "background_median": round(background, 4),
        "sun_modulation_depth": round(sun_modulation_depth, 4),
        "planet_modulation_depth": round(planet_modulation_depth, 4),
        "carrier_modulation_depth": round(carrier_modulation_depth, 4),
        "envelope_kurtosis": round(envelope_kurtosis, 4),
        "sun_fault_significant": sun_fault_snr > SNR_THRESHOLD_WARNING,
        "planet_fault_significant": planet_fault_snr > SNR_THRESHOLD_WARNING,
        "carrier_significant": carrier_snr > SNR_THRESHOLD_WARNING,
        "sun_fault_warning": sun_fault_snr > SNR_THRESHOLD_WARNING,
        "sun_fault_critical": sun_fault_snr > SNR_THRESHOLD_CRITICAL,
        "planet_fault_warning": planet_fault_snr > SNR_THRESHOLD_WARNING,
        "planet_fault_critical": planet_fault_snr > SNR_THRESHOLD_CRITICAL,
        "carrier_warning": carrier_snr > SNR_THRESHOLD_WARNING,
        "carrier_critical": carrier_snr > SNR_THRESHOLD_CRITICAL,
    }


def planetary_vmd_demod_analysis(
    signal: np.ndarray,
    fs: float,
    rot_freq: float,
    gear_teeth: Dict,
    max_K: int = 5,
) -> Dict:
    """
    Level 3: VMD 幅频联合解调分析（Feng, Zhang & Zuo 2017）

    VMD 分解 → 选择围绕 mesh_freq 的敏感 IMF →
    幅值解调谱（包络谱）+ 频率解调谱（瞬时频率谱）

    Args:
        signal: 原始振动信号
        fs: 采样率
        rot_freq: 估计转频 Hz
        gear_teeth: 齿轮参数
        max_K: VMD 最大模态数（2GB服务器限制 K≤5）

    Returns:
        {
            "method": "planetary_vmd_demod",
            "imf_count": int,
            "selected_imf_index": int,
            "selected_imf_center_freq": float,
            "amplitude_demod": Dict,   # 幅值解调结果
            "frequency_demod": Dict,   # 频率解调结果
        }
    """
    from ..vmd_denoise import _vmd_core

    z_sun = int(gear_teeth.get("sun") or 0)
    z_ring = int(gear_teeth.get("ring") or 0)
    planet_count = int(gear_teeth.get("planet_count") or 0)

    if planet_count < 3 or z_sun <= 0 or z_ring <= 0:
        return {"method": "planetary_vmd_demod", "error": "not_planetary"}

    mesh_order = round(z_ring * z_sun / (z_sun + z_ring), 4)
    carrier_order = round(z_sun / (z_sun + z_ring), 4)
    sun_fault_order = round(z_ring / (z_sun + z_ring) * planet_count, 4)
    planet_fault_order = round(z_ring / (z_sun + z_ring), 4)

    arr = prepare_signal(signal)
    # 信号截断至5秒
    max_samples = int(fs * 5)
    if len(arr) > max_samples:
        arr = arr[:max_samples]

    mesh_freq = rot_freq * mesh_order

    # VMD 分解
    K = min(max_K, int(fs / (2 * mesh_freq + 1)))
    K = max(2, K)  # 至少2个模态
    try:
        u, u_hat, omega = _vmd_core(
            arr, alpha=2000, tau=0, K=K, DC=False, init=1, tol=1e-6
        )
    except Exception:
        return {"method": "planetary_vmd_demod", "error": "vmd_failed"}

    # === 敏感 IMF 选择 ===
    # 选择中心频率最接近 mesh_freq 的 IMF
    imf_center_freqs = omega[-1]  # 最终迭代的中心频率
    # omega 返回形状: (max_iter+1, K) — 取最后一行
    if imf_center_freqs.ndim == 0:
        # 单模态情况
        selected_idx = 0
        selected_center = float(imf_center_freqs)
    else:
        selected_idx = int(np.argmin(np.abs(imf_center_freqs - mesh_freq)))
        selected_center = float(imf_center_freqs[selected_idx])

    sensitive_imf = u[selected_idx]

    # === 经验 AM-FM 分解 ===
    # 幅值包络 a(t)
    analytic = scipy_hilbert(sensitive_imf)
    amplitude_envelope = np.abs(analytic)
    # 载波 c(t) = x(t) / a(t)，避免 a(t)=0 处奇异
    carrier = sensitive_imf / (amplitude_envelope + 1e-12)

    # === 幅值解调谱 ===
    # 对 a(t) 做阶次谱
    amplitude_envelope_demod = amplitude_envelope - np.mean(amplitude_envelope)
    try:
        amp_oa, amp_os = _compute_order_spectrum(
            amplitude_envelope_demod, fs, rot_freq, samples_per_rev=1024
        )
    except Exception:
        amp_oa, amp_os = np.array([]), np.array([])

    # === 频率解调谱 ===
    # 对 c(t) 做 Hilbert → 瞬时相位 → 瞬时频率 → FFT
    try:
        carrier_analytic = scipy_hilbert(carrier)
        inst_phase = np.unwrap(np.angle(carrier_analytic))
        inst_freq = np.diff(inst_phase) / (2 * np.pi) * fs  # Hz
        inst_freq = np.concatenate([inst_freq, [inst_freq[-1]]])  # 补齐长度
        # 去DC，保留频率调制成分
        inst_freq_demod = inst_freq - np.mean(inst_freq)
        freq_oa, freq_os = _compute_order_spectrum(
            inst_freq_demod, fs, rot_freq, samples_per_rev=1024
        )
    except Exception:
        freq_oa, freq_os = np.array([]), np.array([])

    # === 搜索特征故障阶次 ===
    def _search_fault_orders(oa, os, name):
        if len(oa) == 0:
            return {}
        oa_arr = np.asarray(oa)
        os_arr = np.asarray(os)

        # 背景：排除目标频率附近 ±0.5 阶次后的中位数
        exclude_orders = [sun_fault_order, planet_fault_order, carrier_order, mesh_order, 1.0, 2.0]
        exclude_mask = np.zeros(len(oa_arr), dtype=bool)
        for ex_o in exclude_orders:
            exclude_mask |= (oa_arr >= ex_o - 0.5) & (oa_arr <= ex_o + 0.5)
        bg_mask = ~exclude_mask & (oa_arr > 0.5)
        if np.any(bg_mask):
            bg = float(np.median(os_arr[bg_mask]))
        else:
            bg = float(np.median(os_arr))
        if bg < 1e-12:
            bg = 1e-12

        sun_amp = _order_band_amplitude(oa_arr, os_arr, sun_fault_order, 0.3)
        planet_amp = _order_band_amplitude(oa_arr, os_arr, planet_fault_order, 0.3)
        carrier_amp = _order_band_amplitude(oa_arr, os_arr, carrier_order, 0.3)

        return {
            f"{name}_sun_fault_snr": round(sun_amp / bg, 4),
            f"{name}_planet_fault_snr": round(planet_amp / bg, 4),
            f"{name}_carrier_snr": round(carrier_amp / bg, 4),
            f"{name}_sun_fault_significant": sun_amp / bg > 3.0,
            f"{name}_planet_fault_significant": planet_amp / bg > 3.0,
            f"{name}_carrier_significant": carrier_amp / bg > 3.0,
        }

    amp_demod = _search_fault_orders(amp_oa, amp_os, "amp_demod")
    freq_demod = _search_fault_orders(freq_oa, freq_os, "freq_demod")

    return {
        "method": "planetary_vmd_demod",
        "mesh_order": mesh_order,
        "carrier_order": carrier_order,
        "sun_fault_order": sun_fault_order,
        "planet_fault_order": planet_fault_order,
        "imf_count": K,
        "selected_imf_index": selected_idx,
        "selected_imf_center_freq": round(selected_center, 2),
        "amplitude_demod": amp_demod,
        "frequency_demod": freq_demod,
    }


def planetary_tsa_envelope_analysis(
    signal: np.ndarray,
    fs: float,
    rot_freq: float,
    gear_teeth: Dict,
) -> Dict:
    """
    Level 2c: TSA 残差包络阶次分析

    TSA → 残差信号 → 包络 → 阶次谱 → 搜索故障阶次
    消除确定性啮合分量后，残差中的冲击成分更容易检出。

    Args:
        signal: 原始振动信号
        fs: 采样率
        rot_freq: 估计转频 Hz
        gear_teeth: 齿轮参数
    """
    from ..gear.metrics import compute_tsa_residual_order

    z_sun = int(gear_teeth.get("sun") or 0)
    z_ring = int(gear_teeth.get("ring") or 0)
    planet_count = int(gear_teeth.get("planet_count") or 0)

    if planet_count < 3 or z_sun <= 0 or z_ring <= 0:
        return {"method": "planetary_tsa_envelope", "error": "not_planetary"}

    mesh_order = round(z_ring * z_sun / (z_sun + z_ring), 4)
    carrier_order = round(z_sun / (z_sun + z_ring), 4)
    sun_fault_order = round(z_ring / (z_sun + z_ring) * planet_count, 4)
    planet_fault_order = round(z_ring / (z_sun + z_ring), 4)

    arr = prepare_signal(signal)
    max_samples = int(fs * 5)
    if len(arr) > max_samples:
        arr = arr[:max_samples]

    # TSA + 残差
    tsa_result = compute_tsa_residual_order(arr, fs, rot_freq, samples_per_rev=1024)
    if not tsa_result.get("valid"):
        return {"method": "planetary_tsa_envelope", "error": "tsa_invalid"}

    residual = tsa_result["residual"]

    # 残差包络 → 阶次谱
    envelope = np.abs(scipy_hilbert(residual))
    envelope = envelope - np.mean(envelope)

    try:
        env_oa, env_os = _compute_order_spectrum(
            envelope, fs, rot_freq, samples_per_rev=1024
        )
    except Exception:
        return {"method": "planetary_tsa_envelope", "error": "order_spectrum_failed"}

    env_oa_arr = np.asarray(env_oa)
    env_os_arr = np.asarray(env_os)

    # TSA 残差包络阶次谱：全局中位数作为背景
    global_bg = float(np.median(env_os_arr[env_oa_arr > 0.5])) if np.any(env_oa_arr > 0.5) else 1e-12
    background = max(global_bg, 1e-12)

    sun_fault_amp = _order_band_amplitude(env_oa_arr, env_os_arr, sun_fault_order, 0.3)
    planet_fault_amp = _order_band_amplitude(env_oa_arr, env_os_arr, planet_fault_order, 0.3)
    carrier_amp = _order_band_amplitude(env_oa_arr, env_os_arr, carrier_order, 0.3)
    mesh_amp = _order_band_amplitude(env_oa_arr, env_os_arr, mesh_order, 1.0)

    sun_fault_snr = sun_fault_amp / background
    planet_fault_snr = planet_fault_amp / background
    carrier_snr = carrier_amp / background

    # 调制深度比
    sun_modulation_depth = sun_fault_amp / max(mesh_amp, 1e-12)
    planet_modulation_depth = planet_fault_amp / max(mesh_amp, 1e-12)
    carrier_modulation_depth = carrier_amp / max(mesh_amp, 1e-12)

    # 残差峭度（去掉确定性分量后的冲击指标）
    residual_kurtosis = float(
        np.mean((residual - np.mean(residual)) ** 4) /
        (np.var(residual) ** 2 + 1e-12) - 3
    )

    return {
        "method": "planetary_tsa_envelope",
        "mesh_order": mesh_order,
        "carrier_order": carrier_order,
        "sun_fault_order": sun_fault_order,
        "planet_fault_order": planet_fault_order,
        "tsa_revolutions": tsa_result.get("revolutions", 0),
        "residual_kurtosis": round(residual_kurtosis, 4),
        "sun_fault_snr": round(sun_fault_snr, 4),
        "planet_fault_snr": round(planet_fault_snr, 4),
        "carrier_snr": round(carrier_snr, 4),
        "sun_fault_amp": round(sun_fault_amp, 4),
        "planet_fault_amp": round(planet_fault_amp, 4),
        "carrier_amp": round(carrier_amp, 4),
        "mesh_amp": round(mesh_amp, 4),
        "sun_modulation_depth": round(sun_modulation_depth, 4),
        "planet_modulation_depth": round(planet_modulation_depth, 4),
        "carrier_modulation_depth": round(carrier_modulation_depth, 4),
        "sun_fault_significant": sun_fault_snr > 3.0,
        "planet_fault_significant": planet_fault_snr > 3.0,
        "carrier_significant": carrier_snr > 3.0,
    }


def planetary_hp_envelope_order_analysis(
    signal: np.ndarray,
    fs: float,
    rot_freq: float,
    gear_teeth: Dict,
) -> Dict:
    """
    Level 2d: 高通滤波包络阶次分析

    先高通滤波（去除低频旋转谐波），再做包络+阶次谱。
    低频旋转谐波是行星箱误报的主要来源，高通后包络更纯净。
    """
    z_sun = int(gear_teeth.get("sun") or 0)
    z_ring = int(gear_teeth.get("ring") or 0)
    planet_count = int(gear_teeth.get("planet_count") or 0)

    if planet_count < 3 or z_sun <= 0 or z_ring <= 0:
        return {"method": "planetary_hp_envelope_order", "error": "not_planetary"}

    mesh_order = round(z_ring * z_sun / (z_sun + z_ring), 4)
    carrier_order = round(z_sun / (z_sun + z_ring), 4)
    sun_fault_order = round(z_ring / (z_sun + z_ring) * planet_count, 4)
    planet_fault_order = round(z_ring / (z_sun + z_ring), 4)

    arr = prepare_signal(signal)
    max_samples = int(fs * 5)
    if len(arr) > max_samples:
        arr = arr[:max_samples]

    mesh_freq = rot_freq * mesh_order

    # 高通滤波：截止频率 = mesh_freq × 0.5（保留啮合频率及其谐波）
    hp_cutoff = max(50.0, mesh_freq * 0.5)
    hp_signal = lowpass_filter(arr, fs, fs / 2.0 - 10.0, order=4)  # placeholder
    from ..signal_utils import highpass_filter
    hp_signal = highpass_filter(arr, fs, hp_cutoff, order=4)

    # 包络 → 阶次谱
    envelope = np.abs(scipy_hilbert(hp_signal))
    envelope = envelope - np.mean(envelope)

    try:
        env_oa, env_os = _compute_order_spectrum(
            envelope, fs, rot_freq, samples_per_rev=1024
        )
    except Exception:
        return {"method": "planetary_hp_envelope_order", "error": "order_spectrum_failed"}

    env_oa_arr = np.asarray(env_oa)
    env_os_arr = np.asarray(env_os)

    # HP 包络阶次谱：全局中位数作为背景
    global_bg = float(np.median(env_os_arr[env_oa_arr > 0.5])) if np.any(env_oa_arr > 0.5) else 1e-12
    background = max(global_bg, 1e-12)

    sun_fault_amp = _order_band_amplitude(env_oa_arr, env_os_arr, sun_fault_order, 0.3)
    planet_fault_amp = _order_band_amplitude(env_oa_arr, env_os_arr, planet_fault_order, 0.3)
    carrier_amp = _order_band_amplitude(env_oa_arr, env_os_arr, carrier_order, 0.3)
    mesh_amp = _order_band_amplitude(env_oa_arr, env_os_arr, mesh_order, 1.0)

    sun_fault_snr = sun_fault_amp / background
    planet_fault_snr = planet_fault_amp / background
    carrier_snr = carrier_amp / background

    # 调制深度比
    sun_modulation_depth = sun_fault_amp / max(mesh_amp, 1e-12)
    planet_modulation_depth = planet_fault_amp / max(mesh_amp, 1e-12)
    carrier_modulation_depth = carrier_amp / max(mesh_amp, 1e-12)

    # 包络峭度
    if len(envelope) > 4:
        e_mean = np.mean(envelope)
        e_var = np.var(envelope)
        envelope_kurtosis = float(np.mean((envelope - e_mean) ** 4) / (e_var ** 2 + 1e-12) - 3)
    else:
        envelope_kurtosis = 0.0

    return {
        "method": "planetary_hp_envelope_order",
        "mesh_order": mesh_order,
        "carrier_order": carrier_order,
        "sun_fault_order": sun_fault_order,
        "planet_fault_order": planet_fault_order,
        "hp_cutoff_hz": round(hp_cutoff, 2),
        "sun_fault_snr": round(sun_fault_snr, 4),
        "planet_fault_snr": round(planet_fault_snr, 4),
        "carrier_snr": round(carrier_snr, 4),
        "sun_fault_amp": round(sun_fault_amp, 4),
        "planet_fault_amp": round(planet_fault_amp, 4),
        "carrier_amp": round(carrier_amp, 4),
        "mesh_amp": round(mesh_amp, 4),
        "sun_modulation_depth": round(sun_modulation_depth, 4),
        "planet_modulation_depth": round(planet_modulation_depth, 4),
        "carrier_modulation_depth": round(carrier_modulation_depth, 4),
        "envelope_kurtosis": round(envelope_kurtosis, 4),
        "sun_fault_significant": sun_fault_snr > 3.0,
        "planet_fault_significant": planet_fault_snr > 3.0,
        "carrier_significant": carrier_snr > 3.0,
    }


def planetary_sc_scoh_analysis(
    signal: np.ndarray,
    fs: float,
    rot_freq: float,
    gear_teeth: Dict,
) -> Dict:
    """
    Level 4: 谱相关/谱相干解调分析 (Spectral Correlation / Spectral Coherence)

    Dong, Liu & Feng (2025) 提出基于AM-FM模型的谱相关解调分析方法。

    核心原理：对于AM-FM信号，谱相关密度(SC)在二维谱面上呈现**分组离散特征点**，
    其循环频率等于调制频率，谱频率等于载波与调制频率的组合。
    这与冲击信号的垂直线特征显著不同。

    算法流程：
    1. 将信号分段 → 对每段做FFT → 计算谱相关密度 S_x^α(f)
    2. 计算谱相干 γ_x^α(f) = S_x^α(f) / sqrt(S_x^0(f+α/2) * S_x^0(f-α/2))
    3. 在循环频率轴搜索行星箱故障特征频率处的离散点群
    4. 报告谱相干值作为诊断指标

    约束：2GB服务器内存限制 → 循环频率范围限制在0~5×mesh_freq，分段长度1024点

    Args:
        signal: 原始振动信号
        fs: 采样率
        rot_freq: 估计转频 Hz
        gear_teeth: 齿轮参数 {sun, ring, planet, planet_count}

    Returns:
        Dict 包含谱相关密度和谱相干在故障循环频率处的指标及显著性判定
    """
    z_sun = int(gear_teeth.get("sun") or 0)
    z_ring = int(gear_teeth.get("ring") or 0)
    planet_count = int(gear_teeth.get("planet_count") or 0)

    if planet_count < 3 or z_sun <= 0 or z_ring <= 0:
        return {"method": "planetary_sc_scoh", "error": "not_planetary"}

    # 特征阶次与频率
    mesh_order = round(z_ring * z_sun / (z_sun + z_ring), 4)      # 21.875
    carrier_order = round(z_sun / (z_sun + z_ring), 4)            # 0.21875
    sun_fault_order = round(z_ring / (z_sun + z_ring) * planet_count, 4)  # 3.125
    planet_fault_order = round(z_ring / (z_sun + z_ring), 4)      # 0.78125

    mesh_freq = rot_freq * mesh_order
    sun_fault_freq = rot_freq * sun_fault_order
    planet_fault_freq = rot_freq * planet_fault_order
    carrier_freq = rot_freq * carrier_order

    arr = prepare_signal(signal)
    # 信号截断至5秒（2GB服务器内存限制）
    max_samples = int(fs * 5)
    if len(arr) > max_samples:
        arr = arr[:max_samples]

    N = len(arr)

    # === 参数设置 ===
    # 分段长度：1024点（平衡分辨率与内存）
    seg_len = 1024
    # 重叠率：50%（增加分段数以提高估计稳定性）
    overlap = seg_len // 2
    step = seg_len - overlap

    # 循环频率范围：0 ~ 5×mesh_freq（覆盖所有故障特征频率）
    alpha_max = 5.0 * mesh_freq
    # 循环频率分辨率 = fs / seg_len
    alpha_res = fs / seg_len
    # 频率分辨率 = fs / seg_len
    freq_res = fs / seg_len

    # 计算分段数
    n_segments = max(1, (N - seg_len) // step + 1)
    if n_segments < 2:
        # 信号太短，至少需要2段才能计算谱相关
        return {"method": "planetary_sc_scoh", "error": "signal_too_short"}

    # === Step 1: 分段FFT ===
    # 对每段做FFT，存储频谱（复数）
    # 仅存储正频率部分（0 ~ fs/2）
    n_freq_bins = seg_len // 2 + 1  # rfft 输出长度
    X_segments = np.zeros((n_segments, n_freq_bins), dtype=np.complex128)

    for i in range(n_segments):
        start = i * step
        end = start + seg_len
        if end > N:
            # 末段补零
            seg = np.zeros(seg_len)
            actual_len = N - start
            if actual_len > 0:
                seg[:actual_len] = arr[start:N]
        else:
            seg = arr[start:end]
        # 加窗（Hanning窗减少频谱泄漏）
        seg = seg * np.hanning(seg_len)
        X_segments[i] = np.fft.rfft(seg)

    # 频率轴
    f_axis = np.fft.rfftfreq(seg_len, d=1.0 / fs)

    # === Step 2: 计算谱相关密度 S_x^α(f) ===
    # S_x^α(f) = <X_i(f-α/2) * X_i^*(f+α/2)>_i  （分段平均）
    # 其中 α 为循环频率

    # 确定循环频率轴范围
    # α 的范围：0 ~ alpha_max，步长 = alpha_res
    n_alpha_bins = int(alpha_max / alpha_res) + 1
    alpha_axis = np.arange(n_alpha_bins) * alpha_res

    # 谱相关密度矩阵：shape (n_alpha_bins, n_freq_bins)
    # 内存估算：10000 × 513 × 16 bytes ≈ 82MB（可接受）
    # 但对于2GB服务器需要更保守 → 限制 alpha 轴数量
    # alpha_max ≈ 5×mesh_freq，mesh_freq≈437.5Hz @ 20Hz → alpha_max≈2187.5
    # alpha_res ≈ fs/1024 ≈ 25Hz → n_alpha ≈ 87（可接受）
    # alpha_max ≈ 5×mesh_freq ≈ 5×21.875×rot_freq
    # 对于rot_freq=20Hz: alpha_max≈2187.5, n_alpha≈87
    # 对于rot_freq=50Hz: alpha_max≈5468.75, n_alpha≈214
    # 内存上限：214 × 513 × 16 ≈ 1.76MB（完全可接受）

    Sx_alpha = np.zeros((n_alpha_bins, n_freq_bins), dtype=np.complex128)

    for a_idx in range(n_alpha_bins):
        alpha = alpha_axis[a_idx]
        # f+α/2 和 f-α/2 对应的频率索引
        # f_idx 对应 f_axis[k]，f+α/2 对应 f_axis[k] + alpha/2
        # 需要找到 f+α/2 和 f-α/2 在 f_axis 上的索引

        # 频率偏移量（以索引为单位）
        shift = alpha / (2.0 * freq_res)  # α/2 对应的频率索引偏移

        # 对每个频率 bin k：
        # X(f-α/2) → X_segments[:, k - shift]  (低频侧)
        # X(f+α/2) → X_segments[:, k + shift]  (高频侧)
        # S_x^α(f) = <X(f-α/2) * conj(X(f+α/2))>

        shift_int = int(round(shift))
        if shift_int == 0:
            # α=0：谱相关密度 = 功率谱密度 S_x^0(f)
            Sx_alpha[a_idx] = np.mean(X_segments * np.conj(X_segments), axis=0)
            continue

        # 有效频率范围：确保 k-shift_int >= 0 且 k+shift_int < n_freq_bins
        k_low = shift_int
        k_high = n_freq_bins - shift_int

        if k_low >= k_high:
            # 循环频率太大，无有效交叉谱
            continue

        # 计算交叉谱
        X_low = X_segments[:, k_low:k_high]    # X(f-α/2)，shape (n_seg, k_high-k_low)
        X_high = X_segments[:, k_low:k_high]   # 但需要 f+α/2 → 偏移 +shift_int
        # 正确：X(f-α/2) = X_segments[:, k-shift_int]，X(f+α/2) = X_segments[:, k+shift_int]
        # 对于输出 bin k_out（对应 f_axis[k_out]），需要：
        #   X(f-α/2) 对应 bin (k_out + shift_int)  [因为 f-α/2 = f_axis[k_out] - α/2]
        #   X(f+α/2) 对应 bin (k_out - shift_int)  [不对，让我重新推导]

        # 更清晰的推导：
        # 设输出频率索引为 k_out，对应频率 f = f_axis[k_out]
        # f-α/2 对应索引：k_minus = k_out - shift_int
        # f+α/2 对应索引：k_plus = k_out + shift_int
        # S_x^α(f_axis[k_out]) = <X(k_minus) * conj(X(k_plus))>

        # 有效范围：0 <= k_minus 且 k_plus < n_freq_bins
        # → k_out >= shift_int 且 k_out < n_freq_bins - shift_int
        k_out_low = shift_int
        k_out_high = n_freq_bins - shift_int

        if k_out_low >= k_out_high:
            continue

        X_minus = X_segments[:, k_out_low - shift_int:k_out_high - shift_int]  # X(f-α/2)
        # 等价于 X_segments[:, 0:k_out_high - shift_int - (k_out_low - shift_int)]
        # = X_segments[:, 0:k_out_high - k_out_low] ... 不对
        # 实际：对于 k_out 从 k_out_low 到 k_out_high-1，
        #   k_minus = k_out - shift_int，范围从 0 到 k_out_high-1-shift_int
        #   k_plus = k_out + shift_int，范围从 k_out_low+shift_int 到 k_out_high-1+shift_int

        # 更安全的做法：逐段计算
        k_minus_range = np.arange(k_out_low - shift_int, k_out_high - shift_int)
        k_plus_range = np.arange(k_out_low + shift_int, k_out_high + shift_int)

        # 确保索引在有效范围内
        if k_minus_range[-1] >= n_freq_bins or k_plus_range[-1] >= n_freq_bins:
            continue

        # 分段平均：S_x^α(f) = <X(f-α/2) * conj(X(f+α/2))>_segments
        cross_spec = np.mean(
            X_segments[:, k_minus_range] * np.conj(X_segments[:, k_plus_range]),
            axis=0
        )
        Sx_alpha[a_idx, k_out_low:k_out_high] = cross_spec

    # === Step 3: 计算谱相干 γ_x^α(f) ===
    # γ_x^α(f) = S_x^α(f) / sqrt(S_x^0(f-α/2) * S_x^0(f+α/2))
    # S_x^0(f) 已在 Sx_alpha[0] 中（功率谱密度）

    PSD = np.real(Sx_alpha[0])  # S_x^0(f)，功率谱密度

    # 谱相干矩阵
    scoh = np.zeros((n_alpha_bins, n_freq_bins), dtype=np.float64)

    for a_idx in range(n_alpha_bins):
        alpha = alpha_axis[a_idx]
        shift_int = int(round(alpha / (2.0 * freq_res)))

        if shift_int == 0:
            # α=0 时谱相干 = 1（自相关）
            scoh[a_idx] = 1.0
            continue

        k_out_low = shift_int
        k_out_high = n_freq_bins - shift_int

        if k_out_low >= k_out_high:
            continue

        # S_x^α(f) 的模
        Sc_abs = np.abs(Sx_alpha[a_idx, k_out_low:k_out_high])

        # S_x^0(f-α/2) 和 S_x^0(f+α/2)
        k_minus_range = np.arange(k_out_low - shift_int, k_out_high - shift_int)
        k_plus_range = np.arange(k_out_low + shift_int, k_out_high + shift_int)

        PSD_minus = PSD[k_minus_range]
        PSD_plus = PSD[k_plus_range]

        # 归一化因子
        norm = np.sqrt(PSD_minus * PSD_plus)
        norm = np.maximum(norm, 1e-12)  # 避免除零

        scoh[a_idx, k_out_low:k_out_high] = Sc_abs / norm

    # === Step 4: 搜索故障循环频率处的谱相干峰值 ===
    # 在每个目标循环频率 α_fault 处，
    # 搜索谱频率轴上的最大谱相干值（即离散点群中最显著的点）

    def _peak_scoh_at_alpha(alpha_target, freq_band=None):
        """
        在循环频率 alpha_target 处，搜索谱相干峰值。

        freq_band: 限制搜索的谱频率范围 (f_low, f_high)，
        默认搜索 mesh_freq 附近的频带（行星箱载波频率）

        Returns:
            (peak_scoh, peak_freq, mean_scoh_in_band)
        """
        # 找到最近的 α 索引
        a_idx = int(round(alpha_target / alpha_res))
        if a_idx < 0 or a_idx >= n_alpha_bins:
            return 0.0, 0.0, 0.0

        # 该循环频率处的谱相干切片
        scoh_slice = scoh[a_idx, :]

        if freq_band is not None:
            f_low, f_high = freq_band
            # 限制搜索范围
            f_mask = (f_axis >= f_low) & (f_axis <= f_high)
            masked_scoh = scoh_slice[f_mask]
            masked_freq = f_axis[f_mask]
        else:
            # 默认：搜索 mesh_freq ± bandwidth 附近
            bandwidth = mesh_freq * 0.5  # ±50% mesh_freq
            f_low = max(0, mesh_freq - bandwidth)
            f_high = mesh_freq + bandwidth
            f_mask = (f_axis >= f_low) & (f_axis <= f_high)
            masked_scoh = scoh_slice[f_mask]
            masked_freq = f_axis[f_mask]

        if len(masked_scoh) == 0:
            return 0.0, 0.0, 0.0

        peak_idx = np.argmax(masked_scoh)
        peak_scoh = float(masked_scoh[peak_idx])
        peak_freq = float(masked_freq[peak_idx])
        mean_scoh = float(np.mean(masked_scoh))

        return peak_scoh, peak_freq, mean_scoh

    # 同时计算谱相关密度峰值（SC绝对值，不受PSD归一化影响）
    def _peak_sc_at_alpha(alpha_target, freq_band=None):
        """
        在循环频率 alpha_target 处，搜索谱相关密度幅值峰值。
        """
        a_idx = int(round(alpha_target / alpha_res))
        if a_idx < 0 or a_idx >= n_alpha_bins:
            return 0.0, 0.0

        Sc_slice = np.abs(Sx_alpha[a_idx, :])

        if freq_band is not None:
            f_low, f_high = freq_band
            f_mask = (f_axis >= f_low) & (f_axis <= f_high)
            masked_sc = Sc_slice[f_mask]
        else:
            bandwidth = mesh_freq * 0.5
            f_low = max(0, mesh_freq - bandwidth)
            f_high = mesh_freq + bandwidth
            f_mask = (f_axis >= f_low) & (f_axis <= f_high)
            masked_sc = Sc_slice[f_mask]

        if len(masked_sc) == 0:
            return 0.0, 0.0

        peak_idx = np.argmax(masked_sc)
        peak_sc = float(masked_sc[peak_idx])
        return peak_sc, float(f_axis[f_mask][peak_idx])

    # 搜索频率范围：mesh_freq ± 50% （行星箱AM-FM信号的载波在mesh频率附近）
    search_band = (max(0, mesh_freq - mesh_freq * 0.5), mesh_freq + mesh_freq * 0.5)

    # 故障循环频率
    # sun_fault: AM-FM调制源 → α = sun_fault_freq
    sun_sc_peak, sun_sc_peak_f = _peak_sc_at_alpha(sun_fault_freq, search_band)
    sun_scoh_peak, sun_scoh_peak_f, sun_scoh_mean = _peak_scoh_at_alpha(sun_fault_freq, search_band)

    # planet_fault: α = planet_fault_freq
    planet_sc_peak, planet_sc_peak_f = _peak_sc_at_alpha(planet_fault_freq, search_band)
    planet_scoh_peak, planet_scoh_peak_f, planet_scoh_mean = _peak_scoh_at_alpha(planet_fault_freq, search_band)

    # carrier: α = carrier_freq
    carrier_sc_peak, carrier_sc_peak_f = _peak_sc_at_alpha(carrier_freq, search_band)
    carrier_scoh_peak, carrier_scoh_peak_f, carrier_scoh_mean = _peak_scoh_at_alpha(carrier_freq, search_band)

    # mesh: α = mesh_freq（啮合频率作为参考基准）
    mesh_sc_peak, mesh_sc_peak_f = _peak_sc_at_alpha(mesh_freq, search_band)
    mesh_scoh_peak, mesh_scoh_peak_f, mesh_scoh_mean = _peak_scoh_at_alpha(mesh_freq, search_band)

    # === 背景：非故障循环频率处的谱相干均值 ===
    # 用 alpha 轴上排除故障频率附近 ±alpha_res 的区域估计背景
    exclude_alphas = [sun_fault_freq, planet_fault_freq, carrier_freq, mesh_freq,
                      2 * sun_fault_freq, 2 * planet_fault_freq]
    bg_mask = np.ones(n_alpha_bins, dtype=bool)
    for ex_a in exclude_alphas:
        ex_idx = int(round(ex_a / alpha_res))
        bg_mask[max(0, ex_idx - 2):min(n_alpha_bins, ex_idx + 3)] = False

    if np.any(bg_mask):
        # 背景谱相干：排除区域外的 alpha 上，search_band 内的均值
        bg_scoh_values = []
        for a_idx in np.where(bg_mask)[0]:
            scoh_slice = scoh[a_idx, :]
            f_mask = (f_axis >= search_band[0]) & (f_axis <= search_band[1])
            if np.any(f_mask):
                bg_scoh_values.append(np.mean(scoh_slice[f_mask]))
        bg_scoh = float(np.mean(bg_scoh_values)) if bg_scoh_values else 0.01
    else:
        bg_scoh = 0.01

    bg_scoh = max(bg_scoh, 1e-6)  # 防止除零

    # 谱相干 SNR（峰值/背景）
    sun_scoh_snr = sun_scoh_peak / bg_scoh
    planet_scoh_snr = planet_scoh_peak / bg_scoh
    carrier_scoh_snr = carrier_scoh_peak / bg_scoh

    # 谱相关密度背景：用 alpha=0 处（功率谱密度）的搜索频带均值
    psd_bg = float(np.mean(PSD[(f_axis >= search_band[0]) & (f_axis <= search_band[1])]))
    psd_bg = max(psd_bg, 1e-12)
    sun_sc_snr = sun_sc_peak / psd_bg
    planet_sc_snr = planet_sc_peak / psd_bg
    carrier_sc_snr = carrier_sc_peak / psd_bg
    mesh_sc_snr = mesh_sc_peak / psd_bg

    # === 显著性判定 ===
    # 谱相干阈值：SCoh > 0.3 为弱证据（warning），> 0.5 为强证据（critical）
    # SCoh SNR 阈值：> 3.0 为 warning，> 5.0 为 critical
    SCOH_WARNING_THRESHOLD = 0.3
    SCOH_CRITICAL_THRESHOLD = 0.5
    SCOH_SNR_WARNING = 3.0
    SCOH_SNR_CRITICAL = 5.0

    return {
        "method": "planetary_sc_scoh",
        "mesh_order": mesh_order,
        "carrier_order": carrier_order,
        "sun_fault_order": sun_fault_order,
        "planet_fault_order": planet_fault_order,
        "mesh_freq": round(mesh_freq, 4),
        "sun_fault_freq": round(sun_fault_freq, 4),
        "planet_fault_freq": round(planet_fault_freq, 4),
        "carrier_freq": round(carrier_freq, 4),
        # 谱相关密度指标
        "sun_fault_sc": round(sun_sc_peak, 6),
        "planet_fault_sc": round(planet_sc_peak, 6),
        "carrier_sc": round(carrier_sc_peak, 6),
        "mesh_sc": round(mesh_sc_peak, 6),
        "sun_fault_sc_snr": round(sun_sc_snr, 4),
        "planet_fault_sc_snr": round(planet_sc_snr, 4),
        "carrier_sc_snr": round(carrier_sc_snr, 4),
        "mesh_sc_snr": round(mesh_sc_snr, 4),
        "sun_fault_sc_peak_f": round(sun_sc_peak_f, 2),
        "planet_fault_sc_peak_f": round(planet_sc_peak_f, 2),
        "carrier_sc_peak_f": round(carrier_sc_peak_f, 2),
        # 谱相干指标
        "sun_fault_scoh": round(sun_scoh_peak, 6),
        "planet_fault_scoh": round(planet_scoh_peak, 6),
        "carrier_scoh": round(carrier_scoh_peak, 6),
        "mesh_scoh": round(mesh_scoh_peak, 6),
        "sun_fault_scoh_snr": round(sun_scoh_snr, 4),
        "planet_fault_scoh_snr": round(planet_scoh_snr, 4),
        "carrier_scoh_snr": round(carrier_scoh_snr, 4),
        "sun_fault_scoh_peak_f": round(sun_scoh_peak_f, 2),
        "planet_fault_scoh_peak_f": round(planet_scoh_peak_f, 2),
        "carrier_scoh_peak_f": round(carrier_scoh_peak_f, 2),
        "sun_fault_scoh_mean": round(sun_scoh_mean, 6),
        "planet_fault_scoh_mean": round(planet_scoh_mean, 6),
        "carrier_scoh_mean": round(carrier_scoh_mean, 6),
        # 背景
        "bg_scoh": round(bg_scoh, 6),
        "psd_bg": round(psd_bg, 6),
        # 计算参数
        "n_segments": n_segments,
        "seg_len": seg_len,
        "alpha_max": round(alpha_max, 2),
        "alpha_res": round(alpha_res, 2),
        "n_alpha_bins": n_alpha_bins,
        # 显著性判定
        "sun_fault_significant": sun_scoh_snr > SCOH_SNR_WARNING or sun_scoh_peak > SCOH_WARNING_THRESHOLD,
        "planet_fault_significant": planet_scoh_snr > SCOH_SNR_WARNING or planet_scoh_peak > SCOH_WARNING_THRESHOLD,
        "carrier_significant": carrier_scoh_snr > SCOH_SNR_WARNING or carrier_scoh_peak > SCOH_WARNING_THRESHOLD,
        "sun_fault_warning": sun_scoh_snr > SCOH_SNR_WARNING,
        "sun_fault_critical": sun_scoh_snr > SCOH_SNR_CRITICAL or sun_scoh_peak > SCOH_CRITICAL_THRESHOLD,
        "planet_fault_warning": planet_scoh_snr > SCOH_SNR_WARNING,
        "planet_fault_critical": planet_scoh_snr > SCOH_SNR_CRITICAL or planet_scoh_peak > SCOH_CRITICAL_THRESHOLD,
        "carrier_warning": carrier_scoh_snr > SCOH_SNR_WARNING,
        "carrier_critical": carrier_scoh_snr > SCOH_SNR_CRITICAL or carrier_scoh_peak > SCOH_CRITICAL_THRESHOLD,
    }


def evaluate_planetary_demod_results(
    narrowband_result: Dict,
    vmd_result: Dict,
) -> Dict:
    """
    综合评估行星箱解调结果 → fault_indicators

    评估结论（WTgearbox 160文件）：
    === 无区分力指标（不使用） ===
    - SNR（所有方法）：区分力 1.05~1.24×，overlap 0.72~0.95
    - carrier_snr：健康 > 故障（行星架固有调制）
    - planet_fault_snr：区分力 <1.5×，overlap >70%
    - sun_modulation_depth（narrowband/tsa）：健康 > 故障

    === 有区分力指标（使用） ===
    - narrowband envelope_kurtosis：区分力 3.28×（健康 0.88, 故障 2.90）
    - fullband envelope_kurtosis：区分力 2.84×（健康 1.80, 故障 5.11）
    - hp envelope_kurtosis：区分力 2.46×（健康 2.10, 故障 5.18）
    - TSA residual_kurtosis：区分力 3.31×（健康 1.19, 故障 3.95）
    - fullband/hp sun_modulation_depth：区分力 1.55×/1.51×，overlap 0.35

    === 融合策略（按 ALGORITHMS.md 2.7 推荐的 Level 1→2→3 分级诊断） ===
    Level 1: 时域证据门控 — envelope_kurtosis/residual_kurtosis 作为先决条件
    Level 2: 窄带包络阶次分析 — envelope_kurtosis 作为主要诊断指标
    Level 3: VMD联合解调（备选，Level 2 不够时启用）
    """
    indicators = {}

    # === Level 1: 时域证据门控 ===
    # 收集各方法的 envelope_kurtosis 和 residual_kurtosis
    env_kurtoses = []
    for result in [narrowband_result]:
        if "error" in result:
            continue
        val = result.get("envelope_kurtosis", 0.0)
        if val > 0:
            env_kurtoses.append(val)

    res_kurt = 0.0
    if "error" not in narrowband_result:
        res_kurt = narrowband_result.get("residual_kurtosis", 0.0)

    # TSA 残差峭度
    tsa_res_kurt = 0.0
    # narrowband 不含 residual_kurtosis, 它在 TSA 方法中（但我们已删除 TSA）
    # 使用 narrowband 的 envelope_kurtosis 作为主判定

    # === Level 2: 窄带包络阶次分析（核心诊断） ===
    # narrowband envelope_kurtosis: 健康 median=0.88, 故障 median=2.90
    # threshold: warning > 2.0 (超过健康max约一半), critical > 5.0
    if env_kurtoses:
        max_env_kurt = max(env_kurtoses)
        indicators["planetary_sun_fault"] = {
            "value": round(max_env_kurt, 4),
            "envelope_kurtosis": round(max_env_kurt, 4),
            "warning": max_env_kurt > 2.0,
            "critical": max_env_kurt > 5.0,
            "method": "narrowband_envelope_kurtosis",
            "note": "行星箱诊断核心指标：窄带包络峭度（区分力3.28×）",
        }
    else:
        indicators["planetary_sun_fault"] = {
            "value": 0.0,
            "warning": False, "critical": False,
            "method": "narrowband_envelope_kurtosis",
        }

    # === 窄带 SNR 仅作为参考（不用于判定） ===
    if "error" not in narrowband_result:
        sun_snr = narrowband_result.get("sun_fault_snr", 0.0)
        planet_snr = narrowband_result.get("planet_fault_snr", 0.0)
        carrier_snr = narrowband_result.get("carrier_snr", 0.0)
        sun_md = narrowband_result.get("sun_modulation_depth", 0.0)
        indicators["planetary_order_snr"] = {
            "sun_fault_snr": round(sun_snr, 4),
            "planet_fault_snr": round(planet_snr, 4),
            "carrier_snr": round(carrier_snr, 4),
            "sun_modulation_depth": round(sun_md, 4),
            "warning": False,   # SNR 无区分力，不用于故障判定
            "critical": False,
            "note": "SNR对行星箱无区分力（overlap>72%），仅记录供参考",
        }

    # === Level 3: VMD 幅频联合解调（备选） ===
    if "error" not in vmd_result:
        amp_demod = vmd_result.get("amplitude_demod", {})
        freq_demod = vmd_result.get("frequency_demod", {})
        amp_sun_snr = amp_demod.get("amp_demod_sun_fault_snr", 0.0)
        freq_sun_snr = freq_demod.get("freq_demod_sun_fault_snr", 0.0)
        indicators["planetary_vmd"] = {
            "amp_sun_fault_snr": round(amp_sun_snr, 4),
            "freq_sun_fault_snr": round(freq_sun_snr, 4),
            "warning": False,  # VMD 需配合 Level 1 门控
            "critical": False,
            "note": "VMD联合解调结果，需结合时域门控使用",
        }
    else:
        indicators["planetary_vmd"] = {"value": 0.0, "warning": False, "critical": False}

    # === carrier 不参与判定（行星架调制是固有特征） ===
    if "error" not in narrowband_result:
        carrier_snr_val = narrowband_result.get("carrier_snr", 0.0)
        indicators["planetary_carrier"] = {
            "value": round(carrier_snr_val, 4),
            "warning": False,
            "critical": False,
            "note": "carrier_snr是行星架调制固有特征，健康值反而更大，不用于故障判定",
        }

    # === envelope_kurtosis 详细指标 ===
    if env_kurtoses:
        indicators["envelope_kurtosis"] = {
            "value": round(max(env_kurtoses), 4),
            "warning": max(env_kurtoses) > 2.0,
            "critical": max(env_kurtoses) > 5.0,
        }

    return indicators