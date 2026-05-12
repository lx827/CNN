"""
VMD（变分模态分解）降噪模块

VMD 将信号分解为若干个本征模态函数（IMF），
通过筛选高相关性 + 高峭度的 IMF 重构信号，实现降噪与特征增强。
"""
import numpy as np
from typing import Tuple, List


def vmd_decompose(
    signal: np.ndarray,
    K: int = 5,
    alpha: float = 2000,
    tau: float = 0.0,
    tol: float = 1e-7,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    VMD 分解

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
        omega: 中心频率
    """
    try:
        from vmdpy import VMD
    except ImportError:
        raise ImportError("vmdpy 未安装，请运行: pip install vmdpy")

    u, u_hat, omega = VMD(signal, alpha, tau, K, 0, 1, tol)
    return u, u_hat, omega


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
        降噪后的信号
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
        arr_z = arr - np.mean(arr)
        corr = np.abs(np.corrcoef(imf_z, arr_z)[0, 1]) if np.std(imf_z) > 0 and np.std(arr_z) > 0 else 0

        # 峭度
        kurt = np.mean(imf_z ** 4) / (np.var(imf_z) ** 2 + 1e-12) if np.var(imf_z) > 0 else 0

        if corr > corr_threshold or kurt > kurt_threshold:
            selected.append(imf)

    if not selected:
        # 如果没有选中任何 IMF，保留相关性最高的一个
        best_idx = 0
        best_corr = 0
        for i in range(u.shape[0]):
            imf = u[i, :]
            corr = np.abs(np.corrcoef(imf - np.mean(imf), arr - np.mean(arr))[0, 1])
            if corr > best_corr:
                best_corr = corr
                best_idx = i
        selected = [u[best_idx, :]]

    # 重构
    reconstructed = np.sum(selected, axis=0)
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
