"""
Layer 1 信号基元 — 独立绘图脚本

为每个功能类别生成独立图表，展示：
  prepare_signal, filters, FFT, find_peaks, statistics,
  parabolic_interpolation, SNR/energy, rot_freq, ZOOM-FFT,
  VMD decompose/denoise/impact

用法:
    python tests/diagnosis/foundation/layer1/plot_results.py
"""
import json
import sys
import os
from pathlib import Path
import numpy as np

# 导入云端模块（绘图需要重跑轻量级计算）
_here = Path(__file__).parent
_ws = _here.parent.parent.parent.parent  # 项目根目录
sys.path.insert(0, str(_ws))
sys.path.insert(0, str(_ws / "cloud"))
from app.services.diagnosis.signal_utils import (
    prepare_signal, bandpass_filter, lowpass_filter, highpass_filter,
    compute_fft_spectrum, find_peaks_in_spectrum, compute_snr,
    kurtosis, skewness, rms, peak_value, crest_factor,
    parabolic_interpolation, _band_energy,
    estimate_rot_freq_spectrum, estimate_rot_freq_autocorr,
    estimate_rot_freq_envelope, zoom_fft_analysis,
)
from app.services.diagnosis.vmd_denoise import (
    vmd_decompose, vmd_denoise, vmd_select_impact_mode,
)
from tests.diagnosis.foundation.layer1.synthetic_signals import (
    sinusoidal, gear_mesh, bearing_outer_race,
)

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

OUTPUT_DIR = _here / "output"
PLOT_DIR = OUTPUT_DIR / "plots"
FS = 8192
T_SHOW = 0.2
F_MAX_SHOW = 500


def load_json(name):
    p = OUTPUT_DIR / name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


# ═══════════════════════════════════════════════════════════
# 图1: prepare_signal — DC去除 / 去趋势 前后对比
# ═══════════════════════════════════════════════════════════
def plot_prepare_signal():
    t = np.arange(0, 2, 1/FS)
    t_show = t[:int(T_SHOW * FS)]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

    sig_dc = 3.0 + np.sin(2 * np.pi * 25 * t)
    out_dc = prepare_signal(sig_dc, detrend=False)
    axes[0].plot(t_show, sig_dc[:len(t_show)], color='#FF4D4F', alpha=0.6, linewidth=0.8,
                 label=f'原始 (DC={np.mean(sig_dc):.0f})')
    axes[0].plot(t_show, out_dc[:len(t_show)], color='#165DFF', linewidth=1.2,
                 label=f'去均值 (DC={np.mean(out_dc):.1e})')
    axes[0].axhline(y=0, color='gray', linestyle=':', alpha=0.5)
    axes[0].set_title("去除直流分量 (detrend=False)"); axes[0].set_xlabel("时间 (s)"); axes[0].set_ylabel("幅值")
    axes[0].legend(fontsize=8)

    sig_drift = np.sin(2 * np.pi * 25 * t) + 0.5 * t
    out_drift = prepare_signal(sig_drift, detrend=True)
    axes[1].plot(t_show, sig_drift[:len(t_show)], color='#FF4D4F', alpha=0.6, linewidth=0.8, label='原始 (含漂移)')
    axes[1].plot(t_show, out_drift[:len(t_show)], color='#52C41A', linewidth=1.2, label='去趋势后')
    axes[1].axhline(y=0, color='gray', linestyle=':', alpha=0.5)
    axes[1].set_title("线性去趋势 (detrend=True)"); axes[1].set_xlabel("时间 (s)"); axes[1].set_ylabel("幅值")
    axes[1].legend(fontsize=8)

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "01_prepare_signal.png", dpi=150); plt.close(fig)
    print("  [OK] 01_prepare_signal.png")


# ═══════════════════════════════════════════════════════════
# 图2: 滤波器 — 原始频谱 vs 带通/低通/高通
# ═══════════════════════════════════════════════════════════
def plot_filters():
    t = np.arange(0, 2, 1/FS)
    sig = np.sin(2*np.pi*20*t) + np.sin(2*np.pi*200*t) + np.sin(2*np.pi*1000*t)
    xf_orig, yf_orig = compute_fft_spectrum(sig, FS)

    bp = bandpass_filter(sig, FS, 150, 250)
    lp = lowpass_filter(sig, FS, 100)
    hp = highpass_filter(sig, FS, 500)

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    mask = xf_orig <= F_MAX_SHOW

    axes[0,0].plot(xf_orig[mask], yf_orig[mask], color='gray', linewidth=0.6)
    for f in [20, 200, 1000]:
        axes[0,0].axvline(x=f, color='#FF4D4F', linestyle='--', alpha=0.5, linewidth=0.8)
    axes[0,0].set_title("原始混合信号: 20Hz + 200Hz + 1000Hz"); axes[0,0].set_ylabel("幅值")

    _, yf_bp = compute_fft_spectrum(bp, FS)
    axes[0,1].plot(xf_orig[mask], yf_bp[mask], color='#165DFF', linewidth=0.6)
    axes[0,1].axvspan(150, 250, alpha=0.1, color='#165DFF')
    axes[0,1].axvline(x=200, color='#165DFF', linestyle='--', alpha=0.6)
    axes[0,1].set_title("带通 150-250Hz → 保留 200Hz")

    _, yf_lp = compute_fft_spectrum(lp, FS)
    axes[1,0].plot(xf_orig[mask], yf_lp[mask], color='#52C41A', linewidth=0.6)
    axes[1,0].axvspan(0, 100, alpha=0.1, color='#52C41A')
    axes[1,0].axvline(x=20, color='#52C41A', linestyle='--', alpha=0.6)
    axes[1,0].set_title("低通 ≤100Hz → 保留 20Hz"); axes[1,0].set_xlabel("频率 (Hz)"); axes[1,0].set_ylabel("幅值")

    _, yf_hp = compute_fft_spectrum(hp, FS)
    axes[1,1].plot(xf_orig[mask], yf_hp[mask], color='#FAAD14', linewidth=0.6)
    axes[1,1].axvspan(500, F_MAX_SHOW, alpha=0.1, color='#FAAD14')
    axes[1,1].axvline(x=1000, color='#FAAD14', linestyle='--', alpha=0.6)
    axes[1,1].set_title("高通 ≥500Hz → 保留 1000Hz"); axes[1,1].set_xlabel("频率 (Hz)")

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "02_filters.png", dpi=150); plt.close(fig)
    print("  [OK] 02_filters.png")


