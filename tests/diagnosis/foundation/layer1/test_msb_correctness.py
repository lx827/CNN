"""
Layer 1 信号基元 — gear/msb 正确性验证

测试 msb_residual_sideband_analysis 的返回结构、边界安全、
合成调制信号的 MSB-SNR 检测能力。

输出: layer1/output/msb_correctness.json
"""
import json, sys, os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.gear.msb import msb_residual_sideband_analysis
from tests.diagnosis.foundation.layer1.synthetic_signals import NumpyEncoder

OUTPUT_DIR = Path(__file__).parent / "output"
FS = 8192


def _make_modulated_signal(mesh_freq=500.0, carrier_freq=12.5, duration=2.0, snr_db=20):
    """构造啮合频率 + 调制边频带的合成信号"""
    t = np.arange(0, duration, 1.0 / FS)
    # 啮合频率载波
    mesh = np.sin(2 * np.pi * mesh_freq * t)
    # 调制（carrier 频率的边频带）
    modulation = 0.5 * np.cos(2 * np.pi * carrier_freq * t)
    sig = (1 + modulation) * mesh
    # 加噪声
    noise = np.random.randn(len(t)) * (10 ** (-snr_db / 20))
    return sig + noise


def test_msb_structure():
    """MSB 分析返回结构完整性"""
    print("\n--- MSB 返回结构 ---")
    results = []

    sig = _make_modulated_signal(duration=1.0)
    res = msb_residual_sideband_analysis(sig, FS, mesh_freq=500.0, carrier_freq=12.5)

    required_keys = [
        "valid", "msb_se_slice", "msb_fc_axis", "msb_spectrum",
        "msb_delta_axis", "sun_fault_msb_snr", "planet_fault_msb_snr",
        "residual_sideband_ratio", "sun_slice_freq", "planet_slice_freq",
        "n_segments", "seg_len", "df",
    ]
    all_present = all(k in res for k in required_keys)
    results.append({"test": "msb_structure", "keys_present": all_present, "passed": all_present})
    print(f"  [{'PASS' if all_present else 'FAIL'}] 所有键存在: {all_present}")

    # valid 应为 True
    valid_ok = res["valid"] is True
    results.append({"test": "msb_valid", "valid": res["valid"], "passed": valid_ok})
    print(f"  [{'PASS' if valid_ok else 'FAIL'}] valid=True")

    # 切片频率正确
    sun_f = res["sun_slice_freq"]
    planet_f = res["planet_slice_freq"]
    freq_ok = abs(sun_f - (2 * 500 - 12.5)) < 1.0 and abs(planet_f - (2 * 500 + 12.5)) < 1.0
    results.append({"test": "msb_slice_freqs", "sun": sun_f, "planet": planet_f, "passed": freq_ok})
    print(f"  [{'PASS' if freq_ok else 'FAIL'}] 切片频率: sun={sun_f:.1f}, planet={planet_f:.1f}")

    return results


def test_msb_empty_input():
    """空/极短输入安全处理"""
    print("\n--- MSB 边界安全 ---")
    results = []

    # 空信号
    res = msb_residual_sideband_analysis(np.array([]), FS, mesh_freq=500.0)
    empty_ok = res["valid"] is False and res["sun_fault_msb_snr"] == 0.0
    results.append({"test": "msb_empty_signal", "valid": res["valid"], "passed": empty_ok})
    print(f"  [{'PASS' if empty_ok else 'FAIL'}] 空信号: valid={res['valid']}")

    # 极短信号
    res2 = msb_residual_sideband_analysis(np.array([1.0, 2.0]), FS, mesh_freq=500.0)
    short_ok = res2["valid"] is False
    results.append({"test": "msb_short_signal", "valid": res2["valid"], "passed": short_ok})
    print(f"  [{'PASS' if short_ok else 'FAIL'}] 短信号: valid={res2['valid']}")

    # 无效参数
    res3 = msb_residual_sideband_analysis(np.ones(1000), FS, mesh_freq=-1.0)
    param_ok = res3["valid"] is False
    results.append({"test": "msb_invalid_param", "valid": res3["valid"], "passed": param_ok})
    print(f"  [{'PASS' if param_ok else 'FAIL'}] 无效参数: valid={res3['valid']}")

    return results


def test_msb_synthetic_detection():
    """合成调制信号的 MSB-SNR 检测"""
    print("\n--- MSB 合成检测 ---")
    results = []

    np.random.seed(42)
    sig = _make_modulated_signal(mesh_freq=500.0, carrier_freq=12.5, duration=2.0, snr_db=15)
    res = msb_residual_sideband_analysis(sig, FS, mesh_freq=500.0, carrier_freq=12.5)

    snr_ok = res["sun_fault_msb_snr"] > 1.0 or res["planet_fault_msb_snr"] > 1.0
    results.append({
        "test": "msb_synthetic_snr",
        "sun_snr": res["sun_fault_msb_snr"],
        "planet_snr": res["planet_fault_msb_snr"],
        "passed": snr_ok,
    })
    print(f"  [{'PASS' if snr_ok else 'FAIL'}] 合成调制 SNR: sun={res['sun_fault_msb_snr']:.2f}, planet={res['planet_fault_msb_snr']:.2f}")

    return results


def main():
    print("=" * 60)
    print("Layer 1: gear/msb — MSB 残余边频带正确性")
    print("=" * 60)

    all_results = {
        "structure": test_msb_structure(),
        "empty_input": test_msb_empty_input(),
        "synthetic": test_msb_synthetic_detection(),
    }

    total = passed = 0
    for items in all_results.values():
        for it in items:
            total += 1
            if it.get("passed", False): passed += 1
    all_results["summary"] = {"total": total, "passed": passed, "failed": total - passed}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "msb_correctness.json"
    out.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder, ensure_ascii=False), encoding='utf-8')
    s = all_results["summary"]
    print(f"\n结果: {out}\n总计: {s['total']}, 通过: {s['passed']}, 失败: {s['failed']}")


if __name__ == "__main__":
    main()
