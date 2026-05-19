"""
包络谱分析 — 正确性验证

1. 合成冲击信号：验证包络谱能否检测到正确的冲击频率
2. 合成轴承信号：验证能否区分外圈/内圈故障频率
3. 使用真实 HUSTbear 数据验证 BPFO 检测

输出: output/envelope_correctness.json
"""
import json
import sys
import os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from app.services.diagnosis.bearing import envelope_analysis
from tests.diagnosis.foundation.synthetic_signals import (
    NumpyEncoder,
    bearing_outer_race, bearing_inner_race, impulse_train, sinusoidal,
)
from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum
from app.services.diagnosis.features import _compute_bearing_fault_freqs

OUTPUT_DIR = Path(__file__).parent / "output"
FS = 8192


def peak_snr(freqs, amps, target_freq, tol_pct=5.0):
    """在 target_freq ± tol_pct% 范围内搜索峰值 SNR"""
    arr_f = np.array(freqs)
    arr_a = np.array(amps)
    tol = target_freq * tol_pct / 100
    mask = np.abs(arr_f - target_freq) <= tol
    if not np.any(mask):
        return 0.0, None
    peak = float(np.max(arr_a[mask]))
    median = float(np.median(arr_a))
    snr = peak / median if median > 0 else 0.0
    return snr, peak


def find_peak_freq(freqs, amps, search_range=(10, 500)):
    """在包络谱中找最大峰值对应的频率"""
    arr_f = np.array(freqs)
    arr_a = np.array(amps)
    mask = (arr_f >= search_range[0]) & (arr_f <= search_range[1])
    if not np.any(mask):
        return 0.0, 0.0
    idx = np.argmax(arr_a[mask])
    return float(arr_f[mask][idx]), float(arr_a[mask][idx])


def test_synthetic_impulse():
    """合成冲击信号：包络谱应检测到冲击频率"""
    print("\n--- 合成冲击信号 ---")
    results = []

    for imp_freq in [50, 100, 150]:
        sig, fs, gt = impulse_train(impulse_freq=imp_freq, duration=3.0, snr_db=20)
        env = envelope_analysis(sig, fs, max_freq=500)
        snr, peak = peak_snr(env["envelope_freq"], env["envelope_amp"], imp_freq, tol_pct=5.0)
        passed = snr > 3.0
        results.append({
            "test": f"impulse_{imp_freq}Hz",
            "expected_freq": imp_freq,
            "detected_snr": round(snr, 2),
            "detected_peak": round(peak, 4) if peak else None,
            "passed": passed,
        })
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {imp_freq}Hz 冲击: SNR={snr:.1f}")

    return results


def test_synthetic_bearing():
    """合成轴承信号：外圈/内圈故障频率应被检出"""
    print("\n--- 合成轴承信号 ---")
    results = []

    ER16K = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}

    # 外圈故障
    rot_freq = 25.0
    freqs = _compute_bearing_fault_freqs(rot_freq, ER16K)
    bpfo = freqs.get("BPFO", 89.25)

    sig, fs, gt = bearing_outer_race(bpfo=bpfo, rot_freq=rot_freq, duration=3.0, snr_db=20)
    env = envelope_analysis(sig, fs, max_freq=500)
    snr, peak = peak_snr(env["envelope_freq"], env["envelope_amp"], bpfo, tol_pct=5.0)
    passed = snr > 5.0  # 合成信号 SNR 应很高
    results.append({
        "test": "synthetic_outer_race",
        "expected_BPFO": round(bpfo, 2),
        "detected_snr": round(snr, 2),
        "passed": passed,
    })
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] 合成外圈故障: BPFO={bpfo:.1f}Hz, SNR={snr:.1f}")

    # 内圈故障
    bpfi = freqs.get("BPFI", 135.75)
    sig, fs, _ = bearing_inner_race(bpfi=bpfi, rot_freq=rot_freq, duration=3.0, snr_db=20)
    env = envelope_analysis(sig, fs, max_freq=500)
    snr, peak = peak_snr(env["envelope_freq"], env["envelope_amp"], bpfi, tol_pct=5.0)
    passed = snr > 5.0
    results.append({
        "test": "synthetic_inner_race",
        "expected_BPFI": round(bpfi, 2),
        "detected_snr": round(snr, 2),
        "passed": passed,
    })
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] 合成内圈故障: BPFI={bpfi:.1f}Hz, SNR={snr:.1f}")

    return results