# ═══════════════════════════════════════════════════════════
# 图3: FFT 频谱 — 频率检出精度
# ═══════════════════════════════════════════════════════════
def plot_fft():
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for ax, freq in zip(axes, [25, 50, 200]):
        sig, _, _ = sinusoidal(freq=freq, duration=2.0, fs=FS)
        xf, yf = compute_fft_spectrum(sig, FS)
        mask = xf <= freq * 3
        peak_idx = np.argmax(yf)
        detected = xf[peak_idx]
        ax.plot(xf[mask], yf[mask], color='#165DFF', linewidth=0.6)
        ax.axvline(x=freq, color='#52C41A', linestyle='--', linewidth=1.5, label=f'理论={freq}Hz')
        ax.scatter([detected], [yf[peak_idx]], color='red', s=40, zorder=5, label=f'检出={detected:.1f}Hz')
        ax.set_title(f"{freq}Hz 正弦"); ax.set_xlabel("频率 (Hz)"); ax.legend(fontsize=7)

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "03_fft_spectrum.png", dpi=150); plt.close(fig)
    print("  [OK] 03_fft_spectrum.png")


# ═══════════════════════════════════════════════════════════
# 图4: find_peaks_in_spectrum — 谐波族搜索
# ═══════════════════════════════════════════════════════════
def plot_find_peaks():
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

    sig, _, _ = sinusoidal(freq=25.0, duration=2.0, fs=FS)
    xf, yf = compute_fft_spectrum(sig, FS)
    found = find_peaks_in_spectrum(xf, yf, 25.0, tolerance_hz=3.0, n_harmonics=3)
    mask = xf <= 100
    axes[0].plot(xf[mask], yf[mask], color='#165DFF', linewidth=0.6)
    if found["fundamental"]:
        axes[0].scatter([found["fundamental"]["freq"]], [found["fundamental"]["amp"]],
                        color='red', s=60, zorder=5, label='基频')
    for h in found["harmonics"]:
        axes[0].scatter([h["freq"]], [h["amp"]], color='orange', s=40, zorder=5, marker='D', label=f'{h["order"]}次谐波')
    axes[0].set_title("纯正弦 25Hz — 谐波搜索"); axes[0].set_xlabel("频率 (Hz)"); axes[0].set_ylabel("幅值")
    axes[0].legend(fontsize=7)

    sig, _, gt = gear_mesh(mesh_freq=450.0, rot_freq=25.0, duration=2.0, fs=FS, snr_db=30)
    xf, yf = compute_fft_spectrum(sig, FS)
    found = find_peaks_in_spectrum(xf, yf, 450.0, tolerance_hz=5.0, n_harmonics=3)
    mask = xf <= 1400
    axes[1].plot(xf[mask], yf[mask], color='#165DFF', linewidth=0.5)
    if found["fundamental"]:
        axes[1].scatter([found["fundamental"]["freq"]], [found["fundamental"]["amp"]],
                        color='red', s=60, zorder=5, label=f'啮合基频 SNR={found["fundamental"]["snr"]:.0f}')
    for h in found["harmonics"]:
        axes[1].scatter([h["freq"]], [h["amp"]], color='orange', s=35, zorder=5, marker='D')
    axes[1].set_title(f"齿轮啮合信号 450Hz — {len(found['harmonics'])}个谐波检出")
    axes[1].set_xlabel("频率 (Hz)"); axes[1].legend(fontsize=7)

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "04_find_peaks.png", dpi=150); plt.close(fig)
    print("  [OK] 04_find_peaks.png")


