"""
轴承故障诊断算法模块

包含：
- 各方法共用 algorithms.bearing.envelope 的结构化包络表示
- Fast Kurtogram + 自适应包络分析
- CPW + 包络分析
- MED + 包络分析
"""
import numpy as np
from scipy.signal import stft
from typing import Dict, Tuple, Optional, List

from app.algorithms.bearing.envelope import EnvelopeParameters, compute_envelope
from .signal_utils import prepare_signal
from .preprocessing import cepstrum_pre_whitening, minimum_entropy_deconvolution


def _compute_envelope_result(
    signal: np.ndarray,
    fs: float,
    fc: Optional[float] = None,
    bw: Optional[float] = None,
    f_low_pass: float = 2000.0,
) -> Dict:
    """供尚未拆成独立 Pipeline 的轴承方法共享新包络表示。"""
    return {
        "representation": compute_envelope(
            np.asarray(signal, dtype=np.float64),
            fs,
            EnvelopeParameters(
                band_center_hz=fc,
                band_width_hz=bw,
                envelope_low_pass_hz=f_low_pass,
            ),
        )
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
            "representation": EnvelopeRepresentation,  # 结构化包络谱与实际频带
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

    # 如果峭度都很低（无明显冲击），退回标准包络分析（不限定频带）
    if best_kurt < 0.5:
        result = _compute_envelope_result(arr, fs)
        result["optimal_fc"] = None
        result["optimal_bw"] = None
        result["max_kurtosis"] = round(float(best_kurt), 4)
        result["kurtogram"] = []
        return result

    # 对最优频带执行包络分析
    result = _compute_envelope_result(arr, fs, fc=best_fc, bw=best_bw)
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
) -> Dict:
    """
    CPW（倒频谱预白化）+ 包络分析

    先消除齿轮啮合/轴频等确定性干扰，再提取包络谱检测轴承故障。

    Args:
        signal: 输入信号
        fs: 采样率
        comb_frequencies: 需要抑制的确定性频率列表 (Hz)

    Returns:
        {
            "representation": EnvelopeRepresentation,  # 结构化包络谱与实际频带
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
) -> Dict:
    """
    MED（最小熵解卷积）+ 包络分析

    先用 MED 锐化故障冲击，再做包络分析。

    Args:
        signal: 输入信号
        fs: 采样率
        med_filter_len: MED 滤波器长度

    Returns:
        {
            "representation": EnvelopeRepresentation,  # 结构化包络谱与实际频带
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
    result = _compute_envelope_result(med_signal, fs)
    result["med_filter_len"] = med_filter_len
    result["kurtosis_before"] = round(kurt_before, 4)
    result["kurtosis_after"] = round(kurt_after, 4)
    result["method"] = "MED + Envelope"

    return result


def teager_envelope_analysis(
    signal: np.ndarray,
    fs: float,
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
        return _compute_envelope_result(arr, fs)

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
        return _compute_envelope_result(arr, fs)

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

    result = _compute_envelope_result(arr, fs, fc=best_fc, bw=best_bw)
    candidates.sort(key=lambda x: x["score"], reverse=True)
    result["method"] = "Adaptive Reweighted Spectral Kurtosis Envelope"
    result["optimal_fc"] = round(float(best_fc), 2)
    result["optimal_bw"] = round(float(best_bw), 2)
    result["reweighted_score"] = round(float(best_score), 4)
    result["spectral_kurtosis_bands"] = candidates[:100]
    return result
