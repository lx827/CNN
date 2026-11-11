"""小波包业务响应适配；分解、频率映射、能量和选择由纯 Pipeline 提供。"""
import numpy as np
from app.algorithms.pipelines.decomposition import WaveletPacketEnergyPipeline


def compute_wavelet_packet_energy_entropy(signal, fs, wavelet="db8", level=3, gear_mesh_freq=None):
    """返回 WP 原时间轴分量能量分布；mesh 频带按 Gray 频率序定位。"""
    analysis = WaveletPacketEnergyPipeline(wavelet, level).analyze(signal, fs)
    decomposition = analysis.decomposition
    if analysis.energy_ratios is None:
        return {"status": "indeterminate", "reason": "zero_component_energy",
                "energy_entropy": None, "normalized_entropy": None, "mesh_band_concentration": None,
                "max_energy_ratio": None, "energy_ratios": {}, "n_nodes": len(decomposition.nodes),
                "wavelet": wavelet, "level": level}
    ratios = {node.path: float(ratio) for node, ratio in zip(decomposition.nodes, analysis.energy_ratios)}
    mesh = None
    if gear_mesh_freq is not None:
        mesh = ratios[decomposition.node_for_frequency(gear_mesh_freq).path]
    return {"status": "computed", "energy_entropy": analysis.entropy_bits,
            "normalized_entropy": analysis.normalized_entropy,
            "max_energy_ratio": float(np.max(analysis.energy_ratios)), "mesh_band_concentration": mesh,
            "energy_ratios": ratios, "n_nodes": len(decomposition.nodes), "wavelet": wavelet, "level": level,
            "coefficient_sample_rate_hz": fs / 2**level,
            "node_frequency_bands_hz": {node.path: list(node.frequency_band_hz) for node in decomposition.nodes}}


def wavelet_packet_denoise(signal, wavelet="db8", level=3, energy_threshold_ratio=.05):
    """能量比例去噪的业务适配；没有满足节点时抛错，不强制返回全零。"""
    pipeline = WaveletPacketEnergyPipeline(wavelet, level)
    analysis = pipeline.analyze(signal, 1.0)
    representation, paths = pipeline.select(analysis, energy_threshold_ratio=energy_threshold_ratio)
    if representation is None:
        raise ValueError("no_eligible_wavelet_packet_nodes")
    return representation, {"method": "wavelet_packet_energy", "status": "computed", "level": level,
        "energy_threshold_ratio": energy_threshold_ratio, "retained_nodes": len(paths),
        "selected_nodes": list(paths), "valid_interval": [0, len(representation)]}


def _coarse_grain(signal, scale):
    """既有 MSWPEE 业务组合前处理，本工单不扩展该实验流程。"""
    arr = np.asarray(signal, dtype=float)
    if scale <= 1:
        return arr
    count = len(arr) // scale
    if count < 4:
        raise ValueError("粗粒化后记录过短")
    return np.mean(arr[:count * scale].reshape(count, scale), axis=1)


def compute_mswpee(signal, fs, wavelet="db8", level=3, max_scale=5, gear_mesh_freq=None):
    """既有多尺度组合改用唯一 WP Pipeline；不新增效果或生产可用性声明。"""
    if isinstance(max_scale, bool) or not isinstance(max_scale, int) or max_scale <= 0:
        raise ValueError("max_scale 必须为正整数")
    results = {}
    for scale in range(1, max_scale + 1):
        coarse = _coarse_grain(signal, scale)
        # 啮合频率超出该粗粒化序列 Nyquist 时没有对应可观测节点。
        observable_mesh = gear_mesh_freq if gear_mesh_freq is not None and 0 <= gear_mesh_freq <= fs / (2 * scale) else None
        results[f"scale_{scale}"] = compute_wavelet_packet_energy_entropy(
            coarse, fs / scale, wavelet, level, observable_mesh)
    vector = [item["normalized_entropy"] for item in results.values()]
    raw = [item["energy_entropy"] for item in results.values()]
    valid = all(value is not None for value in vector)
    return {"status": "computed" if valid else "indeterminate", "mswpee_vector": vector,
            "mswpee_raw_vector": raw, "scales": list(range(1, max_scale + 1)),
            "single_scale_results": results, "mswpee_mean": float(np.mean(vector)) if valid else None,
            "mswpee_std": float(np.std(vector)) if valid else None, "wavelet": wavelet, "level": level}
