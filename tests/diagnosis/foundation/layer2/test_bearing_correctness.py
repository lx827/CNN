"""
Layer 2 轴承诊断 — bearing.py 正确性验证

测试 bearing.py 中依赖 Layer 1 的函数：
  envelope_analysis, fast_kurtogram, med_envelope_analysis,
  teager_envelope_analysis, spectral_kurtosis_envelope_analysis

原则：合成已知故障频率的信号，验证各方法能否检出目标频率。

输出: layer2/output/bearing_correctness.json
"""
import json
import sys
import os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.bearing import (
    envelope_analysis, fast_kurtogram, med_envelope_analysis,
    teager_envelope_analysis, spectral_kurtosis_envelope_analysis,
)
from app.services.diagnosis.signal_utils import compute_fft_spectrum, kurtosis, find_peaks_in_spectrum
from tests.diagnosis.foundation.layer1.synthetic_signals import (
    NumpyEncoder, bearing_outer_race, impulse_train,
)

OUTPUT_DIR = Path(__file__).parent / "output"
FS = 8192


def _get_peak_snr(found):
    """从 find_peaks_in_spectrum 结果中提取峰值频率和 SNR"""
    fund = found.get("fundamental")
    if fund:
        return fund["freq"], fund["snr"]
    return 0.0, 0.0


# ═══════════════════════════════════════════════════════════
# 1. envelope_analysis — 标准包络分析
# ═══════════════════════════════════════════════════════════

