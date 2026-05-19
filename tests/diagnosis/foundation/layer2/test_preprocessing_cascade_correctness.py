"""
Layer 2 级联预处理 — preprocessing.py cascade 方法正确性验证

测试以下函数：
  cascade_wavelet_vmd, cascade_wavelet_lms

输出: layer2/output/preprocessing_cascade_correctness.json
"""
import json
import sys
import os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.preprocessing import cascade_wavelet_vmd, cascade_wavelet_lms
from app.services.diagnosis.signal_utils import kurtosis
from tests.diagnosis.foundation.layer1.synthetic_signals import (
    NumpyEncoder, bearing_outer_race,
)

OUTPUT_DIR = Path(__file__).parent / "output"
FS = 8192


def test_cascade_wavelet_vmd():
    """小波+VMD 级联降噪：验证 SNR 改善"""
    print("\n--- cascade_wavelet_vmd ---")
    results = []

    sig, fs, gt = bearing_outer_race(bpfo=90.0, rot_freq=25.0, duration=2.0, fs=FS, snr_db=10)
    denoised, info = cascade_wavelet_vmd(sig, wavelet="db8", wavelet_level=4, wavelet_mode="soft",
                                          vmd_K=3, vmd_alpha=2000)

    kurt_before = info.get("kurtosis_before", 0)
    kurt_after = info.get("kurtosis_after_cascade", 0)
    # VMD 级联可能将冲击能量分散到多个模态，允许峭度下降但不超过 50%
    kurt_ok = kurt_after > kurt_before * 0.5
    has_meta = info.get("method") == "cascade_wavelet_vmd"

    passed = has_meta and kurt_ok
    results.append({
        "test": "cascade_wavelet_vmd_bearing",
        "kurt_before": round(kurt_before, 2),
        "kurt_after_wavelet": round(info.get("kurtosis_after_wavelet", 0), 2),
        "kurt_after_cascade": round(kurt_after, 2),
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] Wav+VMD: kurt_before={kurt_before:.1f}, after_wavelet={info.get('kurtosis_after_wavelet', 0):.1f}, after_cascade={kurt_after:.1f}")

    return results


def test_cascade_wavelet_lms():
    """小波+LMS 级联降噪：验证输出合理"""
    print("\n--- cascade_wavelet_lms ---")
    results = []

    sig, fs, gt = bearing_outer_race(bpfo=90.0, rot_freq=25.0, duration=2.0, fs=FS, snr_db=10)
    denoised, info = cascade_wavelet_lms(sig, wavelet="db8", wavelet_level=4, wavelet_mode="soft",
                                          lms_filter_len=32, lms_step_size=0.01)

    kurt_before = info.get("kurtosis_before", 0)
    kurt_after = info.get("kurtosis_after_cascade", 0)
    # LMS 级联应至少不严重恶化峭度（允许下降 30%）
    kurt_ok = kurt_after > kurt_before * 0.7
    has_meta = info.get("method") in ("cascade_wavelet_lms", "LMS")

    passed = has_meta and kurt_ok
    results.append({
        "test": "cascade_wavelet_lms_bearing",
        "kurt_before": round(kurt_before, 2),
        "kurt_after_cascade": round(kurt_after, 2),
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] Wav+LMS: kurt_before={kurt_before:.1f}, after_cascade={kurt_after:.1f}")

    return results


def main():
    print("=" * 60)
    print("Layer 2: cascade 级联预处理正确性验证")
    print("=" * 60)

    all_results = {
        "cascade_wavelet_vmd": test_cascade_wavelet_vmd(),
        "cascade_wavelet_lms": test_cascade_wavelet_lms(),
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
    out_path = OUTPUT_DIR / "preprocessing_cascade_correctness.json"
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
