"""
齿轮指标计算模块

包含基于阶次谱和时域的高级齿轮诊断指标：
- FM0 / FM0_order: 粗故障检测
- FM4 / M6A / M8A: 局部故障高阶矩检测
- NA4: 趋势型故障检测（损伤扩展追踪）
- NB4: 包络域局部齿损坏
- SER / SER_order: 边频带能量比
- CAR: 倒频谱幅值比
- analyze_sidebands_order: 基于阶次谱的边频带分析
"""
import numpy as np
from scipy.fft import rfft, rfftfreq
from scipy.signal import hilbert
from typing import Dict, List, Optional

from ..signal_utils import (
    prepare_signal,
    compute_fft_spectrum,
    bandpass_filter,
    _band_energy,
    _order_band_energy,
    zoom_fft_analysis,
)


def compute_tsa_residual_order(
    signal: np.ndarray,
    fs: float,
    rot_freq: float,
    samples_per_rev: int = 1024,
    min_revolutions: int = 4,
) -> Dict:
    """
    角域时域同步平均（TSA）与残差信号。

    没有编码器时使用估计转频进行等角度重采样，再按转周期做鲁棒平均。
    返回的 residual/differential 用于 FM4/M6A/M8A，避免直接用高通近似。
    """
    arr = prepare_signal(signal)
    if rot_freq <= 0 or len(arr) < samples_per_rev:
        return {"valid": False, "reason": "invalid_rot_freq"}

    duration = len(arr) / fs
    total_revs = duration * rot_freq
    n_revs = int(np.floor(total_revs))
    if n_revs < min_revolutions:
        return {"valid": False, "reason": "too_few_revolutions"}

    n_points = n_revs * samples_per_rev
    times = np.arange(len(arr)) / fs
    target_times = np.linspace(0, n_revs / rot_freq, n_points, endpoint=False)
    order_signal = np.interp(target_times, times, arr)
    cycles = order_signal.reshape(n_revs, samples_per_rev)

    tsa_cycle = np.median(cycles, axis=0)
    tsa_signal = np.tile(tsa_cycle, n_revs)
    residual = order_signal - tsa_signal

    # 差分信号：从 TSA 周期中移除低阶平滑啮合形态，保留局部齿损伤尖峰。
    win = max(5, samples_per_rev // 32)
    if win % 2 == 0:
        win += 1
    kernel = np.ones(win, dtype=np.float64) / win
    regular = np.convolve(tsa_cycle, kernel, mode="same")
    differential_cycle = tsa_cycle - regular
    differential = np.tile(differential_cycle, n_revs)

    return {
        "valid": True,
        "revolutions": n_revs,
        "order_signal": order_signal,
        "tsa_signal": tsa_signal,
        "tsa_cycle": tsa_cycle,
        "residual": residual,
        "differential": differential,
    }


def _order_band_amplitude(order_axis, spectrum, center_order: float, bandwidth: float) -> float:
    """计算指定阶次带幅值和（非能量和）"""
    order_axis = np.asarray(order_axis)
    spectrum = np.asarray(spectrum)
    mask = (order_axis >= center_order - bandwidth) & (order_axis <= center_order + bandwidth)
    if not np.any(mask):
        return 0.0
    return float(np.sum(np.abs(spectrum[mask])))


def compute_fm4(differential_signal: np.ndarray) -> float:
    """
    FM4 — 局部故障检测（单/双齿点蚀/裂纹）

    基于差分信号的归一化峭度。
    局部故障产生孤立大峰值，使分布尖锐，FM4 > 3（高斯基准）。
    """
    d = np.array(differential_signal, dtype=np.float64)
    N = len(d)
    if N < 4:
        return 0.0

    d_mean = np.mean(d)
    numerator = N * np.sum((d - d_mean) ** 4)
    denominator = np.sum((d - d_mean) ** 2) ** 2

    if denominator < 1e-12:
        return 0.0
    return float(numerator / denominator)


def compute_m6a(differential_signal: np.ndarray) -> float:
    """M6A — 表面损伤高阶矩（6阶）"""
    d = np.array(differential_signal, dtype=np.float64)
    N = len(d)
    if N < 6:
        return 0.0

    d_mean = np.mean(d)
    var = np.mean((d - d_mean) ** 2)
    if var < 1e-12:
        return 0.0

    m6 = np.mean((d - d_mean) ** 6)
    return float(m6 / (var ** 3))


def compute_m8a(differential_signal: np.ndarray) -> float:
    """M8A — 表面损伤高阶矩（8阶）"""
    d = np.array(differential_signal, dtype=np.float64)
    N = len(d)
    if N < 8:
        return 0.0

    d_mean = np.mean(d)
    var = np.mean((d - d_mean) ** 2)
    if var < 1e-12:
        return 0.0

    m8 = np.mean((d - d_mean) ** 8)
    return float(m8 / (var ** 4))


def compute_car(
    signal: np.ndarray,
    fs: float,
    rot_freq: float,
    n_harmonics: int = 3,
    tolerance_hz: float = 500.0,
) -> float:
    """
    CAR — 倒频谱幅值比（Cepstrum Amplitude Ratio）

    CAR = mean(C_peaks) / mean(C_background)
    CAR > 1 且持续上升趋势指示齿轮劣化。
    """
    arr = prepare_signal(signal)
    N = len(arr)

    # 加窗减少频谱泄漏
    window = np.hanning(N)
    sig_windowed = arr * window

    spectrum = np.fft.fft(sig_windowed)
    log_spectrum = np.log(np.abs(spectrum) + 1e-10)
    log_spectrum = log_spectrum - np.mean(log_spectrum)

    cepstrum = np.real(np.fft.ifft(log_spectrum))
    quefrency = np.arange(N) / fs
    half = N // 2
    quef = quefrency[:half]
    cep = cepstrum[:half]

    # 搜索目标倒频率对应的峰值
    peak_amps = []
    for k in range(1, n_harmonics + 1):
        tau_k = k / rot_freq
        mask = np.abs(quef - tau_k) <= (1.0 / tolerance_hz if tolerance_hz > 0 else 0.002)
        if np.any(mask):
            peak_amps.append(float(np.max(cep[mask])))

    if not peak_amps:
        return 0.0

    # 背景：高倒频率区域（> 2 * max(tau_k)）
    bg_threshold = 2.0 * n_harmonics / rot_freq
    bg_mask = quef > bg_threshold
    if not np.any(bg_mask):
        bg_mask = quef > quef[-1] * 0.5

    bg_mean = float(np.mean(cep[bg_mask])) if np.any(bg_mask) else 1e-12
    if bg_mean < 1e-12:
        bg_mean = 1e-12

    return float(np.mean(peak_amps) / bg_mean)


def compute_ser_order(
    order_axis,
    spectrum,
    mesh_order: float,
    n_sidebands: int = 6,
    sideband_bw: float = 0.3,
) -> float:
    """
    基于阶次谱计算 SER（边频带能量比）

    SER = sum(A_SB_i^+ + A_SB_i^-) / A(mesh_order)

    与 compute_ser 的区别：基于阶次谱而非 FFT 频谱，
    确保齿轮诊断结果与阶次谱页面一致。
    """
    order_axis = np.asarray(order_axis)
    spectrum = np.asarray(spectrum)

    mesh_amp = _order_band_amplitude(order_axis, spectrum, mesh_order, 0.5)
    if mesh_amp < 1e-12:
        return 0.0

    total_sideband = 0.0
    for i in range(1, n_sidebands + 1):
        sb_low = mesh_order - i
        sb_high = mesh_order + i
        total_sideband += _order_band_amplitude(order_axis, spectrum, sb_low, sideband_bw)
        total_sideband += _order_band_amplitude(order_axis, spectrum, sb_high, sideband_bw)

    return float(total_sideband / mesh_amp)


def analyze_sidebands_order(
    order_axis,
    spectrum,
    mesh_order: float,
    n_sidebands: int = 6,
    spacing: float = 1.0,
) -> Dict:
    """
    基于阶次谱的边频带分析

    spacing 参数控制边频带间隔：
    - 定轴齿轮箱: spacing=1.0（边频带间隔 = 转频阶次）
    - 行星齿轮箱: spacing=carrier_order = Z_sun/(Z_sun+Z_ring)（边频带间隔 = carrier 转频）

    返回边频带的阶次、幅值、显著性、对称性等信息。
    """
    order_axis = np.asarray(order_axis)
    spectrum = np.asarray(spectrum)

    mesh_amp = _order_band_amplitude(order_axis, spectrum, mesh_order, 0.5)
    if mesh_amp < 1e-12:
        return {"sidebands": [], "ser": 0.0, "mesh_amp": 0.0}

    sidebands = []
    total_sb = 0.0

    for i in range(1, n_sidebands + 1):
        sb_low = mesh_order - i * spacing
        sb_high = mesh_order + i * spacing

        amp_low = _order_band_amplitude(order_axis, spectrum, sb_low, 0.3)
        amp_high = _order_band_amplitude(order_axis, spectrum, sb_high, 0.3)

        total_sb += amp_low + amp_high

        # 显著性：边频幅值超过啮合频率的 5%
        significant = (amp_low > mesh_amp * 0.05) or (amp_high > mesh_amp * 0.05)

        sidebands.append({
            "order": i,
            "spacing": spacing,
            "order_low": round(sb_low, 4),
            "order_high": round(sb_high, 4),
            "amp_low": round(amp_low, 6),
            "amp_high": round(amp_high, 6),
            "significant": significant,
            "asymmetry": round(abs(amp_low - amp_high) / (amp_low + amp_high + 1e-12), 4),
        })

    return {
        "sidebands": sidebands,
        "ser": round(total_sb / mesh_amp, 4),
        "mesh_amp": round(mesh_amp, 6),
    }


def compute_fm0_order(
    tsa_signal: np.ndarray,
    order_axis,
    spectrum,
    mesh_order: float,
    n_harmonics: int = 3,
) -> float:
    """
    基于阶次谱计算 FM0（粗故障检测）

    FM0 = PP / sum(A(mesh_order_harmonics))
    """
    arr = np.array(tsa_signal, dtype=np.float64)
    pp = np.max(arr) - np.min(arr)

    order_axis = np.asarray(order_axis)
    spectrum = np.asarray(spectrum)

    harmonics_sum = 0.0
    for i in range(1, n_harmonics + 1):
        harmonics_sum += _order_band_amplitude(order_axis, spectrum, mesh_order * i, 0.5)

    if harmonics_sum < 1e-12:
        return 0.0
    return float(pp / harmonics_sum)


# ---------------------------------------------------------------------------
# NA4 / NB4 — 趋势型齿轮故障检测指标
# ---------------------------------------------------------------------------


def compute_na4(
    residual_signal: np.ndarray,
    historical_variances: List[float],
) -> float:
    """
    NA4 — 趋势型齿轮故障检测（损伤扩展追踪）

    NA4 是准归一化峭度指标，分母使用历史批次残余信号方差的均值，
    使得随着损伤扩展 NA4 单调上升，而 FM4 因分母随损伤同步增长而无法单调。

    公式：
        NA4 = mean((r - r_mean)^4) / (mean(historical_variances))^2

    当无历史数据（historical_variances 为空）时退化为 FM4：
        NA4 ≈ FM4 = mean((r - r_mean)^4) / (current_variance)^2

    物理意义：
    - 健康齿轮 NA4 ≈ 3（高斯基准），随局部损伤扩展单调增大
    - 分母固定为历史均值，即使当前残余方差因损伤增大，NA4 仍持续上升
    - 适用于齿轮损伤趋势监测和预防性维护决策

    Args:
        residual_signal: TSA 残余信号（当前批次）
        historical_variances: 历史批次残余信号方差列表（来自 diagnosis 表）
                               每个元素为一个 float 方差值，不是原始信号

    Returns:
        NA4 值（float），健康状态约 3，损伤状态 > 3 且趋势上升
    """
    r = np.array(residual_signal, dtype=np.float64)
    N = len(r)
    if N < 4:
        return 0.0

    # 当前残余信号的四阶矩（峭度的分子）
    r_mean = np.mean(r)
    numerator = np.mean((r - r_mean) ** 4)

    # 当前方差（用于无历史数据时的退化计算）
    current_var = np.mean((r - r_mean) ** 2)

    # 分母：历史方差均值，或退化使用当前方差
    if historical_variances and len(historical_variances) > 0:
        # 过滤掉无效值（零或负数）
        valid_vars = [v for v in historical_variances if v > 0]
        if valid_vars:
            denom_var = np.mean(valid_vars)
        else:
            # 所有历史方差无效，退化为 FM4
            denom_var = current_var
    else:
        # 无历史数据，退化为 FM4
        denom_var = current_var

    denominator = denom_var ** 2
    if denominator < 1e-12:
        return 0.0

    return float(numerator / denominator)


def compute_nb4(
    residual_signal: np.ndarray,
    fs: float,
    mesh_freq: float,
    historical_variances: List[float],
) -> float:
    """
    NB4 — 包络域局部齿损坏检测

    NB4 是包络域的准归一化峭度指标，用于检测由局部齿损坏引起的瞬态负载波动。
    与 NA4 类似使用历史方差作为分母，但作用于包络信号而非残余信号本身。

    计算步骤：
    1. 对残余信号在 mesh_freq ± 10% 带宽内做带通滤波（最低截止 50 Hz）
    2. 对滤波信号做 Hilbert 变换提取包络
    3. NB4 = mean((E - E_mean)^4) / (mean(historical_variances))^2

    当无历史数据时退化为包络峭度：
        NB4 ≈ mean((E - E_mean)^4) / (current_envelope_variance)^2

    物理意义：
    - 局部齿损坏（点蚀、裂纹）在啮合频率附近产生幅值调制
    - 包络信号捕捉该调制模式，NB4 对局部冲击敏感
    - 分母使用历史方差使 NB4 具有趋势追踪能力
    - 健康齿轮 NB4 ≈ 3，损伤状态 > 3 且趋势上升

    Args:
        residual_signal: TSA 残余信号
        fs: 采样率 Hz
        mesh_freq: 啮合频率 Hz（带通滤波中心频率）
        historical_variances: 历史批次包络信号方差列表（来自 diagnosis 表）
                               每个元素为一个 float 方差值

    Returns:
        NB4 值（float），健康状态约 3，损伤状态 > 3 且趋势上升
    """
    r = np.array(residual_signal, dtype=np.float64)
    N = len(r)
    if N < 4 or fs <= 0 or mesh_freq <= 0:
        return 0.0

    # --- 带通滤波：mesh_freq ± 10% 带宽，最低截止 50 Hz ---
    bandwidth_ratio = 0.10  # 10% 带宽
    f_low = mesh_freq * (1.0 - bandwidth_ratio)
    f_high = mesh_freq * (1.0 + bandwidth_ratio)

    # 最低截止频率 50 Hz（避免直流/低频噪声干扰）
    f_low = max(50.0, f_low)
    # 最高截止不超过奈奎斯特频率
    f_high = min(fs / 2.0 - 10.0, f_high)

    # 如果低截止超过高截止（mesh_freq 极低的情况），调整带宽
    if f_low >= f_high:
        f_low = max(50.0, mesh_freq - 50.0)
        f_high = min(fs / 2.0 - 10.0, mesh_freq + 50.0)
        if f_low >= f_high:
            # mesh_freq 太低或 fs 太低，无法带通滤波，使用原始信号
            filtered = r
        else:
            filtered = bandpass_filter(r, fs, f_low, f_high)
    else:
        filtered = bandpass_filter(r, fs, f_low, f_high)

    # --- Hilbert 包络提取 ---
    envelope = np.abs(hilbert(filtered))
    N_env = len(envelope)
    if N_env < 4:
        return 0.0

    # --- NB4 计算 ---
    e_mean = np.mean(envelope)
    numerator = np.mean((envelope - e_mean) ** 4)

    # 当前包络方差（用于无历史数据时的退化计算）
    current_env_var = np.mean((envelope - e_mean) ** 2)

    # 分母：历史方差均值，或退化使用当前包络方差
    if historical_variances and len(historical_variances) > 0:
        valid_vars = [v for v in historical_variances if v > 0]
        if valid_vars:
            denom_var = np.mean(valid_vars)
        else:
            denom_var = current_env_var
    else:
        # 无历史数据，退化为包络峭度
        denom_var = current_env_var

    denominator = denom_var ** 2
    if denominator < 1e-12:
        return 0.0

    return float(numerator / denominator)


# ---------------------------------------------------------------------------
# ZOOM-FFT 细化谱边频带分析
# ---------------------------------------------------------------------------


def analyze_sidebands_zoom_fft(
    signal: np.ndarray,
    fs: float,
    mesh_freq: float,
    rot_freq: float,
    n_sidebands: int = 6,
    zoom_factor: int = 16,
    bandwidth_hz: Optional[float] = None,
) -> Dict:
    """
    基于 ZOOM-FFT 细化谱的边频带分析

    ALGORITHMS.md §2.5.1 Step2：
    "采用 ZOOM-FFT 或细化谱分析，确保频率分辨率 Δf ≤ f_r/4（至少能分辨 4 根边频）"

    标准 FFT 的频率分辨率 Δf = fs/N，当 Δf > f_r/4 时边频带无法精确分辨。
    ZOOM-FFT 在不增加数据长度的情况下将指定频带分辨率提升 zoom_factor 倍，
    使边频间隔可精确分辨。

    算法流程：
    1. 检查标准 FFT 分辨率是否足够（Δf ≤ rot_freq/4）
    2. 若不够，用 ZOOM-FFT 细化啮合频率附近频带
    3. 在细化谱中搜索 n_sidebands 阶边频带
    4. 计算边频显著性（幅值超过啮合频率的 5%~10%）
    5. 计算 SER（边频带能量比）和边频不对称性

    Args:
        signal: 输入振动信号
        fs: 采样率 Hz
        mesh_freq: 啮合频率 Hz (f_mesh = Z × f_r)
        rot_freq: 转频 Hz
        n_sidebands: 搜索的边频带阶数（默认6阶，与 SER 定义一致）
        zoom_factor: 细化倍数（默认16，即分辨率提升16倍）
        bandwidth_hz: 细化带宽 Hz，None 则自动计算

    Returns:
        {
            "sidebands": List[Dict],
            "ser": float,
            "mesh_amp": float,
            "resolution_hz": float,
            "original_resolution_hz": float,
            "zoom_used": bool,
            "zoom_factor": int,
        }
    """
    arr = prepare_signal(signal)
    N = len(arr)

    # 计算原始 FFT 分辨率
    original_resolution = fs / N

    # 自动计算细化带宽：覆盖 mesh_freq ± n_sidebands × rot_freq
    if bandwidth_hz is None:
        bandwidth_hz = max(2 * n_sidebands * rot_freq + rot_freq * 4,
                          mesh_freq * 0.5)
    bandwidth_hz = min(bandwidth_hz, fs / 2.0)

    # 判断是否需要 ZOOM-FFT
    # 标准: Δf ≤ f_r/4 才能精确分辨边频带
    need_zoom = original_resolution > rot_freq / 4.0

    if need_zoom:
        # 使用 ZOOM-FFT 细化谱
        zoom_result = zoom_fft_analysis(
            arr, fs, center_freq=mesh_freq,
            bandwidth=bandwidth_hz, zoom_factor=zoom_factor
        )
        if not zoom_result.get("valid", False):
            # ZOOM-FFT 失败，退回标准 FFT
            xf, yf = compute_fft_spectrum(arr, fs)
            xf = np.array(xf)
            yf = np.array(yf)
            zoom_used = False
            resolution = original_resolution
        else:
            xf = zoom_result["zoom_freq_axis"]
            yf = zoom_result["zoom_spectrum"]
            resolution = zoom_result["resolution_hz"]
            zoom_used = True
    else:
        # 标准 FFT 分辨率足够，直接用标准 FFT
        xf, yf = compute_fft_spectrum(arr, fs)
        xf = np.array(xf)
        yf = np.array(yf)
        resolution = original_resolution
        zoom_used = False

    # 搜索啮合频率幅值
    mesh_bw = max(resolution * 3, 2.0)
    mesh_amp = _band_energy(xf, yf, mesh_freq, mesh_bw)
    if mesh_amp < 1e-12:
        return {
            "sidebands": [],
            "ser": 0.0,
            "mesh_amp": 0.0,
            "resolution_hz": round(resolution, 4),
            "original_resolution_hz": round(original_resolution, 4),
            "zoom_used": zoom_used,
            "zoom_factor": zoom_factor if zoom_used else 1,
        }

    # 搜索各阶边频带
    sidebands = []
    total_sb = 0.0
    sb_bw = max(resolution * 3, 2.0)  # 边频搜索带宽

    for i in range(1, n_sidebands + 1):
        sb_low = mesh_freq - i * rot_freq
        sb_high = mesh_freq + i * rot_freq

        # 确保边频频率在有效范围内
        if sb_low < 0 or sb_high > fs / 2.0:
            continue

        amp_low = _band_energy(xf, yf, sb_low, sb_bw)
        amp_high = _band_energy(xf, yf, sb_high, sb_bw)

        total_sb += amp_low + amp_high

        # 显著性：边频幅值超过啮合频率的 5%~10%
        significant = (amp_low > mesh_amp * 0.05) or (amp_high > mesh_amp * 0.05)

        sidebands.append({
            "order": i,
            "freq_low_hz": round(sb_low, 2),
            "freq_high_hz": round(sb_high, 2),
            "amp_low": round(amp_low, 6),
            "amp_high": round(amp_high, 6),
            "significant": significant,
            "asymmetry": round(abs(amp_low - amp_high) / (amp_low + amp_high + 1e-12), 4),
            "ratio_low": round(amp_low / mesh_amp, 4),
            "ratio_high": round(amp_high / mesh_amp, 4),
        })

    return {
        "sidebands": sidebands,
        "ser": round(total_sb / mesh_amp, 4),
        "mesh_amp": round(mesh_amp, 6),
        "resolution_hz": round(resolution, 4),
        "original_resolution_hz": round(original_resolution, 4),
        "zoom_used": zoom_used,
        "zoom_factor": zoom_factor if zoom_used else 1,
    }
