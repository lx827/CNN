"""基于 Chirp-Z 的窄带密集频率采样，不虚构超分辨率。"""

from __future__ import annotations

from cnn_compute import rotation as native

import numpy as np

from app.algorithms.core import Spectrum

from .types import ZoomParameters, ZoomSpectrum


def compute_zoom_spectrum(
    signal: np.ndarray,
    sample_rate_hz: float,
    parameters: ZoomParameters,
) -> ZoomSpectrum:
    """在 [fc-B/2, fc+B/2) 上直接计算 Chirp-Z，频率轴始终递增。

    `frequency_step_hz` 是 CZT 网格间隔；`rayleigh_resolution_hz=fs/N`
    才是由有效记录长度决定的分辨能力。增加 output_points 只加密网格，
    不在同一 N 上宣称把物理分辨率提高 zoom_factor 倍。若需分开小于
    fs/N 的谱峰，必须提供更长的有效记录或其他经过验证的参数模型。
    上限排除，即使上限为Nyquist，末点仍按普通正频率单边幅值刻度；
    只有实际位于0 Hz的DC点不翻倍。
    """
    values = np.asarray(signal, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError("Chirp-Z 输入必须是一维信号")
    low = parameters.center_frequency_hz - parameters.bandwidth_hz / 2
    high = parameters.center_frequency_hz + parameters.bandwidth_hz / 2
    amplitude = native.zoom_spectrum(values, sample_rate_hz, low, high, parameters.output_points)
    step = parameters.bandwidth_hz / parameters.output_points
    frequencies = low + np.arange(parameters.output_points, dtype=np.float64) * step
    return ZoomSpectrum(spectrum=Spectrum(frequency_hz=frequencies, amplitude=amplitude,
        scaling="single_sided_amplitude"), rayleigh_resolution_hz=float(sample_rate_hz / len(values)),
        frequency_step_hz=float(step), original_frequency_step_hz=float(sample_rate_hz / len(values)))
