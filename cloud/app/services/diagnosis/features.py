"""
特征提取模块

统一提供时域、频域、包络域、阶次域的特征提取接口。
"""
import numpy as np
from scipy import stats
from scipy.fft import rfft, rfftfreq
from scipy.signal import hilbert, detrend
from typing import Dict, List, Tuple, Optional

from .signal_utils import (
    prepare_signal, rms, peak_value, crest_factor, kurtosis, skewness,
    compute_fft_spectrum, bandpass_filter, lowpass_filter, _band_energy,
    estimate_rot_freq_spectrum as _estimate_rot_freq_simple,
)


def compute_time_features(signal: np.ndarray) -> Dict[str, float]:
    """
    计算时域统计特征

    Returns:
        {
            "peak", "rms", "mean_abs", "kurtosis", "skewness",
            "margin", "shape_factor", "impulse_factor", "crest_factor",
        }
    """
    arr = prepare_signal(signal)
    if len(arr) == 0:
        return {}

    peak = peak_value(arr)
    rms_val = rms(arr)
    mean_abs = float(np.mean(np.abs(arr)))

    kurt = kurtosis(arr, fisher=False)
    skew = skewness(arr)

    margin = peak / rms_val if rms_val > 1e-12 else 0.0
    shape_factor = rms_val / mean_abs if mean_abs > 1e-12 else 0.0
    impulse_factor = peak / mean_abs if mean_abs > 1e-12 else 0.0
    crest = crest_factor(arr)

    return {
        "peak": round(peak, 6),
        "rms": round(rms_val, 6),
        "mean_abs": round(mean_abs, 6),
        "kurtosis": round(kurt, 4),
        "skewness": round(skew, 4),
        "margin": round(margin, 4),
        "shape_factor": round(shape_factor, 4),
        "impulse_factor": round(impulse_factor, 4),
        "crest_factor": round(crest, 4),
    }


def compute_fft_features(
    signal: np.ndarray,
    fs: float,
    gear_teeth: Optional[Dict] = None,
    bearing_params: Optional[Dict] = None,
    rot_freq: Optional[float] = None,
) -> Dict[str, float]:
    """
    从 FFT 频谱提取齿轮/轴承相关特征

    Args:
        signal: 输入信号
        fs: 采样率
        gear_teeth: 齿轮参数 {input: Z_in, output: Z_out}
        bearing_params: 轴承参数 {n, d, D, alpha}
        rot_freq: 轴转频 (Hz)，不传则自动估计

    Returns:
        特征字典
    """
    arr = prepare_signal(signal)
    xf, yf = compute_fft_spectrum(arr, fs)
    yf = np.array(yf)
    xf = np.array(xf)
    total_energy = float(np.sum(yf ** 2)) + 1e-10

    features = {}

    # 估计转频
    if rot_freq is None:
        rot_freq = _estimate_rot_freq_simple(arr, fs)
    features["estimated_rot_freq"] = round(rot_freq, 3)

    # --- 齿轮特征 ---
    if gear_teeth and isinstance(gear_teeth, dict):
        z_in = gear_teeth.get("input") or 0
        if z_in > 0:
            mesh_freq = rot_freq * z_in
            features["mesh_freq_hz"] = round(mesh_freq, 2)
            mesh_amp = _band_energy(xf, yf, mesh_freq, 5.0)
            features["mesh_freq_ratio"] = round(mesh_amp / total_energy, 6)

            sideband_total = 0.0
            sideband_count = 0
            for n in range(1, 4):
                sb_low = mesh_freq - n * rot_freq
                sb_high = mesh_freq + n * rot_freq
                sb_amp = _band_energy(xf, yf, sb_low, 2.0) + _band_energy(xf, yf, sb_high, 2.0)
                sideband_total += sb_amp
                if sb_amp > mesh_amp * 0.05:
                    sideband_count += 1
            features["sideband_total_ratio"] = round(sideband_total / total_energy, 6)
            features["sideband_count"] = sideband_count

    # --- 轴承特征 ---
    if bearing_params and isinstance(bearing_params, dict):
        bfreqs = _compute_bearing_fault_freqs(rot_freq, bearing_params)
        for name, f_hz in bfreqs.items():
            features[f"{name}_hz"] = round(f_hz, 2)
            f_amp = _band_energy(xf, yf, f_hz, 3.0)
            features[f"{name}_ratio"] = round(f_amp / total_energy, 6)
            harmonic_total = 0.0
            for h in range(2, 4):
                harmonic_total += _band_energy(xf, yf, f_hz * h, 3.0)
            features[f"{name}_harmonic_ratio"] = round(harmonic_total / total_energy, 6)

    return features


