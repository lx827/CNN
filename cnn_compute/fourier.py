"""未移频 Fourier 入口；正向不归一化，逆向除以 N。单线程 pocketfft。"""

import numpy as np
from numpy.typing import ArrayLike, NDArray

from ._native import fourier as _impl

ComplexArray = NDArray[np.complex128]
FloatArray = NDArray[np.float64]


def fft(signal: ArrayLike) -> ComplexArray:
    """返回完整复频谱，实输入走成熟 real FFT；结果独立拥有。"""
    a = np.asarray(signal)
    if np.iscomplexobj(a):
        return _impl.fft(np.ascontiguousarray(a, dtype=np.complex128))
    return _impl.fft_real(np.ascontiguousarray(a, dtype=np.float64))


def ifft(spectrum: ArrayLike) -> ComplexArray:
    """任意完整复频谱的复逆变换，不假设 Hermitian 对称。"""
    return _impl.ifft(np.ascontiguousarray(spectrum, dtype=np.complex128))


def rfft(signal: ArrayLike) -> ComplexArray:
    """返回 N//2+1 个非负频点。"""
    return _impl.rfft(np.ascontiguousarray(signal, dtype=np.float64))


def irfft(half_spectrum: ArrayLike, samples: int) -> FloatArray:
    """Hermitian 半谱的实逆变换；显式 samples 区分奇偶原长。"""
    return _impl.irfft(
        np.ascontiguousarray(half_spectrum, dtype=np.complex128), samples
    )


def convolve(first: ArrayLike, second: ArrayLike) -> FloatArray:
    """返回 full 线性实卷积；空输入返回空数组。"""
    return _impl.convolve(
        np.ascontiguousarray(first, dtype=np.float64),
        np.ascontiguousarray(second, dtype=np.float64),
    )
