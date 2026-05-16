"""
定轴齿轮箱 VMD 幅频联合解调分析模块

基于 ALGORITHMS.md §12.2：
VMD 分解 → 选择啮合频率附近敏感模态 → 幅值解调谱 + 频率解调谱 → 边频带故障检测

定轴齿轮箱与行星齿轮箱的核心区别：
- 定轴箱边频带间隔 = 转频 (rot_freq)，而非 carrier_order
- 定轴箱啮合频率 = gear_teeth × rot_freq（整数阶次），而非行星架构的分数阶次
- 定轴箱 SER 正常 < 1.5，> 3.0 为严重故障

算法流程（§12.2）：
1. VMD 分解：K = min(max_K, int(fs / (2 * mesh_freq)))
2. 选择中心频率最接近 mesh_freq 的模态
3. Hilbert 包络 a(t) = |u_k + j·H[u_k]|
4. 包络谱 = FFT(envelope)
5. 瞬时频率 f_inst(t) = d/dt · atan(H[c(t)] / c(t)) / (2π)，c(t) = u_k / a(t)
6. 在幅值和频率解调谱中搜索 n × rot_freq 边频带

故障检测逻辑：
- 幅值解调谱中的边频带 → 幅值调制（AM）故障特征
- 频率解调谱中的边频带 → 频率调制（FM）故障特征
- SER 边频能量比量化调制严重程度
"""
import numpy as np
from scipy.signal import hilbert as scipy_hilbert
from scipy.fft import rfft, rfftfreq
from typing import Dict, List, Optional

from ..vmd_denoise import vmd_decompose
from ..signal_utils import (
    prepare_signal,
    _band_energy,
)


