"""解析信号 AM 与 FM；解调频率是调制频率，不是原始载波边带。"""
from dataclasses import dataclass

import numpy as np
from scipy.signal import hilbert

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


def demodulate_amfm(signal, sample_rate_hz: float, *, input_unit="input_signal") -> AMFMRepresentation:
    """a=|analytic(x)|，f=diff(unwrap(arg(analytic(x)))) fs/(2π)。

    FM 位于相邻采样中点，长度 N-1；不重复 Hilbert 归一化载波，也不补尾值。
    幅值零点使瞬时相位失去定义，显式拒绝。FFT 采用公共单边 Hann 刻度。
    """
    values = np.asarray(signal, dtype=float)
    if values.ndim != 1 or len(values) < 64 or not np.all(np.isfinite(values)):
        raise ValueError("AM/FM requires at least 64 finite scalar samples")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be positive")
    analytic = hilbert(values - np.mean(values))
    envelope = np.abs(analytic)
    scale = float(np.max(envelope))
    if scale == 0 or np.min(envelope) <= 64 * np.finfo(float).eps * scale:
        raise ValueError("undefined_instantaneous_phase_at_amplitude_null")
    frequency = np.diff(np.unwrap(np.angle(analytic))) * (sample_rate_hz / (2 * np.pi))
    return AMFMRepresentation(
        envelope, frequency, compute_spectrum(envelope, sample_rate_hz, amplitude_unit=input_unit),
        compute_spectrum(frequency, sample_rate_hz, amplitude_unit="Hz"),
        float(sample_rate_hz), input_unit,
    )


def analyze_modulation_peak(spectrum: FourierSpectrum, target_hz: float, *, reference_hz=None) -> ModulationPeak:
    """目标附近峰和同一局部谱背景；不提供未经标定的故障阈值。"""
    axis, amplitude = spectrum.frequency_hz, spectrum.amplitude
    if not np.isfinite(target_hz) or target_hz <= 0:
        raise ValueError("modulation target must be positive Hz")
    if reference_hz is not None and (not np.isfinite(reference_hz) or reference_hz <= 0):
        raise ValueError("reference speed must be positive Hz")
    order = target_hz / reference_hz if reference_hz else None
    df = axis[1] - axis[0]
    tolerance = max(1.5 * df, 0.02 * target_hz)
    mask = (np.abs(axis - target_hz) <= tolerance) & (axis > 0)
    if target_hz > axis[-1] or not np.any(mask) or target_hz < 2 * df:
        return ModulationPeak(target_hz, order, None, None, spectrum.amplitude_unit, None, None,
                              "not_evaluable", "target_outside_resolvable_modulation_band")
    indices = np.flatnonzero(mask)
    index = int(indices[np.argmax(amplitude[indices])])
    bg_mask = (np.abs(axis - target_hz) >= 3 * tolerance) & (np.abs(axis - target_hz) <= 8 * tolerance) & (axis > 0)
    background = float(np.median(amplitude[bg_mask])) if np.any(bg_mask) else None
    peak = float(amplitude[index])
    ratio = peak / background if background is not None and background > 0 else None
    return ModulationPeak(target_hz, order, float(axis[index]), peak, spectrum.amplitude_unit,
                          background, ratio, "computed")
