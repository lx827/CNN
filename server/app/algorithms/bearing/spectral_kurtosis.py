"""真实带通滤波器组谱峭度与工程重加权选带。

这里不是 Fast Kurtogram 的 1/3-二叉树实现，也不把单个 STFT bin 当时域窄带
信号。每个候选频带都实际执行 Butterworth 带通和 Hilbert 解析变换。
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np
from cnn_compute import diagnostic as native_diagnostic
from numpy.typing import NDArray

from app.algorithms.bearing.envelope import (
    EnvelopeParameters,
    EnvelopeRepresentation,
    compute_envelope,
)
from app.algorithms.core import FrequencyBand


@dataclass(frozen=True)
class FilterBankKurtogramParameters:
    """均匀二叉频带网格；max_level=3 时搜索 2/4/8 个频带的各层。"""

    max_level: int = 4
    min_frequency_hz: float = 100.0
    filter_order: int = 4
    selection_threshold: float = 0.5
    envelope_low_pass_hz: float = 2000.0


@dataclass(frozen=True)
class BandKurtosis:
    band: FrequencyBand
    level: int
    spectral_kurtosis: float
    impulsiveness: float
    signal_to_background: float
    reweighted_score: float
    estimator: str = "complex_gaussian_sk_minus_2"


@dataclass(frozen=True)
class FilterBankKurtogramResult:
    status: str
    method: str
    bands: tuple[BandKurtosis, ...]
    best_band: Optional[FrequencyBand]
    representation: Optional[EnvelopeRepresentation]
    reason: Optional[str] = None

    @property
    def max_spectral_kurtosis(self) -> float:
        return max((item.spectral_kurtosis for item in self.bands), default=-1.0)


def complex_spectral_kurtosis(values):
    """原生K=E|z|⁴/(E|z|²)²-2；圆对称复高斯背景理论基准为0。"""
    return native_diagnostic.complex_spectral_kurtosis(values)


def _validate_parameters(parameters: FilterBankKurtogramParameters) -> None:
    if isinstance(parameters.max_level, bool) or not isinstance(
        parameters.max_level, int
    ):
        raise ValueError("滤波器组层数必须是整数")
    if not 1 <= parameters.max_level <= 6:
        raise ValueError("滤波器组层数必须位于 1~6")
    if isinstance(parameters.filter_order, bool) or not isinstance(
        parameters.filter_order, int
    ):
        raise ValueError("滤波器阶数必须是整数")
    if parameters.filter_order <= 0:
        raise ValueError("滤波器阶数必须为正整数")
    if not np.isfinite(parameters.min_frequency_hz) or parameters.min_frequency_hz <= 0:
        raise ValueError("最低搜索频率必须为有限正数")
    if not np.isfinite(parameters.selection_threshold):
        raise ValueError("选带阈值必须为有限数")
    if (
        not np.isfinite(parameters.envelope_low_pass_hz)
        or parameters.envelope_low_pass_hz <= 0
    ):
        raise ValueError("包络低通截止频率必须为有限正数")


def compute_filter_bank_kurtogram(
    signal, sample_rate_hz, parameters=None
) -> tuple[BandKurtosis, ...]:
    """原生实际IIR滤波器组+Hilbert+逐带统计；工程评分与阈值留在Python。"""
    params = parameters or FilterBankKurtogramParameters()
    _validate_parameters(params)
    rows = native_diagnostic.filter_bank_kurtogram(
        signal,
        sample_rate_hz,
        params.max_level,
        params.min_frequency_hz,
        params.filter_order,
    )
    return tuple(
        BandKurtosis(
            FrequencyBand(low, high),
            level,
            sk,
            impulsiveness,
            background,
            max(0.0, sk) * float(np.log1p(impulsiveness) * np.log1p(background)),
        )
        for low, high, level, sk, impulsiveness, background in rows
    )


class FilterBankKurtogramPipeline:
    """真实滤波器组 + 复高斯基谱峭度 + 标准包络；无显著频带时不回退。"""

    method = "Dyadic IIR Butterworth filter-bank spectral kurtosis + Envelope"

    def _select(self, bands: tuple[BandKurtosis, ...]) -> BandKurtosis:
        return max(bands, key=lambda item: item.spectral_kurtosis)

    def run(
        self,
        signal: NDArray[np.float64],
        sample_rate_hz: float,
        parameters: Optional[FilterBankKurtogramParameters] = None,
    ) -> FilterBankKurtogramResult:
        params = parameters or FilterBankKurtogramParameters()
        bands = compute_filter_bank_kurtogram(signal, sample_rate_hz, params)
        best = self._select(bands)
        if best.spectral_kurtosis <= params.selection_threshold:
            return FilterBankKurtogramResult(
                status="indeterminate",
                method=self.method,
                bands=bands,
                best_band=None,
                representation=None,
                reason="no_impulsive_band_above_threshold",
            )
        representation = compute_envelope(
            signal,
            sample_rate_hz,
            EnvelopeParameters(
                band_center_hz=best.band.center_hz,
                band_width_hz=best.band.width_hz,
                envelope_low_pass_hz=params.envelope_low_pass_hz,
                filter_order=params.filter_order,
            ),
        )
        return FilterBankKurtogramResult(
            status="computed",
            method=self.method,
            bands=bands,
            best_band=best.band,
            representation=representation,
        )


class ReweightedSpectralKurtosisPipeline(FilterBankKurtogramPipeline):
    """SK×log(1+冲击度)×log(1+局部幅值比) 的显式工程重加权版本。"""

    method = "Dyadic filter-bank reweighted complex spectral kurtosis + Envelope"

    def _select(self, bands: tuple[BandKurtosis, ...]) -> BandKurtosis:
        return max(bands, key=lambda item: item.reweighted_score)

    def run(self, signal, sample_rate_hz, parameters=None) -> FilterBankKurtogramResult:
        result = super().run(signal, sample_rate_hz, parameters)
        # 低冲击度频带的零分不能触发选带，即使其 SK 因有限样本略大于阈值。
        if result.best_band is not None:
            best = max(result.bands, key=lambda item: item.reweighted_score)
            if best.reweighted_score <= 0.0:
                return FilterBankKurtogramResult(
                    status="indeterminate",
                    method=self.method,
                    bands=result.bands,
                    best_band=None,
                    representation=None,
                    reason="no_impulsive_band_above_threshold",
                )
        return FilterBankKurtogramResult(
            status=result.status,
            method=self.method,
            bands=result.bands,
            best_band=result.best_band,
            representation=result.representation,
            reason=result.reason,
        )
