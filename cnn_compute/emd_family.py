"""业务 EMD/EEMD/Torres CEEMDAN 的完整 C++ 入口，与 emd.sift 参照族独立。"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from ._native import emd as _native

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class Decomposition:
    """各 IMF/残差独立拥有 C++ 存储，后续调用不覆盖；未收敛保留真实状态。"""

    imfs: tuple[FloatArray, ...]
    residual: FloatArray
    sift_iterations: tuple[int, ...]
    converged: tuple[bool, ...]
    reason: str | None

    @property
    def status(self) -> str:
        return "valid" if self.imfs else "indeterminate"


def _enum(enum, value: str):
    if not isinstance(value, str) or not hasattr(enum, value):
        raise ValueError(f"不支持的 EMD 配置: {value!r}")
    return getattr(enum, value)


def decompose(
    signal: ArrayLike,
    *,
    method: str = "emd",
    max_imfs: int = 8,
    max_sifts: int = 100,
    mirror_extrema: int = 3,
    sd_threshold: float = 0.2,
    interpolation: str = "pchip",
    stopping_rule: str = "sd",
    rilling_thresholds: tuple[float, float, float] = (0.05, 0.5, 0.05),
    ensemble_size: int = 50,
    noise_scale: float = 0.2,
    seed: int = 0,
) -> Decomposition:
    """完整数值流程在 C++ 中执行，Python 仅适配参数、布局与拥有型结果。

    输入为至少 8 点的一维有限信号；合规 float64 C 连续输入只读借用，
    其它布局/类型在此转换一次。原生公开边界检查数值前提，计算释放 GIL。
    每个返回数组通过 capsule 独立持有最终缓冲，生命周期与工作区无关。
    原生噪声由 seed_seq/mt19937_64/标准库 normal_distribution 生成，seed
    支持任意长度非负整数，同一构建可复现，不承诺 NumPy/跨标准库逐点一致。
    迭代耗尽保留近似 IMF、次数与 converged=False；数值失败直接抛出异常。
    """
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("随机种子必须是非负整数")
    limbs = []
    remaining = seed
    while remaining:
        limbs.append(remaining & 0xFFFFFFFF)
        remaining >>= 32
    options = _native.FamilyOptions()
    sift = _native.FamilySiftParameters()
    sift.max_sifts = max_sifts
    sift.mirror_extrema = mirror_extrema
    sift.sd_threshold = sd_threshold
    sift.interpolation = _enum(_native.FamilyInterpolation, interpolation)
    sift.stopping_rule = _enum(_native.FamilyStoppingRule, stopping_rule)
    sift.rilling_thresholds = rilling_thresholds
    options.sift = sift
    options.max_imfs = max_imfs
    options.ensemble_size = ensemble_size
    options.noise_scale = noise_scale
    arrays, residual, iterations, converged, reason = _native.decompose(
        np.ascontiguousarray(signal, dtype=np.float64),
        _enum(_native.FamilyMethod, method),
        options,
        limbs,
    )
    return Decomposition(arrays, residual, tuple(iterations), tuple(converged), reason)
