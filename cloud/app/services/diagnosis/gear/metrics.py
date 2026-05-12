"""
齿轮指标计算模块

包含基于阶次谱和时域的高级齿轮诊断指标：
- FM0 / FM0_order: 粗故障检测
- FM4 / M6A / M8A: 局部故障高阶矩检测
- SER / SER_order: 边频带能量比
- CAR: 倒频谱幅值比
- analyze_sidebands_order: 基于阶次谱的边频带分析
"""
import numpy as np
from scipy.fft import rfft, rfftfreq
from typing import Dict

from ..signal_utils import (
    prepare_signal,
    compute_fft_spectrum,
    _band_energy,
    _order_band_energy,
)


def _order_band_amplitude(order_axis, spectrum, center_order: float, bandwidth: float) -> float:
    """计算指定阶次带幅值和（非能量和）"""
    order_axis = np.asarray(order_axis)
    spectrum = np.asarray(spectrum)
    mask = (order_axis >= center_order - bandwidth) & (order_axis <= center_order + bandwidth)
    if not np.any(mask):
        return 0.0
    return float(np.sum(np.abs(spectrum[mask])))


def compute_fm4(differential_signal: np.ndarray) -> float:
    """
    FM4 — 局部故障检测（单/双齿点蚀/裂纹）

    基于差分信号的归一化峭度。
    局部故障产生孤立大峰值，使分布尖锐，FM4 > 3（高斯基准）。
    """
    d = np.array(differential_signal, dtype=np.float64)
    N = len(d)
    if N < 4:
        return 0.0

    d_mean = np.mean(d)
    numerator = N * np.sum((d - d_mean) ** 4)
    denominator = np.sum((d - d_mean) ** 2) ** 2

    if denominator < 1e-12:
        return 0.0
    return float(numerator / denominator)


def compute_m6a(differential_signal: np.ndarray) -> float:
    """M6A — 表面损伤高阶矩（6阶）"""
    d = np.array(differential_signal, dtype=np.float64)
    N = len(d)
    if N < 6:
        return 0.0

    d_mean = np.mean(d)
    var = np.mean((d - d_mean) ** 2)
    if var < 1e-12:
        return 0.0

    m6 = np.mean((d - d_mean) ** 6)
    return float(m6 / (var ** 3))


def compute_m8a(differential_signal: np.ndarray) -> float:
    """M8A — 表面损伤高阶矩（8阶）"""
    d = np.array(differential_signal, dtype=np.float64)
    N = len(d)
    if N < 8:
        return 0.0

    d_mean = np.mean(d)
    var = np.mean((d - d_mean) ** 2)
    if var < 1e-12:
        return 0.0

    m8 = np.mean((d - d_mean) ** 8)
    return float(m8 / (var ** 4))


def compute_car(
    signal: np.ndarray,
    fs: float,
    rot_freq: float,
    n_harmonics: int = 3,
    tolerance_hz: float = 500.0,
) -> float:
    """
    CAR — 倒频谱幅值比（Cepstrum Amplitude Ratio）

    CAR = mean(C_peaks) / mean(C_background)
    CAR > 1 且持续上升趋势指示齿轮劣化。
    """
    arr = prepare_signal(signal)
    N = len(arr)

    # 加窗减少频谱泄漏
    window = np.hanning(N)
    sig_windowed = arr * window

    spectrum = np.fft.fft(sig_windowed)
    log_spectrum = np.log(np.abs(spectrum) + 1e-10)
    log_spectrum = log_spectrum - np.mean(log_spectrum)

    cepstrum = np.real(np.fft.ifft(log_spectrum))
    quefrency = np.arange(N) / fs
    half = N // 2
    quef = quefrency[:half]
    cep = cepstrum[:half]

    # 搜索目标倒频率对应的峰值
    peak_amps = []
    for k in range(1, n_harmonics + 1):
        tau_k = k / rot_freq
        mask = np.abs(quef - tau_k) <= (1.0 / tolerance_hz if tolerance_hz > 0 else 0.002)
        if np.any(mask):
            peak_amps.append(float(np.max(cep[mask])))

    if not peak_amps:
        return 0.0

    # 背景：高倒频率区域（> 2 * max(tau_k)）
    bg_threshold = 2.0 * n_harmonics / rot_freq
    bg_mask = quef > bg_threshold
    if not np.any(bg_mask):
        bg_mask = quef > quef[-1] * 0.5

    bg_mean = float(np.mean(cep[bg_mask])) if np.any(bg_mask) else 1e-12
    if bg_mean < 1e-12:
        bg_mean = 1e-12

    return float(np.mean(peak_amps) / bg_mean)