# ═══════════════════════════════════════════════════════════
# 图5: 统计指标 — 期望值 vs 实际值
# ═══════════════════════════════════════════════════════════
def plot_statistics():
    np.random.seed(42)
    noise = np.random.randn(50000)
    sig, _, _ = sinusoidal(freq=25.0, duration=2.0, fs=FS)

    metrics = [
        ("峭度\n(高斯≈3)", kurtosis(noise, fisher=False), 3.0),
        ("偏度\n(高斯≈0)", skewness(noise), 0.0),
        ("RMS\n(正弦=1/√2)", rms(sig), 1/np.sqrt(2)),
        ("峰值因子\n(正弦≈√2)", crest_factor(sig), np.sqrt(2)),
        ("峰值\n(正弦≈1)", peak_value(sig), 1.0),
    ]

    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(metrics)); w = 0.35
    actuals = [m[1] for m in metrics]
    expecteds = [m[2] for m in metrics]
    labels = [m[0] for m in metrics]

    ax.bar(x - w/2, expecteds, w, color='#D9D9D9', edgecolor='#999', label='期望值')
    ax.bar(x + w/2, actuals, w, color='#165DFF', label='实际值')

    for i, (a, e) in enumerate(zip(actuals, expecteds)):
        err = abs(a - e) / (abs(e) + 0.001) * 100
        color = '#52C41A' if err < 5 else '#FF4D4F'
        ax.annotate(f'Δ={err:.1f}%', (i, max(a, e) + 0.02), ha='center', fontsize=8, color=color)

    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("值"); ax.set_title("统计指标 — 期望值 vs 实际值")
    ax.legend(); ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "05_statistics.png", dpi=150); plt.close(fig)
    print("  [OK] 05_statistics.png")


# ═══════════════════════════════════════════════════════════
# 图6: parabolic_interpolation — 亚 bin 精度
# ═══════════════════════════════════════════════════════════
def plot_parabolic():
    true_freq = 100.3
    duration = 0.5
    t = np.arange(0, duration, 1/FS)
    sig = np.sin(2 * np.pi * true_freq * t)
    xf, yf = compute_fft_spectrum(sig, FS)
    peak_idx = np.argmax(yf)
    fft_freq = xf[peak_idx]
    interp_freq = parabolic_interpolation(xf, yf, peak_idx)

    margin = 15
    lo, hi = max(0, peak_idx - margin), min(len(xf), peak_idx + margin)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.stem(xf[lo:hi], yf[lo:hi], linefmt='#165DFF', markerfmt='o', basefmt=' ', label='FFT 频谱')
    ax.axvline(x=true_freq, color='#52C41A', linestyle='--', linewidth=2, label=f'真实频率={true_freq}Hz')
    ax.axvline(x=fft_freq, color='orange', linestyle=':', linewidth=1.5, label=f'FFT bin={fft_freq:.1f}Hz')
    ax.axvline(x=interp_freq, color='red', linestyle='-', linewidth=1.5, label=f'插值={interp_freq:.2f}Hz')
    ax.set_title(f"抛物线插值 — 亚 bin 精度\n"
                 f"真实={true_freq}Hz, FFT误差={abs(fft_freq-true_freq):.2f}Hz, 插值误差={abs(interp_freq-true_freq):.3f}Hz")
    ax.set_xlabel("频率 (Hz)"); ax.set_ylabel("幅值"); ax.legend()
    ax.set_xlim(xf[lo], xf[hi-1])
    plt.tight_layout()
    fig.savefig(PLOT_DIR / "06_parabolic_interp.png", dpi=150); plt.close(fig)
    print("  [OK] 06_parabolic_interp.png")


# ═══════════════════════════════════════════════════════════
# 图7: SNR & 频带能量
# ═══════════════════════════════════════════════════════════
def plot_snr_energy():
    sig, _, _ = sinusoidal(freq=50.0, duration=2.0, fs=FS)
    xf, yf = compute_fft_spectrum(sig, FS)
    peak_idx = np.argmax(yf)
    snr_val = compute_snr(yf[peak_idx], yf, method="median")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    mask = xf <= 200
    axes[0].plot(xf[mask], yf[mask], color='#165DFF', linewidth=0.6)
    axes[0].scatter([xf[peak_idx]], [yf[peak_idx]], color='red', s=50, zorder=5)
    axes[0].annotate(f'SNR={snr_val:.0f}\n(中位数法)', (xf[peak_idx], yf[peak_idx]),
                     xytext=(30, 30), textcoords='offset points', fontsize=9,
                     arrowprops=dict(arrowstyle='->', color='red'), color='red')
    axes[0].set_title("compute_snr — 峰值 vs 背景噪声"); axes[0].set_xlabel("频率 (Hz)"); axes[0].set_ylabel("幅值")

    be = _band_energy(xf, yf, center=50.0, bandwidth=10.0)
    mask_band = (xf >= 40) & (xf <= 60)
    axes[1].plot(xf[mask_band], yf[mask_band], color='#165DFF', linewidth=0.6)
    axes[1].fill_between(xf[mask_band], 0, yf[mask_band], alpha=0.2, color='#165DFF')
    axes[1].set_title(f"_band_energy 50±10Hz = {be:.0f}"); axes[1].set_xlabel("频率 (Hz)"); axes[1].set_ylabel("幅值")

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "07_snr_energy.png", dpi=150); plt.close(fig)
    print("  [OK] 07_snr_energy.png")


