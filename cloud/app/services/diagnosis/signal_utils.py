"""
通用信号处理辅助函数
"""
import numpy as np
from scipy import signal as scipy_signal
from scipy.fft import rfft, rfftfreq
from typing import Tuple, Optional, List, Dict


# ══════════════════════════════════════════════════════════
# Layer 0: 原子函数（不可再分的基本操作）
# ══════════════════════════════════════════════════════════

def _search_peak_in_band(
    axis: np.ndarray,
    spectrum: np.ndarray,
    target: float,
    tolerance: float,
) -> Optional[dict]:
    """
    原子函数：在目标值附近的频带内搜索峰值。

    Args:
        axis: 频率/阶次轴 (1D np.ndarray)
        spectrum: 幅值谱 (1D np.ndarray，长度与 axis 一致)
        target: 目标搜索中心值 (float)
        tolerance: 搜索容差 (float, 与 axis 同单位)

    Returns:
        {"freq": float, "amp": float}  或  None (未找到)
    """
    axis = np.asarray(axis)
    spectrum = np.asarray(spectrum)
    mask = np.abs(axis - target) <= tolerance
    if not np.any(mask):
        return None
    idx = int(np.argmax(spectrum[mask]))
    abs_idx = int(np.where(mask)[0][idx])
    return {"freq": float(axis[abs_idx]), "amp": float(spectrum[abs_idx])}


def _estimate_background(
    spectrum: np.ndarray,
    method: str = "median",
) -> float:
    """
    原子函数：估计频谱背景水平。

    Args:
        spectrum: 频谱幅值数组 (1D np.ndarray)
        method: "median" | "mean" | "q75"

    Returns:
        float: 背景估计值（保证 > 0）
    """
    if method == "median":
        bg = np.median(spectrum)
    elif method == "mean":
        bg = np.mean(spectrum)
    elif method == "q75":
        bg = np.percentile(spectrum, 75)
    else:
        bg = np.median(spectrum)
    return max(float(bg), 1e-12)


def _compute_peak_snr(
    peak_amp: float,
    spectrum: np.ndarray,
    method: str = "median",
) -> float:
    """
    原子函数：计算峰值信噪比 SNR = peak / background。

    Args:
        peak_amp: 峰值幅值 (float)
        spectrum: 完整频谱（用于估计背景）(np.ndarray)
        method: 背景估计方法 ("median" | "mean" | "q75")

    Returns:
        float: SNR
    """
    bg = _estimate_background(spectrum, method)
    return peak_amp / bg


def _estimate_noise_mad(arr: np.ndarray) -> float:
    """
    原子函数：MAD法噪声标准差估计

    σ̂ = median(|arr - median(arr)|) / 0.6745

    用于小波去噪等场景的鲁棒噪声水平估计。

    Args:
        arr: 一维信号数组

    Returns:
        float: 噪声标准差估计值（≥ 1e-12）
    """
    arr = np.asarray(arr, dtype=np.float64)
    if len(arr) < 4:
        return 1e-12
    median_val = np.median(arr)
    mad = np.median(np.abs(arr - median_val))
    return max(float(mad / 0.6745), 1e-12)


def _snr_by_residual_std(original: np.ndarray, denoised: np.ndarray) -> float:
    """
    原子函数：基于残差标准差的 SNR 改善比

    SNR_imp = std(original) / std(original - denoised)

    Args:
        original: 原始信号
        denoised: 降噪后信号（长度需与 original 一致）

    Returns:
        float: SNR 改善比（≥ 0）
    """
    orig = np.asarray(original, dtype=np.float64)
    den = np.asarray(denoised, dtype=np.float64)
    n = min(len(orig), len(den))
    resid_std = float(np.std(orig[:n] - den[:n]))
    orig_std = float(np.std(orig[:n]))
    if resid_std < 1e-12:
        return 1e12
    return orig_std / resid_std


# ══════════════════════════════════════════════════════════
# Layer 1: 信号预处理
# ══════════════════════════════════════════════════════════

def remove_dc(signal: np.ndarray) -> np.ndarray:
    """去除直流分量（零均值化）"""
    return signal - np.mean(signal)


def linear_detrend(signal: np.ndarray) -> np.ndarray:
    """线性去趋势"""
    return scipy_signal.detrend(signal, type='linear')


