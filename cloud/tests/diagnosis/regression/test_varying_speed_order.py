"""P0 转速/相位回归：独立合成信号与公式断言，无数据集、无旧输出 golden。

运行：cd cloud && uv run python tests/diagnosis/regression/test_varying_speed_order.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from tests.diagnosis.algorithms.test_order_pipeline import run_all_tests


if __name__ == "__main__":
    run_all_tests()