# ═══════════════════════════════════════════════════════════
# 图8: 转频估计 — 三种方法对比
# ═══════════════════════════════════════════════════════════
def plot_rot_freq():
    test_freqs = [20, 35, 50]
    methods_data = {"spectrum": [], "autocorr": [], "envelope": []}

    for freq in test_freqs:
        sig, _, _ = sinusoidal(freq=freq, duration=2.0, fs=FS)
        methods_data["spectrum"].append(estimate_rot_freq_spectrum(sig, FS, freq_range=(10, 80)))
        ac = estimate_rot_freq_autocorr(sig, FS, freq_range=(10, 80))
        methods_data["autocorr"].append(ac if ac else 0)
        xf, yf = compute_fft_spectrum(sig, FS)
        peak_f = xf[np.argmax(yf)]
        env = estimate_rot_freq_envelope(sig, FS, f_center=peak_f, bw=30, freq_range=(10, 80))
        methods_data["envelope"].append(env if env else 0)

    fig, ax = plt.subplots(figsize=(9, 5))
    x = np.arange(len(test_freqs)); w = 0.22
    colors = {'spectrum': '#165DFF', 'autocorr': '#52C41A', 'envelope': '#FAAD14'}
    for i, (method, vals) in enumerate(methods_data.items()):
        offset = (i - 1) * w
        ax.bar(x + offset, vals, w, label=method, color=colors[method], alpha=0.85)

    for i, freq in enumerate(test_freqs):
        ax.axhline(y=freq, xmin=(i-0.4)/len(test_freqs), xmax=(i+0.4)/len(test_freqs),
                   color='red', linestyle='--', alpha=0.4, linewidth=1)
    ax.set_xticks(x); ax.set_xticklabels([f"{f}Hz 正弦" for f in test_freqs])
    ax.set_ylabel("估计转频 (Hz)"); ax.set_title("转频估计 — spectrum / autocorr / envelope 三方法对比\n红色虚线=真实转频")
    ax.legend()
    plt.tight_layout()
    fig.savefig(PLOT_DIR / "08_rot_freq.png", dpi=150); plt.close(fig)
    print("  [OK] 08_rot_freq.png")


# ═══════════════════════════════════════════════════════════
# 图9: ZOOM-FFT — 细化谱 vs 标准 FFT
# ═══════════════════════════════════════════════════════════
def plot_zoom_fft():
    duration = 0.5
    t = np.arange(0, duration, 1/FS)
    sig = np.sin(2*np.pi*200*t) + 0.8*np.sin(2*np.pi*201*t)
    xf, yf = compute_fft_spectrum(sig, FS)
    zoom = zoom_fft_analysis(sig, FS, center_freq=200.5, bandwidth=10.0, zoom_factor=16)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    mask = (xf >= 190) & (xf <= 210)
    axes[0].stem(xf[mask], yf[mask], linefmt='#165DFF', markerfmt='o', basefmt=' ')
    axes[0].axvline(x=200, color='#52C41A', linestyle='--', linewidth=1, label='200Hz')
    axes[0].axvline(x=201, color='#FF4D4F', linestyle='--', linewidth=1, label='201Hz')
    orig_res = FS / len(sig)
    axes[0].set_title(f"标准 FFT (Δf={orig_res:.1f}Hz)\n200Hz 和 201Hz 难以分辨")
    axes[0].set_xlabel("频率 (Hz)"); axes[0].set_ylabel("幅值"); axes[0].legend(fontsize=7)

    zf = zoom.get("zoom_freq_axis", np.array([]))
    zs = zoom.get("zoom_spectrum", np.array([]))
    if len(zf) > 0:
        axes[1].stem(zf, zs, linefmt='#FAAD14', markerfmt='o', basefmt=' ', label='ZOOM-FFT')
        axes[1].axvline(x=200, color='#52C41A', linestyle='--', linewidth=1, label='200Hz')
        axes[1].axvline(x=201, color='#FF4D4F', linestyle='--', linewidth=1, label='201Hz')
    axes[1].set_title(f"ZOOM-FFT (zoom×{zoom['zoom_factor']})\n聚焦 200.5±5Hz 频带")
    axes[1].set_xlabel("频率 (Hz)"); axes[1].legend(fontsize=7)

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "09_zoom_fft.png", dpi=150); plt.close(fig)
    print("  [OK] 09_zoom_fft.png")


# ═══════════════════════════════════════════════════════════
# 图10: VMD 分解 — IMF 频谱
# ═══════════════════════════════════════════════════════════
def plot_vmd_decompose():
    duration = 1.0
    t = np.arange(0, duration, 1/FS)
    sig = (np.sin(2*np.pi*30*t) + 0.7*np.sin(2*np.pi*120*t) + 0.5*np.sin(2*np.pi*300*t))

    try:
        u, u_hat, omega = vmd_decompose(sig, K=3, alpha=2000, tol=1e-6)
        n_imfs = u.shape[0]

        fig, axes = plt.subplots(1, n_imfs + 1, figsize=(14, 4))
        xf, yf = compute_fft_spectrum(sig, FS)
        mask = xf <= 400
        axes[0].plot(xf[mask], yf[mask], color='gray', linewidth=0.7)
        for f in [30, 120, 300]:
            axes[0].axvline(x=f, color='red', linestyle='--', alpha=0.5, linewidth=0.8)
        axes[0].set_title("原始混合信号\n30+120+300Hz"); axes[0].set_xlabel("Hz")

        for i in range(n_imfs):
            xf_i, yf_i = compute_fft_spectrum(u[i, :], FS)
            peak_f = xf_i[np.argmax(yf_i)]
            axes[i+1].plot(xf_i[mask], yf_i[mask], color='#165DFF', linewidth=0.7)
            axes[i+1].scatter([peak_f], [yf_i[np.argmax(yf_i)]], color='red', s=30, zorder=5)
            axes[i+1].set_title(f"IMF {i}\n峰值={peak_f:.0f}Hz"); axes[i+1].set_xlabel("Hz")

        plt.tight_layout()
        fig.savefig(PLOT_DIR / "10_vmd_decompose.png", dpi=150); plt.close(fig)
        print("  [OK] 10_vmd_decompose.png")
    except Exception as e:
        print(f"  [SKIP] VMD 分解绘图失败: {e}")