def prepare_signal(signal, detrend: bool = False) -> np.ndarray:
    """
    信号预处理：零均值化或线性去趋势
    detrend=False: 去直流（零均值化）
    detrend=True:  线性去趋势（消除 y=kx+b 漂移）
    """
    arr = np.array(signal, dtype=np.float64)
    if detrend:
        return scipy_signal.detrend(arr, type='linear')
    return arr - np.mean(arr)


def denoise_signal(signal: np.ndarray, method: str) -> np.ndarray:
    """
    通用信号去噪（供 DataView 实时计算端点复用）
    method 可选值对应 DenoiseMethod 枚举的字符串值。
    返回去噪后的信号；method='none' 或未知值时原样返回。
    注意：输入信号应为已经 prepare_signal 处理过的零均值信号。
    """
    arr = np.asarray(signal, dtype=np.float64)
    if not method or method == "none":
        return arr

    try:
        if method == "wavelet":
            from .preprocessing import wavelet_denoise
            return wavelet_denoise(arr, wavelet="db8")
        elif method == "vmd":
            from .vmd_denoise import vmd_denoise
            return vmd_denoise(arr, K=5, alpha=2000)
        elif method == "wavelet_vmd":
            from .preprocessing import cascade_wavelet_vmd
            result, _ = cascade_wavelet_vmd(arr)
            return result
        elif method == "wavelet_lms":
            from .preprocessing import cascade_wavelet_lms
            result, _ = cascade_wavelet_lms(arr)
            return result
        elif method == "emd":
            from .emd_denoise import emd_denoise
            result, _ = emd_denoise(arr, method="emd")
            return result
        elif method == "ceemdan":
            from .emd_denoise import emd_denoise
            result, _ = emd_denoise(arr, method="ceemdan")
            return result
        elif method == "savgol":
            from .savgol_denoise import sg_denoise
            result, _ = sg_denoise(arr)
            return result
        elif method == "wavelet_packet":
            from .wavelet_packet import wavelet_packet_denoise
            result, _ = wavelet_packet_denoise(arr)
            return result
        elif method == "ceemdan_wp":
            from .emd_denoise import emd_denoise
            from .wavelet_packet import wavelet_packet_denoise
            step1, _ = emd_denoise(arr, method="ceemdan")
            step2, _ = wavelet_packet_denoise(step1)
            return step2
        elif method == "eemd":
            from .emd_denoise import emd_denoise
            result, _ = emd_denoise(arr, method="eemd")
            return result
    except Exception:
        pass
    return arr


def bandpass_filter(
    signal: np.ndarray,
    fs: float,
    f_low: float,
    f_high: float,
    order: int = 4,
) -> np.ndarray:
    """Butterworth 带通滤波"""
    if len(signal) < order * 7:
        return signal.copy()
    nyq = fs / 2.0
    low = max(1e-6, f_low / nyq)
    high = min(1.0 - 1e-6, f_high / nyq)
    if low >= high:
        return signal.copy()
    b, a = scipy_signal.butter(order, [low, high], btype='band')
    return scipy_signal.filtfilt(b, a, signal)


def lowpass_filter(
    signal: np.ndarray,
    fs: float,
    f_cut: float,
    order: int = 4,
) -> np.ndarray:
    """Butterworth 低通滤波"""
    if len(signal) < order * 7:
        return signal.copy()
    nyq = fs / 2.0
    cut = min(1.0 - 1e-6, f_cut / nyq)
    b, a = scipy_signal.butter(order, cut, btype='low')
    return scipy_signal.filtfilt(b, a, signal)


def highpass_filter(
    signal: np.ndarray,
    fs: float,
    f_cut: float,
    order: int = 4,
) -> np.ndarray:
    """Butterworth 高通滤波"""
    if len(signal) < order * 7:
        return signal.copy()
    nyq = fs / 2.0
    cut = max(1e-6, f_cut / nyq)
    b, a = scipy_signal.butter(order, cut, btype='high')
    return scipy_signal.filtfilt(b, a, signal)