def compute_envelope_features(
    envelope_freq: list,
    envelope_amp: list,
    bearing_params: Optional[Dict] = None,
    rot_freq: Optional[float] = None,
) -> Dict[str, float]:
    """
    从已计算好的包络谱提取轴承故障特征能量比

    Args:
        envelope_freq: 包络谱频率轴 (Hz)，由外部轴承方法（envelope_analysis/kurtogram等）提供
        envelope_amp:  包络谱幅值
        bearing_params: 轴承几何参数 {n, d, D, alpha}
        rot_freq:       轴转频 (Hz)

    Returns:
        特征字典，含 BPFO/BPFI/BSF/FTF 在各特征频率处的能量比
    """
    if envelope_freq is None or envelope_amp is None or len(envelope_freq) == 0:
        return {"total_env_energy": 0.0}

    xf = np.array(envelope_freq, dtype=np.float64)
    yf = np.array(envelope_amp, dtype=np.float64)
    total_energy = float(np.sum(yf ** 2)) + 1e-10
    features = {"total_env_energy": round(float(total_energy), 6)}

    if not bearing_params or not isinstance(bearing_params, dict):
        return features

    # 提取轴承特征频率
    n_val = bearing_params.get("n")
    d_val = bearing_params.get("d")
    D_val = bearing_params.get("D")
    alpha_val = bearing_params.get("alpha")

    try:
        n_balls = int(float(n_val)) if n_val is not None else 0
        d = float(d_val) if d_val is not None else 0.0
        D = float(D_val) if D_val is not None else 0.0
        alpha = np.radians(float(alpha_val)) if alpha_val is not None else 0.0
    except (TypeError, ValueError):
        return features

    if n_balls <= 0 or d <= 1e-9 or D <= 1e-9:
        return features

    if rot_freq is None or rot_freq <= 0:
        return features

    cos_a = np.cos(alpha)
    dd = (d / D) * cos_a

    freqs = {
        "BPFO": (n_balls / 2.0) * rot_freq * (1 - dd),
        "BPFI": (n_balls / 2.0) * rot_freq * (1 + dd),
        "BSF":  (D / (2.0 * d)) * rot_freq * (1 - dd ** 2),
    }  # FTF 是保持架频率，不作为故障指示器

    for name, f_hz in freqs.items():
        if f_hz <= 0 or f_hz > envelope_freq[-1]:
            continue
        # 能量窗口：±2% 理论频率
        bw = max(1.0, f_hz * 0.02)
        env_amp_val = _band_energy(xf, yf, f_hz, bw)
        features[f"{name}_env_ratio"] = round(env_amp_val / total_energy, 6)
        harmonic_total = 0.0
        for h in range(2, 5):
            h_freq = f_hz * h
            if h_freq <= envelope_freq[-1]:
                harmonic_total += _band_energy(xf, yf, h_freq, bw)
        features[f"{name}_env_harmonic_ratio"] = round(harmonic_total / total_energy, 6)

    return features


def remove_dc(signal: List[float]) -> np.ndarray:
    """去除信号线性趋势与直流分量（基频漂移导致的 y=kx+b 趋势）"""
    arr = np.array(signal, dtype=np.float64)
    return detrend(arr, type='linear')


