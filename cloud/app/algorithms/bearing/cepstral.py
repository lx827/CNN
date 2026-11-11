"""恒定频率梳状干扰的倒谱预白化（CPW）及包络 Pipeline。"""

from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np
from numpy.typing import NDArray

from app.algorithms.bearing.envelope import EnvelopeRepresentation
from app.algorithms.bearing.spectral_kurtosis import (
    FilterBankKurtogramParameters,
    FilterBankKurtogramPipeline,
    FilterBankKurtogramResult,
)


@dataclass(frozen=True)
class CPWEnvelopeResult:
    status: str
    method: str
    representation: Optional[EnvelopeRepresentation]
    reason: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    kurtogram: Optional[FilterBankKurtogramResult] = None


def _validate_comb(
    sample_rate_hz: float, comb_frequencies_hz: Sequence[float]
) -> tuple[float, ...]:
    values = tuple(sorted(set(float(value) for value in comb_frequencies_hz)))
    if not values:
        raise ValueError("CPW 必须提供至少一个稳定梳状频率")
    if not all(
        np.isfinite(value) and 0.0 < value < sample_rate_hz / 2.0 for value in values
    ):
        raise ValueError("梳状频率必须全部有限、为正且低于 Nyquist")
    return values


def cepstral_pre_whitening(
    signal: NDArray[np.float64],
    sample_rate_hz: float,
    comb_frequencies_hz: Sequence[float],
    notch_width_ratio: float = 0.02,
) -> np.ndarray:
    """在基频对应倒频率及其 rahmonics 处插值 lifter，再保留原相位重构。

    输入频率必须是整段记录内稳定的梳状基频；该恒定频率模型不处理滑频。
    """
    arr = np.asarray(signal, dtype=np.float64)
    if arr.ndim != 1 or len(arr) < 256:
        raise ValueError("CPW 输入必须是一维且至少 256 点")
    if (
        not np.all(np.isfinite(arr))
        or not np.isfinite(sample_rate_hz)
        or sample_rate_hz <= 0
    ):
        raise ValueError("CPW 输入和采样率必须为有限值，采样率为正")
    if not np.isfinite(notch_width_ratio) or not 0.0 < notch_width_ratio <= 0.1:
        raise ValueError("倒谱陷波相对宽度必须位于 (0,0.1]")
    comb = _validate_comb(sample_rate_hz, comb_frequencies_hz)
    n = len(arr)
    spectrum = np.fft.rfft(arr - np.mean(arr))
    magnitude = np.abs(spectrum)
    peak = float(np.max(magnitude))
    if peak == 0.0:
        raise ValueError("零能量信号无法倒谱预白化")
    floor = peak * 1e-10
    log_magnitude = np.log(np.maximum(magnitude, floor))
    cepstrum = np.fft.irfft(log_magnitude, n=n)

    for fundamental in comb:
        base_index = sample_rate_hz / fundamental
        for harmonic in range(1, int(n / (2.0 * base_index)) + 1):
            center = harmonic * base_index
            half_width = max(1, int(round(center * notch_width_ratio / 2.0)))
            left = int(np.floor(center)) - half_width
            right = int(np.ceil(center)) + half_width
            if left < 1 or right >= n // 2 - 1:
                continue
            indices = np.arange(left, right + 1)
            # 对称编辑正负倒频率，保持实倒谱的共轭对称关系。
            for signed in (1, -1):
                target = (signed * indices) % n
                left_value = cepstrum[(signed * (left - 1)) % n]
                right_value = cepstrum[(signed * (right + 1)) % n]
                weights = (indices - left + 1) / (right - left + 2)
                cepstrum[target] = left_value * (1.0 - weights) + right_value * weights

    edited_log_magnitude = np.fft.rfft(cepstrum).real
    edited_log_magnitude = np.clip(
        edited_log_magnitude,
        float(np.min(log_magnitude)) - 2.0,
        float(np.max(log_magnitude)) + 2.0,
    )
    reconstructed = np.exp(edited_log_magnitude) * np.exp(1j * np.angle(spectrum))
    return np.fft.irfft(reconstructed, n=n)


class CPWEnvelopePipeline:
    method = "Constant-comb cepstral pre-whitening + filter-bank SK + Envelope"

    def run(
        self,
        signal: NDArray[np.float64],
        sample_rate_hz: float,
        comb_frequencies: Sequence[float],
        comb_is_stable: bool = True,
        parameters: Optional[FilterBankKurtogramParameters] = None,
    ) -> CPWEnvelopeResult:
        if not comb_is_stable:
            return CPWEnvelopeResult(
                status="indeterminate",
                method=self.method,
                representation=None,
                reason="time_varying_comb_requires_time_frequency_model",
            )
        if not comb_frequencies:
            return CPWEnvelopeResult(
                status="indeterminate",
                method=self.method,
                representation=None,
                reason="missing_stable_comb_frequencies",
            )
        comb = _validate_comb(sample_rate_hz, comb_frequencies)
        whitened = cepstral_pre_whitening(signal, sample_rate_hz, comb)
        downstream = FilterBankKurtogramPipeline().run(
            whitened, sample_rate_hz, parameters
        )
        return CPWEnvelopeResult(
            status=downstream.status,
            method=self.method,
            representation=downstream.representation,
            reason=downstream.reason,
            metadata={"comb_frequencies_hz": comb, "comb_model": "constant_frequency"},
            kurtogram=downstream,
        )
