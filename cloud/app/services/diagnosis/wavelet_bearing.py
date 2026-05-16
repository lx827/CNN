"""
小波类轴承故障诊断模块 (Wavelet-based Bearing Diagnosis)

基于小波包分解和DWT分解的轴承诊断方法，
通过敏感分量选择（能量+峭度综合评分）定位共振频带，
再对敏感频带重构信号执行Hilbert包络分析。

参考: wavelet_and_modality_decomposition.md §9

返回格式与 bearing.py 现有方法一致:
    {envelope_freq, envelope_amp, method, ...方法特有字段}
"""
import numpy as np
import pywt
from typing import Dict, Optional, List

from .signal_utils import remove_dc, bandpass_filter, lowpass_filter
from .sensitive_selector import (
    select_wp_sensitive_nodes,
    BEARING_WEIGHTS,
)


# ═══════════════════════════════════════════════════════════
# 小波包轴承诊断
# ═══════════════════════════════════════════════════════════

def wavelet_packet_bearing_analysis(
    signal: np.ndarray,
    fs: float,
    wavelet: str = "db8",
    level: int = 3,
    top_n: int = 1,
    f_low_pass: float = 2000.0,
    max_freq: float = 1000.0,
    target_freq: float = 0.0,
) -> Dict:
    """
    小波包轴承故障诊断（§9.2 + §9.4）

    流程:
    1. 小波包完全二叉树分解（level层 → 2^level个节点）
    2. 计算各节点综合敏感度（相关性+峭度+包络熵+能量占比）
    3. 选择最敏感节点（top_n个）
    4. 对敏感节点重构窄带信号
    5. Hilbert包络 → 低通滤波 → FFT包络谱
    6. 返回标准格式结果

    Args:
        signal: 输入振动信号
        fs: 采样率
        wavelet: 小波基（默认 db8，与去噪保持一致）
        level: WP分解层数（3→8节点@8192Hz各512Hz; 4→16节点各256Hz）
        top_n: 选择前N个敏感节点（默认1）
        f_low_pass: 包络低通截止频率
        max_freq: 包络谱最大显示频率
        target_freq: 目标共振频率（0=自动检测）

    Returns:
        {
            envelope_freq, envelope_amp,  # 标准包络谱
            method,                        # "Wavelet Packet Envelope"
            wp_level, wp_wavelet,          # 分解参数
            selected_nodes,                # 选中的节点路径列表
            node_scores,                   # 各节点评分详情
            node_center_freqs,             # 各节点中心频率
        }
    """
    from scipy.signal import hilbert
    from scipy.fft import rfft, rfftfreq

    arr = remove_dc(np.asarray(signal, dtype=np.float64))
    N = len(arr)

    # ── Step 1: 小波包分解 ──
    wp = pywt.WaveletPacket(data=arr, wavelet=wavelet, mode='symmetric')
    nodes = wp.get_level(level, order='natural')

    # ── Step 2: 计算各节点指标 + 综合评分 ──
    wp_coeffs = {node.path: np.array(node.data, dtype=np.float64) for node in nodes}
    n_nodes = 2 ** level
    node_bw = fs / 2.0 / n_nodes  # 每节点带宽

    # 节点中心频率（自然序）
    node_center_freqs = {}
    for path in sorted(wp_coeffs.keys()):
        idx = int(path, 2) if path else 0
        # natural order: 节点按频率递增排列
        # 第j层第k个节点覆盖 [k*bw, (k+1)*bw]
        node_center_freqs[path] = idx * node_bw + node_bw / 2.0

    # 自动目标频率：选峭度最高节点的中心频率作为共振频率估计
    if target_freq <= 0:
        node_kurts = []
        for path, coeff in wp_coeffs.items():
            c = coeff - np.mean(coeff)
            s2 = np.var(coeff)
            if s2 > 1e-12:
                node_kurts.append((path, float(np.mean((c / np.sqrt(s2)) ** 4) - 3.0)))
            else:
                node_kurts.append((path, 0.0))
        best_kurt_path = max(node_kurts, key=lambda x: x[1])[0]
        target_freq = node_center_freqs.get(best_kurt_path, 0.0)

    # ── Step 3: 敏感节点选择 ──
    selected_paths, node_scores = select_wp_sensitive_nodes(
        wp_coeffs, arr, fs, mode="bearing", target_freq=target_freq, top_n=top_n
    )

    # ── Step 4: 重构敏感节点窄带信号 ──
    wp2 = pywt.WaveletPacket(data=arr, wavelet=wavelet, mode='symmetric')
    # 保留选中节点，其余置零
    for node in wp2.get_level(level, order='natural'):
        if node.path not in selected_paths:
            node.data = np.zeros_like(np.array(node.data))

    reconstructed = wp2.reconstruct(update=True)
    if len(reconstructed) > N:
        reconstructed = reconstructed[:N]

    # ── Step 5: Hilbert 包络分析 ──
    analytic = hilbert(reconstructed)
    envelope = np.abs(analytic)
    envelope = envelope - np.mean(envelope)  # 零均值化

    # 低通滤波
    if f_low_pass < fs / 2:
        envelope = lowpass_filter(envelope, fs, f_low_pass)

    # FFT 包络谱
    yf = np.abs(rfft(envelope))
    xf = rfftfreq(N, 1.0 / fs)

    # 仅保留 0 ~ max_freq
    freq_list = [f for f, a in zip(xf, yf) if f <= max_freq]
    amp_list = [a for f, a in zip(xf, yf) if f <= max_freq]

    return {
        "envelope_freq": freq_list,
        "envelope_amp": amp_list,
        "method": "Wavelet Packet Envelope",
        "wp_level": level,
        "wp_wavelet": wavelet,
        "selected_nodes": selected_paths,
        "node_scores": node_scores,
        "node_center_freqs": node_center_freqs,
        "target_freq": round(target_freq, 2),
        "n_selected": len(selected_paths),
    }


