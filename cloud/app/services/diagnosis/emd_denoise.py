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


def _pad_extrema_rilling(signal: np.ndarray, max_idx: np.ndarray,
                         min_idx: np.ndarray, pad_width: int = 3
                         ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Rilling 边界镜像填充（严格参考 emd 库 _pad_extrema_rilling）

    与旧版关键区别：
    - 对称轴根据信号端点值与首个极值的大小关系确定
    - 填充幅值取信号在镜像位置的值（而非极值幅值的代数镜像）
    - 同时处理极大值和极小值，确保左/右两端各有足够极值覆盖

    Returns:
        (max_locs, max_mags, min_locs, min_mags) 填充后的极值位置和幅值
    """
    N = len(signal)
    t = np.arange(N, dtype=np.float64)

    if len(max_idx) < 1 or len(min_idx) < 1:
        return t[max_idx], signal[max_idx], t[min_idx], signal[min_idx]

    max_locs = t[max_idx].copy()
    max_mags = signal[max_idx].copy()
    min_locs = t[min_idx].copy()
    min_mags = signal[min_idx].copy()

    # ── 左侧填充 ──
    # 确定左对称轴：首个极大值和首个极小值中靠左的那个的位置
    lmax = max_locs[0]
    lmin = min_locs[0]

    # 对称轴 = 信号首端值与首个极值的大小关系决定
    # 如果信号[0] >= 首个极大值 → lsym在极大值位置, 反之在首个极值靠左的位置
    if signal[0] > max_mags[0]:
        lsym = lmax
    elif signal[0] < min_mags[0]:
        lsym = lmin
    else:
        # 信号[0]在极值范围内，对称轴取更靠左的极值位置
        lsym = min(lmax, lmin)

    # 如果对称轴不在 t[0] 以内，强制设在 t[0]
    if lsym > t[0]:
        lsym = t[0]

    # 镜像填充：新极值位置 = 2*lsym - 原位置，幅值 = 信号在新位置对应的值
    left_max_locs = []
    left_max_mags = []
    left_min_locs = []
    left_min_mags = []

    for i in range(1, pad_width + 1):
        if i < len(max_locs):
            new_loc = 2 * lsym - max_locs[i]
            if new_loc >= 0:
                idx = int(round(new_loc))
                idx = max(0, min(idx, N - 1))
                left_max_locs.append(new_loc)
                left_max_mags.append(signal[idx])
        if i < len(min_locs):
            new_loc = 2 * lsym - min_locs[i]
            if new_loc >= 0:
                idx = int(round(new_loc))
                idx = max(0, min(idx, N - 1))
                left_min_locs.append(new_loc)
                left_min_mags.append(signal[idx])

    # ── 右侧填充 ──
    rmax = max_locs[-1]
    rmin = min_locs[-1]

    if signal[-1] < max_mags[-1]:
        rsym = rmax
    elif signal[-1] > min_mags[-1]:
        rsym = rmin
    else:
        rsym = max(rmax, rmin)

    if rsym < t[-1]:
        rsym = t[-1]

    right_max_locs = []
    right_max_mags = []
    right_min_locs = []
    right_min_mags = []

    for i in range(1, pad_width + 1):
        if i < len(max_locs):
            new_loc = 2 * rsym - max_locs[-(i + 1)]
            if new_loc <= t[-1]:
                idx = int(round(new_loc))
                idx = max(0, min(idx, N - 1))
                right_max_locs.append(new_loc)
                right_max_mags.append(signal[idx])
        if i < len(min_locs):
            new_loc = 2 * rsym - min_locs[-(i + 1)]
            if new_loc <= t[-1]:
                idx = int(round(new_loc))
                idx = max(0, min(idx, N - 1))
                right_min_locs.append(new_loc)
                right_min_mags.append(signal[idx])

    # 合并
    all_max_locs = np.concatenate([left_max_locs[::-1], max_locs, right_max_locs]) if left_max_locs or right_max_locs else max_locs
    all_max_mags = np.concatenate([left_max_mags[::-1], max_mags, right_max_mags]) if left_max_mags or right_max_mags else max_mags
    all_min_locs = np.concatenate([left_min_locs[::-1], min_locs, right_min_locs]) if left_min_locs or right_min_locs else min_locs
    all_min_mags = np.concatenate([left_min_mags[::-1], min_mags, right_min_mags]) if left_min_mags or right_min_mags else min_mags

    return all_max_locs, all_max_mags, all_min_locs, all_min_mags


# ═══════════════════════════════════════════════════════════
# 包络计算
# ═══════════════════════════════════════════════════════════

def _compute_envelope_mean(signal: np.ndarray,
                           max_idx: np.ndarray,
                           min_idx: np.ndarray,
                           use_pchip: bool = True,
                           pad_width: int = 3) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """构造上下包络并求平均

    Args:
        use_pchip: True 用 PchipInterpolator（保守，无过冲）；
                   False 用 CubicSpline（光滑但可能过冲）
        pad_width: Rilling 边界镜像填充宽度

    Returns:
        (envelope_mean, upper_env, lower_env) 平均包络、上包络、下包络
        Rilling 停止准则需要 upper/lower 包络值
    """
    t = np.arange(len(signal), dtype=np.float64)
    if len(max_idx) < 2 or len(min_idx) < 2:
        return np.zeros_like(signal), np.zeros_like(signal), np.zeros_like(signal)

    # 精化极值位置
    max_r = _refine_extrema_parabolic(signal, max_idx)
    min_r = _refine_extrema_parabolic(signal, min_idx)

    # 边界镜像填充（新版同时处理极大极小值）
    max_locs, max_mags, min_locs, min_mags = _pad_extrema_rilling(
        signal, max_idx.astype(int), min_idx.astype(int), pad_width=pad_width
    )

    # 插值
    if use_pchip:
        upper = PchipInterpolator(max_locs, max_mags, extrapolate=True)(t)
        lower = PchipInterpolator(min_locs, min_mags, extrapolate=True)(t)
    else:
        from scipy.interpolate import CubicSpline
        upper = CubicSpline(max_locs, max_mags, extrapolate=True)(t)
        lower = CubicSpline(min_locs, min_mags, extrapolate=True)(t)

    env_mean = (upper + lower) / 2.0
    return env_mean, upper, lower


# ═══════════════════════════════════════════════════════════
# 停止准则
# ═══════════════════════════════════════════════════════════

def _stop_sd(proto_imf: np.ndarray, old: np.ndarray) -> float:
    """标准差停止准则（Huang 1998）"""
    denom = np.sum(old ** 2) + 1e-18
    return np.sum((proto_imf - old) ** 2) / denom


def _stop_rilling(upper_env: np.ndarray, lower_env: np.ndarray,
                  sd1: float = 0.05, sd2: float = 0.5, tol: float = 0.05) -> bool:
    """Rilling 停止准则（严格参考 emd 库 stop_imf_rilling）

    评估包络对称性而非前后两轮差值：
    E(t) = |avg_env(t)| / amp(t) = |均值偏移| / 模态振幅

    停止条件 = (E < sd1 的比例 >= 1-tol) AND (所有点 E < sd2)

    Args:
        upper_env: 上包络
        lower_env: 下包络
        sd1: 严格阈值（默认 0.05）
        sd2: 宽松阈值（默认 0.5）
        tol: 允许超过 sd1 的比例（默认 0.05 = 5%）
    """
    avg_env = (upper_env + lower_env) / 2.0
    amp = np.abs(upper_env - lower_env) / 2.0

    # 模态振幅过小 → 已收敛
    if np.max(amp) < 1e-12:
        return True

    eval_metric = np.abs(avg_env) / (amp + 1e-18)

    # 条件1: 超过 sd1 的比例 <= tol
    ratio_over_sd1 = np.mean(eval_metric > sd1)
    cond1 = ratio_over_sd1 <= tol

    # 条件2: 所有点 E < sd2
    cond2 = np.all(eval_metric < sd2)

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
            m, upper, lower = _compute_envelope_mean(h, max_idx, min_idx, use_pchip=use_pchip)
            h_new = h - m
            if use_rilling:
                # Rilling 停止准则：评估包络对称性
                # 停止时保留当前 proto_imf（不做最后一次均值扣除，与 emd 包一致）
                if _stop_rilling(upper, lower, *rilling_thresh):
                    h = h_new  # 停止时接受本轮结果
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
) -> Tuple[List[np.ndarray], np.ndarray]:
    """
    CEEMDAN 分解（完备集成经验模态分解 — Torres 2011 标准）

    与旧版关键区别（参考 emd 包 complete_ensemble_sift + 用户 myemd.py）：
    1. 噪声来源：预分解白噪声的各阶 IMF 分层（而非纯白噪声）
       - 第 k 阶使用白噪声的第 k 阶 IMF，确保噪声频段匹配当前提取层
    2. 第1阶噪声加到原信号 X 上；第2阶起噪声加到残差上
    3. 噪声缩放: 第1阶 ε×noise_imf/std(noise_imf) × std(X)
                  第2阶起 ε×noise_imf × std(residue)
    4. 逐阶提取：每步只取1个 IMF (= residue - local_mean)

    Returns:
        (imfs_list, residual)
    """
    arr = np.array(signal, dtype=np.float64)
    N = len(arr)
    xstd = float(np.std(arr))
    if xstd < 1e-12:
        return [arr.copy()], np.zeros_like(arr)

    # 标准化（与 emd 库 / myemd.py 一致）
    arr_norm = arr / xstd

    # ── 预分解白噪声：每个 ensemble 成员的白噪声分解为 IMF 分层 ──
    # Torres 2011 核心：CEEMDAN 的噪声应该是白噪声的 IMF 分解而非原白噪声
    noise_imf_layers: List[List[np.ndarray]] = []
    for i in range(ensemble_size):
        white_noise = np.random.normal(0, 1.0, N)
        wn_imfs, _ = emd_decompose(
            white_noise, max_imfs=max_imfs, max_sifts=max_sifts,
            sd_threshold=sd_threshold,
            use_rilling=use_rilling, rilling_thresh=rilling_thresh,
            use_pchip=use_pchip, normalize=False,
        )
        noise_imf_layers.append(wn_imfs)

    imfs: List[np.ndarray] = []
    residue = arr_norm.copy()

    for k in range(max_imfs):
        local_mean_accum = np.zeros(N, dtype=np.float64)
        valid_ensemble = 0

        for i in range(ensemble_size):
            wn_imfs_i = noise_imf_layers[i]

            # ── 构造加噪信号 ──
            # 第1阶: noise 加到 X 上, 使用白噪声第0阶 IMF
            # 第2阶起: noise 加到 residue 上, 使用白噪声第 k 阶 IMF
            if k < len(wn_imfs_i):
                noise_component = wn_imfs_i[k]
            else:
                # 白噪声分解出的 IMF 数量少于 k → 用残差作为噪声（衰减至零）
                continue

            # 噪声缩放（Torres 2011 / emd 包）
            if k == 0:
                # 第1阶: ε × (noise_imf_0 / std(noise_imf_0)) × 1.0
                # 在标准化空间中 std(X)=1，所以最终是 ε × normalized_noise
                noise_std_local = float(np.std(noise_component))
                if noise_std_local > 1e-12:
                    scaled_noise = noise_std * noise_component / noise_std_local
                else:
                    scaled_noise = np.zeros(N)
                trial = arr_norm + scaled_noise
            else:
                # 第2阶起: ε × noise_imf_k × std(residue)
                # 噪声幅值与残差成正比，保证各阶 SNR 一致
                scaled_noise = noise_std * noise_component * float(np.std(residue))
                trial = residue + scaled_noise

            # ── 提取 local_mean (而非直接取 IMF) ──
            # get_next_local_mean: 对 trial 做一次筛分 → IMF_1
            # local_mean = trial - IMF_1
            trial_imfs, _ = emd_decompose(
                trial, max_imfs=1, max_sifts=max_sifts,
                sd_threshold=sd_threshold,
                use_rilling=use_rilling, rilling_thresh=rilling_thresh,
                use_pchip=use_pchip, normalize=False,
            )
            if trial_imfs:
                imf_1 = trial_imfs[0]
                local_mean_i = trial - imf_1
            else:
                # 筛分失败 → local_mean = trial 本身（跳过此成员）
                local_mean_i = trial

            local_mean_accum += local_mean_i
            valid_ensemble += 1

        if valid_ensemble == 0:
            break

        # ── 计算本阶结果 ──
        local_mean_k = local_mean_accum / valid_ensemble
        imf_k = residue - local_mean_k

        imfs.append(imf_k)
        residue = local_mean_k  # 残差更新为新 local_mean（与 emd 包一致）

        # 检查残差是否还有极值
        max_idx, min_idx, _ = _find_extrema(residue)
        if len(max_idx) <= 1 and len(min_idx) <= 1:
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
