"""
轴承包络谱边频带密度分析模块

针对三种轴承故障类型的谱形态特征：
- BPFI（内圈故障）：包络谱峰值周围常有转频调制边带，边带密度高
- BPFO（外圈故障）：谐波更规律，边带较少
- BSF（滚动体故障）：频率附近有保持架频率（FTF）调制

核心函数：compute_sideband_density — 计算指定故障频率周围的边频带密度指标
"""
import numpy as np
from typing import Dict, Optional, List, Any


def compute_sideband_density(
    env_freq: np.ndarray,
    env_amp: np.ndarray,
    fault_freq_hz: float,
    mod_freq_hz: float,
    background: float,
    max_harmonics: int = 5,
    snr_threshold: float = 3.0,
    freq_tolerance: float = 0.0,
    df: float = 1.0,
) -> Dict[str, Any]:
    """
    计算指定故障频率周围的边频带密度指标

    边频带密度 = 在 fault_freq ± n×mod_freq (n=1,2,...,N) 位置
    超过 SNR_threshold 的边带数量 / 总搜索边带数量

    Args:
        env_freq: 包络谱频率轴 (Hz)
        env_amp: 包络谱幅值轴
        fault_freq_hz: 故障特征频率 (BPFO/BPFI/BSF)
        mod_freq_hz: 调制频率（通常为转频 fr 或保持架频率 FTF）
        background: 包络谱背景水平（中位数）
        max_harmonics: 最大搜索谐波阶数（±1×, ±2×, ..., ±N×mod）
        snr_threshold: 边带显著性的 SNR 阈值
        freq_tolerance: 频率匹配容差 (Hz)，0 则自动计算
        df: 频率分辨率 (Hz)

    Returns:
        {
            "total_searched": int,        # 搜索的边带总数
            "significant_count": int,     # 超过阈值的边带数
            "density": float,             # 边带密度 (0~1)
            "sideband_details": List[Dict], # 各边带的详细信息
            "asymmetry": float,           # 上/下边带不对称性
        }
    """
    if freq_tolerance <= 0:
        freq_tolerance = max(fault_freq_hz * 0.05, df * 2)

    sideband_details = []
    upper_count = 0  # 上边带（+n×mod）
    lower_count = 0  # 下边带（-n×mod）

    for n in range(1, max_harmonics + 1):
        # 上边带：fault_freq + n×mod_freq
        sb_upper = fault_freq_hz + n * mod_freq_hz
        # 下边带：fault_freq - n×mod_freq
        sb_lower = fault_freq_hz - n * mod_freq_hz

        for side, sb_f in [("upper", sb_upper), ("lower", sb_lower)]:
            if sb_f <= 0 or sb_f > env_freq[-1]:
                # 超出频率范围
                sideband_details.append({
                    "order": n,
                    "side": side,
                    "theory_hz": round(sb_f, 2),
                    "detected": False,
                    "snr": 0.0,
                    "significant": False,
                })
                continue

            mask = np.abs(env_freq - sb_f) <= freq_tolerance
            if np.any(mask):
                sb_peak = float(np.max(env_amp[mask]))
                sb_snr = sb_peak / (background + 1e-12)
                significant = sb_snr > snr_threshold
                if significant:
                    if side == "upper":
                        upper_count += 1
                    else:
                        lower_count += 1
                sideband_details.append({
                    "order": n,
                    "side": side,
                    "theory_hz": round(sb_f, 2),
                    "detected": True,
                    "snr": round(sb_snr, 2),
                    "significant": significant,
                })
            else:
                sideband_details.append({
                    "order": n,
                    "side": side,
                    "theory_hz": round(sb_f, 2),
                    "detected": False,
                    "snr": 0.0,
                    "significant": False,
                })

    total_searched = len(sideband_details)
    significant_count = upper_count + lower_count
    density = significant_count / total_searched if total_searched > 0 else 0.0

    # 不对称性：上边带与下边带的比例差异
    # 内圈故障因承载区调制，上下边带幅度不对称
    upper_snrs = [d["snr"] for d in sideband_details if d["side"] == "upper" and d["detected"]]
    lower_snrs = [d["snr"] for d in sideband_details if d["side"] == "lower" and d["detected"]]
    if upper_snrs and lower_snrs:
        asymmetry = abs(np.mean(upper_snrs) - np.mean(lower_snrs)) / (np.mean(upper_snrs) + np.mean(lower_snrs) + 1e-12)
    else:
        asymmetry = 0.0

    return {
        "total_searched": total_searched,
        "significant_count": significant_count,
        "density": round(density, 4),
        "sideband_details": sideband_details,
        "asymmetry": round(asymmetry, 4),
        "upper_count": upper_count,
        "lower_count": lower_count,
    }


def evaluate_bearing_sideband_features(
    env_freq: List[float],
    env_amp: List[float],
    bearing_params: Optional[Dict],
    rot_freq: float,
) -> Dict[str, Dict]:
    """
    评估三种轴承故障类型的边频带密度特征

    返回各故障类型 (BPFO/BPFI/BSF) 的边带密度、不对称性指标，
    供 _evaluate_bearing_faults 使用以增强故障类型区分。

    Args:
        env_freq: 包络谱频率轴
        env_amp: 包络谱幅值轴
        bearing_params: 轴承几何参数
        rot_freq: 转频 (Hz)

    Returns:
        Dict[str, Dict] — 各故障类型的边带分析结果
    """
    if not env_freq or not env_amp or rot_freq <= 0:
        return {}

    freq_arr = np.array(env_freq, dtype=np.float64)
    amp_arr = np.array(env_amp, dtype=np.float64)
    df = freq_arr[1] - freq_arr[0] if len(freq_arr) > 1 else 1.0
    background = float(np.median(amp_arr))

    # 计算故障频率
    has_params = bearing_params and any(v is not None for v in bearing_params.values())
    fault_freqs = {}
    ftf = 0.0

    if has_params:
        try:
            n = int(float(bearing_params.get("n") or 0))
            d = float(bearing_params.get("d") or 0)
            D = float(bearing_params.get("D") or 0)
            alpha = np.radians(float(bearing_params.get("alpha") or 0))
            if n > 0 and d > 0 and D > 0:
                cos_a = np.cos(alpha)
                dd = (d / D) * cos_a
                fault_freqs = {
                    "BPFO": (n / 2.0) * rot_freq * (1 - dd),
                    "BPFI": (n / 2.0) * rot_freq * (1 + dd),
                    "BSF": (D / (2.0 * d)) * rot_freq * (1 - dd ** 2),
                }
                ftf = 0.5 * rot_freq * (1 - dd)
        except (TypeError, ValueError):
            has_params = False

    if not fault_freqs:
        return {}

    results = {}
    for name, f_hz in fault_freqs.items():
        if f_hz <= 0 or f_hz > freq_arr[-1]:
            continue

        # BPFO/BPFI 的调制频率是转频 fr
        # BSF 的调制频率是保持架频率 FTF
        mod_freq = rot_freq if name != "BSF" else ftf

        density_result = compute_sideband_density(
            freq_arr, amp_arr, f_hz, mod_freq, background,
            max_harmonics=5, snr_threshold=3.0, df=df,
        )

        results[name] = {
            "sideband_density": density_result["density"],
            "sideband_significant_count": density_result["significant_count"],
            "sideband_asymmetry": density_result["asymmetry"],
            # 故障类型判定辅助
            "high_density": density_result["density"] >= 0.3,  # 内圈特征
            "low_density": density_result["density"] < 0.15,   # 外圈特征
            "high_asymmetry": density_result["asymmetry"] > 0.3,  # 内圈特征
        }

    return results