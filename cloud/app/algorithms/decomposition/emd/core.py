"""EMD/EEMD/CEEMDAN 公共参数、结果和算法族 adapter 契约。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from ..types import ValidInterval


FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class EMDParameters:
    """筛分参数；``sd_threshold`` 只控制 IMF 数学筛分，不是去噪阈值。"""

    max_imfs: int = 8
    max_sifts: int = 100
    sd_threshold: float = 0.2
    mirror_extrema: int = 3
    interpolation: str = "pchip"
    stopping_rule: str = "sd"
    rilling_thresholds: tuple[float, float, float] = (0.05, 0.5, 0.05)

    def __post_init__(self) -> None:
        for name in ("max_imfs", "max_sifts", "mirror_extrema"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} 必须是正整数")
        if not np.isfinite(self.sd_threshold) or self.sd_threshold <= 0.0:
            raise ValueError("SD 阈值必须是有限正数")
        if self.interpolation not in ("pchip", "cubic"):
            raise ValueError("包络插值只支持 pchip 或 cubic")
        if self.stopping_rule not in ("sd", "rilling"):
            raise ValueError("停止准则只支持 sd 或 rilling")
        sd1, sd2, fraction = self.rilling_thresholds
        if not (0 < sd1 <= sd2 and 0 <= fraction <= 1) or not np.all(np.isfinite(self.rilling_thresholds)):
            raise ValueError("Rilling 阈值必须满足 0 < sd1 <= sd2, 0 <= fraction <= 1")


@dataclass(frozen=True)
class EnsembleParameters:
    """EEMD/CEEMDAN 参数；随机种子由公开函数显式传入。"""

    emd: EMDParameters = field(default_factory=EMDParameters)
    ensemble_size: int = 50
    noise_scale: float = 0.2

    def __post_init__(self) -> None:
        if isinstance(self.ensemble_size, bool) or not isinstance(self.ensemble_size, int) or self.ensemble_size <= 0:
            raise ValueError("集成次数必须是正整数")
        if not np.isfinite(self.noise_scale) or self.noise_scale < 0.0:
            raise ValueError("噪声幅值比例必须是有限非负数")


@dataclass(frozen=True)
class EMDResult:
    """所有 IMF 和残差都与输入共享长度及时间轴。"""

    method: str
    status: str
    input_length: int
    sample_rate_hz: float
    imfs: tuple[FloatArray, ...]
    residual: FloatArray
    valid_interval: ValidInterval
    sift_iterations: tuple[int, ...]
    converged: tuple[bool, ...]
    seed: int | None = None
    reason: str | None = None

    @property
    def reconstructed(self) -> FloatArray:
        return sum(self.imfs, start=self.residual.copy())


class EMDImplementation(Protocol):
    """EMD 族专属替换接口；未来 EMD-signal/PyEMD 在 adapter 内适配。"""

    def emd(self, signal: FloatArray, sample_rate_hz: float, parameters: EMDParameters) -> EMDResult:
        ...

    def eemd(
        self, signal: FloatArray, sample_rate_hz: float,
        parameters: EnsembleParameters, seed: int,
    ) -> EMDResult:
        ...

    def ceemdan(
        self, signal: FloatArray, sample_rate_hz: float,
        parameters: EnsembleParameters, seed: int,
    ) -> EMDResult:
        ...


def _validate_signal(signal: FloatArray, sample_rate_hz: float) -> FloatArray:
    arr = np.asarray(signal, dtype=np.float64)
    if arr.ndim != 1 or len(arr) < 8:
        raise ValueError("EMD 输入必须是一维且至少包含 8 个采样点")
    if not np.all(np.isfinite(arr)):
        raise ValueError("输入信号不能包含 NaN 或无穷值")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise ValueError("采样率必须是有限正数")
    return arr


def _implementation(implementation: EMDImplementation | None) -> EMDImplementation:
    if implementation is not None:
        return implementation
    from .python_adapter import PythonEMDImplementation
    return PythonEMDImplementation()


def decompose_emd(
    signal: FloatArray,
    sample_rate_hz: float,
    parameters: EMDParameters | None = None,
    implementation: EMDImplementation | None = None,
) -> EMDResult:
    """基础 EMD；无足够极值时返回原残差和 ``indeterminate``，不伪造 IMF。"""
    arr = _validate_signal(signal, sample_rate_hz)
    return _implementation(implementation).emd(arr, sample_rate_hz, parameters or EMDParameters())


def _validate_seed(seed: int) -> None:
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("随机种子必须是非负整数")


def decompose_eemd(
    signal: FloatArray,
    sample_rate_hz: float,
    *,
    seed: int,
    parameters: EnsembleParameters | None = None,
    implementation: EMDImplementation | None = None,
) -> EMDResult:
    """EEMD；相同输入、参数和种子逐数组可复现。"""
    arr = _validate_signal(signal, sample_rate_hz)
    _validate_seed(seed)
    return _implementation(implementation).eemd(arr, sample_rate_hz, parameters or EnsembleParameters(), seed)


def decompose_ceemdan(
    signal: FloatArray,
    sample_rate_hz: float,
    *,
    seed: int,
    parameters: EnsembleParameters | None = None,
    implementation: EMDImplementation | None = None,
) -> EMDResult:
    """CEEMDAN；逐阶添加白噪声 IMF，并保持 IMF 与残差的完备性。"""
    arr = _validate_signal(signal, sample_rate_hz)
    _validate_seed(seed)
    return _implementation(implementation).ceemdan(arr, sample_rate_hz, parameters or EnsembleParameters(), seed)
