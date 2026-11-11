"""转速、相位与阶次分析的结构化数据契约。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

import numpy as np
from numpy.typing import NDArray


FloatArray = NDArray[np.float64]


def _validate_finite_vector(name: str, values: FloatArray) -> None:
    if values.ndim != 1 or len(values) == 0:
        raise ValueError(f"{name} 必须是非空一维数组")
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{name} 不能包含 NaN 或无穷值")


@dataclass(frozen=True)
class SpeedSearchRange:
    """转频搜索范围，单位 Hz。"""

    low_hz: float = 10.0
    high_hz: float = 100.0

    def __post_init__(self) -> None:
        if not np.isfinite(self.low_hz) or not np.isfinite(self.high_hz):
            raise ValueError("转频搜索范围必须是有限数")
        if self.low_hz <= 0 or self.high_hz <= self.low_hz:
            raise ValueError("转频搜索范围必须满足 0 < low_hz < high_hz")


@dataclass(frozen=True)
class ScalarSpeed:
    """单个时间区间唯一的标量转频，不表示转速轨迹。"""

    frequency_hz: Optional[float]
    source: str
    status: str = "valid"
    reason: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status not in {"valid", "indeterminate"}:
            raise ValueError("标量转频状态必须是 valid 或 indeterminate")
        if self.status == "valid":
            if (
                self.frequency_hz is None
                or not np.isfinite(self.frequency_hz)
                or self.frequency_hz <= 0
            ):
                raise ValueError("有效标量转频必须是有限正数")
        elif self.frequency_hz is not None:
            raise ValueError("不可判定的标量转频不能携带频率值")

    @classmethod
    def indeterminate(cls, source: str, reason: str) -> "ScalarSpeed":
        return cls(
            frequency_hz=None, source=source, status="indeterminate", reason=reason
        )


@dataclass(frozen=True)
class LocalSpeedEstimates:
    """各时间帧的局部标量转频；不是连续相位或连续转速轨迹。"""

    frame_start_s: FloatArray
    frame_time_s: FloatArray
    frequency_hz: FloatArray
    reliable_mask: NDArray[np.bool_]
    retained_mask: NDArray[np.bool_]
    source: str = "frame_spectrum"

    def __post_init__(self) -> None:
        lengths = {
            len(self.frame_start_s),
            len(self.frame_time_s),
            len(self.frequency_hz),
            len(self.reliable_mask),
            len(self.retained_mask),
        }
        if len(lengths) != 1 or not lengths or next(iter(lengths)) == 0:
            raise ValueError("局部转频序列各字段必须是非空等长数组")
        for name, values in (
            ("帧起点", self.frame_start_s),
            ("帧中心时间", self.frame_time_s),
        ):
            _validate_finite_vector(name, values)
        if self.frequency_hz.ndim != 1:
            raise ValueError("局部转频必须是一维数组")
        reliable = self.reliable_mask
        if not np.all(np.isfinite(self.frequency_hz[reliable])) or np.any(
            self.frequency_hz[reliable] <= 0
        ):
            raise ValueError("可靠局部转频必须是有限正数；不可靠帧可用 NaN 占位")
        if np.any(
            ~reliable & np.isfinite(self.frequency_hz) & (self.frequency_hz <= 0)
        ):
            raise ValueError("局部转频占位值不能是非正有限数")
        if np.any(self.retained_mask & ~self.reliable_mask):
            raise ValueError("保留帧必须是可靠帧的子集")

    @property
    def retained_frequencies_hz(self) -> FloatArray:
        return self.frequency_hz[self.retained_mask]

    @property
    def median_hz(self) -> float:
        retained = self.retained_frequencies_hz
        if len(retained) == 0:
            raise ValueError("没有可用于汇总的局部转频")
        return float(np.median(retained))

    @property
    def std_hz(self) -> float:
        retained = self.retained_frequencies_hz
        if len(retained) == 0:
            raise ValueError("没有可用于汇总的局部转频")
        return float(np.std(retained))


@dataclass(frozen=True)
class SpeedTrajectory:
    """连续时间轴上的转速轨迹，单位 Hz。"""

    time_s: FloatArray
    frequency_hz: FloatArray
    source: str
    stft_window_samples: Optional[int] = None
    stft_hop_samples: Optional[int] = None
    stft_frequency_resolution_hz: Optional[float] = None

    def __post_init__(self) -> None:
        _validate_finite_vector("转速时间轴", self.time_s)
        _validate_finite_vector("连续转速轨迹", self.frequency_hz)
        if len(self.time_s) != len(self.frequency_hz):
            raise ValueError("转速时间轴与轨迹长度必须一致")
        if len(self.time_s) > 1 and np.any(np.diff(self.time_s) <= 0):
            raise ValueError("转速时间轴必须严格递增")
        if np.any(self.frequency_hz <= 0):
            raise ValueError("连续转速轨迹必须严格为正")


@dataclass(frozen=True)
class PhaseTrajectory:
    """连续相位轨迹；revolutions 是从零开始的累计转数。"""

    time_s: FloatArray
    revolutions: FloatArray

    def __post_init__(self) -> None:
        _validate_finite_vector("相位时间轴", self.time_s)
        _validate_finite_vector("累计转数", self.revolutions)
        if len(self.time_s) != len(self.revolutions):
            raise ValueError("相位时间轴与累计转数长度必须一致")
        if self.revolutions[0] != 0:
            raise ValueError("累计转数必须从零开始")
        if len(self.time_s) > 1 and (
            np.any(np.diff(self.time_s) <= 0) or np.any(np.diff(self.revolutions) <= 0)
        ):
            raise ValueError("时间轴与连续相位必须严格递增")

    @property
    def phase_rad(self) -> FloatArray:
        """按需生成弧度相位，构造对象时不复制第二份数组。"""
        return 2.0 * np.pi * self.revolutions


@dataclass(frozen=True)
class AngleDomainSignal:
    """等角采样信号及其采样点位置轴；该轴不是 FFT bin 阶次轴。"""

    angle_revolutions: FloatArray
    samples: FloatArray
    samples_per_revolution: int

    def __post_init__(self) -> None:
        _validate_finite_vector("角域采样点轴", self.angle_revolutions)
        _validate_finite_vector("角域信号", self.samples)
        if len(self.angle_revolutions) != len(self.samples):
            raise ValueError("角域采样点轴与信号长度必须一致")
        if (
            isinstance(self.samples_per_revolution, bool)
            or self.samples_per_revolution < 8
        ):
            raise ValueError("每转采样点数必须是不小于 8 的整数")
        if len(self.angle_revolutions) > 1 and not np.allclose(
            np.diff(self.angle_revolutions),
            1.0 / self.samples_per_revolution,
            rtol=1e-8,
            atol=1e-12,
        ):
            raise ValueError("角域采样点轴必须按 1/samples_per_revolution 等间隔")


@dataclass(frozen=True)
class OrderSpectrum:
    """单边峰值幅值阶次谱；order_bins 仅表示 FFT bin 的阶次。"""

    order_bins: FloatArray
    amplitude: FloatArray
    order_resolution: float
    samples_per_revolution: int
    total_revolutions: float
    amplitude_unit: str = "input_signal"
    scaling: str = "single_sided_amplitude"

    def __post_init__(self) -> None:
        _validate_finite_vector("FFT 阶次轴", self.order_bins)
        _validate_finite_vector("阶次谱幅值", self.amplitude)
        if len(self.order_bins) != len(self.amplitude):
            raise ValueError("FFT 阶次轴与幅值长度必须一致")
        if np.any(self.amplitude < 0):
            raise ValueError("阶次谱幅值不能为负数")
        if self.order_bins[0] != 0 or (
            len(self.order_bins) > 1
            and not np.allclose(
                np.diff(self.order_bins), self.order_resolution, rtol=1e-7, atol=1e-12
            )
        ):
            raise ValueError("FFT 阶次轴必须从零开始并按 order_resolution 等间隔")


@dataclass(frozen=True)
class OrderParameters:
    samples_per_revolution: int = 1024
    max_order: float = 50.0

    def __post_init__(self) -> None:
        if isinstance(self.samples_per_revolution, bool) or not isinstance(
            self.samples_per_revolution, int
        ):
            raise ValueError("每转采样点数必须是整数")
        if self.samples_per_revolution < 16:
            raise ValueError("每转采样点数至少为 16")
        if not np.isfinite(self.max_order) or self.max_order <= 0:
            raise ValueError("最大阶次必须是有限正数")
        if self.max_order >= self.samples_per_revolution / 2:
            raise ValueError("最大阶次必须低于角域奈奎斯特阶次")


@dataclass(frozen=True)
class FrameParameters:
    frame_duration_s: float = 1.0
    overlap: float = 0.5
    mad_threshold: float = 3.0
    relative_mad_floor: float = 0.01
    absolute_mad_floor_hz: float = 0.05
    varying_speed_cv_threshold: float = 0.10

    def __post_init__(self) -> None:
        if not np.isfinite(self.frame_duration_s) or self.frame_duration_s <= 0:
            raise ValueError("帧长必须是有限正数")
        if not np.isfinite(self.overlap) or not 0 <= self.overlap < 1:
            raise ValueError("帧重叠率必须位于 [0, 1)")
        if (
            self.mad_threshold <= 0
            or self.relative_mad_floor < 0
            or self.absolute_mad_floor_hz <= 0
        ):
            raise ValueError("MAD 阈值和绝对下限必须为正数，相对下限不能为负数")
        if self.varying_speed_cv_threshold <= 0:
            raise ValueError("快速变速判据必须为正数")


@dataclass(frozen=True)
class RidgeParameters:
    """STFT 脊线参数；实际窗长同时受采样率和最长窗时长约束。"""

    target_frequency_resolution_hz: float = 0.5
    maximum_window_duration_s: float = 0.5
    overlap: float = 0.75
    minimum_peak_to_background: float = 8.0
    minimum_local_energy_fraction: float = 0.12
    minimum_reliable_frame_fraction: float = 0.60
    maximum_consecutive_boundary_frames: int = 2
    maximum_boundary_frame_fraction: float = 0.20

    def __post_init__(self) -> None:
        if (
            self.target_frequency_resolution_hz <= 0
            or self.maximum_window_duration_s <= 0
        ):
            raise ValueError("STFT 目标分辨率和最长窗时长必须为正数")
        if not 0 <= self.overlap < 1:
            raise ValueError("STFT 重叠率必须位于 [0, 1)")
        if (
            self.minimum_peak_to_background <= 1
            or self.minimum_local_energy_fraction <= 0
        ):
            raise ValueError("STFT 脊线可靠性阈值无效")
        if not 0 < self.minimum_reliable_frame_fraction <= 1:
            raise ValueError("可靠脊线帧比例必须位于 (0, 1]")
        if self.maximum_consecutive_boundary_frames < 0:
            raise ValueError("允许的连续边界帧数不能为负数")
        if not 0 <= self.maximum_boundary_frame_fraction < 1:
            raise ValueError("边界帧比例上限必须位于 [0, 1)")


@dataclass(frozen=True)
class TachometerPulses:
    """未来 tach 输入的独立类型；当前 Pipeline 不声明已实现 tach 跟踪。"""

    pulse_times_s: FloatArray
    pulses_per_revolution: int

    def __post_init__(self) -> None:
        _validate_finite_vector("tach 脉冲时间", self.pulse_times_s)
        if self.pulses_per_revolution <= 0:
            raise ValueError("每转脉冲数必须为正整数")


SpeedRepresentation = Union[ScalarSpeed, LocalSpeedEstimates, SpeedTrajectory]


@dataclass(frozen=True)
class OrderAnalysis:
    """完整阶次分析结果；缓变结果的 phase/angle_domain 明确为空。"""

    status: str
    tracking_method: str
    speed: SpeedRepresentation
    spectrum: Optional[OrderSpectrum]
    phase: Optional[PhaseTrajectory] = None
    angle_domain: Optional[AngleDomainSignal] = None
    reason: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status not in {"valid", "indeterminate"}:
            raise ValueError("阶次分析状态必须是 valid 或 indeterminate")
        if self.status == "valid" and self.spectrum is None:
            raise ValueError("有效阶次分析必须包含阶次谱")
        if self.status == "indeterminate" and self.spectrum is not None:
            raise ValueError("不可判定结果不能携带正常阶次谱")
        if self.tracking_method == "multi_frame" and (
            self.phase is not None or self.angle_domain is not None
        ):
            raise ValueError("多帧谱平均不能伪装成连续相位重采样")

    @classmethod
    def failed(
        cls,
        tracking_method: str,
        speed: SpeedRepresentation,
        reason: str,
    ) -> "OrderAnalysis":
        return cls(
            status="indeterminate",
            tracking_method=tracking_method,
            speed=speed,
            spectrum=None,
            reason=reason,
        )
