"""Dragomiretskiy–Zosso ADMM VMD；计算、循环和重构均在 C++。

以 vrcarva/vmdpy 官方实现核实公式，保留当前调用的归一化、奇数长度和有效
窗口语义；不继承参考实现保存所有轮次频谱、丢弃奇数尾点和少返回一轮的问题。
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from ._native import vmd as _vmd

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class Decomposition:
    """拥有型结果。模态形状 [K,valid_length]；中心及历史单位 Hz。

    history 只显示真实迭代行，其 owner 保留预分配 max_iterations*K 容量；
    无额外裁剪复制。status=valid 不代表 converged；未收敛保留研究表示。
    失败模态为空，残差只在 valid/indeterminate 时有有效含义。
    """

    modes: FloatArray
    center_frequencies_hz: FloatArray
    center_frequency_history_hz: FloatArray
    residual: FloatArray
    input_length: int
    valid_length: int
    iterations: int
    converged: bool
    status: str
    reason: str | None


def decompose(signal, sample_rate_hz: float, *, modes: int = 5, alpha: float = 2000.0,
              tau: float = 0.0, tolerance: float = 1e-7, max_iterations: int = 200,
              dc: bool = False, max_samples: int | None = 51200,
              initialization: int = 1, seed: int = 0) -> Decomposition:
    """同步 VMD。有效窗口 [0,min(N,max_samples))，None 明确处理全长。

    输入一维有限，至少16点；modes/max_iterations 为正，alpha/tolerance>0，
    tau>=0。初始化 0/1/2 分别为零/均匀/对数随机中心，随机路径按本库 seed
    可复现，不承诺复现 NumPy RNG。dc 固定第一中心为零。连续 float64 借用，
    其他布局集中转换；输出不借用输入或工作区，计算释放 GIL，无内部线程。
    """
    values = np.asarray(signal, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError("VMD 输入必须是一维")
    values = np.ascontiguousarray(values)
    raw = _vmd.decompose(values, sample_rate_hz, modes, alpha, tau, tolerance,
                         max_iterations, dc, 0 if max_samples is None else max_samples,
                         initialization, seed)
    components, centers, history, residual, length, iterations, converged, status, reason = raw
    components = components.reshape((-1, length))
    history = history.reshape((-1, modes))[:iterations]
    return Decomposition(components, centers, history, residual, len(values), length,
                         iterations, converged, status, reason or None)
