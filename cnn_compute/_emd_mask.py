"""EMD mask 系列薄入口：参数与布局在 Python，数值循环全部在 C++。"""

from dataclasses import dataclass

import numpy as np

from ._native import emd as _native
from .emd import (
    ConvergenceError,
    Decomposition,
    _envelope_options,
    _imf_options,
    _options,
    _require_success,
    _result,
    _signal,
)


@dataclass(frozen=True)
class MaskDecomposition:
    """零复制拥有型 IMF 列及实际 mask 频率，结果独立于工作区。"""

    decomposition: Decomposition
    mask_frequencies: np.ndarray


@dataclass(frozen=True)
class IteratedMaskDecomposition:
    """迭代 mask 输出；达到外层迭代上限仍保留有效结果与 converged=False。"""

    decomposition: Decomposition
    mask_frequencies: np.ndarray
    mask_variability: np.ndarray
    iterations: int
    converged: bool


def _first_mask(value):
    if isinstance(value, str):
        if value not in {"zc", "if"}:
            raise ValueError("首个 mask 方法必须为 zc、if 或频率数值")
        return getattr(_native.FirstMask, "ifrequency" if value == "if" else "zc"), 0.25
    return _native.FirstMask.explicit_frequency, float(value)


def _mask_options(
    mask_amp=1,
    mask_amp_mode="ratio_sig",
    mask_freqs="zc",
    mask_step_factor=2,
    max_imfs=9,
    sift_thresh=1e-8,
    nphases=4,
    imf_opts=None,
    envelope_opts=None,
    extrema_opts=None,
):
    options = _native.MaskOptions()
    options.imf = _imf_options(imf_opts)
    options.envelope = _envelope_options(envelope_opts, extrema_opts)
    options.mask_amp = np.atleast_1d(np.asarray(mask_amp, dtype=np.float64)).tolist()
    if mask_amp_mode not in {"abs", "ratio_sig", "ratio_imf"}:
        raise ValueError("mask_amp_mode 必须为 abs、ratio_sig 或 ratio_imf")
    options.amp_mode = getattr(_native.AmplitudeMode, mask_amp_mode)
    if isinstance(mask_freqs, (list, tuple, np.ndarray)):
        frequencies = np.asarray(mask_freqs, dtype=np.float64)
        if frequencies.ndim != 1 or not len(frequencies):
            raise ValueError("mask_freqs 必须是非空一维数组")
        options.mask_freqs = frequencies.tolist()
    else:
        options.first_mask, options.first_frequency = _first_mask(mask_freqs)
    options.mask_step_factor = mask_step_factor
    options.max_imfs = max_imfs
    options.nphases = nphases
    options.sift_thresh = sift_thresh
    return options


def _serial(nprocesses):
    if nprocesses != 1:
        raise ValueError("原生算法由上层调度并发，nprocesses 仅支持 1")


def get_next_imf_mask(
    signal,
    z,
    amp,
    nphases=4,
    nprocesses=1,
    imf_opts=None,
    envelope_opts=None,
    extrema_opts=None,
):
    """返回 [samples,1] mask IMF 和继续提取标志；相位循环全在 C++。"""
    _serial(nprocesses)
    values = _signal(signal)
    array, more, _, status = _native.get_next_imf_mask(
        values,
        z,
        amp,
        nphases,
        _imf_options(imf_opts),
        _envelope_options(envelope_opts, extrema_opts),
    )
    if status in {"iteration_limit", "numerical_failure"}:
        raise ConvergenceError(f"mask IMF 未完成: {status}")
    return array[:, None], more


def get_mask_freqs(signal, first_mask_mode="zc", imf_opts=None):
    """返回首个 mask 频率，单位 cycles/sample；支持过零、NHT 加权 IF 和显式值。"""
    method, frequency = _first_mask(first_mask_mode)
    try:
        return _native.get_mask_frequency(
            _signal(signal), method, frequency, _imf_options(imf_opts)
        )
    except _native.MaskConvergenceFailure as error:
        raise ConvergenceError(str(error)) from error


def mask_sift_detailed(signal, **kwargs):
    """返回独立拥有的 IMF 列和 mask 频率，避免二维布局复制。"""
    values = _signal(signal)
    try:
        raw, frequencies = _native.mask_sift(values, _mask_options(**kwargs))
    except _native.MaskConvergenceFailure as error:
        raise ConvergenceError(str(error)) from error
    return MaskDecomposition(_result(raw, len(values)), frequencies)


def mask_sift(
    signal,
    mask_amp=1,
    mask_amp_mode="ratio_sig",
    mask_freqs="zc",
    mask_step_factor=2,
    ret_mask_freq=False,
    max_imfs=9,
    sift_thresh=1e-8,
    nphases=4,
    nprocesses=1,
    verbose=None,
    imf_opts=None,
    envelope_opts=None,
    extrema_opts=None,
):
    """完整原生 mask sift；二维 IMF 输出做一次列组装，不追加残差列。"""
    _serial(nprocesses)
    result = mask_sift_detailed(
        signal,
        mask_amp=mask_amp,
        mask_amp_mode=mask_amp_mode,
        mask_freqs=mask_freqs,
        mask_step_factor=mask_step_factor,
        max_imfs=max_imfs,
        sift_thresh=sift_thresh,
        nphases=nphases,
        imf_opts=imf_opts,
        envelope_opts=envelope_opts,
        extrema_opts=extrema_opts,
    )
    _require_success(result.decomposition)
    array = result.decomposition.as_array()
    return (array, result.mask_frequencies) if ret_mask_freq else array


