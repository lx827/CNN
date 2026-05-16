"""
信号预处理与降噪模块

包含：
- 小波阈值去噪（软阈值/硬阈值/改进阈值）
- 倒频谱预白化（CPW）
- 最小熵解卷积（MED）
- 联合降噪策略（wavelet+VMD 级联等组合）
"""
import numpy as np
from scipy import signal as scipy_signal
from scipy.fft import rfft, irfft
from typing import Tuple, Optional, Literal, Dict
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


# ---------------------------------------------------------------------------
# 联合降噪策略
# ---------------------------------------------------------------------------


def cascade_wavelet_vmd(
    signal: np.ndarray,
    wavelet: str = "db8",
    wavelet_level: Optional[int] = None,
    wavelet_mode: Literal["soft", "hard", "improved"] = "soft",
    vmd_K: int = 5,
    vmd_alpha: int = 2000,
    vmd_corr_threshold: float = 0.3,
    vmd_kurt_threshold: float = 3.0,
) -> Tuple[np.ndarray, Dict]:
    """
    小波 + VMD 级联联合降噪

    ALGORITHMS.md §4.2.5 推荐组合：
    "强高斯白噪声：小波阈值 + VMD"
    小波先去除白噪声，VMD 再分离非平稳成分。

    算法流程：
    1. 小波阈值去噪 → 去除大部分高频白噪声
    2. VMD 分解 → 将去噪后的信号分解为 K 个 IMF
    3. IMF 筛选 → 保留相关性 > 0.3 或峭度 > 3.0 的 IMF
    4. 重构 → 由筛选后的 IMF 重构最终去噪信号

    Args:
        signal: 输入信号
        wavelet: 小波基
        wavelet_level: 小波分解层数
        wavelet_mode: 小波阈值模式
        vmd_K: VMD 模态数
        vmd_alpha: VMD 惩罚因子
        vmd_corr_threshold: IMF 相关系数阈值
        vmd_kurt_threshold: IMF 峭度阈值

    Returns:
        (去噪信号, 元信息字典)
    """
    arr = np.array(signal, dtype=np.float64)
    N = len(arr)

    # Step 1: 小波阈值去噪
    wavelet_result = wavelet_denoise(
        arr, wavelet=wavelet, level=wavelet_level,
        threshold_mode=wavelet_mode
    )

    # Step 2-4: VMD 分解 + 筛选重构
    vmd_result = vmd_denoise(
        wavelet_result, K=vmd_K, alpha=vmd_alpha,
        corr_threshold=vmd_corr_threshold,
        kurt_threshold=vmd_kurt_threshold
    )

    # 计算指标
    kurt_before = float(np.mean(arr ** 4) / (np.var(arr) ** 2 + 1e-12))
    kurt_wavelet = float(np.mean(wavelet_result ** 4) / (np.var(wavelet_result) ** 2 + 1e-12))
    kurt_final = float(np.mean(vmd_result ** 4) / (np.var(vmd_result) ** 2 + 1e-12))

    noise_reduction = float(np.var(arr) / (np.var(vmd_result) + 1e-12))

    return vmd_result, {
        "method": "cascade_wavelet_vmd",
        "wavelet": wavelet,
        "wavelet_mode": wavelet_mode,
        "vmd_K": vmd_K,
        "vmd_alpha": vmd_alpha,
        "kurtosis_before": round(kurt_before, 4),
        "kurtosis_after_wavelet": round(kurt_wavelet, 4),
        "kurtosis_after_cascade": round(kurt_final, 4),
        "noise_reduction_ratio": round(noise_reduction, 4),
    }


def cascade_wavelet_lms(
    signal: np.ndarray,
    wavelet: str = "db8",
    wavelet_level: Optional[int] = None,
    wavelet_mode: Literal["soft", "hard", "improved"] = "soft",
    lms_filter_len: int = 32,
    lms_step_size: float = 0.01,
    lms_delay: int = 1,
) -> Tuple[np.ndarray, Dict]:
    """
    小波 + LMS 级联联合降噪

    ALGORITHMS.md §4.2.5 推荐组合：
    "强脉冲型干扰：LMS + 中值滤波"
    本实现用小波替代中值滤波（更通用），组成 wavelet+LMS 级联。

    算法流程：
    1. 小波阈值去噪 → 去除宽带噪声
    2. LMS 自适应滤波 → 去除与小波去噪后残留相关的周期性噪声

    Args:
        signal: 输入信号
        wavelet: 小波基
        wavelet_level: 分解层数
        wavelet_mode: 阈值模式
        lms_filter_len: LMS 滤波器长度
        lms_step_size: LMS 步长
        lms_delay: LMS 参考延迟

    Returns:
        (去噪信号, 元信息字典)
    """
    from .lms_filter import lms_filter

    arr = np.array(signal, dtype=np.float64)

    # Step 1: 小波阈值去噪
    wavelet_result = wavelet_denoise(
        arr, wavelet=wavelet, level=wavelet_level,
        threshold_mode=wavelet_mode
    )

    # Step 2: LMS 自适应滤波
    lms_result, lms_info = lms_filter(
        wavelet_result, filter_len=lms_filter_len,
        step_size=lms_step_size, delay=lms_delay
    )

    # 计算指标
    kurt_before = float(np.mean(arr ** 4) / (np.var(arr) ** 2 + 1e-12))
    kurt_final = float(np.mean(lms_result ** 4) / (np.var(lms_result) ** 2 + 1e-12))
    noise_reduction = float(np.var(arr) / (np.var(lms_result) + 1e-12))

    return lms_result, {
        "method": "cascade_wavelet_lms",
        "wavelet": wavelet,
        "wavelet_mode": wavelet_mode,
        "lms_filter_len": lms_filter_len,
        "lms_step_size": lms_step_size,
        "kurtosis_before": round(kurt_before, 4),
        "kurtosis_after_cascade": round(kurt_final, 4),
        "noise_reduction_ratio": round(noise_reduction, 4),
        **lms_info,
    }


