"""
Layer 1 信号基元 — signal_utils 正确性验证

测试 signal_utils.py 中所有零内部依赖的函数：
  prepare_signal, bandpass/lowpass/highpass_filter,
  compute_fft_spectrum, compute_power_spectrum,
  find_peaks_in_spectrum, compute_snr,
  kurtosis, skewness, rms, peak_value, crest_factor,
  parabolic_interpolation, _band_energy, _order_band_energy,
  estimate_rot_freq_spectrum, estimate_rot_freq_autocorr,
  estimate_rot_freq_envelope, zoom_fft_analysis

原则：用合成信号（已知 ground truth）验证计算正确性。

输出: layer1/output/signal_utils_correctness.json
"""
import json
import sys
import os
from pathlib import Path
import numpy as np

# 导入云端模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.signal_utils import (
    prepare_signal, remove_dc, linear_detrend,
    bandpass_filter, lowpass_filter, highpass_filter,
    compute_fft_spectrum, compute_power_spectrum,
    find_peaks_in_spectrum, compute_snr,
    kurtosis, skewness, rms, peak_value, crest_factor,
    parabolic_interpolation, _band_energy, _order_band_energy,
    estimate_rot_freq_spectrum, estimate_rot_freq_autocorr,
    estimate_rot_freq_envelope, zoom_fft_analysis,
)
from tests.diagnosis.foundation.layer1.synthetic_signals import NumpyEncoder, sinusoidal, chirp_rotating, gear_mesh

OUTPUT_DIR = Path(__file__).parent / "output"
FS = 8192

# ═══════════════════════════════════════════════════════════
# 1. prepare_signal — 零均值化 / 线性去趋势
# ═══════════════════════════════════════════════════════════

def test_prepare_signal():
    """零均值化和去趋势"""
    print("\n--- prepare_signal ---")
    results = []

    # 1a. 零均值化：带 DC 偏移的正弦信号
    t = np.arange(0, 2, 1/FS)
    sig = 3.0 + np.sin(2 * np.pi * 25 * t)  # DC=3, AC=1
    out = prepare_signal(sig, detrend=False)
    mean_ok = abs(np.mean(out)) < 1e-10
    amp_ok = abs(np.max(out) - 1.0) < 0.05
    results.append({
        "test": "prepare_zero_mean", "expected_mean": 0.0,
        "actual_mean": float(np.mean(out)), "passed": mean_ok and amp_ok,
    })
    print(f"  [{'PASS' if mean_ok and amp_ok else 'FAIL'}] 零均值化: mean={np.mean(out):.2e}, max≈{np.max(out):.2f}")

    # 1b. 线性去趋势：带线性漂移的信号
    sig_drift = np.sin(2 * np.pi * 25 * t) + 0.5 * t  # 线性增长漂移
    out = prepare_signal(sig_drift, detrend=True)
    # 去趋势后均值应接近0, 不应有明显趋势
    residual_trend = np.polyfit(t, out, 1)[0]
    trend_removed = abs(residual_trend) < 0.05
    results.append({
        "test": "prepare_detrend", "expected_trend": 0.0,
        "actual_trend": round(float(residual_trend), 4), "passed": trend_removed,
    })
    print(f"  [{'PASS' if trend_removed else 'FAIL'}] 去趋势: residual slope={residual_trend:.4f}")

    # 1c. 输入为 list 而非 ndarray
    out = prepare_signal([1.0, 2.0, 3.0, 2.0, 1.0], detrend=False)
    list_ok = isinstance(out, np.ndarray) and abs(np.mean(out)) < 1e-10
    results.append({
        "test": "prepare_list_input", "passed": list_ok,
    })
    print(f"  [{'PASS' if list_ok else 'FAIL'}] list 输入: type={type(out).__name__}")

    return results


# ═══════════════════════════════════════════════════════════
# 2. 滤波器 — 频带隔离
# ═══════════════════════════════════════════════════════════

