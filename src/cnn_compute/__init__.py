"""独立原生诊断计算包；应用依赖由根项目依赖组管理。"""

from ._native import build_info as _build_info

__all__ = ["build_info"]


def build_info() -> dict:
    """返回编译器、目标、编译选项、实际 SIMD 与 Eigen 版本等原生构建信息。"""
    return _build_info()
