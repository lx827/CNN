"""
盲源分离模块（Blind Source Separation）

包含：
- FastICA 独立成分分析
- 单通道 VMD+ICA：用 VMD 将单通道扩展为多通道，再执行 ICA 分离

ALGORITHMS.md §4.2.4 参考：
单通道盲分离采用 EEMD+ICA 或相空间重构+ICA。
本项目使用 VMD（已实现且内存优化）替代 EEMD，
将单通道振动信号分解为多个 IMF 作为多通道输入，再执行 FastICA。

用途：从物理上分离噪声源与故障源，而非简单滤除频带，
避免损伤故障成分。适合多源叠加的复合故障场景。
"""
import numpy as np
from typing import Dict, Tuple, Optional, List


def fast_ica(
    X: np.ndarray,
    n_components: Optional[int] = None,
    max_iter: int = 200,
    tol: float = 1e-6,
    whiten: bool = True,
) -> Tuple[np.ndarray, Dict]:
    """
    FastICA 独立成分分析

    基于 Hyvärinen (1999) 的固定点算法，使用 negentropy 近似：
    G(u) = log(cos(a·u))，a ≈ 1.5

    算法流程：
    1. 中心化 + 白化（PCA）
    2. 对每个独立成分，迭代求解分离向量使 negentropy 最大化
    3. Gram-Schmidt 去相关（逐成分估计模式）

    Args:
        X: 输入矩阵 (n_samples, n_features)，每列一个观测通道
        n_components: 要提取的独立成分数，None 则取 min(n_features, 5)
        max_iter: 每成分最大迭代次数
        tol: 收敛容差
        whiten: 是否先白化

    Returns:
        (独立成分矩阵 (n_samples, n_components), 元信息字典)
    """
    X = np.array(X, dtype=np.float64)
    n_samples, n_features = X.shape

    if n_components is None:
        n_components = min(n_features, 5)
    n_components = min(n_components, n_features)

    # Step 1: 中心化
    X = X - np.mean(X, axis=0)

    # Step 2: 白化（PCA）
    if whiten:
        cov = np.dot(X.T, X) / n_samples
        try:
            eigenvalues, eigenvectors = np.linalg.eigh(cov)
        except np.linalg.LinAlgError:
            # 协方差矩阵奇异，加小正则项
            cov += 1e-6 * np.eye(n_features)
            eigenvalues, eigenvectors = np.linalg.eigh(cov)

        # 降维：只保留前 n_components 个主成分
        idx = np.argsort(eigenvalues)[::-1][:n_components]
        D = np.diag(1.0 / np.sqrt(eigenvalues[idx] + 1e-12))
        E = eigenvectors[:, idx]
        # 白化矩阵
        K = np.dot(D, E.T)  # (n_components, n_features)
        X_white = np.dot(X, K.T)  # (n_samples, n_components)
    else:
        X_white = X[:, :n_components] if n_components < n_features else X
        K = np.eye(n_components)

    # Step 3: FastICA 逐成分估计（deflation 模式）
    W = np.zeros((n_components, n_components), dtype=np.float64)
    a = 1.5  # negentropy 近似参数

    for i in range(n_components):
        # 初始化分离向量（随机）
        w = np.random.randn(n_components)
        w = w / np.linalg.norm(w)

        for _ in range(max_iter):
            # negentropy 近似 G'(u) = -a·tan(a·u)，G''(u) = -a²·(1/cos(a·u))²
            # 但 tan/cos 在 a=1.5 时可能溢出，改用鲁棒近似：
            # G(u) = u³（kurtosis近似），G'(u) = 3u²，G''(u) = 6u
            # 使用更稳定的 tanh 近似：G(u) = tanh(u)，G'(u) = 1-tanh²(u)
            u = np.dot(X_white, w)
            tanh_u = np.tanh(u)
            g = tanh_u  # G'(w^T·x)
            g_prime = 1.0 - tanh_u ** 2  # G''(w^T·x)

            w_new = (np.dot(X_white.T, g) / n_samples
                     - np.dot(np.mean(g_prime), w))

            # Gram-Schmidt 去相关
            if i > 0:
                proj = np.dot(w_new, W[:i].T)
                w_new = w_new - np.dot(proj, W[:i])

            w_new = w_new / (np.linalg.norm(w_new) + 1e-12)

            # 收敛判断
            if abs(np.dot(w_new, w)) > 1.0 - tol:
                w = w_new
                break
            w = w_new

        W[i, :] = w

    # 计算独立成分
    S = np.dot(X_white, W.T)  # (n_samples, n_components)

    # 各成分的峭度（独立性指标）
    kurtoses = []
    for j in range(n_components):
        s = S[:, j]
        k = float(np.mean(s ** 4) / (np.var(s) ** 2 + 1e-12) - 3.0)
        kurtoses.append(k)

    # 各成分与原信号的互相关（帮助识别故障成分）
    correlations = []
    for j in range(n_components):
        s = S[:, j]
        for f_idx in range(n_features):
            corr = float(np.corrcoef(s, X[:, f_idx])[0, 1])
            correlations.append({"component": j, "feature": f_idx, "correlation": round(corr, 4)})

    return S, {
        "method": "FastICA",
        "n_components": n_components,
        "kurtoses": [round(k, 4) for k in kurtoses],
        "correlations": correlations[:n_components * min(n_features, 5)],
        "whiten": whiten,
    }


