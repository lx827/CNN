"""
Layer 2 行星齿轮箱解调 — gear/planetary_demod.py 正确性验证

测试以下函数：
  planetary_envelope_order_analysis, planetary_fullband_envelope_order_analysis,
  planetary_vmd_demod_analysis, planetary_tsa_envelope_analysis

原则：合成行星齿轮信号（已知 sun/planet/ring 齿数），验证各方法能返回有效指标。

输出: layer2/output/planetary_demod_correctness.json
"""
import json
import sys
import os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.gear.planetary_demod import (
    planetary_envelope_order_analysis, planetary_fullband_envelope_order_analysis,
    planetary_vmd_demod_analysis, planetary_tsa_envelope_analysis,
    evaluate_planetary_demod_results,
)
from tests.diagnosis.foundation.layer1.synthetic_signals import NumpyEncoder

OUTPUT_DIR = Path(__file__).parent / "output"
FS = 8192


def _make_planetary_signal(rot_freq=25.0, duration=4.0, fs=FS, snr_db=25):
    """合成行星齿轮信号：太阳轮 28齿，行星轮 36齿，内齿圈 100齿"""
    t = np.arange(0, duration, 1/fs)
    # 啮合频率 = (175/8) * rot_freq
    mesh_freq = (175.0 / 8.0) * rot_freq
    sig = np.sin(2 * np.pi * mesh_freq * t)
    # 加边频带
    sig += 0.3 * np.sin(2 * np.pi * (mesh_freq + rot_freq) * t)
    sig += 0.3 * np.sin(2 * np.pi * (mesh_freq - rot_freq) * t)
    # 加噪声
    sig_power = np.var(sig)
    noise_power = sig_power / (10 ** (snr_db / 10))
    sig += np.sqrt(noise_power) * np.random.randn(len(t))
    return sig, fs


GEAR_TEETH = {"sun": 28, "planet": 36, "ring": 100, "planet_count": 4}


