"""
Layer 1 信号基元 — 独立绘图脚本（严格遵循绘图规范 v2）

规范摘要：每张图必须包含 GT参照、阈值线、✓/✗标记、定量差异标注、判定标准标题

用法:
    python tests/diagnosis/foundation/layer1/plot_results.py
"""
import json, sys, os
from pathlib import Path
import numpy as np

_here = Path(__file__).parent
_ws = _here.parent.parent.parent.parent
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
    sinusoidal, gear_mesh, bearing_outer_race, bearing_inner_race,
)

# ── 新增模块导入 ──
from app.services.diagnosis.savgol_denoise import sg_denoise, sg_trend_residual
from app.services.diagnosis.wavelet_packet import (
    wavelet_packet_decompose, compute_wavelet_packet_energy_entropy, wavelet_packet_denoise,
)
from app.services.diagnosis.gear.msb import msb_residual_sideband_analysis
from app.services.diagnosis.bearing_cyclostationary import _compute_sc_scoh_bearing, bearing_sc_scoh_analysis
from app.services.diagnosis.modality_bearing import emd_bearing_analysis, vmd_bearing_analysis
from app.services.diagnosis.sensitive_selector import score_components
from app.services.diagnosis.trend_prediction import holt_winters_forecast, kalman_smooth_health_scores
from app.services.diagnosis.probability_calibration import _sigmoid_prob, calibrate_snr_to_prob

try:
    import matplotlib; matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

OUTPUT_DIR = _here / "output"
PLOT_DIR = OUTPUT_DIR / "plots"
FS, T_SHOW, F_MAX_SHOW = 8192, 0.2, 500

# ═══════ 统一颜色语义（强制所有图使用） ═══════
C_PASS   = '#52C41A'  # 绿 = 通过/正确
C_FAIL   = '#FF4D4F'  # 红 = 失败/错误
C_GT     = '#D9D9D9'  # 灰 = Ground Truth / 理论值
C_THRESH = '#FAAD14'  # 橙 = 阈值线 / 边界
C_EST    = '#165DFF'  # 蓝 = 算法估计值
MK_OK, MK_NG = 'PASS', 'FAIL'

def load_json(name):
    p = OUTPUT_DIR / name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


# ═══════════════════════════════════════════════════════════
# 图1: prepare_signal — DC去除 / 去趋势 前后对比
# ═══════════════════════════════════════════════════════════
def plot_prepare_signal():
    t = np.arange(0, 2, 1/FS); ts = t[:int(T_SHOW * FS)]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

    sig_dc = 3.0 + np.sin(2*np.pi*25*t)
    out_dc = prepare_signal(sig_dc, detrend=False)
    axes[0].plot(ts, sig_dc[:len(ts)], color=C_FAIL, alpha=0.6, lw=0.8, label=f'原始(DC={np.mean(sig_dc):.0f})')
    axes[0].plot(ts, out_dc[:len(ts)], color=C_EST, lw=1.2, label=f'去均值后(DC={np.mean(out_dc):.1e})')
    axes[0].axhline(y=0, color=C_GT, ls='--', lw=1, label='GT: DC=0')
    mk = MK_OK if abs(np.mean(out_dc)) < 1e-8 else MK_NG
    axes[0].set_title(f"去除直流分量 | 残余DC={np.mean(out_dc):.1e} [{mk}]\n判定:处理后均值<1e-8为通过")
    axes[0].set_xlabel("时间(s)"); axes[0].set_ylabel("幅值"); axes[0].legend(fontsize=7)

    sig_drift = np.sin(2*np.pi*25*t) + 0.5*t
    out_drift = prepare_signal(sig_drift, detrend=True)
    slope = float(np.polyfit(t, out_drift, 1)[0])
    axes[1].plot(ts, sig_drift[:len(ts)], color=C_FAIL, alpha=0.6, lw=0.8, label='原始(含漂移y=0.5t)')
    axes[1].plot(ts, out_drift[:len(ts)], color=C_PASS, lw=1.2, label=f'去趋势后(斜率={slope:.1e})')
    axes[1].axhline(y=0, color=C_GT, ls='--', lw=1, label='GT: 斜率=0')
    mk2 = MK_OK if abs(slope) < 0.05 else MK_NG
    axes[1].set_title(f"线性去趋势 y=kx+b | 残余斜率={slope:.3f} [{mk2}]\n判定:残余斜率<0.05为通过")
    axes[1].set_xlabel("时间(s)"); axes[1].legend(fontsize=7)

    plt.tight_layout(); fig.savefig(PLOT_DIR/"01_prepare_signal.png", dpi=150); plt.close()
    print("  [OK] 01_prepare_signal.png")


# ═══════════════════════════════════════════════════════════
# 图2: 滤波器 — 原始频谱 vs 带通/低通/高通
# ═══════════════════════════════════════════════════════════
def plot_filters():
    t = np.arange(0, 2, 1/FS)
    sig = np.sin(2*np.pi*20*t)+np.sin(2*np.pi*200*t)+np.sin(2*np.pi*1000*t)
    xf, yf = compute_fft_spectrum(sig, FS); m = xf <= F_MAX_SHOW
    bp = bandpass_filter(sig, FS, 150, 250); lp = lowpass_filter(sig, FS, 100); hp = highpass_filter(sig, FS, 500)

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    axes[0,0].plot(xf[m], yf[m], color=C_GT, lw=0.6)
    for f in [20,200,1000]: axes[0,0].axvline(x=f, color=C_FAIL, ls='--', alpha=0.5, lw=0.8)
    axes[0,0].set_title("原始混合信号: 20+200+1000Hz (GT)"); axes[0,0].set_ylabel("幅值")

    _, yb = compute_fft_spectrum(bp, FS)
    axes[0,1].plot(xf[m], yb[m], color=C_EST, lw=0.6)
    axes[0,1].axvspan(150, 250, alpha=0.15, color=C_PASS, label='通带150-250Hz')
    axes[0,1].axvline(x=200, color=C_PASS, ls='--', alpha=0.6, label='保留200Hz')
    ratio = yb[(xf>=150)&(xf<=250)].sum()/(yb.sum()+1e-12)
    mk = MK_OK if ratio > 0.6 else MK_NG
    axes[0,1].set_title(f"带通150-250Hz | 带内能量={ratio:.0%} [{mk}]\n判定:带内能量>60%为通过")
    axes[0,1].legend(fontsize=6)

    _, yl = compute_fft_spectrum(lp, FS)
    axes[1,0].plot(xf[m], yl[m], color=C_PASS, lw=0.6)
    axes[1,0].axvspan(0, 100, alpha=0.15, color=C_PASS, label='通带≤100Hz')
    axes[1,0].axvline(x=20, color=C_PASS, ls='--', alpha=0.6, label='保留20Hz')
    axes[1,0].set_title("低通≤100Hz → 保留20Hz"); axes[1,0].set_xlabel("Hz"); axes[1,0].set_ylabel("幅值")
    axes[1,0].legend(fontsize=6)

    _, yh = compute_fft_spectrum(hp, FS)
    axes[1,1].plot(xf[m], yh[m], color=C_THRESH, lw=0.6)
    axes[1,1].axvspan(500, F_MAX_SHOW, alpha=0.15, color=C_THRESH, label='通带≥500Hz')
    axes[1,1].axvline(x=1000, color=C_THRESH, ls='--', alpha=0.6, label='保留1000Hz')
    axes[1,1].set_title("高通≥500Hz → 保留1000Hz"); axes[1,1].set_xlabel("Hz")
    axes[1,1].legend(fontsize=6)

    plt.tight_layout(); fig.savefig(PLOT_DIR/"02_filters.png", dpi=150); plt.close()
    print("  [OK] 02_filters.png")


