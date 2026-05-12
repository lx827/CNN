"""
通用工具函数
"""
import numpy as np
from scipy import signal as scipy_signal
from scipy.fft import rfft, rfftfreq
from typing import Tuple, Optional, List


def remove_dc(signal: np.ndarray) -> np.ndarray:
    """去除直流分量（零均值化）"""
    return signal - np.mean(signal)


def linear_detrend(signal: np.ndarray) -> np.ndarray:
    """线性去趋势"""
    return scipy_signal.detrend(signal, type='linear')


def prepare_signal(signal, detrend: bool = False) -> np.ndarray:
    """
    信号预处理：零均值化或线性去趋势
    detrend=False: 去直流（零均值化）
    detrend=True:  线性去趋势（消除 y=kx+b 漂移）
    """
    arr = np.array(signal, dtype=np.float64)
    if detrend:
        return scipy_signal.detrend(arr, type='linear')
    return arr - np.mean(arr)


def bandpass_filter(
    signal: np.ndarray,
    fs: float,
    f_low: float,
    f_high: float,
    order: int = 4,
) -> np.ndarray:
    """Butterworth 带通滤波"""
    nyq = fs / 2.0
    low = max(1e-6, f_low / nyq)
    high = min(1.0 - 1e-6, f_high / nyq)
    b, a = scipy_signal.butter(order, [low, high], btype='band')
    return scipy_signal.filtfilt(b, a, signal)


def lowpass_filter(
    signal: np.ndarray,
    fs: float,
    f_cut: float,
    order: int = 4,
) -> np.ndarray:
    """Butterworth 低通滤波"""
    nyq = fs / 2.0
    cut = min(1.0 - 1e-6, f_cut / nyq)
    b, a = scipy_signal.butter(order, cut, btype='low')
    return scipy_signal.filtfilt(b, a, signal)


def highpass_filter(
    signal: np.ndarray,
    fs: float,
    f_cut: float,
    order: int = 4,
) -> np.ndarray:
    """Butterworth 高通滤波"""
    nyq = fs / 2.0
    cut = max(1e-6, f_cut / nyq)
    b, a = scipy_signal.butter(order, cut, btype='high')
    return scipy_signal.filtfilt(b, a, signal)


def compute_fft_spectrum(
    signal: np.ndarray,
    fs: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """计算 FFT 频谱，返回 (频率轴, 幅值)"""
    arr = prepare_signal(signal)
    n = len(arr)
    yf = np.abs(rfft(arr))
    xf = rfftfreq(n, 1.0 / fs)
    return xf, yf


def compute_power_spectrum(
    signal: np.ndarray,
    fs: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """计算功率谱（幅值平方）"""
    xf, yf = compute_fft_spectrum(signal, fs)
    return xf, yf ** 2


def find_peaks_in_spectrum(
    freqs: np.ndarray,
    amps: np.ndarray,
    target_freq: float,
    tolerance_hz: float = 2.0,
    n_harmonics: int = 5,
) -> dict:
    """
    在频谱中搜索目标频率及其谐波族

    Returns:
        {
            "fundamental": {"freq": float, "amp": float, "snr": float},
            "harmonics": [{"freq": float, "amp": float, "order": int}, ...],
            "sidebands": [{"freq": float, "amp": float, "offset_hz": float}, ...],
        }
    """
    result = {
        "fundamental": None,
        "harmonics": [],
        "sidebands": [],
    }
    df = freqs[1] - freqs[0] if len(freqs) > 1 else 1.0
    background = np.median(amps)

    # 搜索基频
    mask = np.abs(freqs - target_freq) <= tolerance_hz
    if np.any(mask):
        idx = np.argmax(amps[mask])
        abs_idx = np.where(mask)[0][idx]
        result["fundamental"] = {
            "freq": float(freqs[abs_idx]),
            "amp": float(amps[abs_idx]),
            "snr": float(amps[abs_idx] / background) if background > 0 else 0.0,
        }

    # 搜索谐波
    for h in range(2, n_harmonics + 1):
        hf = target_freq * h
        if hf > freqs[-1]:
            break
        hmask = np.abs(freqs - hf) <= tolerance_hz
        if np.any(hmask):
            idx = np.argmax(amps[hmask])
            abs_idx = np.where(hmask)[0][idx]
            result["harmonics"].append({
                "freq": float(freqs[abs_idx]),
                "amp": float(amps[abs_idx]),
                "order": h,
            })

    return result


def compute_snr(peak_amp: float, spectrum: np.ndarray, method: str = "median") -> float:
    """计算峰值信噪比"""
    if method == "median":
        background = np.median(spectrum)
    elif method == "mean":
        background = np.mean(spectrum)
    else:
        background = np.percentile(spectrum, 75)
    if background <= 0:
        background = 1e-12
    return peak_amp / background


def kurtosis(signal: np.ndarray, fisher: bool = False) -> float:
    """计算峭度，fisher=False 时正态分布=3"""
    from scipy import stats
    return float(stats.kurtosis(signal, fisher=fisher))


def skewness(signal: np.ndarray) -> float:
    """计算偏度"""
    from scipy import stats
    return float(stats.skew(signal))


def rms(signal: np.ndarray) -> float:
    """均方根"""
    return float(np.sqrt(np.mean(signal ** 2)))


def peak_value(signal: np.ndarray) -> float:
    """峰值（最大绝对值）"""
    return float(np.max(np.abs(signal)))


def crest_factor(signal: np.ndarray) -> float:
    """峰值因子 = Peak / RMS"""
    r = rms(signal)
    return peak_value(signal) / r if r > 1e-12 else 0.0


def parabolic_interpolation(freqs, spectrum, idx):
    """抛物线插值精确定位谱峰频率"""
    if idx <= 0 or idx >= len(spectrum) - 1:
        return freqs[idx]
    alpha = spectrum[idx - 1]
    beta = spectrum[idx]
    gamma = spectrum[idx + 1]
    if beta <= max(alpha, gamma):
        return freqs[idx]
    p = 0.5 * (alpha - gamma) / (alpha - 2 * beta + gamma)
    return float(freqs[idx] + p * (freqs[1] - freqs[0]))


def _band_energy(freq, amp, center: float, bandwidth: float) -> float:
    """计算指定频带能量"""
    freq = np.asarray(freq)
    amp = np.asarray(amp)
    mask = (freq >= center - bandwidth) & (freq <= center + bandwidth)
    if not np.any(mask):
        return 0.0
    return float(np.sum(amp[mask] ** 2))
