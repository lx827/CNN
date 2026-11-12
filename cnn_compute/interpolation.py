"""独立插值模块；公开结果拥有存储，内部 C++ 入口支持直接写输出。"""

import numpy as np
from numpy.typing import NDArray

from ._native import interpolation as _native


def interpolate(x, y, query, method="splrep") -> NDArray[np.float64]:
    """在严格递增节点上插值，支持 splrep、pchip、mono_pchip 和 cubic。

    一维有限输入在 C++ 公开边界检查；合规连续 float64 数组借用，其余
    输入集中转换一次。返回独立一维数组，查询允许外推。
    """
    method = "pchip" if method == "mono_pchip" else method
    if method not in {"splrep", "pchip", "cubic"}:
        raise ValueError(f"不支持的插值方法: {method!r}")
    arrays = [np.ascontiguousarray(v, dtype=np.float64) for v in (x, y, query)]
    return _native.interpolate(*arrays, getattr(_native.Method, method))
