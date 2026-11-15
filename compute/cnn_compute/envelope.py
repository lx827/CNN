"""独立极值插值包络模块；不依赖 EMD 筛分。"""

import numpy as np
from numpy.typing import NDArray

from ._native import envelope as _native
from ._native import interpolation as _interpolation

Options = _native.Options


def _options(envelope_opts=None, extrema_opts=None) -> Options:
    options = Options()
    for name, value in (envelope_opts or {}).items():
        if name != "interp_method":
            raise TypeError(f"不支持的包络参数: {name}")
        method = "pchip" if value == "mono_pchip" else value
        if method not in {"splrep", "pchip", "cubic"}:
            raise ValueError(f"不支持的插值方法: {method!r}")
        options.interpolation = getattr(_interpolation.Method, method)
    for name, value in (extrema_opts or {}).items():
        if name == "method":
            if value not in {"rilling", "numpypad"}:
                raise ValueError(f"不支持的延拓方法: {value!r}")
            options.padding = getattr(_native.Padding, value)
        elif name in {"pad_width", "parabolic_extrema"}:
            setattr(options, name, value)
        elif name in {"loc_pad_opts", "mag_pad_opts"} and value is None:
            pass  # 采用参考默认的 odd-reflect 位置和端点幅值延拓。
        else:
            raise TypeError(f"不支持的极值参数: {name}")
    return options


def find_extrema(signal, *, maxima=True, parabolic=False):
    """返回独立 (位置, 幅值)；严格局部极值，平台不算极值。"""
    values = np.ascontiguousarray(signal, dtype=np.float64)
    return _native.find_extrema(values, maxima, parabolic)


def extrema_envelopes(signal, *, envelope_opts=None, extrema_opts=None):
    """返回拥有型 (上包络, 下包络)，极值不足返回 None。

    输入只读借用，原生计算释放 GIL；下一次调用不会覆盖本次结果。
    """
    values = np.ascontiguousarray(signal, dtype=np.float64)
    return _native.extrema_envelopes(values, _options(envelope_opts, extrema_opts))


def combined_envelope(
    signal, *, envelope_opts=None, extrema_opts=None
) -> NDArray[np.float64] | None:
    """对绝对值信号的峰插值，默认 numpypad；返回独立数组或 None。"""
    if extrema_opts is None:
        extrema_opts = {"method": "numpypad"}
    values = np.ascontiguousarray(signal, dtype=np.float64)
    return _native.combined_envelope(values, _options(envelope_opts, extrema_opts))
