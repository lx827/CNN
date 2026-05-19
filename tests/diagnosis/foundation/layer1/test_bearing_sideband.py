"""
Layer 1 信号基元 — bearing_sideband 正确性验证

测试 compute_sideband_density — 包络谱边频带密度分析

输出: layer1/output/bearing_sideband.json
"""
import json, sys, os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.bearing_sideband import compute_sideband_density
from tests.diagnosis.foundation.layer1.synthetic_signals import NumpyEncoder

OUTPUT_DIR = Path(__file__).parent / "output"
FS = 8192


def test_sideband_density_synthetic():
    """合成包络谱：已知边频带结构的密度检测"""
    print("\n--- 合成边频带密度 ---")
    results = []

    # 构造包络谱：BPFO=90Hz 周围有 ±fr=25Hz 的强边频带
    df = 0.5
    freqs = np.arange(0, 500, df)
    amps = np.random.randn(len(freqs)) * 0.1 + 0.2  # 噪声底噪
    amps = np.abs(amps)

    bpfo = 90.0
    mod_freq = 25.0
    # 在 BPFO 位置放强峰
    idx_bpfo = np.argmin(np.abs(freqs - bpfo))
    amps[idx_bpfo] = 10.0
    # 在 ±mod_freq 位置放边频带
    for n in range(1, 4):
        for side, mult in [("upper", 1), ("lower", -1)]:
            f = bpfo + mult * n * mod_freq
            idx = np.argmin(np.abs(freqs - f))
            amps[idx] = 3.0  # SNR ≈ 3/0.2 = 15

    background = float(np.median(amps))
    density = compute_sideband_density(freqs, amps, bpfo, mod_freq, background,
                                        max_harmonics=3, snr_threshold=3.0, df=df)

    # 应该有显著的边频带密度
    sig_ok = density["significant_count"] >= 3  # 6个边频带中至少3个over threshold
    results.append({
        "test": "sideband_BPFO_with_modulation",
        "density": density["density"],
        "significant_count": density["significant_count"],
        "total_searched": density["total_searched"],
        "asymmetry": density["asymmetry"],
        "passed": sig_ok,
    })
    print(f"  [{'PASS' if sig_ok else 'FAIL'}] BPFO±fr边带: density={density['density']:.2f}, "
          f"significant={density['significant_count']}/{density['total_searched']}")

    return results


def test_sideband_density_clean():
    """无调制包络谱：边频带密度应为0"""
    print("\n--- 无调制边频带 ---")
    results = []

    df = 0.5
    freqs = np.arange(0, 500, df)
    amps = np.abs(np.random.randn(len(freqs)) * 0.1 + 0.2)
    # 只在 BPFO 位置放峰，不加边频带
    bpfo = 90.0
    idx = np.argmin(np.abs(freqs - bpfo))
    amps[idx] = 10.0

    background = float(np.median(amps))
    density = compute_sideband_density(freqs, amps, bpfo, 25.0, background,
                                        max_harmonics=3, snr_threshold=3.0, df=df)

    # 无调制：边频带应该很少
    clean_ok = density["significant_count"] <= 1
    results.append({
        "test": "sideband_no_modulation",
        "density": density["density"],
        "significant_count": density["significant_count"],
        "passed": clean_ok,
    })
    print(f"  [{'PASS' if clean_ok else 'FAIL'}] 无调制: density={density['density']:.2f}, "
          f"significant={density['significant_count']}/{density['total_searched']}")

    return results


def main():
    print("=" * 60)
    print("Layer 1: bearing_sideband — 边频带密度正确性")
    print("=" * 60)

    all_results = {
        "synthetic_with_mod": test_sideband_density_synthetic(),
        "synthetic_clean": test_sideband_density_clean(),
    }

    total = passed = 0
    for items in all_results.values():
        for it in items:
            total += 1
            if it.get("passed", False): passed += 1
    all_results["summary"] = {"total": total, "passed": passed, "failed": total - passed}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "bearing_sideband.json"
    out.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder, ensure_ascii=False), encoding='utf-8')
    s = all_results["summary"]
    print(f"\n结果: {out}\n总计: {s['total']}, 通过: {s['passed']}, 失败: {s['failed']}")


if __name__ == "__main__":
    main()
