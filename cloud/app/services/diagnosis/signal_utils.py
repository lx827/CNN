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
    return scipy_signal.detrend(signal, type="linear")


def prepare_signal(signal, detrend: bool = False) -> np.ndarray:
    """
    信号预处理：零均值化或线性去趋势
    detrend=False: 去直流（零均值化）
    detrend=True:  线性去趋势（消除 y=kx+b 漂移）
    """
    arr = np.array(signal, dtype=np.float64)
    if detrend:
        return scipy_signal.detrend(arr, type="linear")
    return arr - np.mean(arr)


class DenoisingError(ValueError):
    """去噪未产生有效表示；业务/API 必须保留方法与原因，禁止静默回退原信号。"""

    def __init__(self, method: str, reason: str):
        self.method = method
        self.reason = reason
        super().__init__(f"去噪 {method} 无法完成: {reason}")


def denoise_signal(signal: np.ndarray, method: str) -> np.ndarray:
    """统一去噪业务分派；none 原样返回，未知方法或计算失败显式报错。"""
    arr = np.asarray(signal, dtype=np.float64)
    if method == "none":
        return arr
    try:
        if arr.ndim != 1 or not len(arr) or not np.all(np.isfinite(arr)):
            raise ValueError("去噪输入必须是非空的一维有限数组")
        if method == "wavelet":
            from app.algorithms.decomposition.wavelet import denoise_wavelet

            result = denoise_wavelet(arr, wavelet="db8")
        elif method == "vmd":
            from .vmd_denoise import vmd_denoise

            result = vmd_denoise(arr, K=5, alpha=2000)
        elif method in ("wavelet_vmd", "wavelet_lms"):
            from .preprocessing import cascade_wavelet_vmd, cascade_wavelet_lms

            function = (
                cascade_wavelet_vmd if method == "wavelet_vmd" else cascade_wavelet_lms
            )
            result, _ = function(arr)
        elif method in ("emd", "eemd", "ceemdan"):
            from .emd_denoise import emd_denoise

            result, _ = emd_denoise(arr, method=method)
        elif method == "savgol":
            from .savgol_denoise import sg_denoise

            result, _ = sg_denoise(arr)
        elif method == "wavelet_packet":
            from .wavelet_packet import wavelet_packet_denoise

            result, _ = wavelet_packet_denoise(arr)
        elif method == "ceemdan_wp":
            from .emd_denoise import emd_denoise
            from .wavelet_packet import wavelet_packet_denoise

            step1, _ = emd_denoise(arr, method="ceemdan")
            result, _ = wavelet_packet_denoise(step1)
        else:
            raise ValueError("未知去噪方法")
        result = np.asarray(result, dtype=np.float64)
        if result.shape != arr.shape or not np.all(np.isfinite(result)):
            raise ValueError("去噪未返回同时间轴的有限表示")
        return result
    except DenoisingError:
        raise
    except Exception as exc:
        raise DenoisingError(str(method), str(exc)) from exc


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
    b, a = scipy_signal.butter(order, [low, high], btype="band")
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
    b, a = scipy_signal.butter(order, cut, btype="low")
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
    b, a = scipy_signal.butter(order, cut, btype="high")
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
    return xf, yf**2


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
            result["harmonics"].append(
                {
                    "freq": peak_h["freq"],
                    "amp": peak_h["amp"],
                    "order": h,
                }
            )

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
    return float(np.sqrt(np.mean(signal**2)))


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


def _order_band_energy(
    order_axis, spectrum, center_order: float, bandwidth: float
) -> float:
    """计算指定阶次带能量"""
    order_axis = np.asarray(order_axis)
    spectrum = np.asarray(spectrum)
    mask = (order_axis >= center_order - bandwidth) & (
        order_axis <= center_order + bandwidth
    )
    if not np.any(mask):
        return 0.0
    return float(np.sum(spectrum[mask] ** 2))


def estimate_rot_freq_envelope(
    sig: np.ndarray,
    fs: float,
    f_center: float,
    bw: float = 60.0,
    freq_range: Tuple[float, float] = (10, 100),
) -> Optional[float]:
    """兼容适配：独立包络转频候选，算法位于 algorithms.order。"""
    from app.algorithms.order import SpeedSearchRange, estimate_envelope_speed

    result = estimate_envelope_speed(
        sig, fs, f_center, SpeedSearchRange(*freq_range), bw
    )
    return result.frequency_hz if result.status == "valid" else None


def estimate_rot_freq_autocorr(
    sig: np.ndarray,
    fs: float,
    freq_range: Tuple[float, float] = (10, 100),
) -> Optional[float]:
    """兼容适配：独立自相关转频候选，算法位于 algorithms.order。"""
    from app.algorithms.order import SpeedSearchRange, estimate_autocorrelation_speed

    result = estimate_autocorrelation_speed(sig, fs, SpeedSearchRange(*freq_range))
    return result.frequency_hz if result.status == "valid" else None


def estimate_rot_freq_spectrum(
    sig: np.ndarray,
    fs: float,
    freq_range: Tuple[float, float] = (10, 100),
    harmonics_num: int = 5,
    bandwidth_hz: float = 3.0,
    smooth_win_hz: float = 1.5,
) -> float:
    """旧标量接口的薄适配；不可判定时抛错，不再返回默认转频。"""
    from app.algorithms.order import SpeedSearchRange, estimate_spectrum_speed

    result = estimate_spectrum_speed(
        sig,
        fs,
        SpeedSearchRange(*freq_range),
        harmonics_num,
        bandwidth_hz,
        smooth_win_hz,
    )
    if result.status != "valid" or result.frequency_hz is None:
        raise ValueError(result.reason or "标量转频不可判定")
    return float(result.frequency_hz)


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
    """旧字典接口的 Chirp-Z 适配器；数学实现位于 algorithms/gear/fixed_axis。

    resolution_hz 始终是 fs/N 的记录长度分辨率；frequency_step_hz 才是
    CZT 网格间隔。zoom_factor 仅控制网格密度，不宣称超分辨率。
    """
    from app.algorithms.gear.fixed_axis import ZoomParameters, compute_zoom_spectrum

    try:
        result = compute_zoom_spectrum(
            signal,
            fs,
            ZoomParameters(center_freq, bandwidth, max(16, int(zoom_factor) * 64 + 1)),
        )
    except (TypeError, ValueError) as exc:
        return {
            "valid": False,
            "reason": str(exc),
            "zoom_freq_axis": np.array([]),
            "zoom_spectrum": np.array([]),
            "resolution_hz": 0.0,
            "original_resolution_hz": 0.0,
            "zoom_factor": 1,
            "center_freq": center_freq,
            "bandwidth": bandwidth,
            "n_zoom_points": 0,
        }
    return {
        "valid": True,
        "zoom_freq_axis": result.spectrum.frequency_hz,
        "zoom_spectrum": result.spectrum.amplitude,
        "resolution_hz": result.rayleigh_resolution_hz,
        "original_resolution_hz": result.rayleigh_resolution_hz,
        "frequency_step_hz": result.frequency_step_hz,
        "resolution_contract": result.resolution_contract,
        "zoom_factor": 1,
        "center_freq": center_freq,
        "bandwidth": bandwidth,
        "n_zoom_points": len(result.spectrum.amplitude),
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
    b, a = scipy_signal.butter(order, cut, btype="low")

    # 分离实部和虚部，分别滤波
    real_part = scipy_signal.filtfilt(b, a, np.real(signal))
    imag_part = scipy_signal.filtfilt(b, a, np.imag(signal))

    return real_part + 1.0j * imag_part
