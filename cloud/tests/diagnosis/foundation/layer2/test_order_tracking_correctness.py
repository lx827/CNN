"""Layer 2 转速/相位正确性：由独立公式测试提供全部断言。

旧测试只检查宽泛转速范围和谱峰形态，无法发现谱轴、分辨率或幅值刻度错误，已删除。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from tests.diagnosis.algorithms.test_order_pipeline import run_all_tests


if __name__ == "__main__":
    run_all_tests()