def compute_ser_order(
    order_axis,
    spectrum,
    mesh_order: float,
    n_sidebands: int = 6,
    sideband_bw: float = 0.3,
) -> float:
    """
    基于阶次谱计算 SER（边频带能量比）

    SER = sum(A_SB_i^+ + A_SB_i^-) / A(mesh_order)

    与 compute_ser 的区别：基于阶次谱而非 FFT 频谱，
    确保齿轮诊断结果与阶次谱页面一致。
    """
    order_axis = np.asarray(order_axis)
    spectrum = np.asarray(spectrum)

    mesh_amp = _order_band_amplitude(order_axis, spectrum, mesh_order, 0.5)
    if mesh_amp < 1e-12:
        return 0.0

    total_sideband = 0.0
    for i in range(1, n_sidebands + 1):
        sb_low = mesh_order - i
        sb_high = mesh_order + i
        total_sideband += _order_band_amplitude(order_axis, spectrum, sb_low, sideband_bw)
        total_sideband += _order_band_amplitude(order_axis, spectrum, sb_high, sideband_bw)

    return float(total_sideband / mesh_amp)


def analyze_sidebands_order(
    order_axis,
    spectrum,
    mesh_order: float,
    n_sidebands: int = 6,
) -> Dict:
    """
    基于阶次谱的边频带分析

    返回边频带的阶次、幅值、显著性、对称性等信息。
    与 analyze_sidebands 的区别：基于阶次谱而非 FFT 频谱。
    """
    order_axis = np.asarray(order_axis)
    spectrum = np.asarray(spectrum)

    mesh_amp = _order_band_amplitude(order_axis, spectrum, mesh_order, 0.5)
    if mesh_amp < 1e-12:
        return {"sidebands": [], "ser": 0.0, "mesh_amp": 0.0}

    sidebands = []
    total_sb = 0.0

    for i in range(1, n_sidebands + 1):
        sb_low = mesh_order - i
        sb_high = mesh_order + i

        amp_low = _order_band_amplitude(order_axis, spectrum, sb_low, 0.3)
        amp_high = _order_band_amplitude(order_axis, spectrum, sb_high, 0.3)

        total_sb += amp_low + amp_high

        # 显著性：边频幅值超过啮合频率的 5%
        significant = (amp_low > mesh_amp * 0.05) or (amp_high > mesh_amp * 0.05)

        sidebands.append({
            "order": i,
            "order_low": round(sb_low, 2),
            "order_high": round(sb_high, 2),
            "amp_low": round(amp_low, 6),
            "amp_high": round(amp_high, 6),
            "significant": significant,
            "asymmetry": round(abs(amp_low - amp_high) / (amp_low + amp_high + 1e-12), 4),
        })

    return {
        "sidebands": sidebands,
        "ser": round(total_sb / mesh_amp, 4),
        "mesh_amp": round(mesh_amp, 6),
    }


def compute_fm0_order(
    tsa_signal: np.ndarray,
    order_axis,
    spectrum,
    mesh_order: float,
    n_harmonics: int = 3,
) -> float:
    """
    基于阶次谱计算 FM0（粗故障检测）

    FM0 = PP / sum(A(mesh_order_harmonics))
    """
    arr = np.array(tsa_signal, dtype=np.float64)
    pp = np.max(arr) - np.min(arr)

    order_axis = np.asarray(order_axis)
    spectrum = np.asarray(spectrum)

    harmonics_sum = 0.0
    for i in range(1, n_harmonics + 1):
        harmonics_sum += _order_band_amplitude(order_axis, spectrum, mesh_order * i, 0.5)

    if harmonics_sum < 1e-12:
        return 0.0
    return float(pp / harmonics_sum)
