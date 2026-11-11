"""倒谱显示峰值分析；不包含机械故障阈值或健康结论。"""
from dataclasses import dataclass

import numpy as np
from scipy.signal import find_peaks

from .representation import CepstrumRepresentation


@dataclass(frozen=True)
class CepstrumPeak:
    quefrency_s: float
    amplitude: float

    @property
    def frequency_hz(self) -> float:
        """倒频率倒数对应的谱线间隔 Hz。"""
        return 1.0 / self.quefrency_s if self.quefrency_s > 0 else 0.0


@dataclass(frozen=True)
class CepstrumAnalysis:
    representation: CepstrumRepresentation
    peaks: tuple[CepstrumPeak, ...]


def analyze_cepstrum(
    representation: CepstrumRepresentation,
    *,
    max_quefrency_s: float = 0.5,
    search_min_s: float = 0.003,
    search_max_s: float = 0.2,
    min_peak_distance_bins: int = 50,
    relative_amplitude: float = 0.5,
    merge_tolerance_s: float = 0.003,
) -> CepstrumAnalysis:
    """先截断表示，再在指定倒频率区间提取局部峰。

    峰按幅值降序保留；低于最高峰 relative_amplitude 倍后停止，
    相距小于 merge_tolerance_s 的峰合并。参数是显示峰值选择规则，
    不是轴承/齿轮故障显著性阈值。
    """
    if not 0 <= search_min_s < search_max_s:
        raise ValueError("倒谱搜索区间必须满足 0 <= 下限 < 上限")
    if isinstance(min_peak_distance_bins, bool) or not isinstance(min_peak_distance_bins, int) \
            or min_peak_distance_bins <= 0:
        raise ValueError("倒谱峰最小间距必须是正整数")
    if not np.isfinite(relative_amplitude) or not 0 <= relative_amplitude <= 1:
        raise ValueError("倒谱峰相对幅值必须位于 [0, 1]")
    if not np.isfinite(merge_tolerance_s) or merge_tolerance_s < 0:
        raise ValueError("倒谱峰合并容差必须是有限非负数")

    truncated = representation.truncated(max_quefrency_s)
    quefrency = truncated.quefrency_s
    amplitude = truncated.amplitude
    peaks: list[CepstrumPeak] = []
    if len(amplitude) > 10:
        search_mask = (quefrency >= search_min_s) & (quefrency <= search_max_s)
        search_amplitude = amplitude[search_mask]
        search_quefrency = quefrency[search_mask]
        if len(search_amplitude) > 10:
            indices, _ = find_peaks(search_amplitude, distance=min_peak_distance_bins)
            ordered = sorted(indices, key=lambda index: search_amplitude[index], reverse=True)
            top_amplitude = None
            for index in ordered:
                value = float(search_amplitude[index])
                if top_amplitude is None:
                    top_amplitude = value
                elif value < top_amplitude * relative_amplitude:
                    break
                quefrency_s = float(search_quefrency[index])
                if any(abs(item.quefrency_s - quefrency_s) < merge_tolerance_s for item in peaks):
                    continue
                peaks.append(CepstrumPeak(quefrency_s=quefrency_s, amplitude=value))
    return CepstrumAnalysis(representation=truncated, peaks=tuple(peaks))
