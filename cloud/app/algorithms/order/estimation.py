"""转频估计：标量候选与 STFT 连续转速轨迹分开建模。"""

from __future__ import annotations

from cnn_compute import rotation as native

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
from numpy.typing import NDArray

from .types import RidgeParameters, ScalarSpeed, SpeedSearchRange, SpeedTrajectory


FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class SpeedTrajectoryEstimate:
    status: str
    trajectory: Optional[SpeedTrajectory]
    reliable_frame_count: int
    total_frame_count: int
    reason: Optional[str] = None

    @classmethod
    def failed(
        cls, reason: str, reliable: int = 0, total: int = 0
    ) -> "SpeedTrajectoryEstimate":
        return cls("indeterminate", None, reliable, total, reason)






def _validate_sample_rate(fs: float) -> None:
    if not np.isfinite(fs) or fs <= 0:
        raise ValueError("采样率必须是有限正数")








def estimate_envelope_speed(
    signal: FloatArray,
    sample_rate_hz: float,
    carrier_frequency_hz: float,
    search: SpeedSearchRange = SpeedSearchRange(),
    bandwidth_hz: float = 60.0,
) -> ScalarSpeed:
    """对指定载波频带做 Hilbert 包络，返回独立的标量候选。"""
    _validate_sample_rate(sample_rate_hz)
    values = np.asarray(signal, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError("转频估计输入必须是一维信号")
    frequency, source, reason = native.envelope_speed(values, sample_rate_hz, carrier_frequency_hz,
        search.low_hz, search.high_hz, bandwidth_hz)
    return ScalarSpeed.indeterminate(source, reason) if reason else ScalarSpeed(frequency, source)


def estimate_autocorrelation_speed(
    signal: FloatArray,
    sample_rate_hz: float,
    search: SpeedSearchRange = SpeedSearchRange(),
) -> ScalarSpeed:
    """用归一化自相关的显著滞后峰产生标量转频候选。"""
    _validate_sample_rate(sample_rate_hz)
    values = np.asarray(signal, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError("转频估计输入必须是一维信号")
    frequency, source, reason = native.autocorrelation_speed(values, sample_rate_hz, search.low_hz, search.high_hz)
    return ScalarSpeed.indeterminate(source, reason) if reason else ScalarSpeed(frequency, source)


def estimate_spectrum_speed(
    signal: FloatArray,
    sample_rate_hz: float,
    search: SpeedSearchRange = SpeedSearchRange(),
    harmonics_num: int = 5,
    bandwidth_hz: float = 3.0,
    smooth_win_hz: float = 1.5,
) -> ScalarSpeed:
    """频谱谐波、包络、Welch 与自相关候选的标量仲裁，不执行故障增强。"""
    _validate_sample_rate(sample_rate_hz)
    values = np.asarray(signal, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError("转频估计输入必须是一维信号")
    frequency, source, reason = native.spectrum_speed(values, sample_rate_hz, search.low_hz, search.high_hz,
        harmonics_num, bandwidth_hz, smooth_win_hz)
    return ScalarSpeed.indeterminate(source, reason) if reason else ScalarSpeed(frequency, source)


def resolve_stft_window_samples(
    signal_length: int,
    sample_rate_hz: float,
    parameters: RidgeParameters = RidgeParameters(),
) -> Tuple[int, int]:
    """按 fs/目标分辨率选择窗长，并限制最长窗时长；返回窗长和 hop。"""
    _validate_sample_rate(sample_rate_hz)
    if signal_length < 64:
        raise ValueError("STFT 转速估计至少需要 64 个采样点")
    target_samples = int(
        2
        ** np.ceil(np.log2(sample_rate_hz / parameters.target_frequency_resolution_hz))
    )
    maximum_samples = max(
        64, int(sample_rate_hz * parameters.maximum_window_duration_s)
    )
    nperseg = min(target_samples, maximum_samples, signal_length)
    if nperseg < 64:
        raise ValueError("有效 STFT 窗长不足 64 点")
    hop = max(1, int(round(nperseg * (1.0 - parameters.overlap))))
    return nperseg, hop


def _longest_true_run(mask: NDArray[np.bool_]) -> int:
    best = current = 0
    for value in mask:
        current = current + 1 if value else 0
        best = max(best, current)
    return best


def _speed_range_violation(
    frequency_hz: FloatArray,
    time_s: FloatArray,
    stft_times_s: FloatArray,
    search: SpeedSearchRange,
    maximum_edge_outside_samples: int,
) -> Optional[str]:
    """检查逐采样点越界；边缘阈值与输入统一使用采样点计数。"""
    outside = (frequency_hz < search.low_hz) | (frequency_hz > search.high_hz)
    if not np.any(outside):
        return None
    edge_extrapolation = (time_s < stft_times_s[0]) | (time_s > stft_times_s[-1])
    if np.any(outside & ~edge_extrapolation):
        return "连续转速轨迹在 STFT 记录内部越出搜索范围"
    if maximum_edge_outside_samples < 1:
        raise ValueError("边缘越界采样点上限必须为正整数")
    if _longest_true_run(outside) > maximum_edge_outside_samples:
        return "连续转速轨迹在边缘长时间越出搜索范围"
    return None


def estimate_stft_speed_trajectory(
    signal: FloatArray,
    sample_rate_hz: float,
    search: SpeedSearchRange = SpeedSearchRange(),
    parameters: RidgeParameters = RidgeParameters(),
) -> SpeedTrajectoryEstimate:
    """追踪 STFT 基频脊线；低信噪比或可靠帧不足时明确不可判定。"""
    _validate_sample_rate(sample_rate_hz)
    values = np.asarray(signal, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError("转频估计输入必须是一维信号")
    if search.high_hz >= sample_rate_hz / 2:
        return SpeedTrajectoryEstimate.failed("转频搜索上限必须低于奈奎斯特频率")
    try:
        nperseg, hop = resolve_stft_window_samples(len(values), sample_rate_hz, parameters)
    except ValueError as exc:
        return SpeedTrajectoryEstimate.failed(str(exc))
    frequency, reliable, total, reason = native.speed_ridge(values, sample_rate_hz,
        search.low_hz, search.high_hz, nperseg, hop, parameters)
    if reason:
        return SpeedTrajectoryEstimate.failed(reason, reliable, total)
    trajectory = SpeedTrajectory(time_s=np.arange(len(values), dtype=np.float64) / sample_rate_hz,
        frequency_hz=frequency, source="stft_ridge", stft_window_samples=nperseg,
        stft_hop_samples=hop, stft_frequency_resolution_hz=float(sample_rate_hz / nperseg))
    return SpeedTrajectoryEstimate("valid", trajectory, reliable, total)
