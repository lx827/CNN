"""基础数值入口。float64 C 连续输入借用；其它输入在边界集中转换一次。

NumPy 最终数组持有独立 C++ owner，工作区复用和后续调用不会覆盖结果。
参数/数值前提由公开 C++ 入口检查；这里仅转换布局和类型。
"""

import numpy as np
from numpy.typing import ArrayLike, NDArray

from ._native import numeric as _impl

FloatArray = NDArray[np.float64]


def _input(value: ArrayLike) -> FloatArray:
    return np.ascontiguousarray(value, dtype=np.float64)


def spectrum(
    signal: ArrayLike, fs: float, remove_mean: bool = True
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """返回 frequency、peak amplitude、mean-square power 三个一维数组。"""
    return _impl.spectrum(_input(signal), fs, remove_mean)


def stft(
    signal: ArrayLike, fs: float, window: int, overlap: int, nfft: int
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """返回 time、frequency、(frequency,time) 单边峰值幅值。"""
    return _impl.stft(_input(signal), fs, window, overlap, nfft)


def statistics(signal: ArrayLike, margin_floor: float = 1e-12) -> list[float]:
    """返回 peak,rms,Pearson kurtosis,skewness,margin,shape,impulse,crest。"""
    return _impl.statistics(_input(signal), margin_floor)


def time_domain(
    signal: ArrayLike, fs: float, window: int = 1024, step: int = 0
) -> tuple[list[float], FloatArray, FloatArray, int, int]:
    """返回 overall、起点时间、(frames,8) 统计、实际 window 与 step。"""
    return _impl.time_domain(_input(signal), fs, window, step)


def segmented_rms(
    signal: ArrayLike, fs: float, segment: int, remove_mean: bool = True
) -> FloatArray:
    """返回两列矩阵 (中心时间,RMS)，保留不足整段的尾部。"""
    return _impl.segmented_rms(_input(signal), fs, segment, remove_mean)


def extrema(x: ArrayLike, y: ArrayLike, maximum: int = 2400) -> FloatArray:
    """绘图极值抽点，返回两列 (x,y)；不改变输入。"""
    return _impl.extrema(_input(x), _input(y), maximum)


def autocorrelation(signal: ArrayLike, demean: bool = True) -> FloatArray:
    """返回未归一化的非负 lag 自相关。"""
    return _impl.autocorrelation(_input(signal), demean)


def cepstrum(signal: ArrayLike) -> FloatArray:
    """周期 Hann、去均值 log magnitude 实倒谱的前 N//2 点。"""
    return _impl.cepstrum(_input(signal))


def hilbert_envelope(signal: ArrayLike) -> FloatArray:
    """返回实信号解析表示的模。"""
    return _impl.hilbert_envelope(_input(signal))
