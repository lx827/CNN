"""本地 emd 0.8.1 语义的原生 EMD；独立于旧筛分候选与生产默认实现。

计算和算法循环在 C++；此层处理输入布局、参数映射和输出形状。
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from ._native import emd as _emd
from ._native import envelope as _envelope
from .envelope import _options as _envelope_options

FloatArray = NDArray[np.float64]
IMFOptions = _emd.IMFOptions
Options = _emd.Options
EnvelopeOptions = _envelope.Options


class ConvergenceError(RuntimeError):
    """筛分迭代耗尽或产生数值失败；不把近似值伪装为已收敛。"""


@dataclass(frozen=True)
class Decomposition:
    """各列零复制交接的拥有型结果；基础 sift 的末列可能是残差。

    components 与输入和 C++ 工作区独立，iterations 只记录真实 IMF 筛分。
    as_array 按 [samples, components] 组装一次连续二维数组并复制所有列；
    需要避免该布局复制的调用者可直接使用 components。
    """

    components: tuple[FloatArray, ...]
    iterations: tuple[int, ...]
    status: str
    input_length: int

    def as_array(self) -> FloatArray:
        """返回独立二维数组；明确包含一次列组装复制。"""
        if not self.components:
            return np.empty((self.input_length, 0), dtype=np.float64)
        return np.column_stack(self.components)


def _signal(signal) -> FloatArray:
    values = np.asarray(signal, dtype=np.float64)
    if values.ndim == 2 and values.shape[1] == 1:
        values = values[:, 0]
    if values.ndim != 1:
        raise ValueError("输入必须是一维或 [samples, 1]")
    return np.ascontiguousarray(values)


def _enum(enum, value, field):
    if not isinstance(value, str) or not hasattr(enum, value):
        raise ValueError(f"不支持的 {field}: {value!r}")
    return getattr(enum, value)


def _imf_options(values=None) -> IMFOptions:
    options = IMFOptions()
    for name, value in (values or {}).items():
        if name not in {
            "env_step_size",
            "max_iters",
            "energy_thresh",
            "stop_method",
            "sd_thresh",
            "rilling_thresh",
        }:
            raise TypeError(f"不支持的 IMF 参数: {name}")
        if name == "stop_method":
            value = _enum(_emd.StopMethod, value, name)
        setattr(options, name, value)
    return options


def _options(
    max_imfs=None,
    sift_thresh=1e-8,
    energy_thresh=50,
    rilling_thresh=None,
    imf_opts=None,
    envelope_opts=None,
    extrema_opts=None,
) -> Options:
    options = Options()
    options.imf = _imf_options(imf_opts)
    options.envelope = _envelope_options(envelope_opts, extrema_opts)
    if max_imfs is not None and (
        isinstance(max_imfs, bool) or not isinstance(max_imfs, int) or max_imfs <= 0
    ):
        raise ValueError("max_imfs 必须是正整数或 None")
    options.max_imfs = 0 if max_imfs is None else max_imfs
    options.sift_thresh = sift_thresh
    options.energy_thresh = energy_thresh
    options.rilling_thresh = (
        (0.05, 0.5, 0.05) if rilling_thresh is True else rilling_thresh
    )
    return options


def _result(raw, length) -> Decomposition:
    columns, iterations, status = raw
    return Decomposition(tuple(columns), tuple(iterations), status, length)


def _require_success(result: Decomposition) -> None:
    if result.status in {"iteration_limit", "numerical_failure"}:
        raise ConvergenceError(f"EMD 未完成: {result.status}")


def sift_detailed(
    signal,
    *,
    max_imfs=None,
    sift_thresh=1e-8,
    energy_thresh=50,
    rilling_thresh=None,
    imf_opts=None,
    envelope_opts=None,
    extrema_opts=None,
) -> Decomposition:
    """完整原生 EMD，返回各列拥有型结果与真实状态；输入只读借用。

    初始极值不足时返回原残差及 insufficient_extrema；参考 0.8.1 在此
    边界可能引用未定义变量，本入口明确结果，不宣称逐异常兼容。
    """
    values = _signal(signal)
    options = _options(
        max_imfs,
        sift_thresh,
        energy_thresh,
        rilling_thresh,
        imf_opts,
        envelope_opts,
        extrema_opts,
    )
    return _result(_emd.sift(values, options), len(values))


def sift(
    signal,
    sift_thresh=1e-8,
    energy_thresh=50,
    rilling_thresh=None,
    max_imfs=None,
    return_residual=True,
    *,
    imf_opts=None,
    envelope_opts=None,
    extrema_opts=None,
) -> FloatArray:
    """返回 [samples, components]，完整筛分循环在 C++ 中执行。

    非零残差附在末列；与本地 emd 0.8.1 一样 return_residual 不改变此
    行为。二维输出包含一次布局复制；sift_detailed 可直接获得零复制列。
    迭代耗尽抛 ConvergenceError，不返回假成功。
    """
    result = sift_detailed(
        signal,
        max_imfs=max_imfs,
        sift_thresh=sift_thresh,
        energy_thresh=energy_thresh,
        rilling_thresh=rilling_thresh,
        imf_opts=imf_opts,
        envelope_opts=envelope_opts,
        extrema_opts=extrema_opts,
    )
    _require_success(result)
    return result.as_array()


def get_next_imf(
    signal,
    env_step_size=1,
    max_iters=1000,
    energy_thresh=50,
    stop_method="sd",
    sd_thresh=0.1,
    rilling_thresh=(0.05, 0.5, 0.05),
    envelope_opts=None,
    extrema_opts=None,
) -> tuple[FloatArray, bool]:
    """返回 [samples,1] IMF 和能否继续提取的标志；后者不是收敛标志。

    输入在调用期间借用，输出独立拥有；原生计算释放 GIL。
    """
    values = _signal(signal)
    options = _imf_options(
        {
            "env_step_size": env_step_size,
            "max_iters": max_iters,
            "energy_thresh": energy_thresh,
            "stop_method": stop_method,
            "sd_thresh": sd_thresh,
            "rilling_thresh": rilling_thresh,
        }
    )
    array, more, _, status = _emd.get_next_imf(
        values, options, _envelope_options(envelope_opts, extrema_opts)
    )
    if status in {"iteration_limit", "numerical_failure"}:
        raise ConvergenceError(f"EMD 未完成: {status}")
    return array[:, None], more


# 各算法单独实现；此处聚合公开入口，复用上面的参数与拥有型结果契约。
from ._emd_mask import (  # noqa: F401
    IteratedMaskDecomposition,
    MaskDecomposition,
    get_mask_freqs,
    get_next_imf_mask,
    iterated_mask_sift,
    iterated_mask_sift_detailed,
    mask_sift,
    mask_sift_detailed,
    mask_sift_second_layer,
    sift_second_layer,
)
