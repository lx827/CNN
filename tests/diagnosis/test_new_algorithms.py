"""
新算法验证测试脚本

使用 HUSTbear（轴承）、CW（变速轴承）、WTgearbox（行星齿轮箱）数据集
验证 ALGORITHMS.md 中描述但之前未实现的算法。

测试内容：
1. LMS 自适应滤波 — 对强噪声轴承信号去噪效果
2. BSS/FastICA — 分离故障与噪声成分
3. 轴承 SC/SCoh 循环平稳分析 — 检测轴承故障循环频率
4. ZOOM-FFT 边频带分析 — 齿轮边频带精细分辨
5. 联合降噪（wavelet+VMD）— 级联去噪效果
6. 非参数 CUSUM — 健康vs故障漂移检测
"""
import sys
sys.path.insert(0, 'd:\\code\\CNN\\cloud')

import numpy as np
import os

# 数据集路径
HUST_DIR = "d:\\code\\wavelet_study\\dataset\\HUSTbear\\down8192"
CW_DIR = "d:\\code\\CNN\\CW\\down8192_CW"
WTG_DIR = "d:\\code\\wavelet_study\\dataset\\WTgearbox\\down8192"

FS = 8192  # 所有数据集采样率 8192 Hz

print("=" * 70)
print("新算法有效性验证测试")
print("=" * 70)

# ── 1. LMS 自适应滤波 ──
print("\n── 1. LMS 自适应滤波 ──")
from app.services.diagnosis.lms_filter import lms_filter, nlms_filter, vsslms_filter

# 加载内圈故障轴承数据
ir_file = os.path.join(HUST_DIR, "I_40Hz-X.npy")
healthy_file = os.path.join(HUST_DIR, "H_40Hz-X.npy")
ir_signal = np.load(ir_file)
h_signal = np.load(healthy_file)
# 截断到5秒
max_s = int(FS * 5)
ir_signal = ir_signal[:max_s]
h_signal = h_signal[:max_s]

print(f"  内圈故障信号: kurtosis={float(np.mean(ir_signal**4)/(np.var(ir_signal)**2)): .2f}")
print(f"  健康信号: kurtosis={float(np.mean(h_signal**4)/(np.var(h_signal)**2)): .2f}")

# 标准 LMS
result_lms, info_lms = lms_filter(ir_signal, filter_len=32, step_size=0.01)
print(f"  LMS: kurt_before={info_lms['kurtosis_before']}, kurt_after={info_lms['kurtosis_after']}, "
      f"NR={info_lms['noise_reduction_ratio']}")

# NLMS
result_nlms, info_nlms = nlms_filter(ir_signal, filter_len=32, step_size=0.5)
print(f"  NLMS: kurt_before={info_nlms['kurtosis_before']}, kurt_after={info_nlms['kurtosis_after']}, "
      f"NR={info_nlms['noise_reduction_ratio']}")

# VSSLMS
result_vss, info_vss = vsslms_filter(ir_signal, filter_len=32, mu_init=0.01)
print(f"  VSSLMS: kurt_before={info_vss['kurtosis_before']}, kurt_after={info_vss['kurtosis_after']}, "
      f"NR={info_vss['noise_reduction_ratio']}")

# 对健康信号做同样处理（验证不会误增强噪声）
_, info_h_lms = lms_filter(h_signal, filter_len=32, step_size=0.01)
print(f"  健康信号LMS: kurt_before={info_h_lms['kurtosis_before']}, kurt_after={info_h_lms['kurtosis_after']}")

print("  ✓ LMS 滤波完成")

# ── 2. BSS/FastICA 盲源分离 ──
print("\n── 2. BSS/FastICA 盲源分离 ──")
from app.services.diagnosis.bss import vmd_ica_separation

bss_result = vmd_ica_separation(ir_signal, FS, K=3, alpha=2000)
print(f"  VMD modes: {bss_result.get('n_modes', 0)}")
print(f"  VMD kurtoses: {bss_result.get('vmd_kurtoses', [])}")
print(f"  ICA kurtoses: {bss_result.get('ica_kurtoses', [])}")
print(f"  Selected component index: {bss_result.get('selected_component_index', -1)}")
if "error" not in bss_result:
    fc = bss_result.get("fault_component", np.zeros(10))
    fc_kurt = float(np.mean(fc**4) / (np.var(fc)**2 + 1e-12))
    print(f"  Fault component kurtosis: {fc_kurt:.2f}")
