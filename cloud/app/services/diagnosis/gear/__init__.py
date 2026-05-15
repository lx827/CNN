"""
齿轮故障诊断算法模块

包含：
- FM0: 粗故障检测（齿断裂/严重磨损）
- FM4: 局部故障检测（单/双齿点蚀/裂纹）
- NA4: 趋势型故障检测（损伤扩展追踪）
- NB4: 局部齿损坏（包络域）
- M6A / M8A: 表面损伤高阶矩
- ER: 能量比（多齿磨损）
- SER: 边频带能量比（核心频域指标）
- CAR: 倒频谱幅值比
- 边频带分析
"""
import numpy as np
from scipy import stats
from scipy.fft import rfft, rfftfreq
from scipy.signal import hilbert
from typing import Dict, List, Optional, Tuple

from ..signal_utils import prepare_signal, compute_fft_spectrum, _band_energy
from .metrics import (
    analyze_sidebands_order,
    compute_fm0_order,
    compute_tsa_residual_order,
    compute_car,
    compute_fm4,
    compute_m6a,
    compute_m8a,
    compute_ser_order,
)
from .planetary_demod import (
    planetary_envelope_order_analysis,
    planetary_fullband_envelope_order_analysis,
    planetary_vmd_demod_analysis,
    planetary_tsa_envelope_analysis,
    planetary_hp_envelope_order_analysis,
    planetary_sc_scoh_analysis,
    evaluate_planetary_demod_results,
)

__all__ = [
    "compute_fm0",
    "compute_fm0_order",
    "compute_tsa_residual_order",
    "compute_fm4",
    "compute_na4",
    "compute_ser",
    "compute_ser_order",
    "compute_car",
    "compute_m6a",
    "compute_m8a",
    "analyze_sidebands",
    "analyze_sidebands_order",
    "_evaluate_gear_faults",
    "planetary_envelope_order_analysis",
    "planetary_fullband_envelope_order_analysis",
    "planetary_vmd_demod_analysis",
    "planetary_tsa_envelope_analysis",
    "planetary_hp_envelope_order_analysis",
    "planetary_sc_scoh_analysis",
    "evaluate_planetary_demod_results",
]


def compute_fm0(
    tsa_signal: np.ndarray,
    mesh_freq: float,
    fs: float,
    n_harmonics: int = 3,
) -> float:
    """
    FM0 — 粗故障检测（齿断裂/严重磨损）

    FM0 = PP / sum(A(f_mesh_harmonics))
    """
    arr = np.array(tsa_signal, dtype=np.float64)
    pp = np.max(arr) - np.min(arr)

    xf, yf = compute_fft_spectrum(arr, fs)
    yf = np.array(yf)

    harmonics_sum = 0.0
    for i in range(1, n_harmonics + 1):
        harmonics_sum += _band_energy(xf, yf, mesh_freq * i, 5.0)

    if harmonics_sum < 1e-12:
        return 0.0
    return float(pp / harmonics_sum)


def compute_na4(
    residual_signal: np.ndarray,
    historical_residuals: List[np.ndarray],
) -> float:
    """
    NA4 — 趋势型故障检测（损伤扩展追踪）

    准归一化峭度，分母为历史平均方差，随损伤扩展单调上升。

    Args:
        residual_signal: 当前残余信号
        historical_residuals: 历史残余信号列表（至少1条）
    """
    r = np.array(residual_signal, dtype=np.float64)
    N = len(r)
    if N < 4:
        return 0.0

    r_mean = np.mean(r)
    numerator = (1.0 / N) * np.sum((r - r_mean) ** 4)

    if not historical_residuals:
        denominator = ((1.0 / N) * np.sum((r - r_mean) ** 2)) ** 2
        return float(numerator / denominator) if denominator > 1e-12 else 0.0

    variances = []
    for hist in historical_residuals:
        hist = np.array(hist, dtype=np.float64)
        if len(hist) > 0:
            hist_mean = np.mean(hist)
            variances.append((1.0 / len(hist)) * np.sum((hist - hist_mean) ** 2))

    if not variances:
        return 0.0

    denom_mean = np.mean(variances)
    return float(numerator / (denom_mean ** 2)) if denom_mean > 1e-12 else 0.0


