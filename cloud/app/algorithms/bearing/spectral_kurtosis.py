"""真实带通滤波器组谱峭度与工程重加权选带。

这里不是 Fast Kurtogram 的 1/3-二叉树实现，也不把单个 STFT bin 当时域窄带
信号。每个候选频带都实际执行 Butterworth 带通和 Hilbert 解析变换。
"""
from dataclasses import dataclass
from typing import Optional

import numpy as np
from numpy.typing import NDArray
from scipy.signal import butter, hilbert, sosfiltfilt

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


def _validated_signal(signal: NDArray[np.float64], sample_rate_hz: float) -> np.ndarray:
    arr = np.asarray(signal, dtype=np.float64)
    if arr.ndim != 1 or len(arr) < 256:
        raise ValueError("谱峭度滤波器组输入必须是一维且至少 256 点")
    if not np.all(np.isfinite(arr)):
        raise ValueError("输入信号不能包含 NaN 或无穷值")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("采样率必须为有限正数")
    return arr - np.mean(arr)


def complex_spectral_kurtosis(values: NDArray[np.complex128]) -> float:
    """K=E|z|^4/(E|z|^2)^2-2；圆对称复高斯背景的理论基准为 0。"""
    z = np.asarray(values, dtype=np.complex128)
    if z.ndim != 1 or len(z) < 2:
        raise ValueError("谱峭度输入必须是一维且至少两个复样本")
    if not np.all(np.isfinite(z)):
        raise ValueError("谱峭度输入不能包含 NaN 或无穷值")
    scale = float(np.max(np.abs(z)))
    if scale == 0.0:
        raise ValueError("零能量频带无法估计谱峭度")
    power = np.abs(z / scale) ** 2
    mean_power = float(np.mean(power))
    if mean_power == 0.0 or not np.isfinite(mean_power):
        raise ValueError("频带数值退化，无法估计谱峭度")
    return float(np.mean(power**2) / mean_power**2 - 2.0)


def _validate_parameters(parameters: FilterBankKurtogramParameters) -> None:
    if isinstance(parameters.max_level, bool) or not isinstance(parameters.max_level, int):
        raise ValueError("滤波器组层数必须是整数")
    if not 1 <= parameters.max_level <= 6:
        raise ValueError("滤波器组层数必须位于 1~6")
    if isinstance(parameters.filter_order, bool) or not isinstance(parameters.filter_order, int):
        raise ValueError("滤波器阶数必须是整数")
    if parameters.filter_order <= 0:
        raise ValueError("滤波器阶数必须为正整数")
    if not np.isfinite(parameters.min_frequency_hz) or parameters.min_frequency_hz <= 0:
        raise ValueError("最低搜索频率必须为有限正数")
    if not np.isfinite(parameters.selection_threshold):
        raise ValueError("选带阈值必须为有限数")
    if not np.isfinite(parameters.envelope_low_pass_hz) or parameters.envelope_low_pass_hz <= 0:
        raise ValueError("包络低通截止频率必须为有限正数")


def _band_statistics(z: np.ndarray, level: int, band: FrequencyBand) -> BandKurtosis:
    # 零相位滤波的边缘暂态不参与统计，避免把滤波器边缘误当冲击。
    edge = max(8, len(z) // 20)
    core = z[edge:-edge] if len(z) > 2 * edge + 16 else z
    sk = complex_spectral_kurtosis(core)
    magnitude = np.abs(core)
    peak = float(np.max(magnitude))
    # 工程幅值比只使用随当前频带尺度变化的下限，避免零中位数除法。
    median = max(float(np.median(magnitude)), peak * np.finfo(np.float64).eps)
    impulsiveness = peak / median
    signal_to_background = float(np.percentile(magnitude, 95.0)) / median
    # 明确是工程重加权分数，不把 Pearson 峭度减 3 冒充谱峭度。
    score = max(0.0, sk) * float(np.log1p(impulsiveness) * np.log1p(signal_to_background))
    return BandKurtosis(
        band=band,
        level=level,
        spectral_kurtosis=sk,
        impulsiveness=impulsiveness,
        signal_to_background=signal_to_background,
        reweighted_score=score,
    )


def compute_filter_bank_kurtogram(
    signal: NDArray[np.float64],
    sample_rate_hz: float,
    parameters: Optional[FilterBankKurtogramParameters] = None,
) -> tuple[BandKurtosis, ...]:
    """对每层每个实际带通后的解析信号估计复谱峭度。"""
    params = parameters or FilterBankKurtogramParameters()
    _validate_parameters(params)
    arr = _validated_signal(signal, sample_rate_hz)
    nyquist = sample_rate_hz / 2.0
    if params.min_frequency_hz >= nyquist:
        raise ValueError("最低搜索频率必须低于 Nyquist")

    candidates = []
    for level in range(1, params.max_level + 1):
        width = nyquist / (2**level)
        for index in range(2**level):
            low = max(index * width, params.min_frequency_hz)
            high = min((index + 1) * width, nyquist * (1.0 - 1e-8))
            if high - low < max(2.0, width * 0.05):
                continue
            band = FrequencyBand(float(low), float(high))
            sos = butter(
                params.filter_order,
                [band.low_hz, band.high_hz],
                btype="bandpass",
                fs=sample_rate_hz,
                output="sos",
            )
            filtered = sosfiltfilt(sos, arr)
            if not np.any(filtered):
                continue
            candidates.append(_band_statistics(hilbert(filtered), level, band))
    if not candidates:
        raise ValueError("没有足够采样点或有效频带可估计谱峭度")
    return tuple(candidates)


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
