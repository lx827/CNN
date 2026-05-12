"""
齿轮故障诊断算法模块

包含：
- FM0: 粗故障检测（齿断裂/严重磨损）
- FM4: 局部故障检测（单/双齿点蚀/裂纹）
- NA4: 趋势型故障检测（损伤扩展追踪）
- NB4: 局部齿损坏（包络域）
- M6A / M8A: 表面损伤高阶矩
- ER: 能量比（多齿磨损）
- SER: 边频带能量比（核心频域指标）
- CAR: 倒频谱幅值比
- 边频带分析
"""
import numpy as np
from scipy import stats
from scipy.fft import rfft, rfftfreq
from scipy.signal import hilbert
from typing import Dict, List, Optional, Tuple

from .utils import prepare_signal, compute_fft_spectrum, _band_energy


def compute_fm0(
    tsa_signal: np.ndarray,
    mesh_freq: float,
    fs: float,
    n_harmonics: int = 3,
) -> float:
    """
    FM0 — 粗故障检测（齿断裂/严重磨损）

    FM0 = PP / sum(A(f_mesh_harmonics))
    """
    arr = np.array(tsa_signal, dtype=np.float64)
    pp = np.max(arr) - np.min(arr)

    xf, yf = compute_fft_spectrum(arr, fs)
    yf = np.array(yf)

    harmonics_sum = 0.0
    for i in range(1, n_harmonics + 1):
        harmonics_sum += _band_energy(xf, yf, mesh_freq * i, 5.0)

    if harmonics_sum < 1e-12:
        return 0.0
    return float(pp / harmonics_sum)


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


def compute_na4(
    residual_signal: np.ndarray,
    historical_residuals: List[np.ndarray],
) -> float:
    """
    NA4 — 趋势型故障检测（损伤扩展追踪）

    准归一化峭度，分母为历史平均方差，随损伤扩展单调上升。

    Args:
        residual_signal: 当前残余信号
        historical_residuals: 历史残余信号列表（至少1条）
    """
    r = np.array(residual_signal, dtype=np.float64)
    N = len(r)
    if N < 4:
        return 0.0

    r_mean = np.mean(r)
    numerator = (1.0 / N) * np.sum((r - r_mean) ** 4)

    if not historical_residuals:
        denominator = ((1.0 / N) * np.sum((r - r_mean) ** 2)) ** 2
        return float(numerator / denominator) if denominator > 1e-12 else 0.0

    variances = []
    for hist in historical_residuals:
        hist = np.array(hist, dtype=np.float64)
        if len(hist) > 0:
            hist_mean = np.mean(hist)
            variances.append((1.0 / len(hist)) * np.sum((hist - hist_mean) ** 2))

    if not variances:
        return 0.0

    denom_mean = np.mean(variances)
    return float(numerator / (denom_mean ** 2)) if denom_mean > 1e-12 else 0.0


def compute_nb4(
    residual_signal: np.ndarray,
    fs: float,
    historical_envelopes: Optional[List[np.ndarray]] = None,
    band_center: Optional[float] = None,
    band_width: float = 500.0,
) -> float:
    """
    NB4 — 局部齿损坏（包络域）

    检测由局部齿损坏引起的瞬态负载波动（反映在包络上）。
    """
    r = np.array(residual_signal, dtype=np.float64)

    # 带通滤波 + 包络
    if band_center is not None:
        from .utils import bandpass_filter
        filtered = bandpass_filter(r, fs, max(10, band_center - band_width / 2), min(fs / 2 - 10, band_center + band_width / 2))
    else:
        filtered = r

    envelope = np.abs(hilbert(filtered))
    N = len(envelope)
    if N < 4:
        return 0.0

    e_mean = np.mean(envelope)
    numerator = (1.0 / N) * np.sum((envelope - e_mean) ** 4)

    if not historical_envelopes:
        denominator = ((1.0 / N) * np.sum((envelope - e_mean) ** 2)) ** 2
        return float(numerator / denominator) if denominator > 1e-12 else 0.0

    variances = []
    for hist in historical_envelopes:
        hist = np.array(hist, dtype=np.float64)
        if len(hist) > 0:
            hist_mean = np.mean(hist)
            variances.append((1.0 / len(hist)) * np.sum((hist - hist_mean) ** 2))

    if not variances:
        return 0.0

    denom_mean = np.mean(variances)
    return float(numerator / (denom_mean ** 2)) if denom_mean > 1e-12 else 0.0


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


