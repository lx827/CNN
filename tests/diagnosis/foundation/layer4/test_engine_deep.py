"""
Layer 4 中央调度器 — engine.py 深层功能测试

测试 preprocess（各去噪方法分支）和 _estimate_rot_freq（转频估计）

输出: layer4/output/engine_deep.json
"""
import json, sys, os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.engine import DiagnosisEngine, DenoiseMethod
from tests.diagnosis.foundation.layer1.synthetic_signals import NumpyEncoder

OUTPUT_DIR = Path(__file__).parent / "output"
FS = 8192


def test_preprocess_none():
    """preprocess: NONE 只去直流"""
    print("\n--- preprocess NONE ---")
    results = []

    engine = DiagnosisEngine(denoise_method=DenoiseMethod.NONE)
    sig = np.ones(1000) * 5.0 + np.random.randn(1000) * 0.1
    out = engine.preprocess(sig)
    mean_near_zero = abs(np.mean(out)) < 0.1
    shape_ok = len(out) == len(sig)
    results.append({"test": "preprocess_none", "mean": round(float(np.mean(out)), 4),
                    "passed": mean_near_zero and shape_ok})
    print(f"  [{'PASS' if mean_near_zero and shape_ok else 'FAIL'}] NONE: mean={np.mean(out):.4f}, shape={shape_ok}")
    return results


def test_preprocess_wavelet():
    """preprocess: WAVELET 去噪"""
    print("\n--- preprocess WAVELET ---")
    results = []

    engine = DiagnosisEngine(denoise_method=DenoiseMethod.WAVELET)
    np.random.seed(1)
    sig = np.sin(2 * np.pi * 50 * np.arange(1000) / FS) + np.random.randn(1000) * 0.5
    out = engine.preprocess(sig)
    # 去噪后应降低噪声方差
    var_reduced = np.var(out) < np.var(sig) * 0.9
    results.append({"test": "preprocess_wavelet", "var_in": round(float(np.var(sig)), 4),
                    "var_out": round(float(np.var(out)), 4), "passed": var_reduced})
    print(f"  [{'PASS' if var_reduced else 'FAIL'}] WAVELET: var {np.var(sig):.3f} -> {np.var(out):.3f}")
    return results


def test_preprocess_vmd():
    """preprocess: VMD 去噪"""
    print("\n--- preprocess VMD ---")
    results = []

    engine = DiagnosisEngine(denoise_method=DenoiseMethod.VMD)
    np.random.seed(2)
    sig = np.sin(2 * np.pi * 100 * np.arange(2000) / FS) + np.random.randn(2000) * 0.3
    out = engine.preprocess(sig)
    # VMD 去噪后信号应仍有明显结构（非全0）
    not_zero = np.max(np.abs(out)) > 0.01
    results.append({"test": "preprocess_vmd", "max_amp": round(float(np.max(np.abs(out))), 4),
                    "passed": not_zero})
    print(f"  [{'PASS' if not_zero else 'FAIL'}] VMD: max_amp={np.max(np.abs(out)):.4f}")
    return results


def test_estimate_rot_freq():
    """_estimate_rot_freq: 恒定转速信号转频估计"""
    print("\n--- _estimate_rot_freq ---")
    results = []

    engine = DiagnosisEngine()
    rot_freq = 25.0
    t = np.arange(0, 2.0, 1.0 / FS)
    # 构造含 25Hz 转频谐波的信号
    sig = np.sin(2 * np.pi * rot_freq * t)
    for h in range(2, 6):
        sig += 0.3 * np.sin(2 * np.pi * rot_freq * h * t)
    sig += np.random.randn(len(t)) * 0.1

    rf, oa, os_, method, rsd = engine._estimate_rot_freq(sig, FS)
    rf_ok = rf is not None and abs(rf - rot_freq) / rot_freq < 0.15
    method_ok = method in ("multi_frame", "single_frame", "varying_speed", "fallback")
    results.append({
        "test": "estimate_rot_freq_const",
        "rot_freq": round(float(rf), 2), "method": method,
        "passed": rf_ok and method_ok,
    })
    print(f"  [{'PASS' if rf_ok and method_ok else 'FAIL'}] 恒速转频: rf={rf:.2f}Hz, method={method}")

    # 极短信号应回退
    rf2, _, _, method2, _ = engine._estimate_rot_freq(np.ones(50), FS)
    fallback_ok = method2 == "fallback" or rf2 == 10.0
    results.append({"test": "estimate_rot_freq_short", "method": method2, "passed": fallback_ok})
    print(f"  [{'PASS' if fallback_ok else 'FAIL'}] 短信号回退: method={method2}")

    return results


def main():
    print("=" * 60)
    print("Layer 4: engine.py — 深层功能测试")
    print("=" * 60)

    all_results = {
        "preprocess_none": test_preprocess_none(),
        "preprocess_wavelet": test_preprocess_wavelet(),
        "preprocess_vmd": test_preprocess_vmd(),
        "estimate_rot_freq": test_estimate_rot_freq(),
    }

    total = passed = 0
    for items in all_results.values():
        for it in items:
            total += 1
            if it.get("passed", False): passed += 1
    all_results["summary"] = {"total": total, "passed": passed, "failed": total - passed}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "engine_deep.json"
    out.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder, ensure_ascii=False), encoding='utf-8')
    s = all_results["summary"]
    print(f"\n结果: {out}\n总计: {s['total']}, 通过: {s['passed']}, 失败: {s['failed']}")


if __name__ == "__main__":
    main()