print("  ✓ BSS 分离完成")

# ── 3. 轴承 SC/SCoh 循环平稳分析 ──
print("\n── 3. 轴承 SC/SCoh 循环平稳分析 ──")
from app.services.diagnosis.bearing_cyclostationary import bearing_sc_scoh_analysis

# HUSTbear 内圈故障 — 已知 40Hz 转频
# HUST轴承: n=9, d/D≈0.19 (典型深沟球轴承)
bearing_params = {"n": 9, "d": 5.5, "D": 29, "alpha": 0}
sc_result = bearing_sc_scoh_analysis(ir_signal, FS, bearing_params=bearing_params, rot_freq=40.0)
print(f"  转频: {sc_result['rot_freq_hz']} Hz")
print(f"  故障频率: {sc_result['fault_freqs_hz']}")
print(f"  最大SCoh值: {sc_result['sc_max_value']}")
print(f"  主导故障: {sc_result['dominant_fault']}")

# 输出各故障频率指标
for name, indicator in sc_result.get("fault_indicators", {}).items():
    if isinstance(indicator, dict):
        print(f"    {name}: scoh_peak={indicator.get('scoh_peak', 0)}, "
              f"snr={indicator.get('scoh_snr', 0)}, "
              f"significant={indicator.get('significant', False)}")

# 对健康信号做同样分析（验证不误报）
sc_healthy = bearing_sc_scoh_analysis(h_signal, FS, bearing_params=bearing_params, rot_freq=40.0)
print(f"  健康信号SCoh最大值: {sc_healthy['sc_max_value']}")
print(f"  健康信号主导故障: {sc_healthy['dominant_fault']}")
print("  ✓ SC/SCoh 分析完成")

# CW 变速工况下 SC/SCoh
cw_i_file = os.path.join(CW_DIR, "I-A-1.npy")  # 内圈故障升速
cw_h_file = os.path.join(CW_DIR, "H-A-1.npy")  # 健康
cw_i_signal = np.load(cw_i_file)[:max_s]
cw_h_signal = np.load(cw_h_file)[:max_s]
print(f"\n  CW 变速内圈故障: kurtosis={float(np.mean(cw_i_signal**4)/(np.var(cw_i_signal)**2)): .2f}")
sc_cw = bearing_sc_scoh_analysis(cw_i_signal, FS, bearing_params=bearing_params, rot_freq=20.0)
print(f"  CW SCoh最大值: {sc_cw['sc_max_value']}, 主导: {sc_cw['dominant_fault']}")
print("  ✓ 变速工况 SC/SCoh 完成")

# ── 4. ZOOM-FFT 边频带分析 ──
print("\n── 4. ZOOM-FFT 边频带分析 ──")
from app.services.diagnosis.gear.metrics import analyze_sidebands_zoom_fft

# WTgearbox 断齿 + 健康
br_file = os.path.join(WTG_DIR, "Br_B1_40-c1.npy")
he_file = os.path.join(WTG_DIR, "He_N1_40-c1.npy")
br_signal = np.load(br_file)[:max_s]
he_signal = np.load(he_file)[:max_s]

# 行星齿轮箱参数
z_sun = 28
z_ring = 100
mesh_freq = 40.0 * z_ring * z_sun / (z_sun + z_ring)  # ≈ 875 Hz
rot_freq = 40.0

print(f"  断齿信号 kurtosis: {float(np.mean(br_signal**4)/(np.var(br_signal)**2)): .2f}")
print(f"  健康信号 kurtosis: {float(np.mean(he_signal**4)/(np.var(he_signal)**2)): .2f}")
print(f"  mesh_freq ≈ {mesh_freq:.1f} Hz, rot_freq = {rot_freq} Hz")

# ZOOM-FFT 边频带分析
zoom_br = analyze_sidebands_zoom_fft(br_signal, FS, mesh_freq, rot_freq, n_sidebands=6)
zoom_he = analyze_sidebands_zoom_fft(he_signal, FS, mesh_freq, rot_freq, n_sidebands=6)

