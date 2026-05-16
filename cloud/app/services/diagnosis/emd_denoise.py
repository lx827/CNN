"""
EMD / CEEMDAN 经验模态分解降噪模块

与现有 VMD 形成互补：
- VMD 基于频域变分优化，需预设模态数 K；
- EMD/CEEMDAN 基于时域局部特征尺度，自适应确定模态数，
  更适合转速剧烈波动的变速工况（CW数据集）。

优化点（参考 emd 库 + 用户版 myemd.py）：
1. 边界镜像填充（Rilling 方法）提高边界包络精度
2. Pchip 插值替代 CubicSpline，抑制包络过冲
3. 抛物线插值精化极值位置
4. 信号标准化处理，稳定噪声幅值
5. 预生成噪声数组复用，减少 CEEMDAN 随机数开销
6. Rilling 停止准则作为可选，比纯 SD 更稳健

参考: Huang et al. (1998) EMD; Torres et al. (2011) CEEMDAN;
      emd package (https://emd.readthedocs.io)
"""
import numpy as np
from scipy.interpolate import PchipInterpolator
from typing import Tuple, List, Dict


# ═══════════════════════════════════════════════════════════
# 极值检测与精化
# ═══════════════════════════════════════════════════════════

def _find_extrema(signal: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """定位局部极大值、极小值和过零点"""
    diff = np.diff(signal)
    maxima_idx = np.where((diff[:-1] > 0) & (diff[1:] <= 0))[0] + 1
    minima_idx = np.where((diff[:-1] < 0) & (diff[1:] >= 0))[0] + 1
    zero_cross = np.where(np.diff(np.sign(signal)))[0]
    return maxima_idx, minima_idx, zero_cross


def _refine_extrema_parabolic(signal: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """抛物线插值精化极值位置（参考 emd 库 parabolic_extrema）"""
    if len(idx) == 0:
        return idx.astype(float)
    refined = []
    for i in idx:
        if i == 0 or i >= len(signal) - 1:
            refined.append(float(i))
            continue
        a = signal[i - 1]
        b = signal[i]
        c = signal[i + 1]
        denom = 2 * (a - 2 * b + c)
        if abs(denom) < 1e-18:
            refined.append(float(i))
        else:
            offset = (a - c) / denom
            refined.append(float(i) + offset)
    return np.array(refined)


def _pad_extrema_rilling(t: np.ndarray, locs: np.ndarray, mags: np.ndarray,
                         pad_width: int = 2) -> Tuple[np.ndarray, np.ndarray]:
    """Rilling 边界镜像填充（参考 emd 库 get_padded_extrema）

    在信号两端镜像对称地补充虚拟极值点，使包络插值在边界处更稳定。
    """
    if len(locs) < 2:
        return locs.copy(), mags.copy()
    # 左侧镜像
    left_locs = []
    left_mags = []
    for i in range(1, pad_width + 1):
        if i <= len(locs):
            mirror_loc = 2 * locs[0] - locs[i]
            left_locs.append(mirror_loc)
            left_mags.append(mags[0] + (mags[0] - mags[i]))
    # 右侧镜像
    right_locs = []
    right_mags = []
    for i in range(1, pad_width + 1):
        if i <= len(locs):
            mirror_loc = 2 * locs[-1] - locs[-(i + 1)]
            right_locs.append(mirror_loc)
            right_mags.append(mags[-1] + (mags[-1] - mags[-(i + 1)]))
    all_locs = np.concatenate([left_locs[::-1], locs, right_locs])
    all_mags = np.concatenate([left_mags[::-1], mags, right_mags])
    return all_locs, all_mags


# ═══════════════════════════════════════════════════════════
# 包络计算
# ═══════════════════════════════════════════════════════════

def _compute_envelope_mean(signal: np.ndarray,
                           max_idx: np.ndarray,
                           min_idx: np.ndarray,
                           use_pchip: bool = True,
                           pad_width: int = 2) -> np.ndarray:
    """构造上下包络并求平均

    Args:
        use_pchip: True 用 PchipInterpolator（保守，无过冲）；
                   False 用 CubicSpline（光滑但可能过冲）
        pad_width: Rilling 边界镜像填充宽度
    """
    t = np.arange(len(signal), dtype=np.float64)
    if len(max_idx) < 2 or len(min_idx) < 2:
        return np.zeros_like(signal)

    # 精化极值位置
    max_r = _refine_extrema_parabolic(signal, max_idx)
    min_r = _refine_extrema_parabolic(signal, min_idx)

    # 边界镜像填充
    max_locs, max_mags = _pad_extrema_rilling(t, max_r, signal[max_idx], pad_width=pad_width)
    min_locs, min_mags = _pad_extrema_rilling(t, min_r, signal[min_idx], pad_width=pad_width)

    # 插值
    if use_pchip:
        upper = PchipInterpolator(max_locs, max_mags, extrapolate=True)(t)
        lower = PchipInterpolator(min_locs, min_mags, extrapolate=True)(t)
    else:
        from scipy.interpolate import CubicSpline
        upper = CubicSpline(max_locs, max_mags, extrapolate=True)(t)
        lower = CubicSpline(min_locs, min_mags, extrapolate=True)(t)

    return (upper + lower) / 2.0


# ═══════════════════════════════════════════════════════════
# 停止准则
# ═══════════════════════════════════════════════════════════

def _stop_sd(proto_imf: np.ndarray, old: np.ndarray) -> float:
    """标准差停止准则（Huang 1998）"""
    denom = np.sum(old ** 2) + 1e-18
    return np.sum((proto_imf - old) ** 2) / denom


def _stop_rilling(proto_imf: np.ndarray, old: np.ndarray,
                  sd1: float = 0.05, sd2: float = 0.5, alpha: float = 0.05) -> bool:
    """Rilling 停止准则（参考 emd 库）

    计算评估函数 E = |proto_imf - old| / mode_amplitude
    对 (1-alpha) 比例的数据要求 E < sd1，其余要求 E < sd2
    """
    mode_amp = np.max(proto_imf) - np.min(proto_imf)
    if mode_amp < 1e-12:
        return True
    eval_fun = np.abs(proto_imf - old) / mode_amp
    sorted_eval = np.sort(eval_fun)
    n = len(sorted_eval)
    cutoff = int(np.floor((1 - alpha) * n))
    if cutoff < 1:
        cutoff = 1
    cond1 = np.all(sorted_eval[:cutoff] < sd1)
    cond2 = np.all(sorted_eval[cutoff:] < sd2)
    return cond1 and cond2


# ═══════════════════════════════════════════════════════════
# 基础 EMD 分解
# ═══════════════════════════════════════════════════════════

def emd_decompose(
    signal: np.ndarray,
    max_imfs: int = 10,
    max_sifts: int = 100,
    sd_threshold: float = 0.25,
    use_rilling: bool = False,
    rilling_thresh: Tuple[float, float, float] = (0.05, 0.5, 0.05),
    use_pchip: bool = True,
    normalize: bool = False,
) -> Tuple[List[np.ndarray], np.ndarray]:
    """
    基础 EMD 分解

    Args:
        signal: 输入信号
        max_imfs: 最大IMF数量
        max_sifts: 单个IMF最大筛分次数
        sd_threshold: SD准则阈值（use_rilling=False 时生效）
        use_rilling: 是否使用 Rilling 停止准则（更稳健）
        rilling_thresh: (sd1, sd2, alpha)
        use_pchip: 包络插值方法
        normalize: 是否对信号做标准化（std=1）后再分解

    Returns:
        (imfs_list, residual)
    """
    arr = np.array(signal, dtype=np.float64)
    xstd = float(np.std(arr))
    if normalize and xstd > 1e-12:
        arr = arr / xstd

    imfs = []
    residue = arr.copy()

    for _ in range(max_imfs):
        if len(residue) < 4:
            break
        h = residue.copy()
        for _ in range(max_sifts):
            max_idx, min_idx, _ = _find_extrema(h)
            if len(max_idx) < 2 or len(min_idx) < 2:
                break
            m = _compute_envelope_mean(h, max_idx, min_idx, use_pchip=use_pchip)
            h_new = h - m
            if use_rilling:
                if _stop_rilling(h_new, h, *rilling_thresh):
                    break
            else:
                sd = _stop_sd(h_new, h)
                if sd < sd_threshold:
                    break
            h = h_new
        imfs.append(h)
        residue = residue - h
        max_idx, min_idx, _ = _find_extrema(residue)
        if len(max_idx) <= 1 and len(min_idx) <= 1:
            break

    # 恢复原始幅值
    if normalize and xstd > 1e-12:
        imfs = [imf * xstd for imf in imfs]
        residue = residue * xstd

    return imfs, residue


# ═══════════════════════════════════════════════════════════
# CEEMDAN 分解
# ═══════════════════════════════════════════════════════════

def ceemdan_decompose(
    signal: np.ndarray,
    max_imfs: int = 10,
    ensemble_size: int = 50,
    noise_std: float = 0.2,
    max_sifts: int = 100,
    sd_threshold: float = 0.25,
    use_rilling: bool = False,
    rilling_thresh: Tuple[float, float, float] = (0.05, 0.5, 0.05),
    use_pchip: bool = True,
    precompute_noise: bool = True,
) -> Tuple[List[np.ndarray], np.ndarray]:
    """
    CEEMDAN 分解（完备集成经验模态分解）

    优化（参考用户 myemd.py + Torres 2011）：
    1. 信号标准化后再分解，结果恢复原始幅值
    2. 预生成噪声数组复用，避免每轮重新生成随机数
    3. 噪声幅值按残余标准差自适应缩放（Torres 标准）

    Args:
        precompute_noise: 是否预生成噪声并复用（减少随机数开销）

    Returns:
        (imfs_list, residual)
    """
    arr = np.array(signal, dtype=np.float64)
    N = len(arr)
    xstd = float(np.std(arr))
    if xstd < 1e-12:
        return [arr.copy()], np.zeros_like(arr)

    # 标准化（参考用户 myemd.py）
    arr_norm = arr / xstd

    # 预生成噪声（标准化单位）
    if precompute_noise:
        noise_realizations = [
            np.random.normal(0, 1.0, N)
            for _ in range(ensemble_size)
        ]
    else:
        noise_realizations = None

    imfs = [np.zeros(N, dtype=np.float64) for _ in range(max_imfs)]
    residue = arr_norm.copy()

    for k in range(max_imfs):
        # Torres 2011: β_k = ε * std(residue)
        beta = noise_std * float(np.std(residue))
        if beta < 1e-18:
            beta = noise_std

        mode_accum = np.zeros(N, dtype=np.float64)
        for i in range(ensemble_size):
            if precompute_noise:
                noise = noise_realizations[i]
            else:
                noise = np.random.normal(0, 1.0, N)

            if k == 0:
                trial = arr_norm + beta * noise
            else:
                trial = residue + beta * noise

            trial_imfs, _ = emd_decompose(
                trial, max_imfs=1, max_sifts=max_sifts,
                sd_threshold=sd_threshold,
                use_rilling=use_rilling, rilling_thresh=rilling_thresh,
                use_pchip=use_pchip, normalize=False,
            )
            if trial_imfs:
                mode_accum += trial_imfs[0]
            else:
                mode_accum += trial

        imf_k = mode_accum / ensemble_size
        imfs[k] = imf_k
        residue = residue - imf_k

        max_idx, min_idx, _ = _find_extrema(residue)
        if len(max_idx) <= 1 and len(min_idx) <= 1:
            imfs = imfs[:k + 1]
            break

    # 恢复原始幅值
    imfs = [imf * xstd for imf in imfs]
    residue = residue * xstd

    return imfs, residue


# ═══════════════════════════════════════════════════════════
# 峭度计算（统一为 excess kurtosis）
# ═══════════════════════════════════════════════════════════

def _excess_kurtosis(x: np.ndarray) -> float:
    """Excess kurtosis（正态分布 = 0），与 scipy.stats.kurtosis 一致"""
    arr = np.asarray(x, dtype=np.float64)
    if len(arr) < 4:
        return 0.0
    mu = np.mean(arr)
    sigma2 = np.var(arr)
    if sigma2 < 1e-18:
        return 0.0
    return float(np.mean((arr - mu) ** 4) / (sigma2 ** 2) - 3.0)


# ═══════════════════════════════════════════════════════════
# EMD 降噪统一入口
# ═══════════════════════════════════════════════════════════

def emd_denoise(
    signal: np.ndarray,
    method: str = "ceemdan",
    corr_threshold: float = 0.35,
    kurt_threshold: float = 3.5,
    max_imfs: int = 8,
    ensemble_size: int = 50,
    noise_std: float = 0.2,
    use_rilling: bool = False,
    use_pchip: bool = True,
    precompute_noise: bool = True,
) -> Tuple[np.ndarray, Dict]:
    """
    EMD/CEEMDAN 降噪统一入口

    筛选策略：保留高相关或高峭度IMF，丢弃低频趋势和高频噪声IMF。
    """
    arr = np.array(signal, dtype=np.float64)
    N = len(arr)

    if method == "ceemdan":
        imfs, residue = ceemdan_decompose(
            arr, max_imfs=max_imfs,
            ensemble_size=ensemble_size, noise_std=noise_std,
            use_rilling=use_rilling,
            use_pchip=use_pchip,
            precompute_noise=precompute_noise,
        )
    else:
        imfs, residue = emd_decompose(
            arr, max_imfs=max_imfs,
            use_rilling=use_rilling,
            use_pchip=use_pchip,
            normalize=True,
        )

    selected = []
    info = []

    for i, imf in enumerate(imfs):
        imf_z = imf - np.mean(imf)
        arr_z = arr[:len(imf)] - np.mean(arr[:len(imf)])
        corr = (
            np.abs(np.corrcoef(imf_z, arr_z)[0, 1])
            if np.std(imf_z) > 0 and np.std(arr_z) > 0 else 0.0
        )
        kurt = _excess_kurtosis(imf_z)
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
            best = max(mid_imfs, key=lambda t: _excess_kurtosis(t[1]))
            selected = [best[1]]
            info[best[0]]["selected"] = True

    reconstructed = np.sum(selected, axis=0) if selected else np.zeros(N)
    if len(reconstructed) < N:
        out = np.zeros(N)
        out[:len(reconstructed)] = reconstructed
        reconstructed = out

    kurt_before = _excess_kurtosis(arr)
    kurt_after = _excess_kurtosis(reconstructed)

    return reconstructed, {
        "method": method,
        "n_imfs": len(imfs),
        "imfs_info": info,
        "kurtosis_before": round(kurt_before, 4),
        "kurtosis_after": round(kurt_after, 4),
    }
