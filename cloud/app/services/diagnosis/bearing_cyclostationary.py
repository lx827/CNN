"""
轴承循环平稳分析模块

包含：
- 轴承谱相关密度 (Spectral Correlation, SC)
- 轴承谱相干 (Spectral Coherence, SCoh)
- 循环频率搜索与故障判定

ALGORITHMS.md §1.5 参考：
轴承故障信号具有二阶循环平稳性——其统计特性随轴转角周期变化。
谱相关密度 S_x^α(f) 在循环频率 α 等于故障特征频率（BPFO/BPFI/BSF）
处出现显著峰值。该方法对随机噪声和确定性干扰具有天然免疫力，
是变速工况下的高级诊断手段。

本模块与行星箱 planetary_demod.py::planetary_sc_scoh_analysis 算法相同，
但循环频率搜索目标改为轴承特征频率 (BPFO/BPFI/BSF/FTF)。
"""
import numpy as np
from typing import Dict, Tuple, Optional, List

from .signal_utils import prepare_signal


def _compute_sc_scoh_bearing(
    signal: np.ndarray,
    fs: float,
    seg_len: int = 1024,
    overlap_ratio: float = 0.5,
    alpha_max: Optional[float] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    计算谱相关密度和谱相干（底层函数，轴承与行星箱共用）

    使用分段 FFT 估计法：
    S_x^α(f) = <X(f-α/2) * conj(X(f+α/2))>  (分段平均)
    γ_x^α(f) = |S_x^α(f)| / sqrt(PSD(f+α/2) * PSD(f-α/2))

    Args:
        signal: 输入信号
        fs: 采样率
        seg_len: 分段长度
        overlap_ratio: 分段重叠比例
        alpha_max: 最大循环频率 (Hz)，None 则取 fs/4

    Returns:
        (f_axis, alpha_axis, scoh_matrix)
        scoh_matrix[i_alpha, i_f] = 谱相干值
    """
    arr = prepare_signal(signal)
    N = len(arr)

    if alpha_max is None:
        alpha_max = fs / 4.0

    # 分段
    step = int(seg_len * (1 - overlap_ratio))
    n_segments = max(1, (N - seg_len) // step + 1)

    # 频率轴
    f_axis = np.fft.rfftfreq(seg_len, 1.0 / fs)
    n_freq = len(f_axis)

    # 循环频率轴
    alpha_axis = np.fft.rfftfreq(seg_len, 1.0 / fs)
    # 只保留 alpha <= alpha_max
    alpha_mask = alpha_axis <= alpha_max
    alpha_axis = alpha_axis[alpha_mask]
    n_alpha = len(alpha_axis)

    # 预分配
    sc_accum = np.zeros((n_alpha, n_freq), dtype=np.float64)
    psd_f_plus = np.zeros(n_freq, dtype=np.float64)
    psd_f_minus = np.zeros(n_freq, dtype=np.float64)
    count = 0

    for seg_idx in range(n_segments):
        start = seg_idx * step
        end = start + seg_len
        if end > N:
            break
        segment = arr[start:end]

        # Hanning 窗
        window = np.hanning(seg_len)
        seg_windowed = segment * window

        # FFT
        X = np.fft.rfft(seg_windowed)
        PSD = np.abs(X) ** 2 / seg_len

        # 对每个循环频率 alpha，计算谱相关
        for a_idx, alpha in enumerate(alpha_axis):
            # f+α/2 和 f-α/2 的频率索引
            delta_idx = int(round(alpha * seg_len / fs / 2))
            if delta_idx == 0:
                # alpha=0 时，SC = PSD
                sc_accum[a_idx, :] += PSD
                continue
            if delta_idx >= n_freq:
                continue

            # X(f+α/2) 和 X(f-α/2)
            X_plus = X[delta_idx:]    # X[f_idx + delta_idx]
            X_minus = X[:n_freq - delta_idx]  # X[f_idx - delta_idx]

            # S_x^α(f) = X(f-α/2) * conj(X(f+α/2))
            sc_slice = X_minus * np.conj(X_plus)
            sc_accum[a_idx, delta_idx:n_freq] += np.abs(sc_slice)

        # PSD 用于谱相干归一化
        psd_f_plus += PSD
        psd_f_minus += PSD
        count += 1

    if count == 0:
        return f_axis, alpha_axis, np.zeros((n_alpha, n_freq))

    # 平均
    sc_avg = sc_accum / count
    psd_avg = (psd_f_plus + psd_f_minus) / (2 * count)

    # 谱相干：γ_x^α(f) = |S_x^α(f)| / sqrt(PSD(f+α/2) * PSD(f-α/2))
    denominator = np.sqrt(psd_avg * psd_avg) + 1e-12
    scoh = sc_avg / denominator

    # alpha=0 行（自谱），设为1
    if alpha_axis[0] < fs / seg_len:
        scoh[0, :] = 1.0

    return f_axis, alpha_axis, scoh


def bearing_sc_scoh_analysis(
    signal: np.ndarray,
    fs: float,
    bearing_params: Optional[Dict] = None,
    rot_freq: Optional[float] = None,
    seg_len: int = 1024,
) -> Dict:
    """
    轴承谱相关/谱相干分析

    在循环频率轴搜索 BPFO/BPFI/BSF/FTF 对应的峰值，
    判断轴承故障类型。对随机噪声和确定性干扰天然免疫。

    ALGORITHMS.md §1.5, §1.5.3:
    - 谱相干在循环频率 α=故障特征频率处出现显著峰值
    - 工程判据：SCoh > 0.3 为 warning，> 0.5 为 critical

    Args:
        signal: 输入信号
        fs: 采样率
        bearing_params: 轴承几何参数 {n, d, D, alpha}
        rot_freq: 轴转频 (Hz)
        seg_len: 分段 FFT 长度

    Returns:
        {
            "method": "bearing_sc_scoh",
            "rot_freq_hz": float,
            "fault_freqs_hz": Dict[str, float],
            "fault_indicators": Dict[str, Dict],  # 各故障频率的 SCoh 峰值和显著性
            "sc_max_alpha_hz": float,   # SCoh 最大峰值对应的循环频率
            "sc_max_value": float,      # SCoh 最大峰值
            "dominant_fault": str,      # 最可能的故障类型
        }
    """
    arr = prepare_signal(signal)

    # 估计/获取转频
    if rot_freq is None or rot_freq <= 0:
        from .signal_utils import estimate_rot_freq_spectrum
        rot_freq = float(estimate_rot_freq_spectrum(arr, fs))

    # 计算轴承故障频率
    fault_freqs = {}
    if bearing_params and isinstance(bearing_params, dict):
        n = bearing_params.get("n") or 0
        d = bearing_params.get("d") or 0
        D = bearing_params.get("D") or 0
        alpha_deg = bearing_params.get("alpha") or 0
        try:
            n = int(float(n))
            d = float(d)
            D = float(D)
            alpha_rad = np.radians(float(alpha_deg))
        except (TypeError, ValueError):
            n = d = D = 0

        if n > 0 and d > 0 and D > 0:
            cos_a = np.cos(alpha_rad)
            dd = (d / D) * cos_a
            fault_freqs = {
                "BPFO": (n / 2.0) * rot_freq * (1 - dd),
                "BPFI": (n / 2.0) * rot_freq * (1 + dd),
                "BSF":  (D / (2.0 * d)) * rot_freq * (1 - dd ** 2),
                "FTF":  0.5 * rot_freq * (1 - dd),
            }

    # 无轴承参数时，搜索转频附近的循环频率
    if not fault_freqs:
        # 经验估算：BPFO ≈ 0.4·N·fr, BPFI ≈ 0.6·N·fr
        # N 未知时搜索常见范围
        n_est = 8  # 常见轴承滚珠数默认估计
        fault_freqs = {
            "BPFO_est": 0.40 * n_est * rot_freq,
            "BPFI_est": 0.60 * n_est * rot_freq,
        }

    # 设置循环频率搜索范围
    alpha_max = max(fs / 4.0, max(fault_freqs.values()) * 3)

    # 计算谱相干
    f_axis, alpha_axis, scoh = _compute_sc_scoh_bearing(
        arr, fs, seg_len=seg_len, alpha_max=alpha_max
    )

    # 搜索各故障频率对应的谱相干峰值
    alpha_resolution = fs / seg_len
    indicators = {}
    best_scoh = 0.0
    best_fault = ""
    best_alpha = 0.0

    for name, f_hz in fault_freqs.items():
        if f_hz <= 0 or f_hz > alpha_max:
            indicators[name] = {
                "theory_hz": round(f_hz, 2),
                "scoh_peak": 0.0,
                "scoh_snr": 0.0,
                "significant": False,
                "warning": False,
                "critical": False,
            }
            continue

        # 在循环频率轴上搜索 f_hz ± 容差
        # 容差: ±2% 理论频率 或 ±1个频率分辨率
        tol = max(f_hz * 0.03, alpha_resolution * 2)
        alpha_mask = np.abs(alpha_axis - f_hz) <= tol

        if np.any(alpha_mask):
            # 取该循环频率处所有谱频率的 SCoh 最大值
            scoh_slice = scoh[alpha_mask, :]
            peak = float(np.max(scoh_slice))
            # 背景：中位数
            background = float(np.median(scoh_slice))
            snr = peak / (background + 1e-12)

            warning = peak > 0.3 and snr > 3.0
            critical = peak > 0.5 and snr > 5.0

            indicators[name] = {
                "theory_hz": round(f_hz, 2),
                "scoh_peak": round(peak, 4),
                "scoh_snr": round(snr, 4),
                "significant": bool(peak > 0.3),
                "warning": warning,
                "critical": critical,
            }

            if peak > best_scoh:
                best_scoh = peak
                best_fault = name
                best_alpha = f_hz
        else:
            indicators[name] = {
                "theory_hz": round(f_hz, 2),
                "scoh_peak": 0.0,
                "scoh_snr": 0.0,
                "significant": False,
                "warning": False,
                "critical": False,
            }

    # 同时搜索谐波 (2×, 3× 故障频率)
    for name, f_hz in fault_freqs.items():
        for h in [2, 3]:
            h_hz = f_hz * h
            h_name = f"{name}_h{h}"
            if h_hz > alpha_max:
                continue
            tol = max(h_hz * 0.03, alpha_resolution * 2)
            alpha_mask = np.abs(alpha_axis - h_hz) <= tol
            if np.any(alpha_mask):
                scoh_slice = scoh[alpha_mask, :]
                peak = float(np.max(scoh_slice))
                background = float(np.median(scoh_slice))
                snr = peak / (background + 1e-12)
                indicators[h_name] = {
                    "theory_hz": round(h_hz, 2),
                    "scoh_peak": round(peak, 4),
                    "scoh_snr": round(snr, 4),
                    "significant": bool(peak > 0.3),
                }

    return {
        "method": "bearing_sc_scoh",
        "rot_freq_hz": round(rot_freq, 3),
        "fault_freqs_hz": {k: round(v, 2) for k, v in fault_freqs.items()},
        "fault_indicators": indicators,
        "sc_max_alpha_hz": round(best_alpha, 2),
        "sc_max_value": round(best_scoh, 4),
        "dominant_fault": best_fault,
    }