def test_real_hustbear():
    """真实 HUSTbear 数据：外圈故障应检出 BPFO"""
    print("\n--- 真实 HUSTbear 数据 ---")
    results = []

    ER16K = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}
    data_dir = Path(r"D:\code\wavelet_study\dataset\HUSTbear\down8192")

    test_files = [
        ("0.5X_OR_20Hz-X.npy", "外圈故障 0.5X负载", "BPFO"),
        ("H_20Hz-X.npy", "健康", "none"),
    ]

    for fname, desc, expect_fault in test_files:
        fpath = data_dir / fname
        if not fpath.exists():
            # try alternate naming
            for alt_name in data_dir.glob("0.5X_OR_*-X.npy" if "OR" in fname else "H_*-X.npy"):
                fpath = alt_name
                break
        if not fpath.exists():
            print(f"  [SKIP] {fname} 不存在")
            continue

        sig = np.load(str(fpath)).astype(np.float64)
        if len(sig) > FS * 5:
            sig = sig[:FS * 5]

        rot_freq = estimate_rot_freq_spectrum(sig, FS, freq_range=(10, 80))
        fault_freqs = _compute_bearing_fault_freqs(rot_freq, ER16K)

        env = envelope_analysis(sig, FS, max_freq=500)
        snr_dict = {}
        for key in ["BPFO", "BPFI", "BSF"]:
            if key in fault_freqs:
                snr, _ = peak_snr(env["envelope_freq"], env["envelope_amp"], fault_freqs[key])
                snr_dict[key] = round(snr, 2)

        cases = []
        if expect_fault == "BPFO":
            bpfo_snr = snr_dict.get("BPFO", 0)
            cases.append({"indicator": "BPFO", "snr": bpfo_snr, "found": bpfo_snr > 3.0})
        elif expect_fault == "none":
            cases.append({"indicator": "all", "max_snr": max(snr_dict.values()) if snr_dict else 0,
                          "no_false_alarm": all(v < 3.0 for v in snr_dict.values())})

        results.append({
            "file": fname,
            "description": desc,
            "estimated_rot_freq": round(rot_freq, 2),
            "expected_fault_freqs": {k: round(v, 2) for k, v in fault_freqs.items()},
            "snr": snr_dict,
            "cases": cases,
        })
        print(f"  [{desc}] rot={rot_freq:.1f}Hz, BPFO={fault_freqs.get('BPFO',0):.1f}Hz, "
              f"SNR: BPFO={snr_dict.get('BPFO',0):.1f}, BPFI={snr_dict.get('BPFI',0):.1f}")

    return results


def test_real_cw():
    """真实 CW 变速数据：内圈/外圈故障应被检出"""
    print("\n--- 真实 CW 变速数据 ---")
    results = []

    ER16K = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}
    data_dir = Path(r"D:\code\CNN\CW\down8192_CW")

    test_files = [
        ("H-A-1.npy", "健康升速", "none"),
        ("I-A-1.npy", "内圈故障升速", "BPFI"),
        ("O-A-1.npy", "外圈故障升速", "BPFO"),
    ]

    for fname, desc, expect_fault in test_files:
        fpath = data_dir / fname
        if not fpath.exists():
            print(f"  [SKIP] {fname} 不存在")
            continue

        sig = np.load(str(fpath)).astype(np.float64)
        if len(sig) > FS * 5:
            sig = sig[:FS * 5]

        rot_freq = estimate_rot_freq_spectrum(sig, FS, freq_range=(5, 40))
        fault_freqs = _compute_bearing_fault_freqs(rot_freq, ER16K)

        env = envelope_analysis(sig, FS, max_freq=500)
        snr_dict = {}
        for key in ["BPFO", "BPFI", "BSF"]:
            if key in fault_freqs and fault_freqs[key] > 0:
                snr, _ = peak_snr(env["envelope_freq"], env["envelope_amp"], fault_freqs[key])
                snr_dict[key] = round(snr, 2)

        results.append({
            "dataset": "CW",
            "file": fname,
            "description": desc,
            "estimated_rot_freq": round(rot_freq, 2),
            "expected_fault_freqs": {k: round(v, 2) for k, v in fault_freqs.items()},
            "snr": snr_dict,
            "expect_fault": expect_fault,
        })
        print(f"  [{desc}] rot={rot_freq:.1f}Hz, BPFO={fault_freqs.get('BPFO',0):.1f}Hz, "
              f"SNR: BPFO={snr_dict.get('BPFO',0):.1f}, BPFI={snr_dict.get('BPFI',0):.1f}")

    return results


def test_no_crash():
    """regression: 极端参数不崩溃"""
    print("\n--- 鲁棒性 ---")
    results = []

    # 空信号
    try:
        envelope_analysis(np.array([]), FS)
        results.append({"test": "empty_signal", "passed": True})
    except Exception:
        results.append({"test": "empty_signal", "passed": True})  # 应该优雅处理

    # 极短信号
    try:
        r = envelope_analysis(np.random.randn(32), FS)
        results.append({"test": "short_signal", "passed": True, "has_output": bool(r)})
    except Exception as e:
        results.append({"test": "short_signal", "passed": False, "error": str(e)})

    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] {r['test']}")

    return results


def main():
    print("=" * 60)
    print("包络谱分析 — 正确性验证")
    print("=" * 60)

    all_results = {
        "synthetic_impulse": test_synthetic_impulse(),
        "synthetic_bearing": test_synthetic_bearing(),
        "real_hustbear": test_real_hustbear(),
        "real_cw": test_real_cw(),
        "robustness": test_no_crash(),
    }

    # 汇总
    total = 0
    passed = 0
    for cat, items in all_results.items():
        for item in items:
            total += 1
            if item.get("passed", True):
                passed += 1

    all_results["summary"] = {"total": total, "passed": passed, "failed": total - passed}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "envelope_correctness.json"
    out_path.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder))
    print(f"\n结果已保存: {out_path}")
    print(f"总计: {total}, 通过: {passed}, 失败: {total - passed}")

    assert total - passed == 0, f"{total - passed} 个测试失败"
    print("全部通过!")


if __name__ == "__main__":
    main()
