"""转频估计：标量候选与 STFT 连续转速轨迹分开建模。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
from numpy.typing import NDArray
from scipy import signal as scipy_signal
from scipy.fft import rfft, rfftfreq

from .types import RidgeParameters, ScalarSpeed, SpeedSearchRange, SpeedTrajectory


FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class SpeedTrajectoryEstimate:
    status: str
    trajectory: Optional[SpeedTrajectory]
    reliable_frame_count: int
    total_frame_count: int
    reason: Optional[str] = None

    @classmethod
    def failed(
        cls, reason: str, reliable: int = 0, total: int = 0
    ) -> "SpeedTrajectoryEstimate":
        return cls("indeterminate", None, reliable, total, reason)


@dataclass(frozen=True)
class _Candidate:
    frequency_hz: float
    method: str


def _prepare(signal: FloatArray) -> FloatArray:
    arr = np.asarray(signal, dtype=np.float64)
    if arr.ndim != 1:
        raise ValueError("转频估计输入必须是一维信号")
    if len(arr) == 0 or not np.all(np.isfinite(arr)):
        raise ValueError("转频估计输入不能为空或包含非有限值")
    return arr - np.mean(arr)


def _validate_sample_rate(fs: float) -> None:
    if not np.isfinite(fs) or fs <= 0:
        raise ValueError("采样率必须是有限正数")


def _search_peak(
    axis: FloatArray, values: FloatArray, low: float, high: float
) -> Optional[int]:
    indices = np.flatnonzero((axis >= low) & (axis <= high))
    if len(indices) == 0:
        return None
    return int(indices[int(np.argmax(values[indices]))])


def _parabolic_frequency(freqs: FloatArray, spectrum: FloatArray, index: int) -> float:
    if index <= 0 or index >= len(spectrum) - 1:
        return float(freqs[index])
    alpha, beta, gamma = spectrum[index - 1 : index + 2]
    denominator = alpha - 2 * beta + gamma
    if denominator == 0 or beta <= max(alpha, gamma):
        return float(freqs[index])
    offset = 0.5 * (alpha - gamma) / denominator
    return float(freqs[index] + offset * (freqs[1] - freqs[0]))


def _bandpass(signal: FloatArray, fs: float, low: float, high: float) -> FloatArray:
    if len(signal) < 28 or low <= 0 or high >= fs / 2 or low >= high:
        return signal
    sos = scipy_signal.butter(4, [low, high], btype="bandpass", fs=fs, output="sos")
    return scipy_signal.sosfiltfilt(sos, signal)


def estimate_envelope_speed(
    signal: FloatArray,
    sample_rate_hz: float,
    carrier_frequency_hz: float,
    search: SpeedSearchRange = SpeedSearchRange(),
    bandwidth_hz: float = 60.0,
) -> ScalarSpeed:
    """对指定载波频带做 Hilbert 包络，返回独立的标量候选。"""
    _validate_sample_rate(sample_rate_hz)
    arr = _prepare(signal)
    low = max(search.low_hz, carrier_frequency_hz - bandwidth_hz)
    high = min(sample_rate_hz / 2 - 1e-6, carrier_frequency_hz + bandwidth_hz)
    if len(arr) < 32 or low >= high:
        return ScalarSpeed.indeterminate("envelope", "包络频带或信号长度无效")
    try:
        filtered = _bandpass(arr, sample_rate_hz, low, high)
        envelope = np.abs(scipy_signal.hilbert(filtered))
        envelope -= np.mean(envelope)
        spectrum = np.abs(rfft(envelope))
        frequencies = rfftfreq(len(envelope), 1.0 / sample_rate_hz)
        index = _search_peak(frequencies, spectrum, search.low_hz, search.high_hz)
        if index is None or spectrum[index] <= np.finfo(float).eps:
            return ScalarSpeed.indeterminate("envelope", "包络谱搜索范围内无谱峰")
        return ScalarSpeed(float(frequencies[index]), "envelope")
    except (ValueError, FloatingPointError) as exc:
        return ScalarSpeed.indeterminate("envelope", f"包络估计失败: {exc}")


def estimate_autocorrelation_speed(
    signal: FloatArray,
    sample_rate_hz: float,
    search: SpeedSearchRange = SpeedSearchRange(),
) -> ScalarSpeed:
    """用归一化自相关的显著滞后峰产生标量转频候选。"""
    _validate_sample_rate(sample_rate_hz)
    arr = _prepare(signal)
    if len(arr) < 16 or np.std(arr) <= np.finfo(float).eps:
        return ScalarSpeed.indeterminate("autocorrelation", "信号过短或没有有效变化")
    high = min(sample_rate_hz / 2 - 1e-6, max(search.high_hz * 6, search.high_hz + 20))
    low = max(1e-6, search.low_hz * 0.5)
    if low < high:
        try:
            arr = _bandpass(arr, sample_rate_hz, low, high)
        except ValueError:
            pass
    arr = arr / (np.std(arr) + 1e-12)
    correlation = scipy_signal.correlate(arr, arr, mode="full", method="fft")
    correlation = correlation[len(correlation) // 2 :]
    if correlation[0] <= 0:
        return ScalarSpeed.indeterminate("autocorrelation", "零滞后自相关无效")
    correlation = correlation / correlation[0]
    min_lag = max(1, int(sample_rate_hz / search.high_hz))
    max_lag = min(len(correlation) - 1, int(sample_rate_hz / search.low_hz))
    if max_lag <= min_lag:
        return ScalarSpeed.indeterminate(
            "autocorrelation", "搜索范围对应的滞后区间为空"
        )
    segment = correlation[min_lag : max_lag + 1]
    peaks, properties = scipy_signal.find_peaks(segment, prominence=0.03)
    if len(peaks):
        prominences = properties["prominences"]
        best = int(peaks[int(np.argmax(prominences))])
    else:
        best = int(np.argmax(segment))
    lag = min_lag + best
    if lag <= 0 or not np.isfinite(sample_rate_hz / lag):
        return ScalarSpeed.indeterminate("autocorrelation", "没有有效自相关滞后")
    return ScalarSpeed(float(sample_rate_hz / lag), "autocorrelation")


def estimate_spectrum_speed(
    signal: FloatArray,
    sample_rate_hz: float,
    search: SpeedSearchRange = SpeedSearchRange(),
    harmonics_num: int = 5,
    bandwidth_hz: float = 3.0,
    smooth_win_hz: float = 1.5,
) -> ScalarSpeed:
    """频谱谐波、包络、Welch 与自相关候选的标量仲裁，不执行故障增强。"""
    _validate_sample_rate(sample_rate_hz)
    arr = _prepare(signal)
    if len(arr) < 32 or np.std(arr) <= np.finfo(float).eps:
        return ScalarSpeed.indeterminate(
            "spectrum_arbitration", "信号过短或没有有效变化"
        )
    if harmonics_num < 1 or bandwidth_hz <= 0 or smooth_win_hz < 0:
        raise ValueError("谐波数、频带宽度和谱平滑参数无效")

    spectrum = np.abs(rfft(arr))
    freqs = rfftfreq(len(arr), 1.0 / sample_rate_hz)
    if len(freqs) < 2:
        return ScalarSpeed.indeterminate("spectrum_arbitration", "频谱点不足")
    df = float(freqs[1] - freqs[0])
    if smooth_win_hz > 0:
        kernel_size = max(1, int(round(smooth_win_hz / df)))
        if kernel_size > 1:
            spectrum = np.convolve(
                spectrum, np.ones(kernel_size) / kernel_size, mode="same"
            )
    maximum = float(np.max(spectrum))
    if maximum <= np.finfo(float).eps:
        return ScalarSpeed.indeterminate("spectrum_arbitration", "频谱没有非零分量")
    normalized = spectrum / maximum
    search_indices = np.flatnonzero(
        (freqs >= search.low_hz) & (freqs <= search.high_hz)
    )
    if len(search_indices) == 0:
        return ScalarSpeed.indeterminate(
            "spectrum_arbitration", "采样长度无法覆盖转频搜索范围"
        )

    bw_bins = max(1, int(round(bandwidth_hz / df / 2)))
    min_base_energy = 0.015 * (2 * bw_bins + 1)

    def band_energy(index: int) -> float:
        return float(
            np.sum(
                normalized[
                    max(0, index - bw_bins) : min(len(normalized), index + bw_bins + 1)
                ]
            )
        )

    def sub_harmonic_penalty(candidate: float) -> float:
        penalty = 0.0
        for divisor in (2, 3, 4, 5):
            sub_frequency = candidate / divisor
            if sub_frequency < search.low_hz:
                continue
            index = int(np.argmin(np.abs(freqs - sub_frequency)))
            energy = band_energy(index)
            if energy > min_base_energy * 0.6:
                penalty += energy * (0.5 / divisor)
        return penalty

    best_frequency = float(freqs[search_indices[0]])
    best_index: Optional[int] = None
    best_energy = 0.0
    for index in search_indices:
        base_energy = band_energy(int(index))
        if base_energy < min_base_energy:
            continue
        candidate = float(freqs[index])
        energy = 0.0
        for harmonic in range(1, harmonics_num + 1):
            harmonic_frequency = candidate * harmonic
            if harmonic_frequency > sample_rate_hz / 2:
                break
            harmonic_index = int(np.argmin(np.abs(freqs - harmonic_frequency)))
            energy += band_energy(harmonic_index) / harmonic
        energy -= sub_harmonic_penalty(candidate)
        if energy > best_energy:
            best_energy = energy
            best_frequency = candidate
            best_index = int(index)

    if best_index is None:
        best_index = int(search_indices[int(np.argmax(normalized[search_indices]))])
        best_frequency = float(freqs[best_index])
    else:
        best_frequency = _parabolic_frequency(freqs, normalized, best_index)
    best_base_energy = band_energy(best_index)

    for divisor in (5, 4, 3, 2):
        candidate = best_frequency / divisor
        if candidate < search.low_hz:
            continue
        index = int(np.argmin(np.abs(freqs - candidate)))
        base_energy = band_energy(index)
        if base_energy < max(min_base_energy * 0.2, best_base_energy * 0.12):
            continue
        ratio = best_frequency / candidate
        if abs(ratio - round(ratio)) >= 0.12:
            continue
        harmonic_energy = 0.0
        for harmonic in range(1, harmonics_num + 1):
            if harmonic == divisor:
                continue
            harmonic_frequency = candidate * harmonic
            if harmonic_frequency > sample_rate_hz / 2:
                break
            harmonic_energy += (
                band_energy(int(np.argmin(np.abs(freqs - harmonic_frequency))))
                / harmonic
            )
        if harmonic_energy > best_energy * 0.15:
            best_frequency = _parabolic_frequency(freqs, normalized, index)
            best_index = index
            break

    candidates = [_Candidate(best_frequency, "spectrum")]
    mid_index = _search_peak(freqs, normalized, 200.0, min(500.0, sample_rate_hz / 2))
    high_index = _search_peak(freqs, normalized, 100.0, sample_rate_hz / 4)
    for index, method in ((mid_index, "envelope_mesh"), (high_index, "envelope_high")):
        if index is None:
            continue
        estimate = estimate_envelope_speed(
            arr, sample_rate_hz, float(freqs[index]), search
        )
        if estimate.status == "valid":
            candidates.append(_Candidate(float(estimate.frequency_hz), method))
    try:
        nperseg = min(len(arr), max(256, int(sample_rate_hz)))
        welch_f, welch_p = scipy_signal.welch(arr, fs=sample_rate_hz, nperseg=nperseg)
        welch_index = _search_peak(welch_f, welch_p, search.low_hz, search.high_hz)
        if welch_index is not None and welch_p[welch_index] > 0:
            candidates.append(_Candidate(float(welch_f[welch_index]), "welch"))
    except ValueError:
        pass
    autocorrelation = estimate_autocorrelation_speed(arr, sample_rate_hz, search)
    if autocorrelation.status == "valid":
        candidates.append(
            _Candidate(float(autocorrelation.frequency_hz), "autocorrelation")
        )

    search_background = float(np.median(normalized[search_indices]))

    def has_spectral_support(frequency_hz: float) -> bool:
        index = int(np.argmin(np.abs(freqs - frequency_hz)))
        local_peak = float(np.max(normalized[max(0, index - 1) : index + 2]))
        # 平滑谱中的 5 倍中位数门控可保留弱基频，同时拒绝噪声包络候选。
        return local_peak > max(1e-12, 5.0 * search_background)

    for candidate in candidates:
        if not candidate.method.startswith("envelope"):
            continue
        index = int(np.argmin(np.abs(freqs - candidate.frequency_hz)))
        if band_energy(index) < min_base_energy * 0.3:
            continue
        carrier_index = mid_index if candidate.method == "envelope_mesh" else high_index
        if carrier_index is None:
            continue
        teeth = freqs[carrier_index] / candidate.frequency_hz
        if abs(teeth - round(teeth)) < 0.30 and 10 <= round(teeth) <= 50:
            if has_spectral_support(candidate.frequency_hz):
                return ScalarSpeed(candidate.frequency_hz, candidate.method)

    for ac_candidate in (c for c in candidates if c.method == "autocorrelation"):
        ac_support = band_energy(
            int(np.argmin(np.abs(freqs - ac_candidate.frequency_hz)))
        )
        for candidate in candidates:
            if candidate.frequency_hz <= ac_candidate.frequency_hz:
                continue
            ratio = candidate.frequency_hz / ac_candidate.frequency_hz
            candidate_support = band_energy(
                int(np.argmin(np.abs(freqs - candidate.frequency_hz)))
            )
            if (
                1.8 <= ratio <= 5.2
                and abs(ratio - round(ratio)) < 0.18
                and ac_support > max(min_base_energy * 0.3, candidate_support * 0.2)
            ):
                if has_spectral_support(ac_candidate.frequency_hz):
                    return ScalarSpeed(ac_candidate.frequency_hz, ac_candidate.method)

    def score(candidate: _Candidate) -> float:
        if not search.low_hz <= candidate.frequency_hz <= search.high_hz:
            return -1.0
        value = band_energy(int(np.argmin(np.abs(freqs - candidate.frequency_hz))))
        for harmonic in range(2, harmonics_num + 1):
            harmonic_frequency = candidate.frequency_hz * harmonic
            if harmonic_frequency > sample_rate_hz / 2:
                break
            value += (
                band_energy(int(np.argmin(np.abs(freqs - harmonic_frequency))))
                / harmonic
            )
        value -= sub_harmonic_penalty(candidate.frequency_hz)
        if candidate.method == "autocorrelation":
            value *= 1.10
        elif candidate.method == "welch":
            value *= 1.05
        return value

    best_candidate = max(candidates, key=score)
    if (
        not np.isfinite(best_candidate.frequency_hz)
        or not search.low_hz <= best_candidate.frequency_hz <= search.high_hz
    ):
        return ScalarSpeed.indeterminate(
            "spectrum_arbitration", "候选仲裁没有产生有效转频"
        )
    if not has_spectral_support(best_candidate.frequency_hz):
        return ScalarSpeed.indeterminate(
            "spectrum_arbitration", "搜索范围内没有显著谱峰"
        )
    return ScalarSpeed(float(best_candidate.frequency_hz), best_candidate.method)


def resolve_stft_window_samples(
    signal_length: int,
    sample_rate_hz: float,
    parameters: RidgeParameters = RidgeParameters(),
) -> Tuple[int, int]:
    """按 fs/目标分辨率选择窗长，并限制最长窗时长；返回窗长和 hop。"""
    _validate_sample_rate(sample_rate_hz)
    if signal_length < 64:
        raise ValueError("STFT 转速估计至少需要 64 个采样点")
    target_samples = int(
        2
        ** np.ceil(np.log2(sample_rate_hz / parameters.target_frequency_resolution_hz))
    )
    maximum_samples = max(
        64, int(sample_rate_hz * parameters.maximum_window_duration_s)
    )
    nperseg = min(target_samples, maximum_samples, signal_length)
    if nperseg < 64:
        raise ValueError("有效 STFT 窗长不足 64 点")
    hop = max(1, int(round(nperseg * (1.0 - parameters.overlap))))
    return nperseg, hop


def _longest_true_run(mask: NDArray[np.bool_]) -> int:
    best = current = 0
    for value in mask:
        current = current + 1 if value else 0
        best = max(best, current)
    return best


def _speed_range_violation(
    frequency_hz: FloatArray,
    time_s: FloatArray,
    stft_times_s: FloatArray,
    search: SpeedSearchRange,
    maximum_edge_outside_samples: int,
) -> Optional[str]:
    """检查逐采样点越界；边缘阈值与输入统一使用采样点计数。"""
    outside = (frequency_hz < search.low_hz) | (frequency_hz > search.high_hz)
    if not np.any(outside):
        return None
    edge_extrapolation = (time_s < stft_times_s[0]) | (time_s > stft_times_s[-1])
    if np.any(outside & ~edge_extrapolation):
        return "连续转速轨迹在 STFT 记录内部越出搜索范围"
    if maximum_edge_outside_samples < 1:
        raise ValueError("边缘越界采样点上限必须为正整数")
    if _longest_true_run(outside) > maximum_edge_outside_samples:
        return "连续转速轨迹在边缘长时间越出搜索范围"
    return None


def estimate_stft_speed_trajectory(
    signal: FloatArray,
    sample_rate_hz: float,
    search: SpeedSearchRange = SpeedSearchRange(),
    parameters: RidgeParameters = RidgeParameters(),
) -> SpeedTrajectoryEstimate:
    """追踪 STFT 基频脊线；低信噪比或可靠帧不足时明确不可判定。"""
    _validate_sample_rate(sample_rate_hz)
    arr = _prepare(signal)
    if search.high_hz >= sample_rate_hz / 2:
        return SpeedTrajectoryEstimate.failed("转频搜索上限必须低于奈奎斯特频率")
    try:
        nperseg, hop = resolve_stft_window_samples(len(arr), sample_rate_hz, parameters)
    except ValueError as exc:
        return SpeedTrajectoryEstimate.failed(str(exc))
    noverlap = nperseg - hop
    frequencies, times, stft = scipy_signal.stft(
        arr,
        fs=sample_rate_hz,
        window="hann",
        nperseg=nperseg,
        noverlap=noverlap,
        nfft=nperseg,
        boundary=None,
        padded=False,
    )
    band_indices = np.flatnonzero(
        (frequencies >= search.low_hz) & (frequencies <= search.high_hz)
    )
    if len(band_indices) < 3 or stft.shape[1] < 3:
        return SpeedTrajectoryEstimate.failed(
            "STFT 搜索频带或时间帧不足", total=stft.shape[1]
        )

    full_magnitude = np.abs(stft)
    full_power = full_magnitude**2
    magnitude = full_magnitude[band_indices, :]
    ridge = np.zeros(stft.shape[1], dtype=np.float64)
    reliable = np.zeros(stft.shape[1], dtype=bool)
    boundary_hits = np.zeros(stft.shape[1], dtype=bool)
    for column in range(stft.shape[1]):
        local_index = int(np.argmax(magnitude[:, column]))
        global_index = int(band_indices[local_index])
        at_lower_boundary = local_index == 0
        at_upper_boundary = local_index == len(band_indices) - 1
        peak = float(full_magnitude[global_index, column])
        estimated_frequency = _parabolic_frequency(
            frequencies,
            full_magnitude[:, column],
            global_index,
        )
        frequency_tolerance = 0.25 * float(frequencies[1] - frequencies[0])
        outside_by_interpolation = (
            estimated_frequency < search.low_hz - frequency_tolerance
            or estimated_frequency > search.high_hz + frequency_tolerance
        )
        outside_by_energy = False
        if at_upper_boundary and global_index + 1 < len(frequencies):
            external_power = float(
                np.sum(full_power[global_index + 1 : global_index + 4, column])
            )
            internal_power = float(
                np.sum(full_power[max(0, global_index - 2) : global_index + 1, column])
            )
            outside_by_energy = external_power > internal_power
        elif at_lower_boundary and global_index > 0:
            external_power = float(
                np.sum(full_power[max(0, global_index - 3) : global_index, column])
            )
            internal_power = float(
                np.sum(full_power[global_index + 1 : global_index + 3, column])
            )
            outside_by_energy = external_power > internal_power
        boundary_hits[column] = (at_lower_boundary or at_upper_boundary) and (
            outside_by_interpolation or outside_by_energy
        )
        background_mask = np.ones(len(frequencies), dtype=bool)
        background_mask[0] = False
        background_mask[max(0, global_index - 2) : global_index + 3] = False
        background = float(np.median(full_magnitude[background_mask, column])) + 1e-15
        local_power = float(
            np.sum(full_power[max(0, global_index - 2) : global_index + 3, column])
        )
        total_power = float(np.sum(full_power[1:, column])) + 1e-30
        if (
            peak / background < parameters.minimum_peak_to_background
            or local_power / total_power < parameters.minimum_local_energy_fraction
        ):
            continue
        # 抛物线插值只细化峰位置；物理分辨率仍由 fs/nperseg 决定。
        ridge[column] = estimated_frequency
        reliable[column] = search.low_hz <= ridge[column] <= search.high_hz

    # 首尾 bin 只是候选位置，不等于真实越界：亚 bin 峰位仍在范围内且外侧
    # 局部能量不占优时接受；只有插值越界或外侧能量占优才记为边界风险。
    if _longest_true_run(
        boundary_hits
    ) > parameters.maximum_consecutive_boundary_frames or int(
        np.sum(boundary_hits)
    ) > int(np.ceil(stft.shape[1] * parameters.maximum_boundary_frame_fraction)):
        return SpeedTrajectoryEstimate.failed(
            "STFT 转频脊线持续触及搜索边界，可能越出搜索范围",
            int(np.sum(reliable)),
            stft.shape[1],
        )

    reliable_count = int(np.sum(reliable))
    if reliable_count < 3 or reliable_count < int(
        np.ceil(stft.shape[1] * parameters.minimum_reliable_frame_fraction)
    ):
        return SpeedTrajectoryEstimate.failed(
            "没有足够可靠的 STFT 转频脊线",
            reliable_count,
            stft.shape[1],
        )
    sample_times = np.arange(len(arr), dtype=np.float64) / sample_rate_hz
    ridge_times = times[reliable]
    ridge_values = ridge[reliable]
    per_sample = np.interp(sample_times, ridge_times, ridge_values)
    # STFT 只覆盖窗中心；端点按最靠近边缘的可靠脊线局部斜率外推，
    # 避免把扫频信号前/后半窗强行当恒速而积累错误相位。
    edge_count = min(5, len(ridge_times))
    if edge_count >= 2:
        left = sample_times < ridge_times[0]
        right = sample_times > ridge_times[-1]
        left_slope, left_intercept = np.polyfit(
            ridge_times[:edge_count],
            ridge_values[:edge_count],
            1,
        )
        right_slope, right_intercept = np.polyfit(
            ridge_times[-edge_count:],
            ridge_values[-edge_count:],
            1,
        )
        per_sample[left] = left_intercept + left_slope * sample_times[left]
        per_sample[right] = right_intercept + right_slope * sample_times[right]
    range_violation = _speed_range_violation(
        per_sample,
        sample_times,
        times,
        search,
        maximum_edge_outside_samples=max(1, nperseg // 2),
    )
    if range_violation:
        return SpeedTrajectoryEstimate.failed(
            range_violation,
            reliable_count,
            stft.shape[1],
        )
    per_sample = np.clip(per_sample, search.low_hz, search.high_hz)
    trajectory = SpeedTrajectory(
        time_s=sample_times,
        frequency_hz=per_sample,
        source="stft_ridge",
        stft_window_samples=nperseg,
        stft_hop_samples=hop,
        stft_frequency_resolution_hz=float(sample_rate_hz / nperseg),
    )
    return SpeedTrajectoryEstimate("valid", trajectory, reliable_count, stft.shape[1])
