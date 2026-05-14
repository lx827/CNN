"""
轴承故障诊断算法模块

包含：
- 标准包络分析
- Fast Kurtogram + 自适应包络分析
- CPW + 包络分析
- MED + 包络分析
"""
import numpy as np
from scipy.signal import hilbert, stft
from scipy.fft import rfft, rfftfreq
from typing import Dict, Tuple, Optional, List

from .signal_utils import (
    prepare_signal, bandpass_filter, lowpass_filter,
)
from .preprocessing import cepstrum_pre_whitening, minimum_entropy_deconvolution


def envelope_analysis(
    signal: np.ndarray,
    fs: float,
    fc: Optional[float] = None,
    bw: Optional[float] = None,
    f_low_pass: float = 2000.0,
    max_freq: float = 1000.0,
) -> Dict:
    """
    标准包络分析（Envelope Analysis）

    Args:
        signal: 输入信号
        fs: 采样率
        fc: 带通中心频率，None 则使用 2000~4000 Hz 默认频段
        bw: 带通带宽，None 则使用 2000 Hz
        f_low_pass: 包络低通截止频率
        max_freq: 返回包络谱的最大频率

    Returns:
        {
            "envelope_freq": List[float],
            "envelope_amp": List[float],
            "band_center": float,
            "band_width": float,
        }
    """
    arr = prepare_signal(signal)

    # Step 1: 带通滤波 — 根据采样率自适应选择共振频段
    if fc is None:
        # 低采样率场景（<10kHz）：取 Nyquist 的 25%~75% 作为共振带
        if fs < 10000:
            fc = fs * 0.45  # e.g. 8192*0.45 ≈ 3686 Hz
            bw = fs * 0.35  # e.g. 8192*0.35 ≈ 2867 Hz
        else:
            fc = 3000.0
            bw = 2000.0
    if bw is None:
        bw = min(2000.0, fs * 0.3)
    low = max(100, fc - bw / 2)
    high = min(fs / 2 - 100, fc + bw / 2)
    if low >= high:
        # 频段非法，fallback
        low = max(100, fs * 0.15)
        high = min(fs / 2 - 100, fs * 0.85)
    filtered = bandpass_filter(arr, fs, low, high)

    # Step 2-3: 希尔伯特变换 → 包络
    analytic = hilbert(filtered)
    envelope = np.abs(analytic)

    # Step 4: 低通滤波（截止频率自适应采样率）
    if f_low_pass > fs * 0.3:
        f_low_pass = fs * 0.3  # 8k→2.4k, 25.6k→7.68k, capped
    envelope = lowpass_filter(envelope, fs, f_low_pass)
    envelope = envelope - np.mean(envelope)

    # Step 5: FFT 包络谱
    n = len(envelope)
    yf = np.abs(rfft(envelope))
    xf = rfftfreq(n, 1.0 / fs)

    mask = xf <= max_freq
    return {
        "envelope_freq": [round(float(f), 2) for f in xf[mask]],
        "envelope_amp": [round(float(a), 4) for a in yf[mask]],
        "band_center": fc,
        "band_width": bw,
    }


