"""联合去噪的业务编排；小波、MED/CPW 数学实现统一位于 algorithms。"""

import numpy as np
from typing import Tuple, Optional, Literal, Dict

from app.algorithms.decomposition.wavelet import denoise_wavelet
from .vmd_denoise import vmd_denoise


def cascade_wavelet_vmd(
    signal: np.ndarray,
    wavelet: str = "db8",
    wavelet_level: Optional[int] = None,
    wavelet_mode: Literal["soft", "hard", "improved"] = "soft",
    wavelet_threshold_scale: float = 0.5,
    vmd_K: int = 5,
    vmd_alpha: int = 2000,
    vmd_corr_threshold: float = 0.3,
    vmd_kurt_threshold: float = 3.0,
) -> Tuple[np.ndarray, Dict]:
    """
    小波 + VMD 级联联合降噪

    docs/算法原理.md §4.2.5 推荐组合：
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
        wavelet_threshold_scale: 小波阈值缩放系数（级联场景默认 0.5，避免过度去噪）
        vmd_K: VMD 模态数
        vmd_alpha: VMD 惩罚因子
        vmd_corr_threshold: IMF 相关系数阈值
        vmd_kurt_threshold: IMF 峭度阈值

    Returns:
        (去噪信号, 元信息字典)
    """
    arr = np.array(signal, dtype=np.float64)
    N = len(arr)

    # Step 1: 小波阈值去噪（级联场景降低阈值，避免过度去噪扭曲信号结构）
    wavelet_result = denoise_wavelet(
        arr,
        wavelet=wavelet,
        level=wavelet_level,
        threshold_mode=wavelet_mode,
        threshold_scale=wavelet_threshold_scale,
    )

    # Step 2-4: VMD 分解 + 筛选重构
    # 传入原始信号作为 reference_signal，避免 IMF 与"已失真小波输出"的相关性被低估（Bug #14）
    vmd_result = vmd_denoise(
        wavelet_result,
        K=vmd_K,
        alpha=vmd_alpha,
        corr_threshold=vmd_corr_threshold,
        kurt_threshold=vmd_kurt_threshold,
        reference_signal=arr,
    )

    # 计算指标
    kurt_before = float(np.mean(arr**4) / (np.var(arr) ** 2 + 1e-12))
    kurt_wavelet = float(
        np.mean(wavelet_result**4) / (np.var(wavelet_result) ** 2 + 1e-12)
    )
    kurt_final = float(np.mean(vmd_result**4) / (np.var(vmd_result) ** 2 + 1e-12))

    noise_reduction = float(np.var(arr) / (np.var(vmd_result) + 1e-12))

    return vmd_result, {
        "method": "cascade_wavelet_vmd",
        "wavelet": wavelet,
        "wavelet_mode": wavelet_mode,
        "wavelet_threshold_scale": wavelet_threshold_scale,
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

    docs/算法原理.md §4.2.5 推荐组合：
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
    wavelet_result = denoise_wavelet(
        arr, wavelet=wavelet, level=wavelet_level, threshold_mode=wavelet_mode
    )

    # Step 2: LMS 自适应滤波
    lms_result, lms_info = lms_filter(
        wavelet_result,
        filter_len=lms_filter_len,
        step_size=lms_step_size,
        delay=lms_delay,
    )

    # 计算指标
    kurt_before = float(np.mean(arr**4) / (np.var(arr) ** 2 + 1e-12))
    kurt_final = float(np.mean(lms_result**4) / (np.var(lms_result) ** 2 + 1e-12))
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
        "wavelet_vmd",
        "wavelet_lms",
        "wavelet",
        "vmd",
        "ceemdan_wp",
        "eemd",
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

    docs/算法原理.md §4.2.5 联合降噪策略推荐：
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
            arr,
            wavelet=wavelet,
            wavelet_level=wavelet_level,
            wavelet_mode=wavelet_mode,
            vmd_K=vmd_K,
            vmd_alpha=vmd_alpha,
        )
    elif strategy == "wavelet_lms":
        return cascade_wavelet_lms(
            arr,
            wavelet=wavelet,
            wavelet_level=wavelet_level,
            wavelet_mode=wavelet_mode,
            lms_filter_len=lms_filter_len,
            lms_step_size=lms_step_size,
        )
    elif strategy == "wavelet":
        result = denoise_wavelet(
            arr, wavelet=wavelet, level=wavelet_level, threshold_mode=wavelet_mode
        )
        kurt_before = float(np.mean(arr**4) / (np.var(arr) ** 2 + 1e-12))
        kurt_after = float(np.mean(result**4) / (np.var(result) ** 2 + 1e-12))
        return result, {
            "method": "wavelet",
            "kurtosis_before": round(kurt_before, 4),
            "kurtosis_after": round(kurt_after, 4),
        }
    elif strategy == "vmd":
        result = vmd_denoise(arr, K=vmd_K, alpha=vmd_alpha)
        kurt_before = float(np.mean(arr**4) / (np.var(arr) ** 2 + 1e-12))
        kurt_after = float(np.mean(result**4) / (np.var(result) ** 2 + 1e-12))
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
        kurt_before = float(np.mean(arr**4) / (np.var(arr) ** 2 + 1e-12))
        kurt_after = float(np.mean(step2**4) / (np.var(step2) ** 2 + 1e-12))
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
        kurt_before = float(np.mean(arr**4) / (np.var(arr) ** 2 + 1e-12))
        kurt_after = float(np.mean(result**4) / (np.var(result) ** 2 + 1e-12))
        return result, {
            "method": "eemd",
            "emd_info": info,
            "kurtosis_before": round(kurt_before, 4),
            "kurtosis_after": round(kurt_after, 4),
        }
    else:
        raise ValueError(f"未知联合去噪策略: {strategy}")
