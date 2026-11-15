"""时域统计、加窗统计序列与分段 RMS；不执行故障阈值评估。"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from cnn_compute import numeric

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class SignalStatistics:
    peak: float
    rms: float
    kurtosis: float
    skewness: float
    margin: float
    shape_factor: float
    impulse_factor: float
    crest_factor: float


@dataclass(frozen=True)
class WindowedStatistics:
    """每条序列等长；time_s 是窗口起点而非中心。"""

    time_s: FloatArray
    kurtosis: FloatArray
    skewness: FloatArray
    rms: FloatArray
    peak: FloatArray
    margin: FloatArray
    crest_factor: FloatArray
    shape_factor: FloatArray
    impulse_factor: FloatArray

    @property
    def mean_kurtosis(self) -> float:
        return float(np.mean(self.kurtosis)) if len(self.kurtosis) else 0.0


@dataclass(frozen=True)
class TimeDomainAnalysis:
    overall: SignalStatistics
    windowed: WindowedStatistics
    window_size: int
    step: int


@dataclass(frozen=True)
class SegmentedRMS:
    """time_s 为每段中心时间，rms 与输入信号单位一致。"""

    time_s: FloatArray
    rms: FloatArray
    remove_mean: bool = True


def _statistics(values: FloatArray) -> SignalStatistics:
    return SignalStatistics(*numeric.statistics(values))


def analyze_time_domain(
    signal: FloatArray,
    sample_rate_hz: float,
    *,
    window_size: int = 1024,
    step: int | None = None,
) -> TimeDomainAnalysis:
    """全长总体指标与周期 Hann 加窗序列分开计算，窗口序列不做绘图抽点。"""
    values = np.asarray(signal, dtype=np.float64)
    if values.ndim != 1 or len(values) == 0:
        raise ValueError("统计输入必须是一维非空信号")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("采样率必须是有限正数")
    if (
        isinstance(window_size, bool)
        or not isinstance(window_size, int)
        or window_size <= 0
    ):
        raise ValueError("统计窗口大小必须是正整数")
    if step is not None and (
        isinstance(step, bool) or not isinstance(step, int) or step <= 0
    ):
        raise ValueError("统计步长必须是正整数")

    overall, times, series, actual_window, actual_step = numeric.time_domain(
        values, sample_rate_hz, window_size, 0 if step is None else step
    )
    windowed = WindowedStatistics(
        time_s=times,
        kurtosis=series[:, 2],
        skewness=series[:, 3],
        rms=series[:, 1],
        peak=series[:, 0],
        margin=series[:, 4],
        crest_factor=series[:, 7],
        shape_factor=series[:, 5],
        impulse_factor=series[:, 6],
    )
    return TimeDomainAnalysis(
        overall=SignalStatistics(*overall),
        windowed=windowed,
        window_size=actual_window,
        step=actual_step,
    )


def centered_rms(signal: FloatArray) -> float:
    """去均值 RMS，单位与输入一致。"""
    values = np.asarray(signal, dtype=np.float64)
    if values.ndim != 1 or len(values) == 0:
        raise ValueError("RMS 输入必须是一维非空有限信号")
    return float(numeric.segmented_rms(values, 1.0, len(values), True)[0, 1])


def segmented_rms(
    signal: FloatArray,
    sample_rate_hz: float,
    *,
    segment_duration_s: float = 1.0,
    remove_mean: bool = True,
) -> SegmentedRMS:
    """按固定时长分段，末段保留实际长度；每段独立选择去均值。"""
    values = np.asarray(signal, dtype=np.float64)
    if values.ndim != 1 or len(values) == 0:
        raise ValueError("分段 RMS 输入必须是一维非空有限信号")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("采样率必须是有限正数")
    if not np.isfinite(segment_duration_s) or segment_duration_s <= 0:
        raise ValueError("分段时长必须是有限正数")
    segment_samples = max(1, int(round(segment_duration_s * sample_rate_hz)))
    result = numeric.segmented_rms(values, sample_rate_hz, segment_samples, remove_mean)
    return SegmentedRMS(
        time_s=result[:, 0],
        rms=result[:, 1],
        remove_mean=remove_mean,
    )