print(f"  断齿: SER={zoom_br['ser']}, zoom_used={zoom_br['zoom_used']}, "
      f"resolution={zoom_br['resolution_hz']} Hz")
print(f"  健康: SER={zoom_he['ser']}, zoom_used={zoom_he['zoom_used']}, "
      f"resolution={zoom_he['resolution_hz']} Hz")

# SER 区分比
if zoom_he['ser'] > 0:
    print(f"  SER 区分比(故障/健康): {zoom_br['ser']/zoom_he['ser']: .2f}")

# 显著边频带数量
n_significant_br = sum(1 for sb in zoom_br['sidebands'] if sb.get('significant', False))
n_significant_he = sum(1 for sb in zoom_he['sidebands'] if sb.get('significant', False))
print(f"  断齿显著边频: {n_significant_br}, 健康显著边频: {n_significant_he}")
print("  ✓ ZOOM-FFT 边频带分析完成")

# ── 5. 联合降噪 ──
print("\n── 5. 联合降噪 (wavelet+VMD 级联) ──")
from app.services.diagnosis.preprocessing import cascade_wavelet_vmd, cascade_wavelet_lms, joint_denoise

# 小波+VMD级联
casc_wv_result, casc_wv_info = cascade_wavelet_vmd(ir_signal)
print(f"  Wavelet+VMD: kurt_before={casc_wv_info['kurtosis_before']}, "
      f"kurt_after_wavelet={casc_wv_info['kurtosis_after_wavelet']}, "
      f"kurt_after_cascade={casc_wv_info['kurtosis_after_cascade']}, "
      f"NR={casc_wv_info['noise_reduction_ratio']}")

# 小波+LMS级联
casc_wl_result, casc_wl_info = cascade_wavelet_lms(ir_signal)
print(f"  Wavelet+LMS: kurt_before={casc_wl_info['kurtosis_before']}, "
      f"kurt_after={casc_wl_info['kurtosis_after_cascade']}, "
      f"NR={casc_wl_info['noise_reduction_ratio']}")

# 统一入口 joint_denoise
jd_result, jd_info = joint_denoise(ir_signal, strategy="wavelet_vmd")
print(f"  joint_denoise(wavelet_vmd): kurt_after={jd_info.get('kurtosis_after_cascade', 0)}")

print("  ✓ 联合降噪完成")

# ── 6. 非参数 CUSUM ──
print("\n── 6. 非参数 CUSUM ──")
from app.services.diagnosis.features import compute_nonparam_cusum_features

np_cusum_ir = compute_nonparam_cusum_features(ir_signal)
np_cusum_h = compute_nonparam_cusum_features(h_signal)
print(f"  内圈故障:")
print(f"    sign_cusum_pos={np_cusum_ir['sign_cusum_positive']}, "
      f"neg={np_cusum_ir['sign_cusum_negative']}, "
      f"alarm={np_cusum_ir['sign_cusum_alarm']}")
print(f"    mw_cusum_pos={np_cusum_ir['mw_cusum_positive']}, "
      f"neg={np_cusum_ir['mw_cusum_negative']}, "
      f"alarm={np_cusum_ir['mw_cusum_alarm']}")
print(f"  健康信号:")
print(f"    sign_cusum_pos={np_cusum_h['sign_cusum_positive']}, "
      f"neg={np_cusum_h['sign_cusum_negative']}, "
      f"alarm={np_cusum_h['sign_cusum_alarm']}")
print(f"    mw_cusum_pos={np_cusum_h['mw_cusum_positive']}, "
      f"neg={np_cusum_h['mw_cusum_negative']}, "
      f"alarm={np_cusum_h['mw_cusum_alarm']}")

# WTgearbox 断齿 vs 健康
np_cusum_br = compute_nonparam_cusum_features(br_signal)
np_cusum_he = compute_nonparam_cusum_features(he_signal)
print(f"  断齿: sign_alarm={np_cusum_br['sign_cusum_alarm']}, mw_alarm={np_cusum_br['mw_cusum_alarm']}")
print(f"  健康: sign_alarm={np_cusum_he['sign_cusum_alarm']}, mw_alarm={np_cusum_he['mw_cusum_alarm']}")
print("  ✓ 非参数 CUSUM 完成")

print("\n" + "=" * 70)
print("所有新算法验证测试完成!")
print("=" * 70)