def compute_nb4(
    residual_signal: np.ndarray,
    fs: float,
    historical_envelopes: Optional[List[np.ndarray]] = None,
    band_center: Optional[float] = None,
    band_width: float = 500.0,
) -> float:
    """
    NB4 — 局部齿损坏（包络域）

    检测由局部齿损坏引起的瞬态负载波动（反映在包络上）。
    """
    r = np.array(residual_signal, dtype=np.float64)

    # 带通滤波 + 包络
    if band_center is not None:
        from ..signal_utils import bandpass_filter
        filtered = bandpass_filter(r, fs, max(10, band_center - band_width / 2), min(fs / 2 - 10, band_center + band_width / 2))
    else:
        filtered = r

    envelope = np.abs(hilbert(filtered))
    N = len(envelope)
    if N < 4:
        return 0.0

    e_mean = np.mean(envelope)
    numerator = (1.0 / N) * np.sum((envelope - e_mean) ** 4)

    if not historical_envelopes:
        denominator = ((1.0 / N) * np.sum((envelope - e_mean) ** 2)) ** 2
        return float(numerator / denominator) if denominator > 1e-12 else 0.0

    variances = []
    for hist in historical_envelopes:
        hist = np.array(hist, dtype=np.float64)
        if len(hist) > 0:
            hist_mean = np.mean(hist)
            variances.append((1.0 / len(hist)) * np.sum((hist - hist_mean) ** 2))

    if not variances:
        return 0.0

    denom_mean = np.mean(variances)
    return float(numerator / (denom_mean ** 2)) if denom_mean > 1e-12 else 0.0


def compute_er(
    differential_signal: np.ndarray,
    tsa_signal: np.ndarray,
    mesh_freq: float,
    fs: float,
    n_harmonics: int = 3,
    n_sidebands: int = 3,
) -> float:
    """
    ER — 能量比（多齿磨损）

    ER = RMS[d(t)] / (啮合谐波能量 + 边带能量)
    """
    d = np.array(differential_signal, dtype=np.float64)
    rms_d = np.sqrt(np.mean(d ** 2))

    xf, yf = compute_fft_spectrum(np.array(tsa_signal), fs)
    yf = np.array(yf)

    # 啮合谐波能量
    mesh_energy = 0.0
    for i in range(1, n_harmonics + 1):
        mesh_energy += _band_energy(xf, yf, mesh_freq * i, 5.0)

    # 边带能量
    sb_energy = 0.0
    rot_freq = mesh_freq / 18  # 近似估算，实际应传入
    for j in range(1, n_sidebands + 1):
        sb_energy += _band_energy(xf, yf, mesh_freq - j * rot_freq, 2.0)
        sb_energy += _band_energy(xf, yf, mesh_freq + j * rot_freq, 2.0)

    denom = mesh_energy + sb_energy
    if denom < 1e-12:
        return 0.0
    return float(rms_d / denom)


def compute_ser(
    signal: np.ndarray,
    fs: float,
    mesh_freq: float,
    rot_freq: float,
    n_sidebands: int = 6,
    sideband_bw: float = 2.0,
) -> float:
    """
    SER — 边频带能量比（核心频域指标）

    SER = sum(A_SB_i^+ + A_SB_i^-) / A(f_mesh)

    健康齿轮 SER < 1；故障齿轮 SER > 1 且随劣化单调上升。
    """
    arr = prepare_signal(signal)
    xf, yf = compute_fft_spectrum(arr, fs)
    yf = np.array(yf)

    mesh_amp = _band_energy(xf, yf, mesh_freq, 5.0)
    if mesh_amp < 1e-12:
        return 0.0

    total_sideband = 0.0
    for i in range(1, n_sidebands + 1):
        sb_low = mesh_freq - i * rot_freq
        sb_high = mesh_freq + i * rot_freq
        total_sideband += _band_energy(xf, yf, sb_low, sideband_bw)
        total_sideband += _band_energy(xf, yf, sb_high, sideband_bw)

    return float(total_sideband / mesh_amp)


def analyze_sidebands(
    signal: np.ndarray,
    fs: float,
    mesh_freq: float,
    rot_freq: float,
    n_sidebands: int = 6,
) -> Dict:
    """
    边频带分析

    返回边频带的幅值、显著性、对称性等信息。
    """
    arr = prepare_signal(signal)
    xf, yf = compute_fft_spectrum(arr, fs)
    yf = np.array(yf)

    mesh_amp = _band_energy(xf, yf, mesh_freq, 5.0)
    if mesh_amp < 1e-12:
        return {"sidebands": [], "ser": 0.0}

    sidebands = []
    total_sb = 0.0

    for i in range(1, n_sidebands + 1):
        sb_low = mesh_freq - i * rot_freq
        sb_high = mesh_freq + i * rot_freq

        amp_low = _band_energy(xf, yf, sb_low, 2.0)
        amp_high = _band_energy(xf, yf, sb_high, 2.0)

        total_sb += amp_low + amp_high

        # 显著性：边频幅值超过啮合频率的 5%
        significant = (amp_low > mesh_amp * 0.05) or (amp_high > mesh_amp * 0.05)

        sidebands.append({
            "order": i,
            "freq_low": round(sb_low, 2),
            "freq_high": round(sb_high, 2),
            "amp_low": round(amp_low, 6),
            "amp_high": round(amp_high, 6),
            "significant": significant,
            "asymmetry": round(abs(amp_low - amp_high) / (amp_low + amp_high + 1e-12), 4),
        })

    return {
        "sidebands": sidebands,
        "ser": round(total_sb / mesh_amp, 4),
        "mesh_amp": round(mesh_amp, 6),
    }


