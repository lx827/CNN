"""高级诊断计算的薄适配；数值循环在同一套C++模块，结果独立拥有。

连续float64输入同步借用；dtype/布局转换只在此边界进行。输出capsule持有
C++缓冲区，下一次计算不覆盖旧结果。C++执行释放GIL，无内部线程池。
"""

from __future__ import annotations

import numpy as np
from ._native import diagnostic as _native


def _vector(signal):
    values = np.asarray(signal, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError("输入必须为一维")
    return np.ascontiguousarray(values)


def deconvolve(
    signal,
    *,
    filter_length=64,
    max_iterations=30,
    tolerance=1e-6,
    ridge=1e-8,
    period=0,
    shift_order=1,
):
    """返回(signal, FIR, objective_history, iterations, converged)。

    period=0为MED，正整数为MCKD。固定矩阵只做一次QR/小R的SVD，不物化薄U。
    数值秩亏/迭代数值失败转换为LinAlgError；零能量为ValueError。
    """
    for name, value, minimum in (
        ("filter_length", filter_length, 2),
        ("max_iterations", max_iterations, 1),
        ("shift_order", shift_order, 1),
        ("period", period, 0),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(f"{name}必须为大于等于{minimum}的整数")
    try:
        return _native.deconvolve(
            _vector(signal),
            filter_length,
            max_iterations,
            tolerance,
            ridge,
            period,
            shift_order,
        )
    except RuntimeError as error:
        raise np.linalg.LinAlgError(str(error)) from error


def normalized_kurtosis(signal):
    """E[y⁴]/E[y²]²，保留输入幅值缩放不变性。"""
    return _native.normalized_kurtosis(_vector(signal))


def mckd_update(matrix, coefficients, period, shift_order, ridge):
    """独立MCKD留一乘积更新，复用完整分解的同一C++更新/求解实现。"""
    try:
        return _native.mckd_update(
            np.ascontiguousarray(matrix, dtype=np.float64),
            _vector(coefficients),
            period,
            shift_order,
            ridge,
        )
    except RuntimeError as error:
        raise np.linalg.LinAlgError(str(error)) from error


def correlated_kurtosis(signal, period, shift_order=1):
    """平方周期乘积相关峭度；周期/移位阶数显式提供。"""
    return _native.correlated_kurtosis(_vector(signal), period, shift_order)


def adaptive_filter(
    signal,
    method="lms",
    *,
    filter_length=32,
    step_size=0.01,
    delay=1,
    max_updates=0,
    alpha=0.97,
    gamma=5e-5,
    minimum_step=1e-6,
    maximum_step=0.05,
):
    """延迟参考LMS/NLMS/VSS-LMS；最多更新max_updates次，0表示全段。"""
    methods = {"lms": 0, "nlms": 1, "vsslms": 2}
    return _native.adaptive_filter(
        _vector(signal),
        methods[method],
        filter_length,
        step_size,
        delay,
        max_updates,
        alpha,
        gamma,
        minimum_step,
        maximum_step,
    )


def fast_ica(observations, *, components=0, max_iterations=200, tolerance=1e-6, seed=0):
    """samples×channels logcosh FastICA；返回独立矩阵与rank/迭代/状态。

    状态0收敛、1迭代上限、2秩亏、3固定点更新奇异。seed本实现内可重复。
    """
    values = np.ascontiguousarray(observations, dtype=np.float64)
    return _native.fast_ica(values, components, max_iterations, tolerance, seed)


def teager(signal):
    """Psi[x_n]=x_n²-x_(n-1)x_(n+1)，保留负值，端点为单边能量。"""
    return _native.teager(_vector(signal))


def complex_spectral_kurtosis(signal):
    """复高斯基谱峭度E|z|⁴/(E|z|²)²-2。"""
    values = np.ascontiguousarray(signal, dtype=np.complex128)
    return _native.complex_spectral_kurtosis(values)


def cepstral_prewhiten(signal, sample_rate, comb, width=0.02):
    """恒定频率梳状倒谱lifter，保留原复频谱相位。"""
    return _native.cepstral_prewhiten(
        _vector(signal), sample_rate, _vector(sorted(set(comb))), width
    )


def sc_scoh(signal, sample_rate, alpha, segment_length=512, step=128):
    """返回(alpha×carrier的复SC、SCoh、段数、输入尺度)，同步逐段归约。"""
    return _native.sc_scoh(
        _vector(signal), sample_rate, _vector(alpha), segment_length, step
    )


def modulation_bispectrum(
    signal,
    sample_rate,
    carriers,
    modulation,
    segment_length=1024,
    step=512,
    minimum_segments=3,
):
    """返回四阶复均值、相干、有效网格与段数；无效项NaN，不夹目标频率。"""
    return _native.modulation_bispectrum(
        _vector(signal),
        sample_rate,
        _vector(carriers),
        _vector(modulation),
        segment_length,
        step,
        minimum_segments,
    )


def filter_bank_kurtogram(
    signal, sample_rate, max_level=4, min_frequency=100.0, filter_order=4
):
    """返回真实Butterworth滤波器组逐带(low,high,level,SK,峰/中位数,P95/中位数)。"""
    return _native.filter_bank_kurtogram(
        _vector(signal), sample_rate, max_level, min_frequency, filter_order
    )
