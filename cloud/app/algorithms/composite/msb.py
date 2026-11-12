"""四阶调制信号双谱：E[X(fc+fm)X(fc-fm)conj(X(fc))²]。

Guo 等 Sensors 2018 (doi:10.3390/s18092908), Eq.10。它不是三阶常规双谱。
返回复均值；先 abs 再平均不能抑制非耦合相位。只估计指定小网格，避免全二维 O(N²) 内存。
"""

from dataclasses import dataclass

import numpy as np
from cnn_compute import diagnostic as native_diagnostic


@dataclass(frozen=True)
class MSBParameters:
    segment_length: int = 1024
    overlap: float = 0.5
    minimum_segments: int = 3

    def __post_init__(self):
        if (
            isinstance(self.segment_length, bool)
            or not isinstance(self.segment_length, int)
            or self.segment_length < 32
        ):
            raise ValueError("MSB segment_length must be an integer >=32")
        if not np.isfinite(self.overlap) or not 0 <= self.overlap < 1:
            raise ValueError("MSB overlap must be within [0,1)")
        if (
            isinstance(self.minimum_segments, bool)
            or not isinstance(self.minimum_segments, int)
            or self.minimum_segments < 2
        ):
            raise ValueError("MSB needs at least two segments")


@dataclass(frozen=True)
class ModulationBispectrum:
    carrier_frequency_hz: np.ndarray
    modulation_frequency_hz: np.ndarray
    complex_mean: np.ndarray
    coherence: np.ndarray
    valid: np.ndarray
    segments: int
    frequency_resolution_hz: float
    requested_carrier_frequency_hz: np.ndarray
    requested_modulation_frequency_hz: np.ndarray
    amplitude_unit: str = "input_signal^4"
    definition: str = "E[X(fc+fm)X(fc-fm)conj(X(fc))^2]"

    @property
    def magnitude(self):
        return np.abs(self.complex_mean)


def compute_modulation_bispectrum(
    signal,
    sample_rate_hz,
    carrier_frequency_hz,
    modulation_frequency_hz,
    parameters=MSBParameters(),
    *,
    input_unit="input_signal",
):
    """原生四阶复平均MSB；保留请求坐标、实际bin坐标及无效网格。"""
    carriers = np.atleast_1d(np.asarray(carrier_frequency_hz, dtype=float))
    modulation = np.atleast_1d(np.asarray(modulation_frequency_hz, dtype=float))
    length = parameters.segment_length
    step = max(1, int(round(length * (1 - parameters.overlap))))
    mean, coherence, valid, count = native_diagnostic.modulation_bispectrum(
        signal,
        sample_rate_hz,
        carriers,
        modulation,
        length,
        step,
        parameters.minimum_segments,
    )
    df = sample_rate_hz / length
    return ModulationBispectrum(
        np.rint(carriers / df) * df,
        np.rint(modulation / df) * df,
        mean,
        coherence,
        valid.astype(bool, copy=False),
        count,
        df,
        carriers,
        modulation,
        f"{input_unit}^4",
    )


def analyze_msb_slice(representation: ModulationBispectrum):
    """沿carrier取平均，峰与背景均使用同一四阶幅值切片；不返回故障阈值。"""
    magnitude = representation.magnitude
    valid_counts = np.sum(representation.valid, axis=0)
    slice_values = np.full(magnitude.shape[1], np.nan)
    np.divide(
        np.nansum(magnitude, axis=0),
        valid_counts,
        out=slice_values,
        where=valid_counts > 0,
    )
    usable = np.isfinite(slice_values)
    background = (
        float(np.median(slice_values[usable]))
        if np.count_nonzero(usable) >= 3
        else None
    )
    ratios = np.full_like(slice_values, np.nan)
    if background is not None and background > 0:
        ratios[usable] = slice_values[usable] / background
    return {
        "modulation_frequency_hz": representation.modulation_frequency_hz,
        "magnitude": slice_values,
        "background": background,
        "peak_to_background": ratios,
        "amplitude_unit": representation.amplitude_unit,
    }
