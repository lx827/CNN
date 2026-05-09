"""
风机振动信号生成器
用数学模型模拟风机齿轮箱在不同工况下的振动信号

配置参数（通过 .env 或修改下方常量）：
- SAMPLE_RATE: 采样率 Hz（默认 25600）
- DURATION: 每次生成时长 秒（默认 10）
- N_SAMPLES: 总采样点数 = SAMPLE_RATE * DURATION

包含工况：
- 正常：平稳基频 + 轻微噪声
- 齿轮磨损：啮合频率及其谐波增强
- 轴承故障：周期性冲击脉冲
- 轴不对中：2倍转频分量显著
"""
import numpy as np
import random
import os

# 从环境变量读取，没有则使用默认值
SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "25600"))  # Hz
DURATION = int(os.getenv("DURATION", "10"))           # 秒


def _add_noise(signal, snr_db=30):
    """添加高斯白噪声"""
    power = np.mean(signal ** 2)
    noise_power = power / (10 ** (snr_db / 10))
    noise = np.random.normal(0, np.sqrt(noise_power), len(signal))
    return signal + noise


def normal_signal(duration=None, sample_rate=None):
    """
    正常工况振动信号
    主要成分：转频 25 Hz + 齿轮啮合频率 180 Hz + 噪声
    """
    dur = duration or DURATION
    sr = sample_rate or SAMPLE_RATE
    n_samples = sr * dur
    t = np.linspace(0, dur, n_samples, endpoint=False)
    shaft_freq = 25.0
    mesh_freq = 180.0

    signal = (
        0.5 * np.sin(2 * np.pi * shaft_freq * t)
        + 0.3 * np.sin(2 * np.pi * mesh_freq * t)
        + 0.1 * np.sin(2 * np.pi * 2 * mesh_freq * t)
    )
    return _add_noise(signal, snr_db=35)


def gear_wear_signal(duration=None, sample_rate=None):
    """齿轮磨损故障信号"""
    dur = duration or DURATION
    sr = sample_rate or SAMPLE_RATE
    n_samples = sr * dur
    t = np.linspace(0, dur, n_samples, endpoint=False)
    shaft_freq = 25.0
    mesh_freq = 180.0

    signal = (
        0.5 * np.sin(2 * np.pi * shaft_freq * t)
        + 1.2 * np.sin(2 * np.pi * mesh_freq * t)
        + 0.4 * np.sin(2 * np.pi * (mesh_freq + shaft_freq) * t)
        + 0.4 * np.sin(2 * np.pi * (mesh_freq - shaft_freq) * t)
        + 0.2 * np.sin(2 * np.pi * 2 * mesh_freq * t)
    )
    return _add_noise(signal, snr_db=25)


def bearing_fault_signal(duration=None, sample_rate=None):
    """轴承外圈故障信号"""
    dur = duration or DURATION
    sr = sample_rate or SAMPLE_RATE
    n_samples = sr * dur
    t = np.linspace(0, dur, n_samples, endpoint=False)
    shaft_freq = 25.0
    mesh_freq = 180.0
    bpfo = 120.0

    signal = (
        0.5 * np.sin(2 * np.pi * shaft_freq * t)
        + 0.3 * np.sin(2 * np.pi * mesh_freq * t)
    )

    period_samples = int(sr / bpfo)
    for i in range(0, n_samples, period_samples):
        if i < n_samples - 10:
            pulse_len = min(20, n_samples - i)
            pulse_t = np.linspace(0, 0.02, pulse_len)
            pulse = 1.5 * np.sin(2 * np.pi * 3000 * pulse_t) * np.exp(-100 * pulse_t)
            signal[i:i+pulse_len] += pulse[:pulse_len]

    return _add_noise(signal, snr_db=22)


def misalignment_signal(duration=None, sample_rate=None):
    """轴不对中故障信号"""
    dur = duration or DURATION
    sr = sample_rate or SAMPLE_RATE
    n_samples = sr * dur
    t = np.linspace(0, dur, n_samples, endpoint=False)
    shaft_freq = 25.0
    mesh_freq = 180.0

    signal = (
        0.5 * np.sin(2 * np.pi * shaft_freq * t)
        + 1.0 * np.sin(2 * np.pi * 2 * shaft_freq * t)
        + 0.3 * np.sin(2 * np.pi * 3 * shaft_freq * t)
        + 0.3 * np.sin(2 * np.pi * mesh_freq * t)
    )
    return _add_noise(signal, snr_db=28)


def generate_signals(mode: str = "auto", channel_count: int = None, duration=None, sample_rate=None) -> dict:
    """
    生成 k 通道振动信号

    Args:
        mode: "auto" 随机切换工况，或指定 "normal"/"gear_wear"/"bearing_fault"/"misalignment"
        channel_count: 通道数，传入则优先使用，否则读取环境变量 CHANNEL_COUNT（默认 3）
        duration: 信号时长（秒），不传则使用全局 DURATION
        sample_rate: 采样率（Hz），不传则使用全局 SAMPLE_RATE

    Returns:
        {"ch1": [...], "ch2": [...], ...}
    """
    generators = {
        "normal": normal_signal,
        "gear_wear": gear_wear_signal,
        "bearing_fault": bearing_fault_signal,
        "misalignment": misalignment_signal,
    }

    # 通道数：优先使用传入值，否则读取环境变量
    if channel_count is None:
        channel_count = int(os.getenv("CHANNEL_COUNT", "3"))

    if mode == "auto":
        r = random.random()
        if r < 0.7:
            selected = ["normal"] * channel_count
        elif r < 0.8:
            selected = ["gear_wear"] + ["normal"] * (channel_count - 1)
        elif r < 0.9:
            selected = ["normal", "bearing_fault"] + ["normal"] * (channel_count - 2)
        else:
            selected = ["normal"] * (channel_count - 1) + ["misalignment"]
    else:
        selected = [mode] * channel_count

    result = {}
    for i, mode_name in enumerate(selected, 1):
        sig = generators[mode_name](duration=duration, sample_rate=sample_rate)
        result[f"ch{i}"] = sig.tolist()

    return result
