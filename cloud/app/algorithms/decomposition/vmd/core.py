"""VMD 参数、带 Hz 单位的结果和算法族 adapter 契约。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from ..types import ValidInterval


FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class VMDParameters:
    """VMD 数学参数；``max_samples`` 是显式前导分析窗口，不做隐式补零。"""

    modes: int = 5
    alpha: float = 2000.0
    tau: float = 0.0
    tolerance: float = 1e-7
    max_iterations: int = 200
    dc: bool = False
    max_samples: int | None = 51200

    def __post_init__(self) -> None:
        for name in ("modes", "max_iterations"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} 必须是正整数")
        if self.max_samples is not None and (
            isinstance(self.max_samples, bool) or not isinstance(self.max_samples, int)
            or self.max_samples < 16
        ):
            raise ValueError("VMD 分析窗口必须至少为 16 点，或设为 None")
        if not np.isfinite(self.alpha) or self.alpha <= 0.0:
            raise ValueError("alpha 必须是有限正数")
        if not np.isfinite(self.tau) or self.tau < 0.0:
            raise ValueError("tau 必须是有限非负数")
        if not np.isfinite(self.tolerance) or self.tolerance <= 0.0:
            raise ValueError("收敛容差必须是有限正数")
        if not isinstance(self.dc, bool):
            raise ValueError("dc 必须是布尔值")


@dataclass(frozen=True)
class VMDResult:
    """固定 VMD 返回结构；模态和残差只覆盖 ``valid_interval``。"""

    status: str
    input_length: int
    sample_rate_hz: float
    modes: FloatArray
    center_frequencies_hz: FloatArray
    center_frequency_history_hz: FloatArray
    residual: FloatArray
    valid_interval: ValidInterval
    iterations: int
    converged: bool
    reason: str | None = None


class VMDImplementation(Protocol):
    """VMD 族专属 seam；Rust/C++ 实现无需模拟 Python tuple 返回。"""

    def vmd(self, signal: FloatArray, sample_rate_hz: float, parameters: VMDParameters) -> VMDResult:
        ...


def decompose_vmd(
    signal: FloatArray,
    sample_rate_hz: float,
    parameters: VMDParameters | None = None,
    implementation: VMDImplementation | None = None,
) -> VMDResult:
    """执行 VMD；中心频率从 cycles/sample 乘采样率转换为 Hz。"""
    arr = np.asarray(signal, dtype=np.float64)
    if arr.ndim != 1 or len(arr) < 16:
        raise ValueError("VMD 输入必须是一维且至少包含 16 个采样点")
    if not np.all(np.isfinite(arr)):
        raise ValueError("输入信号不能包含 NaN 或无穷值")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise ValueError("采样率必须是有限正数")
    params = parameters or VMDParameters()
    if implementation is None:
        from .python_adapter import PythonVMDImplementation
        implementation = PythonVMDImplementation()
    return implementation.vmd(arr, sample_rate_hz, params)
