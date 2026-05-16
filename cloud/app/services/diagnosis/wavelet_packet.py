"""
小波包能量熵模块 (Wavelet Packet Energy Entropy)

与现有小波阈值去噪的互补性：
- wavelet_denoise: 利用小波系数阈值处理进行降噪；
- 小波包能量熵: 利用小波包分解的全频带覆盖特性提取能量分布特征，
  对齿轮故障引起的频带能量重分布敏感。
"""
import numpy as np
import pywt
from typing import Dict, Tuple


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
