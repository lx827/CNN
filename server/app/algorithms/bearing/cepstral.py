"""恒定频率梳状干扰的倒谱预白化（CPW）及包络 Pipeline。"""

from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np
from cnn_compute import diagnostic as native_diagnostic
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
    signal, sample_rate_hz, comb_frequencies_hz, notch_width_ratio=0.02
):
    """原生恒定梳状倒谱lifter，保留原相位；不处理滑频。"""
    comb = _validate_comb(sample_rate_hz, comb_frequencies_hz)
    return native_diagnostic.cepstral_prewhiten(
        signal, sample_rate_hz, comb, notch_width_ratio
    )


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