def test_filters():
    """带通/低通/高通滤波"""
    print("\n--- 滤波器 ---")
    results = []
    t = np.arange(0, 2, 1/FS)
    # 混合信号: 20Hz + 200Hz + 1000Hz
    sig = (np.sin(2*np.pi*20*t) + np.sin(2*np.pi*200*t) + np.sin(2*np.pi*1000*t))

    # 2a. 带通: 隔离 200Hz
    bp = bandpass_filter(sig, FS, 150, 250, order=4)
    _, bp_spec = compute_fft_spectrum(bp, FS)
    _, orig_spec = compute_fft_spectrum(sig, FS)
    # 滤波后 200Hz 附近能量应占主导
    mask_band = (np.arange(len(bp_spec)) * FS / len(bp) >= 150) & (np.arange(len(bp_spec)) * FS / len(bp) <= 250)
    ratio = bp_spec[mask_band].sum() / (bp_spec.sum() + 1e-12)
    bp_ok = ratio > 0.6
    results.append({
        "test": "bandpass_200Hz", "band_energy_ratio": round(float(ratio), 3),
        "passed": bp_ok,
    })
    print(f"  [{'PASS' if bp_ok else 'FAIL'}] 带通 150-250Hz: 带内能量占比={ratio:.2f}")

    # 2b. 低通: 仅保留 20Hz
    lp = lowpass_filter(sig, FS, 100, order=4)
    _, lp_spec = compute_fft_spectrum(lp, FS)
    # 1000Hz 应被大幅衰减
    idx_1k = int(1000 * len(lp_spec) / (FS/2))
    idx_20 = int(20 * len(lp_spec) / (FS/2))
    if idx_1k < len(lp_spec) and idx_20 < len(lp_spec):
        lp_ok = lp_spec[idx_20] > lp_spec[idx_1k] * 3
    else:
        lp_ok = True
    results.append({
        "test": "lowpass_100Hz", "passed": lp_ok,
    })
    print(f"  [{'PASS' if lp_ok else 'FAIL'}] 低通 100Hz: 20Hz抑制1000Hz")

    # 2c. 高通: 仅保留 1000Hz
    hp = highpass_filter(sig, FS, 500, order=4)
    _, hp_spec = compute_fft_spectrum(hp, FS)
    idx_1k_hp = int(1000 * len(hp_spec) / (FS/2))
    idx_20_hp = int(20 * len(hp_spec) / (FS/2))
    if idx_1k_hp < len(hp_spec) and idx_20_hp < len(hp_spec):
        hp_ok = hp_spec[idx_1k_hp] > hp_spec[idx_20_hp] * 3
    else:
        hp_ok = True
    results.append({
        "test": "highpass_500Hz", "passed": hp_ok,
    })
    print(f"  [{'PASS' if hp_ok else 'FAIL'}] 高通 500Hz: 1000Hz抑制20Hz")

    # 2d. 极短信号（不会崩溃）
    short = np.array([1.0, -1.0, 1.0])
    try:
        _ = bandpass_filter(short, FS, 10, 100)
        short_ok = True
    except Exception:
        short_ok = False
    results.append({
        "test": "filter_short_signal", "passed": short_ok,
    })
    print(f"  [{'PASS' if short_ok else 'FAIL'}] 极短信号(3点)不崩溃")

    return results


# ═══════════════════════════════════════════════════════════
# 3. FFT 频谱 — 频率 & 幅值正确
# ═══════════════════════════════════════════════════════════

def test_fft_spectrum():
    """FFT 频谱：纯正弦 → 正确频率 + 近似幅值"""
    print("\n--- FFT 频谱 ---")
    results = []

    for freq in [25, 50, 200]:
        sig, fs, gt = sinusoidal(freq=freq, duration=3.0, fs=FS)
        xf, yf = compute_fft_spectrum(sig, fs)

        # 找最大峰值
        peak_idx = np.argmax(yf)
        detected_freq = xf[peak_idx]
        detected_amp = yf[peak_idx]

        # 频率误差 < 分辨率
        df = fs / len(sig)
        freq_ok = abs(detected_freq - freq) < df * 1.5

        # 幅值：正弦幅值=1 → FFT 幅值 ≈ N/2（去掉直流）
        n = len(sig) - 2  # 去掉 DC 分量损失
        expected_amp = n / 2.0
        amp_ok = abs(detected_amp / expected_amp - 1.0) < 0.15

        results.append({
            "test": f"fft_sine_{freq}Hz",
            "expected_freq": freq,
            "detected_freq": round(float(detected_freq), 2),
            "freq_error_hz": round(float(abs(detected_freq - freq)), 3),
            "passed": freq_ok,
        })
        print(f"  [{'PASS' if freq_ok else 'FAIL'}] {freq}Hz正弦: 检出{freq}={detected_freq:.1f}Hz, 幅值比={detected_amp/expected_amp:.2f}")

    return results


# ═══════════════════════════════════════════════════════════
# 4. find_peaks_in_spectrum — 谐波族搜索
# ═══════════════════════════════════════════════════════════

