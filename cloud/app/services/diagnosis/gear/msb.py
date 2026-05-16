"""
调制信号双谱（MSB）残余边频带分析模块

MSB（Modulation Signal Bispectrum）利用三阶谱估计提取二次相位耦合（QPC）信息，
从边频带中分离故障调制分量，不受制造/装配误差干扰。

核心理论（Guo, Xu, Tian et al.）：
- 传统同相边频带受制造/装配误差影响大，健康状态下也可能显著
- 残余边频带（residual sidebands）来自多行星轮啮合的不完全叠加，
  值较小但受误差影响弱
- 在特征切片 f_c = 2*f_mesh ± f_carrier 处，
  残余边频带的 MSB 幅值随故障程度单调增长

MSB 定义：
    B(f_c, f_Δ) = E[X(f_c+f_Δ) · conj(X(f_c-f_Δ)) · X(f_c)]

其中 X(f) 为信号 x(t) 的傅里叶系数，E 为分段平均。

实现方法：
- 分段 FFT 估计（类似 Welch 法），将信号分成 n_segments 段
- 对每段计算三阶谱分量，然后求段间平均得到 MSB 估计
- MSB-SE 切片：对 f_Δ 积分得到 MSB_SE(f_c) = Σ|B(f_c, f_Δ)| over f_Δ
- 在特征切片位置计算 SNR 相对于背景

典型应用场景：
- 行星齿轮箱太阳轮故障检测（f_c = 2*f_mesh - f_carrier）
- 行星齿轮箱行星轮故障检测（f_c = 2*f_mesh - f_planet）
- 定轴齿轮箱边频带调制分析
"""
import numpy as np
from scipy.fft import rfft, rfftfreq
from typing import Dict, Optional


