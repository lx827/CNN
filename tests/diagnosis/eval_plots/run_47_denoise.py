"""
4.7 去噪效果评估 — 独立可并行
输出: 47_denoise.json
"""
import sys, time
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _eval_utils import *
from app.services.diagnosis.preprocessing import wavelet_denoise, cascade_wavelet_vmd
from app.services.diagnosis.vmd_denoise import vmd_denoise
from app.services.diagnosis.savgol_denoise import sg_denoise

def snr_db(sig_clean, sig_processed):
    """计算处理后信号相对纯净信号的 SNR"""
    noise = sig_processed - sig_clean
    s_pow = np.mean(sig_clean ** 2)
    n_pow = np.mean(noise ** 2) + 1e-12
    return 10 * np.log10(s_pow / n_pow)

def run():
    print(f"\n{'='*60}\n4.7 去噪效果\n{'='*60}")
    or_files = sorted(f for f in HUST_DIR.glob("*-X.npy") if fault_hust(f.name) == "O")
    h_files = sorted(f for f in HUST_DIR.glob("*-X.npy") if fault_hust(f.name) == "H")
    if not or_files or not h_files:
        print("  ⚠️ 样本不足")
        return

    results = {"methods": {}}
    for label, fp in [("外圈故障", or_files[0]), ("健康", h_files[0])]:
        sig_clean = load_sig(fp)
        noise = np.random.randn(len(sig_clean)) * np.std(sig_clean)
        sig_noisy = sig_clean + noise  # 0dB
        baseline_snr = snr_db(sig_clean, sig_noisy)

        row = {"baseline": round(baseline_snr, 2)}
        # 小波
        w = wavelet_denoise(sig_noisy, FS)
        row["小波"] = round(snr_db(sig_clean, w) - baseline_snr, 2)
        # VMD
        v = vmd_denoise(sig_noisy, FS)
        row["VMD"] = round(snr_db(sig_clean, v) - baseline_snr, 2)
        # SG
        s = sg_denoise(sig_noisy)
        row["SG"] = round(snr_db(sig_clean, s) - baseline_snr, 2)
        # 级联
        c = cascade_wavelet_vmd(sig_noisy, FS)
        row["级联"] = round(snr_db(sig_clean, c) - baseline_snr, 2)

        results["methods"][label] = row
        print(f"  {label}: baseline={baseline_snr:.1f}dB, VMD={row['VMD']:+.2f}, 级联={row['级联']:+.2f}")

    save_json(results, "47_denoise.json")
    return results

if __name__ == "__main__":
    run()
