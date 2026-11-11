"""只用于绘图的极值抽点；不参与任何全长数值分析。"""

import numpy as np
from numpy.typing import NDArray


def decimate_extrema(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    maximum: int = 2400,
) -> NDArray[np.float64]:
    """按块保留最小/最大点及真实横坐标，返回 (x, y) 两列数组。"""
    x_values = np.asarray(x)
    y_values = np.asarray(y)
    if x_values.ndim != 1 or y_values.ndim != 1 or len(x_values) != len(y_values):
        raise ValueError("抽点横纵坐标必须是一维等长数组")
    if (
        isinstance(maximum, bool)
        or not isinstance(maximum, (int, np.integer))
        or maximum < 2
    ):
        raise ValueError("绘图点数上限必须是至少为 2 的整数")
    if len(y_values) <= maximum:
        return np.column_stack((x_values, y_values))

    block_size = int(np.ceil(len(y_values) / (maximum // 2)))
    indices = []
    for start in range(0, len(y_values), block_size):
        block = y_values[start : start + block_size]
        indices.extend(
            sorted(
                {
                    start + int(np.argmin(block)),
                    start + int(np.argmax(block)),
                }
            )
        )
    return np.column_stack((x_values[indices], y_values[indices]))
