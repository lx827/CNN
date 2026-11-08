"""连续相位积分、等角重采样与有明确刻度的阶次 FFT。"""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.fft import rfft
from scipy.integrate import cumulative_trapezoid
from scipy.signal import windows

from .types import (
    AngleDomainSignal,
    OrderSpectrum,
    PhaseTrajectory,
    ScalarSpeed,
    SpeedTrajectory,
)


FloatArray = NDArray[np.float64]


def _validate_signal(signal: FloatArray, sample_rate_hz: float) -> FloatArray:
    arr = np.asarray(signal, dtype=np.float64)
    if arr.ndim != 1 or len(arr) < 16:
        raise ValueError("阶次跟踪输入必须是一维且至少包含 16 个采样点")
    if not np.all(np.isfinite(arr)):
        raise ValueError("阶次跟踪输入不能包含 NaN 或无穷值")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("采样率必须是有限正数")
    return arr


def integrate_speed_trajectory(speed: SpeedTrajectory) -> PhaseTrajectory:
    """用梯形积分计算 θ(t)/(2π)=∫fr(t)dt，不采用后向欧拉累加。"""
    revolutions = cumulative_trapezoid(speed.frequency_hz, speed.time_s, initial=0.0)
    return PhaseTrajectory(time_s=speed.time_s, revolutions=np.asarray(revolutions, dtype=np.float64))


def resample_constant_speed(
    signal: FloatArray,
    sample_rate_hz: float,
    speed: ScalarSpeed,
    samples_per_revolution: int = 1024,
) -> tuple[AngleDomainSignal, PhaseTrajectory]:
    """已知准确标量转频时，无需 tach 即可按 t=θ/(2πfr) 等角采样。"""
    arr = _validate_signal(signal, sample_rate_hz)
    if speed.status != "valid" or speed.frequency_hz is None:
        raise ValueError("恒速等角重采样需要有效标量转频")
    if isinstance(samples_per_revolution, bool) or not isinstance(samples_per_revolution, int):
        raise ValueError("每转采样点数必须是整数")
    if samples_per_revolution < 16:
        raise ValueError("每转采样点数至少为 16")
    times = np.arange(len(arr), dtype=np.float64) / sample_rate_hz
    revolutions = times * speed.frequency_hz
    phase = PhaseTrajectory(time_s=times, revolutions=revolutions)
    return resample_to_phase(arr, phase, samples_per_revolution), phase


def resample_to_phase(
    signal: FloatArray,
    phase: PhaseTrajectory,
    samples_per_revolution: int = 1024,
) -> AngleDomainSignal:
    """在等累计转数位置插值；采样点轴单位为 rev，独立于后续 FFT 阶次轴。"""
    arr = np.asarray(signal, dtype=np.float64)
    if arr.ndim != 1 or len(arr) != len(phase.time_s):
        raise ValueError("重采样信号必须与连续相位时间轴等长")
    if not np.all(np.isfinite(arr)):
        raise ValueError("重采样信号不能包含 NaN 或无穷值")
    if isinstance(samples_per_revolution, bool) or not isinstance(samples_per_revolution, int):
        raise ValueError("每转采样点数必须是整数")
    if samples_per_revolution < 16:
        raise ValueError("每转采样点数至少为 16")
    point_count = int(np.floor(phase.revolutions[-1] * samples_per_revolution))
    if point_count < 16:
        raise ValueError("有效转数太少，无法进行等角重采样")
    target_revolutions = np.arange(point_count, dtype=np.float64) / samples_per_revolution
    samples = np.interp(target_revolutions, phase.revolutions, arr)
    return AngleDomainSignal(
        angle_revolutions=target_revolutions,
        samples=samples,
        samples_per_revolution=samples_per_revolution,
    )


def compute_order_spectrum(
    angle_domain: AngleDomainSignal,
    max_order: float = 50.0,
) -> OrderSpectrum:
    """周期 Hann + 相干增益补偿，返回输入单位下的单边峰值幅值。

    对整数周期正弦 A·sin(2πkθ)，第 k 阶非 DC/Nyquist bin 的幅值为 A；
    DC 与 Nyquist 不做双倍。该刻度不是功率谱或窗能量归一化。
    """
    if not np.isfinite(max_order) or max_order <= 0:
        raise ValueError("最大阶次必须是有限正数")
    if max_order >= angle_domain.samples_per_revolution / 2:
        raise ValueError("最大阶次必须低于角域奈奎斯特阶次")
    centered = angle_domain.samples - np.mean(angle_domain.samples)
    count = len(centered)
    window = windows.hann(count, sym=False)
    coherent_gain = float(np.sum(window))
    if coherent_gain <= 0:
        raise ValueError("角域信号过短，无法形成有效窗")
    amplitude = np.abs(rfft(centered * window)) * (2.0 / coherent_gain)
    amplitude[0] *= 0.5
    if count % 2 == 0:
        amplitude[-1] *= 0.5
    order_resolution = angle_domain.samples_per_revolution / count
    order_bins = np.arange(len(amplitude), dtype=np.float64) * order_resolution
    retained = order_bins <= max_order + order_resolution * 1e-9
    return OrderSpectrum(
        order_bins=order_bins[retained],
        amplitude=amplitude[retained],
        order_resolution=float(order_resolution),
        samples_per_revolution=angle_domain.samples_per_revolution,
        total_revolutions=count / angle_domain.samples_per_revolution,
    )


def order_band_amplitude_sum(
    order_bins: FloatArray,
    amplitude: FloatArray,
    center_order: float,
    half_width_order: float,
) -> float:
    """返回阶次窗内单边幅值之和；供仍需带和的行星旧读模型复用。

    该函数不声明能量比，也不执行峰值检测。定轴 SER 使用独立的不重叠
    局部峰幅值比，不与行星 carrier 间隔共用高层逻辑。
    """
    orders = np.asarray(order_bins, dtype=np.float64)
    values = np.asarray(amplitude, dtype=np.float64)
    if orders.ndim != 1 or values.ndim != 1 or len(orders) != len(values) or len(orders) == 0:
        raise ValueError("阶次轴与幅值必须是非空一维等长数组")
    if not np.all(np.isfinite(orders)) or not np.all(np.isfinite(values)) or np.any(values < 0):
        raise ValueError("阶次轴与幅值必须有限，幅值不能为负")
    if not np.isfinite(center_order) or not np.isfinite(half_width_order) or half_width_order < 0:
        raise ValueError("阶次窗中心必须有限，半带宽必须有限且非负")
    mask = np.abs(orders - center_order) <= half_width_order
    return float(np.sum(values[mask])) if np.any(mask) else 0.0
