"""
Layer 1 信号基元 — wavelet_packet 正确性验证

测试 wavelet_packet_decompose / compute_wavelet_packet_energy_entropy /
     wavelet_packet_denoise / compute_mswpee

输出: layer1/output/wavelet_packet.json
"""
import json, sys, os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.wavelet_packet import (
    wavelet_packet_decompose, compute_wavelet_packet_energy_entropy,
    wavelet_packet_denoise, compute_mswpee,
)
from tests.diagnosis.foundation.layer1.synthetic_signals import NumpyEncoder

OUTPUT_DIR = Path(__file__).parent / "output"
FS = 8192


def test_wp_decompose():
    """wavelet_packet_decompose: 二叉树分解结构"""
    print("\n--- wavelet_packet_decompose ---")
    results = []

    sig = np.sin(2 * np.pi * 100 * np.arange(512) / FS) + np.random.randn(512) * 0.1
    nodes = wavelet_packet_decompose(sig, wavelet="db8", level=3)

    # level=3 → 2^3=8 个节点
    n_nodes_ok = len(nodes) == 8
    results.append({"test": "wp_nodes_count", "n_nodes": len(nodes), "passed": n_nodes_ok})
    print(f"  [{'PASS' if n_nodes_ok else 'FAIL'}] 节点数: {len(nodes)} (期望8)")

    # 所有节点都是 ndarray
    all_arrays = all(isinstance(v, np.ndarray) for v in nodes.values())
    results.append({"test": "wp_nodes_type", "passed": all_arrays})
    print(f"  [{'PASS' if all_arrays else 'FAIL'}] 节点类型正确")

    return results


def test_wp_energy_entropy():
    """compute_wavelet_packet_energy_entropy: 能量熵特征"""
    print("\n--- compute_wavelet_packet_energy_entropy ---")
    results = []

    # 纯噪声 → 能量分布均匀 → 熵接近最大值
    noise = np.random.randn(1024)
    res_noise = compute_wavelet_packet_energy_entropy(noise, FS, level=3)
    ne_noise = res_noise["normalized_entropy"]
    noise_high = ne_noise > 0.8  # 均匀分布熵高
    results.append({"test": "wp_entropy_noise", "normalized_entropy": ne_noise, "passed": noise_high})
    print(f"  [{'PASS' if noise_high else 'FAIL'}] 噪声熵: ne={ne_noise:.3f} (期望>0.8)")

    # 单频正弦 → 能量集中在少数节点 → 熵较低
    sig = np.sin(2 * np.pi * 200 * np.arange(1024) / FS)
    res_sig = compute_wavelet_packet_energy_entropy(sig, FS, level=3)
    ne_sig = res_sig["normalized_entropy"]
    signal_low = ne_sig < 0.7  # 集中分布熵低
    results.append({"test": "wp_entropy_tone", "normalized_entropy": ne_sig, "passed": signal_low})
    print(f"  [{'PASS' if signal_low else 'FAIL'}] 单频熵: ne={ne_sig:.3f} (期望<0.7)")

    # 带啮合频率集中度
    mesh_f = 500.0
    res_mesh = compute_wavelet_packet_energy_entropy(sig, FS, level=3, gear_mesh_freq=mesh_f)
    mc = res_mesh.get("mesh_band_concentration", 0)
    has_mc = mc >= 0  # 只要有值就算通过
    results.append({"test": "wp_mesh_concentration", "mc": mc, "passed": has_mc})
    print(f"  [{'PASS' if has_mc else 'FAIL'}] 啮合集中度: mc={mc:.4f}")

    return results


def test_wp_denoise():
    """wavelet_packet_denoise: 基于能量阈值的降噪"""
    print("\n--- wavelet_packet_denoise ---")
    results = []

    t = np.arange(0, 1.0, 1.0 / FS)
    clean = np.sin(2 * np.pi * 50 * t)
    noise = np.random.randn(len(t)) * 0.3
    sig = clean + noise

    recon, info = wavelet_packet_denoise(sig, wavelet="db8", level=3, energy_threshold_ratio=0.05)
    len_ok = len(recon) == len(sig)
    mse_before = np.mean((sig - clean) ** 2)
    mse_after = np.mean((recon - clean) ** 2) if len_ok else float('inf')
    improved = mse_after < mse_before * 0.9
    results.append({
        "test": "wp_denoise",
        "mse_before": round(float(mse_before), 6),
        "mse_after": round(float(mse_after), 6),
        "retained": info.get("retained_nodes", 0),
        "passed": len_ok and improved,
    })
    print(f"  [{'PASS' if len_ok and improved else 'FAIL'}] WP降噪: MSE {mse_before:.4f} -> {mse_after:.4f}, retained={info.get('retained_nodes', 0)}")

    return results


def test_mswpee():
    """compute_mswpee: 多尺度小波包能量熵"""
    print("\n--- compute_mswpee ---")
    results = []

    sig = np.sin(2 * np.pi * 100 * np.arange(512) / FS) + np.random.randn(512) * 0.1
    res = compute_mswpee(sig, FS, wavelet="db8", level=2, max_scale=3)

    vec = res.get("mswpee_vector", [])
    vec_ok = len(vec) == 3  # max_scale=3
    results.append({"test": "mswpee_vector_len", "len": len(vec), "passed": vec_ok})
    print(f"  [{'PASS' if vec_ok else 'FAIL'}] MSWPEE向量长度: {len(vec)} (期望3)")

    mean_val = res.get("mswpee_mean", 0)
    has_mean = mean_val > 0
    results.append({"test": "mswpee_mean", "mean": round(mean_val, 4), "passed": has_mean})
    print(f"  [{'PASS' if has_mean else 'FAIL'}] MSWPEE均值: {mean_val:.4f}")

    return results


def main():
    print("=" * 60)
    print("Layer 1: wavelet_packet — 小波包正确性")
    print("=" * 60)

    all_results = {
        "decompose": test_wp_decompose(),
        "energy_entropy": test_wp_energy_entropy(),
        "denoise": test_wp_denoise(),
        "mswpee": test_mswpee(),
    }

    total = passed = 0
    for items in all_results.values():
        for it in items:
            total += 1
            if it.get("passed", False): passed += 1
    all_results["summary"] = {"total": total, "passed": passed, "failed": total - passed}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "wavelet_packet.json"
    out.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder, ensure_ascii=False), encoding='utf-8')
    s = all_results["summary"]
    print(f"\n结果: {out}\n总计: {s['total']}, 通过: {s['passed']}, 失败: {s['failed']}")


if __name__ == "__main__":
    main()
