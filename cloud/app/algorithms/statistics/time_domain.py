"""时域统计、加窗统计序列与分段 RMS；不执行故障阈值评估。"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy import stats
from scipy.signal import windows


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
    absolute = np.abs(values)
    peak = float(np.max(absolute))
    rms = float(np.sqrt(np.mean(values**2)))
    mean_abs = float(np.mean(absolute))
    mean_sqrt = float(np.mean(np.sqrt(absolute + 1e-12)))
    return SignalStatistics(
        peak=peak,
        rms=rms,
        kurtosis=float(stats.kurtosis(values, fisher=False)),
        skewness=float(stats.skew(values)),
        margin=peak / (mean_sqrt**2) if mean_sqrt > 1e-12 else 0.0,
        shape_factor=rms / mean_abs if mean_abs > 1e-12 else 0.0,
        impulse_factor=peak / mean_abs if mean_abs > 1e-12 else 0.0,
        crest_factor=peak / rms if rms > 1e-12 else 0.0,
    )


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
    if not np.all(np.isfinite(values)):
        raise ValueError("输入信号不能包含 NaN 或无穷值")
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

    overall = _statistics(values)
    actual_window = min(window_size, len(values))
    actual_step = step if step is not None else actual_window // 2
    actual_step = max(1, min(actual_step, actual_window))
    window = windows.hann(actual_window, sym=False)
    series = []
    for start in range(0, len(values) - actual_window + 1, actual_step):
        segment = values[start : start + actual_window] * window
        series.append((start / sample_rate_hz, _statistics(segment)))

    def column(attribute: str | None) -> FloatArray:
        return np.asarray(
            [
                item[0] if attribute is None else getattr(item[1], attribute)
                for item in series
            ],
            dtype=np.float64,
        )

    windowed = WindowedStatistics(
        time_s=column(None),
        kurtosis=column("kurtosis"),
        skewness=column("skewness"),
        rms=column("rms"),
        peak=column("peak"),
        margin=column("margin"),
        crest_factor=column("crest_factor"),
        shape_factor=column("shape_factor"),
        impulse_factor=column("impulse_factor"),
    )
    return TimeDomainAnalysis(
        overall=overall,
        windowed=windowed,
        window_size=actual_window,
        step=actual_step,
    )


def centered_rms(signal: FloatArray) -> float:
    """去均值 RMS，单位与输入一致。"""
    values = np.asarray(signal, dtype=np.float64)
    if values.ndim != 1 or len(values) == 0 or not np.all(np.isfinite(values)):
        raise ValueError("RMS 输入必须是一维非空有限信号")
    centered = values - np.mean(values)
    return float(np.sqrt(np.mean(centered**2)))


def segmented_rms(
    signal: FloatArray,
    sample_rate_hz: float,
    *,
    segment_duration_s: float = 1.0,
    remove_mean: bool = True,
) -> SegmentedRMS:
    """按固定时长分段，末段保留实际长度；每段独立选择去均值。"""
    values = np.asarray(signal, dtype=np.float64)
    if values.ndim != 1 or len(values) == 0 or not np.all(np.isfinite(values)):
        raise ValueError("分段 RMS 输入必须是一维非空有限信号")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("采样率必须是有限正数")
    if not np.isfinite(segment_duration_s) or segment_duration_s <= 0:
        raise ValueError("分段时长必须是有限正数")
    segment_samples = max(1, int(round(segment_duration_s * sample_rate_hz)))
    centers = []
    rms_values = []
    for start in range(0, len(values), segment_samples):
        block = values[start : start + segment_samples]
        analyzed = block - np.mean(block) if remove_mean else block
        centers.append((start + len(block) / 2.0) / sample_rate_hz)
        rms_values.append(float(np.sqrt(np.mean(analyzed**2))))
    return SegmentedRMS(
        time_s=np.asarray(centers, dtype=np.float64),
        rms=np.asarray(rms_values, dtype=np.float64),
        remove_mean=remove_mean,
    )