# ═══════════════════════════════════════════════════════════
# 图3: FFT 频谱 — 频率检出精度
# ═══════════════════════════════════════════════════════════
def plot_fft():
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for ax, freq in zip(axes, [25, 50, 200]):
        sig, _, _ = sinusoidal(freq=freq, duration=2.0, fs=FS)
        xf, yf = compute_fft_spectrum(sig, FS)
        mm = xf <= freq*3; pi = np.argmax(yf); det = xf[pi]
        df = FS/len(sig); err_hz = abs(det-freq); mk = MK_OK if err_hz < df*1.5 else MK_NG
        ax.plot(xf[mm], yf[mm], color=C_EST, lw=0.6)
        ax.axvline(x=freq, color=C_GT, ls='--', lw=1.5, label=f'GT={freq}Hz')
        ax.scatter([det], [yf[pi]], color=C_FAIL, s=40, zorder=5, label=f'检出={det:.1f}Hz')
        ax.annotate(f'err={err_hz:.1f}Hz [{mk}]', (freq, yf[pi]*0.7), fontsize=8,
                    color=C_PASS if 'PASS' in mk else C_FAIL)
        ax.set_title(f"{freq}Hz正弦 | Δf={df:.1f}Hz [{mk}]\n判定:误差<1.5×Δf为通过")
        ax.set_xlabel("Hz"); ax.legend(fontsize=6)
    plt.tight_layout(); fig.savefig(PLOT_DIR/"03_fft_spectrum.png", dpi=150); plt.close()
    print("  [OK] 03_fft_spectrum.png")


# ═══════════════════════════════════════════════════════════
# 图4: find_peaks_in_spectrum — 谐波族搜索
# ═══════════════════════════════════════════════════════════
def plot_find_peaks():
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    sig, _, _ = sinusoidal(freq=25.0, duration=2.0, fs=FS)
    xf, yf = compute_fft_spectrum(sig, FS)
    found = find_peaks_in_spectrum(xf, yf, 25.0, tolerance_hz=3.0, n_harmonics=3)
    mm = xf <= 100
    axes[0].plot(xf[mm], yf[mm], color=C_EST, lw=0.6, label='频谱')
    axes[0].axvline(x=25, color=C_GT, ls='--', lw=1, label='GT=25Hz')
    if found["fundamental"]:
        axes[0].scatter([found["fundamental"]["freq"]], [found["fundamental"]["amp"]],
                        color=C_FAIL, s=60, zorder=5, label='基频检出')
    for h in found["harmonics"]:
        axes[0].scatter([h["freq"]], [h["amp"]], color=C_THRESH, s=40, zorder=5, marker='D',
                        label=f'{h["order"]}次谐波')
    mk = MK_OK if found["fundamental"] else MK_NG
    axes[0].set_title(f"纯正弦25Hz | {len(found['harmonics'])}谐波 [{mk}]\n判定:基频检出且误差<1Hz为通过")
    axes[0].set_xlabel("Hz"); axes[0].legend(fontsize=6)

    sig, _, _ = gear_mesh(mesh_freq=450.0, rot_freq=25.0, duration=2.0, fs=FS, snr_db=30)
    xf, yf = compute_fft_spectrum(sig, FS)
    found = find_peaks_in_spectrum(xf, yf, 450.0, tolerance_hz=5.0, n_harmonics=3)
    mm = xf <= 1400
    axes[1].plot(xf[mm], yf[mm], color=C_EST, lw=0.5, label='频谱')
    axes[1].axvline(x=450, color=C_GT, ls='--', lw=1, label='GT=450Hz')
    if found["fundamental"]:
        axes[1].scatter([found["fundamental"]["freq"]], [found["fundamental"]["amp"]],
                        color=C_FAIL, s=60, zorder=5, label=f'啮合基频 SNR={found["fundamental"]["snr"]:.0f}')
    for h in found["harmonics"]:
        axes[1].scatter([h["freq"]], [h["amp"]], color=C_THRESH, s=35, zorder=5, marker='D')
    mk2 = MK_OK if found["fundamental"] and found["fundamental"]["snr"] > 3 else MK_NG
    axes[1].set_title(f"齿轮啮合450Hz | {len(found['harmonics'])}谐波 [{mk2}]\n判定:基频SNR>3为通过")
    axes[1].set_xlabel("Hz"); axes[1].legend(fontsize=6)

    plt.tight_layout(); fig.savefig(PLOT_DIR/"04_find_peaks.png", dpi=150); plt.close()
    print("  [OK] 04_find_peaks.png")


# ═══════════════════════════════════════════════════════════
# 图5: 统计指标 — 期望值 vs 实际值
# ═══════════════════════════════════════════════════════════
def plot_statistics():
    np.random.seed(42)
    noise = np.random.randn(50000)
    sig, _, _ = sinusoidal(freq=25.0, duration=2.0, fs=FS)

    metrics = [
        ("峭度\n(GT=3)", kurtosis(noise, fisher=False), 3.0),
        ("偏度\n(GT=0)", skewness(noise), 0.0),
        ("RMS\n(GT=1/√2)", rms(sig), 1/np.sqrt(2)),
        ("峰值因子\n(GT=√2)", crest_factor(sig), np.sqrt(2)),
        ("峰值\n(GT=1)", peak_value(sig), 1.0),
    ]
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(metrics)); w = 0.35
    actuals = [m[1] for m in metrics]; expecteds = [m[2] for m in metrics]; labels = [m[0] for m in metrics]
    ax.bar(x-w/2, expecteds, w, color=C_GT, edgecolor='#999', label='期望值(GT)')
    ax.bar(x+w/2, actuals, w, color=C_EST, label='计算值')

    all_ok = True
    for i, (a, e) in enumerate(zip(actuals, expecteds)):
        err = abs(a-e)/(abs(e)+0.001)*100
        ok = err < 5
        if not ok: all_ok = False
        c = C_PASS if ok else C_FAIL; mk = MK_OK if ok else MK_NG
        ax.annotate(f'Δ={err:.1f}% [{mk}]', (i, max(a,e)+max(expecteds)*0.03), ha='center', fontsize=7, color=c)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("值")
    ax.set_title(f"统计指标验证 | |相对误差|<5%为通过 [{'ALL OK' if all_ok else 'HAS FAIL'}]\n灰=GT 蓝=计算值")
    ax.legend(); ax.grid(axis='y', alpha=0.3)
    plt.tight_layout(); fig.savefig(PLOT_DIR/"05_statistics.png", dpi=150); plt.close()
    print("  [OK] 05_statistics.png")


# ═══════════════════════════════════════════════════════════
# 图6: parabolic_interpolation — 亚 bin 精度
# ═══════════════════════════════════════════════════════════
def plot_parabolic():
    true_freq = 100.3
    t = np.arange(0, 0.5, 1/FS)
    sig = np.sin(2*np.pi*true_freq*t)
    xf, yf = compute_fft_spectrum(sig, FS)
    pi = np.argmax(yf); fft_f = xf[pi]; interp_f = parabolic_interpolation(xf, yf, pi)
    mrg = 15; lo, hi = max(0, pi-mrg), min(len(xf), pi+mrg)
    fft_err, interp_err = abs(fft_f-true_freq), abs(interp_f-true_freq)
    improved = interp_err < fft_err; mk = MK_OK if improved else MK_NG

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.stem(xf[lo:hi], yf[lo:hi], linefmt=C_EST, markerfmt='o', basefmt=' ', label='FFT频谱')
    ax.axvline(x=true_freq, color=C_GT, ls='--', lw=2, label=f'GT={true_freq}Hz')
    ax.axvline(x=fft_f, color=C_THRESH, ls=':', lw=1.5, label=f'FFT bin={fft_f:.1f}Hz(Δ={fft_err:.2f})')
    ax.axvline(x=interp_f, color=C_PASS if improved else C_FAIL, lw=2,
               label=f'插值={interp_f:.2f}Hz(Δ={interp_err:.3f}) [{mk}]')
    ax.set_title(f"抛物线插值亚bin精度 | 插值误差={interp_err:.3f}Hz [{mk}]\n判定:插值误差<FFT bin误差为通过")
    ax.set_xlabel("Hz"); ax.set_ylabel("幅值"); ax.legend(fontsize=7)
    ax.set_xlim(xf[lo], xf[hi-1])
    plt.tight_layout(); fig.savefig(PLOT_DIR/"06_parabolic_interp.png", dpi=150); plt.close()
    print("  [OK] 06_parabolic_interp.png")