def vmd_fixed_axis_demod_analysis(
    signal: np.ndarray,
    fs: float,
    rot_freq: float,
    gear_teeth: Dict,
    max_K: int = 5,
    alpha: float = 2000,
) -> Dict:
    """
    VMD 幅频联合解调分析（定轴齿轮箱专用）

    对定轴齿轮箱振动信号做 VMD 分解，选择啮合频率附近的敏感模态，
    分别提取幅值解调谱（包络谱）和频率解调谱（瞬时频率谱），
    在两个解调谱中搜索 n × rot_freq 边频带以检测齿轮故障。

    Args:
        signal: 原始振动信号
        fs: 采样率 Hz
        rot_freq: 估计转频 Hz
        gear_teeth: 齿轮参数字典，定轴箱应包含：
            - "input": 输入齿轮齿数（主动轮）
            - "output": 输出齿轮齿数（被动轮，可选）
            至少需要 "input" 齿数来计算啮合频率
        max_K: VMD 最大模态数（默认5，2GB服务器限制 K≤5）
        alpha: VMD 惩罚因子（默认2000）

    Returns:
        {
            "method": "VMD Fixed-Axis Gear Demod",
            "mesh_freq_hz": float,
            "rot_freq_hz": float,
            "K": int,
            "selected_mode": int,
            "mode_center_freqs": List[float],
            "amplitude_demod_freq": List[float],   # 包络谱频率轴
            "amplitude_demod_amp": List[float],     # 包络谱幅值
            "freq_demod_freq": List[float],         # 瞬时频率谱频率轴
            "freq_demod_amp": List[float],           # 瞬时频率谱幅值
            "sideband_analysis": Dict,               # 边频带检测结果
        }
    """
    # === 参数校验 ===
    arr = prepare_signal(signal)

    if rot_freq <= 0 or fs <= 0:
        return {
            "method": "VMD Fixed-Axis Gear Demod",
            "mesh_freq_hz": 0.0,
            "rot_freq_hz": float(rot_freq),
            "K": 0,
            "selected_mode": -1,
            "mode_center_freqs": [],
            "amplitude_demod_freq": [],
            "amplitude_demod_amp": [],
            "freq_demod_freq": [],
            "freq_demod_amp": [],
            "sideband_analysis": {"error": "invalid_params"},
        }

    # 计算啮合频率：定轴箱 f_mesh = Z_input × f_rot
    z_input = int(gear_teeth.get("input") or 0)
    if z_input <= 0:
        return {
            "method": "VMD Fixed-Axis Gear Demod",
            "mesh_freq_hz": 0.0,
            "rot_freq_hz": float(rot_freq),
            "K": 0,
            "selected_mode": -1,
            "mode_center_freqs": [],
            "amplitude_demod_freq": [],
            "amplitude_demod_amp": [],
            "freq_demod_freq": [],
            "freq_demod_amp": [],
            "sideband_analysis": {"error": "missing_gear_teeth"},
        }

    mesh_freq = z_input * rot_freq

    if mesh_freq <= 0:
        return {
            "method": "VMD Fixed-Axis Gear Demod",
            "mesh_freq_hz": 0.0,
            "rot_freq_hz": float(rot_freq),
            "K": 0,
            "selected_mode": -1,
            "mode_center_freqs": [],
            "amplitude_demod_freq": [],
            "amplitude_demod_amp": [],
            "freq_demod_freq": [],
            "freq_demod_amp": [],
            "sideband_analysis": {"error": "mesh_freq_zero"},
        }

    # 信号截断至5秒（2GB服务器内存限制）
    max_samples = int(fs * 5)
    if len(arr) > max_samples:
        arr = arr[:max_samples]

    # === Step 1: VMD 分解 ===
    # K = min(max_K, int(fs / (2 * mesh_freq)))
    # 原理：奈奎斯特频率 fs/2 需容纳 K 个模态，每个模态中心频率约 mesh_freq
    # 所以 K_max = fs / (2 * mesh_freq) 是物理上限
    K = min(max_K, int(fs / (2 * mesh_freq)))
    K = max(2, K)  # 至少2个模态（1个模态无分解意义）

    try:
        u, u_hat, omega = vmd_decompose(arr, K=K, alpha=alpha)
    except Exception:
        return {
            "method": "VMD Fixed-Axis Gear Demod",
            "mesh_freq_hz": float(mesh_freq),
            "rot_freq_hz": float(rot_freq),
            "K": K,
            "selected_mode": -1,
            "mode_center_freqs": [],
            "amplitude_demod_freq": [],
            "amplitude_demod_amp": [],
            "freq_demod_freq": [],
            "freq_demod_amp": [],
            "sideband_analysis": {"error": "vmd_failed"},
        }

    # VMD 返回 omega 形状 (n_iter, K)，取最终迭代的中心频率
    # omega 是归一化频率 (0~0.5)，需转换为 Hz：freq_hz = omega * fs
    # 但 vmd_decompose 内部对信号做了镜像扩展，omega 的频率基数基于扩展后的长度
    # 直接使用 u_hat 的频谱峰值作为中心频率更准确
    mode_center_freqs = []
    for k_idx in range(u.shape[0]):
        imf = u[k_idx, :]
        # 对每个 IMF 做 FFT 取峰值频率作为中心频率
        spectrum = np.abs(rfft(imf))
        freqs = rfftfreq(len(imf), 1.0 / fs)
        if len(spectrum) > 0:
            peak_idx = np.argmax(spectrum)
            center_freq = float(freqs[peak_idx])
        else:
            center_freq = 0.0
        mode_center_freqs.append(center_freq)

    # === Step 2: 选择啮合频率附近的敏感模态 ===
    # 选择中心频率最接近 mesh_freq 的模态
    selected_idx = int(np.argmin(np.abs(np.array(mode_center_freqs) - mesh_freq)))
    sensitive_imf = u[selected_idx, :]

    # === Step 3: Hilbert 包络（幅值解调） ===
    # a(t) = |u_k + j·H[u_k]| = |analytic signal|
    analytic = scipy_hilbert(sensitive_imf)
    amplitude_envelope = np.abs(analytic)

    # === Step 4: 包络谱（幅值解调谱） ===
    # 去均值后做 FFT
    envelope_demod = amplitude_envelope - np.mean(amplitude_envelope)
    envelope_spectrum = np.abs(rfft(envelope_demod))
    envelope_freq_axis = rfftfreq(len(envelope_demod), 1.0 / fs)

    # === Step 5: 瞬时频率（频率解调） ===
    # c(t) = u_k / a(t)（载波信号）
    carrier = sensitive_imf / (amplitude_envelope + 1e-12)

    # f_inst(t) = d/dt · atan(H[c(t)] / c(t)) / (2π)
    # 等价于 f_inst(t) = dφ(t)/dt / (2π)，其中 φ(t) 是瞬时相位
    try:
        carrier_analytic = scipy_hilbert(carrier)
        inst_phase = np.unwrap(np.angle(carrier_analytic))
        # 瞬时频率 = 相位导数 / (2π) × fs
        inst_freq = np.diff(inst_phase) / (2 * np.pi) * fs
        # 补齐长度（末尾用最后一个值填充）
        inst_freq = np.concatenate([inst_freq, [inst_freq[-1]]])

        # 去均值保留频率调制成分
        inst_freq_demod = inst_freq - np.mean(inst_freq)
        freq_demod_spectrum = np.abs(rfft(inst_freq_demod))
        freq_demod_freq_axis = rfftfreq(len(inst_freq_demod), 1.0 / fs)
    except Exception:
        freq_demod_spectrum = np.array([])
        freq_demod_freq_axis = np.array([])

    # === Step 6: 边频带分析 ===
    sideband_result = _analyze_fixed_axis_sidebands(
        envelope_freq_axis, envelope_spectrum,
        freq_demod_freq_axis, freq_demod_spectrum,
        mesh_freq, rot_freq, fs,
    )

    return {
        "method": "VMD Fixed-Axis Gear Demod",
        "mesh_freq_hz": round(float(mesh_freq), 4),
        "rot_freq_hz": round(float(rot_freq), 4),
        "K": K,
        "selected_mode": selected_idx,
        "mode_center_freqs": [round(f, 4) for f in mode_center_freqs],
        "amplitude_demod_freq": [round(float(f), 4) for f in envelope_freq_axis],
        "amplitude_demod_amp": [round(float(a), 6) for a in envelope_spectrum],
        "freq_demod_freq": [round(float(f), 4) for f in freq_demod_freq_axis],
        "freq_demod_amp": [round(float(a), 6) for a in freq_demod_spectrum],
        "sideband_analysis": sideband_result,
    }


