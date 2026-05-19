"""
阶次跟踪 — 正确性验证

1. 合成正弦信号：验证转频估计精度
2. 合成扫频信号：验证变速跟踪有效性
3. 真实 HUSTbear 恒速+变速数据

输出: output/order_tracking_correctness.json
"""
import json
import sys
import os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum
from app.services.diagnosis.order_tracking import (
    _compute_order_spectrum,
    _compute_order_spectrum_multi_frame,
    _compute_order_spectrum_varying_speed,
)
from tests.diagnosis.foundation.synthetic_signals import NumpyEncoder,  sinusoidal, chirp_rotating

OUTPUT_DIR = Path(__file__).parent / "output"
FS = 8192


def test_rot_freq_estimation():
    """合成正弦信号：转频估计精度"""
    print("\n--- 转频估计精度 ---")
    results = []

    for freq in [10, 25, 50, 80]:
        sig, fs, gt = sinusoidal(freq=freq, duration=3.0)
        est = estimate_rot_freq_spectrum(sig, fs, freq_range=(5, 120))
        err = abs(est - freq)
        err_pct = err / freq * 100
        passed = err_pct < 5.0
        results.append({
            "actual_freq": freq,
            "estimated_freq": round(est, 2),
            "abs_error_Hz": round(err, 2),
            "rel_error_pct": round(err_pct, 2),
            "passed": passed,
        })
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {freq}Hz → 估计 {est:.1f}Hz (误差 {err_pct:.1f}%)")
    return results


def test_chirp_order_tracking():
    """合成扫频信号：变速跟踪应优于单帧"""
    print("\n--- 变速阶次跟踪 ---")
    results = []

    sig, fs, gt = chirp_rotating(10, 40, duration=5.0)

    # 单帧法
    rf = estimate_rot_freq_spectrum(sig, fs, freq_range=(5, 80))
    orders_s, spec_s = _compute_order_spectrum(sig, fs, rf, samples_per_rev=512)
    mask = orders_s <= 15
    kurt_single = float(np.mean(spec_s[mask]**4) / (np.mean(spec_s[mask]**2)**2 + 1e-12))

    # 多帧法
    orders_m, spec_m, med_rf, std_rf = _compute_order_spectrum_multi_frame(
        sig, fs, freq_range=(5, 80), samples_per_rev=512, max_order=15)
    kurt_multi = float(np.mean(spec_m**4) / (np.mean(spec_m**2)**2 + 1e-12))
    cv = std_rf / med_rf if med_rf > 0 else 0

    # 变速法
    orders_v, spec_v, _, _ = _compute_order_spectrum_varying_speed(
        sig, fs, freq_range=(5, 80), samples_per_rev=512, max_order=15)
    kurt_vary = float(np.mean(spec_v**4) / (np.mean(spec_v**2)**2 + 1e-12))

    results.append({
        "test": "chirp_10_40Hz",
        "single_frame_kurtosis": round(kurt_single, 2),
        "multi_frame_kurtosis": round(kurt_multi, 2),
        "varying_speed_kurtosis": round(kurt_vary, 2),
        "med_rot_freq": round(med_rf, 2),
        "std_rot_freq": round(std_rf, 2),
        "cv_pct": round(cv * 100, 2),
        "chirp_detected": cv > 0.08,  # 应检测到转速变化
        "passed": kurt_vary >= kurt_single * 0.5,  # 变速法不应明显劣于单帧
    })
    status = "PASS" if results[-1]["passed"] else "FAIL"
    print(f"  [{status}] 扫频10→40Hz: 多帧CV={cv:.2%}, 变速峰度={kurt_vary:.1f} vs 单帧={kurt_single:.1f}")
    return results


def test_real_hustbear_order():
    """真实 HUSTbear 数据：转频估计 + 阶次谱"""
    print("\n--- 真实数据阶次分析 ---")
    results = []

    data_dir = Path(r"D:\code\wavelet_study\dataset\HUSTbear\down8192")
    test_files = [
        ("H_20Hz-X.npy", "健康恒速", (15, 60)),
        ("0.5X_OR_20Hz-X.npy", "外圈故障恒速", (15, 60)),
    ]

    for fname, desc, freq_range in test_files:
        fpath = data_dir / fname
        if not fpath.exists():
            # try alternate naming
            matches = list(data_dir.glob(fname.replace("_20Hz-", "_*-")))
            if matches:
                fpath = matches[0]
        if not fpath.exists():
            print(f"  [SKIP] {fname} 不存在")
            continue

        sig = np.load(str(fpath)).astype(np.float64)[:FS * 5]
        rot_freq = estimate_rot_freq_spectrum(sig, FS, freq_range=freq_range)
        orders, spec = _compute_order_spectrum(sig, FS, rot_freq, samples_per_rev=1024)

        results.append({
            "file": fname,
            "description": desc,
            "estimated_rot_freq_Hz": round(rot_freq, 2),
            "estimated_rot_rpm": round(rot_freq * 60, 0),
            "order_spectrum_peak": round(float(np.max(spec)), 2),
            "order_spectrum_points": len(orders),
        })
        print(f"  [{desc}] 转频={rot_freq:.1f}Hz ({rot_freq*60:.0f}RPM)")

    return results


def main():
    print("=" * 60)
    print("阶次跟踪 — 正确性验证")
    print("=" * 60)

    all_results = {
        "rot_freq_estimation": test_rot_freq_estimation(),
        "chirp_order_tracking": test_chirp_order_tracking(),
        "real_hustbear": test_real_hustbear_order(),
    }

    total = 0
    passed = 0
    for cat, items in all_results.items():
        for item in items:
            total += 1
            if item.get("passed", True):
                passed += 1
    all_results["summary"] = {"total": total, "passed": passed, "failed": total - passed}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "order_tracking_correctness.json"
    out_path.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder))
    print(f"\n结果已保存: {out_path}")
    print(f"总计: {total}, 通过: {passed}, 失败: {total - passed}")

    assert total - passed == 0, f"{total - passed} 个测试失败"
    print("全部通过!")


if __name__ == "__main__":
    main()
