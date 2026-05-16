"""
Savitzky-Golay 多项式平滑模块

与现有小波去噪的互补性：
- 小波阈值：适合脉冲型/非平稳噪声，但可能产生伪吉布斯振荡；
- S-G 滤波：适合宽带高斯噪声背景下的平滑，保留峰形，计算极快（O(N)）。
"""
import numpy as np
from scipy.signal import savgol_filter
from typing import Tuple, Dict


def sg_denoise(
    signal: np.ndarray,
    window_length: int = 51,
    polyorder: int = 3,
    deriv: int = 0,
) -> Tuple[np.ndarray, Dict]:
    """
    Savitzky-Golay 多项式平滑去噪

    Args:
        signal: 输入信号
        window_length: 窗口长度（必须为奇数）
        polyorder: 多项式阶数
        deriv: 导数阶数（0=平滑）

    Returns:
        (平滑后信号, 元信息)
    """
    arr = np.array(signal, dtype=np.float64)
    N = len(arr)

    if window_length > N:
        window_length = N if N % 2 == 1 else N - 1
    if window_length < 3:
        return arr, {"method": "sg", "window_length": N, "polyorder": polyorder, "note": "too_short"}

    if window_length % 2 == 0:
        window_length -= 1

    polyorder = min(polyorder, window_length - 1)
    smoothed = savgol_filter(arr, window_length=window_length, polyorder=polyorder, deriv=deriv)

    noise_est = np.median(np.abs(arr - smoothed)) / 0.6745
    snr_imp = float(np.std(arr) / (np.std(arr - smoothed) + 1e-12))

    return smoothed, {
        "method": "savgol",
        "window_length": window_length,
        "polyorder": polyorder,
        "deriv": deriv,
        "noise_est": round(noise_est, 6),
        "snr_improvement": round(snr_imp, 4),
    }


def sg_trend_residual(
    signal: np.ndarray,
    window_length: int = 501,
    polyorder: int = 2,
) -> Tuple[np.ndarray, np.ndarray, Dict]:
    """
    S-G 趋势提取 + 残余信号分离
    """
    arr = np.array(signal, dtype=np.float64)
    trend, info = sg_denoise(arr, window_length=window_length, polyorder=polyorder)
    residual = arr - trend
    return trend, residual, info