def fast_kurtogram(
    signal: np.ndarray,
    fs: float,
    max_level: int = 6,
    f_low: float = 100.0,
) -> Dict:
    """
    快速谱峭度图（Fast Kurtogram）+ 最优频带包络分析

    基于 Antoni (2007) 的 1/3-二叉树滤波器组分解。
    为工程实时性做了简化，用 STFT 近似代替完整滤波器组。

    Args:
        signal: 输入信号
        fs: 采样率
        max_level: 分解层数
        f_low: 最低搜索频率（排除工频干扰）

    Returns:
        {
            "envelope_freq": List[float],
            "envelope_amp": List[float],
            "optimal_fc": float,      # 最优中心频率
            "optimal_bw": float,      # 最优带宽
            "max_kurtosis": float,    # 最大峭度值
            "kurtogram": List[Dict],  # 所有频带的峭度分布
        }
    """
    arr = prepare_signal(signal)
    N = len(arr)

    kurtogram_data = []
    best_kurt = -1.0
    best_fc = f_low
    best_bw = 500.0

    # 简化版 Fast Kurtogram：用多尺度 STFT 近似
    # 层数 l 对应不同的频率分辨率
    from scipy.signal import stft
    for level in range(1, max_level + 1):
        nperseg = max(64, N // (2 ** level))
        noverlap = nperseg // 2

        f, t, Zxx = stft(arr, fs=fs, nperseg=nperseg, noverlap=noverlap)

        # 每个频带计算峭度
        for i, freq in enumerate(f):
            if freq < f_low:
                continue
            # 带宽近似为该层的频率分辨率
            bw_approx = fs / nperseg
            fc_approx = freq

            # 提取该频带的时域信号（ISTFT 单频带）
            band_signal = np.abs(Zxx[i, :])
            if len(band_signal) < 10:
                continue

            # 计算该频带复包络的峭度
            kurt = np.mean(band_signal ** 4) / (np.mean(band_signal ** 2) ** 2 + 1e-12) - 2

            kurtogram_data.append({
                "level": level,
                "fc": round(fc_approx, 2),
                "bw": round(bw_approx, 2),
                "kurtosis": round(float(kurt), 4),
            })

            if kurt > best_kurt:
                best_kurt = kurt
                best_fc = fc_approx
                best_bw = bw_approx

    # 如果峭度都很低（无明显冲击），fallback 到自适应默认频段
    if best_kurt < 0.5:
        if fs < 10000:
            best_fc = fs * 0.45
            best_bw = fs * 0.35
        else:
            best_fc = 3000.0
            best_bw = 2000.0

    # 对最优频带执行包络分析
    result = envelope_analysis(arr, fs, fc=best_fc, bw=best_bw, max_freq=1000.0)
    result["optimal_fc"] = round(best_fc, 2)
    result["optimal_bw"] = round(best_bw, 2)
    result["max_kurtosis"] = round(float(best_kurt), 4)
    # 限制返回数量，按峭度排序保留前100条
    kurtogram_data.sort(key=lambda x: x["kurtosis"], reverse=True)
    result["kurtogram"] = kurtogram_data[:100]

    return result


def cpw_envelope_analysis(
    signal: np.ndarray,
    fs: float,
    comb_frequencies: List[float],
    max_freq: float = 1000.0,
) -> Dict:
    """
    CPW（倒频谱预白化）+ 包络分析

    先消除齿轮啮合/轴频等确定性干扰，再提取包络谱检测轴承故障。

    Args:
        signal: 输入信号
        fs: 采样率
        comb_frequencies: 需要抑制的确定性频率列表 (Hz)
        max_freq: 包络谱最大频率

    Returns:
        {
            "envelope_freq": List[float],
            "envelope_amp": List[float],
            "comb_frequencies": List[float],
        }
    """
    arr = prepare_signal(signal)

    # Step 1: CPW 预白化
    cpw_signal = cepstrum_pre_whitening(arr, fs, comb_frequencies=comb_frequencies)

    # Step 2: 对 CPW 后的信号做 Fast Kurtogram 包络分析
    result = fast_kurtogram(cpw_signal, fs, max_level=5)
    result["comb_frequencies"] = comb_frequencies
    result["method"] = "CPW + Fast Kurtogram Envelope"

    return result


def med_envelope_analysis(
    signal: np.ndarray,
    fs: float,
    med_filter_len: int = 64,
    max_freq: float = 1000.0,
) -> Dict:
    """
    MED（最小熵解卷积）+ 包络分析

    先用 MED 锐化故障冲击，再做包络分析。

    Args:
        signal: 输入信号
        fs: 采样率
        med_filter_len: MED 滤波器长度
        max_freq: 包络谱最大频率

    Returns:
        {
            "envelope_freq": List[float],
            "envelope_amp": List[float],
            "med_filter_len": int,
            "kurtosis_before": float,
            "kurtosis_after": float,
        }
    """
    arr = prepare_signal(signal)

    kurt_before = float(np.mean(arr ** 4) / (np.var(arr) ** 2 + 1e-12))

    # MED 增强
    med_signal, _ = minimum_entropy_deconvolution(arr, filter_len=med_filter_len)

    kurt_after = float(np.mean(med_signal ** 4) / (np.var(med_signal) ** 2 + 1e-12))

    # 包络分析
    result = envelope_analysis(med_signal, fs, max_freq=max_freq)
    result["med_filter_len"] = med_filter_len
    result["kurtosis_before"] = round(kurt_before, 4)
    result["kurtosis_after"] = round(kurt_after, 4)
    result["method"] = "MED + Envelope"

    return result


def teager_envelope_analysis(
    signal: np.ndarray,
    fs: float,
    max_freq: float = 1000.0,
) -> Dict:
    """
    Teager Energy Operator (TEO) envelope analysis.

    The TEO emphasizes transient impact energy before Hilbert envelope
    extraction. It is useful for weak bearing faults under strong broadband
    noise, while still returning the same envelope spectrum shape used by the
    rest of the diagnosis engine.
    """
    arr = prepare_signal(signal)
    if len(arr) < 3:
        return envelope_analysis(arr, fs, max_freq=max_freq)

    teo = arr[1:-1] ** 2 - arr[:-2] * arr[2:]
    teo = np.pad(teo, (1, 1), mode="edge")
    teo = prepare_signal(np.maximum(teo, 0.0))
    result = fast_kurtogram(teo, fs, max_level=5)
    result["method"] = "TEO + Fast Kurtogram Envelope"
    result["teager_rms"] = round(float(np.sqrt(np.mean(teo ** 2))), 6)
    return result


def spectral_kurtosis_envelope_analysis(
    signal: np.ndarray,
    fs: float,
    max_level: int = 6,
    f_low: float = 100.0,
    max_freq: float = 1000.0,
) -> Dict:
    """
    Adaptive reweighted spectral-kurtosis envelope analysis.

    This is an engineering approximation of reweighted kurtogram ideas:
    candidate bands are scored by spectral kurtosis, impulsiveness and local
    SNR, then the best band is used for envelope spectrum extraction.
    """
    arr = prepare_signal(signal)
    n = len(arr)
    if n < 128:
        return envelope_analysis(arr, fs, max_freq=max_freq)

    candidates = []
    best_score = -1.0
    best_fc = None
    best_bw = None

    for level in range(2, max_level + 1):
        nperseg = min(max(128, n // (2 ** level)), 4096)
        noverlap = nperseg // 2
        freqs, _, zxx = stft(arr, fs=fs, nperseg=nperseg, noverlap=noverlap)
        mag = np.abs(zxx)
        if mag.size == 0:
            continue

        bin_bw = fs / nperseg
        group_bins = max(1, int(2 ** max(0, level - 2)))
        for start in range(0, len(freqs), group_bins):
            stop = min(start + group_bins, len(freqs))
            fc = float(np.mean(freqs[start:stop]))
            if fc < f_low or fc >= fs / 2 - 10:
                continue

            band_mag = mag[start:stop, :].reshape(-1)
            if band_mag.size < 8:
                continue

            power = band_mag ** 2
            mean_power = float(np.mean(power)) + 1e-12
            sk = float(np.mean((power - mean_power) ** 4) / (np.var(power) ** 2 + 1e-12))
            impulsiveness = float(np.max(band_mag) / (np.median(band_mag) + 1e-12))
            snr = float(np.percentile(band_mag, 95) / (np.median(band_mag) + 1e-12))
            score = max(0.0, sk - 3.0) * np.log1p(impulsiveness) * np.log1p(snr)
            bw = max(bin_bw * group_bins, fs / 512)

            candidates.append({
                "level": level,
                "fc": round(fc, 2),
                "bw": round(float(bw), 2),
                "spectral_kurtosis": round(sk, 4),
                "impulsiveness": round(impulsiveness, 4),
                "snr": round(snr, 4),
                "score": round(float(score), 4),
            })
            if score > best_score:
                best_score = score
                best_fc = fc
                best_bw = bw

    if best_fc is None or best_score <= 0:
        return fast_kurtogram(arr, fs, max_level=max_level, f_low=f_low)

    result = envelope_analysis(arr, fs, fc=best_fc, bw=best_bw, max_freq=max_freq)
    candidates.sort(key=lambda x: x["score"], reverse=True)
    result["method"] = "Adaptive Reweighted Spectral Kurtosis Envelope"
    result["optimal_fc"] = round(float(best_fc), 2)
    result["optimal_bw"] = round(float(best_bw), 2)
    result["reweighted_score"] = round(float(best_score), 4)
    result["spectral_kurtosis_bands"] = candidates[:100]
    return result
