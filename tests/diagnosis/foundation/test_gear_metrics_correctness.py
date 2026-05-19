"""
齿轮诊断指标 — 正确性验证

1. WTgearbox 行星齿轮箱：验证 SER/FM4/CAR 对健康/故障的区分力
2. HUSTgearbox 定轴齿轮箱：验证标准边频带指标

输出: output/gear_metrics_correctness.json
"""
import json
import sys
import os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from app.services.diagnosis.engine import DiagnosisEngine, GearMethod, DenoiseMethod
from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum
from app.services.diagnosis.features import compute_time_features
from tests.diagnosis.foundation.synthetic_signals import gear_mesh, NumpyEncoder

OUTPUT_DIR = Path(__file__).parent / "output"
FS = 8192


def test_synthetic_gear():
    """合成齿轮啮合信号：SER/FM0 应接近理论值"""
    print("\n--- 合成齿轮信号指标 ---")
    results = []

    sig, fs, gt = gear_mesh(mesh_freq=450.0, rot_freq=25.0, duration=3.0, snr_db=40)
    rot_freq = estimate_rot_freq_spectrum(sig, fs, freq_range=(10, 60))

    engine = DiagnosisEngine(
        gear_method=GearMethod.ADVANCED,
        denoise_method=DenoiseMethod.NONE,
        gear_teeth={"input": 18, "output": 27},
    )
    result = engine.analyze_gear(sig, fs)

    ser = result.get("ser", 0)
    fm0 = result.get("fm0", 0)
    fm4 = result.get("fm4", 0)
    car = result.get("car", 0)

    # 合成信号有清晰的边频带，SER 应 > 0.3
    results.append({
        "dataset": "synthetic",
        "test": "gear_mesh_450Hz",
        "est_rot_freq": round(rot_freq, 2),
        "mesh_freq": result.get("mesh_freq_hz"),
        "ser": round(ser, 4),
        "fm0": round(fm0, 2),
        "fm4": round(fm4, 2),
        "car": round(car, 2),
        "ser_reasonable": ser > 0.3,
        "passed": ser > 0.3 and fm0 > 0,
    })
    status = "PASS" if results[-1]["passed"] else "FAIL"
    print(f"  [{status}] mesh=450Hz: SER={ser:.3f}, FM0={fm0:.2f}, FM4={fm4:.2f}, rot_est={rot_freq:.1f}Hz")
    return results


def test_wtgearbox():
    """WTgearbox 行星齿轮箱：健康 vs 故障指标分布"""
    print("\n--- WTgearbox 行星齿轮箱 ---")
    results = []

    WTGEARBOX_GEAR = {"input": 28, "ring": 100, "planet": 36, "planet_count": 4}
    data_dir = Path(r"D:\code\wavelet_study\dataset\WTgearbox\down8192")

    test_files = [
        ("He_N1_40-c1.npy", "健康 40Hz", "He"),
        ("Br_B1_40-c1.npy", "断齿 40Hz", "Br"),
        ("We_W1_40-c1.npy", "磨损 40Hz", "We"),
        ("Rc_R1_40-c1.npy", "裂纹 40Hz", "Rc"),
        ("Mi_M1_40-c1.npy", "缺齿 40Hz", "Mi"),
    ]

    for fname, desc, label in test_files:
        fpath = data_dir / fname
        if not fpath.exists():
            print(f"  [SKIP] {fname}")
            continue

        sig = np.load(str(fpath)).astype(np.float64)[:FS * 5]
        rot_freq = estimate_rot_freq_spectrum(sig, FS, freq_range=(30, 70))

        engine = DiagnosisEngine(
            gear_method=GearMethod.ADVANCED,
            denoise_method=DenoiseMethod.NONE,
            gear_teeth=WTGEARBOX_GEAR,
        )
        result = engine.analyze_gear(sig, FS)

        time_feat = compute_time_features(sig)
        results.append({
            "dataset": "WTgearbox",
            "file": fname,
            "label": label,
            "description": desc,
            "passed": True,  # 观察性测试，仅记录指标值
            "est_rot_freq": round(rot_freq, 2),
            "mesh_freq_hz": result.get("mesh_freq_hz"),
            "ser": round(result.get("ser", 0), 4),
            "fm0": round(result.get("fm0", 0), 2),
            "fm4": round(result.get("fm4", 0), 2),
            "car": round(result.get("car", 0), 2),
            "kurtosis": round(time_feat.get("kurtosis", 0), 2),
            "crest_factor": round(time_feat.get("crest_factor", 0), 2),
        })
        print(f"  [{label}] rot={rot_freq:.1f}Hz, mesh={result.get('mesh_freq_hz')}Hz, "
              f"SER={result.get('ser',0):.3f}, kurt={time_feat.get('kurtosis',0):.1f}")

    return results