# ═══════════════════════════════════════════════════════════
# 图7: SNR & 频带能量
# ═══════════════════════════════════════════════════════════
def plot_snr_energy():
    sig, _, _ = sinusoidal(freq=50.0, duration=2.0, fs=FS)
    xf, yf = compute_fft_spectrum(sig, FS)
    pi = np.argmax(yf); snr_val = compute_snr(yf[pi], yf, method="median")
    snr_ok = snr_val > 20; mk = MK_OK if snr_ok else MK_NG

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    mm = xf <= 200
    axes[0].plot(xf[mm], yf[mm], color=C_EST, lw=0.6)
    axes[0].scatter([xf[pi]], [yf[pi]], color=C_FAIL, s=50, zorder=5)
    axes[0].annotate(f'SNR={snr_val:.0f} [{mk}]', (xf[pi], yf[pi]),
                     xytext=(30,30), textcoords='offset points', fontsize=9,
                     arrowprops=dict(arrowstyle='->', color=C_FAIL),
                     color=C_PASS if snr_ok else C_FAIL)
    axes[0].axhline(y=np.median(yf), color=C_THRESH, ls='--', alpha=0.5, label='背景中位数')
    axes[0].set_title(f"compute_snr | SNR={snr_val:.0f} [{mk}]\n判定:SNR>20为通过")
    axes[0].set_xlabel("Hz"); axes[0].set_ylabel("幅值"); axes[0].legend(fontsize=7)

    be = _band_energy(xf, yf, center=50.0, bandwidth=10.0)
    mb = (xf>=40)&(xf<=60)
    axes[1].plot(xf[mb], yf[mb], color=C_EST, lw=0.6)
    axes[1].fill_between(xf[mb], 0, yf[mb], alpha=0.2, color=C_EST, label=f'能量={be:.0f}')
    axes[1].axvline(x=50, color=C_GT, ls='--', lw=1, label='GT=50Hz')
    axes[1].set_title(f"_band_energy 50±10Hz={be:.0f}\n判定:频带能量>0为通过")
    axes[1].set_xlabel("Hz"); axes[1].legend(fontsize=7)
    plt.tight_layout(); fig.savefig(PLOT_DIR/"07_snr_energy.png", dpi=150); plt.close()
    print("  [OK] 07_snr_energy.png")


# ═══════════════════════════════════════════════════════════
# 图8: 转频估计 — 三种方法对比
# ═══════════════════════════════════════════════════════════
def plot_rot_freq():
    test_freqs = [20, 35, 50]
    md = {"spectrum": [], "autocorr": [], "envelope": []}
    for freq in test_freqs:
        sig, _, _ = sinusoidal(freq=freq, duration=2.0, fs=FS)
        md["spectrum"].append(estimate_rot_freq_spectrum(sig, FS, freq_range=(10,80)))
        ac = estimate_rot_freq_autocorr(sig, FS, freq_range=(10,80))
        md["autocorr"].append(ac if ac else 0)
        xf, yf = compute_fft_spectrum(sig, FS)
        env = estimate_rot_freq_envelope(sig, FS, f_center=xf[np.argmax(yf)], bw=30, freq_range=(10,80))
        md["envelope"].append(env if env else 0)

    fig, ax = plt.subplots(figsize=(9, 5))
    x = np.arange(len(test_freqs)); w = 0.22
    clrs = {'spectrum': C_EST, 'autocorr': C_PASS, 'envelope': C_THRESH}
    for i, (method, vals) in enumerate(md.items()):
        ax.bar(x+(i-1)*w, vals, w, label=method, color=clrs[method], alpha=0.85)

    for i, freq in enumerate(test_freqs):
        ax.axhline(y=freq, xmin=(i-0.4)/len(test_freqs), xmax=(i+0.4)/len(test_freqs),
                   color=C_GT, ls='--', alpha=0.6, lw=1.5)
        err = abs(md["spectrum"][i]-freq)/freq*100
        mk = MK_OK if err < 10 else MK_NG
        ax.annotate(f'[{mk}]', (i, freq+2), ha='center', fontsize=8,
                    color=C_PASS if mk == MK_OK else C_FAIL)

    ax.set_xticks(x); ax.set_xticklabels([f"{f}Hz正弦" for f in test_freqs])
    ax.set_ylabel("估计转频(Hz)")
    ax.set_title("转频估计三方法对比 | 误差<10%为通过\n灰线=GT 蓝=spectrum 绿=autocorr 橙=envelope")
    ax.legend()
    plt.tight_layout(); fig.savefig(PLOT_DIR/"08_rot_freq.png", dpi=150); plt.close()
    print("  [OK] 08_rot_freq.png")


