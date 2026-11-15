"""独立原生诊断计算包；应用依赖由根项目依赖组管理。"""

import numpy as np
from numpy.typing import NDArray

from . import core, emd, envelope, interpolation
from ._native import sift_imf as _sift_imf
from ._native import sift_pchip_sd as _sift_pchip_sd
from .core import build_info

__all__ = ["build_info", "core", "emd", "envelope", "interpolation", "sift_imf", "sift_pchip_sd"]


def sift_pchip_sd(
    signal: NDArray[np.float64],
    *,
    max_sifts: int = 100,
    mirror_extrema: int = 3,
    sd_threshold: float = 0.2,
) -> tuple[NDArray[np.float64], int, bool] | None:
    """PCHIP/SD 完整单 IMF 筛分，返回 (独立数组, 次数, 收敛) 或 None。

    输入必须是 float64 ndarray；非连续视图显式连续化一次，合规输入只读
    借用且调用方保持 owner。维度、有限性与参数在原生边界检查一次。
    本函数不修改输入，不生成随机数或线程池，不吞原生数值异常。
    """
    if not isinstance(signal, np.ndarray) or signal.dtype != np.float64:
        raise TypeError("输入必须是 float64 ndarray")
    values = np.ascontiguousarray(signal)
    return _sift_pchip_sd(values, max_sifts, mirror_extrema, sd_threshold)


def sift_imf(
    signal: NDArray[np.float64],
    *,
    max_sifts: int = 100,
    mirror_extrema: int = 3,
    sd_threshold: float = 0.2,
    interpolation: str = "pchip",
    stopping_rule: str = "sd",
    rilling_thresholds: tuple[float, float, float] = (0.05, 0.5, 0.05),
) -> tuple[NDArray[np.float64], int, bool] | None:
    """完整单 IMF 筛分，支持 PCHIP/cubic 与 SD/Rilling 四种组合。

    返回 (独立 float64 数组, 筛分次数, 收敛标志)，初始极值不足返回 None。
    输入 float64 ndarray 只读借用；非连续视图最多连续化一次。
    参数与输入在原生边界检查一次；计算释放 GIL，不新增线程池。
    """
    if not isinstance(signal, np.ndarray) or signal.dtype != np.float64:
        raise TypeError("输入必须是 float64 ndarray")
    values = np.ascontiguousarray(signal)
    return _sift_imf(
        values,
        max_sifts,
        mirror_extrema,
        sd_threshold,
        interpolation,
        stopping_rule,
        rilling_thresholds,
    )