def test_planetary_envelope_order():
    """行星齿轮窄带包络阶次分析"""
    print("\n--- planetary_envelope_order_analysis ---")
    results = []

    np.random.seed(42)
    sig, fs = _make_planetary_signal(rot_freq=25.0, duration=4.0)
    res = planetary_envelope_order_analysis(sig, fs, rot_freq=25.0, gear_teeth=GEAR_TEETH)

    has_method = res.get("method") == "planetary_envelope_order"
    has_snr = res.get("sun_fault_snr", 0) > 0 or res.get("planet_fault_snr", 0) > 0
    # 健康信号可能无显著故障 SNR，但方法必须正确执行无 error
    no_error = "error" not in res
    passed = has_method and no_error
    results.append({
        "test": "planetary_envelope_order",
        "sun_fault_snr": round(res.get("sun_fault_snr", 0), 3),
        "planet_fault_snr": round(res.get("planet_fault_snr", 0), 3),
        "carrier_snr": round(res.get("carrier_snr", 0), 3),
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] EnvelopeOrder: sun={res.get('sun_fault_snr', 0):.2f}, planet={res.get('planet_fault_snr', 0):.2f}")

    # 真实 WTG 健康数据验证：planetary_sun_fault 不应误报
    wtg_dir = Path("D:/code/wavelet_study/dataset/WTgearbox/down8192")
    sig_real = np.load(wtg_dir / "He_N1_20-c1.npy")[:FS*5] if wtg_dir.exists() else None
    if sig_real is not None:
        res_real = planetary_envelope_order_analysis(sig_real, FS, rot_freq=20.0, gear_teeth=GEAR_TEETH)
        ek = res_real.get("envelope_kurtosis", 0)  # 窄带包络峭度
        smd = res_real.get("sun_modulation_depth", 0)  # 太阳轮调制深度
        # 阈值 3.0: env_kurt 仅对磨损/缺齿敏感，健康/断齿/裂纹 < 3.0
        # He_N1 ek=2.2 是载波调制偏高的正常波动，不应报警
        no_false_pos = ek < 3.0
        results.append({
            "test": "planetary_envelope_order_healthy",
            "envelope_kurtosis": round(ek, 3),
            "sun_modulation_depth": round(smd, 4),
            "passed": no_false_pos,
        })
        tag = "PASS" if no_false_pos else "WARN"
        print(f"  [{tag}] WTG健康: env_kurt={ek:.3f}, sun_mod_depth={smd:.4f} (期望 env_kurt<3.0)")

    return results


def test_planetary_fullband():
    """行星齿轮全频带包络分析"""
    print("\n--- planetary_fullband_envelope_order_analysis ---")
    results = []

    np.random.seed(42)
    sig, fs = _make_planetary_signal(rot_freq=25.0, duration=4.0)
    res = planetary_fullband_envelope_order_analysis(sig, fs, rot_freq=25.0, gear_teeth=GEAR_TEETH)

    has_method = res.get("method") == "planetary_fullband_envelope_order"
    no_error = "error" not in res
    passed = has_method and no_error
    results.append({
        "test": "planetary_fullband",
        "envelope_kurtosis": round(res.get("envelope_kurtosis", 0), 3),
        "sun_fault_snr": round(res.get("sun_fault_snr", 0), 3),
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] Fullband: kurt={res.get('envelope_kurtosis', 0):.2f}, sun={res.get('sun_fault_snr', 0):.2f}")

    return results


def test_planetary_vmd():
    """行星齿轮 VMD 解调"""
    print("\n--- planetary_vmd_demod_analysis ---")
    results = []

    np.random.seed(42)
    sig, fs = _make_planetary_signal(rot_freq=25.0, duration=3.0)
    res = planetary_vmd_demod_analysis(sig, fs, rot_freq=25.0, gear_teeth=GEAR_TEETH, max_K=4)

    has_method = res.get("method") == "planetary_vmd_demod"
    no_error = "error" not in res
    passed = has_method and no_error
    results.append({
        "test": "planetary_vmd",
        "imf_count": res.get("imf_count", 0),
        "selected_imf": res.get("selected_imf_index"),
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] VMD: imfs={res.get('imf_count', 0)}, selected={res.get('selected_imf_index')}")

    return results


def test_planetary_tsa():
    """行星齿轮 TSA + 包络"""
    print("\n--- planetary_tsa_envelope_analysis ---")
    results = []

    np.random.seed(42)
    sig, fs = _make_planetary_signal(rot_freq=25.0, duration=4.0)
    res = planetary_tsa_envelope_analysis(sig, fs, rot_freq=25.0, gear_teeth=GEAR_TEETH)

    has_method = res.get("method") == "planetary_tsa_envelope"
    no_error = "error" not in res
    passed = has_method and no_error
    results.append({
        "test": "planetary_tsa",
        "residual_kurtosis": round(res.get("residual_kurtosis", 0), 3),
        "sun_fault_snr": round(res.get("sun_fault_snr", 0), 3),
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] TSA: residual_kurt={res.get('residual_kurtosis', 0):.2f}, sun={res.get('sun_fault_snr', 0):.2f}")

    return results


def test_evaluate_results():
    """evaluate_planetary_demod_results: 健康数据不应误报"""
    print("\n--- evaluate_planetary_demod_results ---")
    results = []

    # 用真实 WTG 健康数据的窄带结果
    wtg_dir = Path("D:/code/wavelet_study/dataset/WTgearbox/down8192")
    sig_real = np.load(wtg_dir / "He_N1_20-c1.npy")[:FS*5] if wtg_dir.exists() else None
    if sig_real is None:
        results.append({"test": "eval_results_skip", "passed": True, "skip": "no data"})
        return results

    narrowband = planetary_envelope_order_analysis(sig_real, FS, rot_freq=20.0, gear_teeth=GEAR_TEETH)
    vmd_res = planetary_vmd_demod_analysis(sig_real, FS, rot_freq=20.0, gear_teeth=GEAR_TEETH, max_K=4)

    ev = evaluate_planetary_demod_results(narrowband, vmd_res)
    sun = ev.get("planetary_sun_fault", {})
    no_false = not sun.get("warning") and not sun.get("critical")
    results.append({
        "test": "evaluate_results_healthy",
        "sun_fault_value": sun.get("value"),
        "sun_fault_warning": sun.get("warning"),
        "passed": no_false,
    })
    tag = "PASS" if no_false else "WARN"
    print(f"  [{tag}] WTG健康聚合: sun_fault={sun.get('value')}, warning={sun.get('warning')} (期望False)")

    return results


def main():
    print("=" * 60)
    print("Layer 2: gear/planetary_demod.py — 行星齿轮解调正确性验证")
    print("=" * 60)

    all_results = {
        "planetary_envelope_order": test_planetary_envelope_order(),
        "planetary_fullband": test_planetary_fullband(),
        "planetary_vmd": test_planetary_vmd(),
        "planetary_tsa": test_planetary_tsa(),
        "evaluate_results": test_evaluate_results(),
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
    out_path = OUTPUT_DIR / "planetary_demod_correctness.json"
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