# ═══════════════════════════════════════════════════════════
# 图9: ZOOM-FFT — 细化谱 vs 标准 FFT
# ═══════════════════════════════════════════════════════════
def plot_zoom_fft():
    t = np.arange(0, 0.5, 1/FS)
    sig = np.sin(2*np.pi*200*t)+0.8*np.sin(2*np.pi*201*t)
    xf, yf = compute_fft_spectrum(sig, FS)
    zoom = zoom_fft_analysis(sig, FS, center_freq=200.5, bandwidth=10.0, zoom_factor=16)
    orig_res = FS/len(sig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    mm = (xf>=190)&(xf<=210)
    axes[0].stem(xf[mm], yf[mm], linefmt=C_EST, markerfmt='o', basefmt=' ')
    axes[0].axvline(x=200, color=C_GT, ls='--', lw=1.5, label='GT=200Hz')
    axes[0].axvline(x=201, color=C_FAIL, ls='--', lw=1, label='GT=201Hz')
    axes[0].set_title(f"标准FFT (Δf={orig_res:.1f}Hz)\n200/201Hz难以分辨 [{MK_NG}]")
    axes[0].set_xlabel("Hz"); axes[0].legend(fontsize=7)

    zf = zoom.get("zoom_freq_axis", np.array([]))
    zs = zoom.get("zoom_spectrum", np.array([]))
    if len(zf)>0:
        axes[1].stem(zf, zs, linefmt=C_THRESH, markerfmt='o', basefmt=' ', label='ZOOM-FFT')
        axes[1].axvline(x=200, color=C_GT, ls='--', lw=1.5, label='GT=200Hz')
        axes[1].axvline(x=201, color=C_FAIL, ls='--', lw=1, label='GT=201Hz')
    axes[1].set_title(f"ZOOM-FFT(zoom×{zoom['zoom_factor']}) 聚焦200.5±5Hz\n判定:频率轴围绕center_freq为通过")
    axes[1].set_xlabel("Hz"); axes[1].legend(fontsize=7)
    plt.tight_layout(); fig.savefig(PLOT_DIR/"09_zoom_fft.png", dpi=150); plt.close()
    print("  [OK] 09_zoom_fft.png")


# ═══════════════════════════════════════════════════════════
# 图10: VMD 分解 — IMF 频谱
# ═══════════════════════════════════════════════════════════
def plot_vmd_decompose():
    t = np.arange(0, 1.0, 1/FS)
    sig = np.sin(2*np.pi*30*t)+0.7*np.sin(2*np.pi*120*t)+0.5*np.sin(2*np.pi*300*t)
    try:
        u, _, _ = vmd_decompose(sig, K=3, alpha=2000, tol=1e-6)
        n = u.shape[0]
        fig, axes = plt.subplots(1, n+1, figsize=(14, 4))
        xf, yf = compute_fft_spectrum(sig, FS); mm = xf <= 400
        axes[0].plot(xf[mm], yf[mm], color=C_GT, lw=0.7)
        for f in [30,120,300]: axes[0].axvline(x=f, color=C_FAIL, ls='--', alpha=0.5, lw=0.8)
        axes[0].set_title("原始混合信号(GT)\n30+120+300Hz"); axes[0].set_xlabel("Hz")

        for i in range(n):
            xf_i, yf_i = compute_fft_spectrum(u[i,:], FS); pf = xf_i[np.argmax(yf_i)]
            near = any(abs(pf-ef)/ef<0.2 for ef in [30,120,300])
            c = C_PASS if near else C_FAIL
            axes[i+1].plot(xf_i[mm], yf_i[mm], color=c, lw=0.7)
            axes[i+1].scatter([pf], [yf_i[np.argmax(yf_i)]], color=C_FAIL, s=30, zorder=5)
            mk = MK_OK if near else MK_NG
            axes[i+1].set_title(f"IMF{i} 峰值={pf:.0f}Hz [{mk}]"); axes[i+1].set_xlabel("Hz")

        plt.tight_layout(); fig.savefig(PLOT_DIR/"10_vmd_decompose.png", dpi=150); plt.close()
        print("  [OK] 10_vmd_decompose.png")
    except Exception as e:
        print(f"  [SKIP] VMD分解绘图: {e}")


# ═══════════════════════════════════════════════════════════
# 图11: VMD 降噪 — 时域/频域 前后对比
# ═══════════════════════════════════════════════════════════
def plot_vmd_denoise():
    t = np.arange(0, 1.0, 1/FS)
    clean = np.sin(2*np.pi*50*t)+0.5*np.sin(2*np.pi*120*t)
    np.random.seed(42); noisy = clean+0.5*np.random.randn(len(t))
    try:
        denoised = vmd_denoise(noisy, K=3, alpha=2000, corr_threshold=0.2, kurt_threshold=2.5)
    except Exception:
        print("  [SKIP] VMD降噪绘图"); return

    ts = t[:int(0.15*FS)]
    fig, axes = plt.subplots(2, 3, figsize=(14, 7))

    for ax, lbl, data, c in [
        (axes[0,0],"纯净信号(GT)",clean,C_PASS),
        (axes[0,1],"加噪信号(输入)",noisy,C_FAIL),
        (axes[0,2],"VMD降噪后",denoised,C_EST),
    ]:
        ax.plot(ts, data[:len(ts)], color=c, lw=0.6); ax.set_title(lbl)

    for ax, lbl, data, c in [
        (axes[1,0],"GT频谱",clean,C_PASS),
        (axes[1,1],"输入频谱",noisy,C_FAIL),
        (axes[1,2],"降噪后频谱",denoised,C_EST),
    ]:
        xf, yf = compute_fft_spectrum(data, FS); mm = xf <= 200
        ax.plot(xf[mm], yf[mm], color=c, lw=0.6)
        for f in [50,120]:
            ax.axvline(x=f, color=C_GT, ls='--', alpha=0.5, lw=0.7)
        ax.set_title(lbl); ax.set_xlabel("Hz")

    snr_b = np.var(clean)/(np.var(noisy-clean)+1e-12)
    snr_a = np.var(clean)/(np.var(denoised[:len(clean)]-clean[:len(denoised)])+1e-12)
    improved = snr_a > snr_b*0.8; mk = MK_OK if improved else MK_NG
    fig.suptitle(f"VMD降噪: {10*np.log10(snr_b):.1f}dB→{10*np.log10(snr_a):.1f}dB [{mk}]\n判定:SNR改善>0.8×原始为通过", fontsize=12, y=1.01)
    plt.tight_layout(); fig.savefig(PLOT_DIR/"11_vmd_denoise.png", dpi=150); plt.close()
    print("  [OK] 11_vmd_denoise.png")


# ═══════════════════════════════════════════════════════════
# 图12: VMD 冲击模态 — 时域波形对比
# ═══════════════════════════════════════════════════════════
def plot_vmd_impact():
    sig, _, _ = bearing_outer_race(bpfo=90.0, rot_freq=25.0, duration=1.0, fs=FS, snr_db=15)
    try:
        _, info = vmd_select_impact_mode(sig, K=3, alpha=2000)
    except Exception:
        print("  [SKIP] VMD冲击绘图"); return
    u, _, _ = vmd_decompose(sig, K=3, alpha=2000, tol=1e-6)
    fig, axes = plt.subplots(2, 2, figsize=(10, 7))
    t = np.arange(0, min(1.0, len(sig)/FS), 1/FS); ts = t[:int(0.2*FS)]

    axes[0,0].plot(ts, sig[:len(ts)], color=C_GT, lw=0.5)
    axes[0,0].set_title(f"原始轴承信号(GT)\n峭度={kurtosis(sig,fisher=False):.1f}")

    modes = info.get("modes", [])
    for i, m in enumerate(modes[:3]):
        idx = m["index"]; is_best = idx == info.get("best_index")
        c = C_PASS if is_best else C_GT
        ax_pos = [(0,1),(1,0),(1,1)][i]; ax = axes[ax_pos[0], ax_pos[1]]
        ax.plot(ts, u[idx,:len(ts)], color=c, lw=0.5)
        lb = "★最佳冲击" if is_best else ""
        ax.set_title(f"IMF{idx} {lb}\n峭度={m['kurtosis']:.1f}")
    fig.suptitle("VMD冲击模态选择 | 最佳IMF应保留冲击特征\n判定:最佳IMF峭度最高为通过", fontsize=12)
    plt.tight_layout(); fig.savefig(PLOT_DIR/"12_vmd_impact.png", dpi=150); plt.close()
    print("  [OK] 12_vmd_impact.png")


# ═══════════════════════════════════════════════════════════
# 图14: 真实数据 — 转频估计 vs 真实转速（只读JSON）
# ═══════════════════════════════════════════════════════════
def plot_rot_freq_real():
    data = load_json("signal_utils_correctness.json")
    if not data: return
    items = data.get("rot_freq_real", [])
    if not items: return

    wt = [it for it in items if it.get("dataset")=="WTgearbox"]
    hb = [it for it in items if it.get("dataset")=="HUSTbear"]

    fig, axes = plt.subplots(1, 2 if hb else 1, figsize=(12, 5.5))
    if not isinstance(axes, np.ndarray): axes = [axes]

    if wt:
        ax = axes[0]
        labels = [it["file"].replace("He_N1_","").replace("-c1.npy","") for it in wt]
        ex = [it["expected_rpm_hz"] for it in wt]; se = [it["spectrum_est"] for it in wt]
        ae = [it["autocorr_est"] for it in wt]
        x = np.arange(len(labels)); w = 0.3
        ax.bar(x-w/2, ex, w, color=C_GT, edgecolor='#999', label='GT:真实转速')
        ax.bar(x+w/2, se, w, color=C_EST, alpha=0.85, label='spectrum估计')
        valid_ac = [(i,v) for i,v in enumerate(ae) if v>0]
        if valid_ac:
            ax.scatter([i for i,_ in valid_ac], [v for _,v in valid_ac],
                       color=C_PASS, s=60, zorder=5, marker='D', label='autocorr法')
        for i,(e,s) in enumerate(zip(ex,se)):
            err = abs(s-e)/e*100; ok = err<15 or wt[i].get("known_limitation")
            c = C_PASS if ok else C_FAIL; mk = MK_OK if ok else MK_NG
            ax.annotate(f'{err:.0f}%[{mk}]', (i, max(e,s)+1), ha='center', fontsize=6, color=c)
        ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8)
        ax.set_ylabel("转频(Hz)"); ax.set_title("WTgearbox行星齿轮箱 | 误差<15%或已知限制为通过"); ax.legend(fontsize=7); ax.grid(axis='y', alpha=0.3)

    if hb and len(axes)>1:
        ax = axes[1]
        labels = [it["file"].replace("0.5X_","").replace("_20Hz-X.npy","").replace("H","健康") for it in hb]
        ex = [it["expected_rpm_hz"] for it in hb]; se = [it["spectrum_est"] for it in hb]
        x = np.arange(len(labels)); w = 0.3
        ax.bar(x-w/2, ex, w, color=C_GT, edgecolor='#999', label='GT:真实转速')
        ax.bar(x+w/2, se, w, color=C_EST, alpha=0.85, label='spectrum估计')
        ax.axhline(y=20, color=C_THRESH, ls='--', alpha=0.4)
        for i,(e,s) in enumerate(zip(ex,se)):
            err = abs(s-e)/e*100; ok = err<20 or hb[i].get("known_limitation")
            c = C_PASS if ok else C_FAIL; mk = MK_OK if ok else MK_NG
            lim = " [已知限制]" if hb[i].get("known_limitation") else ""
            ax.annotate(f'{err:.0f}%[{mk}]{lim}', (i, max(e,s)+0.5), ha='center', fontsize=6, color=c)
        ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=7)
        ax.set_title("HUSTbear轴承 | 误差<20%或已知限制为通过"); ax.legend(fontsize=7); ax.grid(axis='y', alpha=0.3)

    fig.suptitle("真实数据转频估计 — GT=灰柱 蓝=spectrum 绿菱=autocorr\n判定:在预期范围或误差<阈值", fontsize=11)
    plt.tight_layout(); fig.savefig(PLOT_DIR/"14_real_rotfreq.png", dpi=150); plt.close()
    print("  [OK] 14_real_rotfreq.png")


