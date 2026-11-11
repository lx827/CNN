"""Teager 能量算子（TEO）与显式工程组合的包络 Pipeline。"""
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from numpy.typing import NDArray
from scipy.fft import rfft, rfftfreq
from scipy.signal import butter, hilbert, sosfiltfilt, windows

from app.algorithms.bearing.envelope import (
    EnvelopeParameters,
    EnvelopeRepresentation,
    _resolve_band,
)
from app.algorithms.core import Spectrum


@dataclass(frozen=True)
class TEOEnvelopeResult:
    status: str
    method: str
    representation: Optional[EnvelopeRepresentation]
    raw_teo: Optional[NDArray[np.float64]]
    envelope_input: Optional[NDArray[np.float64]]
    reason: Optional[str] = None
    metadata: dict = field(default_factory=dict)


def teager_energy_operator(signal: NDArray[np.float64]) -> np.ndarray:
    """Psi[x_n]=x_n^2-x_{n-1}x_{n+1}；保留负值，端点采用单边能量。"""
    x = np.asarray(signal, dtype=np.float64)
    if x.ndim != 1 or len(x) < 3 or not np.all(np.isfinite(x)):
        raise ValueError("TEO 输入必须是一维有限数组且至少 3 点")
    result = np.empty_like(x)
    result[0] = x[0] ** 2
    result[-1] = x[-1] ** 2
    result[1:-1] = x[1:-1] ** 2 - x[:-2] * x[2:]
    return result


def _envelope_after_teo(
    values: np.ndarray,
    sample_rate_hz: float,
    band,
    parameters: EnvelopeParameters,
) -> EnvelopeRepresentation:
    """已限带且已执行 TEO 的信号只做 Hilbert、低通和单边幅值谱。"""
    nyquist = sample_rate_hz / 2.0
    envelope = np.abs(hilbert(values))
    low_pass_hz = min(parameters.envelope_low_pass_hz, nyquist * (1.0 - 1e-6))
    low_sos = butter(parameters.filter_order, low_pass_hz, btype="lowpass", fs=sample_rate_hz, output="sos")
    envelope = sosfiltfilt(low_sos, envelope)
    envelope -= np.mean(envelope)
    window = windows.hann(len(envelope), sym=False)
    amplitude = np.abs(rfft(envelope * window)) * (2.0 / np.sum(window))
    amplitude[0] *= 0.5
    if len(envelope) % 2 == 0:
        amplitude[-1] *= 0.5
    spectrum = Spectrum(
        frequency_hz=rfftfreq(len(envelope), 1.0 / sample_rate_hz),
        amplitude=amplitude, amplitude_unit="input_signal^2",
    )
    return EnvelopeRepresentation(
        spectrum=spectrum.truncated(low_pass_hz),
        band=band,
        envelope_low_pass_hz=float(low_pass_hz),
        sample_rate_hz=float(sample_rate_hz),
    )


class TEOEnvelopePipeline:
    """限带→原始 TEO→仅包络输入截负→Hilbert；不宣称普适变速补偿。"""

    method = "Band-limited TEO (clip for envelope only) + Hilbert Envelope"

    def run(
        self,
        signal: NDArray[np.float64],
        sample_rate_hz: float,
        parameters: Optional[EnvelopeParameters] = None,
    ) -> TEOEnvelopeResult:
        params = parameters or EnvelopeParameters()
        x = np.asarray(signal, dtype=np.float64)
        if x.ndim != 1 or len(x) < 64 or not np.all(np.isfinite(x)):
            raise ValueError("TEO 包络输入必须是一维有限数组且至少 64 点")
        if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
            raise ValueError("采样率必须为有限正数")
        if not np.isfinite(params.envelope_low_pass_hz) or params.envelope_low_pass_hz <= 0:
            raise ValueError("包络低通截止频率必须为有限正数")
        if isinstance(params.filter_order, bool) or not isinstance(params.filter_order, int) or params.filter_order <= 0:
            raise ValueError("滤波器阶数必须为正整数")
        x = x - np.mean(x)
        if not np.any(x):
            return TEOEnvelopeResult(
                status="indeterminate",
                method=self.method,
                representation=None,
                raw_teo=None,
                envelope_input=None,
                reason="zero_energy",
            )
        band = _resolve_band(sample_rate_hz, params)
        sos = butter(
            params.filter_order,
            [band.low_hz, band.high_hz],
            btype="bandpass",
            fs=sample_rate_hz,
            output="sos",
        )
        filtered = sosfiltfilt(sos, x)
        raw = teager_energy_operator(filtered)
        # 多分量 TEO 含交叉项；限带只是工程缓解，截负也只用于包络输入。
        envelope_input = np.maximum(raw, 0.0)
        representation = _envelope_after_teo(envelope_input, sample_rate_hz, band, params)
        return TEOEnvelopeResult(
            status="computed",
            method=self.method,
            representation=representation,
            raw_teo=raw,
            envelope_input=envelope_input,
            metadata={
                "combination": "bandpass_then_raw_teo_then_clip_then_hilbert",
                "negative_value_policy": "clip_only_after_raw_teo",
                "multi_component_policy": "bandpass_before_teo_cross_terms_remain_engineering_approximation",
                "speed_model": "none_no_variable_speed_compensation_claim",
            },
        )
