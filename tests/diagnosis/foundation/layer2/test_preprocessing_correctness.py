"""
Layer 2 预处理 — preprocessing.py 正确性验证

测试 preprocessing.py 中依赖 Layer 1 的函数：
  wavelet_denoise, minimum_entropy_deconvolution, cepstrum_pre_whitening

原则：合成已知成分的信号，验证处理后的信号是否符合预期。

输出: layer2/output/preprocessing_correctness.json
"""
import json
import sys
import os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.preprocessing import (
    wavelet_denoise, minimum_entropy_deconvolution, cepstrum_pre_whitening,
)
from app.services.diagnosis.signal_utils import compute_fft_spectrum, rms, kurtosis
from tests.diagnosis.foundation.layer1.synthetic_signals import (
    NumpyEncoder, sinusoidal, bearing_outer_race,
)

OUTPUT_DIR = Path(__file__).parent / "output"
FS = 8192


# ═══════════════════════════════════════════════════════════
# 1. wavelet_denoise — 小波阈值去噪
# ═══════════════════════════════════════════════════════════

def test_wavelet_denoise():
    """小波去噪：加噪正弦的 SNR 改善与幅值保持"""
    print("\n--- wavelet_denoise ---")
    results = []

    duration = 2.0
    t = np.arange(0, duration, 1/FS)
    clean = np.sin(2 * np.pi * 50 * t) + 0.5 * np.sin(2 * np.pi * 120 * t)
    np.random.seed(42)
    noise = 0.8 * np.random.randn(len(t))
    noisy = clean + noise

    # 降噪前 SNR (dB)
    noise_power = np.var(noise)
    signal_power = np.var(clean)
    snr_before = 10 * np.log10(signal_power / (noise_power + 1e-12))

    denoised = wavelet_denoise(noisy, wavelet="db8", level=4, threshold_mode="soft", threshold_scale=1.0)

    # 降噪后：用 residual 功率估算
    residual = denoised[:len(clean)] - clean[:len(denoised)]
    residual_power = np.var(residual)
    snr_after = 10 * np.log10(signal_power / (residual_power + 1e-12))

    snr_improved = snr_after > snr_before  # 严格要求 SNR 提升
    # 幅值保持：主要频率分量幅值不应被过度衰减
    _, spec_before = compute_fft_spectrum(noisy, FS)
    _, spec_after = compute_fft_spectrum(denoised, FS)
    idx_50 = int(50 * len(spec_after) / (FS/2))
    amp_preserved = idx_50 < len(spec_after) and spec_after[idx_50] > spec_before[idx_50] * 0.5

    passed = snr_improved and amp_preserved
    results.append({
        "test": "wavelet_denoise_snr",
        "snr_before_db": round(snr_before, 2),
        "snr_after_db": round(snr_after, 2),
        "amp_preserved": amp_preserved,
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] 小波去噪: SNR {snr_before:.1f}dB → {snr_after:.1f}dB, amp_preserved={amp_preserved}")

    # 边界：极短信号
    short_ok = False
    try:
        _ = wavelet_denoise(np.array([1.0, -1.0, 0.5, -0.5]))
        short_ok = True
    except Exception:
        pass
    results.append({
        "test": "wavelet_denoise_short",
        "passed": short_ok,
    })
    print(f"  [{'PASS' if short_ok else 'FAIL'}] 极短信号不崩溃")

    return results


# ═══════════════════════════════════════════════════════════
# 2. minimum_entropy_deconvolution — MED 解卷积
# ═══════════════════════════════════════════════════════════

def test_med():
    """MED：合成卷积冲击信号验证解卷积恢复效果"""
    print("\n--- minimum_entropy_deconvolution ---")
    results = []

    # 合成冲击序列 + 低通滤波器(模拟传递函数) → 卷积后信号
    duration = 2.0
    t = np.arange(0, duration, 1/FS)
    impulse_freq = 100.0
    T = 1.0 / impulse_freq
    impulses = np.zeros_like(t)
    for i in range(int(duration / T)):
        idx = int(i * T * FS)
        if idx < len(t):
            impulses[idx] = 1.0

    # 模拟传递函数：低通 FIR
    h = np.array([0.2, 0.5, 0.3, 0.1, 0.05])
    convolved = np.convolve(impulses, h, mode='same')
    # 加少量噪声
    np.random.seed(42)
    noisy = convolved + 0.1 * np.random.randn(len(convolved))

    recovered, filt = minimum_entropy_deconvolution(noisy, filter_len=32, max_iter=50, tol=1e-6)

    # 验证：恢复后信号峭度应高于加噪输入（冲击性增强）
    kurt_before = kurtosis(noisy, fisher=False)
    kurt_after = kurtosis(recovered, fisher=False)
    kurt_improved = kurt_after > kurt_before * 1.1

    # 验证：恢复后信号应有更尖锐的峰值
    peak_before = np.max(np.abs(convolved))
    peak_after = np.max(np.abs(recovered))
    peak_improved = peak_after > peak_before * 0.8  # 至少不严重衰减

    passed = kurt_improved and peak_improved
    results.append({
        "test": "med_impulse_recovery",
        "kurt_before": round(kurt_before, 2),
        "kurt_after": round(kurt_after, 2),
        "peak_before": round(peak_before, 3),
        "peak_after": round(peak_after, 3),
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] MED: kurt {kurt_before:.1f}→{kurt_after:.1f}, peak {peak_before:.3f}→{peak_after:.3f}")

    return results


# ═══════════════════════════════════════════════════════════
# 3. cepstrum_pre_whitening — CPW 倒频谱预白化
# ═══════════════════════════════════════════════════════════

def test_cpw():
    """CPW：合成含确定性频率的信号，验证这些频率被抑制"""
    print("\n--- cepstrum_pre_whitening ---")
    results = []

    # 合成信号：50Hz + 120Hz 确定性频率 + 噪声
    duration = 2.0
    t = np.arange(0, duration, 1/FS)
    sig = np.sin(2*np.pi*50*t) + 0.7*np.sin(2*np.pi*120*t)
    np.random.seed(42)
    sig += 0.3 * np.random.randn(len(t))

    xf, yf = compute_fft_spectrum(sig, FS)
    # 50Hz 和 120Hz 的能量
    idx_50 = int(50 * len(yf) / (FS/2))
    idx_120 = int(120 * len(yf) / (FS/2))
    energy_before = yf[idx_50] + yf[idx_120]

    # CPW：消除 50Hz 和 120Hz 的谐波族
    cpw_sig = cepstrum_pre_whitening(sig, FS, comb_frequencies=[50.0, 120.0], notch_width_ratio=0.02)

    _, yf_cpw = compute_fft_spectrum(cpw_sig, FS)
    energy_after = yf_cpw[idx_50] + yf_cpw[idx_120]

    # 预白化后确定性频率应被抑制（能量降低）
    suppressed = energy_after < energy_before * 0.5

    passed = suppressed
    results.append({
        "test": "cpw_harmonic_suppression",
        "energy_before": round(float(energy_before), 2),
        "energy_after": round(float(energy_after), 2),
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] CPW: 50+120Hz 能量 {energy_before:.1f} → {energy_after:.1f}")

    # 边界：空 comb_frequencies（不应崩溃，应原样返回或安全处理）
    empty_ok = False
    try:
        out = cepstrum_pre_whitening(sig, FS, comb_frequencies=[])
        empty_ok = len(out) == len(sig)
    except Exception:
        pass
    results.append({
        "test": "cpw_empty_comb",
        "passed": empty_ok,
    })
    print(f"  [{'PASS' if empty_ok else 'FAIL'}] 空 comb_frequencies 安全处理")

    return results


# ═══════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("Layer 2: preprocessing.py — 预处理正确性验证")
    print("=" * 60)

    all_results = {
        "wavelet_denoise": test_wavelet_denoise(),
        "med": test_med(),
        "cpw": test_cpw(),
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
    out_path = OUTPUT_DIR / "preprocessing_correctness.json"
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
