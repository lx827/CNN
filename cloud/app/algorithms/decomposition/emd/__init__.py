"""EMD/EEMD/CEEMDAN 纯算法与实现 adapter。"""

from .core import (
    EMDImplementation,
    EMDParameters,
    EMDResult,
    EnsembleParameters,
    decompose_ceemdan,
    decompose_eemd,
    decompose_emd,
)
from .native_adapter import NativeEMDImplementation
from .python_adapter import PythonEMDImplementation

__all__ = [
    "EMDImplementation",
    "EMDParameters",
    "EMDResult",
    "EnsembleParameters",
    "NativeEMDImplementation",
    "PythonEMDImplementation",
    "decompose_ceemdan",
    "decompose_eemd",
    "decompose_emd",
]