def vmd_ica_separation(
    signal: np.ndarray,
    fs: float,
    K: int = 5,
    alpha: int = 2000,
    max_ica_iter: int = 200,
    ica_tol: float = 1e-6,
) -> Dict:
    """
    单通道 VMD+ICA 盲源分离

    算法流程：
    1. VMD 分解 → 得到 K 个 IMF
    2. 将 IMF 组成多通道矩阵 (N, K)
    3. FastICA 分离 → 得到 K 个独立成分
    4. 按峭度选择含故障信息的独立成分
    5. 重构去噪信号（保留故障成分 + 相关性高的成分）

    Args:
        signal: 输入信号
        fs: 采样率
        K: VMD 分解模态数
        alpha: VMD 惩罚因子
        max_ica_iter: ICA 最大迭代次数
        ica_tol: ICA 收敛容差

    Returns:
        {
            "denoised_signal": np.ndarray,
            "fault_component": np.ndarray,  # 最可能的故障成分
            "n_modes": int,
            "vmd_kurtoses": List[float],
            "ica_kurtoses": List[float],
            "selected_component_index": int,
            "info": Dict,
        }
    """
    from .vmd_denoise import _vmd_core

    arr = np.array(signal, dtype=np.float64)
    N = len(arr)

    # 信号截断（内存保护，2G服务器）
    max_samples = int(fs * 5)
    if N > max_samples:
        arr = arr[:max_samples]
        N = len(arr)

    # Step 1: VMD 分解
    try:
        u, u_hat, omega = _vmd_core(arr, alpha=alpha, tau=0.0, K=K, DC=0,
                                      init=1, tol=1e-6, max_iter=200)
    except Exception as exc:
        return {
            "denoised_signal": arr.copy(),
            "fault_component": arr.copy(),
            "n_modes": 0,
            "error": str(exc),
            "method": "VMD+ICA",
        }

    # u: (K, T) 各模态函数
    n_modes = u.shape[0]
    if n_modes < 2:
        return {
            "denoised_signal": arr.copy(),
            "fault_component": arr.copy(),
            "n_modes": n_modes,
            "vmd_kurtoses": [],
            "ica_kurtoses": [],
            "selected_component_index": 0,
            "info": {"method": "VMD+ICA", "note": "insufficient_modes"},
        }

    # 各 IMF 峭度
    vmd_kurtoses = []
    for i in range(n_modes):
        imf = u[i, :]
        k = float(np.mean(imf ** 4) / (np.var(imf) ** 2 + 1e-12) - 3.0)
        vmd_kurtoses.append(round(k, 4))

    # Step 2: 组成多通道矩阵 (N, K)
    X_vmd = u.T  # (N, K)

    # Step 3: FastICA 分离
    try:
        S_ica, ica_info = fast_ica(
            X_vmd,
            n_components=n_modes,
            max_iter=max_ica_iter,
            tol=ica_tol,
        )
    except Exception as exc:
        # ICA 失败时退回 VMD 筛选
        best_idx = int(np.argmax(np.abs(vmd_kurtoses)))
        fault_component = u[best_idx, :]
        denoised = arr.copy()
        return {
            "denoised_signal": denoised,
            "fault_component": fault_component,
            "n_modes": n_modes,
            "vmd_kurtoses": vmd_kurtoses,
            "ica_kurtoses": [],
            "selected_component_index": best_idx,
            "info": {"method": "VMD+ICA", "ica_error": str(exc)},
        }

    ica_kurtoses = ica_info["kurtoses"]

    # Step 4: 按峭度选择最可能的故障成分
    abs_kurt = np.abs(ica_kurtoses)
    best_component_idx = int(np.argmax(abs_kurt))
    fault_component = S_ica[:, best_component_idx]

    # Step 5: 重构信号
    # 保留峭度 > 3 的 ICA 成分（含冲击特征）+ 与原信号相关性 > 0.3 的成分
    selected_indices = []
    for j in range(n_modes):
        if abs_kurt[j] > 3.0:
            selected_indices.append(j)
    if not selected_indices:
        selected_indices = [best_component_idx]

    # 用 ICA 成分的逆变换重构
    # S = X_white @ W^T → X_white = S @ W → X_reconstructed = X_white @ K
    # 简化：仅用选中的成分重构，通过线性组合
    # 但 ICA 分离后成分的尺度可能改变，用 VMD IMF 的相关成分重构更稳定
    # 实际工程中：将选中的 ICA 成分通过逆变换映射回原信号空间
    # 简化方案：直接用选中的 ICA 成分之和作为增强后的故障信号
    denoised = np.sum(S_ica[:, selected_indices], axis=1)
    denoised = denoised - np.mean(denoised)

    # 对齐长度
    if len(denoised) < N:
        denoised = np.pad(denoised, (0, N - len(denoised)))
    elif len(denoised) > N:
        denoised = denoised[:N]
    fault_component = fault_component[:N]

    return {
        "denoised_signal": denoised,
        "fault_component": fault_component,
        "n_modes": n_modes,
        "vmd_kurtoses": vmd_kurtoses,
        "ica_kurtoses": ica_kurtoses,
        "selected_component_index": best_component_idx,
        "selected_indices": selected_indices,
        "info": {**ica_info, "method": "VMD+ICA"},
    }