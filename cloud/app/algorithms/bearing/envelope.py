"""标准 Hilbert 包络计算，只产生信号表示，不判断故障。"""
from dataclasses import dataclass
from typing import Optional

import numpy as np
from numpy.typing import NDArray
from scipy.fft import rfft, rfftfreq
from scipy.signal import butter, hilbert, sosfiltfilt, windows

from app.algorithms.core import FrequencyBand, Spectrum


@dataclass(frozen=True)
class EnvelopeParameters:
    """包络计算参数；center/bandwidth 为空时使用采样率自适应频带。"""

    band_center_hz: Optional[float] = None
    band_width_hz: Optional[float] = None
    envelope_low_pass_hz: float = 2000.0
    filter_order: int = 4


@dataclass(frozen=True)
class EnvelopeRepresentation:
    """包络谱及实际执行的滤波参数。"""

    spectrum: Spectrum
    band: FrequencyBand
    envelope_low_pass_hz: float
    sample_rate_hz: float


def _resolve_band(fs: float, params: EnvelopeParameters) -> FrequencyBand:
    nyquist = fs / 2.0
    if params.band_center_hz is None:
        if fs < 10000.0:
            # Nyquist 的 25%~75%，与算法文档中的默认共振带定义一致。
            low, high = nyquist * 0.25, nyquist * 0.75
        else:
            low, high = 2000.0, 4000.0
            if low >= high or high >= nyquist:
                low, high = nyquist * 0.25, nyquist * 0.75
    else:
        width = params.band_width_hz
        if width is None:
            width = min(2000.0, fs * 0.3)
        if not np.isfinite(params.band_center_hz) or not np.isfinite(width) or width <= 0:
            raise ValueError("带通中心和带宽必须是有限数，且带宽为正数")
        low = params.band_center_hz - width / 2.0
        high = params.band_center_hz + width / 2.0
        # 截到可实现的频率范围，并通过 FrequencyBand 返回真实边界。
        low = max(1e-6, low)
        high = min(nyquist - 1e-6, high)
    return FrequencyBand(float(low), float(high))


def compute_envelope(
    signal: NDArray[np.float64],
    sample_rate_hz: float,
    parameters: Optional[EnvelopeParameters] = None,
) -> EnvelopeRepresentation:
    """执行带通→Hilbert→低通→单边幅值谱，返回实际频带和幅值单位。"""
    params = parameters or EnvelopeParameters()
    arr = np.asarray(signal, dtype=np.float64)
    if arr.ndim != 1:
        raise ValueError("包络分析输入必须是一维信号")
    if len(arr) < 64:
        raise ValueError("包络分析至少需要 64 个采样点")
    if not np.all(np.isfinite(arr)):
        raise ValueError("输入信号不能包含 NaN 或无穷值")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("采样率必须为正数")
    if isinstance(params.filter_order, bool) or not isinstance(params.filter_order, int):
        raise ValueError("滤波器阶数必须是整数")
    if params.filter_order <= 0:
        raise ValueError("滤波器阶数必须为正整数")
    if not np.isfinite(params.envelope_low_pass_hz) or params.envelope_low_pass_hz <= 0:
        raise ValueError("低通截止频率必须是有限正数")

    arr = arr - np.mean(arr)
    nyquist = sample_rate_hz / 2.0
    band = _resolve_band(sample_rate_hz, params)
    sos = butter(
        params.filter_order,
        [band.low_hz / nyquist, band.high_hz / nyquist],
        btype="bandpass",
        output="sos",
    )
    filtered = sosfiltfilt(sos, arr)

    envelope = np.abs(hilbert(filtered))
    low_pass_hz = min(params.envelope_low_pass_hz, nyquist * (1.0 - 1e-6))
    low_sos = butter(
        params.filter_order,
        low_pass_hz / nyquist,
        btype="lowpass",
        output="sos",
    )
    envelope = sosfiltfilt(low_sos, envelope)
    envelope = envelope - np.mean(envelope)

    # 周期 Hann + 相干增益补偿；正弦分量的返回幅值对应输入信号峰值。
    window = windows.hann(len(envelope), sym=False)
    amplitude = np.abs(rfft(envelope * window)) * (2.0 / np.sum(window))
    amplitude[0] *= 0.5
    if len(envelope) % 2 == 0:
        amplitude[-1] *= 0.5
    frequency = rfftfreq(len(envelope), 1.0 / sample_rate_hz)
    spectrum = Spectrum(frequency_hz=frequency, amplitude=amplitude)
    return EnvelopeRepresentation(
        # 分析始终使用完整有效包络频带；展示截断由业务层单独执行。
        spectrum=spectrum.truncated(low_pass_hz),
        band=band,
        envelope_low_pass_hz=float(low_pass_hz),
        sample_rate_hz=float(sample_rate_hz),
    )
