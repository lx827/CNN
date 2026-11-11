"""显式选择的原生筛分候选；归一化、随机数与族编排复用 Python 外层。"""

from .core import EMDParameters, FloatArray
from .python_adapter import PythonEMDImplementation


def _native_sift(signal: FloatArray, parameters: EMDParameters):
    from cnn_compute import sift_imf

    return sift_imf(
        signal,
        max_sifts=parameters.max_sifts,
        mirror_extrema=parameters.mirror_extrema,
        sd_threshold=parameters.sd_threshold,
        interpolation=parameters.interpolation,
        stopping_rule=parameters.stopping_rule,
        rilling_thresholds=parameters.rilling_thresholds,
    )


class NativeEMDImplementation(PythonEMDImplementation):
    """仅显式注入时使用原生筛分；默认生产 adapter 保持 Python。

    支持 PCHIP/cubic 与 SD/Rilling，复用同一外层且不回退或伪装成功。
    """

    def __init__(self) -> None:
        super().__init__(sift_kernel=_native_sift)
