"""
倒谱分析 — 正确性验证

1. 合成齿轮啮合信号：验证倒谱峰值对应正确的倒频率
2. 合成谐波信号：验证倒谱能检测周期性

输出: output/cepstrum_correctness.json
"""
import json
import sys
import os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from tests.diagnosis.foundation.synthetic_signals import NumpyEncoder,  gear_mesh, sinusoidal
from app.api.data_view import _compute_cepstrum as _cloud_cepstrum

OUTPUT_DIR = Path(__file__).parent / "output"
FS = 8192


def _compute_cepstrum_simple(sig, fs, max_quefrency_ms=200.0):
    """委托云端 _compute_cepstrum 计算倒谱，返回 (quefrency_ms, cepstrum, peaks)"""
    quef_ms, cep, peaks = _cloud_cepstrum(sig, fs, max_quefrency_ms=max_quefrency_ms)
    return quef_ms, cep, peaks


def find_quefrency_peaks(peaks_list, top_n=3, min_ms=2.0):
    """从云端 _compute_cepstrum 返回的 peaks 列表中取前 N 个（过滤 min_ms）"""
    filtered = [p for p in peaks_list if p.get("quefrency_ms", 0) >= min_ms]
    return sorted(filtered, key=lambda p: p.get("amplitude", 0), reverse=True)[:top_n]


def test_gear_mesh_cepstrum():
    """合成齿轮啮合信号：倒谱应检测到啮合频率和转频"""
    print("\n--- 齿轮啮合信号倒谱 ---")
    results = []

    sig, fs, gt = gear_mesh(mesh_freq=450.0, rot_freq=25.0, duration=3.0, snr_db=50)
    quef_ms, cep, peaks = _compute_cepstrum_simple(sig, fs)
    top_peaks = find_quefrency_peaks(peaks, top_n=5, min_ms=0.5)

    # ground truth: quefrency = 1 / mesh_freq * 1000 ms
    expected_mesh_quef = 1000.0 / 450.0  # ≈ 2.22 ms
    expected_rot_quef = 1000.0 / 25.0    # = 40 ms

    # 检查是否有峰值接近预期
    mesh_found = any(abs(p["freq_hz"] - 450.0) / 450.0 < 0.1 for p in top_peaks)
    rot_found = any(abs(p["quefrency_ms"] - 40.0) / 40.0 < 0.2 for p in top_peaks)

    results.append({
        "test": "gear_mesh_450Hz_25rps",
        "expected_mesh_quef_ms": round(expected_mesh_quef, 2),
        "expected_rot_quef_ms": round(expected_rot_quef, 2),
        "detected_peaks": top_peaks,
        "mesh_found": mesh_found,
        "rot_found": rot_found,
        "passed": mesh_found or rot_found,
    })
    status = "PASS" if results[-1]["passed"] else "FAIL"
    print(f"  [{status}] 啮合450Hz: mesh_found={mesh_found}, rot_found={rot_found}")
    print(f"    检测到峰值: {[(p['freq_hz'], p['quefrency_ms']) for p in top_peaks]}")
    return results


def test_harmonic_cepstrum():
    """合成谐波信号：倒谱应检测到基频"""
    print("\n--- 谐波信号倒谱 ---")
    results = []

    for f0 in [30, 60]:
        sig, fs, gt = sinusoidal(freq=f0, duration=3.0)
        # 添加谐波
        for h in [2, 3, 5]:
            sig += 0.5 * np.sin(2 * np.pi * f0 * h * np.arange(len(sig)) / fs)

        quef_ms, cep, cloud_peaks = _compute_cepstrum_simple(sig, fs)
        peaks = find_quefrency_peaks(cloud_peaks, top_n=3)
        expected_quef = 1000.0 / f0
        found = any(abs(p["freq_hz"] - f0) / f0 < 0.1 for p in peaks)
        results.append({
            "test": f"harmonic_{f0}Hz",
            "expected_quef_ms": round(expected_quef, 1),
            "detected_peaks": peaks,
            "base_freq_found": found,
            "passed": found,
        })
        status = "PASS" if found else "FAIL"
        print(f"  [{status}] {f0}Hz 谐波: base_found={found}, peaks={[(p['freq_hz'],) for p in peaks]}")

    return results


def main():
    print("=" * 60)
    print("倒谱分析 — 正确性验证")
    print("=" * 60)

    all_results = {
        "gear_mesh": test_gear_mesh_cepstrum(),
        "harmonic": test_harmonic_cepstrum(),
    }

    total = 0
    passed = 0
    for cat, items in all_results.items():
        for item in items:
            total += 1
            if item.get("passed", False):
                passed += 1
    all_results["summary"] = {"total": total, "passed": passed, "failed": total - passed}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "cepstrum_correctness.json"
    out_path.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder))
    print(f"\n结果已保存: {out_path}")
    print(f"总计: {total}, 通过: {passed}, 失败: {total - passed}")

    assert total - passed == 0, f"{total - passed} 个测试失败"
    print("全部通过!")


if __name__ == "__main__":
    main()
