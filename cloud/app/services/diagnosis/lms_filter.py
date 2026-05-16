"""
LMS 自适应滤波模块

包含：
- 标准 LMS（Least Mean Squares）
- NLMS（归一化 LMS）
- VSSLMS（变步长 LMS）

单通道振动信号场景下，参考信号采用延迟构造法：
将原始信号延迟 M 个采样点作为参考噪声输入，
滤波器从主通道中减去与参考相关的成分，保留故障冲击。

ALGORITHMS.md §4.2.3 参考：适用于存在独立参考噪声通道的场景，
单通道时用延迟信号构造参考。
"""
import numpy as np
from typing import Dict, Tuple, Optional


def lms_filter(
    signal: np.ndarray,
    filter_len: int = 32,
    step_size: float = 0.01,
    delay: int = 1,
    max_iter: Optional[int] = None,
) -> Tuple[np.ndarray, Dict]:
    """
    标准 LMS 自适应滤波

    算法流程：
    1. 构造参考信号 u(n) = x(n - delay)
    2. 初始化滤波器系数 w = 0
    3. 迭代更新：w(n+1) = w(n) + μ·e(n)·u(n)
       其中 e(n) = x(n) - w^T·u(n)

    Args:
        signal: 输入信号
        filter_len: FIR 滤波器长度
        step_size: 步长 μ，通常 0.001~0.05
        delay: 参考信号延迟（采样点数），默认 1
        max_iter: 最大迭代次数，None 则等于信号长度

    Returns:
        (滤波后信号, 元信息字典)
    """
    arr = np.array(signal, dtype=np.float64)
    N = len(arr)
    if N < filter_len + delay + 10:
        return arr.copy(), {"method": "LMS", "error": "signal_too_short"}

    iterations = max_iter or N

    # 构造参考信号：延迟 M 个采样点
    ref = np.zeros(N, dtype=np.float64)
    if delay >= N:
        return arr.copy(), {"method": "LMS", "error": "delay_exceeds_signal_length"}
    ref[delay:] = arr[:N - delay]

    # 初始化
    w = np.zeros(filter_len, dtype=np.float64)
    output = np.zeros(N, dtype=np.float64)

    for n in range(filter_len, N):
        # 参考信号向量 u(n) = [u(n), u(n-1), ..., u(n-L+1)]
        u_vec = ref[n - filter_len + 1:n + 1]
        # 估计输出 y(n) = w^T * u(n)
        y_n = np.dot(w, u_vec)
        # 误差 e(n) = x(n) - y(n)
        e_n = arr[n] - y_n
        output[n] = e_n
        # LMS 更新：w(n+1) = w(n) + μ * e(n) * u(n)
        w = w + step_size * e_n * u_vec

    # 前 filter_len 个点直接用原信号（无法构造完整参考向量）
    output[:filter_len] = arr[:filter_len]

    # 去均值
    output = output - np.mean(output)

    # 计算指标
    kurt_before = float(np.mean(arr ** 4) / (np.var(arr) ** 2 + 1e-12))
    kurt_after = float(np.mean(output ** 4) / (np.var(output) ** 2 + 1e-12))
    noise_reduction = float(np.var(arr) / (np.var(output) + 1e-12))

    return output, {
        "method": "LMS",
        "filter_len": filter_len,
        "step_size": step_size,
        "delay": delay,
        "kurtosis_before": round(kurt_before, 4),
        "kurtosis_after": round(kurt_after, 4),
        "noise_reduction_ratio": round(noise_reduction, 4),
    }


