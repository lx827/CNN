"""旧诊断调用方的阶次兼容边界；数学实现唯一位于 app.algorithms.order。

本模块只把结构化结果转换为旧 tuple，不包含 FFT、重采样或转频估计。
新代码应直接使用结构化 Pipeline，不能依赖这里的 tuple 推断相位类型。
"""

from typing import Tuple

import numpy as np

from app.algorithms.order import (
    ConstantSpeedOrderPipeline,
    FastVaryingSpeedOrderPipeline,
    FrameParameters,
    LocalSpeedEstimates,
    OrderParameters,
    RidgeParameters,
    ScalarSpeed,
    SlowVaryingSpeedOrderPipeline,
    SpeedSearchRange,
    SpeedTrajectory,
)


def _require_spectrum(result):
    if result.status != "valid" or result.spectrum is None:
        raise ValueError(result.reason or "阶次分析不可判定")
    return result.spectrum


def _order_tracking(
    sig: np.ndarray,
    fs: float,
    rot_freq: float,
    samples_per_rev: int = 1024,
) -> Tuple[np.ndarray, np.ndarray]:
    """返回角域信号和角域采样点轴(rev)；第二轴不再是 FFT 阶次轴。"""
    result = ConstantSpeedOrderPipeline(
        OrderParameters(
            samples_per_revolution=samples_per_rev, max_order=samples_per_rev / 2 - 1
        )
    ).run(sig, fs, ScalarSpeed(float(rot_freq), "caller_supplied"))
    if result.status != "valid" or result.angle_domain is None:
        raise ValueError(result.reason or "恒速重采样不可判定")
    return result.angle_domain.samples, result.angle_domain.angle_revolutions


def _compute_order_spectrum(
    sig: np.ndarray,
    fs: float,
    rot_freq: float,
    samples_per_rev: int = 1024,
    max_order: float = 50,
) -> Tuple[np.ndarray, np.ndarray]:
    result = ConstantSpeedOrderPipeline(
        OrderParameters(samples_per_revolution=samples_per_rev, max_order=max_order)
    ).run(sig, fs, ScalarSpeed(float(rot_freq), "caller_supplied"))
    spectrum = _require_spectrum(result)
    return spectrum.order_bins, spectrum.amplitude


def _compute_order_spectrum_multi_frame(
    sig: np.ndarray,
    fs: float,
    freq_range: Tuple[float, float] = (10, 100),
    samples_per_rev: int = 1024,
    max_order: int = 50,
    frame_duration: float = 1.0,
    overlap: float = 0.5,
) -> Tuple[np.ndarray, np.ndarray, float, float]:
    result = SlowVaryingSpeedOrderPipeline(
        OrderParameters(samples_per_revolution=samples_per_rev, max_order=max_order),
        FrameParameters(frame_duration_s=frame_duration, overlap=overlap),
        SpeedSearchRange(*freq_range),
    ).run(sig, fs)
    spectrum = _require_spectrum(result)
    if not isinstance(result.speed, LocalSpeedEstimates):
        raise TypeError("多帧结果缺少局部转频序列")
    return (
        spectrum.order_bins,
        spectrum.amplitude,
        result.speed.median_hz,
        result.speed.std_hz,
    )


def _compute_order_spectrum_varying_speed(
    sig: np.ndarray,
    fs: float,
    freq_range: Tuple[float, float] = (10, 100),
    samples_per_rev: int = 1024,
    max_order: int = 50,
    nperseg: int | None = None,
    noverlap: int | None = None,
) -> Tuple[np.ndarray, np.ndarray, float, float]:
    if nperseg is None:
        ridge = RidgeParameters()
    else:
        if nperseg < 64 or noverlap is None or not 0 <= noverlap < nperseg:
            raise ValueError("显式 STFT 窗长/重叠参数无效")
        ridge = RidgeParameters(
            target_frequency_resolution_hz=fs / nperseg,
            maximum_window_duration_s=nperseg / fs,
            overlap=noverlap / nperseg,
        )
    result = FastVaryingSpeedOrderPipeline(
        OrderParameters(samples_per_revolution=samples_per_rev, max_order=max_order),
        SpeedSearchRange(*freq_range),
        ridge,
    ).run(sig, fs)
    spectrum = _require_spectrum(result)
    if not isinstance(result.speed, SpeedTrajectory):
        raise TypeError("快速变速结果缺少连续转速轨迹")
    return (
        spectrum.order_bins,
        spectrum.amplitude,
        float(np.median(result.speed.frequency_hz)),
        float(np.std(result.speed.frequency_hz)),
    )
