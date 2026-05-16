"""
小波包能量熵模块 (Wavelet Packet Energy Entropy)

与现有小波阈值去噪的互补性：
- wavelet_denoise: 利用小波系数阈值处理进行降噪；
- 小波包能量熵: 利用小波包分解的全频带覆盖特性提取能量分布特征，
  对齿轮故障引起的频带能量重分布敏感。

新增功能:
- MSWPEE (Multi-Scale Wavelet Packet Energy Entropy): 多尺度粗粒化处理，
  对早期微弱故障更敏感（参考 §10.3）
"""
import numpy as np
import pywt
from typing import Dict, List, Tuple


def wavelet_packet_decompose(
    signal: np.ndarray,
    wavelet: str = "db8",
    level: int = 3,
) -> Dict[str, np.ndarray]:
    """
    小波包完全二叉树分解

    Args:
        signal: 输入信号
        wavelet: 小波基
        level: 分解层数（3~4层通常足够）

    Returns:
        {节点路径: 系数数组}
    """
    arr = np.array(signal, dtype=np.float64)
    wp = pywt.WaveletPacket(data=arr, wavelet=wavelet, mode='symmetric')
    nodes = wp.get_level(level, order='natural')
    return {node.path: np.array(node.data, dtype=np.float64) for node in nodes}


def compute_wavelet_packet_energy_entropy(
    signal: np.ndarray,
    fs: float,
    wavelet: str = "db8",
    level: int = 3,
    gear_mesh_freq: float = None,
) -> Dict:
    """
    小波包能量熵特征提取（齿轮故障专用）

    Args:
        signal: 输入信号
        fs: 采样率
        wavelet: 小波基
        level: 分解层数
        gear_mesh_freq: 啮合频率(Hz)

    Returns:
        能量熵、各节点能量比、啮合频带能量集中度等特征
    """
    arr = np.array(signal, dtype=np.float64)
    wp_nodes = wavelet_packet_decompose(arr, wavelet=wavelet, level=level)
    n_nodes = 2 ** level

    energies = {}
    total_energy = 0.0
    for path, coeff in wp_nodes.items():
        e = float(np.sum(coeff ** 2))
        energies[path] = e
        total_energy += e

    if total_energy < 1e-12:
        return {"energy_entropy": 0.0, "normalized_entropy": 0.0}

    probs = {k: v / total_energy for k, v in energies.items()}
    entropy = -sum(p * np.log2(p) for p in probs.values() if p > 1e-12)
    max_entropy = np.log2(n_nodes)
    normalized_entropy = float(entropy / max_entropy) if max_entropy > 0 else 0.0

    mesh_concentration = 0.0
    if gear_mesh_freq and gear_mesh_freq > 0 and gear_mesh_freq < fs / 2:
        nyq = fs / 2.0
        node_bw = nyq / n_nodes
        node_idx = int(gear_mesh_freq / node_bw)
        node_idx = max(0, min(node_idx, n_nodes - 1))
        paths = list(wp_nodes.keys())
        if node_idx < len(paths):
            target_path = paths[node_idx]
            mesh_concentration = probs.get(target_path, 0.0)

    max_energy_ratio = float(max(probs.values()))

    return {
        "energy_entropy": round(float(entropy), 4),
        "normalized_entropy": round(normalized_entropy, 4),
        "max_energy_ratio": round(max_energy_ratio, 6),
        "mesh_band_concentration": round(mesh_concentration, 6),
        "energy_ratios": {k: round(v, 6) for k, v in sorted(probs.items())},
        "n_nodes": n_nodes,
        "wavelet": wavelet,
        "level": level,
    }


