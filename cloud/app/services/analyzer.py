"""
故障分析引擎

分析流程：
  1. 优先调用神经网络模型（nn_predictor.py）
  2. 如果神经网络未启用或失败，回退到简化规则算法（FFT + IMF能量 + 阈值判断）

注意：这里的算法是"教学级"简化实现，目的是让整个系统跑起来。
真实工业场景会使用更复杂的 EMD/VMD 分解、小波包分析、深度学习模型等。
"""
import numpy as np
from scipy.fft import rfft, rfftfreq
from scipy.signal import hilbert
from scipy import stats
from typing import Dict, List
import random

from app.services.nn_predictor import predict as nn_predict


def remove_dc(signal: List[float]) -> np.ndarray:
    """去除信号直流分量（零均值化）"""
    arr = np.array(signal, dtype=np.float64)
    return arr - np.mean(arr)


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


def _rule_based_analyze(channels_data: Dict[str, List[float]], sample_rate: int = 25600):
    """
    多特征综合规则诊断算法（回退方案）

    基于振动时域统计特征（峭度、峰值因子、RMS、偏度、脉冲因子、峰值）
    结合工程阈值进行故障类型判别。

    参考阈值（与 alarm_service.py 一致）：
      - Kurtosis(fisher=False): 健康≈3, 预警≥4, 严重≥6
      - Crest Factor: 健康≈3~5, 预警≥6, 严重≥10
      - RMS: 预警≥5, 严重≥10
      - Peak: 预警≥15, 严重≥30
      - Skewness(|值|): 预警≥1, 严重≥2
      - Impulse Factor: 预警≥6, 严重≥10
    """
    # 1. 计算所有通道的特征
    all_features = []
    for ch_name, signal in channels_data.items():
        features = compute_channel_features(signal)
        if features:
            all_features.append(features)

    if not all_features:
        # 无有效数据，返回默认值
        return {
            "health_score": 100,
            "fault_probabilities": {"正常运行": 1.0},
            "imf_energy": {},
            "status": "normal",
        }

    # 2. 计算多通道平均特征
    avg_features = {}
    for key in ["rms", "peak", "kurtosis", "crest_factor", "skewness", "impulse_factor"]:
        values = [f.get(key, 0) for f in all_features if f.get(key) is not None]
        avg_features[key] = np.mean(values) if values else 0.0

    # 3. 计算各特征严重度
    sev = {
        "rms": _feature_severity(avg_features["rms"], "rms"),
        "peak": _feature_severity(avg_features["peak"], "peak"),
        "kurtosis": _feature_severity(avg_features["kurtosis"], "kurtosis"),
        "crest_factor": _feature_severity(avg_features["crest_factor"], "crest_factor"),
        "skewness": _feature_severity(abs(avg_features["skewness"]), "skewness"),
        "impulse_factor": _feature_severity(avg_features["impulse_factor"], "impulse_factor"),
    }

    # 4. 故障类型判别（每种故障对特征的敏感度不同）
    #    权重基于工程经验：冲击型故障（轴承）对峭度/峰值因子敏感；
    #    能量型故障（齿轮磨损/不对中）对RMS/峰值敏感。
    fault_scores = {
        "正常运行": 1.0,
        "齿轮磨损": sev["rms"] * 0.40 + sev["peak"] * 0.30 + sev["crest_factor"] * 0.15 + sev["kurtosis"] * 0.15,
        "轴承内圈故障": sev["kurtosis"] * 0.40 + sev["crest_factor"] * 0.25 + sev["impulse_factor"] * 0.25 + sev["peak"] * 0.10,
        "轴承外圈故障": sev["kurtosis"] * 0.30 + sev["crest_factor"] * 0.25 + sev["rms"] * 0.25 + sev["impulse_factor"] * 0.20,
        "滚动体故障": sev["kurtosis"] * 0.30 + sev["peak"] * 0.30 + sev["impulse_factor"] * 0.25 + sev["crest_factor"] * 0.15,
        "轴不对中": sev["rms"] * 0.40 + sev["skewness"] * 0.30 + sev["peak"] * 0.20 + sev["kurtosis"] * 0.10,
        "基础松动": sev["peak"] * 0.35 + sev["rms"] * 0.25 + sev["crest_factor"] * 0.25 + sev["skewness"] * 0.15,
    }

    # 5. 正常运行概率衰减（任一指标越高，正常概率越低）
    normal_decay = 1.0
    normal_decay *= max(0.0, 1.0 - sev["rms"] * 0.35)
    normal_decay *= max(0.0, 1.0 - sev["kurtosis"] * 0.50)
    normal_decay *= max(0.0, 1.0 - sev["crest_factor"] * 0.35)
    normal_decay *= max(0.0, 1.0 - sev["peak"] * 0.20)
    normal_decay *= max(0.0, 1.0 - sev["skewness"] * 0.25)
    normal_decay *= max(0.0, 1.0 - sev["impulse_factor"] * 0.30)
    fault_scores["正常运行"] = normal_decay

    # 6. 归一化概率
    total = sum(fault_scores.values())
    if total > 0:
        fault_probabilities = {k: round(v / total, 4) for k, v in fault_scores.items()}
    else:
        fault_probabilities = {"正常运行": 1.0}

    # 7. 健康度评分（基于正常运行概率）
    #    同时引入最大单一故障严重度作为惩罚
    max_fault_sev = max(v for k, v in fault_scores.items() if k != "正常运行")
    health_score = int(max(0, min(100,
        fault_probabilities.get("正常运行", 0) * 100 - max_fault_sev * 30 - random.uniform(0, 3)
    )))

    status = "normal" if health_score >= 80 else "warning" if health_score >= 60 else "fault"

    # 8. IMF 能量（取首个通道）
    first_channel = list(channels_data.values())[0]
    imf_energy = compute_imf_energy(first_channel, sample_rate)

    # 调试日志（便于观察诊断依据）
    print(f"[规则诊断] 特征: RMS={avg_features['rms']:.3f}(sev={sev['rms']:.2f}), "
          f"Kurt={avg_features['kurtosis']:.2f}(sev={sev['kurtosis']:.2f}), "
          f"Crest={avg_features['crest_factor']:.2f}(sev={sev['crest_factor']:.2f}), "
          f"Peak={avg_features['peak']:.3f}(sev={sev['peak']:.2f}), "
          f"Skew={avg_features['skewness']:.3f}(sev={sev['skewness']:.2f}), "
          f"Impulse={avg_features['impulse_factor']:.2f}(sev={sev['impulse_factor']:.2f}) | "
          f"健康度={health_score}, 状态={status}")

    return {
        "health_score": health_score,
        "fault_probabilities": fault_probabilities,
        "imf_energy": imf_energy,
        "status": status,
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


def analyze_device(channels_data: Dict[str, List[float]], sample_rate: int = 25600):
    """
    综合分析主函数
    优先调用神经网络，失败回退简化规则算法
    """
    nn_result = nn_predict(channels_data, sample_rate)
    if nn_result is not None:
        print("[分析] 使用神经网络模型预测结果")
        return nn_result

    print("[分析] 神经网络未启用，使用简化规则算法")
    return _rule_based_analyze(channels_data, sample_rate)