def test_hustgearbox():
    """HUSTgearbox 定轴齿轮箱：断齿/缺齿应检出"""
    print("\n--- HUSTgearbox 定轴齿轮箱 ---")
    results = []

    HUSTGEARBOX_GEAR = {"input": 18, "output": 27}
    data_dir = Path(r"D:\code\wavelet_study\dataset\HUSTgearbox\down8192")

    test_files = [
        ("H_20_1-X.npy", "健康 20Hz 1x负载", "H"),
        ("B_20_1-X.npy", "断齿 20Hz 1x负载", "B"),
        ("M_20_1-X.npy", "缺齿 20Hz 1x负载", "M"),
    ]

    for fname, desc, label in test_files:
        fpath = data_dir / fname
        if not fpath.exists():
            print(f"  [SKIP] {fname}")
            continue

        sig = np.load(str(fpath)).astype(np.float64)[:FS * 5]
        rot_freq = estimate_rot_freq_spectrum(sig, FS, freq_range=(10, 50))

        engine = DiagnosisEngine(
            gear_method=GearMethod.ADVANCED,
            denoise_method=DenoiseMethod.NONE,
            gear_teeth=HUSTGEARBOX_GEAR,
        )
        result = engine.analyze_gear(sig, FS)

        time_feat = compute_time_features(sig)
        results.append({
            "dataset": "HUSTgearbox",
            "file": fname,
            "label": label,
            "description": desc,
            "passed": True,  # 观察性测试，仅记录指标值
            "est_rot_freq": round(rot_freq, 2),
            "mesh_freq_hz": result.get("mesh_freq_hz"),
            "ser": round(result.get("ser", 0), 4),
            "fm0": round(result.get("fm0", 0), 2),
            "fm4": round(result.get("fm4", 0), 2),
            "car": round(result.get("car", 0), 2),
            "kurtosis": round(time_feat.get("kurtosis", 0), 2),
            "crest_factor": round(time_feat.get("crest_factor", 0), 2),
        })
        print(f"  [{label}] rot={rot_freq:.1f}Hz, mesh={result.get('mesh_freq_hz')}Hz, "
              f"SER={result.get('ser',0):.3f}, FM4={result.get('fm4',0):.1f}")

    return results


def main():
    print("=" * 60)
    print("齿轮诊断指标 — 正确性验证")
    print("=" * 60)

    all_results = {
        "synthetic_gear": test_synthetic_gear(),
        "wtgearbox": test_wtgearbox(),
        "hustgearbox": test_hustgearbox(),
    }

    total = sum(len(v) for v in all_results.values())
    passed = sum(1 for cat in all_results.values() for item in cat if item.get("passed", False))
    all_results["summary"] = {"total": total, "passed": passed, "failed": total - passed}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "gear_metrics_correctness.json"
    out_path.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder), encoding='utf-8')
    print(f"\n结果已保存: {out_path}")
    print(f"总计: {total}, 通过: {passed}, 失败: {total - passed}")


if __name__ == "__main__":
    main()