# ═══════════════════════════════════════════════════════════
# 图11: VMD 降噪 — 时域/频域 前后对比
# ═══════════════════════════════════════════════════════════
def plot_vmd_denoise():
    duration = 1.0
    t = np.arange(0, duration, 1/FS)
    clean = np.sin(2*np.pi*50*t) + 0.5*np.sin(2*np.pi*120*t)
    np.random.seed(42)
    noisy = clean + 0.5 * np.random.randn(len(t))

    try:
        denoised = vmd_denoise(noisy, K=3, alpha=2000, corr_threshold=0.2, kurt_threshold=2.5)
    except Exception:
        print("  [SKIP] VMD 降噪绘图失败"); return

    t_show = t[:int(0.15 * FS)]
    fig, axes = plt.subplots(2, 3, figsize=(14, 7))

    for ax, label, data, color in [
        (axes[0,0], "纯净信号", clean, '#52C41A'),
        (axes[0,1], "加噪信号", noisy, '#FF4D4F'),
        (axes[0,2], "VMD 降噪后", denoised, '#165DFF'),
    ]:
        ax.plot(t_show, data[:len(t_show)], color=color, linewidth=0.6); ax.set_title(label)

    for ax, label, data, color in [
        (axes[1,0], "纯净信号频谱", clean, '#52C41A'),
        (axes[1,1], "加噪信号频谱", noisy, '#FF4D4F'),
        (axes[1,2], "降噪后频谱", denoised, '#165DFF'),
    ]:
        xf, yf = compute_fft_spectrum(data, FS)
        mask = xf <= 200
        ax.plot(xf[mask], yf[mask], color=color, linewidth=0.6); ax.set_title(label); ax.set_xlabel("Hz")

    snr_before = np.var(clean) / (np.var(noisy - clean) + 1e-12)
    snr_after = np.var(clean) / (np.var(denoised[:len(clean)] - clean[:len(denoised)]) + 1e-12)
    fig.suptitle(f"VMD 降噪: {10*np.log10(snr_before):.1f}dB → {10*np.log10(snr_after):.1f}dB", fontsize=12, y=1.01)
    plt.tight_layout()
    fig.savefig(PLOT_DIR / "11_vmd_denoise.png", dpi=150); plt.close(fig)
    print("  [OK] 11_vmd_denoise.png")


# ═══════════════════════════════════════════════════════════
# 图12: VMD 冲击模态 — 时域波形对比
# ═══════════════════════════════════════════════════════════
def plot_vmd_impact():
    sig, _, gt = bearing_outer_race(bpfo=90.0, rot_freq=25.0, duration=1.0, fs=FS, snr_db=15)

    try:
        best_imf, info = vmd_select_impact_mode(sig, K=3, alpha=2000)
    except Exception:
        print("  [SKIP] VMD 冲击模态绘图失败"); return

    u, _, _ = vmd_decompose(sig, K=3, alpha=2000, tol=1e-6)
    fig, axes = plt.subplots(2, 2, figsize=(10, 7))
    t = np.arange(0, min(1.0, len(sig)/FS), 1/FS)
    t_show = t[:int(0.2 * FS)]

    axes[0,0].plot(t_show, sig[:len(t_show)], color='gray', linewidth=0.5)
    axes[0,0].set_title(f"原始轴承信号\n峭度={kurtosis(sig, fisher=False):.1f}")

    modes = info.get("modes", [])
    for i, m in enumerate(modes[:3]):
        idx = m["index"]
        col = '#165DFF' if idx == info.get("best_index") else '#D9D9D9'
        ax_pos = [(0,1), (1,0), (1,1)][i]
        ax = axes[ax_pos[0], ax_pos[1]]
        ax.plot(t_show, u[idx, :len(t_show)], color=col, linewidth=0.5)
        label = " ★ 最佳冲击" if idx == info.get("best_index") else ""
        ax.set_title(f"IMF {idx}{label}\n峭度={m['kurtosis']:.1f}")

    fig.suptitle("VMD 冲击模态选择 — 最佳 IMF 应保留冲击特征", fontsize=12)
    plt.tight_layout()
    fig.savefig(PLOT_DIR / "12_vmd_impact.png", dpi=150); plt.close(fig)
    print("  [OK] 12_vmd_impact.png")