def msb_residual_sideband_analysis(
    signal: np.ndarray,
    fs: float,
    mesh_freq: float,
    carrier_freq: float = None,
    n_segments: int = 8,
) -> Dict:
    """
    MSB 残余边频带分析（调制信号双谱）

    使用分段 FFT 估计方法计算调制信号双谱（MSB），在特征切片位置提取
    残余边频带信息，计算太阳轮/行星轮故障 MSB-SNR 和残余边频带比。

    MSB 定义：
        B(f_c, f_Δ) = E[X(f_c+f_Δ) · conj(X(f_c-f_Δ)) · X(f_c)]
    其中 X(f) 为信号 x(t) 的傅里叶系数，E 为分段平均算子。

    MSB-SE（Sideband Evaluator）切片：
        MSB_SE(f_c) = Σ |B(f_c, f_Δ)| over f_Δ
    对 f_Δ 方向积分，得到沿 f_c 轴的投影切片，反映各 f_c 位置的调制耦合强度。

    残余边频带法的关键优势：
    - 传统同相边频带（f_c = f_mesh + f_carrier）受制造/装配误差影响
    - 残余边频带（f_c = 2*f_mesh - f_carrier）仅反映故障调制，
      健康状态下幅值极低，故障时单调增长
    - MSB 的相位耦合特性进一步抑制随机噪声和线性干扰

    Args:
        signal: 振动信号（一维 numpy 数组）
        fs: 采样率 Hz
        mesh_freq: 啮合频率 Hz（齿轮啮合基频）
        carrier_freq: carrier 转频 Hz（行星齿轮箱 carrier 频率），
                       None 时自动按 mesh_freq 估算
        n_segments: 分段数（默认 8），影响估计平滑度和频率分辨率

    Returns:
        {
            "msb_se_slice": np.ndarray,    # MSB-SE 切片（沿 f_c 轴的投影）
            "msb_fc_axis": np.ndarray,     # 切片频率轴 Hz
            "msb_spectrum": np.ndarray,     # MSB 二维切片（f_c, f_Δ）
            "msb_delta_axis": np.ndarray,  # f_Δ 轴 Hz
            "sun_fault_msb_snr": float,    # 太阳轮故障切片 MSB-SNR
            "planet_fault_msb_snr": float, # 行星轮故障切片 MSB-SNR
            "residual_sideband_ratio": float,  # 残余边频带比
            "sun_slice_freq": float,       # 太阳轮故障切片频率 Hz
            "planet_slice_freq": float,    # 行星轮故障切片频率 Hz
            "n_segments": int,
            "seg_len": int,
            "df": float,                   # 频率分辨率 Hz
            "valid": bool,
        }
    """
    arr = np.array(signal, dtype=np.float64)
    N = len(arr)

    # --- 异常输入安全处理 ---
    if N < 64 or fs <= 0 or mesh_freq <= 0:
        return {
            "valid": False,
            "reason": "invalid_input",
            "msb_se_slice": np.array([]),
            "msb_fc_axis": np.array([]),
            "msb_spectrum": np.array([]),
            "msb_delta_axis": np.array([]),
            "sun_fault_msb_snr": 0.0,
            "planet_fault_msb_snr": 0.0,
            "residual_sideband_ratio": 0.0,
            "sun_slice_freq": 0.0,
            "planet_slice_freq": 0.0,
            "n_segments": n_segments,
            "seg_len": 0,
            "df": 0.0,
        }

    # --- carrier_freq 估算 ---
    # 若未提供 carrier_freq，按行星齿轮箱典型比率估算
    # 行星箱 carrier_order = z_sun/(z_sun+z_ring)，典型 0.2~0.3
    # mesh_order = z_ring*z_sun/(z_sun+z_ring)，典型 ~22
    # carrier_freq = mesh_freq / mesh_order * carrier_order
    # 但更常见的做法：carrier_freq = mesh_freq 的低频分量
    if carrier_freq is None or carrier_freq <= 0:
        # 估算 carrier_freq：取 mesh_freq / 100 作为默认
        # 这适用于大多数行星齿轮箱（carrier_order ~ 0.2）
        carrier_freq = mesh_freq / 100.0

    # --- 分段 FFT 估计 ---
    # 将信号分成 n_segments 段（50% 重叠），每段做 FFT
    seg_len = N // n_segments
    if seg_len < 32:
        # 数据太短，减少分段数
        n_segments = max(2, N // 64)
        seg_len = N // n_segments

    # 实际分段数（考虑 50% 重叠）
    overlap = seg_len // 2
    step = seg_len - overlap
    n_actual_segments = max(1, (N - seg_len) // step + 1)

    df = fs / seg_len  # 每段的频率分辨率
    freq_axis = rfftfreq(seg_len, 1.0 / fs)  # 每段的频率轴
    n_freq = len(freq_axis)

    # --- MSB 三阶谱估计 ---
    # B(f_c, f_Δ) = E[X_k(f_c+f_Δ) · conj(X_k(f_c-f_Δ)) · X_k(f_c)]
    # f_c: carrier 频率轴（调制频率位置）
    # f_Δ: 边频带偏移频率轴

    # 频率轴范围限制：f_c 和 f_Δ 必须使得 f_c+f_Δ 和 f_c-f_Δ 都在有效范围内
    f_max = freq_axis[-1]

    # MSB 二维数组：行索引对应 f_c，列索引对应 f_Δ
    # f_c 轴范围：0 到 f_max/2（避免 f_c+f_Δ 超出范围）
    # f_Δ 轴范围：0 到 f_max/2
    n_fc = n_freq // 2  # f_c 的频率索引范围
    n_delta = n_freq // 2  # f_Δ 的频率索引范围

    msb_sum = np.zeros((n_fc, n_delta), dtype=np.complex128)

    for k in range(n_actual_segments):
        start = k * step
        end = start + seg_len
        if end > N:
            break

        # 对当前段做加窗 FFT
        segment = arr[start:end]
        window = np.hanning(seg_len)
        segment_windowed = segment * window

        X_k = rfft(segment_windowed)  # 当前段的 FFT

        # 计算三阶谱分量
        # 对每个 f_c 和 f_Δ，计算 B(f_c, f_Δ)
        for i_fc in range(n_fc):
            for i_delta in range(min(n_delta, n_freq - i_fc)):
                idx_sum = i_fc + i_delta   # f_c + f_Δ 的频率索引
                idx_diff = i_fc - i_delta   # f_c - f_Δ 的频率索引
                idx_c = i_fc                # f_c 的频率索引

                # f_c - f_Δ 可能为负索引，对应负频率
                # 使用 full FFT 而非 rfft 来获取负频率分量
                # 但 rfft 只有正频率，利用实信号性质：
                # X(-f) = conj(X(f))
                if idx_diff >= 0:
                    X_diff = X_k[idx_diff]   # 正频率
                else:
                    # 负频率：X(-f) = conj(X(f))，|idx_diff| = -idx_diff
                    abs_idx = -idx_diff
                    if abs_idx < n_freq:
                        X_diff = np.conj(X_k[abs_idx])
                    else:
                        continue

                # 确保所有索引在有效范围内
                if idx_sum >= n_freq or idx_c >= n_freq:
                    continue

                # MSB 三阶谱分量
                msb_sum[i_fc, i_delta] += X_k[idx_sum] * X_diff * X_k[idx_c]

    # 段间平均
    msb_spectrum = msb_sum / n_actual_segments

    # --- MSB-SE 切片 ---
    # MSB_SE(f_c) = Σ |B(f_c, f_Δ)| over f_Δ
    msb_se_slice = np.sum(np.abs(msb_spectrum), axis=1)

    # f_c 轴和 f_Δ 轴（Hz）
    msb_fc_axis = freq_axis[:n_fc]
    msb_delta_axis = freq_axis[:n_delta]

    # --- 特征切片频率 ---
    # 太阳轮故障切片：f_c = 2*f_mesh - f_carrier（残余边频带）
    sun_slice_freq = 2.0 * mesh_freq - carrier_freq

    # 行星轮故障切片：f_c = 2*f_mesh + f_carrier（同相边频带）
    planet_slice_freq = 2.0 * mesh_freq + carrier_freq

    # --- MSB-SNR 计算 ---
    # 在特征切片位置计算 SNR 相对于背景
    # 背景：MSB-SE 切片的统计中位数（排除特征切片附近的区域）

    # 背景区域：排除特征切片附近 ±5*df 的频带
    df_hz = df
    exclude_band = 5.0 * df_hz

    # 计算背景（排除特征频率附近）
    bg_mask = np.ones(len(msb_se_slice), dtype=bool)
    for feat_freq in [sun_slice_freq, planet_slice_freq]:
        mask_exclude = (msb_fc_axis >= feat_freq - exclude_band) & \
                       (msb_fc_axis <= feat_freq + exclude_band)
        bg_mask[mask_exclude] = False

    # 也排除 mesh_freq 和 2*mesh_freq 附近（这些区域天然有强 MSB）
    for feat_freq in [mesh_freq, 2.0 * mesh_freq]:
        mask_exclude = (msb_fc_axis >= feat_freq - exclude_band) & \
                       (msb_fc_axis <= feat_freq + exclude_band)
        bg_mask[mask_exclude] = False

    background_se = np.median(msb_se_slice[bg_mask]) if np.any(bg_mask) else 1e-12
    if background_se < 1e-12:
        background_se = 1e-12

    # 太阳轮故障 MSB-SNR
    sun_snr = _compute_slice_snr(
        msb_se_slice, msb_fc_axis, sun_slice_freq, df_hz, background_se
    )

    # 行星轮故障 MSB-SNR
    planet_snr = _compute_slice_snr(
        msb_se_slice, msb_fc_axis, planet_slice_freq, df_hz, background_se
    )

    # --- 残余边频带比 ---
    # residual_sideband_ratio = MSB_SE(sun_slice) / MSB_SE(planet_slice)
    # 太阳轮切片是残余边频带（健康时极低），行星轮切片是同相边频带（天然较强）
    sun_se_value = _get_slice_value(msb_se_slice, msb_fc_axis, sun_slice_freq, df_hz)
    planet_se_value = _get_slice_value(msb_se_slice, msb_fc_axis, planet_slice_freq, df_hz)

    if planet_se_value > 1e-12:
        residual_sideband_ratio = sun_se_value / planet_se_value
    else:
        residual_sideband_ratio = 0.0

    return {
        "valid": True,
        "msb_se_slice": msb_se_slice,
        "msb_fc_axis": msb_fc_axis,
        "msb_spectrum": msb_spectrum,
        "msb_delta_axis": msb_delta_axis,
        "sun_fault_msb_snr": round(float(sun_snr), 4),
        "planet_fault_msb_snr": round(float(planet_snr), 4),
        "residual_sideband_ratio": round(float(residual_sideband_ratio), 4),
        "sun_slice_freq": round(float(sun_slice_freq), 2),
        "planet_slice_freq": round(float(planet_slice_freq), 2),
        "n_segments": n_actual_segments,
        "seg_len": seg_len,
        "df": round(float(df_hz), 4),
    }


def _compute_slice_snr(
    msb_se_slice: np.ndarray,
    fc_axis: np.ndarray,
    target_freq: float,
    df: float,
    background: float,
) -> float:
    """
    在 MSB-SE 切片的指定频率位置计算 SNR

    在 target_freq ± df 范围内搜索峰值，与背景中位数比较得到 SNR。

    Args:
        msb_se_slice: MSB-SE 切片幅值
        fc_axis: 频率轴 Hz
        target_freq: 目标频率 Hz
        df: 频率分辨率 Hz
        background: 背景中位数

    Returns:
        SNR 值（float）
    """
    if len(msb_se_slice) == 0 or len(fc_axis) == 0:
        return 0.0

    # 搜索频带：±3*df（允许频率偏移）
    search_bw = max(3.0 * df, 10.0)
    mask = (fc_axis >= target_freq - search_bw) & (fc_axis <= target_freq + search_bw)

    if not np.any(mask):
        return 0.0

    peak_value = float(np.max(msb_se_slice[mask]))

    # 如果目标频率超过频率轴范围，返回 0
    if target_freq > fc_axis[-1]:
        return 0.0

    return peak_value / background


def _get_slice_value(
    msb_se_slice: np.ndarray,
    fc_axis: np.ndarray,
    target_freq: float,
    df: float,
) -> float:
    """
    在 MSB-SE 切片的指定频率位置提取峰值幅值

    Args:
        msb_se_slice: MSB-SE 切片幅值
        fc_axis: 频率轴 Hz
        target_freq: 目标频率 Hz
        df: 频率分辨率 Hz

    Returns:
        峰值幅值（float）
    """
    if len(msb_se_slice) == 0 or len(fc_axis) == 0:
        return 0.0

    search_bw = max(3.0 * df, 10.0)
    mask = (fc_axis >= target_freq - search_bw) & (fc_axis <= target_freq + search_bw)

    if not np.any(mask):
        return 0.0

    return float(np.max(msb_se_slice[mask]))