"""敏感分量的原始物理/统计指标；不包含阈值、归一化、排序或故障判断。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
from numpy.typing import NDArray
from scipy.signal import hilbert


FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class ComponentMetrics:
    """不可计算的统计量返回 ``None``，不以 0 冒充有效测量。"""

    correlation: float | None
    kurtosis_pearson: float | None
    kurtosis_excess: float | None
    envelope_entropy: float | None
    energy: float
    energy_ratio: float | None
    center_frequency_hz: float | None


def _validate(component: FloatArray, sample_rate_hz: float) -> FloatArray:
    arr = np.asarray(component, dtype=np.float64)
    if arr.ndim != 1 or len(arr) < 8:
        raise ValueError("分量必须是一维且至少包含 8 个采样点")
    if not np.all(np.isfinite(arr)):
        raise ValueError("分量不能包含 NaN 或无穷值")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise ValueError("采样率必须是有限正数")
    return arr


def compute_component_metrics(
    component: FloatArray,
    sample_rate_hz: float,
    reference: FloatArray | None = None,
) -> ComponentMetrics:
    """计算一个已对齐分量的原始指标。

    ``reference`` 必须与分量等长并共享时间轴；WP/DWT 调用方应传入节点的
    原采样率重构，而不是长度不同的抽取系数。相关系数取 Pearson 绝对值。
    """
    arr = _validate(component, sample_rate_hz)
    scale = float(np.max(np.abs(arr)))
    normalized = arr / scale if scale else arr
    centered = normalized - np.mean(normalized)
    variance = float(np.var(centered))
    energy = float(np.sum(arr * arr))
    correlation = None
    energy_ratio = None
    if reference is not None:
        ref = _validate(reference, sample_rate_hz)
        if len(ref) != len(arr):
            raise ValueError("分量与参考信号必须等长并共享时间轴，禁止截断对齐")
        ref_scale = float(np.max(np.abs(ref)))
        normalized_ref = ref / ref_scale if ref_scale else ref
        ref_centered = normalized_ref - np.mean(normalized_ref)
        denominator = float(np.std(centered) * np.std(ref_centered))
        if denominator > 0:
            correlation = abs(float(np.mean(centered * ref_centered) / denominator))
        reference_energy = float(np.sum(ref * ref))
        if reference_energy > np.finfo(np.float64).tiny:
            energy_ratio = energy / reference_energy

    kurtosis_pearson = None
    kurtosis_excess = None
    if variance > 0:
        kurtosis_pearson = float(np.mean(centered**4) / variance**2)
        kurtosis_excess = kurtosis_pearson - 3.0

    envelope_entropy = None
    envelope = np.abs(hilbert(centered))
    envelope = np.abs(envelope - np.mean(envelope))
    envelope_sum = float(np.sum(envelope))
    if envelope_sum > np.finfo(np.float64).tiny:
        probabilities = envelope[envelope > 0.0] / envelope_sum
        envelope_entropy = float(-np.sum(probabilities * np.log2(probabilities)))

    center_frequency_hz = None
    power = np.abs(np.fft.rfft(centered)) ** 2
    total_power = float(np.sum(power))
    if total_power > np.finfo(np.float64).tiny:
        frequencies = np.fft.rfftfreq(len(arr), 1.0 / sample_rate_hz)
        center_frequency_hz = float(np.dot(frequencies, power) / total_power)
    return ComponentMetrics(
        correlation=correlation,
        kurtosis_pearson=kurtosis_pearson,
        kurtosis_excess=kurtosis_excess,
        envelope_entropy=envelope_entropy,
        energy=energy,
        energy_ratio=energy_ratio,
        center_frequency_hz=center_frequency_hz,
    )


def compute_component_metrics_batch(
    components: Iterable[FloatArray],
    sample_rate_hz: float,
    reference: FloatArray | None = None,
) -> tuple[ComponentMetrics, ...]:
    """逐分量计算原始指标，保持调用方给定的分量类型与顺序。"""
    return tuple(
        compute_component_metrics(component, sample_rate_hz, reference=reference)
        for component in components
    )
