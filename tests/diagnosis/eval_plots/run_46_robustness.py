"""
4.6 鲁棒性评估 (噪声环境) — 独立可并行
输出: 46_robustness.json
"""
import sys, time
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _eval_utils import *

def run():
    print(f"\n{'='*60}\n4.6 鲁棒性评估（强噪声）\n{'='*60}")
    # 找外圈故障样本
    or_files = sorted(f for f in HUST_DIR.glob("*-X.npy") if fault_hust(f.name) == "O")
    if not or_files:
        print("  ⚠️ 未找到外圈故障样本")
        return
    fp = or_files[0]
    sig_clean = load_sig(fp)
    print(f"  样本: {fp.name}, RMS={np.std(sig_clean):.4f}")

    snr_levels = [20, 10, 5, 0, -5]
    methods = [
        ("包络", BearingMethod.ENVELOPE), ("Kurtogram", BearingMethod.KURTOGRAM),
        ("MED", BearingMethod.MED), ("MCKD", BearingMethod.MCKD),
    ]
    results = {"sample": fp.name, "snr_levels": snr_levels, "methods": {}}

    for name_cn, method_val in methods:
        curve = {}
        for s_db in snr_levels:
            noise = np.random.randn(len(sig_clean)) * np.std(sig_clean) / (10 ** (s_db / 20))
            sig_noisy = sig_clean + noise
            try:
                engine = DiagnosisEngine(bearing_method=method_val, bearing_params=BP, denoise_method=DenoiseMethod.NONE)
                res = engine.analyze_bearing(sig_noisy, FS)
                det = bearing_detect(res, False)  # 外圈故障，期望检出
            except Exception:
                det = False
            curve[str(s_db)] = det
            print(f"    {name_cn} SNR={s_db}dB: {'✓' if det else '✗'}")
        results["methods"][name_cn] = curve

    # Ensemble
    curve_e = {}
    for s_db in snr_levels:
        noise = np.random.randn(len(sig_clean)) * np.std(sig_clean) / (10 ** (s_db / 20))
        sig_noisy = sig_clean + noise
        try:
            res = run_research_ensemble(sig_noisy, FS, bearing_params=BP, max_seconds=MAX_S)
            det = ensemble_detect(res, False)
        except Exception:
            det = False
        curve_e[str(s_db)] = det
        print(f"    Ensemble SNR={s_db}dB: {'✓' if det else '✗'}")
    results["methods"]["Ensemble"] = curve_e

    save_json(results, "46_robustness.json")
    return results

if __name__ == "__main__":
    run()
