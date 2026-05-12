"""
特征提取模块

统一提供时域、频域、包络域、阶次域的特征提取接口。
"""
import numpy as np
from scipy import stats
from scipy.fft import rfft, rfftfreq
from scipy.signal import hilbert
from typing import Dict, List, Tuple, Optional

from .utils import (
    prepare_signal, rms, peak_value, crest_factor, kurtosis, skewness,
    compute_fft_spectrum, bandpass_filter, lowpass_filter, _band_energy,
)


def compute_time_features(signal: np.ndarray) -> Dict[str, float]:
    """
    计算时域统计特征

    Returns:
        {
            "peak", "rms", "mean_abs", "kurtosis", "skewness",
            "margin", "shape_factor", "impulse_factor", "crest_factor",
        }
    """
    arr = prepare_signal(signal)
    if len(arr) == 0:
        return {}

    peak = peak_value(arr)
    rms_val = rms(arr)
    mean_abs = float(np.mean(np.abs(arr)))

    kurt = kurtosis(arr, fisher=False)
    skew = skewness(arr)

    margin = peak / rms_val if rms_val > 1e-12 else 0.0
    shape_factor = rms_val / mean_abs if mean_abs > 1e-12 else 0.0
    impulse_factor = peak / mean_abs if mean_abs > 1e-12 else 0.0
    crest = crest_factor(arr)

    return {
        "peak": round(peak, 6),
        "rms": round(rms_val, 6),
        "mean_abs": round(mean_abs, 6),
        "kurtosis": round(kurt, 4),
        "skewness": round(skew, 4),
        "margin": round(margin, 4),
        "shape_factor": round(shape_factor, 4),
        "impulse_factor": round(impulse_factor, 4),
        "crest_factor": round(crest, 4),
    }


def compute_fft_features(
    signal: np.ndarray,
    fs: float,
    gear_teeth: Optional[Dict] = None,
    bearing_params: Optional[Dict] = None,
    rot_freq: Optional[float] = None,
) -> Dict[str, float]:
    """
    从 FFT 频谱提取齿轮/轴承相关特征

    Args:
        signal: 输入信号
        fs: 采样率
        gear_teeth: 齿轮参数 {input: Z_in, output: Z_out}
        bearing_params: 轴承参数 {n, d, D, alpha}
        rot_freq: 轴转频 (Hz)，不传则自动估计

    Returns:
        特征字典
    """
    arr = prepare_signal(signal)
    xf, yf = compute_fft_spectrum(arr, fs)
    yf = np.array(yf)
    xf = np.array(xf)
    total_energy = float(np.sum(yf ** 2)) + 1e-10

    features = {}

    # 估计转频
    if rot_freq is None:
        rot_freq = _estimate_rot_freq_simple(arr, fs)
    features["estimated_rot_freq"] = round(rot_freq, 3)

    # --- 齿轮特征 ---
    if gear_teeth and isinstance(gear_teeth, dict):
        z_in = gear_teeth.get("input", 0)
        if z_in > 0:
            mesh_freq = rot_freq * z_in
            features["mesh_freq_hz"] = round(mesh_freq, 2)
            mesh_amp = _band_energy(xf, yf, mesh_freq, 5.0)
            features["mesh_freq_ratio"] = round(mesh_amp / total_energy, 6)

            sideband_total = 0.0
            sideband_count = 0
            for n in range(1, 4):
                sb_low = mesh_freq - n * rot_freq
                sb_high = mesh_freq + n * rot_freq
                sb_amp = _band_energy(xf, yf, sb_low, 2.0) + _band_energy(xf, yf, sb_high, 2.0)
                sideband_total += sb_amp
                if sb_amp > mesh_amp * 0.05:
                    sideband_count += 1
            features["sideband_total_ratio"] = round(sideband_total / total_energy, 6)
            features["sideband_count"] = sideband_count

    # --- 轴承特征 ---
    if bearing_params and isinstance(bearing_params, dict):
        from .utils import _compute_bearing_fault_freqs
        bfreqs = _compute_bearing_fault_freqs(rot_freq, bearing_params)
        for name, f_hz in bfreqs.items():
            features[f"{name}_hz"] = round(f_hz, 2)
            f_amp = _band_energy(xf, yf, f_hz, 3.0)
            features[f"{name}_ratio"] = round(f_amp / total_energy, 6)
            harmonic_total = 0.0
            for h in range(2, 4):
                harmonic_total += _band_energy(xf, yf, f_hz * h, 3.0)
            features[f"{name}_harmonic_ratio"] = round(harmonic_total / total_energy, 6)

    return features