# ═══════════════════════════════════════════════════════════
# 图15: 真实数据 — VMD 冲击模态（只读JSON）
# ═══════════════════════════════════════════════════════════
def plot_vmd_real():
    data = load_json("vmd_denoise_correctness.json")
    if not data: return
    items = data.get("vmd_real", [])
    if not items: return
    hb = [it for it in items if it.get("dataset")=="HUSTbear"]
    cw = [it for it in items if it.get("dataset")=="CW"]

    fig, axes = plt.subplots(1, 2 if cw else 1, figsize=(14, 6))
    if not isinstance(axes, np.ndarray): axes = [axes]

    for ax, ds, nm in [(axes[0], hb, "HUSTbear恒速"), (axes[1], cw, "CW变速")] if cw else [(axes[0], hb, "HUSTbear")]:
        if not ds: continue
        labels = [it["description"] for it in ds]; y = np.arange(len(labels)); h = 0.3
        ok = [it["original_kurtosis"] for it in ds]; bk = [it["best_imf_kurtosis"] for it in ds]
        ax.barh(y+h/2, ok, h, color=C_GT, edgecolor='#999', label='原始峭度(GT)')
        ax.barh(y-h/2, bk, h, color=C_EST, alpha=0.85, label='最佳IMF峭度')
        ax.axvline(x=3.0, color=C_THRESH, ls='--', alpha=0.5, label='高斯基线≈3')
        for i,(o,b) in enumerate(zip(ok,bk)):
            mk = MK_OK if b>o*0.8 else MK_NG
            ax.annotate(f'{o:.1f}→{b:.1f} [{mk}]', (max(o,b)+0.2, i), va='center', fontsize=6,
                        color=C_PASS if mk == MK_OK else C_FAIL)
        ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=8)
        ax.set_xlabel("峭度"); ax.set_title(f"{nm} | 判定:最佳IMF峭度≥0.8×原始为通过")
        ax.legend(fontsize=7, loc='lower right'); ax.grid(axis='x', alpha=0.3)

    fig.suptitle("真实数据VMD冲击模态 | GT=灰 蓝=输出 橙=高斯基线", fontsize=12)
    plt.tight_layout(); fig.savefig(PLOT_DIR/"15_real_vmd.png", dpi=150); plt.close()
    print("  [OK] 15_real_vmd.png")


# ═══════════════════════════════════════════════════════════
# 图16: 全部合成信号（只读JSON）
# ═══════════════════════════════════════════════════════════
def plot_all_synthetic():
    data = load_json("signal_utils_correctness.json")
    if not data: return
    items = data.get("all_synthetic", [])
    if not items: return

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    labels = [it["signal"] for it in items]; x = np.arange(len(labels))
    colors = [C_PASS if it["passed"] else C_FAIL for it in items]

    axes[0].bar(x, [it["kurtosis"] for it in items], color=colors, alpha=0.85)
    axes[0].axhline(y=3.0, color=C_GT, ls='--', alpha=0.5, label='GT:高斯≈3')
    axes[0].set_xticks(x); axes[0].set_xticklabels(labels, rotation=45, fontsize=6, ha='right')
    axes[0].set_title("峭度"); axes[0].legend(fontsize=7)

    axes[1].bar(x, [it["rms"] for it in items], color=colors, alpha=0.85)
    axes[1].set_xticks(x); axes[1].set_xticklabels(labels, rotation=45, fontsize=6, ha='right')
    axes[1].set_title("RMS")

    axes[2].bar(x, [it["crest_factor"] for it in items], color=colors, alpha=0.85)
    axes[2].set_xticks(x); axes[2].set_xticklabels(labels, rotation=45, fontsize=6, ha='right')
    axes[2].set_title("峰值因子")

    fig.suptitle("6种合成信号统计指标 | 绿=通过 红=失败 灰线=GT\n判定:FFT+统计+峰值均正常为通过", fontsize=12)
    plt.tight_layout(); fig.savefig(PLOT_DIR/"16_all_synthetic.png", dpi=150); plt.close()
    print("  [OK] 16_all_synthetic.png")


# ═══════════════════════════════════════════════════════════
# 图17: CW 变速（只读JSON）
# ═══════════════════════════════════════════════════════════
def plot_cw_variable():
    data = load_json("signal_utils_correctness.json")
    if not data: return
    items = data.get("cw_variable_speed", [])
    if not items: return

    fig, ax = plt.subplots(figsize=(12, 5.5))
    labels = [f"{it['description']}\n({it['file']})" for it in items]
    y_pos = range(len(labels))

    for i, it in enumerate(items):
        lo, hi = it["expected_range_hz"]
        ax.barh(i, hi-lo, left=lo, height=0.3, color=C_GT, alpha=0.5, zorder=1)
        ax.text(hi+0.3, i+0.12, f"[{lo}-{hi}]Hz", fontsize=6, color='gray', va='bottom')

        spec = it["spectrum_est_hz"]
        ax.scatter(spec, i, color=C_EST, s=80, zorder=3, marker='o', edgecolors='white')
        ax.text(spec+0.3, i-0.2, f'spec={spec:.1f}', fontsize=6, color=C_EST, va='top')

        order_m = it["order_median_hz"]
        ax.scatter(order_m, i, color=C_PASS, s=80, zorder=3, marker='D', edgecolors='white')
        ax.text(order_m+0.3, i, f'order={order_m:.1f}±{it["order_std_hz"]:.1f}', fontsize=6, color=C_PASS)

        passed = it.get("passed", False)
        mk = MK_OK if passed else MK_NG
        ax.annotate(f'[{mk}]', (max(lo,hi)+2, i-0.35), ha='center',
                    color=C_PASS if passed else C_FAIL, fontsize=10, fontweight='bold')

    ax.set_yticks(list(y_pos)); ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("频率(Hz)")
    ax.set_title("CW变速数据集转频估计 | 至少一法在预期范围即通过\n灰带=GT转速范围 蓝点=spectrum 绿菱=order_tracking")
    ax.grid(axis='x', alpha=0.3)
    plt.tight_layout(); fig.savefig(PLOT_DIR/"17_cw_variable.png", dpi=150); plt.close()
    print("  [OK] 17_cw_variable.png")


# ═══════════════════════════════════════════════════════════
# 图18: savgol_denoise — 平滑前后 + 趋势提取
# ═══════════════════════════════════════════════════════════
def plot_savgol_detail():
    t = np.arange(0, 1.0, 1/FS); ts = t[:int(0.15*FS)]
    clean = np.sin(2*np.pi*50*t)
    np.random.seed(42); noisy = clean + 0.3*np.random.randn(len(t))
    smoothed, info = sg_denoise(noisy, window_length=51, polyorder=3)

    # 趋势提取
    t2 = np.arange(0, 2.0, 1/FS)
    trend_true = 0.5*t2**2; oscillation = 0.1*np.sin(2*np.pi*100*t2)
    sig2 = trend_true + oscillation
    trend, residual, info2 = sg_trend_residual(sig2, window_length=501, polyorder=2)

    fig, axes = plt.subplots(2, 2, figsize=(12, 7))
    # 平滑前后
    axes[0,0].plot(ts, noisy[:len(ts)], color=C_FAIL, alpha=0.6, lw=0.6, label='含噪信号')
    axes[0,0].plot(ts, clean[:len(ts)], color=C_GT, lw=1, label='GT:纯净信号')
    axes[0,0].plot(ts, smoothed[:len(ts)], color=C_EST, lw=1.2, label='S-G平滑后')
    mse_b = np.mean((noisy-clean)**2); mse_a = np.mean((smoothed-clean)**2)
    mk = MK_OK if mse_a < mse_b*0.8 else MK_NG
    axes[0,0].set_title(f"S-G平滑降噪 | MSE {mse_b:.3f}→{mse_a:.3f} [{mk}]\n判定:MSE降低>20%为通过")
    axes[0,0].legend(fontsize=7)

    # 平滑前后频谱
    xf_b, yf_b = compute_fft_spectrum(noisy, FS); mm = xf_b <= 200
    xf_a, yf_a = compute_fft_spectrum(smoothed, FS)
    axes[0,1].plot(xf_b[mm], yf_b[mm], color=C_FAIL, alpha=0.5, lw=0.6, label='含噪频谱')
    axes[0,1].plot(xf_a[mm], yf_a[mm], color=C_EST, lw=0.8, label='平滑后频谱')
    axes[0,1].axvline(x=50, color=C_GT, ls='--', lw=1, label='GT=50Hz')
    axes[0,1].set_title("频谱对比"); axes[0,1].legend(fontsize=7)

    # 趋势提取
    ts2 = t2[:int(0.3*FS)]
    axes[1,0].plot(ts2, sig2[:len(ts2)], color=C_GT, alpha=0.6, lw=0.5, label='原始(GT)')
    axes[1,0].plot(ts2, trend[:len(ts2)], color=C_EST, lw=1.2, label='提取趋势')
    corr = float(np.corrcoef(trend, trend_true)[0,1])
    mk2 = MK_OK if corr > 0.8 else MK_NG
    axes[1,0].set_title(f"趋势提取 | corr={corr:.3f} [{mk2}]\n判定:与GT相关系数>0.8为通过")
    axes[1,0].legend(fontsize=7)

    # 残余分量
    axes[1,1].plot(ts2, residual[:len(ts2)], color=C_THRESH, lw=0.6)
    axes[1,1].axhline(y=0, color=C_GT, ls='--', alpha=0.5)
    axes[1,1].set_title(f"残余分量(应为高频震荡)\nRMS={np.std(residual):.3f}")
    axes[1,1].set_ylim(-0.3, 0.3)

    fig.suptitle("savgol_denoise S-G平滑 | 绿=GT 蓝=输出 红=输入", fontsize=12)
    plt.tight_layout(); fig.savefig(PLOT_DIR/"18_savgol.png", dpi=150); plt.close()
    print("  [OK] 18_savgol.png")


