"""行星分析与评估的数据契约。"""

from dataclasses import dataclass, field

import numpy as np

from app.algorithms.gear.fixed_axis.types import MetricValue, SynchronousAverage
from app.algorithms.mechanics.planetary import PlanetaryGearGeometry
from app.algorithms.order import OrderSpectrum


@dataclass(frozen=True)
class PlanetaryParameters:
    samples_per_revolution: int = 1024
    max_duration_s: float = 5.0
    n_sidebands: int = 6
    tsa_reference_axis: str = "carrier"
    min_tsa_revolutions: int = 4
    mesh_harmonics: int = 3
    regular_sidebands: int = 1

    def __post_init__(self) -> None:
        for key, minimum in (
            ("samples_per_revolution", 16),
            ("n_sidebands", 1),
            ("min_tsa_revolutions", 2),
            ("mesh_harmonics", 1),
            ("regular_sidebands", 0),
        ):
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"非法 {key}")
        if not np.isfinite(self.max_duration_s) or not 0 < self.max_duration_s <= 5:
            raise ValueError("行星计算窗口必须位于 (0, 5] 秒")
        if self.tsa_reference_axis not in {"sun", "carrier"}:
            raise ValueError("TSA 同步轴只支持 sun 或 carrier，不支持行星轮自转 TSA")


@dataclass(frozen=True)
class PlanetarySidebands:
    ser: MetricValue
    spacing_order: float
    mesh_amplitude: float | None = None
    observations: tuple[dict, ...] = ()


@dataclass(frozen=True)
class ModulationPeak:
    name: str
    target_order: float
    status: str
    amplitude: float | None = None
    peak_order: float | None = None
    background: float | None = None
    amplitude_to_background: float | None = None
    reason: str | None = None


@dataclass(frozen=True)
class PlanetaryMethodAnalysis:
    method: str
    status: str
    reference_axis: str
    spectrum: OrderSpectrum | None = None
    peaks: tuple[ModulationPeak, ...] = ()
    metrics: dict[str, MetricValue] = field(default_factory=dict)
    reason: str | None = None
    details: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PlanetaryAnalysis:
    status: str
    geometry: PlanetaryGearGeometry | None
    reference_speed_hz: float | None
    spectrum: OrderSpectrum | None = None
    sidebands: PlanetarySidebands | None = None
    methods: tuple[PlanetaryMethodAnalysis, ...] = ()
    metrics: dict[str, MetricValue] = field(default_factory=dict)
    synchronous: SynchronousAverage | None = None
    tsa_reference_axis: str | None = None
    reason: str | None = None
    representation_key: tuple = ()


@dataclass(frozen=True)
class PlanetaryThreshold:
    """调用方已验证的健康基线界限；键是具体方法/指标，不接受跨方法投票。"""

    metric_key: str
    warning: float
    critical: float
    direction: str = "above"

    def __post_init__(self) -> None:
        if self.direction not in {"above", "below"} or not all(
            np.isfinite(v) for v in (self.warning, self.critical)
        ):
            raise ValueError("非法基线阈值")
        if (self.direction == "above" and self.warning >= self.critical) or (
            self.direction == "below" and self.warning <= self.critical
        ):
            raise ValueError("warning/critical 顺序与方向不一致")


@dataclass(frozen=True)
class PlanetaryBaseline:
    """相同几何、速度、方法参数与记录长度下的显式可比基线。"""

    representation_key: tuple
    thresholds: tuple[PlanetaryThreshold, ...]
    source: str

    def __post_init__(self) -> None:
        if not self.source or len({v.metric_key for v in self.thresholds}) != len(
            self.thresholds
        ):
            raise ValueError("基线必须有来源，且指标键不能重复")


@dataclass(frozen=True)
class PlanetaryMomentHistory:
    """NA4/NB4 的健康方差历史；表示键同时约束几何、速度、周期数与单位。"""

    representation_key: tuple
    residual_variances: tuple[float, ...] = ()
    envelope_variances: tuple[float, ...] = ()
    source: str = ""

    def __post_init__(self) -> None:
        if not self.source or not all(
            np.isfinite(v) and v > 0
            for v in self.residual_variances + self.envelope_variances
        ):
            raise ValueError("历史必须有来源和有限正方差")


@dataclass(frozen=True)
class PlanetaryEvaluation:
    status: str
    conclusion: str
    indicators: dict[str, dict]
    reason: str | None = None
    unconsumed_metrics: tuple[str, ...] = ()
