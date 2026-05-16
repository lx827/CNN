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

    features = {
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
    features.update(_compute_dynamic_baseline_features(arr))
    features.update(compute_nonparam_cusum_features(arr))
    return features


def _compute_dynamic_baseline_features(signal: np.ndarray) -> Dict[str, float]:
    """
    基于当前批次内滑动窗口的鲁棒基线/趋势指标。

    没有长期历史时，使用窗口中位数 + MAD、EWMA、CUSUM 评估本批次是否出现
    持续偏移或突发冲击，避免完全依赖固定阈值。
    """
    arr = np.asarray(signal, dtype=np.float64)
    if len(arr) < 512:
        return {
            "rms_mad_z": 0.0,
            "kurtosis_mad_z": 0.0,
            "ewma_drift": 0.0,
            "cusum_score": 0.0,
        }

    n_windows = min(32, max(8, len(arr) // 1024))
    win = max(128, len(arr) // n_windows)
    rms_series = []
    kurt_series = []
    for start in range(0, len(arr) - win + 1, win):
        chunk = arr[start:start + win]
        if len(chunk) < 128:
            continue
        rms_series.append(float(np.sqrt(np.mean(chunk ** 2))))
        try:
            kurt_series.append(float(stats.kurtosis(chunk, fisher=False)))
        except Exception:
            kurt_series.append(3.0)

    if len(rms_series) < 4:
        return {
            "rms_mad_z": 0.0,
            "kurtosis_mad_z": 0.0,
            "ewma_drift": 0.0,
            "cusum_score": 0.0,
        }

    def robust_z(series):
        x = np.asarray(series, dtype=np.float64)
        med = float(np.median(x))
        mad = float(np.median(np.abs(x - med)))
        sigma = max(1.4826 * mad, 1e-12)
        return np.abs((x - med) / sigma), med, sigma

    rms_z, _, _ = robust_z(rms_series)
    kurt_z, _, _ = robust_z(kurt_series)

    # EWMA/CUSUM 使用 RMS 序列，捕捉缓慢上升趋势。
    rms_z_signed = np.asarray(rms_series, dtype=np.float64)
    median_rms = float(np.median(rms_z_signed))
    mad_rms = max(1.4826 * float(np.median(np.abs(rms_z_signed - median_rms))), 1e-12)
    z = (rms_z_signed - median_rms) / mad_rms
    ewma = 0.0
    for val in z:
        ewma = 0.2 * float(val) + 0.8 * ewma

    c_pos = 0.0
    c_neg = 0.0
    for val in z:
        c_pos = max(0.0, c_pos + float(val) - 0.5)
        c_neg = max(0.0, c_neg - float(val) - 0.5)

    return {
        "rms_mad_z": round(float(np.max(rms_z)), 4),
        "kurtosis_mad_z": round(float(np.max(kurt_z)), 4),
        "ewma_drift": round(float(abs(ewma)), 4),
        "cusum_score": round(float(max(c_pos, c_neg)), 4),
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
    估算 IMF 能量分布
    用频带能量划分近似 IMF 分量能量占比，用于健康度评分和前端 IMF 能量图展示
    """
    arr = np.array(signal)
    xf, yf = compute_fft(arr, sample_rate)
    yf = np.array(yf)
    xf = np.array(xf)

    # 把频谱分成 5 个频带，估算 5 个 IMF 分量的能量
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


# ---------------------------------------------------------------------------
# 非参数 CUSUM 控制图
# ---------------------------------------------------------------------------


def _sign_cusum(series: np.ndarray, reference: Optional[float] = None) -> Tuple[float, float, Dict]:
    """
    符号统计非参数 CUSUM

    ALGORITHMS.md §4.4.1.3：
    基于符号统计量的 CUSUM，不假设数据服从正态分布，
    对重尾、偏态的工业振动数据更鲁棒。

    算法流程：
    1. 以参考值 μ₀（默认为中位数）为基线
    2. 计算 sign(x_i - μ₀)：正偏差记 +1，负偏差记 -1
    3. CUSUM 累积：C⁺ = max(0, C⁺ + sign - K), C⁻ = max(0, C⁻ - sign - K)
    4. K 为参考值（通常取 0.5），H 为决策限（通常取 4~5σ_equivalent）

    与参数 CUSUM 的区别：
    - 参数 CUSUM 使用 x_i - μ₀ - K（连续值），依赖正态假设
    - 符号 CUSUM 仅用 sign(x_i - μ₀)（离散值），对任何分布都适用
    - 对异常值不敏感（只看方向不看大小）

    Args:
        series: 观测序列（如 RMS 滑动窗口序列）
        reference: 基线值，None 则取中位数

    Returns:
        (C⁺_max, C⁻_max, info_dict)
    """
    x = np.asarray(series, dtype=np.float64)
    if len(x) < 4:
        return 0.0, 0.0, {"method": "sign_cusum", "error": "insufficient_data"}

    # 基线：中位数（比均值更抗异常值）
    if reference is None:
        reference = float(np.median(x))

    # 符号统计量
    signs = np.sign(x - reference)
    K = 0.5  # 参考值（符号统计的K固定为0.5）

    c_pos = 0.0
    c_neg = 0.0
    c_pos_max = 0.0
    c_neg_max = 0.0

    for s in signs:
        c_pos = max(0.0, c_pos + s - K)
        c_neg = max(0.0, c_neg - s - K)
        c_pos_max = max(c_pos_max, c_pos)
        c_neg_max = max(c_neg_max, c_neg)

    # 决策限 H：对于符号统计，等效 σ ≈ 1（因为 sign 只有 ±1）
    # H ≈ 4~5 × n_points的等效标准差
    # 实际工程中 H 取 n/4 到 n/2 之间的值
    n = len(x)
    H = max(4.0, n * 0.1)

    return float(c_pos_max), float(c_neg_max), {
        "method": "sign_cusum",
        "reference": round(reference, 6),
        "K": K,
        "H": round(H, 2),
        "alarm_positive": bool(c_pos_max > H),
        "alarm_negative": bool(c_neg_max > H),
    }


def _mann_whitney_cusum(
    series: np.ndarray,
    window_size: int = 10,
    reference_window: Optional[np.ndarray] = None,
) -> Tuple[float, float, Dict]:
    """
    Mann-Whitney 统计非参数 CUSUM

    ALGORITHMS.md §4.4.1.3：
    基于 Mann-Whitney U 统计量的 CUSUM，不假设分布形式，
    对偏态分布和异常值更鲁棒。

    算法流程：
    1. 将前 window_size 个点作为参考窗口（健康基线）
    2. 对每个滑动窗口，计算与参考窗口的 Mann-Whitney U 统计量
    3. 将 U 统计量归一化为 z 分数
    4. CUSUM 累积归一化 z 分数

    Mann-Whitney U 检验原理：
    - H0：两个窗口来自同一分布（健康状态）
    - U = min(U₁, U₂)，其中 U₁ = ∑∑ I(x₁_i > x₂_j)
    - z = (U - E[U]) / σ_U，E[U] = n₁·n₂/2，σ_U = sqrt(n₁·n₂·(n₁+n₂+1)/12)

    Args:
        series: 观测序列
        window_size: 滑动窗口大小
        reference_window: 健康基线窗口，None 则取序列前 window_size 个点

    Returns:
        (C⁺_max, C⁻_max, info_dict)
    """
    x = np.asarray(series, dtype=np.float64)
    n = len(x)

    if n < window_size * 2:
        return 0.0, 0.0, {"method": "mann_whitney_cusum", "error": "insufficient_data"}

    # 参考窗口（健康基线）
    if reference_window is None:
        reference_window = x[:window_size]
    ref = np.asarray(reference_window, dtype=np.float64)
    n1 = len(ref)

    # 计算每个滑动窗口与参考窗口的 Mann-Whitney z 分数
    z_scores = []
    for start in range(window_size, n - window_size + 1, max(1, window_size // 4)):
        current_window = x[start:start + window_size]
        if len(current_window) < window_size:
            continue
        n2 = len(current_window)

        # 计算 Mann-Whitney U 统计量
        u1 = 0.0
        for x1 in ref:
            for x2 in current_window:
                if x1 > x2:
                    u1 += 1.0
                elif x1 == x2:
                    u1 += 0.5

        u2 = n1 * n2 - u1
        u_min = min(u1, u2)

        # 归一化
        e_u = n1 * n2 / 2.0
        var_u = n1 * n2 * (n1 + n2 + 1) / 12.0
        sigma_u = np.sqrt(var_u) if var_u > 0 else 1.0

        z = (u_min - e_u) / sigma_u
        z_scores.append(z)

    if len(z_scores) < 2:
        return 0.0, 0.0, {"method": "mann_whitney_cusum", "error": "insufficient_z_scores"}

    # CUSUM 累积 z 分数
    K_mw = 0.5  # 参考值
    c_pos = 0.0
    c_neg = 0.0
    c_pos_max = 0.0
    c_neg_max = 0.0

    for z_val in z_scores:
        c_pos = max(0.0, c_pos + z_val - K_mw)
        c_neg = max(0.0, c_neg - z_val - K_mw)
        c_pos_max = max(c_pos_max, c_pos)
        c_neg_max = max(c_neg_max, c_neg)

    # 决策限：基于 z 分数的 CUSUM，H ≈ 4~5
    H_mw = 4.0

    return float(c_pos_max), float(c_neg_max), {
        "method": "mann_whitney_cusum",
        "window_size": window_size,
        "n1": n1,
        "K": K_mw,
        "H": H_mw,
        "n_z_scores": len(z_scores),
        "alarm_positive": bool(c_pos_max > H_mw),
        "alarm_negative": bool(c_neg_max > H_mw),
    }


def compute_nonparam_cusum_features(signal: np.ndarray) -> Dict[str, float]:
    """
    计算非参数 CUSUM 特征（符号统计 + Mann-Whitney）

    ALGORITHMS.md §4.4.1.3：
    工业振动数据往往非高斯、重尾、偏态。
    非参数 CUSUM 基于符号统计或 Mann-Whitney 统计量，
    不假设分布形式，对异常值和偏态分布更鲁棒。

    Args:
        signal: 输入振动信号

    Returns:
        {
            "sign_cusum_positive": float,
            "sign_cusum_negative": float,
            "sign_cusum_alarm": bool,
            "mw_cusum_positive": float,
            "mw_cusum_negative": float,
            "mw_cusum_alarm": bool,
        }
    """
    arr = np.asarray(signal, dtype=np.float64)
    if len(arr) < 512:
        return {
            "sign_cusum_positive": 0.0,
            "sign_cusum_negative": 0.0,
            "sign_cusum_alarm": False,
            "mw_cusum_positive": 0.0,
            "mw_cusum_negative": 0.0,
            "mw_cusum_alarm": False,
        }

    # 滑动窗口 RMS 序列（与 _compute_dynamic_baseline_features 相同的窗口策略）
    n_windows = min(32, max(8, len(arr) // 1024))
    win = max(128, len(arr) // n_windows)
    rms_series = []
    for start in range(0, len(arr) - win + 1, win):
        chunk = arr[start:start + win]
        if len(chunk) < 128:
            continue
        rms_series.append(float(np.sqrt(np.mean(chunk ** 2))))

    if len(rms_series) < 4:
        return {
            "sign_cusum_positive": 0.0,
            "sign_cusum_negative": 0.0,
            "sign_cusum_alarm": False,
            "mw_cusum_positive": 0.0,
            "mw_cusum_negative": 0.0,
            "mw_cusum_alarm": False,
        }

    rms_array = np.array(rms_series)

    # 符号 CUSUM
    sign_c_pos, sign_c_neg, sign_info = _sign_cusum(rms_array)

    # Mann-Whitney CUSUM
    mw_c_pos, mw_c_neg, mw_info = _mann_whitney_cusum(rms_array, window_size=max(5, len(rms_array) // 4))

    return {
        "sign_cusum_positive": round(sign_c_pos, 4),
        "sign_cusum_negative": round(sign_c_neg, 4),
        "sign_cusum_alarm": sign_info.get("alarm_positive", False),
        "mw_cusum_positive": round(mw_c_pos, 4),
        "mw_cusum_negative": round(mw_c_neg, 4),
        "mw_cusum_alarm": mw_info.get("alarm_positive", False),
    }
