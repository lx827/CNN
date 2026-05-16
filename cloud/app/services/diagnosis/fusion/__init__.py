"""
D-S 证据融合子模块

提供 Dempster-Shafer 证据理论融合算法，将多种诊断方法的结果融合为综合故障概率分布。
"""
from .ds_fusion import (
    EvidenceFrame,
    BPA,
    dempster_combination,
    murphy_average_combination,
    dempster_shafer_fusion,
    DEFAULT_FAULT_TYPES,
)

__all__ = [
    "EvidenceFrame",
    "BPA",
    "dempster_combination",
    "murphy_average_combination",
    "dempster_shafer_fusion",
    "DEFAULT_FAULT_TYPES",
]