def wavelet_packet_denoise(
    signal: np.ndarray,
    wavelet: str = "db8",
    level: int = 3,
    energy_threshold_ratio: float = 0.05,
) -> Tuple[np.ndarray, Dict]:
    """
    基于能量熵的小波包降噪

    策略：保留能量占比超过阈值的节点，其余置零后重构。
    """
    arr = np.array(signal, dtype=np.float64)
    wp = pywt.WaveletPacket(data=arr, wavelet=wavelet, mode='symmetric')
    nodes = wp.get_level(level, order='natural')
    energies = [float(np.sum(np.array(n.data) ** 2)) for n in nodes]
    total = sum(energies) + 1e-12
    ratios = [e / total for e in energies]

    for node, ratio in zip(nodes, ratios):
        if ratio < energy_threshold_ratio:
            node.data = np.zeros_like(np.array(node.data))

    reconstructed = wp.reconstruct(update=True)
    if len(reconstructed) > len(arr):
        reconstructed = reconstructed[:len(arr)]

    return reconstructed, {
        "method": "wavelet_packet_energy",
        "level": level,
        "energy_threshold_ratio": energy_threshold_ratio,
        "retained_nodes": sum(1 for r in ratios if r >= energy_threshold_ratio),
    }


# ═══════════════════════════════════════════════════════════
# 多尺度小波包能量熵 (MSWPEE)
# ═══════════════════════════════════════════════════════════

def _coarse_grain(signal: np.ndarray, scale: int) -> np.ndarray:
    """
    粗粒化处理（Multi-Scale Processing）

    对原始序列按 scale 因子分段平均，抑制高频随机噪声，
    凸显低频调制特征（故障特征频率通常在低频段）。

    Args:
        signal: 输入信号
        scale: 粗粒化尺度因子（τ=1为原信号，τ=2每2点取平均）

    Returns:
        粗粒化后的序列（长度 ≈ N/scale）
    """
    arr = np.asarray(signal, dtype=np.float64)
    N = len(arr)
    if scale <= 1:
        return arr
    n_out = N // scale
    if n_out < 4:
        return arr  # 信号过短，不粗粒化
    reshaped = arr[:n_out * scale].reshape(n_out, scale)
    return np.mean(reshaped, axis=1)


def compute_mswpee(
    signal: np.ndarray,
    fs: float,
    wavelet: str = "db8",
    level: int = 3,
    max_scale: int = 5,
    gear_mesh_freq: float = None,
) -> Dict:
    """
    多尺度小波包能量熵 (MSWPEE)

    对各粗粒化序列分别计算小波包能量熵，构建多尺度特征向量。
    粗粒化处理可抑制高频噪声，凸显故障引起的低频调制特征。

    参考: wavelet_and_modality_decomposition.md §10.3

    Args:
        signal: 输入信号
        fs: 采样率
        wavelet: 小波基
        level: WP 分解层数
        max_scale: 最大粗粒化尺度（τ=1,2,...,max_scale）
        gear_mesh_freq: 啮合频率（用于频带集中度计算）

    Returns:
        {
            "mswpee_vector": [H^(1), H^(2), ...],      # 各尺度归一化熵
            "mswpee_raw_vector": [H_raw^(1), ...],      # 各尺度原始熵
            "scales": [1, 2, ..., max_scale],
            "single_scale_results": {...},              # 各尺度的完整WP结果
            "mswpee_mean": float,                       # 多尺度平均熵
            "mswpee_std": float,                        # 多尺度熵标准差
        }
    """
    arr = np.asarray(signal, dtype=np.float64)
    mswpee_vec = []
    mswpee_raw = []
    scale_results = {}

    for tau in range(1, max_scale + 1):
        coarse = _coarse_grain(arr, tau)
        # 粗粒化后采样率虚拟降低
        fs_coarse = fs / tau

        wp_result = compute_wavelet_packet_energy_entropy(
            coarse, fs_coarse, wavelet=wavelet, level=level,
            gear_mesh_freq=gear_mesh_freq,
        )
        mswpee_vec.append(wp_result["normalized_entropy"])
        mswpee_raw.append(wp_result["energy_entropy"])
        scale_results[f"scale_{tau}"] = wp_result

    mean_entropy = float(np.mean(mswpee_vec)) if mswpee_vec else 0.0
    std_entropy = float(np.std(mswpee_vec)) if len(mswpee_vec) > 1 else 0.0

    return {
        "mswpee_vector": [round(v, 4) for v in mswpee_vec],
        "mswpee_raw_vector": [round(v, 4) for v in mswpee_raw],
        "scales": list(range(1, max_scale + 1)),
        "single_scale_results": scale_results,
        "mswpee_mean": round(mean_entropy, 4),
        "mswpee_std": round(std_entropy, 4),
        "wavelet": wavelet,
        "level": level,
        "max_scale": max_scale,
    }