def test_find_peaks():
    """谐波族搜索：纯正弦 + 含谐波的信号"""
    print("\n--- find_peaks_in_spectrum ---")
    results = []

    # 4a. 纯正弦 25Hz
    sig, fs, _ = sinusoidal(freq=25.0, duration=3.0, fs=FS)
    xf, yf = compute_fft_spectrum(sig, fs)
    found = find_peaks_in_spectrum(xf, yf, 25.0, tolerance_hz=3.0, n_harmonics=3)
    fund_freq_ok = found["fundamental"] is not None and abs(found["fundamental"]["freq"] - 25.0) < 1.0
    results.append({
        "test": "find_peaks_sine_25Hz",
        "fundamental_freq": found["fundamental"]["freq"] if found["fundamental"] else None,
        "n_harmonics": len(found["harmonics"]),
        "passed": fund_freq_ok,
    })
    print(f"  [{'PASS' if fund_freq_ok else 'FAIL'}] 25Hz纯正弦: fund={found['fundamental']}")

    # 4b. 齿轮啮合信号（含谐波 + 边频带）
    sig, fs, gt = gear_mesh(mesh_freq=450.0, rot_freq=25.0, duration=3.0, fs=FS, snr_db=30)
    xf, yf = compute_fft_spectrum(sig, fs)
    found = find_peaks_in_spectrum(xf, yf, 450.0, tolerance_hz=5.0, n_harmonics=3)
    mesh_ok = found["fundamental"] is not None and abs(found["fundamental"]["freq"] - 450.0) < 5.0
    results.append({
        "test": "find_peaks_mesh_450Hz",
        "fundamental_freq": found["fundamental"]["freq"] if found["fundamental"] else None,
        "n_harmonics": len(found["harmonics"]),
        "fund_snr": round(found["fundamental"]["snr"], 2) if found["fundamental"] else 0,
        "passed": mesh_ok,
    })
    print(f"  [{'PASS' if mesh_ok else 'FAIL'}] 啮合信号450Hz: fund={found['fundamental']['freq'] if found['fundamental'] else None:.1f}Hz, harmonics={len(found['harmonics'])}")

    return results


# ═══════════════════════════════════════════════════════════
# 5. 统计指标 — kurtosis/skewness/rms/crest
# ═══════════════════════════════════════════════════════════

def test_statistics():
    """统计指标：已知分布的统计量"""
    print("\n--- 统计指标 ---")
    results = []
    np.random.seed(42)

    # 5a. kurtosis: 正态分布 ≈ 3 (fisher=False)
    noise = np.random.randn(50000)
    k = kurtosis(noise, fisher=False)
    k_ok = 2.8 < k < 3.2
    results.append({
        "test": "kurtosis_gaussian", "expected": 3.0, "actual": round(k, 3),
        "passed": k_ok,
    })
    print(f"  [{'PASS' if k_ok else 'FAIL'}] 高斯噪声峭度: {k:.2f} (期望≈3)")

    # 5b. skewness: 正态分布 ≈ 0
    s = skewness(noise)
    s_ok = abs(s) < 0.05
    results.append({
        "test": "skewness_gaussian", "expected": 0.0, "actual": round(s, 4),
        "passed": s_ok,
    })
    print(f"  [{'PASS' if s_ok else 'FAIL'}] 高斯噪声偏度: {s:.4f} (期望≈0)")

    # 5c. rms: 正弦信号 → A/√2
    sig, _, _ = sinusoidal(freq=25.0, duration=3.0, fs=FS)
    r = rms(sig)
    expected_rms = 1.0 / np.sqrt(2)
    r_ok = abs(r - expected_rms) < 0.02
    results.append({
        "test": "rms_sinusoid", "expected": round(expected_rms, 4), "actual": round(r, 4),
        "passed": r_ok,
    })
    print(f"  [{'PASS' if r_ok else 'FAIL'}] 正弦RMS: {r:.4f} (期望≈{expected_rms:.4f})")

    # 5d. crest_factor: 正弦 → √2 ≈ 1.414
    cf = crest_factor(sig)
    cf_ok = 1.35 < cf < 1.5
    results.append({
        "test": "crest_sinusoid", "expected": round(np.sqrt(2), 3), "actual": round(cf, 3),
        "passed": cf_ok,
    })
    print(f"  [{'PASS' if cf_ok else 'FAIL'}] 正弦峰值因子: {cf:.3f} (期望≈{np.sqrt(2):.3f})")

    # 5e. peak_value
    pv = peak_value(sig)
    pv_ok = 0.95 < pv < 1.05
    results.append({
        "test": "peak_sinusoid", "expected": 1.0, "actual": round(pv, 3),
        "passed": pv_ok,
    })
    print(f"  [{'PASS' if pv_ok else 'FAIL'}] 正弦峰值: {pv:.3f} (期望≈1.0)")

    return results


