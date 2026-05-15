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

    # 背景：中位数（排除低阶旋转谐波区域 < 5阶）
    high_mask = env_oa > 5.0
    if np.any(high_mask):
        background = float(np.median(env_os[high_mask]))
    else:
        background = float(np.median(env_os))

    if background < 1e-12:
        background = 1e-12

    # 各特征阶次的幅值
    sun_fault_amp = _order_band_amplitude(env_oa, env_os, sun_fault_order, 0.3)
    planet_fault_amp = _order_band_amplitude(env_oa, env_os, planet_fault_order, 0.3)
    carrier_amp = _order_band_amplitude(env_oa, env_os, carrier_order, 0.3)

    # SNR（相对于背景中位数）
    sun_fault_snr = sun_fault_amp / background
    planet_fault_snr = planet_fault_amp / background
    carrier_snr = carrier_amp / background

    # mesh_order 带内包络谱 SNR（整体调制强度）
    mesh_band_amp = _order_band_amplitude(env_oa, env_os, mesh_order, 1.0)
    mesh_band_snr = mesh_band_amp / background

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
        "background_median": round(background, 4),
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

    high_mask = env_oa > 5.0
    if np.any(high_mask):
        background = float(np.median(env_os[high_mask]))
    else:
        background = float(np.median(env_os))
    if background < 1e-12:
        background = 1e-12

    sun_fault_amp = _order_band_amplitude(env_oa, env_os, sun_fault_order, 0.3)
    planet_fault_amp = _order_band_amplitude(env_oa, env_os, planet_fault_order, 0.3)
    carrier_amp = _order_band_amplitude(env_oa, env_os, carrier_order, 0.3)

    sun_fault_snr = sun_fault_amp / background
    planet_fault_snr = planet_fault_amp / background
    carrier_snr = carrier_amp / background

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
        "background_median": round(background, 4),
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

        # 背景
        high_mask = oa_arr > 5.0
        if np.any(high_mask):
            bg = float(np.median(os_arr[high_mask]))
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

    high_mask = env_oa_arr > 5.0
    if np.any(high_mask):
        background = float(np.median(env_os_arr[high_mask]))
    else:
        background = float(np.median(env_os_arr))
    if background < 1e-12:
        background = 1e-12

    sun_fault_amp = _order_band_amplitude(env_oa_arr, env_os_arr, sun_fault_order, 0.3)
    planet_fault_amp = _order_band_amplitude(env_oa_arr, env_os_arr, planet_fault_order, 0.3)
    carrier_amp = _order_band_amplitude(env_oa_arr, env_os_arr, carrier_order, 0.3)

    sun_fault_snr = sun_fault_amp / background
    planet_fault_snr = planet_fault_amp / background
    carrier_snr = carrier_amp / background

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

    high_mask = env_oa_arr > 5.0
    if np.any(high_mask):
        background = float(np.median(env_os_arr[high_mask]))
    else:
        background = float(np.median(env_os_arr))
    if background < 1e-12:
        background = 1e-12

    sun_fault_amp = _order_band_amplitude(env_oa_arr, env_os_arr, sun_fault_order, 0.3)
    planet_fault_amp = _order_band_amplitude(env_oa_arr, env_os_arr, planet_fault_order, 0.3)
    carrier_amp = _order_band_amplitude(env_oa_arr, env_os_arr, carrier_order, 0.3)

    sun_fault_snr = sun_fault_amp / background
    planet_fault_snr = planet_fault_amp / background
    carrier_snr = carrier_amp / background

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
        "sun_fault_significant": sun_fault_snr > 3.0,
        "planet_fault_significant": planet_fault_snr > 3.0,
        "carrier_significant": carrier_snr > 3.0,
    }


