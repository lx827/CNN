"""
Layer 2 阶次跟踪 — order_tracking.py 正确性验证

测试 order_tracking.py 中依赖 Layer 1 的函数：
  _compute_order_spectrum, _compute_order_spectrum_multi_frame,
  _compute_order_spectrum_varying_speed

原则：合成已知转速和啮合频率的信号，验证阶次谱峰位置正确。

输出: layer2/output/order_tracking_correctness.json
"""
import json
import sys
import os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.order_tracking import (
    _compute_order_spectrum, _compute_order_spectrum_multi_frame,
    _compute_order_spectrum_varying_speed,
)
from app.services.diagnosis.signal_utils import compute_fft_spectrum, _search_peak_in_band
from tests.diagnosis.foundation.layer1.synthetic_signals import (
    NumpyEncoder, gear_mesh, sinusoidal, chirp_rotating,
)

OUTPUT_DIR = Path(__file__).parent / "output"
FS = 8192


def _find_order_peak(order_axis, spectrum, target_order, tol=0.5):
    """委托云端原子函数搜索阶次谱峰"""
    peak = _search_peak_in_band(np.array(order_axis), np.array(spectrum),
                                target_order, tol)
    if peak:
        return peak["freq"], peak["amp"]
    return 0.0, 0.0


# ═══════════════════════════════════════════════════════════
# 1. _compute_order_spectrum — 恒定转速单帧阶次谱
# ═══════════════════════════════════════════════════════════

def test_order_spectrum_constant():
    """恒定转速：合成齿轮信号验证阶次谱峰在啮合阶次"""
    print("\n--- _compute_order_spectrum (恒定转速) ---")
    results = []

    rot_freq = 25.0
    mesh_freq = 450.0
    sig, fs, gt = gear_mesh(mesh_freq=mesh_freq, rot_freq=rot_freq, duration=4.0, fs=FS, snr_db=30)

    order_axis, spectrum = _compute_order_spectrum(sig, fs, rot_freq, samples_per_rev=512)

    # 啮合阶次 = 450 / 25 = 18
    mesh_order = mesh_freq / rot_freq
    peak_order, peak_amp = _find_order_peak(order_axis, spectrum, mesh_order, tol=1.0)
    order_ok = abs(peak_order - mesh_order) < 1.0
    amp_ok = peak_amp > 0

    passed = order_ok and amp_ok
    results.append({
        "test": "order_spectrum_constant_mesh",
        "rot_freq": rot_freq,
        "mesh_order": mesh_order,
        "detected_peak_order": round(peak_order, 2),
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] 啮合阶次={mesh_order}: 检出={peak_order:.1f}")

    # 纯正弦：阶次=1 应清晰
    sig_sin, _, _ = sinusoidal(freq=rot_freq, duration=4.0, fs=FS)
    order_axis2, spectrum2 = _compute_order_spectrum(sig_sin, fs, rot_freq, samples_per_rev=512)
    peak_order2, _ = _find_order_peak(order_axis2, spectrum2, 1.0, tol=0.5)
    order_ok2 = abs(peak_order2 - 1.0) < 0.5
    results.append({
        "test": "order_spectrum_constant_sine",
        "detected_peak_order": round(peak_order2, 2),
        "passed": order_ok2,
    })
    print(f"  [{'PASS' if order_ok2 else 'FAIL'}] 正弦阶次=1: 检出={peak_order2:.1f}")

    return results


# ═══════════════════════════════════════════════════════════
# 2. _compute_order_spectrum_multi_frame — 缓变转速
# ═══════════════════════════════════════════════════════════

def test_order_spectrum_multi_frame():
    """缓变转速：合成扫频信号验证多帧平均"""
    print("\n--- _compute_order_spectrum_multi_frame (缓变转速) ---")
    results = []

    sig, fs, gt = chirp_rotating(freq_start=20.0, freq_end=30.0, duration=5.0, fs=FS)
    orders, spectrum, median_rf, std_rf = _compute_order_spectrum_multi_frame(
        sig, fs, freq_range=(15, 35), samples_per_rev=512, max_order=20,
        frame_duration=1.0, overlap=0.5,
    )

    has_spectrum = len(spectrum) > 0 and len(orders) > 0
    median_ok = 20.0 < median_rf < 30.0  # 中值转频应在扫频范围内
    std_ok = std_rf < 5.0  # 标准差不应过大

    passed = has_spectrum and median_ok and std_ok
    results.append({
        "test": "order_spectrum_multi_frame",
        "median_rot_freq": round(median_rf, 2),
        "std_rot_freq": round(std_rf, 2),
        "n_orders": len(orders),
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] 多帧: median_rf={median_rf:.1f}Hz, std={std_rf:.1f}Hz, n_orders={len(orders)}")

    return results


# ═══════════════════════════════════════════════════════════
# 3. _compute_order_spectrum_varying_speed — 变速跟踪
# ═══════════════════════════════════════════════════════════

def test_order_spectrum_varying_speed():
    """变速：合成扫频信号验证变速阶次跟踪"""
    print("\n--- _compute_order_spectrum_varying_speed (变速) ---")
    results = []

    sig, fs, gt = chirp_rotating(freq_start=15.0, freq_end=35.0, duration=5.0, fs=FS)
    orders, spectrum, median_rf, std_rf = _compute_order_spectrum_varying_speed(
        sig, fs, freq_range=(10, 40), samples_per_rev=512, max_order=20,
        nperseg=1024, noverlap=512,
    )

    has_spectrum = len(spectrum) > 0 and len(orders) > 0
    median_ok = 15.0 < median_rf < 35.0
    std_ok = std_rf < 10.0

    passed = has_spectrum and median_ok and std_ok
    results.append({
        "test": "order_spectrum_varying_speed",
        "median_rot_freq": round(median_rf, 2),
        "std_rot_freq": round(std_rf, 2),
        "n_orders": len(orders),
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] 变速: median_rf={median_rf:.1f}Hz, std={std_rf:.1f}Hz, n_orders={len(orders)}")

    return results


# ═══════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("Layer 2: order_tracking.py — 阶次跟踪正确性验证")
    print("=" * 60)

    all_results = {
        "order_spectrum_constant": test_order_spectrum_constant(),
        "order_spectrum_multi_frame": test_order_spectrum_multi_frame(),
        "order_spectrum_varying_speed": test_order_spectrum_varying_speed(),
    }

    total = 0
    passed = 0
    for category, items in all_results.items():
        for item in items:
            total += 1
            if item.get("passed", False):
                passed += 1

    all_results["summary"] = {"total": total, "passed": passed, "failed": total - passed}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "order_tracking_correctness.json"
    out_path.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder, ensure_ascii=False), encoding='utf-8')
    print(f"\n结果已保存: {out_path}")

    s = all_results["summary"]
    print(f"\n总计: {s['total']}, 通过: {s['passed']}, 失败: {s['failed']}")
    if s["failed"] > 0:
        print(f"WARNING: {s['failed']} 个测试失败")
    else:
        print("全部通过!")


if __name__ == "__main__":
    main()
