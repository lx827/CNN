"""显式选择的原生筛分候选；归一化、随机数与族编排复用 Python 外层。"""

from .core import EMDParameters, FloatArray
from .python_adapter import PythonEMDImplementation


def _native_sift(signal: FloatArray, parameters: EMDParameters):
    if parameters.interpolation != "pchip" or parameters.stopping_rule != "sd":
        raise NotImplementedError("原生候选当前仅支持 PCHIP/SD")
    from cnn_compute import sift_pchip_sd

    return sift_pchip_sd(
        signal,
        max_sifts=parameters.max_sifts,
        mirror_extrema=parameters.mirror_extrema,
        sd_threshold=parameters.sd_threshold,
    )


class NativeEMDImplementation(PythonEMDImplementation):
    """仅显式注入时使用原生筛分；默认生产 adapter 保持 Python。

    当前仅支持 PCHIP/SD，其余配置明确报不支持，不回退或伪装成功。
    """

    def __init__(self) -> None:
        super().__init__(sift_kernel=_native_sift)
