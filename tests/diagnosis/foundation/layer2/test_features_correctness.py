"""
Layer 2 特征提取 — features.py 正确性验证

测试 features.py 中依赖 Layer 1 的函数：
  compute_time_features, _compute_bearing_fault_freqs, _compute_bearing_fault_orders,
  compute_fft_features, has_bearing_params, has_gear_params

原则：合成已知 ground truth 的信号，验证特征计算正确性。

输出: layer2/output/features_correctness.json
"""
import json
import sys
import os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.features import (
    compute_time_features, _compute_bearing_fault_freqs, _compute_bearing_fault_orders,
    compute_fft_features, has_bearing_params, has_gear_params,
)
from tests.diagnosis.foundation.layer1.synthetic_signals import (
    NumpyEncoder, sinusoidal, bearing_outer_race, gear_mesh, impulse_train,
)

OUTPUT_DIR = Path(__file__).parent / "output"
FS = 8192


# ═══════════════════════════════════════════════════════════
# 1. compute_time_features — 时域统计特征
# ═══════════════════════════════════════════════════════════

def test_time_features():
    """时域特征：已知信号的理论值对比"""
    print("\n--- compute_time_features ---")
    results = []

    # 1a. 正弦信号: A=1, 理论值已知
    sig, fs, _ = sinusoidal(freq=50.0, duration=3.0, fs=FS)
    feat = compute_time_features(sig)
    peak_ok = abs(feat["peak"] - 1.0) < 0.05
    rms_ok = abs(feat["rms"] - 1.0 / np.sqrt(2)) < 0.02
    crest_ok = abs(feat["crest_factor"] - np.sqrt(2)) < 0.05
    # 正弦峭度(fisher=False)理论值 = 1.5
    kurt_ok = abs(feat["kurtosis"] - 1.5) < 0.3
    margin_ok = abs(feat["margin"] - feat["peak"] / feat["rms"]) < 0.01
    shape_ok = abs(feat["shape_factor"] - feat["rms"] / feat["mean_abs"]) < 0.01
    impulse_ok = abs(feat["impulse_factor"] - feat["peak"] / feat["mean_abs"]) < 0.01

    passed = peak_ok and rms_ok and crest_ok and kurt_ok and margin_ok and shape_ok and impulse_ok
    results.append({
        "test": "time_features_sine",
        "peak": round(feat["peak"], 4), "peak_ok": peak_ok,
        "rms": round(feat["rms"], 4), "rms_ok": rms_ok,
        "crest": round(feat["crest_factor"], 4), "crest_ok": crest_ok,
        "kurtosis": round(feat["kurtosis"], 4), "kurt_ok": kurt_ok,
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] 正弦: peak={feat['peak']:.3f}, rms={feat['rms']:.3f}, crest={feat['crest_factor']:.3f}, kurt={feat['kurtosis']:.3f}")

    # 1b. 高斯噪声: kurtosis ≈ 3.0
    np.random.seed(42)
    noise = np.random.randn(50000)
    feat = compute_time_features(noise)
    kurt_ok = 2.8 < feat["kurtosis"] < 3.2
    skew_ok = abs(feat["skewness"]) < 0.05
    passed = kurt_ok and skew_ok
    results.append({
        "test": "time_features_gaussian",
        "kurtosis": round(feat["kurtosis"], 4), "kurt_ok": kurt_ok,
        "skewness": round(feat["skewness"], 4), "skew_ok": skew_ok,
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] 高斯噪声: kurt={feat['kurtosis']:.3f}, skew={feat['skewness']:.4f}")

    # 1c. 冲击信号: kurtosis 应显著 > 3
    sig, fs, _ = impulse_train(impulse_freq=100.0, duration=3.0, fs=FS, snr_db=15)
    feat = compute_time_features(sig)
    kurt_ok = feat["kurtosis"] > 5.0
    crest_ok = feat["crest_factor"] > 2.5
    passed = kurt_ok and crest_ok
    results.append({
        "test": "time_features_impulse",
        "kurtosis": round(feat["kurtosis"], 4), "kurt_ok": kurt_ok,
        "crest": round(feat["crest_factor"], 4), "crest_ok": crest_ok,
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] 冲击信号: kurt={feat['kurtosis']:.3f}, crest={feat['crest_factor']:.3f}")

    return results


# ═══════════════════════════════════════════════════════════
# 2. _compute_bearing_fault_freqs / orders — 公式正确性
# ═══════════════════════════════════════════════════════════

def test_bearing_fault_freqs():
    """轴承故障频率：理论公式验证 (HUSTbear ER-16K 参数)"""
    print("\n--- _compute_bearing_fault_freqs ---")
    results = []

    # HUSTbear ER-16K 参数
    params = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}
    rot_freq = 25.0

    freqs = _compute_bearing_fault_freqs(rot_freq, params)

    # 理论值 (来自 AGENTS.md 表: BPFI=5.43fr, BPFO=3.57fr)
    expected_bpfi = 5.43 * rot_freq
    expected_bpfo = 3.57 * rot_freq

    bpfi_ok = abs(freqs["BPFI"] - expected_bpfi) / expected_bpfi < 0.01
    bpfo_ok = abs(freqs["BPFO"] - expected_bpfo) / expected_bpfo < 0.01
    bsf_ok = freqs["BSF"] > 0 and freqs["FTF"] > 0

    passed = bpfi_ok and bpfo_ok and bsf_ok
    results.append({
        "test": "bearing_freqs_er16k_25Hz",
        "rot_freq": rot_freq,
        "params": params,
        "BPFO": round(freqs["BPFO"], 3), "BPFO_expected": round(expected_bpfo, 3), "BPFO_ok": bpfo_ok,
        "BPFI": round(freqs["BPFI"], 3), "BPFI_expected": round(expected_bpfi, 3), "BPFI_ok": bpfi_ok,
        "BSF": round(freqs["BSF"], 3),
        "FTF": round(freqs["FTF"], 3),
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] ER-16K @25Hz: BPFO={freqs['BPFO']:.1f}Hz(期望{expected_bpfo:.1f}), BPFI={freqs['BPFI']:.1f}Hz(期望{expected_bpfi:.1f})")

    # 阶次验证
    orders = _compute_bearing_fault_orders(rot_freq, params)
    order_ok = abs(orders["BPFI"] - 5.43) < 0.05 and abs(orders["BPFO"] - 3.57) < 0.05
    results.append({
        "test": "bearing_orders_er16k",
        "BPFI_order": round(orders["BPFI"], 3),
        "BPFO_order": round(orders["BPFO"], 3),
        "passed": order_ok,
    })
    print(f"  [{'PASS' if order_ok else 'FAIL'}] ER-16K 阶次: BPFI={orders['BPFI']:.2f}, BPFO={orders['BPFO']:.2f}")

    return results


# ═══════════════════════════════════════════════════════════
# 3. has_bearing_params / has_gear_params — 边界条件
# ═══════════════════════════════════════════════════════════

def test_param_validity():
    """参数有效性检查"""
    print("\n--- has_bearing_params / has_gear_params ---")
    results = []

    # bearing
    cases = [
        ({"n": 9, "d": 7.94, "D": 38.52}, True, "valid_params"),
        ({"n": 9, "d": 7.94}, False, "missing_D"),
        ({"n": 9, "d": 7.94, "D": 0}, False, "D_is_zero"),
        ({"n": 9, "d": 7.94, "D": None}, False, "D_is_none"),
        (None, False, "none_input"),
    ]
    for params, expected, name in cases:
        actual = has_bearing_params(params)
        ok = actual == expected
        results.append({"test": f"has_bearing_{name}", "expected": expected, "actual": actual, "passed": ok})
        print(f"  [{'PASS' if ok else 'FAIL'}] bearing {name}: expected={expected}, actual={actual}")

    # gear
    gear_cases = [
        ({"input": 18}, True, "valid_input"),
        ({"input": 0}, False, "input_zero"),
        ({"output": 27}, False, "missing_input"),
        (None, False, "none_input"),
    ]
    for params, expected, name in gear_cases:
        actual = has_gear_params(params)
        ok = actual == expected
        results.append({"test": f"has_gear_{name}", "expected": expected, "actual": actual, "passed": ok})
        print(f"  [{'PASS' if ok else 'FAIL'}] gear {name}: expected={expected}, actual={actual}")

    return results


# ═══════════════════════════════════════════════════════════
# 4. compute_fft_features — 频域特征提取
# ═══════════════════════════════════════════════════════════

def test_fft_features():
    """FFT 特征：合成齿轮/轴承信号验证能量比计算"""
    print("\n--- compute_fft_features ---")
    results = []

    # 4a. 合成齿轮信号: 啮合频率=450Hz, 转频=25Hz
    sig, fs, gt = gear_mesh(mesh_freq=450.0, rot_freq=25.0, duration=3.0, fs=FS, snr_db=30)
    gear_params = {"input": 18}
    feats = compute_fft_features(sig, fs, gear_params, None, 25.0)

    mesh_ok = abs(feats["mesh_freq_hz"] - 450.0) < 5.0
    ratio_ok = feats["mesh_freq_ratio"] > 0.3  # 啮合频率应占显著能量
    passed = mesh_ok and ratio_ok
    results.append({
        "test": "fft_features_gear_mesh",
        "mesh_freq_hz": round(feats["mesh_freq_hz"], 2),
        "mesh_freq_ratio": round(feats["mesh_freq_ratio"], 4),
        "sideband_total_ratio": round(feats.get("sideband_total_ratio", 0), 4),
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] 齿轮啮合: mesh={feats['mesh_freq_hz']:.1f}Hz, ratio={feats['mesh_freq_ratio']:.3f}")

    # 4b. 合成轴承信号: BPFO=90Hz
    sig, fs, gt = bearing_outer_race(bpfo=90.0, rot_freq=25.0, duration=3.0, fs=FS, snr_db=20)
    bearing_params = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}
    feats = compute_fft_features(sig, fs, None, bearing_params, 25.0)

    bpfo_hz = feats.get("BPFO_hz", 0)
    bpfo_ratio = feats.get("BPFO_ratio", 0)
    bpfo_ok = abs(bpfo_hz - 90.0) < 5.0
    ratio_ok = bpfo_ratio > 0.0003  # BPFO 频带应有可检测能量(原始频谱中占比小但非零)
    passed = bpfo_ok and ratio_ok
    results.append({
        "test": "fft_features_bearing_bpfo",
        "BPFO_hz": round(bpfo_hz, 2),
        "BPFO_ratio": round(bpfo_ratio, 4),
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] 轴承BPFO: BPFO={bpfo_hz:.1f}Hz, ratio={bpfo_ratio:.4f}")

    # 4c. 无参数时返回空
    sig, fs, _ = sinusoidal(freq=50.0, duration=1.0, fs=FS)
    feats = compute_fft_features(sig, fs, None, None, None)
    empty_ok = "mesh_freq_hz" not in feats and "BPFO_hz" not in feats
    passed = empty_ok and "estimated_rot_freq" in feats
    results.append({
        "test": "fft_features_no_params",
        "has_mesh": "mesh_freq_hz" in feats,
        "has_bpfo": "BPFO_hz" in feats,
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] 无参数安全: mesh={'mesh_freq_hz' in feats}, bpfo={'BPFO_hz' in feats}")

    return results


# ═══════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("Layer 2: features.py — 特征提取正确性验证")
    print("=" * 60)

    all_results = {
        "time_features": test_time_features(),
        "bearing_fault_freqs": test_bearing_fault_freqs(),
        "param_validity": test_param_validity(),
        "fft_features": test_fft_features(),
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
    out_path = OUTPUT_DIR / "features_correctness.json"
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
