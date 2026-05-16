"""
EMD / CEEMDAN 经验模态分解降噪模块

与现有 VMD 形成互补：
- VMD 基于频域变分优化，需预设模态数 K；
- EMD/CEEMDAN 基于时域局部特征尺度，自适应确定模态数，
  更适合转速剧烈波动的变速工况（CW数据集）。

参考: Huang et al. (1998) EMD; Torres et al. (2011) CEEMDAN
"""
import numpy as np
from scipy.interpolate import CubicSpline
from typing import Tuple, List, Dict


def _find_extrema(signal: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """定位局部极大值、极小值和过零点"""
    diff = np.diff(signal)
    maxima_idx = np.where((diff[:-1] > 0) & (diff[1:] <= 0))[0] + 1
    minima_idx = np.where((diff[:-1] < 0) & (diff[1:] >= 0))[0] + 1
    zero_cross = np.where(np.diff(np.sign(signal)))[0]
    return maxima_idx, minima_idx, zero_cross


def _compute_envelope_mean(signal: np.ndarray, max_idx: np.ndarray, min_idx: np.ndarray) -> np.ndarray:
    """用三次样条插值构造上下包络并求平均"""
    t = np.arange(len(signal))
    if len(max_idx) < 2 or len(min_idx) < 2:
        return np.zeros_like(signal)
    upper = CubicSpline(max_idx, signal[max_idx])(t)
    lower = CubicSpline(min_idx, signal[min_idx])(t)
    return (upper + lower) / 2.0


def _is_imf(signal: np.ndarray, max_idx: np.ndarray, min_idx: np.ndarray, zero_idx: np.ndarray) -> bool:
    """IMF判定：极值点与过零点数量差不超过1，且局部均值近似为零"""
    n_extrema = len(max_idx) + len(min_idx)
    n_zero = len(zero_idx)
    if abs(n_extrema - n_zero) > 1:
        return False
    m = _compute_envelope_mean(signal, max_idx, min_idx)
    return np.mean(np.abs(m)) < 1e-3 * (np.max(signal) - np.min(signal))


def emd_decompose(
    signal: np.ndarray,
    max_imfs: int = 10,
    sd_threshold: float = 0.25,
    max_sifts: int = 100,
) -> Tuple[List[np.ndarray], np.ndarray]:
    """
    基础 EMD 分解

    Args:
        signal: 输入信号
        max_imfs: 最大IMF数量
        sd_threshold: 筛分停止SD准则阈值
        max_sifts: 单个IMF最大筛分次数

    Returns:
        (imfs_list, residual)
    """
    arr = np.array(signal, dtype=np.float64)
    imfs = []
    residue = arr.copy()

    for _ in range(max_imfs):
        if len(residue) < 4:
            break
        h = residue.copy()
        for _ in range(max_sifts):
            max_idx, min_idx, zero_idx = _find_extrema(h)
            if len(max_idx) < 2 or len(min_idx) < 2:
                break
            if _is_imf(h, max_idx, min_idx, zero_idx):
                break
            m = _compute_envelope_mean(h, max_idx, min_idx)
            h_new = h - m
            denom = np.sum(h ** 2) + 1e-12
            sd = np.sum((h - h_new) ** 2) / denom
            h = h_new
            if sd < sd_threshold:
                break
        imfs.append(h)
        residue = residue - h
        max_idx, min_idx, _ = _find_extrema(residue)
        if len(max_idx) <= 1 and len(min_idx) <= 1:
            break

    return imfs, residue


def ceemdan_decompose(
    signal: np.ndarray,
    max_imfs: int = 10,
    ensemble_size: int = 50,
    noise_std: float = 0.2,
    max_sifts: int = 100,
    sd_threshold: float = 0.25,
) -> Tuple[List[np.ndarray], np.ndarray]:
    """
    CEEMDAN 分解（完备集成经验模态分解）

    相比EMD解决了模态混叠；相比EEMD无直流残留。
    计算成本较高，建议仅在 full-analysis 模式启用。
    """
    arr = np.array(signal, dtype=np.float64)
    N = len(arr)
    sigma_x = float(np.std(arr))

    noise_realizations = [
        np.random.normal(0, sigma_x * noise_std, N)
        for _ in range(ensemble_size)
    ]

    imfs = [np.zeros(N, dtype=np.float64) for _ in range(max_imfs)]
    residue = arr.copy()

    for k in range(max_imfs):
        current_noise_std = noise_std * np.std(residue) if k > 0 else noise_std * sigma_x
        mode_accum = np.zeros(N, dtype=np.float64)
        for noise in noise_realizations:
            trial = residue + current_noise_std * noise if k > 0 else arr + current_noise_std * noise
            trial_imfs, _ = emd_decompose(trial, max_imfs=1, max_sifts=max_sifts, sd_threshold=sd_threshold)
            if trial_imfs:
                mode_accum += trial_imfs[0]
            else:
                mode_accum += trial

        imf_k = mode_accum / ensemble_size
        imfs[k] = imf_k
        residue = residue - imf_k if k > 0 else arr - imf_k

        max_idx, min_idx, _ = _find_extrema(residue)
        if len(max_idx) <= 1 and len(min_idx) <= 1:
            imfs = imfs[:k + 1]
            break

    return imfs, residue


def emd_denoise(
    signal: np.ndarray,
    method: str = "ceemdan",
    corr_threshold: float = 0.35,
    kurt_threshold: float = 3.5,
    max_imfs: int = 8,
) -> Tuple[np.ndarray, Dict]:
    """
    EMD/CEEMDAN 降噪统一入口

    筛选策略：保留高相关或高峭度IMF，丢弃低频趋势和高频噪声IMF。
    """
    arr = np.array(signal, dtype=np.float64)
    N = len(arr)

    if method == "ceemdan":
        imfs, residue = ceemdan_decompose(arr, max_imfs=max_imfs)
    else:
        imfs, residue = emd_decompose(arr, max_imfs=max_imfs)

    selected = []
    info = []

    for i, imf in enumerate(imfs):
        imf_z = imf - np.mean(imf)
        arr_z = arr[:len(imf)] - np.mean(arr[:len(imf)])
        corr = (
            np.abs(np.corrcoef(imf_z, arr_z)[0, 1])
            if np.std(imf_z) > 0 and np.std(arr_z) > 0 else 0.0
        )
        kurt = float(np.mean(imf_z ** 4) / (np.var(imf_z) ** 2 + 1e-12))
        info.append({
            "index": i,
            "corr": round(corr, 4),
            "kurtosis": round(kurt, 4),
            "selected": False,
        })

        if 0 < i < len(imfs) - 1:
            if corr > corr_threshold or kurt > kurt_threshold:
                selected.append(imf)
                info[-1]["selected"] = True

    if not selected:
        mid_imfs = [(i, imf) for i, imf in enumerate(imfs) if 0 < i < len(imfs) - 1]
        if mid_imfs:
            best = max(mid_imfs, key=lambda t: np.mean((t[1] - np.mean(t[1]))**4))
            selected = [best[1]]
            info[best[0]]["selected"] = True

    reconstructed = np.sum(selected, axis=0) if selected else np.zeros(N)
    if len(reconstructed) < N:
        out = np.zeros(N)
        out[:len(reconstructed)] = reconstructed
        reconstructed = out

    kurt_before = float(np.mean(arr**4) / (np.var(arr)**2 + 1e-12))
    kurt_after = float(np.mean(reconstructed**4) / (np.var(reconstructed)**2 + 1e-12))

    return reconstructed, {
        "method": method,
        "n_imfs": len(imfs),
        "imfs_info": info,
        "kurtosis_before": round(kurt_before, 4),
        "kurtosis_after": round(kurt_after, 4),
    }