def joint_denoise(
    signal: np.ndarray,
    strategy: Literal[
        "wavelet_vmd", "wavelet_lms", "wavelet", "vmd",
        "ceemdan_wp", "eemd",
    ] = "wavelet_vmd",
    wavelet: str = "db8",
    wavelet_level: Optional[int] = None,
    wavelet_mode: Literal["soft", "hard", "improved"] = "soft",
    vmd_K: int = 5,
    vmd_alpha: int = 2000,
    lms_filter_len: int = 32,
    lms_step_size: float = 0.01,
) -> Tuple[np.ndarray, Dict]:
    """
    联合降噪统一入口

    ALGORITHMS.md §4.2.5 联合降噪策略推荐：
    | 场景 | 推荐组合 | 作用 |
    | 强高斯白噪声 | 小波阈值 + VMD | 小波去除白噪声，VMD分离非平稳成分 |
    | 强脉冲型干扰 | LMS + 中值滤波 | LMS 抑制平稳噪声，中值滤波剔除脉冲 |

    Args:
        signal: 输入信号
        strategy: 降噪策略
            - "wavelet_vmd": 小波+VMD 级联（推荐强高斯噪声场景）
            - "wavelet_lms": 小波+LMS 级联（推荐脉冲干扰场景）
            - "wavelet": 仅小波去噪
            - "vmd": 仅 VMD 去噪

    Returns:
        (去噪信号, 元信息字典)
    """
    arr = np.array(signal, dtype=np.float64)

    if strategy == "wavelet_vmd":
        return cascade_wavelet_vmd(
            arr, wavelet=wavelet, wavelet_level=wavelet_level,
            wavelet_mode=wavelet_mode, vmd_K=vmd_K, vmd_alpha=vmd_alpha
        )
    elif strategy == "wavelet_lms":
        return cascade_wavelet_lms(
            arr, wavelet=wavelet, wavelet_level=wavelet_level,
            wavelet_mode=wavelet_mode, lms_filter_len=lms_filter_len,
            lms_step_size=lms_step_size
        )
    elif strategy == "wavelet":
        result = wavelet_denoise(
            arr, wavelet=wavelet, level=wavelet_level,
            threshold_mode=wavelet_mode
        )
        kurt_before = float(np.mean(arr ** 4) / (np.var(arr) ** 2 + 1e-12))
        kurt_after = float(np.mean(result ** 4) / (np.var(result) ** 2 + 1e-12))
        return result, {
            "method": "wavelet",
            "kurtosis_before": round(kurt_before, 4),
            "kurtosis_after": round(kurt_after, 4),
        }
    elif strategy == "vmd":
        result = vmd_denoise(arr, K=vmd_K, alpha=vmd_alpha)
        kurt_before = float(np.mean(arr ** 4) / (np.var(arr) ** 2 + 1e-12))
        kurt_after = float(np.mean(result ** 4) / (np.var(result) ** 2 + 1e-12))
        return result, {
            "method": "vmd",
            "kurtosis_before": round(kurt_before, 4),
            "kurtosis_after": round(kurt_after, 4),
        }
    elif strategy == "ceemdan_wp":
        # CEEMDAN + 小波包级联（§14.1）
        # CEEMDAN 先抑制模态混叠 → 小波包进一步频带筛选重构
        from .emd_denoise import emd_denoise
        from .wavelet_packet import wavelet_packet_denoise
        step1, info1 = emd_denoise(arr, method="ceemdan", ensemble_size=30)
        step2, info2 = wavelet_packet_denoise(step1, wavelet=wavelet, level=3)
        kurt_before = float(np.mean(arr ** 4) / (np.var(arr) ** 2 + 1e-12))
        kurt_after = float(np.mean(step2 ** 4) / (np.var(step2) ** 2 + 1e-12))
        return step2, {
            "method": "ceemdan_wp",
            "ceemdan_info": info1,
            "wp_info": info2,
            "kurtosis_before": round(kurt_before, 4),
            "kurtosis_after": round(kurt_after, 4),
        }
    elif strategy == "eemd":
        from .emd_denoise import emd_denoise
        result, info = emd_denoise(arr, method="eemd", ensemble_size=30)
        kurt_before = float(np.mean(arr ** 4) / (np.var(arr) ** 2 + 1e-12))
        kurt_after = float(np.mean(result ** 4) / (np.var(result) ** 2 + 1e-12))
        return result, {
            "method": "eemd",
            "emd_info": info,
            "kurtosis_before": round(kurt_before, 4),
            "kurtosis_after": round(kurt_after, 4),
        }
    else:
        return arr, {"method": "none"}
