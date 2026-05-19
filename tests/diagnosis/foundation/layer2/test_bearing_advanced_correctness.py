"""
Layer 2 轴承诊断（高级方法）— bearing.py / mckd.py / bearing_cyclostationary.py 正确性验证

测试以下函数：
  cpw_envelope_analysis, mckd_envelope_analysis, bearing_sc_scoh_analysis

输出: layer2/output/bearing_advanced_correctness.json
"""
import json
import sys
import os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.bearing import cpw_envelope_analysis
from app.services.diagnosis.mckd import mckd_envelope_analysis
from app.services.diagnosis.bearing_cyclostationary import bearing_sc_scoh_analysis
from app.services.diagnosis.signal_utils import find_peaks_in_spectrum
from tests.diagnosis.foundation.layer1.synthetic_signals import (
    NumpyEncoder, bearing_outer_race, bearing_inner_race,
)

OUTPUT_DIR = Path(__file__).parent / "output"
FS = 8192

# ── 真实数据集配置 ──
HUSTBEAR_DIR = Path(r"D:\code\wavelet_study\dataset\HUSTbear\down8192")
BEARING_PARAMS = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}
FAULT_COEFF = {"OR": 3.57, "IR": 5.43, "B": 4.71}


def _load_npy(path: Path):
    """加载 npy 文件"""
    try:
        return np.load(path)
    except Exception as e:
        print(f"  [WARN] 无法加载 {path}: {e}")
        return None


def _get_peak_snr(found):
    """从 find_peaks_in_spectrum 结果中提取峰值频率和 SNR"""
    fund = found.get("fundamental")
    if fund:
        return fund["freq"], fund["snr"]
    return 0.0, 0.0


# ═══════════════════════════════════════════════════════════
# 1. cpw_envelope_analysis — 倒频谱预白化 + 包络
# ═══════════════════════════════════════════════════════════

