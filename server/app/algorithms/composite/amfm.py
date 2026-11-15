"""解析信号 AM 与 FM；解调频率是调制频率，不是原始载波边带。"""

from dataclasses import dataclass

from cnn_compute import rotation as native
import numpy as np

from app.algorithms.transforms import FourierSpectrum, compute_spectrum


@dataclass(frozen=True)
class AMFMRepresentation:
    amplitude_envelope: np.ndarray
    instantaneous_frequency_hz: np.ndarray
    amplitude_spectrum: FourierSpectrum
    frequency_spectrum: FourierSpectrum
    sample_rate_hz: float
    input_unit: str


@dataclass(frozen=True)
class ModulationPeak:
    target_frequency_hz: float
    target_order: float | None
    observed_frequency_hz: float | None
    amplitude: float | None
    amplitude_unit: str
    background_amplitude: float | None
    peak_to_background: float | None
    status: str
    reason: str | None = None


def demodulate_amfm(
    signal, sample_rate_hz: float, *, input_unit="input_signal"
) -> AMFMRepresentation:
    """a=|analytic(x)|，f=diff(unwrap(arg(analytic(x)))) fs/(2π)。

    FM 位于相邻采样中点，长度 N-1；不重复 Hilbert 归一化载波，也不补尾值。
    幅值零点使瞬时相位失去定义，显式拒绝。FFT 采用公共单边 Hann 刻度。
    """
    values = np.asarray(signal, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError("AM/FM requires a scalar vector")
    envelope, frequency = native.amfm(values, sample_rate_hz)
    return AMFMRepresentation(envelope, frequency,
        compute_spectrum(envelope, sample_rate_hz, amplitude_unit=input_unit),
        compute_spectrum(frequency, sample_rate_hz, amplitude_unit="Hz"), float(sample_rate_hz), input_unit)


def analyze_modulation_peak(
    spectrum: FourierSpectrum, target_hz: float, *, reference_hz=None
) -> ModulationPeak:
    """目标附近峰和同一局部谱背景；不提供未经标定的故障阈值。"""
    axis, amplitude = spectrum.frequency_hz, spectrum.amplitude
    if not np.isfinite(target_hz) or target_hz <= 0:
        raise ValueError("modulation target must be positive Hz")
    if reference_hz is not None and (not np.isfinite(reference_hz) or reference_hz <= 0):
        raise ValueError("reference speed must be positive Hz")
    order = target_hz / reference_hz if reference_hz else None
    df = axis[1] - axis[0]
    tolerance = max(1.5 * df, 0.02 * target_hz)
    observed, peak, background, count, found = native.local_peak(axis, amplitude, target_hz,
        tolerance, 3.0, 8.0, median_background=True)
    if target_hz > axis[-1] or not found or target_hz < 2 * df:
        return ModulationPeak(target_hz, order, None, None, spectrum.amplitude_unit,
            None, None, "not_evaluable", "target_outside_resolvable_modulation_band")
    background = background if count else None
    ratio = peak / background if background is not None and background > 0 else None
    return ModulationPeak(target_hz, order, observed, peak, spectrum.amplitude_unit,
        background, ratio, "computed")