# ═══════════════════════════════════════════════════════════
# 图14: 真实数据 — 转频估计 vs 真实转速
# ═══════════════════════════════════════════════════════════
def plot_rot_freq_real():
    """真实 WTgearbox + HUSTbear 数据上的转频估计"""
    # 从 JSON 读取测试结果
    data = load_json("signal_utils_correctness.json")
    if not data:
        return
    real_items = data.get("rot_freq_real", [])
    if not real_items:
        return

    wt_items = [it for it in real_items if it.get("dataset") == "WTgearbox"]
    hb_items = [it for it in real_items if it.get("dataset") == "HUSTbear"]

    fig, axes = plt.subplots(1, 2 if hb_items else 1, figsize=(12, 5.5))
    if not isinstance(axes, np.ndarray):
        axes = [axes]

    # WTgearbox
    if wt_items:
        ax = axes[0]
        labels = [it["file"].replace("He_N1_", "").replace("-c1.npy", "") for it in wt_items]
        expecteds = [it["expected_rpm_hz"] for it in wt_items]
        spectrum_ests = [it["spectrum_est"] for it in wt_items]
        autocorr_ests = [it["autocorr_est"] for it in wt_items]

        x = np.arange(len(labels)); w = 0.3
        ax.bar(x - w/2, expecteds, w, color='#D9D9D9', edgecolor='#999', label='真实转速')
        ax.bar(x + w/2, spectrum_ests, w, color='#165DFF', alpha=0.85, label='spectrum法')
        # autocorr as points on top
        valid_ac = [(i, v) for i, v in enumerate(autocorr_ests) if v > 0]
        if valid_ac:
            ax.scatter([i for i, _ in valid_ac], [v for _, v in valid_ac],
                       color='#52C41A', s=60, zorder=5, marker='D', label='autocorr法')

        for i, (e, s) in enumerate(zip(expecteds, spectrum_ests)):
            err = abs(s - e) / e * 100
            color = '#52C41A' if err < 15 else '#FF4D4F'
            ax.annotate(f'{err:.0f}%', (i, max(e, s) + 1), ha='center', fontsize=7, color=color)

        ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8)
        ax.set_ylabel("转频 (Hz)"); ax.set_title("WTgearbox 行星齿轮箱 — 转频估计")
        ax.legend(fontsize=7); ax.grid(axis='y', alpha=0.3)

    # HUSTbear
    if hb_items and len(axes) > 1:
        ax = axes[1]
        labels = [it["file"].replace("0.5X_", "").replace("_20Hz-X.npy", "").replace("H", "健康") for it in hb_items]
        expecteds = [it["expected_rpm_hz"] for it in hb_items]
        spectrum_ests = [it["spectrum_est"] for it in hb_items]

        x = np.arange(len(labels)); w = 0.3
        ax.bar(x - w/2, expecteds, w, color='#D9D9D9', edgecolor='#999', label='真实转速')
        ax.bar(x + w/2, spectrum_ests, w, color='#165DFF', alpha=0.85, label='spectrum估计')
        ax.axhline(y=20, color='red', linestyle='--', alpha=0.4)

        for i, (e, s) in enumerate(zip(expecteds, spectrum_ests)):
            err = abs(s - e) / e * 100
            color = '#52C41A' if err < 20 else '#FF4D4F'
            ax.annotate(f'{err:.0f}%', (i, max(e, s) + 0.5), ha='center', fontsize=8, color=color)

        ax.set_xticks(x); ax.set_xticklabels(labels)
        ax.set_title("HUSTbear 轴承数据 — 转频估计"); ax.legend(fontsize=7); ax.grid(axis='y', alpha=0.3)

    fig.suptitle("真实数据转频估计 — estimate_rot_freq_spectrum 实战验证\n灰色=真实转速, 蓝色=频谱法估计, 绿色菱形=自相关法", fontsize=11)
    plt.tight_layout()
    fig.savefig(PLOT_DIR / "14_real_rotfreq.png", dpi=150); plt.close(fig)
    print("  [OK] 14_real_rotfreq.png")


# ═══════════════════════════════════════════════════════════
# 图15: 真实数据 — VMD 冲击模态
# ═══════════════════════════════════════════════════════════
def plot_vmd_real():
    """真实轴承数据 VMD 冲击模态对比"""
    data = load_json("vmd_denoise_correctness.json")
    if not data:
        return
    items = data.get("vmd_real", [])
    if not items:
        return

    # 分组：HUSTbear 和 CW 分开
    hb_items = [it for it in items if it.get("dataset") == "HUSTbear"]
    cw_items = [it for it in items if it.get("dataset") == "CW"]

    fig, axes = plt.subplots(1, 2 if cw_items else 1, figsize=(14, 6))
    if not isinstance(axes, np.ndarray):
        axes = [axes]

    for ax, ds_items, ds_name in [
        (axes[0], hb_items, "HUSTbear 恒速"),
        (axes[1], cw_items, "CW 变速"),
    ] if cw_items else [(axes[0], hb_items, "HUSTbear")]:
        if not ds_items:
            continue
        labels = [f"{it['description']}" for it in ds_items]
        y = np.arange(len(labels))
        h = 0.3

        orig_k = [it["original_kurtosis"] for it in ds_items]
        best_k = [it["best_imf_kurtosis"] for it in ds_items]

        ax.barh(y + h/2, orig_k, h, color='#D9D9D9', edgecolor='#999', label='原始峭度')
        ax.barh(y - h/2, best_k, h, color='#165DFF', alpha=0.85, label='最佳IMF峭度')
        ax.axvline(x=3.0, color='red', linestyle='--', alpha=0.5, label='高斯≈3')

        for i, (o, b) in enumerate(zip(orig_k, best_k)):
            ax.annotate(f'{o:.1f}→{b:.1f}', (max(o, b) + 0.2, i), va='center', fontsize=7)

        ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=8)
        ax.set_xlabel("峭度"); ax.set_title(f"{ds_name} — VMD 冲击模态")
        ax.legend(fontsize=7, loc='lower right'); ax.grid(axis='x', alpha=0.3)

    fig.suptitle("真实数据 — VMD 冲击模态峭度对比", fontsize=12)
    plt.tight_layout()
    fig.savefig(PLOT_DIR / "15_real_vmd.png", dpi=150); plt.close(fig)
    print("  [OK] 15_real_vmd.png")


