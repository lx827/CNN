"""
信号预处理与降噪模块

包含：
- 小波阈值去噪（软阈值/硬阈值/改进阈值）
- 倒频谱预白化（CPW）
- 最小熵解卷积（MED）
"""
import numpy as np
from scipy import signal as scipy_signal
from scipy.fft import rfft, irfft
from typing import Tuple, Optional, Literal
import pywt

from .signal_utils import prepare_signal, bandpass_filter, lowpass_filter
from .vmd_denoise import vmd_denoise, vmd_select_impact_mode


def wavelet_denoise(
    signal: np.ndarray,
    wavelet: str = "db8",
    level: Optional[int] = None,
    threshold_mode: Literal["soft", "hard", "improved"] = "soft",
    threshold_scale: float = 1.0,
) -> np.ndarray:
    """
    小波阈值去噪

    Args:
        signal: 输入信号
        wavelet: 小波基，轴承/齿轮冲击推荐 db8/sym8/coif5
        level: 分解层数，默认自动计算 floor(log2(N)) - 2
        threshold_mode: 阈值模式 soft/hard/improved
        threshold_scale: 阈值缩放系数

    Returns:
        去噪后的信号
    """
    arr = np.array(signal, dtype=np.float64)
    N = len(arr)

    if level is None:
        level = max(1, int(np.floor(np.log2(N))) - 2)
    level = min(level, pywt.dwt_max_level(N, pywt.Wavelet(wavelet).dec_len))

    # 小波分解
    coeffs = pywt.wavedec(arr, wavelet, level=level)

    # 用最后一层细节系数估计噪声标准差（鲁棒估计）
    detail = coeffs[-1]
    sigma = np.median(np.abs(detail)) / 0.6745
    if sigma < 1e-12:
        sigma = 1e-12

    # 通用阈值
    threshold = threshold_scale * sigma * np.sqrt(2 * np.log(N))

    # 对各层系数进行阈值处理（保留近似系数）
    denoised_coeffs = [coeffs[0]]  # 近似系数不变
    for i, detail_coeff in enumerate(coeffs[1:], 1):
        if threshold_mode == "soft":
            denoised = np.sign(detail_coeff) * np.maximum(np.abs(detail_coeff) - threshold, 0)
        elif threshold_mode == "hard":
            denoised = detail_coeff * (np.abs(detail_coeff) > threshold).astype(float)
        else:  # improved - 改进非线性阈值，抑制伪吉布斯振荡
            beta = 2.0
            abs_c = np.abs(detail_coeff)
            shrink = abs_c - threshold / (1 + np.exp(beta * (abs_c - threshold)))
            denoised = np.sign(detail_coeff) * np.maximum(shrink, 0)
        denoised_coeffs.append(denoised)

    # 重构
    return pywt.waverec(denoised_coeffs, wavelet)[:N]


def cepstrum_pre_whitening(
    signal: np.ndarray,
    fs: float,
    comb_frequencies: Optional[list] = None,
    notch_width_ratio: float = 0.02,
) -> np.ndarray:
    """
    倒频谱预白化（Cepstrum Pre-Whitening, CPW）

    消除齿轮啮合频率、轴频等确定性离散频率族，
    使被强齿轮分量掩盖的轴承冲击成分凸显。

    Args:
        signal: 输入信号
        fs: 采样率
        comb_frequencies: 需要抑制的确定性频率列表(Hz)，如 [mesh_freq, rot_freq]
        notch_width_ratio: 陷波宽度占倒频率的比例，默认 2%

    Returns:
        CPW 重构后的信号
    """
    arr = np.array(signal, dtype=np.float64)
    N = len(arr)

    # Step 1-3: FFT → 对数幅值 → 倒频谱
    X = np.fft.rfft(arr)
    log_mag = np.log(np.abs(X) + 1e-12)
    cepstrum = np.fft.irfft(log_mag, n=N)

    # Step 4: 倒频谱编辑（Comb Lifter）
    if comb_frequencies is not None and len(comb_frequencies) > 0:
        dt = 1.0 / fs
        quefrency = np.arange(N) * dt

        for f_target in comb_frequencies:
            if f_target is None or f_target <= 0:
                continue
            tau_target = 1.0 / f_target
            # 对该频率及其整数倍的倒频谱线进行陷波
            for k in range(1, int(N * dt * f_target) + 1):
                tau_k = k * tau_target
                if tau_k >= quefrency[-1]:
                    break
                # 陷波宽度
                half_w = notch_width_ratio * tau_k / 2
                mask = np.abs(quefrency - tau_k) <= half_w
                if np.any(mask):
                    # 用邻域均值替换（排除陷波区域内的点）
                    neighbor = ~mask
                    if np.any(neighbor):
                        cepstrum[mask] = np.mean(cepstrum[neighbor])

    # Step 5-6: 重构幅值谱 + 结合原始相位
    log_mag_new = np.fft.rfft(cepstrum).real
    # 限制范围避免数值爆炸
    log_mag_new = np.clip(log_mag_new, log_mag.min() - 2, log_mag.max() + 2)
    X_new = np.exp(log_mag_new) * np.exp(1j * np.angle(X))

    return np.fft.irfft(X_new, n=N)


def minimum_entropy_deconvolution(
    signal: np.ndarray,
    filter_len: int = 64,
    max_iter: int = 30,
    tol: float = 1e-6,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    最小熵解卷积（Minimum Entropy Deconvolution, MED）

    设计 FIR 逆滤波器使输出峭度最大化，增强故障冲击。
    基于 Endo & Randall (2007) 的迭代算法。

    Args:
        signal: 输入信号
        filter_len: FIR 滤波器长度
        max_iter: 最大迭代次数
        tol: 收敛容差

    Returns:
        (滤波后信号, 滤波器系数)
    """
    from scipy.linalg import toeplitz

    arr = np.array(signal, dtype=np.float64)
    N = len(arr)
    L = min(filter_len, N // 4)
    if L < 2:
        return arr.copy(), np.array([1.0])

    # 初始化滤波器（中心脉冲）
    f = np.zeros(L)
    f[L // 2] = 1.0

    prev_kurt = 0.0
    for _ in range(max_iter):
        # 计算输出（full 模式卷积后取前 N 点，与 Toeplitz 矩阵一致）
        x_hat = np.convolve(arr, f, mode='full')[:N]
        x_hat = x_hat - np.mean(x_hat)

        # 计算峭度
        var = np.var(x_hat)
        if var < 1e-12:
            break
        kurt = np.mean(x_hat ** 4) / (var ** 2)

        # 收敛判断
        if abs(kurt - prev_kurt) < tol:
            break
        prev_kurt = kurt

        # 构建输入信号的 Toeplitz 卷积矩阵 Y
        # Y[i,j] = arr[i-j]，其中越界位置为 0
        col = arr[:N]
        row = np.zeros(L)
        row[0] = arr[0]
        Y = toeplitz(col, row)[:N, :L]

        # 参考向量：输出立方（归一化）
        b = x_hat ** 3
        b = b / (np.linalg.norm(b) + 1e-12)

        # 求解正规方程得到新滤波器
        R = np.dot(Y.T, Y) / N + 1e-6 * np.eye(L)
        ryb = np.dot(Y.T, b) / N
        try:
            f_new = np.linalg.solve(R, ryb)
            f_new = f_new / (np.linalg.norm(f_new) + 1e-12)
        except np.linalg.LinAlgError:
            break
        f = f_new

    result = np.convolve(arr, f, mode='full')[:N]
    return result, f
