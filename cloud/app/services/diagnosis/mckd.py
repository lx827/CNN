"""
MCKD (Maximum Correlated Kurtosis Deconvolution)
最大相关峭度解卷积模块

与现有 MED 形成互补：
- MED 最大化全局峭度，增强孤立冲击，但可能放大随机大脉冲；
- MCKD 引入故障周期 T，优化"周期性冲击序列"的检测，
  对轴承外圈/内圈故障更敏感。

参考: McDonald et al. (2012)
"""
import numpy as np
from scipy.linalg import toeplitz
from typing import Tuple, Dict


def mckd_deconvolution(
    signal: np.ndarray,
    filter_len: int = 64,
    period_T: int = 100,
    shift_order_M: int = 1,
    max_iter: int = 30,
    tol: float = 1e-6,
) -> Tuple[np.ndarray, np.ndarray, Dict]:
    """
    最大相关峭度解卷积 (MCKD)

    Args:
        signal: 输入信号
        filter_len: FIR滤波器长度 L
        period_T: 故障冲击周期（采样点数）
        shift_order_M: 移位阶数（建议1~3）
        max_iter: 最大迭代次数
        tol: 收敛容差

    Returns:
        (滤波后信号, 滤波器系数, 元信息)
    """
    arr = np.array(signal, dtype=np.float64)
    N = len(arr)
    L = min(filter_len, N // 4)
    if L < 2 or period_T <= 0 or period_T >= N // 2:
        return arr.copy(), np.array([1.0]), {"error": "invalid_params"}

    col = arr[:N - L + 1]
    row = np.zeros(L)
    row[0] = arr[0]
    X0 = toeplitz(col, row)

    f = np.zeros(L)
    f[L // 2] = 1.0

    prev_ck = 0.0
    it = 0
    for it in range(max_iter):
        y = X0 @ f
        y = y - np.mean(y)
        y_power = np.sum(y ** 2) + 1e-12

        valid_len = len(y) - shift_order_M * period_T
        if valid_len <= 0:
            break

        y_delayed = np.zeros((shift_order_M + 1, valid_len))
        for m in range(shift_order_M + 1):
            y_delayed[m, :] = y[m * period_T : m * period_T + valid_len]

        product = np.prod(y_delayed, axis=0)
        numerator = float(np.sum(product))
        ck = numerator / (y_power ** (shift_order_M + 1))

        if abs(ck - prev_ck) < tol:
            break
        prev_ck = ck

        alpha_sum = np.zeros(len(y))
        for m in range(shift_order_M + 1):
            pad_left = m * period_T
            pad_right = len(y) - valid_len - pad_left
            alpha_m = np.pad(product, (pad_left, pad_right), mode='constant')
            alpha_sum += alpha_m

        R = (X0.T @ X0) / len(y) + 1e-6 * np.eye(L)
        rhs = (X0.T @ alpha_sum) / len(y)
        try:
            f_new = np.linalg.solve(R, rhs)
            f_new = f_new / (np.linalg.norm(f_new) + 1e-12)
        except np.linalg.LinAlgError:
            break
        f = f_new

    result = np.convolve(arr, f, mode='same')
    return result, f, {
        "method": "MCKD",
        "period_T": period_T,
        "shift_order_M": shift_order_M,
        "filter_len": L,
        "correlated_kurtosis": round(float(prev_ck), 6),
        "iterations": it + 1,
    }


def mckd_envelope_analysis(
    signal: np.ndarray,
    fs: float,
    bearing_params: Dict,
    rot_freq: float,
    filter_len: int = 64,
    shift_order_M: int = 1,
    max_freq: float = 1000.0,
) -> Dict:
    """
    MCKD + 包络分析完整流程
    """
    from .bearing import envelope_analysis
    from .preprocessing import minimum_entropy_deconvolution

    n = int(float(bearing_params.get("n") or 0))
    d = float(bearing_params.get("d") or 0)
    D = float(bearing_params.get("D") or 0)
    alpha_deg = float(bearing_params.get("alpha") or 0)

    if n <= 0 or d <= 0 or D <= 0:
        # 无参数时退化为 MED
        med_sig, _ = minimum_entropy_deconvolution(signal, filter_len=filter_len)
        result = envelope_analysis(med_sig, fs, max_freq=max_freq)
        result["method"] = "MED + Envelope (MCKD fallback: no params)"
        return result

    alpha = np.radians(alpha_deg)
    cos_a = np.cos(alpha)
    dd = (d / D) * cos_a
    bpfo = (n / 2.0) * rot_freq * (1 - dd)
    bpfi = (n / 2.0) * rot_freq * (1 + dd)

    target_freq = bpfo if bpfo > 0 else bpfi
    period_T = max(3, int(round(fs / target_freq)))

    mckd_sig, _, mckd_info = mckd_deconvolution(
        signal, filter_len=filter_len, period_T=period_T, shift_order_M=shift_order_M
    )

    result = envelope_analysis(mckd_sig, fs, max_freq=max_freq)
    result["mckd_info"] = mckd_info
    result["method"] = "MCKD + Envelope"
    result["target_fault_freq_hz"] = round(target_freq, 2)
    return result
