"""公开滤波能力；输入只读借用，返回 NumPy 持有的独立 C++ 缓冲区。"""

import numpy as np
from numpy.typing import ArrayLike, NDArray

from ._native import filtering as _impl

FloatArray = NDArray[np.float64]


def butterworth(order: int, low_hz: float, high_hz: float, fs: float) -> FloatArray:
    """返回 (sections,6) SOS；low=0 为低通，high>=Nyquist 为高通。"""
    return _impl.butterworth(order, low_hz, high_hz, fs)


def sosfiltfilt(sos: ArrayLike, signal: ArrayLike, padlen: int = -1) -> FloatArray:
    """SOS 双向滤波，odd 延拓；默认 padlen 与 SciPy SOS 规则一致。"""
    return _impl.sosfiltfilt(
        np.ascontiguousarray(signal, dtype=np.float64),
        np.ascontiguousarray(sos, dtype=np.float64),
        padlen,
    )


def hann(samples: int) -> FloatArray:
    """周期 Hann，单点返回 1。"""
    return _impl.hann(samples)


def detrend(signal: ArrayLike, linear: bool = False) -> FloatArray:
    """去均值或最小二乘直线趋势。"""
    return _impl.detrend(np.ascontiguousarray(signal, dtype=np.float64), linear)


def savgol(
    signal: ArrayLike, window: int, order: int, derivative: int = 0, delta: float = 1.0
) -> FloatArray:
    """奇数窗 Savitzky-Golay，端点采用局部多项式插值。"""
    return _impl.savgol(
        np.ascontiguousarray(signal, dtype=np.float64), window, order, derivative, delta
    )