# ═══════════════════════════════════════════════════════════
# 图16: 全部合成信号 — 峭度/RMS/峰值因子一览
# ═══════════════════════════════════════════════════════════
def plot_all_synthetic():
    """8种合成信号的统计指标对比"""
    data = load_json("signal_utils_correctness.json")
    if not data:
        return
    items = data.get("all_synthetic", [])
    if not items:
        return

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    labels = [it["signal"] for it in items]
    x = np.arange(len(labels))

    # 峭度
    kurt_vals = [it["kurtosis"] for it in items]
    colors = ['#52C41A' if it["passed"] else '#FF4D4F' for it in items]
    axes[0].bar(x, kurt_vals, color=colors, alpha=0.85)
    axes[0].axhline(y=3.0, color='gray', linestyle='--', alpha=0.5, label='高斯≈3')
    axes[0].set_xticks(x); axes[0].set_xticklabels(labels, rotation=45, fontsize=7, ha='right')
    axes[0].set_title("峭度"); axes[0].legend(fontsize=7)

    # RMS
    rms_vals = [it["rms"] for it in items]
    axes[1].bar(x, rms_vals, color=colors, alpha=0.85)
    axes[1].set_xticks(x); axes[1].set_xticklabels(labels, rotation=45, fontsize=7, ha='right')
    axes[1].set_title("RMS")

    # 峰值因子
    cf_vals = [it["crest_factor"] for it in items]
    axes[2].bar(x, cf_vals, color=colors, alpha=0.85)
    axes[2].set_xticks(x); axes[2].set_xticklabels(labels, rotation=45, fontsize=7, ha='right')
    axes[2].set_title("峰值因子")

    fig.suptitle("6种合成信号 × 统计指标 — 绿=通过, 红=失败", fontsize=12)
    plt.tight_layout()
    fig.savefig(PLOT_DIR / "16_all_synthetic.png", dpi=150); plt.close(fig)
    print("  [OK] 16_all_synthetic.png")


# ═══════════════════════════════════════════════════════════
# 图17: CW 变速 — 转频估计 vs 预期范围
# ═══════════════════════════════════════════════════════════
def plot_cw_variable():
    """CW 变速工况：spectrum法 vs 阶次跟踪法"""
    data = load_json("signal_utils_correctness.json")
    if not data:
        return
    items = data.get("cw_variable_speed", [])
    if not items:
        return

    fig, ax = plt.subplots(figsize=(12, 5.5))
    labels = [f"{it['description']}\n({it['file']})" for it in items]
    y_pos = range(len(labels))

    for i, it in enumerate(items):
        lo, hi = it["expected_range_hz"]
        # 预期范围灰色带
        ax.barh(i, hi - lo, left=lo, height=0.3, color='lightgray', alpha=0.6, zorder=1)
        ax.text(hi + 0.3, i + 0.12, f"[{lo}-{hi}]Hz", fontsize=7, color='gray', va='bottom')

        # spectrum 法
        spec = it["spectrum_est_hz"]
        ax.scatter(spec, i, color='#165DFF', s=80, zorder=3, marker='o', edgecolors='white')
        ax.text(spec + 0.3, i - 0.2, f'spec={spec:.1f}', fontsize=7, color='#165DFF', va='top')

        # 阶次跟踪法
        order_m = it["order_median_hz"]
        ax.scatter(order_m, i, color='#52C41A', s=80, zorder=3, marker='D', edgecolors='white')
        ax.text(order_m + 0.3, i, f'order={order_m:.1f}±{it["order_std_hz"]:.1f}', fontsize=7, color='#52C41A')

        # 通过标记
        passed = it.get("passed", False)
        marker = 'OK' if passed else 'XX'
        color = 'green' if passed else 'red'
        ax.annotate(marker, (max(lo, hi) + 2, i - 0.35), ha='center', color=color, fontsize=12, fontweight='bold')

    ax.set_yticks(list(y_pos)); ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("频率 (Hz)")
    ax.set_title("CW 变速数据集 — 转频估计\n灰色带=预期转速范围, 蓝点=频谱法, 绿菱=阶次跟踪法, ✓=通过")
    ax.grid(axis='x', alpha=0.3)
    plt.tight_layout()
    fig.savefig(PLOT_DIR / "17_cw_variable.png", dpi=150); plt.close(fig)
    print("  [OK] 17_cw_variable.png")


# ═══════════════════════════════════════════════════════════
# 图18-25: 新增 Layer 1 模块（只读 JSON 汇总图）
# ═══════════════════════════════════════════════════════════

def _plot_simple_summary(json_name, title, filename):
    """通用：从 JSON 读取 summary 画简单通过率图"""
    data = load_json(json_name)
    if not data or "summary" not in data:
        print(f"  [SKIP] {json_name} 不存在")
        return
    s = data["summary"]
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.barh(["通过", "失败"], [s["passed"], s["failed"]], color=['#52C41A', '#FF4D4F'])
    ax.set_title(f"{title} ({s['total']}测试)")
    for i, v in enumerate([s["passed"], s["failed"]]):
        ax.text(v + 0.1, i, str(v), va='center', fontsize=12)
    ax.set_xlim(0, max(s["total"] * 1.3, 5))
    plt.tight_layout()
    fig.savefig(PLOT_DIR / filename, dpi=150); plt.close(fig)
    print(f"  [OK] {filename}")