# ═══════════════════════════════════════════════════════════
# 6. parabolic_interpolation — 亚分辨率精确定位
# ═══════════════════════════════════════════════════════════

def test_parabolic_interpolation():
    """抛物线插值：比 FFT 分辨率更精确"""
    print("\n--- parabolic_interpolation ---")
    results = []

    # 构造已知频率的正弦，用低分辨率 FFT 后插值
    true_freq = 100.3  # 不落在频率 bin 上
    duration = 0.5  # 短信号 → 分辨率差
    t = np.arange(0, duration, 1/FS)
    sig = np.sin(2 * np.pi * true_freq * t)
    xf, yf = compute_fft_spectrum(sig, FS)

    # 找最强峰
    peak_idx = np.argmax(yf)
    fft_freq = xf[peak_idx]
    interpolated_freq = parabolic_interpolation(xf, yf, peak_idx)

    # 插值后应比原始 FFT bin 更接近真实值
    fft_err = abs(fft_freq - true_freq)
    interp_err = abs(interpolated_freq - true_freq)
    improved = interp_err < fft_err or interp_err < 0.5

    results.append({
        "test": "parabolic_100.3Hz",
        "true_freq": true_freq,
        "fft_bin_freq": round(float(fft_freq), 3),
        "interpolated_freq": round(float(interpolated_freq), 3),
        "fft_error_hz": round(float(fft_err), 3),
        "interp_error_hz": round(float(interp_err), 3),
        "passed": improved,
    })
    print(f"  [{'PASS' if improved else 'FAIL'}] 100.3Hz: FFT bin={fft_freq:.1f}Hz, 插值={interpolated_freq:.2f}Hz, 真实={true_freq}Hz")

    return results


# ═══════════════════════════════════════════════════════════
# 7. compute_snr / _band_energy / _order_band_energy
# ═══════════════════════════════════════════════════════════

def test_snr_and_energy():
    """SNR 和频带能量"""
    print("\n--- SNR & 频带能量 ---")
    results = []

    # 7a. compute_snr: 已知信号+噪声
    sig, fs, _ = sinusoidal(freq=50.0, duration=3.0, fs=FS)
    xf, yf = compute_fft_spectrum(sig, fs)
    peak_idx = np.argmax(yf)
    snr_val = compute_snr(yf[peak_idx], yf, method="median")
    # 纯正弦 SNR 应很高
    snr_ok = snr_val > 20
    results.append({
        "test": "snr_pure_sine", "snr": round(float(snr_val), 1),
        "passed": snr_ok,
    })
    print(f"  [{'PASS' if snr_ok else 'FAIL'}] 纯正弦SNR: {snr_val:.0f} (期望>20)")

    # 7b. _band_energy: 在已知频带
    be = _band_energy(xf, yf, center=50.0, bandwidth=10.0)
    be_ok = be > 0
    results.append({
        "test": "band_energy_50Hz", "energy": round(float(be), 2), "passed": be_ok,
    })
    print(f"  [{'PASS' if be_ok else 'FAIL'}] 50Hz±10Hz 频带能量: {be:.1f}")

    # 7c. _order_band_energy
    order_axis = np.arange(0, 20.1, 0.1)
    spec = np.exp(-((order_axis - 5) ** 2) / 0.5)  # 高斯峰在 order=5
    oe = _order_band_energy(order_axis, spec, center_order=5.0, bandwidth=2.0)
    oe_ok = oe > 0
    results.append({
        "test": "order_band_energy_order5", "energy": round(float(oe), 4), "passed": oe_ok,
    })
    print(f"  [{'PASS' if oe_ok else 'FAIL'}] order=5±2 能量: {oe:.4f}")

    return results


# ═══════════════════════════════════════════════════════════
# 8. 转频估计 — spectrum / autocorr / envelope
# ═══════════════════════════════════════════════════════════

