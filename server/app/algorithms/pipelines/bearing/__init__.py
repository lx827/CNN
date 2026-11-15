"""标准轴承包络的分析与诊断 Pipeline。"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Optional

from numpy.typing import NDArray

from app.algorithms.bearing.analysis import EnvelopeAnalysis, analyze_envelope_spectrum
from app.algorithms.bearing.envelope import (
    EnvelopeParameters,
    EnvelopeRepresentation,
    compute_envelope,
)
from app.algorithms.bearing.evaluation import EnvelopeEvaluation, evaluate_envelope
from app.algorithms.mechanics import BearingGeometry


@dataclass(frozen=True)
class BearingEnvelopeAnalysis:
    representation: EnvelopeRepresentation
    envelope_analysis: EnvelopeAnalysis


@dataclass(frozen=True)
class BearingEnvelopeDiagnosis:
    analysis: BearingEnvelopeAnalysis
    evaluation: EnvelopeEvaluation


class BearingEnvelopePipeline:
    """组合包络计算、指标提取和阈值评估，不持有任何业务状态。"""

    def __init__(
        self,
        geometry: Optional[BearingGeometry] = None,
        parameters: Optional[EnvelopeParameters] = None,
    ) -> None:
        self.geometry = geometry
        self.parameters = parameters or EnvelopeParameters()

    def analyze(
        self,
        signal: NDArray[np.float64],
        sample_rate_hz: float,
        rot_frequency_hz: Optional[float] = None,
        rot_frequency_std_hz: float = 0.0,
    ) -> BearingEnvelopeAnalysis:
        if rot_frequency_hz is not None and (
            not isfinite(rot_frequency_hz) or rot_frequency_hz <= 0
        ):
            raise ValueError("转频必须是有限正数；未知转频请传 None")
        if not isfinite(rot_frequency_std_hz) or rot_frequency_std_hz < 0:
            raise ValueError("转频标准差必须是有限非负数")
        representation = compute_envelope(signal, sample_rate_hz, self.parameters)
        return self.analyze_representation(
            representation,
            rot_frequency_hz,
            rot_frequency_std_hz,
        )

    def analyze_representation(
        self,
        representation: EnvelopeRepresentation,
        rot_frequency_hz: Optional[float] = None,
        rot_frequency_std_hz: float = 0.0,
    ) -> BearingEnvelopeAnalysis:
        """分析已由高级方法生成的包络表示，不重复滤波、解调或 FFT。"""
        analysis = analyze_envelope_spectrum(
            representation.spectrum,
            geometry=self.geometry,
            rot_frequency_hz=rot_frequency_hz,
            rot_frequency_std_hz=rot_frequency_std_hz,
        )
        return BearingEnvelopeAnalysis(
            representation=representation, envelope_analysis=analysis
        )

    def evaluate(self, analysis: BearingEnvelopeAnalysis) -> EnvelopeEvaluation:
        """直接评估已有指标，不重新执行滤波或 FFT。"""
        return evaluate_envelope(analysis.envelope_analysis)

    def run(
        self,
        signal: NDArray[np.float64],
        sample_rate_hz: float,
        rot_frequency_hz: Optional[float] = None,
        rot_frequency_std_hz: float = 0.0,
    ) -> BearingEnvelopeDiagnosis:
        analysis = self.analyze(
            signal,
            sample_rate_hz,
            rot_frequency_hz=rot_frequency_hz,
            rot_frequency_std_hz=rot_frequency_std_hz,
        )
        return BearingEnvelopeDiagnosis(
            analysis=analysis, evaluation=self.evaluate(analysis)
        )