def plot_savgol():
    _plot_simple_summary("savgol_denoise.json", "savgol_denoise", "18_savgol.png")

def plot_wavelet_packet():
    _plot_simple_summary("wavelet_packet.json", "wavelet_packet", "19_wavelet_packet.png")

def plot_msb():
    _plot_simple_summary("msb_correctness.json", "gear/msb MSB", "20_msb.png")

def plot_cyclostationary():
    _plot_simple_summary("bearing_cyclostationary.json", "bearing_cyclostationary", "21_cyclostationary.png")

def plot_modality_bearing():
    _plot_simple_summary("modality_bearing.json", "modality_bearing", "22_modality_bearing.png")

def plot_sensitive_selector():
    _plot_simple_summary("sensitive_selector.json", "sensitive_selector", "23_sensitive_selector.png")

def plot_trend_prediction():
    _plot_simple_summary("trend_prediction.json", "trend_prediction", "24_trend_prediction.png")

def plot_probability_calibration():
    _plot_simple_summary("probability_calibration.json", "probability_calibration", "25_probability_calibration.png")


# ═══════════════════════════════════════════════════════════
# 图13: 汇总 — 全部测试通过率
# ═══════════════════════════════════════════════════════════
def plot_summary():
    summary_data = {}
    all_jsons = [
        "signal_utils_correctness", "vmd_denoise_correctness",
        "health_score_continuous", "bearing_sideband",
        "channel_consensus", "recommendation",
        "savgol_denoise", "wavelet_packet",
        "msb_correctness", "bearing_cyclostationary",
        "modality_bearing", "sensitive_selector",
        "trend_prediction", "probability_calibration",
    ]
    for json_name in all_jsons:
        data = load_json(f"{json_name}.json")
        if data and "summary" in data:
            label = json_name.replace("_correctness", "").replace("_", " ")
            summary_data[label] = data["summary"]

    su_data = load_json("signal_utils_correctness.json")
    categories = {}
    if su_data:
        for cat in [k for k in su_data.keys() if k != "summary"]:
            items = su_data[cat]
            categories[cat.replace("_", " ")] = {
                "total": len(items), "passed": sum(1 for it in items if it.get("passed", False)),
            }

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    if categories:
        labels = list(categories.keys())
        totals = [categories[l]["total"] for l in labels]
        passed = [categories[l]["passed"] for l in labels]
        failed = [t - p for t, p in zip(totals, passed)]
        x = np.arange(len(labels))
        axes[0].bar(x, passed, color='#52C41A', label='通过')
        axes[0].bar(x, failed, bottom=passed, color='#FF4D4F', label='失败')
        axes[0].set_xticks(x); axes[0].set_xticklabels(labels, fontsize=7, rotation=15)
        axes[0].set_title("signal_utils — 13 类函数正确性"); axes[0].legend()
        for i, (t, p) in enumerate(zip(totals, passed)):
            axes[0].text(i, t + 0.15, f"{p}/{t}", ha='center', fontsize=8)

    labels2 = list(summary_data.keys())
    totals2 = [summary_data[l]["total"] for l in labels2]
    passed2 = [summary_data[l]["passed"] for l in labels2]
    failed2 = [t - p for t, p in zip(totals2, passed2)]
    x2 = np.arange(len(labels2))
    axes[1].bar(x2, passed2, color='#52C41A', label='通过')
    axes[1].bar(x2, failed2, bottom=passed2, color='#FF4D4F', label='失败')
    axes[1].set_xticks(x2); axes[1].set_xticklabels(labels2)
    axes[1].set_title("Layer 1 总体通过率"); axes[1].legend()
    for i, (t, p) in enumerate(zip(totals2, passed2)):
        axes[1].text(i, t + 0.3, f"{p}/{t} ({p*100//t}%)", ha='center', fontsize=10)

    fig.suptitle("Layer 1: 信号基元 — 测试通过率汇总", fontsize=13)
    plt.tight_layout()
    fig.savefig(PLOT_DIR / "13_summary.png", dpi=150); plt.close(fig)
    print("  [OK] 13_summary.png")


def main():
    if not HAS_MPL:
        print("matplotlib 未安装，跳过绘图"); return

    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    print("Layer 1: 信号基元 — 生成详细对比图")
    print("=" * 55)

    plot_prepare_signal()      # 01
    plot_filters()             # 02
    plot_fft()                 # 03
    plot_find_peaks()          # 04
    plot_statistics()          # 05
    plot_parabolic()           # 06
    plot_snr_energy()          # 07
    plot_rot_freq()            # 08
    plot_zoom_fft()            # 09
    plot_vmd_decompose()       # 10
    plot_vmd_denoise()         # 11
    plot_vmd_impact()          # 12
    plot_rot_freq_real()       # 14
    plot_vmd_real()            # 15
    plot_all_synthetic()       # 16
    plot_cw_variable()         # 17
    plot_savgol()              # 18
    plot_wavelet_packet()      # 19
    plot_msb()                 # 20
    plot_cyclostationary()     # 21
    plot_modality_bearing()    # 22
    plot_sensitive_selector()  # 23
    plot_trend_prediction()    # 24
    plot_probability_calibration() # 25
    plot_summary()             # 13

    print(f"\n共 25 张图表 → {PLOT_DIR}")


if __name__ == "__main__":
    main()