def compute_envelope_features(
    signal: np.ndarray,
    fs: float,
    bearing_params: Optional[Dict] = None,
    rot_freq: Optional[float] = None,
    max_freq: float = 1000.0,
) -> Dict[str, float]:
    """
    从包络谱提取轴承故障特征

    Args:
        signal: 输入信号
        fs: 采样率
        bearing_params: 轴承参数
        rot_freq: 轴转频 (Hz)
        max_freq: 包络谱最大频率

    Returns:
        特征字典
    """
    arr = prepare_signal(signal)

    # 包络提取
    analytic = hilbert(arr)
    envelope = np.abs(analytic)
    envelope = envelope - np.mean(envelope)

    # 包络谱 FFT
    n = len(envelope)
    yf = np.abs(rfft(envelope))
    xf = rfftfreq(n, 1.0 / fs)

    # 限制频率范围
    mask = xf <= max_freq
    xf = xf[mask]
    yf = yf[mask]
    total_energy = float(np.sum(yf ** 2)) + 1e-10

    features = {"total_env_energy": round(total_energy, 6)}

    if not bearing_params or not isinstance(bearing_params, dict):
        return features

    if rot_freq is None:
        rot_freq = _estimate_rot_freq_simple(arr, fs)

    # 计算轴承特征频率
    n_balls = bearing_params.get("n", 0)
    d = bearing_params.get("d", 0)
    D = bearing_params.get("D", 0)
    alpha = np.radians(bearing_params.get("alpha", 0))

    if n_balls > 0 and d > 0 and D > 0:
        cos_a = np.cos(alpha)
        dd = (d / D) * cos_a

        freqs = {
            "BPFO": (n_balls / 2.0) * rot_freq * (1 - dd),
            "BPFI": (n_balls / 2.0) * rot_freq * (1 + dd),
            "BSF": (D / (2.0 * d)) * rot_freq * (1 - dd ** 2),
            "FTF": 0.5 * rot_freq * (1 - dd),
        }

        for name, f_hz in freqs.items():
            env_amp = _band_energy(xf, yf, f_hz, 2.0)
            features[f"{name}_env_ratio"] = round(env_amp / total_energy, 6)
            harmonic_total = 0.0
            for h in range(2, 5):
                harmonic_total += _band_energy(xf, yf, f_hz * h, 2.0)
            features[f"{name}_env_harmonic_ratio"] = round(harmonic_total / total_energy, 6)

    return features


def _estimate_rot_freq_simple(
    sig: np.ndarray,
    fs: float,
    freq_range: Tuple[float, float] = (10, 100),
    harmonics_num: int = 5,
    bandwidth_hz: float = 3.0,
) -> float:
    """
    通过频谱峰值法估计转频（简化版）
    """
    N = len(sig)
    spectrum = np.abs(rfft(sig))
    freqs = rfftfreq(N, d=1.0 / fs)
    df = freqs[1] - freqs[0]

    spectrum_norm = spectrum / (spectrum.max() + 1e-10)
    mask = (freqs >= freq_range[0]) & (freqs <= freq_range[1])
    search_freqs = freqs[mask]
    search_spectrum = spectrum_norm[mask]

    if len(search_freqs) == 0:
        return freq_range[0]

    bw_bins = max(1, int(round(bandwidth_hz / df / 2)))
    min_base_energy = 0.015 * (2 * bw_bins + 1)

    best_freq = search_freqs[0]
    best_energy = 0.0

    for f in search_freqs:
        idx_base = np.argmin(np.abs(freqs - f))
        base_band = spectrum_norm[max(0, idx_base - bw_bins):min(len(spectrum), idx_base + bw_bins + 1)]
        base_energy = float(np.sum(base_band))
        if base_energy < min_base_energy:
            continue

        energy = 0.0
        for h in range(1, harmonics_num + 1):
            harmonic_freq = f * h
            if harmonic_freq > fs / 2:
                break
            idx = np.argmin(np.abs(freqs - harmonic_freq))
            band = spectrum_norm[max(0, idx - bw_bins):min(len(spectrum), idx + bw_bins + 1)]
            weight = 1.0 / h
            energy += float(np.sum(band)) * weight

        if energy > best_energy:
            best_energy = energy
            best_freq = f

    if best_energy == 0.0:
        best_local_idx = int(np.argmax(search_spectrum))
        best_freq = search_freqs[best_local_idx]

    return float(best_freq)


# 向后兼容：轴承特征频率计算
from .utils import (
    prepare_signal, rms, peak_value, crest_factor, kurtosis, skewness,
    compute_fft_spectrum, bandpass_filter, lowpass_filter,
)
