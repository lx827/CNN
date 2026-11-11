"""基于 Chirp-Z 的窄带密集频率采样，不虚构超分辨率。"""
from __future__ import annotations

import numpy as np
from scipy.signal import czt, windows

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
    """
    values = np.asarray(signal, dtype=np.float64)
    if values.ndim != 1 or len(values) < 64 or not np.all(np.isfinite(values)):
        raise ValueError("Chirp-Z 输入必须是一维、至少 64 点的有限信号")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("采样率必须是有限正数")
    low = parameters.center_frequency_hz - parameters.bandwidth_hz / 2.0
    high = parameters.center_frequency_hz + parameters.bandwidth_hz / 2.0
    if low < 0 or high > sample_rate_hz / 2 or high <= low:
        raise ValueError("Chirp-Z 频带必须完整位于 [0, fs/2] 内")
    count = len(values)
    points = parameters.output_points
    step = (high - low) / points
    # scipy czt 的第 k 点为 sum_n x[n]·exp(-j2πf_k n/fs)。
    transform = czt(
        values * windows.hann(count, sym=False),
        m=points,
        w=np.exp(-2j * np.pi * step / sample_rate_hz),
        a=np.exp(2j * np.pi * low / sample_rate_hz),
    )
    amplitude = np.abs(transform) * (2.0 / np.sum(windows.hann(count, sym=False)))
    frequencies = low + np.arange(points, dtype=np.float64) * step
    if np.isclose(frequencies[0], 0.0):
        amplitude[0] *= 0.5
    if np.isclose(high, sample_rate_hz / 2) and points % 2 == 0:
        # 高频端点不包含在 CZT 网格中，通常没有 Nyquist 点；只有恰好命中才减半。
        nyquist_indices = np.flatnonzero(np.isclose(frequencies, sample_rate_hz / 2))
        amplitude[nyquist_indices] *= 0.5
    return ZoomSpectrum(
        spectrum=Spectrum(
            frequency_hz=frequencies,
            amplitude=np.asarray(amplitude, dtype=np.float64),
            scaling="single_sided_amplitude",
        ),
        rayleigh_resolution_hz=float(sample_rate_hz / count),
        frequency_step_hz=float(step),
        original_frequency_step_hz=float(sample_rate_hz / count),
    )
