"""定轴 CAR 实倒谱表示与幅值比；与 CPW 预白化完全分离。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.fft import fft, ifft
from scipy.signal import windows

from .types import CepstrumRepresentation, MetricValue


@dataclass(frozen=True)
class CARParameters:
    """倒频率搜索容差直接以秒表示，禁止 tolerance_hz 倒数换算。"""

    n_harmonics: int = 3
    tolerance_s: float = 0.002

    def __post_init__(self) -> None:
        if isinstance(self.n_harmonics, bool) or self.n_harmonics < 1:
            raise ValueError("CAR 谐波数必须为正整数")
        if not np.isfinite(self.tolerance_s) or self.tolerance_s <= 0:
            raise ValueError("CAR 倒频率容差必须是有限正数，单位秒")


def compute_real_cepstrum(
    signal: np.ndarray,
    sample_rate_hz: float,
) -> CepstrumRepresentation:
    """c(τ)=Re{IFFT(log(|FFT(w·(x-mean(x))|)))}，τ 单位为秒。"""
    values = np.asarray(signal, dtype=np.float64)
    if values.ndim != 1 or len(values) < 64 or not np.all(np.isfinite(values)):
        raise ValueError("CAR 输入必须是一维、至少 64 点的有限信号")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("采样率必须是有限正数")
    centered = values - np.mean(values)
    windowed = centered * windows.hann(len(values), sym=False)
    magnitude = np.abs(fft(windowed))
    floor = max(float(np.max(magnitude)) * 1e-12, np.finfo(np.float64).tiny)
    log_spectrum = np.log(np.maximum(magnitude, floor))
    log_spectrum -= np.mean(log_spectrum)
    cepstrum = np.real(ifft(log_spectrum))
    half = len(values) // 2 + 1
    quefrency = np.arange(half, dtype=np.float64) / sample_rate_hz
    return CepstrumRepresentation(
        quefrency_s=quefrency,
        amplitude=np.asarray(cepstrum[:half], dtype=np.float64),
        sample_rate_hz=float(sample_rate_hz),
    )


def compute_car(
    cepstrum: CepstrumRepresentation,
    rot_frequency_hz: float,
    parameters: CARParameters = CARParameters(),
) -> MetricValue:
    """CAR=目标倒频率窗内 |c| 峰值均值/独立背景 |c| 中位数。

    第 k 个目标为 τ=k/fr 秒；背景从最后一个目标窗外开始，排除所有
    目标窗。该全局周期性指标要求准确恒速，只反映周期族相对背景的
    强度，不能单独定位到齿轮、轴或某种故障。
    """
    if not np.isfinite(rot_frequency_hz) or rot_frequency_hz <= 0:
        return MetricValue.unavailable("CAR", "invalid_constant_rot_frequency")
    quefrency = cepstrum.quefrency_s
    amplitude = np.abs(cepstrum.amplitude)
    targets = (
        np.arange(1, parameters.n_harmonics + 1, dtype=np.float64) / rot_frequency_hz
    )
    maximum_quefrency = float(quefrency[-1])
    if targets[-1] + parameters.tolerance_s > maximum_quefrency:
        return MetricValue.unavailable(
            "CAR",
            "target_quefrency_above_cepstrum_coverage",
            maximum_target_quefrency_s=float(targets[-1] + parameters.tolerance_s),
            available_quefrency_s=maximum_quefrency,
        )
    excluded = np.zeros(len(quefrency), dtype=bool)
    peak_values = []
    peak_quefrencies = []
    for target in targets:
        mask = np.abs(quefrency - target) <= parameters.tolerance_s
        if not np.any(mask):
            return MetricValue.unavailable(
                "CAR",
                "target_quefrency_not_resolvable",
                target_quefrency_s=float(target),
            )
        excluded |= mask
        local_indices = np.flatnonzero(mask)
        local_peak = int(local_indices[np.argmax(amplitude[mask])])
        peak_values.append(float(amplitude[local_peak]))
        peak_quefrencies.append(float(quefrency[local_peak]))
    background_mask = (quefrency > targets[-1] + parameters.tolerance_s) & ~excluded
    if np.sum(background_mask) < 8:
        return MetricValue.unavailable(
            "CAR", "insufficient_independent_cepstrum_background"
        )
    background = float(np.median(amplitude[background_mask]))
    if background <= np.finfo(np.float64).tiny:
        return MetricValue.unavailable("CAR", "zero_cepstrum_background")
    return MetricValue(
        name="CAR",
        status="evaluated",
        value=float(np.mean(peak_values) / background),
        details={
            "target_quefrencies_s": targets.tolist(),
            "peak_quefrencies_s": peak_quefrencies,
            "peak_absolute_amplitudes": peak_values,
            "background_median_absolute_amplitude": background,
            "tolerance_s": parameters.tolerance_s,
            "background_definition": "median_abs_above_last_target_and_outside_all_target_windows",
            "operating_condition": "accurate_constant_speed_only",
            "localization": "global_periodicity_not_fault_localizing",
            "distinct_from": "cepstrum_pre_whitening",
        },
    )