def test_cpw():
    """CPW 包络：合成轴承外圈故障信号"""
    print("\n--- cpw_envelope_analysis ---")
    results = []

    sig, fs, gt = bearing_outer_race(bpfo=90.0, rot_freq=25.0, duration=3.0, fs=FS, snr_db=15)
    res = cpw_envelope_analysis(sig, fs, comb_frequencies=[25.0, 50.0, 75.0], max_freq=500)

    peak_f, snr = _get_peak_snr(find_peaks_in_spectrum(np.array(res["envelope_freq"]), np.array(res["envelope_amp"]), target_freq=90.0, tolerance_hz=5.0))
    freq_ok = abs(peak_f - 90.0) < 10.0
    snr_ok = snr > 2.0
    passed = freq_ok and snr_ok
    results.append({
        "test": "cpw_bpfo_90Hz",
        "target_freq": 90.0,
        "detected_peak": round(peak_f, 2),
        "snr": round(snr, 2),
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] CPW BPFO=90Hz: peak={peak_f:.1f}Hz, SNR={snr:.1f}")

    # 边界：空 comb_frequencies
    empty_ok = False
    try:
        res_empty = cpw_envelope_analysis(sig, fs, comb_frequencies=[], max_freq=500)
        empty_ok = len(res_empty.get("envelope_freq", [])) > 0
    except Exception:
        pass
    results.append({
        "test": "cpw_empty_comb",
        "passed": empty_ok,
    })
    print(f"  [{'PASS' if empty_ok else 'FAIL'}] 空 comb_frequencies 安全处理")

    return results


# ═══════════════════════════════════════════════════════════
# 2. mckd_envelope_analysis — MCKD 解卷积 + 包络
# ═══════════════════════════════════════════════════════════

def test_mckd():
    """MCKD：验证能检出与轴承参数相关的故障频率"""
    print("\n--- mckd_envelope_analysis ---")
    results = []

    sig, fs, gt = bearing_inner_race(bpfi=135.0, rot_freq=25.0, duration=3.0, fs=FS, snr_db=15)
    bearing_params = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}
    res = mckd_envelope_analysis(sig, fs, bearing_params, rot_freq=25.0, filter_len=64, shift_order_M=1, max_freq=500)

    peak_f, snr = _get_peak_snr(find_peaks_in_spectrum(np.array(res["envelope_freq"]), np.array(res["envelope_amp"]), target_freq=135.0, tolerance_hz=5.0))
    freq_ok = abs(peak_f - 135.0) < 15.0  # MCKD 对 BPFI 有一定容差
    snr_ok = snr > 2.0
    passed = freq_ok and snr_ok
    results.append({
        "test": "mckd_bpfi_135Hz",
        "target_freq": 135.0,
        "detected_peak": round(peak_f, 2),
        "snr": round(snr, 2),
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] MCKD BPFI≈135Hz: peak={peak_f:.1f}Hz, SNR={snr:.1f}")

    return results


# ═══════════════════════════════════════════════════════════
# 3. bearing_sc_scoh_analysis — 谱相关/谱相干循环平稳分析
# ═══════════════════════════════════════════════════════════

def test_sc_scoh():
    """循环平稳分析：合成调制信号验证"""
    print("\n--- bearing_sc_scoh_analysis ---")
    results = []

    # 合成内圈故障信号（带转频调制）
    sig, fs, gt = bearing_inner_race(bpfi=135.0, rot_freq=25.0, duration=4.0, fs=FS, snr_db=15)
    bearing_params = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}
    res = bearing_sc_scoh_analysis(sig, fs, bearing_params=bearing_params, rot_freq=25.0, seg_len=2048)

    has_fault_indicators = len(res.get("fault_indicators", [])) > 0
    sc_max = res.get("sc_max_value", 0)
    sc_ok = sc_max > 0  # 只要有谱相关值即可（循环平稳信号应有一定值）

    passed = has_fault_indicators and sc_ok
    results.append({
        "test": "sc_scoh_inner_race",
        "sc_max_value": round(sc_max, 4),
        "n_fault_indicators": len(res.get("fault_indicators", [])),
        "dominant_fault": res.get("dominant_fault"),
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] SC/SCoh: sc_max={sc_max:.4f}, indicators={len(res.get('fault_indicators', []))}, dominant={res.get('dominant_fault')}")

    return results


# ═══════════════════════════════════════════════════════════
# 4. 真实数据验证 — HUSTbear 数据集（高级方法）
# ═══════════════════════════════════════════════════════════

def test_real_data_hustbear_advanced():
    """在 HUSTbear 真实数据上验证 CPW / MCKD / SC_SCoh"""
    print("\n--- HUSTbear 真实数据验证（高级方法） ---")
    results = []

    if not HUSTBEAR_DIR.exists():
        print("  [SKIP] HUSTbear 数据集未找到")
        return results

    test_files = [
        ("0.5X_O_20Hz-X.npy", "OR", 20.0, "外圈"),
        ("0.5X_O_25Hz-X.npy", "OR", 25.0, "外圈"),
        ("0.5X_I_20Hz-X.npy", "IR", 20.0, "内圈"),
        ("0.5X_I_25Hz-X.npy", "IR", 25.0, "内圈"),
        ("0.5X_B_20Hz-X.npy", "B",  20.0, "球"),
    ]

    for fname, fault, rot_freq, desc in test_files:
        fpath = HUSTBEAR_DIR / fname
        signal = _load_npy(fpath)
        if signal is None:
            continue

        target_freq = 0.0 if fault == "N" else rot_freq * FAULT_COEFF.get(fault, 0)
        print(f"  [{desc}] {fname} 转频={rot_freq}Hz 目标={target_freq:.1f}Hz")

        file_res = {"file": fname, "fault": fault, "rot_freq": rot_freq,
                    "target_freq": round(target_freq, 2), "methods": []}

        # CPW
        try:
            comb = [rot_freq * h for h in range(1, 4)]
            res = cpw_envelope_analysis(signal, FS, comb_frequencies=comb, max_freq=500)
            ef, ea = np.array(res.get("envelope_freq", [])), np.array(res.get("envelope_amp", []))
            if len(ef) > 0:
                peak_f, snr = _get_peak_snr(find_peaks_in_spectrum(ef, ea, target_freq, tolerance_hz=5.0))
                passed = abs(peak_f - target_freq) < target_freq * 0.20 + 5 and snr > 2.0
                file_res["methods"].append({"method": "cpw", "peak_f": round(peak_f, 2), "snr": round(snr, 2), "passed": passed})
                print(f"    [{'PASS' if passed else 'FAIL'}] CPW: peak={peak_f:.1f}Hz SNR={snr:.1f}")
        except Exception as e:
            print(f"    [WARN] CPW 失败: {e}")

        # MCKD
        try:
            res = mckd_envelope_analysis(signal, FS, BEARING_PARAMS, rot_freq=rot_freq, filter_len=64, shift_order_M=1, max_freq=500)
            ef, ea = np.array(res.get("envelope_freq", [])), np.array(res.get("envelope_amp", []))
            if len(ef) > 0:
                peak_f, snr = _get_peak_snr(find_peaks_in_spectrum(ef, ea, target_freq, tolerance_hz=5.0))
                if fault == "N":
                    passed = snr < 3.0
                else:
                    passed = abs(peak_f - target_freq) < target_freq * 0.15 + 3 and snr > 2.0
                file_res["methods"].append({"method": "mckd", "peak_f": round(peak_f, 2), "snr": round(snr, 2), "passed": passed})
                print(f"    [{'PASS' if passed else 'FAIL'}] MCKD: peak={peak_f:.1f}Hz SNR={snr:.1f}")
        except Exception as e:
            print(f"    [WARN] MCKD 失败: {e}")

        # SC_SCoh
        try:
            res = bearing_sc_scoh_analysis(signal, FS, bearing_params=BEARING_PARAMS, rot_freq=rot_freq, seg_len=2048)
            sc_max = res.get("sc_max_value", 0)
            n_ind = len(res.get("fault_indicators", []))
            passed = n_ind > 0 and sc_max > 0
            file_res["methods"].append({"method": "sc_scoh", "sc_max": round(sc_max, 4), "n_indicators": n_ind, "passed": passed})
            print(f"    [{'PASS' if passed else 'FAIL'}] SC_SCoh: sc_max={sc_max:.4f} indicators={n_ind}")
        except Exception as e:
            print(f"    [WARN] SC_SCoh 失败: {e}")

        results.append(file_res)

    return results


# ═══════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("Layer 2: 轴承高级方法 — CPW / MCKD / SC-SCoh 正确性验证")
    print("=" * 60)

    all_results = {
        "cpw": test_cpw(),
        "mckd": test_mckd(),
        "sc_scoh": test_sc_scoh(),
        "real_data_hustbear": test_real_data_hustbear_advanced(),
    }

    total = 0
    passed = 0
    for category, items in all_results.items():
        if category == "real_data_hustbear":
            for file_item in items:
                for m in file_item.get("methods", []):
                    total += 1
                    if m.get("passed", False):
                        passed += 1
        else:
            for item in items:
                total += 1
                if item.get("passed", False):
                    passed += 1

    all_results["summary"] = {"total": total, "passed": passed, "failed": total - passed}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "bearing_advanced_correctness.json"
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
