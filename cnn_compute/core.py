"""公共原生数值模块，供 Python 调用与算法复用。"""

import numpy as np
from numpy.typing import NDArray

from ._native import core as _core

__all__ = ["build_info", "cubic", "pchip", "solve_tridiagonal"]


def _array(values: NDArray[np.float64]) -> NDArray[np.float64]:
    if not isinstance(values, np.ndarray) or values.dtype != np.float64:
        raise TypeError("输入必须是 float64 ndarray")
    return np.ascontiguousarray(values)


def build_info() -> dict[str, object]:
    """返回编译器、目标、编译选项、实际 SIMD 与 Eigen 版本等原生构建信息。"""
    return _core.build_info()


def pchip(
    x: NDArray[np.float64], y: NDArray[np.float64], query: NDArray[np.float64]
) -> NDArray[np.float64]:
    """PCHIP 插值；至少两个严格递增节点，查询可乱序并允许外推。

    三个输入均为一维有限 float64 ndarray，节点与值等长，查询非空。
    非连续视图最多连续化一次；只读借用输入，返回独立且连续的数组。
    参数校验发生在原生边界；计算释放 GIL，非有限插值结果抛 RuntimeError。
    """
    return _core.pchip(_array(x), _array(y), _array(query))


def cubic(
    x: NDArray[np.float64], y: NDArray[np.float64], query: NDArray[np.float64]
) -> NDArray[np.float64]:
    """not-a-knot 三次样条；两个节点退化为直线，三个节点为抛物线。

    节点、查询、输入借用、输出所有权及失败行为与 pchip 相同。
    首尾段多项式承担外推，计算释放 GIL。
    """
    return _core.cubic(_array(x), _array(y), _array(query))


def solve_tridiagonal(
    lower: NDArray[np.float64],
    diagonal: NDArray[np.float64],
    upper: NDArray[np.float64],
    rhs: NDArray[np.float64],
) -> NDArray[np.float64]:
    """部分主元消元求解单右端项三对角系统，工作空间为 O(N)。

    输入均为一维有限 float64 ndarray；主对角与右端项长度 N >= 4，
    上下对角长度 N-1。非连续视图最多连续化一次，消元使用独立缓冲区，
    不修改调用方输入；返回独立连续数组，计算释放 GIL，奇异系统抛 RuntimeError。
    """
    return _core.solve_tridiagonal(
        _array(lower), _array(diagonal), _array(upper), _array(rhs)
    )