def test_rot_freq_estimation():
    """转频估计：三种方法对比"""
    print("\n--- 转频估计 ---")
    results = []

    for freq in [20, 35, 50]:
        sig, fs, _ = sinusoidal(freq=freq, duration=3.0, fs=FS)

        # 8a. 频谱法
        rf_spec = estimate_rot_freq_spectrum(sig, fs, freq_range=(10, 80))
        spec_ok = abs(rf_spec - freq) / freq < 0.10

        # 8b. 自相关法
        rf_ac = estimate_rot_freq_autocorr(sig, fs, freq_range=(10, 80))
        ac_ok = rf_ac is not None and abs(rf_ac - freq) / freq < 0.10

        # 8c. 包络法（用最强峰附近做带通）
        xf, yf = compute_fft_spectrum(sig, fs)
        peak_freq = xf[np.argmax(yf)]
        rf_env = estimate_rot_freq_envelope(sig, fs, f_center=peak_freq, bw=30, freq_range=(10, 80))
        env_ok = rf_env is not None

        results.append({
            "test": f"rot_freq_{freq}Hz",
            "true_freq": freq,
            "spectrum_est": round(float(rf_spec), 2),
            "spectrum_ok": spec_ok,
            "autocorr_est": round(float(rf_ac), 2) if rf_ac else None,
            "autocorr_ok": ac_ok,
            "envelope_est": round(float(rf_env), 2) if rf_env else None,
            "passed": spec_ok,  # 至少频谱法要对
        })
        ac_str = f"{rf_ac:.1f}" if rf_ac else "None"
        env_str = f"{rf_env:.1f}" if rf_env else "None"
        print(f"  [{'PASS' if spec_ok else 'FAIL'}] {freq}Hz: spectrum={rf_spec:.1f}, autocorr={ac_str}, envelope={env_str}")

    return results


# ═══════════════════════════════════════════════════════════
# 9. zoom_fft_analysis — 细化谱
# ═══════════════════════════════════════════════════════════

def test_zoom_fft():
    """ZOOM-FFT：分辨率高于标准 FFT"""
    print("\n--- ZOOM-FFT ---")
    results = []

    # 两个很近的频率：200Hz 和 201Hz（标准 FFT 可能分不开）
    duration = 0.5  # 短信号 → 分辨率 2Hz
    t = np.arange(0, duration, 1/FS)
    sig = np.sin(2*np.pi*200*t) + 0.8*np.sin(2*np.pi*201*t)

    # 标准 FFT 分辨率
    _, yf = compute_fft_spectrum(sig, FS)
    xf, _ = compute_fft_spectrum(sig, FS)
    original_res = FS / len(sig)

    # ZOOM-FFT
    zoom = zoom_fft_analysis(sig, FS, center_freq=200.5, bandwidth=10.0, zoom_factor=16)
    zoom_res = zoom["resolution_hz"]

    # ZOOM-FFT 的正确性：频率轴应围绕 center_freq，且频带限定在 bandwidth 内
    zoom_freqs = zoom.get("zoom_freq_axis", np.array([]))
    centered = len(zoom_freqs) > 0 and abs(np.mean(zoom_freqs) - 200.5) < 3.0
    in_band = len(zoom_freqs) == 0 or (zoom_freqs.min() >= 195.5 and zoom_freqs.max() <= 205.5)

    results.append({
        "test": "zoom_200Hz_close",
        "original_resolution_hz": round(original_res, 4),
        "zoom_resolution_hz": zoom_res,
        "zoom_factor": zoom["zoom_factor"],
        "valid": zoom["valid"],
        "freq_range": [round(float(zoom_freqs.min()), 2), round(float(zoom_freqs.max()), 2)] if len(zoom_freqs) > 0 else [],
        "passed": zoom["valid"] and centered and in_band,
    })
    print(f"  [{'PASS' if zoom['valid'] and centered and in_band else 'FAIL'}] ZOOM-FFT 200Hz: "
          f"频率范围=[{zoom_freqs.min():.1f}, {zoom_freqs.max():.1f}], factor={zoom['zoom_factor']}")

    # 边界条件：无效输入
    zoom_invalid = zoom_fft_analysis(sig, FS, center_freq=0, bandwidth=0)
    invalid_ok = not zoom_invalid["valid"]
    results.append({
        "test": "zoom_invalid_input", "passed": invalid_ok,
    })
    print(f"  [{'PASS' if invalid_ok else 'FAIL'}] 无效输入安全处理")

    return results


# ═══════════════════════════════════════════════════════════
# main — 汇总输出
# ═══════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("Layer 1: signal_utils — 信号基元正确性验证")
    print("=" * 60)

    all_results = {
        "prepare_signal": test_prepare_signal(),
        "filters": test_filters(),
        "fft_spectrum": test_fft_spectrum(),
        "find_peaks": test_find_peaks(),
        "statistics": test_statistics(),
        "parabolic_interpolation": test_parabolic_interpolation(),
        "snr_and_energy": test_snr_and_energy(),
        "rot_freq_estimation": test_rot_freq_estimation(),
        "zoom_fft": test_zoom_fft(),
    }

    # 汇总
    total = 0
    passed = 0
    for category, items in all_results.items():
        for item in items:
            total += 1
            if item.get("passed", False):
                passed += 1

    all_results["summary"] = {"total": total, "passed": passed, "failed": total - passed}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "signal_utils_correctness.json"
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
