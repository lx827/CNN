"""四阶调制信号双谱：E[X(fc+fm)X(fc-fm)conj(X(fc))²]。

Guo 等 Sensors 2018 (doi:10.3390/s18092908), Eq.10。它不是三阶常规双谱。
返回复均值；先 abs 再平均不能抑制非耦合相位。只估计指定小网格，避免全二维 O(N²) 内存。
"""
from dataclasses import dataclass

import numpy as np
from scipy.fft import rfft, rfftfreq
from scipy.signal import windows


@dataclass(frozen=True)
class MSBParameters:
    segment_length: int = 1024
    overlap: float = 0.5
    minimum_segments: int = 3

    def __post_init__(self):
        if isinstance(self.segment_length, bool) or not isinstance(self.segment_length, int) or self.segment_length < 32:
            raise ValueError("MSB segment_length must be an integer >=32")
        if not np.isfinite(self.overlap) or not 0 <= self.overlap < 1:
            raise ValueError("MSB overlap must be within [0,1)")
        if isinstance(self.minimum_segments, bool) or not isinstance(self.minimum_segments, int) or self.minimum_segments < 2:
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


def compute_modulation_bispectrum(signal, sample_rate_hz, carrier_frequency_hz, modulation_frequency_hz,
                                  parameters=MSBParameters(), *, input_unit="input_signal"):
    values = np.asarray(signal, dtype=float)
    if values.ndim != 1 or not np.all(np.isfinite(values)) or not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("MSB input must be a finite vector with positive sample rate")
    carriers = np.atleast_1d(np.asarray(carrier_frequency_hz, dtype=float))
    modulation = np.atleast_1d(np.asarray(modulation_frequency_hz, dtype=float))
    if carriers.ndim != 1 or modulation.ndim != 1 or not len(carriers) or not len(modulation):
        raise ValueError("MSB axes must be nonempty vectors")
    if not np.all(np.isfinite(carriers)) or not np.all(np.isfinite(modulation)) or np.any(carriers <= 0) or np.any(modulation <= 0):
        raise ValueError("MSB frequencies must be finite positive Hz")
    if np.any(carriers > sample_rate_hz / 2) or np.any(modulation > sample_rate_hz / 2):
        raise ValueError("MSB requested frequencies must not exceed Nyquist")
    if len(carriers) * len(modulation) > 16384:
        raise ValueError("MSB requested grid exceeds 16384 cells")
    length = parameters.segment_length
    step = max(1, int(round(length * (1 - parameters.overlap))))
    starts = range(0, len(values) - length + 1, step)
    count = len(starts)
    if count < parameters.minimum_segments:
        raise ValueError("insufficient_segments_for_complex_MSB_average")
    df = sample_rate_hz / length
    carrier_bins = np.rint(carriers / df).astype(int)
    modulation_bins = np.rint(modulation / df).astype(int)
    upper = carrier_bins[:, None] + modulation_bins[None, :]
    lower = carrier_bins[:, None] - modulation_bins[None, :]
    # 不把低于一bin的调制折叠到DC，也不把超Nyquist目标夹到边界。
    valid = (lower >= 1) & (upper <= length // 2) & (modulation_bins[None, :] >= 1)
    valid &= (carriers[:, None] + modulation[None, :] <= sample_rate_hz / 2)
    valid &= (carriers[:, None] - modulation[None, :] > 0)
    shape = (len(carriers), len(modulation))
    total = np.zeros(shape, dtype=complex)
    side_power = np.zeros(shape)
    carrier_power = np.zeros(shape)
    window = windows.hann(length, sym=False)
    # 双边傅里叶系数，bin正弦A的复系数模为A/2；MSB是输入单位四次方。
    safe_carriers = np.clip(carrier_bins, 0, length // 2)
    safe_upper = np.clip(upper, 0, length // 2)
    safe_lower = np.clip(lower, 0, length // 2)
    for start in starts:
        segment = values[start:start + length]
        transformed = rfft((segment - np.mean(segment)) * window) / np.sum(window)
        side = transformed[safe_upper] * transformed[safe_lower]
        center = transformed[safe_carriers, None] ** 2
        total += np.where(valid, side * np.conj(center), 0)
        side_power += np.where(valid, np.abs(side) ** 2, 0)
        carrier_power += np.where(valid, np.abs(center) ** 2, 0)
    mean = total / count
    denominator = np.sqrt(side_power / count * carrier_power / count)
    coherence = np.full(shape, np.nan)
    np.divide(np.abs(mean), denominator, out=coherence, where=valid & (denominator > 0))
    coherence = np.minimum(coherence, 1.0)
    mean[~valid] = complex(np.nan, np.nan)
    return ModulationBispectrum(carrier_bins * df, modulation_bins * df, mean, coherence, valid, count, df, carriers, modulation,
                                 f"{input_unit}^4")


def analyze_msb_slice(representation: ModulationBispectrum):
    """沿carrier取平均，峰与背景均使用同一四阶幅值切片；不返回故障阈值。"""
    magnitude = representation.magnitude
    valid_counts = np.sum(representation.valid, axis=0)
    slice_values = np.full(magnitude.shape[1], np.nan)
    np.divide(np.nansum(magnitude, axis=0), valid_counts, out=slice_values, where=valid_counts > 0)
    usable = np.isfinite(slice_values)
    background = float(np.median(slice_values[usable])) if np.count_nonzero(usable) >= 3 else None
    ratios = np.full_like(slice_values, np.nan)
    if background is not None and background > 0:
        ratios[usable] = slice_values[usable] / background
    return {"modulation_frequency_hz": representation.modulation_frequency_hz, "magnitude": slice_values,
            "background": background, "peak_to_background": ratios,
            "amplitude_unit": representation.amplitude_unit}
