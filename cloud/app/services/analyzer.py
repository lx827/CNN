"""
故障分析引擎

分析流程：
  1. 优先调用神经网络模型（nn_predictor.py）
  2. 如果神经网络未启用，调用新诊断引擎（DiagnosisEngine，支持多种算法配置）
  3. 如果新引擎失败，回退到简化规则算法（FFT + IMF能量 + 阈值判断）

注意：旧规则算法保留作为回退方案，新引擎为默认诊断方式。
"""
import numpy as np
from scipy.fft import rfft, rfftfreq
from scipy.signal import hilbert, detrend
from scipy import stats
from typing import Dict, List
import random

from app.services.nn_predictor import predict as nn_predict
from app.services.diagnosis import DiagnosisEngine, BearingMethod, GearMethod, DenoiseMethod
from app.services.diagnosis.utils import estimate_rot_freq_spectrum as _estimate_rot_freq_spectrum


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
    rms = float(np.sqrt(np.mean(arr ** 2)))
    mean_abs = float(np.mean(np.abs(arr)))

    # 峭度与偏度
    kurtosis = float(stats.kurtosis(arr, fisher=False))
    skewness = float(stats.skew(arr))

    # 无量纲指标
    margin = peak / rms if rms > 1e-12 else 0.0
    shape_factor = rms / mean_abs if mean_abs > 1e-12 else 0.0
    impulse_factor = peak / mean_abs if mean_abs > 1e-12 else 0.0
    crest_factor = peak / rms if rms > 1e-12 else 0.0

    return {
        "peak": round(peak, 6),
        "rms": round(rms, 6),
        "kurtosis": round(kurtosis, 4),
        "skewness": round(skewness, 4),
        "margin": round(margin, 4),
        "crest_factor": round(crest_factor, 4),
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


# 特征阈值基准（与 alarm_service.py 保持一致，用于归一化严重度）
# 基于真实 .npy 数据校准（H组健康 / I,O组故障）
# H组: Peak=0.045 RMS=0.007 Kurt=3.75 Crest=6.66 Skew=0.03 Impulse=8.58
# I组: Peak=0.190 RMS=0.024 Kurt=6.39 Crest=8.00 Skew=0.14 Impulse=11.34
# O组: Peak=0.068 RMS=0.007 Kurt=8.71 Crest=10.42 Skew=0.10 Impulse=14.35
_FEATURE_BASELINES = {
    "rms": {"baseline": 0.008, "warning": 0.015, "critical": 0.030},
    "peak": {"baseline": 0.060, "warning": 0.100, "critical": 0.150},
    "kurtosis": {"baseline": 4.00, "warning": 5.50, "critical": 7.00},  # fisher=False
    "crest_factor": {"baseline": 7.50, "warning": 9.00, "critical": 10.50},
    "skewness": {"baseline": 0.00, "warning": 0.20, "critical": 0.50},
    "impulse_factor": {"baseline": 9.50, "warning": 11.00, "critical": 13.00},
}


def _feature_severity(value: float, metric: str) -> float:
    """
    计算单一特征的严重度 (0.0 ~ 1.0+)
    value: 特征值
    metric: 特征名称
    """
    cfg = _FEATURE_BASELINES.get(metric)
    if not cfg:
        return 0.0
    baseline = cfg["baseline"]
    critical = cfg["critical"]
    if value <= baseline or critical <= baseline:
        return 0.0
    return max(0.0, min(1.0, (abs(value) - baseline) / (critical - baseline)))


def _compute_order_spectrum_simple(sig: np.ndarray, fs: float, rot_freq: float,
                                     samples_per_rev: int = 1024, max_order: int = 50):
    """简化阶次跟踪（单帧），用于诊断内部计算"""
    duration = len(sig) / fs
    num_revs = duration * rot_freq
    n_points = int(num_revs * samples_per_rev)
    if n_points < 10:
        return np.array([0.0]), np.array([0.0])

    times = np.arange(len(sig)) / fs
    target_times = np.linspace(0, duration, n_points, endpoint=False)
    sig_order = np.interp(target_times, times, sig, left=sig[0], right=sig[-1])
    sig_order = sig_order - sig_order.mean()

    N = len(sig_order)
    window = np.hanning(N)
    sig_windowed = sig_order * window
    amplitude_scale = np.sqrt(N / np.sum(window ** 2))
    spectrum = np.abs(rfft(sig_windowed))[:N // 2] * amplitude_scale
    orders = np.arange(len(spectrum)) / num_revs

    mask = orders <= max_order
    return orders[mask], spectrum[mask]


def _rule_based_analyze(channels_data: Dict[str, List[float]], sample_rate: int = 25600, device=None):
    """
    多特征综合规则诊断算法（回退方案）

    融合：时域统计特征 + 频谱特征 + 包络特征 + 阶次特征
    支持齿轮/轴承参数化诊断
    """
    # 1. 计算所有通道的时域特征
    all_features = []
    for ch_name, signal in channels_data.items():
        features = compute_channel_features(signal)
        if features:
            all_features.append(features)

    if not all_features:
        return {
            "health_score": 100,
            "fault_probabilities": {"正常运行": 1.0},
            "imf_energy": {},
            "status": "normal",
            "order_analysis": None,
            "rot_freq": None,
        }

    # 2. 多通道平均时域特征
    avg_features = {}
    for key in ["rms", "peak", "kurtosis", "crest_factor", "skewness", "impulse_factor"]:
        values = [f.get(key, 0) for f in all_features if f.get(key) is not None]
        avg_features[key] = np.mean(values) if values else 0.0

    # 3. 时域特征严重度
    sev = {
        "rms": _feature_severity(avg_features["rms"], "rms"),
        "peak": _feature_severity(avg_features["peak"], "peak"),
        "kurtosis": _feature_severity(avg_features["kurtosis"], "kurtosis"),
        "crest_factor": _feature_severity(avg_features["crest_factor"], "crest_factor"),
        "skewness": _feature_severity(abs(avg_features["skewness"]), "skewness"),
        "impulse_factor": _feature_severity(avg_features["impulse_factor"], "impulse_factor"),
    }

    # 4. 获取设备参数 & 估计转频
    gear_teeth = getattr(device, "gear_teeth", None) if device else None
    bearing_params = getattr(device, "bearing_params", None) if device else None

    first_channel = list(channels_data.values())[0]
    first_arr = np.array(first_channel, dtype=np.float64)
    rot_freq = _estimate_rot_freq_spectrum(first_arr, sample_rate)

    # 5. 频谱/包络/阶次特征提取
    xf, yf = compute_fft(first_channel, sample_rate)
    spec_features = _extract_spectrum_features(xf, yf, rot_freq, gear_teeth, bearing_params)

    env_freq, env_amp = compute_envelope_spectrum(first_channel, sample_rate, max_freq=1000)
    env_features = _extract_envelope_features(env_freq, env_amp, rot_freq, bearing_params)

    order_axis, spectrum = _compute_order_spectrum_simple(
        first_arr, sample_rate, rot_freq, samples_per_rev=1024, max_order=50
    )
    order_features = _extract_order_features(order_axis, spectrum, rot_freq, gear_teeth, bearing_params)

    # 6. 频域/阶次严重度（归一化到 0~1）
    mesh_sev = min(1.0, spec_features.get("mesh_freq_ratio", 0) * 20)
    sideband_sev = min(1.0, spec_features.get("sideband_total_ratio", 0) * 30)
    mesh_order_sev = min(1.0, order_features.get("mesh_order_ratio", 0) * 20)
    sideband_order_sev = min(1.0, order_features.get("sideband_order_total_ratio", 0) * 30)

    bpfo_env_sev = min(1.0, env_features.get("BPFO_env_ratio", 0) * 50)
    bpfi_env_sev = min(1.0, env_features.get("BPFI_env_ratio", 0) * 50)
    bsf_env_sev = min(1.0, env_features.get("BSF_env_ratio", 0) * 50)

    bpfo_order_sev = min(1.0, order_features.get("BPFO_order_ratio", 0) * 50)
    bpfi_order_sev = min(1.0, order_features.get("BPFI_order_ratio", 0) * 50)
    bsf_order_sev = min(1.0, order_features.get("BSF_order_ratio", 0) * 50)

    max_bearing_env_sev = max(bpfo_env_sev, bpfi_env_sev, bsf_env_sev)
    max_bearing_order_sev = max(bpfo_order_sev, bpfi_order_sev, bsf_order_sev)

    # 7. 故障类型判别（融合时域 + 频谱 + 包络 + 阶次）
    fault_scores = {
        "正常运行": 1.0,
        "齿轮磨损": (
            sev["rms"] * 0.25 + sev["peak"] * 0.20 + sev["crest_factor"] * 0.10 +
            mesh_sev * 0.20 + sideband_sev * 0.15 + mesh_order_sev * 0.10
        ),
        "轴承内圈故障": (
            sev["kurtosis"] * 0.20 + sev["crest_factor"] * 0.10 + sev["impulse_factor"] * 0.10 +
            bpfi_env_sev * 0.30 + bpfi_order_sev * 0.20 + sev["peak"] * 0.10
        ),
        "轴承外圈故障": (
            sev["kurtosis"] * 0.15 + sev["crest_factor"] * 0.10 + sev["rms"] * 0.10 +
            bpfo_env_sev * 0.35 + bpfo_order_sev * 0.20 + sev["impulse_factor"] * 0.10
        ),
        "滚动体故障": (
            sev["kurtosis"] * 0.15 + sev["peak"] * 0.15 + sev["impulse_factor"] * 0.10 +
            bsf_env_sev * 0.30 + bsf_order_sev * 0.20 + sev["crest_factor"] * 0.10
        ),
        "轴不对中": (
            sev["rms"] * 0.30 + sev["skewness"] * 0.25 + sev["peak"] * 0.15 +
            mesh_sev * 0.10 + sideband_sev * 0.10 + sideband_order_sev * 0.10
        ),
        "基础松动": (
            sev["peak"] * 0.25 + sev["rms"] * 0.15 + sev["crest_factor"] * 0.15 +
            sev["skewness"] * 0.10 + mesh_sev * 0.10 + sideband_sev * 0.10 +
            max_bearing_env_sev * 0.15
        ),
    }

    # 8. 正常运行概率衰减
    normal_decay = 1.0
    normal_decay *= max(0.0, 1.0 - sev["rms"] * 0.30)
    normal_decay *= max(0.0, 1.0 - sev["kurtosis"] * 0.45)
    normal_decay *= max(0.0, 1.0 - sev["crest_factor"] * 0.30)
    normal_decay *= max(0.0, 1.0 - sev["peak"] * 0.15)
    normal_decay *= max(0.0, 1.0 - sev["skewness"] * 0.20)
    normal_decay *= max(0.0, 1.0 - sev["impulse_factor"] * 0.25)
    normal_decay *= max(0.0, 1.0 - mesh_sev * 0.25)
    normal_decay *= max(0.0, 1.0 - sideband_sev * 0.15)
    normal_decay *= max(0.0, 1.0 - max_bearing_env_sev * 0.35)
    normal_decay *= max(0.0, 1.0 - max_bearing_order_sev * 0.25)
    fault_scores["正常运行"] = normal_decay

    # 9. 归一化概率
    total = sum(fault_scores.values())
    if total > 0:
        fault_probabilities = {k: round(v / total, 4) for k, v in fault_scores.items()}
    else:
        fault_probabilities = {"正常运行": 1.0}

    max_fault_sev = max(v for k, v in fault_scores.items() if k != "正常运行")
    health_score = int(max(0, min(100,
        fault_probabilities.get("正常运行", 0) * 100 - max_fault_sev * 30 - random.uniform(0, 3)
    )))
    status = "normal" if health_score >= 80 else "warning" if health_score >= 60 else "fault"

    # 10. IMF 能量
    imf_energy = compute_imf_energy(first_channel, sample_rate)

    # 11. 构建 order_analysis 报告
    order_analysis = {
        "rot_freq_hz": round(rot_freq, 3),
        "rot_rpm": round(rot_freq * 60, 1),
        "spectrum_features": {k: round(v, 6) for k, v in spec_features.items()},
        "envelope_features": {k: round(v, 6) for k, v in env_features.items()},
        "order_features": {k: round(v, 6) for k, v in order_features.items()},
    }

    # 调试日志
    print(f"[规则诊断] 时域: RMS={avg_features['rms']:.3f}(sev={sev['rms']:.2f}), "
          f"Kurt={avg_features['kurtosis']:.2f}(sev={sev['kurtosis']:.2f}), "
          f"Crest={avg_features['crest_factor']:.2f}(sev={sev['crest_factor']:.2f}) | "
          f"频域: mesh={mesh_sev:.2f}, sb={sideband_sev:.2f} | "
          f"包络: BPFO={bpfo_env_sev:.2f}, BPFI={bpfi_env_sev:.2f}, BSF={bsf_env_sev:.2f} | "
          f"阶次: BPFO={bpfo_order_sev:.2f}, BPFI={bpfi_order_sev:.2f}, BSF={bsf_order_sev:.2f} | "
          f"健康度={health_score}, 状态={status}")

    return {
        "health_score": health_score,
        "fault_probabilities": fault_probabilities,
        "imf_energy": imf_energy,
        "status": status,
        "order_analysis": order_analysis,
        "rot_freq": rot_freq,
    }


def compute_envelope_spectrum(signal: List[float], sample_rate: int = 25600, max_freq: int = 1000):
    """
    计算包络谱（Envelope Spectrum）

    用于轴承故障诊断，通过希尔伯特变换提取信号包络，
    再对包络信号做 FFT，检测轴承特征频率（BPFO/BPFI/BSF/FTF）。

    Args:
        signal: 时域信号数组
        sample_rate: 采样率 Hz
        max_freq: 返回的最大频率 Hz（轴承故障频率通常 < 500Hz）

    Returns:
        freq: 频率数组 (Hz)
        amp: 包络谱幅值数组
    """
    arr = remove_dc(signal)

    # 1. 带通滤波（保留 1kHz~5kHz 的共振频带，可选）
    # 简化版本：直接用原始信号做希尔伯特变换

    # 2. 希尔伯特变换获取包络
    analytic_signal = hilbert(arr)
    envelope = np.abs(analytic_signal)

    # 3. 去除直流分量（零均值化）
    envelope = envelope - np.mean(envelope)

    # 4. 对包络信号做 FFT
    n = len(envelope)
    yf = np.abs(rfft(envelope))
    xf = rfftfreq(n, 1 / sample_rate)

    # 5. 只保留 0~max_freq 范围
    freq_amp = [(f, a) for f, a in zip(xf, yf) if f <= max_freq]
    freq = [round(f, 2) for f, a in freq_amp]
    amp = [round(a, 4) for f, a in freq_amp]

    return freq, amp


# ==================== 齿轮/轴承故障特征计算 ====================

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
    freqs = _compute_bearing_fault_freqs(rot_freq, bearing_params)
    return {k: v / rot_freq for k, v in freqs.items()}


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


def _extract_spectrum_features(freq, amp, rot_freq: float, gear_teeth: dict, bearing_params: dict) -> dict:
    """从频谱提取齿轮/轴承相关特征"""
    freq = np.asarray(freq)
    amp = np.asarray(amp)
    total_energy = float(np.sum(amp ** 2)) + 1e-10
    features = {}

    # --- 齿轮特征 ---
    if gear_teeth and isinstance(gear_teeth, dict):
        z_in = gear_teeth.get("input") or 0
        z_out = gear_teeth.get("output") or 0
        if z_in > 0:
            mesh_freq = rot_freq * z_in
            features["mesh_freq_hz"] = round(mesh_freq, 2)
            mesh_amp = _band_energy(freq, amp, mesh_freq, 5.0)
            features["mesh_freq_ratio"] = round(mesh_amp / total_energy, 6)

            sideband_total = 0.0
            sideband_count = 0
            for n in range(1, 4):
                sb_low = mesh_freq - n * rot_freq
                sb_high = mesh_freq + n * rot_freq
                sb_amp = _band_energy(freq, amp, sb_low, 2.0) + _band_energy(freq, amp, sb_high, 2.0)
                sideband_total += sb_amp
                if sb_amp > mesh_amp * 0.05:
                    sideband_count += 1
            features["sideband_total_ratio"] = round(sideband_total / total_energy, 6)
            features["sideband_count"] = sideband_count

        if z_out > 0:
            out_mesh_freq = rot_freq * z_out
            features["output_mesh_freq_hz"] = round(out_mesh_freq, 2)
            features["output_mesh_ratio"] = round(_band_energy(freq, amp, out_mesh_freq, 5.0) / total_energy, 6)

    # --- 轴承特征 ---
    if bearing_params and isinstance(bearing_params, dict):
        bfreqs = _compute_bearing_fault_freqs(rot_freq, bearing_params)
        for name, f_hz in bfreqs.items():
            features[f"{name}_hz"] = round(f_hz, 2)
            f_amp = _band_energy(freq, amp, f_hz, 3.0)
            features[f"{name}_ratio"] = round(f_amp / total_energy, 6)
            harmonic_total = 0.0
            for h in range(2, 4):
                harmonic_total += _band_energy(freq, amp, f_hz * h, 3.0)
            features[f"{name}_harmonic_ratio"] = round(harmonic_total / total_energy, 6)

    return features


def _extract_envelope_features(envelope_freq, envelope_amp, rot_freq: float, bearing_params: dict) -> dict:
    """从包络谱提取轴承故障特征"""
    envelope_freq = np.asarray(envelope_freq)
    envelope_amp = np.asarray(envelope_amp)
    total_energy = float(np.sum(envelope_amp ** 2)) + 1e-10
    features = {}

    if not bearing_params or not isinstance(bearing_params, dict):
        features["total_env_energy"] = round(total_energy, 6)
        return features

    bfreqs = _compute_bearing_fault_freqs(rot_freq, bearing_params)
    for name, f_hz in bfreqs.items():
        env_amp = _band_energy(envelope_freq, envelope_amp, f_hz, 2.0)
        features[f"{name}_env_ratio"] = round(env_amp / total_energy, 6)
        harmonic_total = 0.0
        for h in range(2, 5):
            harmonic_total += _band_energy(envelope_freq, envelope_amp, f_hz * h, 2.0)
        features[f"{name}_env_harmonic_ratio"] = round(harmonic_total / total_energy, 6)

    features["total_env_energy"] = round(total_energy, 6)
    return features


def _extract_order_features(order_axis, spectrum, rot_freq: float, gear_teeth: dict, bearing_params: dict) -> dict:
    """从阶次谱提取故障特征"""
    order_axis = np.asarray(order_axis)
    spectrum = np.asarray(spectrum)
    total_energy = float(np.sum(spectrum ** 2)) + 1e-10
    features = {}

    # --- 齿轮阶次特征 ---
    if gear_teeth and isinstance(gear_teeth, dict):
        z_in = gear_teeth.get("input") or 0
        z_out = gear_teeth.get("output") or 0
        if z_in > 0:
            mesh_order = float(z_in)
            features["mesh_order"] = mesh_order
            mesh_amp = _order_band_energy(order_axis, spectrum, mesh_order, 0.5)
            features["mesh_order_ratio"] = round(mesh_amp / total_energy, 6)

            sideband_total = 0.0
            sideband_count = 0
            for n in range(1, 4):
                sb_low = mesh_order - n
                sb_high = mesh_order + n
                sb_amp = _order_band_energy(order_axis, spectrum, sb_low, 0.3) + _order_band_energy(order_axis, spectrum, sb_high, 0.3)
                sideband_total += sb_amp
                if sb_amp > mesh_amp * 0.05:
                    sideband_count += 1
            features["sideband_order_total_ratio"] = round(sideband_total / total_energy, 6)
            features["sideband_order_count"] = sideband_count

        if z_out > 0:
            out_order = float(z_out)
            features["output_mesh_order"] = out_order
            features["output_mesh_order_ratio"] = round(_order_band_energy(order_axis, spectrum, out_order, 0.5) / total_energy, 6)

    # --- 轴承阶次特征 ---
    if bearing_params and isinstance(bearing_params, dict):
        borders = _compute_bearing_fault_orders(rot_freq, bearing_params)
        for name, order in borders.items():
            features[f"{name}_order"] = round(order, 3)
            order_amp = _order_band_energy(order_axis, spectrum, order, 0.3)
            features[f"{name}_order_ratio"] = round(order_amp / total_energy, 6)
            harmonic_total = 0.0
            for h in range(2, 4):
                harmonic_total += _order_band_energy(order_axis, spectrum, order * h, 0.3)
            features[f"{name}_order_harmonic_ratio"] = round(harmonic_total / total_energy, 6)

    return features


def analyze_device(channels_data: Dict[str, List[float]], sample_rate: int = 25600, device=None):
    """
    综合分析主函数

    优先级：
      1. 神经网络模型（nn_predictor.py）
      2. 新诊断引擎（DiagnosisEngine，支持 Fast Kurtogram / CPW / MED 等高级算法）
      3. 简化规则算法（回退方案）
    """
    # 1. 神经网络优先
    nn_result = nn_predict(channels_data, sample_rate)
    if nn_result is not None:
        print("[分析] 使用神经网络模型预测结果")
        return nn_result

    # 2. 新诊断引擎（默认方案）
    try:
        bearing_params = getattr(device, "bearing_params", None) if device else None
        gear_teeth = getattr(device, "gear_teeth", None) if device else None

        # 从设备配置读取诊断策略（如果有的话）
        strategy = getattr(device, "diagnosis_strategy", "advanced") if device else "advanced"
        bearing_method = getattr(device, "bearing_method", "kurtogram") if device else "kurtogram"
        gear_method = getattr(device, "gear_method", "standard") if device else "standard"
        denoise = getattr(device, "denoise_method", "none") if device else "none"

        engine = DiagnosisEngine(
            strategy=strategy,
            bearing_method=bearing_method,
            gear_method=gear_method,
            denoise_method=denoise,
            bearing_params=bearing_params,
            gear_teeth=gear_teeth,
        )

        # 对每个通道分别分析，然后融合
        channel_results = []
        for ch_name, signal in channels_data.items():
            result = engine.analyze_comprehensive(np.array(signal, dtype=np.float64), sample_rate)
            channel_results.append((ch_name, result))

        # 融合多通道结果：取最差健康度
        worst_health = min(r["health_score"] for _, r in channel_results)
        worst_status = max(
            ([r["status"] for _, r in channel_results]),
            key=lambda s: {"normal": 0, "warning": 1, "fault": 2}[s]
        )

        # 合并故障概率（取各通道最大概率）
        merged_probs = {}
        for _, r in channel_results:
            for fault_name, prob in r.get("bearing", {}).get("fault_indicators", {}).items():
                if prob.get("significant"):
                    merged_probs.setdefault("轴承" + fault_name, 0)
                    merged_probs["轴承" + fault_name] = max(merged_probs["轴承" + fault_name], min(1.0, prob.get("snr", 0) / 10))
            for fault_name, prob in r.get("gear", {}).get("fault_indicators", {}).items():
                if isinstance(prob, dict) and prob.get("warning"):
                    merged_probs.setdefault("齿轮" + fault_name, 0)
                    merged_probs["齿轮" + fault_name] = max(merged_probs["齿轮" + fault_name], 0.3 if prob.get("warning") else 0)
                    if prob.get("critical"):
                        merged_probs["齿轮" + fault_name] = max(merged_probs["齿轮" + fault_name], 0.6)

        # 构建兼容旧格式的 fault_probabilities
        fault_probabilities = {"正常运行": max(0.0, 1.0 - sum(merged_probs.values()))}
        for k, v in merged_probs.items():
            fault_probabilities[k] = round(v, 4)

        # 取第一个通道的详细分析作为 order_analysis
        first_ch, first_result = channel_results[0]

        # 构建兼容旧格式的结果
        legacy_result = {
            "health_score": worst_health,
            "status": worst_status,
            "fault_probabilities": fault_probabilities,
            "imf_energy": first_result.get("time_features", {}),
            "order_analysis": {
                "engine_result": first_result,
                "channels": {ch: r for ch, r in channel_results},
            },
            "rot_freq": first_result.get("bearing", {}).get("rot_freq_hz"),
        }

        print(f"[分析] 新诊断引擎完成，健康度={worst_health}，状态={worst_status}")
        return legacy_result

    except Exception as e:
        print(f"[分析] 新诊断引擎异常: {e}，回退到规则算法")

    # 3. 回退到简化规则算法
    print("[分析] 使用简化规则算法")
    return _rule_based_analyze(channels_data, sample_rate, device)