def compute_fft_spectrum(
    signal: np.ndarray,
    fs: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """计算 FFT 频谱，返回 (频率轴, 幅值)"""
    arr = prepare_signal(signal)
    n = len(arr)
    yf = np.abs(rfft(arr))
    xf = rfftfreq(n, 1.0 / fs)
    return xf, yf


def compute_power_spectrum(
    signal: np.ndarray,
    fs: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """计算功率谱（幅值平方）"""
    xf, yf = compute_fft_spectrum(signal, fs)
    return xf, yf ** 2


def find_peaks_in_spectrum(
    freqs: np.ndarray,
    amps: np.ndarray,
    target_freq: float,
    tolerance_hz: float = 2.0,
    n_harmonics: int = 5,
) -> dict:
    """
    在频谱中搜索目标频率及其谐波族

    Returns:
        {
            "fundamental": {"freq": float, "amp": float, "snr": float},
            "harmonics": [{"freq": float, "amp": float, "order": int}, ...],
            "sidebands": [{"freq": float, "amp": float, "offset_hz": float}, ...],
        }
    """
    result = {
        "fundamental": None,
        "harmonics": [],
        "sidebands": [],
    }
    freqs = np.asarray(freqs)
    amps = np.asarray(amps)

    # 搜索基频 → 调用原子函数
    peak = _search_peak_in_band(freqs, amps, target_freq, tolerance_hz)
    if peak:
        snr = _compute_peak_snr(peak["amp"], amps)
        result["fundamental"] = {
            "freq": peak["freq"],
            "amp": peak["amp"],
            "snr": snr,
        }

    # 搜索谐波 → 复用原子函数
    for h in range(2, n_harmonics + 1):
        hf = target_freq * h
        if hf > freqs[-1]:
            break
        peak_h = _search_peak_in_band(freqs, amps, hf, tolerance_hz)
        if peak_h:
            result["harmonics"].append({
                "freq": peak_h["freq"],
                "amp": peak_h["amp"],
                "order": h,
            })

    return result


def compute_snr(peak_amp: float, spectrum: np.ndarray, method: str = "median") -> float:
    """计算峰值信噪比"""
    return _compute_peak_snr(peak_amp, spectrum, method)


def kurtosis(signal: np.ndarray, fisher: bool = False) -> float:
    """计算峭度，fisher=False 时正态分布=3"""
    from scipy import stats
    return float(stats.kurtosis(signal, fisher=fisher))


def skewness(signal: np.ndarray) -> float:
    """计算偏度"""
    from scipy import stats
    return float(stats.skew(signal))


def rms(signal: np.ndarray) -> float:
    """均方根"""
    return float(np.sqrt(np.mean(signal ** 2)))


def peak_value(signal: np.ndarray) -> float:
    """峰值（最大绝对值）"""
    return float(np.max(np.abs(signal)))


def crest_factor(signal: np.ndarray) -> float:
    """峰值因子 = Peak / RMS"""
    r = rms(signal)
    return peak_value(signal) / r if r > 1e-12 else 0.0


def parabolic_interpolation(freqs, spectrum, idx):
    """抛物线插值精确定位谱峰频率"""
    if idx <= 0 or idx >= len(spectrum) - 1:
        return freqs[idx]
    alpha = spectrum[idx - 1]
    beta = spectrum[idx]
    gamma = spectrum[idx + 1]
    if beta <= max(alpha, gamma):
        return freqs[idx]
    p = 0.5 * (alpha - gamma) / (alpha - 2 * beta + gamma)
    return float(freqs[idx] + p * (freqs[1] - freqs[0]))


def _band_energy(freq, amp, center: float, bandwidth: float) -> float:
    """计算指定频带能量"""
    freq = np.asarray(freq)
    amp = np.asarray(amp)
    mask = (freq >= center - bandwidth) & (freq <= center + bandwidth)
    if not np.any(mask):
        return 0.0
    return float(np.sum(amp[mask] ** 2))


def _order_band_energy(order_axis, spectrum, center_order: float, bandwidth: float) -> float:
    """计算指定阶次带能量"""
    order_axis = np.asarray(order_axis)
    spectrum = np.asarray(spectrum)
    mask = (order_axis >= center_order - bandwidth) & (order_axis <= center_order + bandwidth)
    if not np.any(mask):
        return 0.0
    return float(np.sum(spectrum[mask] ** 2))


def estimate_rot_freq_envelope(
    sig: np.ndarray, fs: float,
    f_center: float,
    bw: float = 60.0,
    freq_range: Tuple[float, float] = (10, 100)
) -> Optional[float]:
    """在指定中心频率附近做带通滤波+包络解调，返回包络谱峰值频率"""
    low = max(10.0, f_center - bw)
    high = min(fs / 2 - 10.0, f_center + bw)
    b, a = scipy_signal.butter(4, [low / (fs / 2), high / (fs / 2)], btype='band')
    bp_sig = scipy_signal.filtfilt(b, a, sig)
    envelope = np.abs(scipy_signal.hilbert(bp_sig))
    envelope = envelope - np.mean(envelope)
    env_spec = np.abs(rfft(envelope))
    env_freqs = rfftfreq(len(envelope), d=1.0 / fs)
    peak = _search_peak_in_band(env_freqs, env_spec, (freq_range[0]+freq_range[1])/2,
                                (freq_range[1]-freq_range[0])/2)
    return peak["freq"] if peak else None


def estimate_rot_freq_autocorr(
    sig: np.ndarray,
    fs: float,
    freq_range: Tuple[float, float] = (10, 100),
) -> Optional[float]:
    """基于自相关的抗噪转频候选估计。"""
    arr = prepare_signal(sig)
    if len(arr) < 16:
        return None

    try:
        high = min(fs / 2 - 10.0, max(freq_range[1] * 6, freq_range[1] + 20.0))
        low = max(1.0, freq_range[0] * 0.5)
        if low < high:
            arr = bandpass_filter(arr, fs, low, high)
    except Exception:
        pass

    arr = arr / (np.std(arr) + 1e-12)
    corr = scipy_signal.correlate(arr, arr, mode="full", method="fft")
    corr = corr[len(corr) // 2:]
    if corr[0] <= 0:
        return None
    corr = corr / corr[0]

    min_lag = max(1, int(fs / freq_range[1]))
    max_lag = min(len(corr) - 1, int(fs / freq_range[0]))
    if max_lag <= min_lag:
        return None

    segment = corr[min_lag:max_lag + 1]
    peaks, props = scipy_signal.find_peaks(segment, prominence=0.03)
    if len(peaks) == 0:
        best = int(np.argmax(segment))
    else:
        prominences = props.get("prominences", np.ones_like(peaks, dtype=float))
        best = int(peaks[int(np.argmax(prominences))])
    lag = min_lag + best
    return float(fs / lag) if lag > 0 else None


def estimate_rot_freq_spectrum(
    sig: np.ndarray,
    fs: float,
    freq_range: Tuple[float, float] = (10, 100),
    harmonics_num: int = 5,
    bandwidth_hz: float = 3.0,
    smooth_win_hz: float = 1.5,
) -> float:
    """
    通过频谱峰值法估计转频（改进版：平滑 + 频带积分 + 插值 + 包络解调辅助）
    针对齿轮箱等啮合频率强、基频弱的数据，引入包络解调和齿数整数验证启发式。
    """
    N = len(sig)
    spectrum = np.abs(rfft(sig))
    freqs = rfftfreq(N, d=1.0 / fs)
    df = freqs[1] - freqs[0]

    # 1. 谱平滑：抑制随机噪声尖峰
    if smooth_win_hz > 0 and df > 0:
        kernel_size = max(1, int(round(smooth_win_hz / df)))
        if kernel_size > 1:
            kernel = np.ones(kernel_size) / kernel_size
            spectrum = np.convolve(spectrum, kernel, mode='same')

    # 2. 归一化
    spectrum_norm = spectrum / (spectrum.max() + 1e-10)

    mask = (freqs >= freq_range[0]) & (freqs <= freq_range[1])
    search_freqs = freqs[mask]
    search_spectrum = spectrum_norm[mask]

    if len(search_freqs) == 0:
        return freq_range[0]

    bw_bins = max(1, int(round(bandwidth_hz / df / 2)))
    # 降低阈值，让弱基频也能参与竞争
    min_base_energy = 0.015 * (2 * bw_bins + 1)

    best_freq_spec = search_freqs[0]
    best_energy = 0.0
    best_idx_global = None

    # 预收集子谐波惩罚信息（避免在循环中重复计算）
    def _sub_harmonic_penalty(f_candidate: float) -> float:
        """如果 f_candidate 的子谐波（f/2, f/3, f/4, f/5）也有明显能量，说明它可能是谐波而非基频"""
        penalty = 0.0
        for div in [2, 3, 4, 5]:
            sub_f = f_candidate / div
            if sub_f < freq_range[0]:
                continue
            idx_sub = np.argmin(np.abs(freqs - sub_f))
            band_sub = spectrum_norm[
                max(0, idx_sub - bw_bins):min(len(spectrum), idx_sub + bw_bins + 1)
            ]
            sub_energy = float(np.sum(band_sub))
            if sub_energy > min_base_energy * 0.6:
                # 子谐波能量越强，惩罚越大；div 越大惩罚越小
                penalty += sub_energy * (1.0 / div) * 0.5
        return penalty

    for f in search_freqs:
        idx_base = np.argmin(np.abs(freqs - f))
        base_band = spectrum_norm[
            max(0, idx_base - bw_bins):min(len(spectrum), idx_base + bw_bins + 1)
        ]
        base_energy = float(np.sum(base_band))
        if base_energy < min_base_energy:
            continue

        energy = 0.0
        for h in range(1, harmonics_num + 1):
            harmonic_freq = f * h
            if harmonic_freq > fs / 2:
                break
            idx = np.argmin(np.abs(freqs - harmonic_freq))
            band = spectrum_norm[
                max(0, idx - bw_bins):min(len(spectrum), idx + bw_bins + 1)
            ]
            weight = 1.0 / h
            energy += float(np.sum(band)) * weight

        energy -= _sub_harmonic_penalty(f)

        if energy > best_energy:
            best_energy = energy
            best_freq_spec = f
            best_idx_global = idx_base

    if best_energy == 0.0:
        # fallback：搜索范围内最强峰
        best_local_idx = int(np.argmax(search_spectrum))
        best_idx_global = int(np.argmin(np.abs(freqs - search_freqs[best_local_idx])))
        best_freq_spec = freqs[best_idx_global]
    else:
        best_freq_spec = parabolic_interpolation(freqs, spectrum, best_idx_global)

    # 记录 best_freq 的基频能量（用于子谐波后处理判断）
    best_base_energy = float(np.sum(spectrum_norm[
        max(0, best_idx_global - bw_bins):min(len(spectrum), best_idx_global + bw_bins + 1)
    ])) if best_idx_global is not None else 0.0

    # ---------- 子谐波后处理：防止谐波冒充基频 ----------
    # 如果 best_freq 是某个较低频率的整数倍谐波，且该较低频率也有明显能量，
    # 则优先选择较低频率作为真实基频（常见于轴承数据基频弱、谐波强的情况）
    for div in [5, 4, 3, 2]:
        candidate_base = best_freq_spec / div
        if candidate_base < freq_range[0]:
            continue
        idx_base = np.argmin(np.abs(freqs - candidate_base))
        base_band = spectrum_norm[
            max(0, idx_base - bw_bins):min(len(spectrum), idx_base + bw_bins + 1)
        ]
        base_energy = float(np.sum(base_band))
        # 条件1：候选基频能量不能仅由噪声构成
        if base_energy < min_base_energy * 0.2:
            continue
        # 条件2：候选基频能量应占 best_freq 能量的显著比例，
        #        防止在纯正弦波等 best_freq 本身极强的情况下误修正
        if base_energy < best_base_energy * 0.12:
            continue
        ratio = best_freq_spec / candidate_base
        if abs(ratio - round(ratio)) < 0.12:
            # 验证该候选基频的谐波能量是否也足够可观
            # 注意：跳过 h=div，因为该谐波就是当前的 best_freq 本身，
            # 不能让它成为"自我证明"的循环依据
            base_harmonic_energy = 0.0
            for h in range(1, harmonics_num + 1):
                if h == div:
                    continue
                hf = candidate_base * h
                if hf > fs / 2:
                    break
                idx_h = np.argmin(np.abs(freqs - hf))
                band_h = spectrum_norm[
                    max(0, idx_h - bw_bins):min(len(spectrum), idx_h + bw_bins + 1)
                ]
                base_harmonic_energy += float(np.sum(band_h)) * (1.0 / h)
            if base_harmonic_energy > best_energy * 0.15:
                best_freq_spec = parabolic_interpolation(freqs, spectrum, idx_base)
                best_idx_global = idx_base
                break

    # ---------- 包络解调 / Welch / 自相关候选 ----------
    # 对啮合频率常见区域（200~500Hz）和全局高频峰做包络解调，收集候选
    candidates = [(best_freq_spec, "spectrum")]

    # 中频带（200~500Hz）：常见啮合频率区域
    mid_peak_info = _search_peak_in_band(freqs, spectrum, 350, 150)
    if mid_peak_info:
        env_est = estimate_rot_freq_envelope(sig, fs, mid_peak_info["freq"], freq_range=freq_range)
        if env_est:
            candidates.append((env_est, "envelope_mesh"))

    # 全局高频最强峰（100Hz ~ fs/4）
    high_peak_info = _search_peak_in_band(freqs, spectrum, (100+fs/4)/2, (fs/4-100)/2)
    if high_peak_info:
        env_est = estimate_rot_freq_envelope(sig, fs, high_peak_info["freq"], freq_range=freq_range)
        if env_est:
            candidates.append((env_est, "envelope_high"))

    try:
        nperseg = min(len(sig), max(256, int(fs)))
        wf, wp = scipy_signal.welch(sig, fs=fs, nperseg=nperseg)
        welch_peak = _search_peak_in_band(wf, wp, (freq_range[0]+freq_range[1])/2,
                                          (freq_range[1]-freq_range[0])/2)
        if welch_peak:
            candidates.append((welch_peak["freq"], "welch"))
    except Exception:
        pass

    ac_est = estimate_rot_freq_autocorr(sig, fs, freq_range=freq_range)
    if ac_est:
        candidates.append((ac_est, "autocorr"))

    # ---------- 启发式仲裁 ----------
    # 优先选择通过"齿数整数"验证的包络法候选：
    # 如果带通中心频率 / 候选转频 ≈ 整数，且齿数在合理范围（8~50），
    # 说明该候选与啮合频率强相关，可信度最高。
    for f_est, method in candidates:
        if method.startswith("envelope"):
            # 0) 频谱基频支持验证：包络候选必须在原始频谱中有足够基频能量，
            #    防止带通滤波在噪声峰上产生虚假包络峰值
            idx_env = np.argmin(np.abs(freqs - f_est))
            env_band = spectrum_norm[
                max(0, idx_env - bw_bins):min(len(spectrum), idx_env + bw_bins + 1)
            ]
            env_base_energy = float(np.sum(env_band))
            if env_base_energy < min_base_energy * 0.3:
                continue

            # 1) 齿数整数验证
            if method == "envelope_mesh":
                f_center = mid_peak_info["freq"] if mid_peak_info else 0
            else:
                f_center = high_peak_info["freq"] if high_peak_info else 0
            teeth = f_center / f_est
            teeth_rounded = round(teeth)
            if abs(teeth - teeth_rounded) < 0.30 and 10 <= teeth_rounded <= 50:
                return float(f_est)

    # 自相关在强谐波场景下通常能给出真实周期；若频谱最强候选是它的整数倍，
    # 优先采用自相关候选，避免 2x/3x 谐波冒充转频。
    autocorr_candidates = [float(f) for f, method in candidates if method == "autocorr"]
    def _support_energy(f_est: float) -> float:
        idx = np.argmin(np.abs(freqs - f_est))
        return float(np.sum(spectrum_norm[
            max(0, idx - bw_bins):min(len(spectrum), idx + bw_bins + 1)
        ]))

    for ac_f in autocorr_candidates:
        for cand_f, _ in candidates:
            if cand_f <= ac_f:
                continue
            ratio = cand_f / ac_f
            ac_support = _support_energy(ac_f)
            cand_support = _support_energy(cand_f)
            if (
                1.8 <= ratio <= 5.2
                and abs(ratio - round(ratio)) < 0.18
                and ac_support > max(min_base_energy * 0.3, cand_support * 0.2)
            ):
                return float(ac_f)

    # 没有通过齿数验证时，对频谱/Welch/自相关候选做谐波一致性仲裁。
    def _candidate_score(f_est: float, method: str) -> float:
        if f_est < freq_range[0] or f_est > freq_range[1]:
            return -1.0
        idx_base = np.argmin(np.abs(freqs - f_est))
        band = spectrum_norm[
            max(0, idx_base - bw_bins):min(len(spectrum), idx_base + bw_bins + 1)
        ]
        score = float(np.sum(band))
        for h in range(2, harmonics_num + 1):
            hf = f_est * h
            if hf > fs / 2:
                break
            idx_h = np.argmin(np.abs(freqs - hf))
            hband = spectrum_norm[
                max(0, idx_h - bw_bins):min(len(spectrum), idx_h + bw_bins + 1)
            ]
            score += float(np.sum(hband)) / h
        score -= _sub_harmonic_penalty(f_est)
        if method == "autocorr":
            score *= 1.10
        elif method == "welch":
            score *= 1.05
        return score

    best_candidate, _ = max(
        candidates,
        key=lambda item: _candidate_score(float(item[0]), item[1])
    )
    return float(best_candidate)


# ---------------------------------------------------------------------------
# ZOOM-FFT 细化谱分析
# ---------------------------------------------------------------------------


def zoom_fft_analysis(
    signal: np.ndarray,
    fs: float,
    center_freq: float,
    bandwidth: float,
    zoom_factor: int = 16,
) -> Dict:
    """
    ZOOM-FFT 细化谱分析（复调制法）

    对指定频带进行高分辨率频谱分析，频率分辨率提升 zoom_factor 倍。
    使用复调制移频 + 低通滤波 + FFT 的经典 ZOOM-FFT 方法实现。

    原理：
    1. 复调制（频移）：将信号乘以 exp(-j*2π*f_c*t)，把中心频率 f_c 移到零频
    2. 低通滤波：截取移频后信号中 [-bandwidth/2, +bandwidth/2] 范围的频带
    3. 降采样（抽取）：滤波后信号有效带宽仅 bandwidth，可按 M = fs/bandwidth 倍降采样
    4. FFT：对降采样后的短序列做 FFT，得到细化频谱
    5. 频率轴映射：FFT 结果的零频对应原始信号的 center_freq，分辨率提升 M 倍

    物理意义：
    - 标准 FFT 的频率分辨率 Δf = fs/N，受采样率和数据长度制约
    - ZOOM-FFT 在不增加数据长度的情况下，将指定窄带内的分辨率提升 zoom_factor 倍
    - 适用于齿轮箱啮合频率边频带精细分析、轴承故障特征频率精确定位等场景

    典型应用：
    - 齿轮啮合频率附近边频带的精细分辨（区分转频间隔的边频带）
    - 轴承故障特征频率的精确确认（避免频率分辨率不足导致的误判）
    - 变速工况下的瞬时频率精确估计

    Args:
        signal: 振动信号（一维 numpy 数组）
        fs: 采样率 Hz
        center_freq: 细化中心频率 Hz（频带中心位置）
        bandwidth: 细化带宽 Hz（频带宽度）
        zoom_factor: 细化倍数（频率分辨率提升倍数，默认 16）

    Returns:
        {
            "zoom_freq_axis": np.ndarray,  # 细化频谱频率轴 Hz（围绕 center_freq）
            "zoom_spectrum": np.ndarray,    # 细化频谱幅值
            "resolution_hz": float,         # 细化后频率分辨率 Hz
            "original_resolution_hz": float, # 原始频率分辨率 Hz
            "zoom_factor": int,             # 实际细化倍数
            "center_freq": float,           # 细化中心频率 Hz
            "bandwidth": float,             # 细化带宽 Hz
            "n_zoom_points": int,           # 细化谱点数
            "valid": bool,
        }
    """
    arr = np.array(signal, dtype=np.float64)
    N = len(arr)

    # --- 异常输入安全处理 ---
    if N < 64 or fs <= 0 or center_freq <= 0 or bandwidth <= 0:
        return {
            "valid": False,
            "reason": "invalid_input",
            "zoom_freq_axis": np.array([]),
            "zoom_spectrum": np.array([]),
            "resolution_hz": 0.0,
            "original_resolution_hz": 0.0,
            "zoom_factor": zoom_factor,
            "center_freq": center_freq,
            "bandwidth": bandwidth,
            "n_zoom_points": 0,
        }

    # 确保 bandwidth 不超过奈奎斯特频率
    half_bw = bandwidth / 2.0
    if center_freq - half_bw < 0:
        # 低端超出 0 Hz，调整中心频率
        center_freq = half_bw
    if center_freq + half_bw > fs / 2.0:
        # 高端超出奈奎斯特，调整带宽
        half_bw = min(half_bw, fs / 2.0 - center_freq)
        bandwidth = 2.0 * half_bw

    # --- 原始频率分辨率 ---
    original_resolution = fs / N

    # --- 复调制（频移） ---
    # 将 center_freq 移到零频：乘以 exp(-j*2π*f_c*t)
    t = np.arange(N, dtype=np.float64) / fs
    shift_exp = np.exp(-2.0j * np.pi * center_freq * t)
    shifted_signal = arr * shift_exp

    # --- 低通滤波 ---
    # 截取移频后信号中 [-bandwidth/2, +bandwidth/2] 范围的频带
    # 低通截止频率 = bandwidth/2
    f_cut = half_bw
    nyq = fs / 2.0
    if f_cut >= nyq:
        # 不需要滤波（带宽覆盖全频谱）
        filtered = shifted_signal
        decimation_factor = 1
    else:
        # Butterworth 低通滤波，阶数=6 以保证足够的带外衰减
        try:
            filtered = lowpass_filter_complex(shifted_signal, fs, f_cut, order=6)
        except Exception:
            # 滤波失败时，直接使用移频信号（降采样时可能有混叠风险）
            filtered = shifted_signal

        # --- 降采样（抽取） ---
        # 滤波后信号有效带宽仅 bandwidth，可按 M 倍降采样
        # M = fs / bandwidth 的整数部分，同时限制不超过 zoom_factor
        decimation_factor = max(1, min(zoom_factor, int(fs / bandwidth)))

    if decimation_factor > 1:
        # 抽取：每隔 M 个点取一个样本
        # 先确保抽取后长度为偶数（便于 FFT）
        n_decimated = N // decimation_factor
        if n_decimated < 16:
            decimation_factor = 1
            n_decimated = N
        else:
            decimated = filtered[:n_decimated * decimation_factor]
            decimated = decimated[::decimation_factor]
    else:
        decimated = filtered
        n_decimated = len(decimated)

    # --- FFT 细化谱 ---
    # 对降采样后的短序列做 FFT
    zoom_spectrum_complex = np.fft.fft(decimated, n=n_decimated)
    zoom_spectrum = np.abs(zoom_spectrum_complex) / n_decimated

    # --- 频率轴映射 ---
    # FFT 结果的零频对应原始信号的 center_freq
    # 频率范围：center_freq - bandwidth/2 到 center_freq + bandwidth/2
    zoom_df = fs / (decimation_factor * n_decimated)
    zoom_freq_axis = center_freq + np.arange(n_decimated) * zoom_df
    # 只取正频率范围（center_freq ± bandwidth/2）
    # 由于复调制后的 FFT 频率轴从 center_freq 开始向正方向延伸，
    # 需要重排 FFT 输出使其对应 center_freq ± bandwidth/2
    # 标准 FFT 输出：[0, Δf, 2Δf, ..., (N-1)Δf]
    # 映射到原始频率：[f_c, f_c+Δf, ..., f_c+(N-1)Δf]
    # 但我们需要 [-BW/2, ..., f_c, ..., +BW/2] 的对称范围

    # 重排 FFT 输出：将零频（对应 f_c）放在中心
    # 取 FFT 结果中对应 [-BW/2, +BW/2] 范围的部分
    f_min = center_freq - half_bw
    f_max = center_freq + half_bw

    # 使用 np.fft.fftshift 将零频移到中心
    zoom_spectrum_shifted = np.fft.fftshift(zoom_spectrum)
    zoom_freq_shifted = np.fft.fftshift(
        np.arange(n_decimated, dtype=np.float64) * zoom_df
    )
    # 映射到原始频率：零频位置对应 center_freq
    zoom_freq_axis = zoom_freq_shifted + center_freq

    # 只保留在目标频带内的部分
    mask = (zoom_freq_axis >= f_min) & (zoom_freq_axis <= f_max)
    zoom_freq_final = zoom_freq_axis[mask]
    zoom_spectrum_final = zoom_spectrum_shifted[mask]

    if len(zoom_spectrum_final) == 0:
        # 频带内无数据点，返回全范围
        zoom_freq_final = zoom_freq_axis
        zoom_spectrum_final = zoom_spectrum_shifted

    # --- 细化后频率分辨率 ---
    actual_zoom = decimation_factor
    resolution_hz = zoom_df if len(zoom_freq_final) > 1 else 0.0

    return {
        "valid": True,
        "zoom_freq_axis": zoom_freq_final,
        "zoom_spectrum": zoom_spectrum_final,
        "resolution_hz": round(float(resolution_hz), 4),
        "original_resolution_hz": round(float(original_resolution), 4),
        "zoom_factor": actual_zoom,
        "center_freq": round(float(center_freq), 2),
        "bandwidth": round(float(bandwidth), 2),
        "n_zoom_points": len(zoom_spectrum_final),
    }


def lowpass_filter_complex(
    signal: np.ndarray,
    fs: float,
    f_cut: float,
    order: int = 6,
) -> np.ndarray:
    """
    复数信号低通滤波

    对复数信号（如复调制后的信号）做低通滤波。
    将复数信号分离为实部和虚部，分别滤波后重新组合。

    Args:
        signal: 复数信号（一维 numpy 数组，dtype 可为 complex）
        fs: 采样率 Hz
        f_cut: 截止频率 Hz
        order: 滤波器阶数（默认 6）

    Returns:
        滤波后的复数信号
    """
    nyq = fs / 2.0
    cut = min(1.0 - 1e-6, f_cut / nyq)
    b, a = scipy_signal.butter(order, cut, btype='low')

    # 分离实部和虚部，分别滤波
    real_part = scipy_signal.filtfilt(b, a, np.real(signal))
    imag_part = scipy_signal.filtfilt(b, a, np.imag(signal))

    return real_part + 1.0j * imag_part
