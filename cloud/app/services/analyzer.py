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


def compute_channel_features(signal: List[float]) -> Dict[str, float]:
    """
    计算单通道振动信号的统计特征指标
    用于通道级阈值告警。
    """
    arr = np.array(signal)
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
    arr = np.array(signal)
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


def _rule_based_analyze(channels_data: Dict[str, List[float]], sample_rate: int = 25600):
    """
    简化规则算法（回退方案）
    根据振动峰值大小评估健康度和故障概率
    """
    all_peak_values = []
    for ch_name, signal in channels_data.items():
        arr = np.array(signal)
        all_peak_values.append(np.max(np.abs(arr)))

    avg_peak = np.mean(all_peak_values)

    base_probs = {
        "齿轮磨损": 0.05,
        "轴承内圈故障": 0.03,
        "轴承外圈故障": 0.02,
        "轴不对中": 0.04,
        "基础松动": 0.03,
        "正常运行": 0.83,
    }

    severity = min(avg_peak / 2.0, 1.0)

    if severity > 0.3:
        base_probs["齿轮磨损"] += severity * 0.25
        base_probs["轴承内圈故障"] += severity * 0.15
        base_probs["轴承外圈故障"] += severity * 0.10
        base_probs["轴不对中"] += severity * 0.15
        base_probs["基础松动"] += severity * 0.10
        base_probs["正常运行"] = max(0, 1.0 - sum(v for k, v in base_probs.items() if k != "正常运行"))

    total_prob = sum(base_probs.values())
    fault_probabilities = {k: round(v / total_prob, 4) for k, v in base_probs.items()}

    first_channel = list(channels_data.values())[0]
    imf_energy = compute_imf_energy(first_channel, sample_rate)

    health_score = int(max(0, min(100, 100 - severity * 60 - random.uniform(0, 5))))
    status = "normal" if health_score >= 80 else "warning" if health_score >= 60 else "critical"

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
    arr = np.array(signal)

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
