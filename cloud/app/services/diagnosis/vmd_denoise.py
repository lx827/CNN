"""
VMD（变分模态分解）降噪模块

基于用户提供的内存优化版 VMD 实现，核心改进：
- 仅保留迭代所需的当前/前一次数据，不保存完整迭代历史
- 去除 vmdpy 依赖，避免其内部 3GB+ 的大数组分配
- 适配纯 CPU 环境（去除 cupy 依赖）

VMD 将信号分解为若干个本征模态函数（IMF），
通过筛选高相关性 + 高峭度的 IMF 重构信号，实现降噪与特征增强。
"""
import numpy as np
from typing import Tuple, List


def _vmd_core(
    f: np.ndarray,
    alpha: float,
    tau: float,
    K: int,
    DC: bool,
    init: int,
    tol: float,
    max_iter: int = 200,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    内存优化版 VMD 核心实现

    相比原版 vmdpy，内存占用从 O(Niter * T * K) 降到 O(T * K)。
    对于 81920 点、K=5 的信号，内存从 ~3GB 降到 ~20MB。
    """
    # 确保信号长度为偶数（避免镜像处理异常）
    if len(f) % 2:
        f = f[:-1]
    N = len(f)

    # 采样频率（归一化）
    fs = 1.0 / N

    # 信号镜像处理（减少边界效应）
    ltemp = N // 2
    f_mirr = np.concatenate([np.flip(f[:ltemp]), f, np.flip(f[-ltemp:])])
    T = len(f_mirr)

    # 时域和频域离散化
    t = np.arange(1, T + 1) / T
    freqs = t - 0.5 - (1.0 / T)

    # 最大迭代次数
    Niter = max_iter
    Alpha = alpha * np.ones(K, dtype=np.float64)

    # 构建并中心化频谱
    f_hat = np.fft.fftshift(np.fft.fft(f_mirr))
    f_hat_plus = f_hat.copy()
    f_hat_plus[:T // 2] = 0  # 只保留正频率部分

    # 初始化中心频率
    omega_curr = np.zeros(K, dtype=np.float64)
    omega_all = np.zeros((Niter, K), dtype=np.float64)

    if init == 1:
        for i in range(K):
            omega_curr[i] = (0.5 / K) * i
    elif init == 2:
        omega_curr = np.sort(
            np.exp(np.log(fs) + (np.log(0.5) - np.log(fs)) * np.random.rand(K))
        )
    else:
        omega_curr[:] = 0

    if DC:
        omega_curr[0] = 0
    omega_all[0, :] = omega_curr

    # 对偶变量
    lambda_prev = np.zeros(len(freqs), dtype=np.complex128)
    lambda_curr = np.zeros(len(freqs), dtype=np.complex128)

    # 迭代控制
    u_diff = tol + np.spacing(1)
    n = 0
    sum_uk = np.zeros(len(freqs), dtype=np.complex128)

    # 仅保留前一次/当前次的模态频谱
    prev_u_hat = np.zeros((len(freqs), K), dtype=np.complex128)
    curr_u_hat = np.zeros((len(freqs), K), dtype=np.complex128)

    # 主迭代循环
    while u_diff > tol and n < Niter - 1:
        # 第 0 个模态更新
        k = 0
        sum_uk = prev_u_hat[:, K - 1] + sum_uk - prev_u_hat[:, 0]

        curr_u_hat[:, k] = (f_hat_plus - sum_uk - lambda_prev / 2.0) / (
            1.0 + Alpha[k] * (freqs - omega_curr[k]) ** 2
        )

        if not DC:
            freq_slice = freqs[T // 2:T]
            u_slice = curr_u_hat[T // 2:T, k]
            denom = np.sum(np.abs(u_slice) ** 2)
            if denom > 1e-12:
                omega_curr[k] = np.dot(freq_slice, np.abs(u_slice) ** 2) / denom

        # 其余模态更新
        for k in range(1, K):
            sum_uk = curr_u_hat[:, k - 1] + sum_uk - prev_u_hat[:, k]

            curr_u_hat[:, k] = (f_hat_plus - sum_uk - lambda_prev / 2.0) / (
                1.0 + Alpha[k] * (freqs - omega_curr[k]) ** 2
            )

            freq_slice = freqs[T // 2:T]
            u_slice = curr_u_hat[T // 2:T, k]
            denom = np.sum(np.abs(u_slice) ** 2)
            if denom > 1e-12:
                omega_curr[k] = np.dot(freq_slice, np.abs(u_slice) ** 2) / denom

        # 对偶变量更新
        lambda_curr = lambda_prev + tau * (np.sum(curr_u_hat, axis=1) - f_hat_plus)

        # 收敛判断
        u_diff = np.spacing(1)
        for i in range(K):
            diff = curr_u_hat[:, i] - prev_u_hat[:, i]
            u_diff += (1.0 / T) * np.real(np.dot(diff, np.conj(diff)))
        u_diff = float(np.abs(u_diff))

        # 迭代状态更新
        n += 1
        omega_all[n, :] = omega_curr
        prev_u_hat, curr_u_hat = curr_u_hat, prev_u_hat
        lambda_prev = lambda_curr.copy()
        curr_u_hat.fill(0)

    # 后处理：信号重构
    final_u_hat_plus = prev_u_hat if n > 0 else curr_u_hat
    Niter = min(Niter, n + 1)
    omega = omega_all[:Niter, :]

    # 重构完整频谱
    idxs = np.flip(np.arange(1, T // 2 + 1))
    u_hat = np.zeros((T, K), dtype=np.complex128)
    u_hat[T // 2:T, :] = final_u_hat_plus[T // 2:T, :]
    u_hat[idxs, :] = np.conj(final_u_hat_plus[T // 2:T, :])
    u_hat[0, :] = np.conj(u_hat[-1, :])

    # 逆傅里叶变换得到时域信号
    u = np.zeros((K, T), dtype=np.float64)
    for k in range(K):
        u[k, :] = np.real(np.fft.ifft(np.fft.ifftshift(u_hat[:, k])))

    # 移除镜像部分，恢复原始信号长度
    u = u[:, T // 4:3 * T // 4]

    # 重新计算模态频谱（匹配原始信号长度）
    u_hat_out = np.zeros((u.shape[1], K), dtype=np.complex128)
    for k in range(K):
        u_hat_out[:, k] = np.fft.fftshift(np.fft.fft(u[k, :]))

    return u, u_hat_out, omega


def vmd_decompose(
    signal: np.ndarray,
    K: int = 5,
    alpha: float = 2000,
    tau: float = 0.0,
    tol: float = 1e-7,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    VMD 分解（内存优化版）

    Args:
        signal: 输入信号
        K: 模态数
        alpha: 惩罚因子
        tau: 噪声容差
        tol: 收敛容差

    Returns:
        (u, u_hat, omega)
        u: IMF 时域信号，形状 (K, N)
        u_hat: IMF 频域信号
        omega: 中心频率演化
    """
    arr = np.array(signal, dtype=np.float64)
    if len(arr) == 0:
        raise ValueError("输入信号为空")

    # 对于超长信号，先截断到最多 2 秒再做 VMD（防止计算过慢/内存不足）
    # 调用方（如 data_view）通常已截断到 5 秒，这里进一步截断到 2 秒
    # 因为 VMD 的复杂度是 O(N^2)，2 秒 @ 25600Hz = 51200 点已足够
    max_len = 51200  # 约 2 秒 @ 25600Hz
    if len(arr) > max_len:
        arr = arr[:max_len]

    return _vmd_core(arr, alpha, tau, K, DC=False, init=1, tol=tol, max_iter=200)


def vmd_denoise(
    signal: np.ndarray,
    K: int = 5,
    alpha: float = 2000,
    corr_threshold: float = 0.3,
    kurt_threshold: float = 3.0,
) -> np.ndarray:
    """
    VMD 降噪：分解后筛选有效 IMF 重构

    筛选规则：
    - 与原始信号的互相关系数 > corr_threshold
    - 峭度 > kurt_threshold（保留冲击成分）

    Args:
        signal: 输入信号
        K: 模态数
        alpha: 惩罚因子
        corr_threshold: 最小互相关系数
        kurt_threshold: 最小峭度（fisher=False，正态=3）

    Returns:
        降噪后的信号（长度与输入信号原始长度一致）
    """
    arr = np.array(signal, dtype=np.float64)
    N = len(arr)

    u, _, _ = vmd_decompose(arr, K=K, alpha=alpha)

    # 筛选 IMF
    selected = []
    for i in range(u.shape[0]):
        imf = u[i, :]
        # 去均值后计算相关性
        imf_z = imf - np.mean(imf)
        arr_z = arr[: len(imf)] - np.mean(arr[: len(imf)])
        corr = (
            np.abs(np.corrcoef(imf_z, arr_z)[0, 1])
            if np.std(imf_z) > 0 and np.std(arr_z) > 0
            else 0
        )

        # 峭度
        kurt = (
            np.mean(imf_z ** 4) / (np.var(imf_z) ** 2 + 1e-12)
            if np.var(imf_z) > 0
            else 0
        )

        if corr > corr_threshold or kurt > kurt_threshold:
            selected.append(imf)

    if not selected:
        # 如果没有选中任何 IMF，保留相关性最高的一个
        best_idx = 0
        best_corr = 0
        for i in range(u.shape[0]):
            imf = u[i, :]
            arr_seg = arr[: len(imf)]
            corr = np.abs(np.corrcoef(imf - np.mean(imf), arr_seg - np.mean(arr_seg))[0, 1])
            if corr > best_corr:
                best_corr = corr
                best_idx = i
        selected = [u[best_idx, :]]

    # 重构（注意 IMF 可能因截断而短于原始信号）
    reconstructed = np.sum(selected, axis=0)
    if len(reconstructed) < N:
        # 如果 VMD 截断了信号，用原始信号尾部补齐（通常不会发生，因为截断在分解前）
        out = np.zeros(N, dtype=np.float64)
        out[: len(reconstructed)] = reconstructed
        return out
    return reconstructed[:N]


def vmd_select_impact_mode(
    signal: np.ndarray,
    K: int = 5,
    alpha: float = 2000,
) -> Tuple[np.ndarray, dict]:
    """
    VMD 分解并自动选择最佳冲击模态

    选择标准：峭度最大的 IMF

    Returns:
        (最佳 IMF, 各模态信息列表)
    """
    arr = np.array(signal, dtype=np.float64)
    u, _, omega = vmd_decompose(arr, K=K, alpha=alpha)

    modes = []
    best_idx = 0
    best_kurt = 0

    for i in range(u.shape[0]):
        imf = u[i, :]
        kurt = np.mean((imf - np.mean(imf)) ** 4) / (np.var(imf) ** 2 + 1e-12)
        modes.append({
            "index": i,
            "center_freq_hz": float(omega[-1, i]) if omega.shape[0] > 0 else 0,
            "kurtosis": float(kurt),
        })
        if kurt > best_kurt:
            best_kurt = kurt
            best_idx = i

    return u[best_idx, :], {"modes": modes, "best_index": best_idx, "best_kurtosis": float(best_kurt)}
