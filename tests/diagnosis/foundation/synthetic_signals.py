"""
合成信号生成器 — 用于基础算法正确性验证

每个信号都有明确的 ground truth（转频、故障频率等），
算法输出与 ground truth 的偏差就是正确性指标。
"""
import json
import numpy as np

FS = 8192  # 统一采样率


def sinusoidal(freq=25.0, duration=3.0, fs=FS):
    """纯正弦信号 — 验证 FFT/转频估计"""
    t = np.arange(0, duration, 1/fs)
    sig = np.sin(2 * np.pi * freq * t)
    return sig, fs, {"rot_freq": freq, "type": "sinusoidal"}


def bearing_outer_race(bpfo=90.0, rot_freq=25.0, duration=3.0, fs=FS, snr_db=20):
    """
    模拟外圈故障轴承信号
    ground_truth: BPFO=90Hz, 转频=25Hz
    """
    t = np.arange(0, duration, 1/fs)
    # 冲击脉冲序列 (外圈故障频率)
    T_impact = 1.0 / bpfo
    impulse_train = np.zeros_like(t)
    for i in range(int(duration / T_impact)):
        idx = int(i * T_impact * fs)
        if idx < len(t):
            impulse_train[idx] = 1.0

    # 用共振频率卷积模拟冲击响应
    fn = 3000  # 共振频率 Hz
    zeta = 0.05
    wn = 2 * np.pi * fn
    wd = wn * np.sqrt(1 - zeta**2)
    ir = np.exp(-zeta * wn * np.arange(0, 0.01, 1/fs)) * np.sin(wd * np.arange(0, 0.01, 1/fs))
    sig = np.convolve(impulse_train, ir, mode='same')

    # 加噪
    sig_power = np.var(sig)
    noise_power = sig_power / (10 ** (snr_db / 10))
    sig += np.sqrt(noise_power) * np.random.randn(len(sig))

    return sig, fs, {"bpfo": bpfo, "rot_freq": rot_freq, "type": "bearing_outer_race", "snr_db": snr_db}


def bearing_inner_race(bpfi=135.0, rot_freq=25.0, duration=3.0, fs=FS, snr_db=20):
    """
    模拟内圈故障轴承信号（带转频调制）
    ground_truth: BPFI=135Hz, 转频=25Hz
    """
    t = np.arange(0, duration, 1/fs)
    T_impact = 1.0 / bpfi
    impulse_train = np.zeros_like(t)
    for i in range(int(duration / T_impact)):
        idx = int(i * T_impact * fs)
        if idx < len(t):
            # 内圈故障：冲击幅值随转频调制
            impulse_train[idx] = 1.0 + 0.5 * np.sin(2 * np.pi * rot_freq * t[idx])

    fn = 3000
    zeta = 0.05
    wn = 2 * np.pi * fn
    wd = wn * np.sqrt(1 - zeta**2)
    ir = np.exp(-zeta * wn * np.arange(0, 0.01, 1/fs)) * np.sin(wd * np.arange(0, 0.01, 1/fs))
    sig = np.convolve(impulse_train, ir, mode='same')

    sig_power = np.var(sig)
    noise_power = sig_power / (10 ** (snr_db / 10))
    sig += np.sqrt(noise_power) * np.random.randn(len(sig))

    return sig, fs, {"bpfi": bpfi, "rot_freq": rot_freq, "type": "bearing_inner_race", "snr_db": snr_db}


def gear_mesh(mesh_freq=450.0, rot_freq=25.0, duration=3.0, fs=FS, snr_db=20):
    """
    模拟齿轮啮合信号（含边频带）
    ground_truth: 啮合频率=450Hz, 转频=25Hz
    """
    t = np.arange(0, duration, 1/fs)
    sig = np.sin(2 * np.pi * mesh_freq * t)
    # 添加边频带 (mesh ± rot_freq)
    sig += 0.3 * np.sin(2 * np.pi * (mesh_freq + rot_freq) * t)
    sig += 0.3 * np.sin(2 * np.pi * (mesh_freq - rot_freq) * t)
    sig += 0.15 * np.sin(2 * np.pi * (mesh_freq + 2*rot_freq) * t)
    sig += 0.15 * np.sin(2 * np.pi * (mesh_freq - 2*rot_freq) * t)

    sig_power = np.var(sig)
    noise_power = sig_power / (10 ** (snr_db / 10))
    sig += np.sqrt(noise_power) * np.random.randn(len(sig))

    return sig, fs, {"mesh_freq": mesh_freq, "rot_freq": rot_freq, "type": "gear_mesh", "snr_db": snr_db}


def chirp_rotating(freq_start=10.0, freq_end=40.0, duration=5.0, fs=FS):
    """
    线性扫频信号 — 模拟变速工况
    ground_truth: 瞬时频率从 freq_start → freq_end 线性变化
    """
    t = np.arange(0, duration, 1/fs)
    # 线性扫频: 瞬时频率 = f0 + (f1-f0)*t/duration
    phase = 2 * np.pi * (freq_start * t + (freq_end - freq_start) * t**2 / (2 * duration))
    sig = np.sin(phase)
    return sig, fs, {"freq_start": freq_start, "freq_end": freq_end, "type": "chirp", "duration": duration}


def impulse_train(impulse_freq=100.0, duration=3.0, fs=FS, snr_db=15):
    """纯冲击序列 — 验证包络分析最基础能力"""
    t = np.arange(0, duration, 1/fs)
    T = 1.0 / impulse_freq
    sig = np.zeros_like(t)
    for i in range(int(duration / T)):
        idx = int(i * T * fs)
        if idx < len(t):
            sig[idx] = 1.0

    sig_power = np.var(sig)
    noise_power = sig_power / (10 ** (snr_db / 10))
    sig += np.sqrt(noise_power) * np.random.randn(len(sig))

    return sig, fs, {"impulse_freq": impulse_freq, "type": "impulse_train", "snr_db": snr_db}

import json as _json

class NumpyEncoder(_json.JSONEncoder):
    """JSON encoder that handles numpy types."""
    def default(self, obj):
        import numpy as _np
        if isinstance(obj, (_np.integer,)): return int(obj)
        if isinstance(obj, (_np.floating,)): return float(obj)
        if isinstance(obj, (_np.bool_,)): return bool(obj)
        if isinstance(obj, _np.ndarray): return obj.tolist()
        return super().default(obj)
