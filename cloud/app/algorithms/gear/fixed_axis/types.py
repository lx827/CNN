"""定轴齿轮计算表示、历史输入与原始指标的数据契约。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from numpy.typing import NDArray

from app.algorithms.core import Spectrum
from app.algorithms.order import AngleDomainSignal, OrderAnalysis, OrderSpectrum


FloatArray = NDArray[np.float64]


def _finite_vector(name: str, values: FloatArray) -> None:
    if values.ndim != 1 or len(values) == 0 or not np.all(np.isfinite(values)):
        raise ValueError(f"{name}必须是非空有限一维数组")


@dataclass(frozen=True)
class MetricValue:
    """原始标量指标；不可评估时值必须为 None，不能用 0 代替。"""

    name: str
    status: str
    value: Optional[float] = None
    unit: str = "dimensionless"
    reason: Optional[str] = None
    details: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in {"evaluated", "not_evaluable"}:
            raise ValueError("指标状态必须是 evaluated 或 not_evaluable")
        if self.status == "evaluated":
            if self.value is None or not np.isfinite(self.value):
                raise ValueError("可评估指标必须携带有限值")
        elif self.value is not None:
            raise ValueError("不可评估指标不能携带数值")

    @classmethod
    def unavailable(cls, name: str, reason: str, **details) -> "MetricValue":
        return cls(name=name, status="not_evaluable", reason=reason, details=details)


@dataclass(frozen=True)
class TSAParameters:
    """TSA 参数；samples_per_revolution 是角域采样率（点/转），不是 Hz。"""

    samples_per_revolution: int = 1024
    min_revolutions: int = 4
    mesh_harmonics: int = 3
    regular_sideband_order: int = 1
    max_order: float = 50.0

    def __post_init__(self) -> None:
        if isinstance(self.samples_per_revolution, bool) or self.samples_per_revolution < 16:
            raise ValueError("每转采样点数至少为 16")
        if self.min_revolutions < 2:
            raise ValueError("TSA 至少需要 2 个完整转周期")
        if self.mesh_harmonics < 1 or self.regular_sideband_order < 0:
            raise ValueError("啮合谐波数至少为 1，regular 边带阶数不能为负")
        if not np.isfinite(self.max_order) or self.max_order <= 0:
            raise ValueError("最大阶次必须是有限正数")


@dataclass(frozen=True)
class SynchronousAverage:
    """输入轴同步的算术 TSA；非同步成分位于 nonsynchronous_signal。"""

    angle_domain: AngleDomainSignal
    tsa_cycle: FloatArray
    tsa_signal: FloatArray
    revolutions: int
    synchronous_shaft: str = "input"

    def __post_init__(self) -> None:
        _finite_vector("TSA 单转波形", self.tsa_cycle)
        _finite_vector("TSA 序列", self.tsa_signal)
        if len(self.tsa_cycle) != self.angle_domain.samples_per_revolution:
            raise ValueError("TSA 单转波形长度必须等于每转采样点数")
        if self.revolutions < 2 or len(self.tsa_signal) != self.revolutions * len(self.tsa_cycle):
            raise ValueError("TSA 序列必须由整数个完整转周期构成")
        if len(self.angle_domain.samples) != len(self.tsa_signal):
            raise ValueError("TSA 角域输入必须截断到相同完整转数")

    @property
    def nonsynchronous_signal(self) -> FloatArray:
        """原始等角信号减 TSA，含非本轴同步成分；不是经典 residual。"""
        return self.angle_domain.samples - self.tsa_signal


@dataclass(frozen=True)
class TSARepresentation:
    """经典 regular/residual/differential 的显式构造结果。

    regular=啮合谐波及指定一阶边带；residual=TSA-regular；
    differential=regular-纯啮合谐波，即仅保留 regular 边带。
    """

    synchronous: SynchronousAverage
    mesh_order: float
    mesh_signal: FloatArray
    regular_signal: FloatArray
    residual_signal: FloatArray
    differential_signal: FloatArray
    spectrum: OrderSpectrum
    mesh_orders: tuple[float, ...]
    regular_sideband_orders: tuple[float, ...]
    regular_sideband_order: int
    amplitude_unit: str = "input_signal"

    def __post_init__(self) -> None:
        count = len(self.synchronous.tsa_signal)
        for name, values in (
            ("纯啮合信号", self.mesh_signal),
            ("regular 信号", self.regular_signal),
            ("residual 信号", self.residual_signal),
            ("differential 信号", self.differential_signal),
        ):
            _finite_vector(name, values)
            if len(values) != count:
                raise ValueError(f"{name}长度必须与 TSA 一致")
        if not np.allclose(
            self.synchronous.tsa_signal,
            self.regular_signal + self.residual_signal,
            rtol=1e-9,
            atol=1e-10,
        ):
            raise ValueError("residual 必须严格等于 TSA-regular")
        if not np.allclose(
            self.regular_signal,
            self.mesh_signal + self.differential_signal,
            rtol=1e-9,
            atol=1e-10,
        ):
            raise ValueError("differential 必须严格等于 regular-纯啮合信号")


@dataclass(frozen=True)
class TrendHistory:
    """与当前角域表示可比的健康历史方差，单位分别为输入单位²和包络单位²。"""

    samples_per_revolution: int
    mesh_order: float
    mesh_harmonics: int
    regular_sideband_order: int
    revolutions: int
    residual_variances: tuple[float, ...] = ()
    envelope_variances: tuple[float, ...] = ()
    input_unit: str = "input_signal"

    def __post_init__(self) -> None:
        if self.samples_per_revolution < 16 or not np.isfinite(self.mesh_order) or self.mesh_order <= 0:
            raise ValueError("历史角域采样率或啮合阶次无效")
        if self.mesh_harmonics < 1 or self.regular_sideband_order < 0 or self.revolutions < 2:
            raise ValueError("历史 regular 定义或实际 TSA 转数无效")
        for name, values in (
            ("历史 residual 方差", self.residual_variances),
            ("历史包络方差", self.envelope_variances),
        ):
            if any(not np.isfinite(value) or value <= 0 for value in values):
                raise ValueError(f"{name}必须全部为有限正数")


@dataclass(frozen=True)
class SidebandObservation:
    order: int
    lower_order: float
    upper_order: float
    lower_amplitude: float
    upper_amplitude: float
    asymmetry: float


@dataclass(frozen=True)
class SidebandAnalysis:
    """SER 是各窗最大单边幅值之和/啮合窗最大单边幅值，不是能量比。"""

    status: str
    mesh_amplitude: Optional[float]
    ser: MetricValue
    sidebands: tuple[SidebandObservation, ...] = ()
    ratio_semantics: str = "sum_of_window_peak_single_sided_amplitudes_over_mesh_peak"
    amplitude_unit: str = "input_signal"


@dataclass(frozen=True)
class CepstrumRepresentation:
    """实倒谱；quefrency_s 单位为秒，幅值是对数频谱单位。"""

    quefrency_s: FloatArray
    amplitude: FloatArray
    sample_rate_hz: float
    source: str = "real_cepstrum_log_amplitude"
    amplitude_unit: str = "log_input_amplitude"

    def __post_init__(self) -> None:
        _finite_vector("倒频率轴", self.quefrency_s)
        _finite_vector("倒谱幅值", self.amplitude)
        if len(self.quefrency_s) != len(self.amplitude):
            raise ValueError("倒频率轴与倒谱长度必须一致")
        if self.quefrency_s[0] != 0 or (
            len(self.quefrency_s) > 1
            and not np.allclose(np.diff(self.quefrency_s), 1.0 / self.sample_rate_hz)
        ):
            raise ValueError("倒频率轴必须从零开始并以 1/fs 秒等间隔")


@dataclass(frozen=True)
class OrderStatistics:
    status: str
    peak_concentration: Optional[float]
    kurtosis: Optional[float]
    reason: Optional[str] = None


@dataclass(frozen=True)
class FixedAxisAnalysis:
    """一次分析产生的全部原始结果，供独立评估 Pipeline 重评。"""

    order: OrderAnalysis
    spectrum: OrderSpectrum
    mesh_order: Optional[float]
    tsa: Optional[TSARepresentation]
    cepstrum: Optional[CepstrumRepresentation]
    order_statistics: OrderStatistics
    fm0: MetricValue
    fm4: MetricValue
    m6a: MetricValue
    m8a: MetricValue
    na4: MetricValue
    nb4: MetricValue
    car: MetricValue
    sideband_analysis: SidebandAnalysis
    tsa_status: str
    tsa_reason: Optional[str] = None
    rot_frequency_hz: Optional[float] = None
    rot_frequency_std_hz: float = 0.0


@dataclass(frozen=True)
class ZoomParameters:
    """Chirp-Z 网格参数；频率步长与记录长度分辨率严格分开。"""

    center_frequency_hz: float
    bandwidth_hz: float
    output_points: int = 1025

    def __post_init__(self) -> None:
        if not np.isfinite(self.center_frequency_hz) or self.center_frequency_hz <= 0:
            raise ValueError("Zoom 中心频率必须是有限正数")
        if not np.isfinite(self.bandwidth_hz) or self.bandwidth_hz <= 0:
            raise ValueError("Zoom 带宽必须是有限正数")
        if isinstance(self.output_points, bool) or self.output_points < 16:
            raise ValueError("Chirp-Z 输出点数至少为 16")


@dataclass(frozen=True)
class ZoomSpectrum:
    spectrum: Spectrum
    rayleigh_resolution_hz: float
    frequency_step_hz: float
    original_frequency_step_hz: float
    method: str = "chirp_z"
    resolution_contract: str = "rayleigh_fs_over_record_samples;denser_grid_is_not_super_resolution"
