"""DWT、WP 与小波阈值去噪；数学计算全部位于独立 C++ 模块。

滤波器为 PyWavelets 1.8.0 官方 C 内核，支持其全部内置离散小波与九种
延拓模式。输入连续 float64 时借用，其他布局集中转换一次；输出 NumPy
持有独立 C++ owner，下一次调用不会覆盖它。计算期间释放 GIL。
"""

import numpy as np
from numpy.typing import NDArray

from ._native import wavelet as _wavelet

FloatArray = NDArray[np.float64]
CoefficientSet = _wavelet.CoefficientSet


def _signal(signal) -> FloatArray:
    values = np.asarray(signal, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError("小波输入必须是一维")
    return np.ascontiguousarray(values)


def analyze_coefficients(signal, wavelet: str = "db8", level: int = 3,
                         mode: str = "symmetric", *, packet: bool = False) -> CoefficientSet:
    """轻量分析：只返回原生系数 owner，不物化全部全长分量。

    result.coefficients 为只读 NumPy 借用视图，各视图保持 owner 存活；
    result.reconstruct(indices) 只沿所选路径重构并相加，返回独立拥有型
    长度 N 数组。DWT 索引顺序 aL,dL,...,d1；WP 索引为自然路径顺序。
    选哪些分量仍由调用者决定，重复或不存在的索引显式报错。
    """
    return _wavelet.analyze_coefficients(_signal(signal), wavelet, level, mode, packet)


def dwt(signal, wavelet: str = "db8", level: int = 3, mode: str = "symmetric") -> tuple[tuple[FloatArray, ...], tuple[FloatArray, ...]]:
    """返回 (系数, 原时间轴分量)，两者均按 aL,dL,...,d1 排序。

    层数必须位于当前记录和滤波器的无边界效应最大层数内；分量精确裁至
    输入长度，奇数记录不丢点。每个结果数组独立拥有；完整分量占 O(level*N)。
    """
    return _wavelet.decompose(_signal(signal), wavelet, level, mode, False)


def wavelet_packet(signal, wavelet: str = "db8", level: int = 3, mode: str = "symmetric") -> tuple[tuple[FloatArray, ...], tuple[FloatArray, ...]]:
    """返回 (叶系数, 原时间轴叶分量)，均为自然路径 aa... 到 dd...。

    自然路径与频率顺序不同；此入口不做节点选择或故障评估。完整返回
    2**level 个波形，因此结果占 O(2**level*N)；不复制整棵包树。
    """
    return _wavelet.decompose(_signal(signal), wavelet, level, mode, True)


def denoise(signal, wavelet: str = "db8", level: int | None = None,
            threshold_mode: str = "soft", threshold_scale: float = 1.0) -> FloatArray:
    """MAD 通用阈值细节收缩，支持 soft/hard/improved，近似带不收缩。

    level=None 使用最大允许层数；边界固定 symmetric。保持输入幅值单位和
    长度，MAD 不设绝对幅值下限。improved 是既有工程收缩，不声称普适最优。
    """
    return _wavelet.denoise(_signal(signal), wavelet, 0 if level is None else level,
                            threshold_mode, threshold_scale)