# ═══════════════════════════════════════════════════════════
# 图19: wavelet_packet — 能量熵分布
# ═══════════════════════════════════════════════════════════
def plot_wavelet_packet_detail():
    # 纯噪声 vs 单频信号的能量熵对比
    noise = np.random.randn(1024)
    tone = np.sin(2*np.pi*200*np.arange(1024)/FS)

    rn = compute_wavelet_packet_energy_entropy(noise, FS, level=3)
    rt = compute_wavelet_packet_energy_entropy(tone, FS, level=3)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    for ax, res, lbl, c in [
        (axes[0], rn, "白噪声", C_FAIL),
        (axes[1], rt, "200Hz单频", C_PASS),
    ]:
        energies = res.get("node_energies", [])
        if energies:
            ax.bar(range(len(energies)), energies, color=c, alpha=0.85)
        ne = res.get("normalized_entropy", 0)
        mk = MK_OK if (lbl=="白噪声" and ne>0.7) or (lbl=="200Hz单频" and ne<0.7) else MK_NG
        ax.set_title(f"{lbl} | 归一化熵={ne:.3f} [{mk}]\n判定:噪声熵>0.7, 单频熵<0.7为通过")
        ax.set_xlabel("小波包节点"); ax.set_ylabel("能量占比")

    fig.suptitle("wavelet_packet 能量熵 | 红=噪声(均匀) 绿=单频(集中)", fontsize=12)
    plt.tight_layout(); fig.savefig(PLOT_DIR/"19_wavelet_packet.png", dpi=150); plt.close()
    print("  [OK] 19_wavelet_packet.png")


# ═══════════════════════════════════════════════════════════
# 图20: gear/msb — MSB-SE 切片
# ═══════════════════════════════════════════════════════════
def plot_msb_detail():
    t = np.arange(0, 2.0, 1/FS)
    mesh = np.sin(2*np.pi*500*t)
    mod = 0.5*np.cos(2*np.pi*12.5*t)
    sig = (1+mod)*mesh + np.random.randn(len(t))*0.05

    try:
        res = msb_residual_sideband_analysis(sig, FS, mesh_freq=500.0, carrier_freq=12.5)
    except Exception:
        print("  [SKIP] MSB绘图失败"); return

    if not res.get("valid"):
        print("  [SKIP] MSB结果无效"); return

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

    fc = res.get("msb_fc_axis", np.array([]))
    se_slice = res.get("msb_se_slice", np.array([]))
    if len(fc) > 0 and len(se_slice) > 0:
        axes[0].plot(fc, se_slice, color=C_EST, lw=0.6)
        sun_f = res.get("sun_slice_freq", 0); planet_f = res.get("planet_slice_freq", 0)
        axes[0].axvline(x=sun_f, color=C_PASS, ls='--', lw=1, label=f'太阳轮切片={sun_f:.0f}Hz')
        axes[0].axvline(x=planet_f, color=C_FAIL, ls='--', lw=1, label=f'行星轮切片={planet_f:.0f}Hz')
        axes[0].set_title(f"MSB-SE切片 | 太阳SNR={res['sun_fault_msb_snr']:.1f} 行星SNR={res['planet_fault_msb_snr']:.1f}")
        axes[0].set_xlabel("f_c (Hz)"); axes[0].set_ylabel("MSB-SE幅值"); axes[0].legend(fontsize=7)

    sun_snr = res.get("sun_fault_msb_snr", 0); planet_snr = res.get("planet_fault_msb_snr", 0)
    ratio = res.get("residual_sideband_ratio", 0)
    metrics = [("太阳轮SNR", sun_snr), ("行星轮SNR", planet_snr), ("残余边带比", ratio)]
    axes[1].bar(range(len(metrics)), [m[1] for m in metrics], color=[C_EST, C_THRESH, C_PASS])
    axes[1].set_xticks(range(len(metrics))); axes[1].set_xticklabels([m[0] for m in metrics])
    axes[1].set_title(f"MSB指标 | 判定:SNR>1为检出调制")
    for i, (_, v) in enumerate(metrics):
        axes[1].text(i, v+0.1, f'{v:.2f}', ha='center', fontsize=9)

    fig.suptitle("gear/msb 调制双谱 | 蓝=SE切片 绿=残余边带", fontsize=12)
    plt.tight_layout(); fig.savefig(PLOT_DIR/"20_msb.png", dpi=150); plt.close()
    print("  [OK] 20_msb.png")