def _analyze_fixed_axis_sidebands(
    amp_freq: np.ndarray,
    amp_spectrum: np.ndarray,
    freq_freq: np.ndarray,
    freq_spectrum: np.ndarray,
    mesh_freq: float,
    rot_freq: float,
    fs: float,
    n_sidebands: int = 6,
    sideband_bw_hz: float = 2.0,
) -> Dict:
    """
    定轴齿轮箱边频带检测

    在幅值解调谱（包络谱）和频率解调谱中搜索 n × rot_freq 边频带。

    定轴箱边频带特征：
    - 边频间隔 = rot_freq（转频），而非行星箱的 carrier_order
    - 边频位置 = mesh_freq ± n × rot_freq
    - 幅值调制（AM）：包络谱中的边频带 → 齿面磨损/点蚀/裂纹
    - 频率调制（FM）：瞬时频率谱中的边频带 → 齿距误差/载荷波动

    SER 计算：
    - SER = sum(A_SB_i) / A(mesh_freq)
    - 定轴箱 SER < 1.5 为正常，> 3.0 为严重故障

    Args:
        amp_freq: 包络谱频率轴
        amp_spectrum: 包络谱幅值
        freq_freq: 频率解调谱频率轴
        freq_spectrum: 频率解调谱幅值
        mesh_freq: 啮合频率 Hz
        rot_freq: 转频 Hz
        fs: 采样率 Hz
        n_sidebands: 搜索边频带阶数（默认6）
        sideband_bw_hz: 边频搜索带宽 Hz（默认2.0）

    Returns:
        {
            "amplitude_sidebands": List[Dict],   # 包络谱边频带
            "frequency_sidebands": List[Dict],   # 频率解调谱边频带
            "amplitude_ser": float,              # 包络谱 SER
            "frequency_ser": float,              # 频率解调谱 SER
            "amplitude_mesh_energy": float,      # 包络谱啮合频率能量
            "frequency_mesh_energy": float,      # 频率解调谱啮合频率能量
            "amplitude_significant_count": int,  # 包络谱显著边频数
            "frequency_significant_count": int,  # 频率解调谱显著边频数
            "amplitude_fault_indicators": Dict,  # AM 故障指示器
            "frequency_fault_indicators": Dict,  # FM 故障指示器
        }
    """
    amp_freq = np.asarray(amp_freq)
    amp_spectrum = np.asarray(amp_spectrum)
    freq_freq = np.asarray(freq_freq)
    freq_spectrum = np.asarray(freq_spectrum)

    # --- 包络谱边频带分析 ---
    amp_sidebands = []
    amp_total_sb = 0.0

    # 啮合频率处的包络谱能量
    amp_mesh_energy = _band_energy(amp_freq, amp_spectrum, mesh_freq, sideband_bw_hz)
    if amp_mesh_energy < 1e-12:
        # 包络谱中 mesh_freq 处无能量（可能 VMD 分解偏移），使用最大峰值
        if len(amp_spectrum) > 0:
            peak_idx = np.argmax(amp_spectrum)
            amp_mesh_energy = float(amp_spectrum[peak_idx] ** 2)
        else:
            amp_mesh_energy = 1e-12

    for i in range(1, n_sidebands + 1):
        sb_low = mesh_freq - i * rot_freq
        sb_high = mesh_freq + i * rot_freq

        # 边频频率必须在有效范围内
        amp_sb_low = 0.0
        amp_sb_high = 0.0

        if sb_low > 0 and sb_low < fs / 2.0:
            amp_sb_low = _band_energy(amp_freq, amp_spectrum, sb_low, sideband_bw_hz)
        if sb_high > 0 and sb_high < fs / 2.0:
            amp_sb_high = _band_energy(amp_freq, amp_spectrum, sb_high, sideband_bw_hz)

        amp_total_sb += amp_sb_low + amp_sb_high

        # 显著性：边频能量超过啮合频率能量的 5%
        significant = (amp_sb_low > amp_mesh_energy * 0.05) or \
                      (amp_sb_high > amp_mesh_energy * 0.05)

        amp_sidebands.append({
            "order": i,
            "freq_low_hz": round(sb_low, 4),
            "freq_high_hz": round(sb_high, 4),
            "energy_low": round(amp_sb_low, 6),
            "energy_high": round(amp_sb_high, 6),
            "significant": significant,
            "asymmetry": round(
                abs(amp_sb_low - amp_sb_high) / (amp_sb_low + amp_sb_high + 1e-12),
                4
            ),
        })

    amp_ser = amp_total_sb / amp_mesh_energy if amp_mesh_energy > 1e-12 else 0.0
    amp_sig_count = sum(1 for sb in amp_sidebands if sb["significant"])

    # --- 频率解调谱边频带分析 ---
    freq_sidebands = []
    freq_total_sb = 0.0

    freq_mesh_energy = _band_energy(freq_freq, freq_spectrum, mesh_freq, sideband_bw_hz)
    if freq_mesh_energy < 1e-12:
        if len(freq_spectrum) > 0:
            peak_idx = np.argmax(freq_spectrum)
            freq_mesh_energy = float(freq_spectrum[peak_idx] ** 2)
        else:
            freq_mesh_energy = 1e-12

    for i in range(1, n_sidebands + 1):
        sb_low = mesh_freq - i * rot_freq
        sb_high = mesh_freq + i * rot_freq

        freq_sb_low = 0.0
        freq_sb_high = 0.0

        if sb_low > 0 and sb_low < fs / 2.0:
            freq_sb_low = _band_energy(freq_freq, freq_spectrum, sb_low, sideband_bw_hz)
        if sb_high > 0 and sb_high < fs / 2.0:
            freq_sb_high = _band_energy(freq_freq, freq_spectrum, sb_high, sideband_bw_hz)

        freq_total_sb += freq_sb_low + freq_sb_high

        significant = (freq_sb_low > freq_mesh_energy * 0.05) or \
                      (freq_sb_high > freq_mesh_energy * 0.05)

        freq_sidebands.append({
            "order": i,
            "freq_low_hz": round(sb_low, 4),
            "freq_high_hz": round(sb_high, 4),
            "energy_low": round(freq_sb_low, 6),
            "energy_high": round(freq_sb_high, 6),
            "significant": significant,
            "asymmetry": round(
                abs(freq_sb_low - freq_sb_high) / (freq_sb_low + freq_sb_high + 1e-12),
                4
            ),
        })

    freq_ser = freq_total_sb / freq_mesh_energy if freq_mesh_energy > 1e-12 else 0.0
    freq_sig_count = sum(1 for sb in freq_sidebands if sb["significant"])

    # --- 故障指示器评估（定轴箱阈值） ---
    # SER: < 1.5 正常，> 3.0 严重
    # 显著边频数: ≥ 2 warning，≥ 4 critical
    amp_fault_indicators = _evaluate_fixed_axis_indicators(
        amp_ser, amp_sig_count, amp_mesh_energy, "amplitude"
    )
    freq_fault_indicators = _evaluate_fixed_axis_indicators(
        freq_ser, freq_sig_count, freq_mesh_energy, "frequency"
    )

    return {
        "amplitude_sidebands": amp_sidebands,
        "frequency_sidebands": freq_sidebands,
        "amplitude_ser": round(amp_ser, 4),
        "frequency_ser": round(freq_ser, 4),
        "amplitude_mesh_energy": round(amp_mesh_energy, 6),
        "frequency_mesh_energy": round(freq_mesh_energy, 6),
        "amplitude_significant_count": amp_sig_count,
        "frequency_significant_count": freq_sig_count,
        "amplitude_fault_indicators": amp_fault_indicators,
        "frequency_fault_indicators": freq_fault_indicators,
    }


def _evaluate_fixed_axis_indicators(
    ser: float,
    significant_count: int,
    mesh_energy: float,
    demod_type: str,
) -> Dict:
    """
    定轴齿轮箱解调谱故障指示器评估

    定轴箱阈值（与行星箱不同）：
    - SER < 1.5: 正常
    - SER 1.5~3.0: warning
    - SER > 3.0: critical
    - 显著边频数 ≥ 2: warning
    - 显著边频数 ≥ 4: critical

    Args:
        ser: 边频能量比
        significant_count: 显著边频数量
        mesh_energy: 啮合频率处能量（用于 SNR 计算）
        demod_type: "amplitude" 或 "frequency"

    Returns:
        {
            "ser": {"value": float, "warning": bool, "critical": bool},
            "sideband_count": {"value": int, "warning": bool, "critical": bool},
            "demod_type": str,
        }
    """
    return {
        "demod_type": demod_type,
        "ser": {
            "value": round(ser, 4),
            "warning": ser > 1.5,
            "critical": ser > 3.0,
        },
        "sideband_count": {
            "value": significant_count,
            "warning": significant_count >= 2,
            "critical": significant_count >= 4,
        },
    }