def compute_channel_features(signal: List[float]) -> Dict[str, float]:
    """
    计算单通道振动信号的统计特征指标
    用于通道级阈值告警。
    """
    arr = remove_dc(signal)
    if len(arr) == 0:
        return {}

    # 基本统计量
    peak = float(np.max(np.abs(arr)))
    rms_val = float(np.sqrt(np.mean(arr ** 2)))
    mean_abs = float(np.mean(np.abs(arr)))

    # 峭度与偏度
    kurt = float(stats.kurtosis(arr, fisher=False))
    skew = float(stats.skew(arr))

    # 无量纲指标
    # Margin = Peak / (mean(sqrt(|x|)))^2
    mean_sqrt = float(np.mean(np.sqrt(np.abs(arr) + 1e-12)))
    margin = peak / (mean_sqrt ** 2) if mean_sqrt > 1e-12 else 0.0
    shape_factor = rms_val / mean_abs if mean_abs > 1e-12 else 0.0
    impulse_factor = peak / mean_abs if mean_abs > 1e-12 else 0.0
    crest = peak / rms_val if rms_val > 1e-12 else 0.0

    return {
        "peak": round(peak, 6),
        "rms": round(rms_val, 6),
        "kurtosis": round(kurt, 4),
        "skewness": round(skew, 4),
        "margin": round(margin, 4),
        "crest_factor": round(crest, 4),
        "shape_factor": round(shape_factor, 4),
        "impulse_factor": round(impulse_factor, 4),
    }


def compute_fft(signal: List[float], sample_rate: int = 25600):
    """计算 FFT 频谱"""
    arr = remove_dc(signal)
    n = len(arr)
    yf = np.abs(rfft(arr))
    xf = rfftfreq(n, 1 / sample_rate)
    return xf.tolist(), yf.tolist()


def compute_imf_energy(signal: List[float], sample_rate: int = 25600) -> Dict[str, float]:
    """
    模拟 IMF 能量分布
    真实场景需要 EMD/VMD 分解，这里用频带能量近似模拟
    """
    arr = np.array(signal)
    xf, yf = compute_fft(arr, sample_rate)
    yf = np.array(yf)
    xf = np.array(xf)

    # 把频谱分成 5 个频带，模拟 5 个 IMF 分量的能量
    max_freq = sample_rate / 2
    band_width = max_freq / 5
    bands = [(i * band_width, (i + 1) * band_width) for i in range(5)]
    energy = {}
    total = 0.0
    for i, (low, high) in enumerate(bands, 1):
        mask = (xf >= low) & (xf < high)
        e = float(np.sum(yf[mask] ** 2))
        energy[f"IMF{i}"] = e
        total += e

    if total > 0:
        for k in energy:
            energy[k] = round(energy[k] / total * 100, 2)
    return energy


def _get_channel_params(device, channel_index, field):
    """
    从设备配置中按通道索引提取参数。
    支持两种格式：
      - 旧格式（设备级共用）: {input:18, output:27}
      - 新格式（通道级独立）: {"1":{input:18}, "2":{input:27}}
    """
    raw = getattr(device, field, None) if device else None
    if raw is None:
        return None
    ch_key = str(channel_index)
    if ch_key in raw:
        return raw[ch_key]
    if "input" in raw or "n" in raw or "output" in raw:
        return raw
    return None


def _compute_bearing_fault_freqs(rot_freq: float, bearing_params: dict) -> dict:
    """
    计算轴承故障特征频率 (Hz)
    公式针对深沟球轴承 / 圆柱滚子轴承通用形式
    """
    n = bearing_params.get("n") or 0
    d = bearing_params.get("d") or 0
    D = bearing_params.get("D") or 0
    alpha = np.radians(bearing_params.get("alpha") or 0)

    if n <= 0 or d <= 0 or D <= 0:
        return {}

    cos_a = np.cos(alpha)
    dd = (d / D) * cos_a

    return {
        "BPFO": (n / 2.0) * rot_freq * (1 - dd),
        "BPFI": (n / 2.0) * rot_freq * (1 + dd),
        "BSF":  (D / (2.0 * d)) * rot_freq * (1 - dd ** 2),
        "FTF":  0.5 * rot_freq * (1 - dd),
    }


def _compute_bearing_fault_orders(rot_freq: float, bearing_params: dict) -> dict:
    """计算轴承故障特征阶次 (order = freq / rot_freq)"""
    if rot_freq <= 0:
        return {}
    freqs = _compute_bearing_fault_freqs(rot_freq, bearing_params)
    return {k: v / rot_freq for k, v in freqs.items()}