def evaluate_planetary_demod_results(
    narrowband_result: Dict,
    fullband_result: Dict,
    vmd_result: Dict,
    tsa_result: Dict,
    hp_result: Dict,
) -> Dict:
    """
    综合评估行星箱解调结果 → fault_indicators

    融合策略：
    1. 各方法独立计算 sun/planet/carrier 的 SNR
    2. 取所有方法中最大的 SNR 作为综合证据
    3. 至少 2 个方法一致检出（SNR > 3）才标记为 warning
    4. 至少 2 个方法一致检出（SNR > 5）才标记为 critical
    """
    indicators = {}

    # 收集各方法的 sun_fault_snr
    all_sun_snrs = []
    all_planet_snrs = []
    all_carrier_snrs = []

    for result in [narrowband_result, fullband_result, tsa_result, hp_result]:
        if "error" in result:
            continue
        snr = result.get("sun_fault_snr", 0.0)
        if snr > 0:
            all_sun_snrs.append(snr)
        snr = result.get("planet_fault_snr", 0.0)
        if snr > 0:
            all_planet_snrs.append(snr)
        snr = result.get("carrier_snr", 0.0)
        if snr > 0:
            all_carrier_snrs.append(snr)

    # VMD 结果单独处理（幅值解调 + 频率解调）
    if "error" not in vmd_result:
        amp_demod = vmd_result.get("amplitude_demod", {})
        freq_demod = vmd_result.get("frequency_demod", {})
        for demod in [amp_demod, freq_demod]:
            snr = demod.get("amp_demod_sun_fault_snr", 0.0)
            if snr > 0:
                all_sun_snrs.append(snr)
            snr = demod.get("freq_demod_sun_fault_snr", 0.0)
            if snr > 0:
                all_sun_snrs.append(snr)
            snr = demod.get("amp_demod_planet_fault_snr", 0.0)
            if snr > 0:
                all_planet_snrs.append(snr)
            snr = demod.get("freq_demod_planet_fault_snr", 0.0)
            if snr > 0:
                all_planet_snrs.append(snr)
            snr = demod.get("amp_demod_carrier_snr", 0.0)
            if snr > 0:
                all_carrier_snrs.append(snr)
            snr = demod.get("freq_demod_carrier_snr", 0.0)
            if snr > 0:
                all_carrier_snrs.append(snr)

    # 融合判定
    def _evaluate_fault(all_snrs, name):
        if not all_snrs:
            return {
                "value": 0.0,
                "max_snr": 0.0,
                "warning": False,
                "critical": False,
                "methods_agree_warning": 0,
                "methods_agree_critical": 0,
            }
        max_snr = max(all_snrs)
        warning_count = sum(1 for s in all_snrs if s > 3.0)
        critical_count = sum(1 for s in all_snrs if s > 5.0)
        return {
            "value": round(max_snr, 4),
            "max_snr": round(max_snr, 4),
            "warning": warning_count >= 2,
            "critical": critical_count >= 2,
            "methods_agree_warning": warning_count,
            "methods_agree_critical": critical_count,
        }

    indicators[f"planetary_sun_fault"] = _evaluate_fault(all_sun_snrs, "sun")
    indicators[f"planetary_planet_fault"] = _evaluate_fault(all_planet_snrs, "planet")
    indicators[f"planetary_carrier"] = _evaluate_fault(all_carrier_snrs, "carrier")

    # 包络峭度指标（窄带方法）
    if "error" not in narrowband_result:
        env_kurt = narrowband_result.get("envelope_kurtosis", 0.0)
        indicators["envelope_kurtosis"] = {
            "value": round(env_kurt, 4),
            "warning": env_kurt > 5.0,
            "critical": env_kurt > 10.0,
        }

    # 残差峭度指标（TSA 方法）
    if "error" not in tsa_result:
        res_kurt = tsa_result.get("residual_kurtosis", 0.0)
        indicators["residual_kurtosis"] = {
            "value": round(res_kurt, 4),
            "warning": res_kurt > 5.0,
            "critical": res_kurt > 10.0,
        }

    return indicators