def compute_er(
    differential_signal: np.ndarray,
    tsa_signal: np.ndarray,
    mesh_freq: float,
    fs: float,
    n_harmonics: int = 3,
    n_sidebands: int = 3,
) -> float:
    """
    ER — 能量比（多齿磨损）

    ER = RMS[d(t)] / (啮合谐波能量 + 边带能量)
    """
    d = np.array(differential_signal, dtype=np.float64)
    rms_d = np.sqrt(np.mean(d ** 2))

    xf, yf = compute_fft_spectrum(np.array(tsa_signal), fs)
    yf = np.array(yf)

    # 啮合谐波能量
    mesh_energy = 0.0
    for i in range(1, n_harmonics + 1):
        mesh_energy += _band_energy(xf, yf, mesh_freq * i, 5.0)

    # 边带能量
    sb_energy = 0.0
    rot_freq = mesh_freq / 18  # 近似估算，实际应传入
    for j in range(1, n_sidebands + 1):
        sb_energy += _band_energy(xf, yf, mesh_freq - j * rot_freq, 2.0)
        sb_energy += _band_energy(xf, yf, mesh_freq + j * rot_freq, 2.0)

    denom = mesh_energy + sb_energy
    if denom < 1e-12:
        return 0.0
    return float(rms_d / denom)


def compute_ser(
    signal: np.ndarray,
    fs: float,
    mesh_freq: float,
    rot_freq: float,
    n_sidebands: int = 6,
    sideband_bw: float = 2.0,
) -> float:
    """
    SER — 边频带能量比（核心频域指标）

    SER = sum(A_SB_i^+ + A_SB_i^-) / A(f_mesh)

    健康齿轮 SER < 1；故障齿轮 SER > 1 且随劣化单调上升。
    """
    arr = prepare_signal(signal)
    xf, yf = compute_fft_spectrum(arr, fs)
    yf = np.array(yf)

    mesh_amp = _band_energy(xf, yf, mesh_freq, 5.0)
    if mesh_amp < 1e-12:
        return 0.0

    total_sideband = 0.0
    for i in range(1, n_sidebands + 1):
        sb_low = mesh_freq - i * rot_freq
        sb_high = mesh_freq + i * rot_freq
        total_sideband += _band_energy(xf, yf, sb_low, sideband_bw)
        total_sideband += _band_energy(xf, yf, sb_high, sideband_bw)

    return float(total_sideband / mesh_amp)


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


def analyze_sidebands(
    signal: np.ndarray,
    fs: float,
    mesh_freq: float,
    rot_freq: float,
    n_sidebands: int = 6,
) -> Dict:
    """
    边频带分析

    返回边频带的幅值、显著性、对称性等信息。
    """
    arr = prepare_signal(signal)
    xf, yf = compute_fft_spectrum(arr, fs)
    yf = np.array(yf)

    mesh_amp = _band_energy(xf, yf, mesh_freq, 5.0)
    if mesh_amp < 1e-12:
        return {"sidebands": [], "ser": 0.0}

    sidebands = []
    total_sb = 0.0

    for i in range(1, n_sidebands + 1):
        sb_low = mesh_freq - i * rot_freq
        sb_high = mesh_freq + i * rot_freq

        amp_low = _band_energy(xf, yf, sb_low, 2.0)
        amp_high = _band_energy(xf, yf, sb_high, 2.0)

        total_sb += amp_low + amp_high

        # 显著性：边频幅值超过啮合频率的 5%
        significant = (amp_low > mesh_amp * 0.05) or (amp_high > mesh_amp * 0.05)

        sidebands.append({
            "order": i,
            "freq_low": round(sb_low, 2),
            "freq_high": round(sb_high, 2),
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