def nlms_filter(
    signal: np.ndarray,
    filter_len: int = 32,
    step_size: float = 0.5,
    delay: int = 1,
    max_iter: Optional[int] = None,
) -> Tuple[np.ndarray, Dict]:
    """
    NLMS（归一化 LMS）自适应滤波

    与标准 LMS 的区别：步长按输入功率归一化，防止发散。
    更新公式：w(n+1) = w(n) + μ / (||u(n)||² + ε) · e(n) · u(n)

    Args:
        signal: 输入信号
        filter_len: FIR 滤波器长度
        step_size: 归一化步长 μ，通常 0.1~1.0
        delay: 参考信号延迟
        max_iter: 最大迭代次数

    Returns:
        (滤波后信号, 元信息字典)
    """
    arr = np.array(signal, dtype=np.float64)
    N = len(arr)
    if N < filter_len + delay + 10:
        return arr.copy(), {"method": "NLMS", "error": "signal_too_short"}

    iterations = max_iter or N
    epsilon = 1e-6  # 防止 ||u||² = 0 时除零

    # 构造参考信号
    ref = np.zeros(N, dtype=np.float64)
    ref[delay:] = arr[:N - delay]

    w = np.zeros(filter_len, dtype=np.float64)
    output = np.zeros(N, dtype=np.float64)

    for n in range(filter_len, N):
        u_vec = ref[n - filter_len + 1:n + 1]
        y_n = np.dot(w, u_vec)
        e_n = arr[n] - y_n
        output[n] = e_n
        # NLMS 更新：步长按输入功率归一化
        u_power = np.dot(u_vec, u_vec) + epsilon
        w = w + (step_size / u_power) * e_n * u_vec

    output[:filter_len] = arr[:filter_len]
    output = output - np.mean(output)

    kurt_before = float(np.mean(arr ** 4) / (np.var(arr) ** 2 + 1e-12))
    kurt_after = float(np.mean(output ** 4) / (np.var(output) ** 2 + 1e-12))
    noise_reduction = float(np.var(arr) / (np.var(output) + 1e-12))

    return output, {
        "method": "NLMS",
        "filter_len": filter_len,
        "step_size": step_size,
        "delay": delay,
        "kurtosis_before": round(kurt_before, 4),
        "kurtosis_after": round(kurt_after, 4),
        "noise_reduction_ratio": round(noise_reduction, 4),
    }


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
    """
    VSSLMS（变步长 LMS）自适应滤波

    步长随误差自适应调整：
    μ(n) = α·μ(n-1) + γ·e²(n)
    兼顾收敛速度（大误差时步长增大）与稳态误差（小误差时步长减小）。

    Args:
        signal: 输入信号
        filter_len: FIR 滤波器长度
        mu_init: 初始步长
        alpha: 步长记忆系数（0~1），越大则步长变化越慢
        gamma: 步长增长系数
        mu_min: 步长下限
        mu_max: 步长上限
        delay: 参考信号延迟
        max_iter: 最大迭代次数

    Returns:
        (滤波后信号, 元信息字典)
    """
    arr = np.array(signal, dtype=np.float64)
    N = len(arr)
    if N < filter_len + delay + 10:
        return arr.copy(), {"method": "VSSLMS", "error": "signal_too_short"}

    iterations = max_iter or N

    # 构造参考信号
    ref = np.zeros(N, dtype=np.float64)
    ref[delay:] = arr[:N - delay]

    w = np.zeros(filter_len, dtype=np.float64)
    output = np.zeros(N, dtype=np.float64)
    mu = mu_init

    for n in range(filter_len, N):
        u_vec = ref[n - filter_len + 1:n + 1]
        y_n = np.dot(w, u_vec)
        e_n = arr[n] - y_n
        output[n] = e_n

        # VSSLMS 步长更新
        mu = alpha * mu + gamma * e_n ** 2
        mu = np.clip(mu, mu_min, mu_max)

        # LMS 更新（使用自适应步长）
        w = w + mu * e_n * u_vec

    output[:filter_len] = arr[:filter_len]
    output = output - np.mean(output)

    kurt_before = float(np.mean(arr ** 4) / (np.var(arr) ** 2 + 1e-12))
    kurt_after = float(np.mean(output ** 4) / (np.var(output) ** 2 + 1e-12))
    noise_reduction = float(np.var(arr) / (np.var(output) + 1e-12))

    return output, {
        "method": "VSSLMS",
        "filter_len": filter_len,
        "mu_init": mu_init,
        "alpha": alpha,
        "gamma": gamma,
        "delay": delay,
        "kurtosis_before": round(kurt_before, 4),
        "kurtosis_after": round(kurt_after, 4),
        "noise_reduction_ratio": round(noise_reduction, 4),
    }