# ═══════════════════════════════════════════════════════════
# DWT 敏感层轴承诊断
# ═══════════════════════════════════════════════════════════

def dwt_bearing_analysis(
    signal: np.ndarray,
    fs: float,
    wavelet: str = "db8",
    level: int = 5,
    top_n: int = 1,
    f_low_pass: float = 2000.0,
    max_freq: float = 1000.0,
) -> Dict:
    """
    DWT 敏感层轴承诊断（§9.1 + §9.4）

    流程:
    1. DWT 多层分解 → 各层细节系数 d_j
    2. 计算各层细节系数的峭度和能量
    3. 选择综合指标最高的层作为共振频带
    4. 重构敏感层窄带信号
    5. Hilbert包络 → 低通 → FFT包络谱

    各层对应频带（@8192Hz, level=5）:
        d1: 2048~4096 Hz  — 极高频噪声/结构共振
        d2: 1024~2048 Hz  — 高频共振（轴承常用）
        d3: 512~1024 Hz   — 中频共振/齿轮啮合
        d4: 256~512 Hz    — 中低频
        d5: 128~256 Hz    — 低频/转频

    Args:
        signal: 输入振动信号
        fs: 采样率
        wavelet: 小波基
        level: DWT分解层数
        top_n: 选择前N个敏感层
        f_low_pass: 包络低通截止频率
        max_freq: 包络谱最大显示频率

    Returns:
        {
            envelope_freq, envelope_amp,
            method,                        # "DWT Sensitive Layer Envelope"
            dwt_level, dwt_wavelet,
            selected_layers,               # 选中的分解层索引列表
            layer_scores,                  # 各层评分详情
        }
    """
    from scipy.signal import hilbert
    from scipy.fft import rfft, rfftfreq

    arr = remove_dc(np.asarray(signal, dtype=np.float64))
    N = len(arr)

    # ── Step 1: DWT 分解 ──
    coeffs = pywt.wavedec(arr, wavelet, level=level)
    # coeffs = [a_level, d_level, d_level-1, ..., d_1]
    # 细节系数索引: d_j → coeffs[level - j]

    detail_coeffs = []
    layer_ranges = []  # 各层频带范围

    for j in range(1, level + 1):
        d = coeffs[level - j + 1] if level - j + 1 < len(coeffs) else None
        if d is not None:
            detail_coeffs.append(np.array(d, dtype=np.float64))
            f_low = fs / 2 ** (j + 1)
            f_high = fs / 2 ** j
            layer_ranges.append((j, f_low, f_high))
        else:
            detail_coeffs.append(np.zeros(1))
            layer_ranges.append((j, 0, 0))

    # ── Step 2: 各层指标 ──
    layer_data = []
    for idx, (j, f_lo, f_hi) in enumerate(layer_ranges):
        d = detail_coeffs[idx]
        c = d - np.mean(d)
        s2 = np.var(d)
        kurt = float(np.mean((c / np.sqrt(s2 + 1e-12)) ** 4) - 3.0) if s2 > 1e-12 else 0.0
        energy = float(np.sum(d ** 2))
        center_freq = (f_lo + f_hi) / 2.0

        # 与原始信号相关性（长度匹配）
        orig_seg = arr[:len(d)]
        d_z = d - np.mean(d)
        o_z = orig_seg - np.mean(orig_seg)
        corr = 0.0
        if np.std(d_z) > 1e-12 and np.std(o_z) > 1e-12:
            corr = float(np.abs(np.corrcoef(d_z, o_z)[0, 1]))

        # 综合评分（峭度主导 + 能量辅助）
        score = BEARING_WEIGHTS["kurt"] * min(kurt / 20.0, 1.0) + \
                BEARING_WEIGHTS["corr"] * min(corr / 0.8, 1.0) + \
                BEARING_WEIGHTS["energy"] * min(energy / (np.sum(arr ** 2) * 0.3 + 1e-12), 1.0)

        layer_data.append({
            "layer": j,
            "freq_range": f"[{f_lo:.0f}, {f_hi:.0f}]",
            "center_freq": round(center_freq, 1),
            "kurtosis": round(kurt, 2),
            "energy": round(energy, 2),
            "corr": round(corr, 4),
            "score": round(score, 4),
        })

    # ── Step 3: 选择敏感层 ──
    sorted_layers = sorted(layer_data, key=lambda x: x["score"], reverse=True)
    selected = sorted_layers[:top_n]
    selected_layer_indices = [s["layer"] for s in selected]

    # ── Step 4: 重构敏感层信号 ──
    # 置零非选中层的细节系数
    new_coeffs = list(coeffs)
    for j in range(1, level + 1):
        coeff_idx = level - j + 1
        if j not in selected_layer_indices and coeff_idx < len(new_coeffs):
            new_coeffs[coeff_idx] = np.zeros_like(new_coeffs[coeff_idx])

    reconstructed = pywt.waverec(new_coeffs, wavelet)
    if len(reconstructed) > N:
        reconstructed = reconstructed[:N]
    elif len(reconstructed) < N:
        padded = np.zeros(N)
        padded[:len(reconstructed)] = reconstructed
        reconstructed = padded

    # ── Step 5: Hilbert 包络分析 ──
    analytic = hilbert(reconstructed)
    envelope = np.abs(analytic)
    envelope = envelope - np.mean(envelope)

    if f_low_pass < fs / 2:
        envelope = lowpass_filter(envelope, fs, f_low_pass)

    yf = np.abs(rfft(envelope))
    xf = rfftfreq(N, 1.0 / fs)

    freq_list = [f for f, a in zip(xf, yf) if f <= max_freq]
    amp_list = [a for f, a in zip(xf, yf) if f <= max_freq]

    return {
        "envelope_freq": freq_list,
        "envelope_amp": amp_list,
        "method": "DWT Sensitive Layer Envelope",
        "dwt_level": level,
        "dwt_wavelet": wavelet,
        "selected_layers": selected_layer_indices,
        "layer_scores": layer_data,
        "best_layer": selected[0] if selected else None,
    }