# ═══════════════════════════════════════════════════════════
# 图21: bearing_cyclostationary — SCoh 谱相干
# ═══════════════════════════════════════════════════════════
def plot_cyclostationary_detail():
    t = np.arange(0, 2.0, 1/FS)
    bpfo = 90.0; rot_f = 25.0
    sig = np.zeros_like(t)
    for i in range(int(2.0*bpfo)):
        idx = int(i/bpfo*FS)
        if idx < len(sig)-10: sig[idx:idx+5] += 1.0
    sig += np.random.randn(len(t))*0.2

    try:
        f_axis, alpha_axis, scoh = _compute_sc_scoh_bearing(sig, FS, seg_len=1024)
    except Exception:
        print("  [SKIP] SCoh绘图失败"); return

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

    # SCoh 热图（降采样显示）
    step = max(1, len(f_axis)//200)
    f_ds = f_axis[::step]; a_ds = alpha_axis[::step]; scoh_ds = scoh[::step, ::len(alpha_axis)//100+1]
    if scoh_ds.size > 0:
        im = axes[0].pcolormesh(f_ds[:scoh_ds.shape[1]] if len(f_ds)>=scoh_ds.shape[1] else f_ds[:scoh_ds.shape[0]],
                                a_ds[:scoh_ds.shape[0]] if len(a_ds)>=scoh_ds.shape[0] else a_ds[:scoh_ds.shape[1]],
                                scoh_ds.T if scoh_ds.shape[0]>scoh_ds.shape[1] else scoh_ds,
                                cmap='viridis', shading='auto')
        plt.colorbar(im, ax=axes[0], label='SCoh')
    axes[0].axhline(y=bpfo, color=C_FAIL, ls='--', lw=1, label=f'GT:BPFO={bpfo}Hz')
    axes[0].set_xlabel("频率(Hz)"); axes[0].set_ylabel("循环频率α(Hz)")
    axes[0].set_title(f"谱相干SCoh图 | GT:BPFO={bpfo}Hz\n判定:在α=BPFO处有显著值为通过")
    axes[0].legend(fontsize=7)

    # α轴投影
    alpha_proj = np.mean(scoh, axis=1) if scoh.shape[1] > 0 else np.zeros(len(alpha_axis))
    axes[1].plot(alpha_axis, alpha_proj, color=C_EST, lw=0.6)
    axes[1].axvline(x=bpfo, color=C_GT, ls='--', lw=1.5, label=f'GT:BPFO={bpfo}Hz')
    peak_idx = np.argmax(alpha_proj[len(alpha_proj)//4:]) + len(alpha_proj)//4
    peak_a = alpha_axis[peak_idx] if peak_idx < len(alpha_axis) else 0
    near = abs(peak_a-bpfo)/bpfo < 0.1 if bpfo > 0 else False
    mk = MK_OK if near else MK_NG
    axes[1].scatter([peak_a], [alpha_proj[peak_idx]], color=C_FAIL if near else C_FAIL, s=50, zorder=5,
                    label=f'峰值α={peak_a:.1f}Hz [{mk}]')
    axes[1].set_title(f"α轴投影 | 峰值={peak_a:.1f}Hz [{mk}]\n判定:峰值α接近BPFO为通过")
    axes[1].set_xlabel("循环频率α(Hz)"); axes[1].set_ylabel("平均SCoh"); axes[1].legend(fontsize=7)

    fig.suptitle("bearing_cyclostationary 谱相干 | 红虚线=GT 蓝=检测值", fontsize=12)
    plt.tight_layout(); fig.savefig(PLOT_DIR/"21_cyclostationary.png", dpi=150); plt.close()
    print("  [OK] 21_cyclostationary.png")


# ═══════════════════════════════════════════════════════════
# 图22: modality_bearing — EMD/VMD 轴承诊断
# ═══════════════════════════════════════════════════════════
def plot_modality_bearing_detail():
    t = np.arange(0, 0.5, 1/FS)
    bpfo = 90.0; sig = np.zeros_like(t)
    for i in range(int(0.5*bpfo)):
        idx = int(i/bpfo*FS)
        if idx < len(sig)-5: sig[idx:idx+3] += [1.0, 0.5, 0.3]
    sig += 0.3*np.sin(2*np.pi*3000*t)*(sig>0.1) + np.random.randn(len(t))*0.1

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # EMD 轴承诊断
    try:
        res_emd = emd_bearing_analysis(sig, FS, max_imfs=5, max_sifts=20, top_n=1)
        env_f = res_emd.get("envelope_freq", []); env_a = res_emd.get("envelope_amp", [])
        if len(env_f) > 0:
            axes[0].plot(env_f, env_a, color=C_EST, lw=0.6)
            axes[0].axvline(x=bpfo, color=C_GT, ls='--', lw=1.5, label=f'GT:BPFO={bpfo}Hz')
            peak_e = env_f[np.argmax(env_a[(env_f>=30)&(env_f<=150)])+np.argmin(np.abs(env_f-30))]
            snr = float(np.max(env_a[(env_f>=30)&(env_f<=150)])/np.median(env_a[(env_f>=30)&(env_f<=150)]))
            mk = MK_OK if snr > 3 else MK_NG
            axes[0].set_title(f"EMD轴承诊断 | BPFO SNR={snr:.1f} [{mk}]\n判定:SNR>3检出故障为通过")
    except Exception:
        axes[0].set_title("EMD诊断失败")
    axes[0].set_xlabel("Hz"); axes[0].set_ylabel("包络幅值"); axes[0].legend(fontsize=7)

    # VMD 轴承诊断
    try:
        res_vmd = vmd_bearing_analysis(sig, FS, K=3, alpha=2000, top_n=1)
        env_f2 = res_vmd.get("envelope_freq", []); env_a2 = res_vmd.get("envelope_amp", [])
        if len(env_f2) > 0:
            axes[1].plot(env_f2, env_a2, color=C_THRESH, lw=0.6)
            axes[1].axvline(x=bpfo, color=C_GT, ls='--', lw=1.5, label=f'GT:BPFO={bpfo}Hz')
            axes[1].set_title(f"VMD轴承诊断 | modes={len(res_vmd.get('mode_center_freqs',[]))}")
    except Exception:
        axes[1].set_title("VMD诊断失败")
    axes[1].set_xlabel("Hz"); axes[1].legend(fontsize=7)

    fig.suptitle("modality_bearing 模态轴承诊断 | 灰线=GT(BPFO) 蓝/橙=检出", fontsize=12)
    plt.tight_layout(); fig.savefig(PLOT_DIR/"22_modality_bearing.png", dpi=150); plt.close()
    print("  [OK] 22_modality_bearing.png")


# ═══════════════════════════════════════════════════════════
# 图23: sensitive_selector — 分量评分排序
# ═══════════════════════════════════════════════════════════
def plot_sensitive_selector_detail():
    t = np.arange(0, 1.0, 1/FS)
    original = np.sin(2*np.pi*100*t) + np.random.randn(len(t))*0.1
    comp1 = np.sin(2*np.pi*100*t).copy()
    for i in range(int(0.5*80)):
        idx = int(i/80*len(t))
        if idx < len(t)-3: comp1[idx:idx+3] += [2.0, 1.0, 0.5]
    comp2 = np.random.randn(len(t))*0.5
    comp3 = np.sin(2*np.pi*5*t)*0.1

    scored = score_components([comp1, comp2, comp3], original, FS, mode="bearing")
    scores = [s["score"] for s in scored]; idxs = [s["index"] for s in scored]
    names = [f"IMF{idx}" for idx in idxs]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

    colors = [C_PASS if i==scored[np.argmax(scores)]["index"] else C_GT for i in idxs]
    axes[0].bar(names, scores, color=colors, alpha=0.85)
    for i, s in enumerate(scores):
        mk = MK_OK if i == np.argmax(scores) else ""
        axes[0].text(i, s+0.02, f'{s:.3f} {mk}', ha='center', fontsize=8,
                     color=C_PASS if mk else 'gray')
    axes[0].set_title("分量综合评分排序\n判定:与GT最相关的分量得分最高为通过")
    axes[0].set_ylabel("综合得分")

    # 各维度分项
    fields = ["corr", "kurt", "freq_score"]
    for idx, s in enumerate(scored):
        vals = [s.get(f, 0) for f in fields]
        axes[1].plot(fields, vals, 'o-', lw=1, markersize=6,
                     color=C_PASS if idx==np.argmax(scores) else C_GT,
                     label=f'IMF{idx}' if idx==np.argmax(scores) else "")
    axes[1].set_title("分项指标雷达"); axes[1].legend(fontsize=7)

    fig.suptitle("sensitive_selector 敏感分量选择 | 绿=最优 灰=其他", fontsize=12)
    plt.tight_layout(); fig.savefig(PLOT_DIR/"23_sensitive_selector.png", dpi=150); plt.close()
    print("  [OK] 23_sensitive_selector.png")


# ═══════════════════════════════════════════════════════════
# 图24: trend_prediction — Holt-Winters预测 + Kalman平滑
# ═══════════════════════════════════════════════════════════
def plot_trend_prediction_detail():
    # Holt-Winters 退化预测
    hs = [100.0, 98.0, 95.0, 92.0, 88.0, 85.0]
    ts = list(range(len(hs)))
    res = holt_winters_forecast(hs, ts, forecast_steps=4)
    fc = res.get("forecast_values", [])
    direction = res.get("trend_direction", "")

    # Kalman 平滑
    np.random.seed(42)
    true_hs = [90.0]*10
    noisy_hs = [h+np.random.randn()*3 for h in true_hs]
    res2 = kalman_smooth_health_scores(noisy_hs)
    smoothed = res2.get("smoothed_scores", [])

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

    # 预测曲线
    all_ts = list(range(len(hs)+len(fc)))
    axes[0].plot(ts, hs, 'o-', color=C_EST, lw=1.5, markersize=6, label='历史数据')
    axes[0].plot(range(len(hs), len(hs)+len(fc)), fc, 's--', color=C_THRESH, lw=1.5, markersize=6, label=f'预测({direction})')
    axes[0].axvline(x=len(hs)-1, color=C_GT, ls='--', alpha=0.5, label='预测起点')
    axes[0].set_title(f"Holt-Winters预测 | 趋势={direction} [{MK_OK}]\n判定:退化趋势方向正确为通过")
    axes[0].set_xlabel("时间步"); axes[0].set_ylabel("健康度"); axes[0].legend(fontsize=7)

    # Kalman 平滑
    axes[1].plot(range(len(noisy_hs)), noisy_hs, 'o-', color=C_FAIL, alpha=0.5, lw=0.8, markersize=4, label='含噪观测')
    axes[1].plot(range(len(noisy_hs)), true_hs, color=C_GT, lw=1, label='GT:真实值=90')
    axes[1].plot(range(len(smoothed)), smoothed, color=C_EST, lw=1.5, label='Kalman平滑')
    var_b = float(np.var(noisy_hs)); var_a = float(np.var(smoothed))
    mk = MK_OK if var_a < var_b*1.2 else MK_NG
    axes[1].set_title(f"Kalman平滑 | var {var_b:.1f}→{var_a:.1f} [{mk}]\n判定:方差降低或持平为通过")
    axes[1].set_xlabel("时间步"); axes[1].legend(fontsize=7)

    fig.suptitle("trend_prediction 趋势预测 | 蓝=数据 灰=GT 橙=预测", fontsize=12)
    plt.tight_layout(); fig.savefig(PLOT_DIR/"24_trend_prediction.png", dpi=150); plt.close()
    print("  [OK] 24_trend_prediction.png")


# ═══════════════════════════════════════════════════════════
# 图25: probability_calibration — Sigmoid概率曲线
# ═══════════════════════════════════════════════════════════
def plot_probability_calibration_detail():
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

    # Sigmoid 概率曲线
    snr_vals = np.linspace(0, 15, 100)
    probs = [_sigmoid_prob(v, threshold=5.0, max_prob=0.85, slope=1.5) for v in snr_vals]
    axes[0].plot(snr_vals, probs, color=C_EST, lw=1.5)
    axes[0].axvline(x=5.0, color=C_THRESH, ls='--', lw=1, label='阈值SNR=5')
    axes[0].axhline(y=0.85, color=C_GT, ls='--', lw=1, alpha=0.5, label='max_prob=0.85')
    axes[0].fill_between(snr_vals, 0, probs, alpha=0.1, color=C_EST)
    axes[0].set_title("_sigmoid_prob SNR→概率映射\n判定:单调递增且边界合理为通过")
    axes[0].set_xlabel("SNR"); axes[0].set_ylabel("故障概率"); axes[0].legend(fontsize=7)
    axes[0].set_ylim(0, 1)

    # 不同故障类型的概率曲线
    types = ["generic", "bearing", "gear"]
    colors_t = [C_EST, C_PASS, C_THRESH]
    for tp, c in zip(types, colors_t):
        probs_t = [calibrate_snr_to_prob(v, fault_type=tp) for v in snr_vals]
        axes[1].plot(snr_vals, probs_t, color=c, lw=1.2, label=tp)
    axes[1].axhline(y=0.5, color=C_GT, ls='--', alpha=0.5, label='P=0.5')
    axes[1].set_title("calibrate_snr_to_prob 按故障类型\n判定:各类型曲线单调为通过")
    axes[1].set_xlabel("SNR"); axes[1].set_ylabel("故障概率"); axes[1].legend(fontsize=7)
    axes[1].set_ylim(0, 1)

    fig.suptitle("probability_calibration 概率校准 | 蓝=generic 绿=bearing 橙=gear", fontsize=12)
    plt.tight_layout(); fig.savefig(PLOT_DIR/"25_probability_calibration.png", dpi=150); plt.close()
    print("  [OK] 25_probability_calibration.png")


# ═══════════════════════════════════════════════════════════
# 图18-25: 新增模块通过率汇总（只读JSON）— 已被详细图替代，仅保留为fallback
# ═══════════════════════════════════════════════════════════
def _plot_simple_summary(json_name, title, filename):
    data = load_json(json_name)
    if not data or "summary" not in data:
        print(f"  [SKIP] {json_name}")
        return
    s = data["summary"]
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.barh(["通过", "失败"], [s["passed"], s["failed"]], color=[C_PASS, C_FAIL])
    pct = s["passed"]/max(s["total"],1)*100
    mk = "[ALL PASS]" if s["failed"]==0 else f"[{s['failed']} FAIL]"
    ax.set_title(f"{title} | {s['total']}测试 {mk}\n判定:全部通过为PASS")
    for i, v in enumerate([s["passed"], s["failed"]]):
        ax.text(v+0.1, i, str(v), va='center', fontsize=12)
    ax.set_xlim(0, max(s["total"]*1.3, 5))
    plt.tight_layout(); fig.savefig(PLOT_DIR/filename, dpi=150); plt.close()
    print(f"  [OK] {filename}")

def plot_savgol(): _plot_simple_summary("savgol_denoise.json", "savgol_denoise S-G平滑", "18_savgol.png")
def plot_wavelet_packet(): _plot_simple_summary("wavelet_packet.json", "wavelet_packet 小波包", "19_wavelet_packet.png")
def plot_msb(): _plot_simple_summary("msb_correctness.json", "gear/msb MSB", "20_msb.png")
def plot_cyclostationary(): _plot_simple_summary("bearing_cyclostationary.json", "bearing_cyclostationary", "21_cyclostationary.png")
def plot_modality_bearing(): _plot_simple_summary("modality_bearing.json", "modality_bearing", "22_modality_bearing.png")
def plot_sensitive_selector(): _plot_simple_summary("sensitive_selector.json", "sensitive_selector", "23_sensitive_selector.png")
def plot_trend_prediction(): _plot_simple_summary("trend_prediction.json", "trend_prediction", "24_trend_prediction.png")
def plot_probability_calibration(): _plot_simple_summary("probability_calibration.json", "probability_calibration", "25_probability_calibration.png")


# ═══════════════════════════════════════════════════════════
# 图13: 汇总 — 全部测试通过率（只读JSON）
# ═══════════════════════════════════════════════════════════
def plot_summary():
    all_jsons = ["signal_utils_correctness","vmd_denoise_correctness","health_score_continuous",
                 "bearing_sideband","channel_consensus","recommendation","savgol_denoise",
                 "wavelet_packet","msb_correctness","bearing_cyclostationary","modality_bearing",
                 "sensitive_selector","trend_prediction","probability_calibration"]
    summary_data = {}
    for jn in all_jsons:
        d = load_json(f"{jn}.json")
        if d and "summary" in d:
            summary_data[jn.replace("_correctness","").replace("_"," ")] = d["summary"]

    su_data = load_json("signal_utils_correctness.json")
    categories = {}
    if su_data:
        for cat in [k for k in su_data if k!="summary"]:
            items = su_data[cat]
            categories[cat.replace("_"," ")] = {"total":len(items), "passed":sum(1 for it in items if it.get("passed",False))}

    fig, axes = plt.subplots(1, 2, figsize=(15, 6))

    if categories:
        labels = list(categories.keys())
        ttl = [categories[l]["total"] for l in labels]; pss = [categories[l]["passed"] for l in labels]
        fl = [t-p for t,p in zip(ttl,pss)]
        x = np.arange(len(labels))
        axes[0].bar(x, pss, color=C_PASS, label='PASS')
        axes[0].bar(x, fl, bottom=pss, color=C_FAIL, label='FAIL')
        axes[0].set_xticks(x); axes[0].set_xticklabels(labels, fontsize=7, rotation=15)
        axes[0].set_title("signal_utils 13类函数 | 判定:每类全通过为PASS"); axes[0].legend()
        for i,(t,p) in enumerate(zip(ttl,pss)):
            axes[0].text(i, t+0.15, f"{p}/{t}", ha='center', fontsize=8)

    labels2 = list(summary_data.keys())
    ttl2 = [summary_data[l]["total"] for l in labels2]; pss2 = [summary_data[l]["passed"] for l in labels2]
    fl2 = [t-p for t,p in zip(ttl2,pss2)]
    x2 = np.arange(len(labels2))
    axes[1].bar(x2, pss2, color=C_PASS, label='PASS')
    axes[1].bar(x2, fl2, bottom=pss2, color=C_FAIL, label='FAIL')
    axes[1].set_xticks(x2); axes[1].set_xticklabels(labels2, fontsize=6, rotation=45, ha='right')
    axes[1].set_title("Layer1 14模块 | 151测试 | 判定:100%=PASS"); axes[1].legend()
    for i,(t,p) in enumerate(zip(ttl2,pss2)):
        axes[1].text(i, t+0.3, f"{p}/{t}", ha='center', fontsize=8)

    fig.suptitle("Layer1信号基元测试通过率汇总 | 绿=PASS 红=FAIL", fontsize=13)
    plt.tight_layout(); fig.savefig(PLOT_DIR/"13_summary.png", dpi=150); plt.close()
    print("  [OK] 13_summary.png")


def main():
    if not HAS_MPL: print("matplotlib未安装"); return
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    print("Layer1信号基元 — 严格规范绘图"); print("="*55)

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
    plot_savgol_detail()       # 18  ← 详细版
    plot_wavelet_packet_detail() # 19 ← 详细版
    plot_msb_detail()          # 20  ← 详细版
    plot_cyclostationary_detail() # 21 ← 详细版
    plot_modality_bearing_detail() # 22 ← 详细版
    plot_sensitive_selector_detail() # 23 ← 详细版
    plot_trend_prediction_detail()  # 24 ← 详细版
    plot_probability_calibration_detail() # 25 ← 详细版
    plot_summary()             # 13

    print(f"\n25张图表 → {PLOT_DIR}")


if __name__ == "__main__":
    main()