def test_envelope_analysis():
    """标准包络分析：合成轴承外圈故障信号"""
    print("\n--- envelope_analysis ---")
    results = []

    # 1a. 合成外圈故障: BPFO=90Hz
    sig, fs, gt = bearing_outer_race(bpfo=90.0, rot_freq=25.0, duration=3.0, fs=FS, snr_db=15)
    res = envelope_analysis(sig, fs, fc=3000, bw=2000, f_low_pass=500, max_freq=500)
    peak_f, snr = _get_peak_snr(find_peaks_in_spectrum(np.array(res["envelope_freq"]), np.array(res["envelope_amp"]), target_freq=90.0, tolerance_hz=3.0))
    freq_ok = abs(peak_f - 90.0) < 5.0
    snr_ok = snr > 3.0
    passed = freq_ok and snr_ok
    results.append({
        "test": "envelope_bpfo_90Hz",
        "target_freq": 90.0,
        "detected_peak": round(peak_f, 2),
        "snr": round(snr, 2),
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] BPFO=90Hz: peak={peak_f:.1f}Hz, SNR={snr:.1f}")

    # 1b. 纯冲击序列: 100Hz
    sig, fs, gt = impulse_train(impulse_freq=100.0, duration=3.0, fs=FS, snr_db=15)
    res = envelope_analysis(sig, fs, fc=2000, bw=1500, f_low_pass=500, max_freq=500)
    peak_f, snr = _get_peak_snr(find_peaks_in_spectrum(np.array(res["envelope_freq"]), np.array(res["envelope_amp"]), target_freq=100.0, tolerance_hz=3.0))
    freq_ok = abs(peak_f - 100.0) < 5.0
    snr_ok = snr > 3.0
    passed = freq_ok and snr_ok
    results.append({
        "test": "envelope_impulse_100Hz",
        "target_freq": 100.0,
        "detected_peak": round(peak_f, 2),
        "snr": round(snr, 2),
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] 冲击100Hz: peak={peak_f:.1f}Hz, SNR={snr:.1f}")

    return results


# ═══════════════════════════════════════════════════════════
# 2. fast_kurtogram — 谱峭度选带
# ═══════════════════════════════════════════════════════════

def test_fast_kurtogram():
    """Fast Kurtogram：合成冲击信号验证最优频带选择"""
    print("\n--- fast_kurtogram ---")
    results = []

    sig, fs, gt = bearing_outer_race(bpfo=90.0, rot_freq=25.0, duration=2.0, fs=FS, snr_db=15)
    res = fast_kurtogram(sig, fs, max_level=5, f_low=100)

    # 验证：返回了最优频带参数
    has_optimal = res.get("optimal_fc", 0) > 0 and res.get("optimal_bw", 0) > 0
    # 包络谱应能检出 BPFO
    peak_f, snr = _get_peak_snr(find_peaks_in_spectrum(np.array(res["envelope_freq"]), np.array(res["envelope_amp"]), target_freq=90.0, tolerance_hz=5.0))
    freq_ok = abs(peak_f - 90.0) < 10.0
    passed = has_optimal and freq_ok
    results.append({
        "test": "fast_kurtogram_bpfo",
        "optimal_fc": round(res.get("optimal_fc", 0), 1),
        "optimal_bw": round(res.get("optimal_bw", 0), 1),
        "detected_peak": round(peak_f, 2),
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] Kurtogram: fc={res.get('optimal_fc', 0):.0f}Hz, bw={res.get('optimal_bw', 0):.0f}Hz, peak={peak_f:.1f}Hz")

    return results


# ═══════════════════════════════════════════════════════════
# 3. med_envelope_analysis — MED 解卷积 + 包络
# ═══════════════════════════════════════════════════════════

def test_med_envelope():
    """MED：验证解卷积后峭度提升"""
    print("\n--- med_envelope_analysis ---")
    results = []

    sig, fs, gt = bearing_outer_race(bpfo=90.0, rot_freq=25.0, duration=2.0, fs=FS, snr_db=10)
    res = med_envelope_analysis(sig, fs, med_filter_len=64, max_freq=500)

    kurt_before = res.get("kurtosis_before", 0)
    kurt_after = res.get("kurtosis_after", 0)
    kurt_improved = kurt_after > kurt_before * 1.2  # MED 应显著提升峭度

    peak_f, snr = _get_peak_snr(find_peaks_in_spectrum(np.array(res["envelope_freq"]), np.array(res["envelope_amp"]), target_freq=90.0, tolerance_hz=5.0))
    freq_ok = abs(peak_f - 90.0) < 10.0

    passed = kurt_improved and freq_ok
    results.append({
        "test": "med_envelope_bpfo",
        "kurt_before": round(kurt_before, 2),
        "kurt_after": round(kurt_after, 2),
        "detected_peak": round(peak_f, 2),
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] MED: kurt_before={kurt_before:.1f}, kurt_after={kurt_after:.1f}, peak={peak_f:.1f}Hz")

    return results


# ═══════════════════════════════════════════════════════════
# 4. teager_envelope_analysis — Teager 算子
# ═══════════════════════════════════════════════════════════

def test_teager_envelope():
    """Teager 能量算子包络分析"""
    print("\n--- teager_envelope_analysis ---")
    results = []

    sig, fs, gt = bearing_outer_race(bpfo=90.0, rot_freq=25.0, duration=2.0, fs=FS, snr_db=15)
    res = teager_envelope_analysis(sig, fs, max_freq=500)

    peak_f, snr = _get_peak_snr(find_peaks_in_spectrum(np.array(res["envelope_freq"]), np.array(res["envelope_amp"]), target_freq=90.0, tolerance_hz=5.0))
    freq_ok = abs(peak_f - 90.0) < 10.0
    snr_ok = snr > 2.0
    passed = freq_ok and snr_ok
    results.append({
        "test": "teager_envelope_bpfo",
        "detected_peak": round(peak_f, 2),
        "snr": round(snr, 2),
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] Teager: peak={peak_f:.1f}Hz, SNR={snr:.1f}")

    return results


# ═══════════════════════════════════════════════════════════
# 5. spectral_kurtosis_envelope_analysis — 谱峭度重加权
# ═══════════════════════════════════════════════════════════

def test_spectral_kurtosis_envelope():
    """谱峭度重加权包络分析"""
    print("\n--- spectral_kurtosis_envelope_analysis ---")
    results = []

    sig, fs, gt = bearing_outer_race(bpfo=90.0, rot_freq=25.0, duration=2.0, fs=FS, snr_db=15)
    res = spectral_kurtosis_envelope_analysis(sig, fs, max_level=4, f_low=100, max_freq=500)

    peak_f, snr = _get_peak_snr(find_peaks_in_spectrum(np.array(res["envelope_freq"]), np.array(res["envelope_amp"]), target_freq=90.0, tolerance_hz=5.0))
    freq_ok = abs(peak_f - 90.0) < 10.0
    snr_ok = snr > 2.0
    passed = freq_ok and snr_ok
    results.append({
        "test": "sk_envelope_bpfo",
        "detected_peak": round(peak_f, 2),
        "snr": round(snr, 2),
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] SK: peak={peak_f:.1f}Hz, SNR={snr:.1f}")

    return results


# ═══════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("Layer 2: bearing.py — 轴承诊断正确性验证")
    print("=" * 60)

    all_results = {
        "envelope_analysis": test_envelope_analysis(),
        "fast_kurtogram": test_fast_kurtogram(),
        "med_envelope": test_med_envelope(),
        "teager_envelope": test_teager_envelope(),
        "spectral_kurtosis_envelope": test_spectral_kurtosis_envelope(),
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
    out_path = OUTPUT_DIR / "bearing_correctness.json"
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
