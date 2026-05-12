"""
轴承故障诊断算法模块

包含：
- 标准包络分析
- Fast Kurtogram + 自适应包络分析
- CPW + 包络分析
- MED + 包络分析
"""
import numpy as np
from scipy.signal import hilbert
from scipy.fft import rfft, rfftfreq
from typing import Dict, Tuple, Optional, List

from .signal_utils import (
    prepare_signal, bandpass_filter, lowpass_filter, compute_snr,
    parabolic_interpolation,
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

    # Step 1: 带通滤波
    if fc is None:
        fc = 3000.0
    if bw is None:
        bw = 2000.0
    low = max(100, fc - bw / 2)
    high = min(fs / 2 - 100, fc + bw / 2)
    if low >= high:
        # 频段非法，fallback 到默认频段
        low = max(100, 3000.0 - 2000.0 / 2)
        high = min(fs / 2 - 100, 3000.0 + 2000.0 / 2)
    filtered = bandpass_filter(arr, fs, low, high)

    # Step 2-3: 希尔伯特变换 → 包络
    analytic = hilbert(filtered)
    envelope = np.abs(analytic)

    # Step 4: 低通滤波
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
    for level in range(1, max_level + 1):
        nperseg = max(64, N // (2 ** level))
        noverlap = nperseg // 2

        from scipy.signal import stft
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

    # 如果峭度都很低（无明显冲击），fallback 到默认频段
    if best_kurt < 0.5:
        best_fc = 3000.0
        best_bw = 2000.0

    # 对最优频带执行包络分析
    result = envelope_analysis(arr, fs, fc=best_fc, bw=best_bw, max_freq=1000.0)
    result["optimal_fc"] = round(best_fc, 2)
    result["optimal_bw"] = round(best_bw, 2)
    result["max_kurtosis"] = round(float(best_kurt), 4)
    result["kurtogram"] = kurtogram_data[:100]  # 限制返回数量

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
