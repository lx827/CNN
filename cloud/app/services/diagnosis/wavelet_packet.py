"""小波包业务响应适配；分解、频率映射、能量和选择由纯 Pipeline 提供。"""

import numpy as np
from app.algorithms.pipelines.decomposition import WaveletPacketEnergyPipeline


def compute_wavelet_packet_energy_entropy(
    signal, fs, wavelet="db8", level=3, gear_mesh_freq=None
):
    """返回 WP 原时间轴分量能量分布；mesh 频带按 Gray 频率序定位。"""
    analysis = WaveletPacketEnergyPipeline(wavelet, level).analyze(signal, fs)
    decomposition = analysis.decomposition
    if analysis.energy_ratios is None:
        return {
            "status": "indeterminate",
            "reason": "zero_component_energy",
            "energy_entropy": None,
            "normalized_entropy": None,
            "mesh_band_concentration": None,
            "max_energy_ratio": None,
            "energy_ratios": {},
            "n_nodes": len(decomposition.nodes),
            "wavelet": wavelet,
            "level": level,
        }
    ratios = {
        node.path: float(ratio)
        for node, ratio in zip(decomposition.nodes, analysis.energy_ratios)
    }
    mesh = None
    if gear_mesh_freq is not None:
        mesh = ratios[decomposition.node_for_frequency(gear_mesh_freq).path]
    return {
        "status": "computed",
        "energy_entropy": analysis.entropy_bits,
        "normalized_entropy": analysis.normalized_entropy,
        "max_energy_ratio": float(np.max(analysis.energy_ratios)),
        "mesh_band_concentration": mesh,
        "energy_ratios": ratios,
        "n_nodes": len(decomposition.nodes),
        "wavelet": wavelet,
        "level": level,
        "coefficient_sample_rate_hz": fs / 2**level,
        "node_frequency_bands_hz": {
            node.path: list(node.frequency_band_hz) for node in decomposition.nodes
        },
    }


def wavelet_packet_denoise(signal, wavelet="db8", level=3, energy_threshold_ratio=0.05):
    """能量比例去噪的业务适配；没有满足节点时抛错，不强制返回全零。"""
    pipeline = WaveletPacketEnergyPipeline(wavelet, level)
    analysis = pipeline.analyze(signal, 1.0)
    representation, paths = pipeline.select(
        analysis, energy_threshold_ratio=energy_threshold_ratio
    )
    if representation is None:
        raise ValueError("no_eligible_wavelet_packet_nodes")
    return representation, {
        "method": "wavelet_packet_energy",
        "status": "computed",
        "level": level,
        "energy_threshold_ratio": energy_threshold_ratio,
        "retained_nodes": len(paths),
        "selected_nodes": list(paths),
        "valid_interval": [0, len(representation)],
    }


def compute_mswpee(
    signal, fs, wavelet="db8", level=3, max_scale=5, gear_mesh_freq=None
):
    """多尺度研究边界；不把粗粒化后的mesh混叠峰解释为原始物理频率。"""
    from .composite import analyze_composite_research

    result = analyze_composite_research(
        "mswpee",
        signal,
        fs,
        options={"wavelet": wavelet, "level": level, "max_scale": max_scale},
    )
    scales = result.analysis.data["scales"]
    vector = result.analysis.data["normalized_entropy_vector"]
    valid = result.analysis.status == "computed"
    return {
        "status": result.analysis.status,
        "reason": result.analysis.reason,
        "mswpee_vector": vector,
        "mswpee_raw_vector": tuple(item["entropy_bits"] for item in scales),
        "scales": tuple(item["scale"] for item in scales),
        "single_scale_results": {f"scale_{item['scale']}": item for item in scales},
        "mswpee_mean": float(np.mean(vector)) if valid else None,
        "mswpee_std": float(np.std(vector)) if valid else None,
        "research_only": True,
        "production_eligible": False,
        "wavelet": wavelet,
        "level": level,
    }