def _evaluate_gear_faults(gear_result: Dict) -> Dict:
    """评估齿轮故障指示器

    行星齿轮箱（planet_count≥3）的频域指标阈值与定轴齿轮箱不同：
    - 行星架构天然产生大量边频带（多个行星轮同时啮合调制）
    - SER 天然在 5~12 范围（定轴箱健康 < 1.5）
    - CAR 天然在 10^9~10^10 量级（定轴箱健康 < 2）
    - sideband_count 天然 = 6（定轴箱健康通常 ≤ 2）

    因此行星箱的 warning/critical 阈值需要大幅提升，
    否则所有数据（健康和故障）都会被标记为 critical。
    """
    indicators = {}

    # 行星齿轮箱判断：planet_count ≥ 3 → 行星架构
    planet_count = gear_result.get("planet_count", 0)
    is_planetary = planet_count >= 3

    ser = gear_result.get("ser") if gear_result.get("ser") is not None else 0.0
    if is_planetary:
        # 行星箱 SER 天然 2~15（carrier_order 间隔边频带占主导）
        # 健康和故障 SER 范围完全重叠，无区分力
        # 设极高阈值避免误报
        indicators["ser"] = {
            "value": round(ser, 4),
            "warning": ser > 15.0,
            "critical": ser > 20.0,
        }
    else:
        # 定轴箱 SER < 1.5 为正常，> 3.0 为严重
        indicators["ser"] = {
            "value": round(ser, 4),
            "warning": ser > 1.5,
            "critical": ser > 3.0,
        }

    fm0 = gear_result.get("fm0")
    if fm0 is not None:
        indicators["fm0"] = {
            "value": round(fm0, 4),
            "warning": fm0 > 5,
            "critical": fm0 > 10,
        }

    car = gear_result.get("car")
    if car is not None:
        if is_planetary:
            # 行星箱 CAR 范围 3500 ~ 8.4e9（健康和故障完全重叠）
            # mesh_order 修复后 CAR 计算正确但仍无区分力
            # 仅设极高阈值避免误报
            indicators["car"] = {
                "value": round(car, 4),
                "warning": car > 1e10,
                "critical": car > 1e12,
            }
        else:
            # 定轴箱 CAR 正常 < 2.0，故障 > 3.0
            indicators["car"] = {
                "value": round(car, 4),
                "warning": car > 2.0,
                "critical": car > 3.0,
            }

    # 边频带统计
    sidebands = gear_result.get("sidebands", [])
    significant_count = sum(1 for sb in sidebands if sb.get("significant"))
    if is_planetary:
        # 行星箱天然 6 个边频带（4行星轮 × 调制），对故障无区分力
        # 仅标记 ≥ 8 为 warning（实际不可能超过此值）
        indicators["sideband_count"] = {
            "value": significant_count,
            "warning": significant_count >= 8,
            "critical": significant_count >= 10,
        }
    else:
        indicators["sideband_count"] = {
            "value": significant_count,
            "warning": significant_count >= 2,
            "critical": significant_count >= 4,
        }

    # 无齿轮参数时的阶次谱统计指示器
    order_peak_conc = gear_result.get("order_peak_concentration")
    if order_peak_conc is not None:
        if is_planetary:
            # 行星箱健康 peak_conc = 0.2~0.4（旋转谐波占优）
            indicators["order_peak_concentration"] = {
                "value": round(order_peak_conc, 4),
                "warning": order_peak_conc > 0.7,
                "critical": order_peak_conc > 0.9,
            }
        else:
            indicators["order_peak_concentration"] = {
                "value": round(order_peak_conc, 4),
                "warning": order_peak_conc > 0.5,
                "critical": order_peak_conc > 0.7,
            }

    order_kurt = gear_result.get("order_kurtosis")
    if order_kurt is not None:
        if is_planetary:
            # 行星箱健康 order_kurt = 10~1000（旋转谐波峰值导致）
            # FM4/M6A/M8A 也在 3~5 范围，无区分力
            # 仅设极高阈值
            indicators["order_kurtosis"] = {
                "value": round(order_kurt, 2),
                "warning": order_kurt > 50.0,
                "critical": order_kurt > 200.0,
            }
        else:
            indicators["order_kurtosis"] = {
                "value": round(order_kurt, 2),
                "warning": order_kurt > 5.0,
                "critical": order_kurt > 8.0,
            }

    return indicators