def iterated_mask_sift_detailed(
    signal,
    mask_0="zc",
    w_method="power",
    max_iter=15,
    iter_th=0.1,
    N_avg=1,
    exclude_edges=False,
    sample_rate=1.0,
    seed=None,
    max_imfs=6,
    mask_amp_mode="ratio_imf",
    **kwargs,
):
    """迭代与 NHT 全在 C++；Python 只准备随机初始 mask 和参数。

    频率输出沿用 emd 0.8.1：收敛平均分支为 Hz，max_iter 退出分支为归一化
    cycles/sample。收敛后在线聚合，不保存全部信号历史，也不执行平均完成后
    的额外空耗轮次。converged 区分外层收敛，不伪造 IMF 收敛状态。
    """
    values = _signal(signal)
    _serial(kwargs.pop("nprocesses", 1))
    kwargs.pop("verbose", None)
    if isinstance(mask_0, str) and mask_0 == "random":
        mask_0 = (
            np.random.RandomState(seed).randint(0, sample_rate / 4, size=max_imfs)
            / sample_rate
        )
    if isinstance(mask_0, (list, tuple, np.ndarray)):
        max_imfs = min(max_imfs, len(mask_0))
    options = _native.IteratedMaskOptions()
    options.mask = _mask_options(
        mask_freqs=mask_0,
        max_imfs=max_imfs,
        mask_amp_mode=mask_amp_mode,
        **kwargs,
    )
    options.max_iter = max_iter
    options.averages = N_avg
    options.iter_thresh = iter_th
    options.sample_rate = sample_rate
    options.exclude_edges = exclude_edges
    if w_method == "avg":
        options.weighted = False
    elif w_method == "amplitude":
        options.weight_power = 1.0
    elif w_method == "power":
        options.weight_power = 2.0
    elif isinstance(w_method, float):
        options.weight_power = w_method
    else:
        raise ValueError("w_method 必须为 amplitude、power、avg 或浮点指数")
    try:
        (raw, frequencies), variability, iterations, converged = (
            _native.iterated_mask_sift(values, options)
        )
    except _native.MaskConvergenceFailure as error:
        raise ConvergenceError(str(error)) from error
    return IteratedMaskDecomposition(
        _result(raw, len(values)), frequencies, variability, iterations, converged
    )


def iterated_mask_sift(signal, *, ret_mask_freq=False, **kwargs):
    """返回原生迭代 mask 的二维结果；外层上限退出保留参考的最后有效结果。"""
    result = iterated_mask_sift_detailed(signal, **kwargs)
    if result.decomposition.status == "numerical_failure" or (
        result.decomposition.status == "iteration_limit"
        and len(result.decomposition.iterations) > len(result.decomposition.components)
    ):
        _require_success(result.decomposition)
    array = result.decomposition.as_array()
    return (array, result.mask_frequencies) if ret_mask_freq else array


def _second_input(values):
    array = np.asarray(values, dtype=np.float64)
    if array.ndim == 1:
        array = array[:, None]
    if array.ndim != 2:
        raise ValueError("二层输入必须为 [samples, first_layer_imfs]")
    return array, [np.ascontiguousarray(array[:, i]) for i in range(array.shape[1])]


def _second_result(raw, length, first_layers):
    layers, depth = raw
    output = np.zeros((length, first_layers, depth), dtype=np.float64)
    for i, layer in enumerate(layers):
        result = _result(layer, length)
        _require_success(result)
        for j, column in enumerate(result.components):
            output[:, i, j] = column
    return output


def sift_second_layer(IA, sift_args=None):
    """原生 sift 的二层组合；3D 输出从独立 C++ 列组装一次。

    本地参考只在显式 sift_args 且 max_imfs 不超过输入列数、每次 sift
    输出不超过预分配深度时成功；超出此域明确报错，不悄悄截断残差。
    """
    array, columns = _second_input(IA)
    options = dict(sift_args or {})
    options.setdefault("max_imfs", array.shape[1])
    raw = _native.sift_second_layer(columns, _options(**options))
    return _second_result(raw, len(array), array.shape[1])


def mask_sift_second_layer(IA, mask_freqs, sift_args=None):
    """逐列使用截短 mask 列表做二层分解，数值与逐列调度均在 C++。"""
    array, columns = _second_input(IA)
    options = dict(sift_args or {})
    _serial(options.pop("nprocesses", 1))
    options.pop("verbose", None)
    options.pop("mask_freqs", None)
    options.setdefault("max_imfs", array.shape[1])
    frequencies = _signal(mask_freqs)
    raw = _native.mask_sift_second_layer(columns, frequencies, _mask_options(**options))
    return _second_result(raw, len(array), array.shape[1])
