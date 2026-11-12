"""
LMS 自适应滤波模块

包含：
- 标准 LMS（Least Mean Squares）
- NLMS（归一化 LMS）
- VSSLMS（变步长 LMS）

单通道振动信号场景下，参考信号采用延迟构造法：
将原始信号延迟 M 个采样点作为参考噪声输入，
滤波器从主通道中减去与参考相关的成分，保留故障冲击。

docs/算法原理.md §4.2.3 参考：适用于存在独立参考噪声通道的场景，
单通道时用延迟信号构造参考。
"""

import numpy as np
from cnn_compute import diagnostic as native_diagnostic
from typing import Dict, Tuple, Optional


def _run(signal, method, filter_len, step_size, delay, max_iter, **options):
    """计算在原生核；业务元信息留在服务层，max_iter限制实际权重更新次数。"""
    arr = np.asarray(signal, dtype=np.float64)
    if arr.ndim != 1 or not np.all(np.isfinite(arr)):
        raise ValueError("自适应滤波输入必须为有限一维数组")
    if (
        isinstance(filter_len, bool)
        or not isinstance(filter_len, int)
        or filter_len < 1
    ):
        raise ValueError("滤波器长度必须为正整数")
    if isinstance(delay, bool) or not isinstance(delay, int) or delay < 0:
        raise ValueError("延迟必须为非负整数")
    if max_iter is not None and (
        isinstance(max_iter, bool) or not isinstance(max_iter, int) or max_iter < 1
    ):
        raise ValueError("max_iter必须为正整数或None")
    name = method.upper()
    if len(arr) < filter_len + delay + 10:
        return arr.copy(), {"method": name, "error": "signal_too_short"}
    output = native_diagnostic.adaptive_filter(
        arr,
        method,
        filter_length=filter_len,
        step_size=step_size,
        delay=delay,
        max_updates=max_iter or 0,
        **options,
    )
    before, after = np.var(arr), np.var(output)
    metadata = {
        "method": name,
        "filter_len": filter_len,
        "delay": delay,
        "kurtosis_before": round(float(np.mean(arr**4) / (before**2 + 1e-12)), 4),
        "kurtosis_after": round(float(np.mean(output**4) / (after**2 + 1e-12)), 4),
        "noise_reduction_ratio": round(float(before / (after + 1e-12)), 4),
    }
    if method == "vsslms":
        metadata.update(
            mu_init=step_size, alpha=options["alpha"], gamma=options["gamma"]
        )
    else:
        metadata["step_size"] = step_size
    return output, metadata


def lms_filter(
    signal: np.ndarray,
    filter_len: int = 32,
    step_size: float = 0.01,
    delay: int = 1,
    max_iter: Optional[int] = None,
) -> Tuple[np.ndarray, Dict]:
    """延迟参考LMS，max_iter为最多权重更新次数，之后固定权重继续滤波。"""
    return _run(signal, "lms", filter_len, step_size, delay, max_iter)


def nlms_filter(
    signal: np.ndarray,
    filter_len: int = 32,
    step_size: float = 0.5,
    delay: int = 1,
    max_iter: Optional[int] = None,
) -> Tuple[np.ndarray, Dict]:
    """归一化LMS，更新分母为参考能量+1e-6；max_iter限制更新次数。"""
    return _run(signal, "nlms", filter_len, step_size, delay, max_iter)


def vsslms_filter(
    signal: np.ndarray,
    filter_len: int = 32,
    mu_init: float = 0.01,
    alpha: float = 0.97,
    gamma: float = 5e-5,
    mu_min: float = 1e-6,
    mu_max: float = 0.05,
    delay: int = 1,
    max_iter: Optional[int] = None,
) -> Tuple[np.ndarray, Dict]:
    """VSS-LMS：mu=clip(alpha*mu+gamma*e²)，max_iter限制实际权重更新次数。"""
    return _run(
        signal,
        "vsslms",
        filter_len,
        mu_init,
        delay,
        max_iter,
        alpha=alpha,
        gamma=gamma,
        minimum_step=mu_min,
        maximum_step=mu_max,
    )
