"""复频谱频移 SC/SCoh 估计、候选循环频率搜索与专属评估。"""

from dataclasses import dataclass, field
from typing import Optional, Mapping, Sequence

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from numpy.typing import NDArray
from scipy.fft import fft, rfftfreq
from scipy.signal import windows

from app.algorithms.mechanics import BearingGeometry


@dataclass(frozen=True)
class CyclicRepresentation:
    cyclic_frequencies_hz: NDArray[np.float64]
    carrier_frequencies_hz: NDArray[np.float64]
    spectral_correlation: NDArray[np.complex128]
    spectral_coherence: NDArray[np.float64]
    cyclic_resolution_hz: float
    segment_count: int
    sample_rate_hz: float
    duration_s: float
    input_amplitude_scale: float


@dataclass(frozen=True)
class CyclicEvaluation:
    status: str
    indicators: dict[str, dict]


@dataclass(frozen=True)
class CyclostationaryResult:
    status: str
    method: str
    representation: Optional[CyclicRepresentation]
    evaluation: CyclicEvaluation
    reason: Optional[str] = None
    metadata: dict = field(default_factory=dict)


def compute_sc_scoh(
    signal: NDArray[np.float64],
    sample_rate_hz: float,
    cyclic_frequencies_hz: Sequence[float],
    segment_length: int = 512,
    overlap_ratio: float = 0.75,
) -> CyclicRepresentation:
    """直接频移复 FFT：X(f-alpha/2)*conj(X(f+alpha/2))，再跨段复平均。

    频移由全局时间复指数完成，因此 alpha 不必落在 FFT bin 上；循环频率物理
    分辨率仍由完整记录时长决定，零填充或直接计算不会改善该分辨率。
    """
    x = np.asarray(signal, dtype=np.float64)
    if x.ndim != 1 or len(x) < 128 or not np.all(np.isfinite(x)):
        raise ValueError("SC/SCoh 输入必须是一维有限数组且至少 128 点")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("采样率必须为有限正数")
    if (
        isinstance(segment_length, bool)
        or not isinstance(segment_length, int)
        or segment_length < 32
    ):
        raise ValueError("分段长度必须是至少为 32 的整数")
    if segment_length > len(x):
        raise ValueError("分段长度不能超过输入长度")
    if not np.isfinite(overlap_ratio) or not 0.0 <= overlap_ratio < 1.0:
        raise ValueError("重叠率必须位于 [0,1)")
    alpha = np.asarray(
        tuple(sorted(set(float(value) for value in cyclic_frequencies_hz))),
        dtype=np.float64,
    )
    if alpha.ndim != 1 or len(alpha) == 0:
        raise ValueError("必须至少提供一个候选循环频率")
    if (
        not np.all(np.isfinite(alpha))
        or np.any(alpha < 0)
        or np.any(alpha > sample_rate_hz / 2.0)
    ):
        raise ValueError("循环频率必须有限且位于 [0,Nyquist]")

    step = max(1, int(round(segment_length * (1.0 - overlap_ratio))))
    starts = np.arange(0, len(x) - segment_length + 1, step, dtype=int)
    if len(starts) < 4:
        raise ValueError("SC/SCoh 至少需要四个完整分段")
    centered = x - np.mean(x)
    input_scale = float(np.max(np.abs(centered)))
    # 相干性和后续峰背景比都是归一化量；先缩放可让固定正则化彻底退出公式。
    normalized = centered / input_scale if input_scale > 0.0 else centered
    segments = sliding_window_view(normalized, segment_length)[starts]
    window = windows.hann(segment_length, sym=False)
    scale = sample_rate_hz * float(np.sum(window**2))
    local = np.arange(segment_length)[None, :]
    global_time_s = (starts[:, None] + local) / sample_rate_hz
    windowed = segments * window[None, :]
    # 复 FFT 的 k=N/2 点在非负半轴标记为 +Nyquist；奇数长度没有 Nyquist 点。
    carrier = rfftfreq(segment_length, 1.0 / sample_rate_hz)
    sc = np.empty((len(alpha), len(carrier)), dtype=np.complex128)
    scoh = np.empty((len(alpha), len(carrier)), dtype=np.float64)

    for index, cyclic_frequency in enumerate(alpha):
        # e^{+j*pi*alpha*t} 使 X(f-alpha/2)，e^{-j*pi*alpha*t} 使 X(f+alpha/2)。
        x_lo = fft(
            windowed * np.exp(1j * np.pi * cyclic_frequency * global_time_s), axis=1
        )[:, : len(carrier)] / np.sqrt(scale)
        x_hi = fft(
            windowed * np.exp(-1j * np.pi * cyclic_frequency * global_time_s), axis=1
        )[:, : len(carrier)] / np.sqrt(scale)
        cross = x_lo * np.conj(x_hi)
        sc[index] = np.mean(cross, axis=0)
        psd_lo = np.mean(np.abs(x_lo) ** 2, axis=0)
        psd_hi = np.mean(np.abs(x_hi) ** 2, axis=0)
        # 顺序除以 sqrt(PSD)，避免 PSD 乘积及 |SC|^2 同时下溢。
        coherence_amplitude = np.divide(
            np.abs(sc[index]),
            np.sqrt(psd_lo),
            out=np.zeros(len(carrier), dtype=np.float64),
            where=psd_lo > 0.0,
        )
        coherence_amplitude = np.divide(
            coherence_amplitude,
            np.sqrt(psd_hi),
            out=np.zeros(len(carrier), dtype=np.float64),
            where=psd_hi > 0.0,
        )
        scoh[index] = np.clip(coherence_amplitude**2, 0.0, 1.0)

    return CyclicRepresentation(
        cyclic_frequencies_hz=alpha,
        carrier_frequencies_hz=carrier,
        # SC 保留原输入幅值单位，服从 SC(s*x)=s^2*SC(x)。
        spectral_correlation=sc * input_scale**2,
        spectral_coherence=scoh,
        cyclic_resolution_hz=float(sample_rate_hz / len(x)),
        segment_count=len(starts),
        sample_rate_hz=float(sample_rate_hz),
        duration_s=float(len(x) / sample_rate_hz),
        input_amplitude_scale=input_scale,
    )


def _not_evaluable(target: float, reason: str) -> dict:
    return {
        "status": "not_evaluable",
        "evaluable": False,
        "reason": reason,
        "theory_cyclic_frequency_hz": target,
        "detected_cyclic_frequency_hz": None,
        "carrier_frequency_hz": None,
        "scoh_peak": None,
        "sc_peak": None,
        "coherence_background_ratio": None,
        "sc_background_ratio": None,
        "significant": None,
    }


def _peak_background_ratio(peak: float, background: float) -> Optional[float]:
    """零背景不施加绝对下限；峰与背景同时为零时比值没有定义。"""
    if background == 0.0:
        return None if peak == 0.0 else float("inf")
    return peak / background


def evaluate_cyclic_candidates(
    representation: CyclicRepresentation,
    candidates: Mapping[str, float],
    relative_tolerance: float = 0.03,
    coherence_threshold: float = 0.2,
    background_ratio_threshold: float = 3.0,
) -> CyclicEvaluation:
    """只使用 |SC| 与 SCoh 的离目标循环频率背景，不调用包络谱 SNR。"""
    if not candidates:
        return CyclicEvaluation(status="indeterminate", indicators={})
    if not np.isfinite(relative_tolerance) or relative_tolerance <= 0:
        raise ValueError("循环频率相对容差必须为有限正数")
    if not 0.0 <= coherence_threshold <= 1.0 or not np.isfinite(
        background_ratio_threshold
    ):
        raise ValueError("SCoh 阈值或背景比阈值无效")

    alpha = representation.cyclic_frequencies_hz
    sc = np.abs(representation.spectral_correlation)
    scoh = representation.spectral_coherence
    resolution = representation.cyclic_resolution_hz
    indicators: dict[str, dict] = {}
    peaks: dict[str, tuple[int, int]] = {}
    tolerances = {
        name: float(target) * relative_tolerance for name, target in candidates.items()
    }

    for name, raw_target in candidates.items():
        target = float(raw_target)
        tolerance = (
            target * relative_tolerance if np.isfinite(target) and target > 0 else 0.0
        )
        if not np.isfinite(target) or target <= 0:
            indicators[name] = _not_evaluable(target, "invalid_target_frequency")
            continue
        if target > float(alpha[-1]) + tolerance:
            indicators[name] = _not_evaluable(target, "target_above_analysis_bandwidth")
            continue
        if target < float(alpha[0]) - tolerance:
            indicators[name] = _not_evaluable(target, "target_not_computed")
            continue
        if representation.input_amplitude_scale == 0.0:
            indicators[name] = _not_evaluable(target, "zero_energy")
            continue
        if tolerance < resolution:
            indicators[name] = _not_evaluable(
                target, "insufficient_cyclic_frequency_resolution"
            )
            continue
        duplicated = any(
            other != name
            and abs(target - float(other_target))
            < max(resolution, tolerance + tolerances[other])
            for other, other_target in candidates.items()
        )
        if duplicated:
            reason = (
                "shared_cyclic_target"
                if any(
                    other != name and target == float(other_target)
                    for other, other_target in candidates.items()
                )
                else "shared_cyclic_resolution_cell"
            )
            indicators[name] = _not_evaluable(target, reason)
            continue
        indices = np.flatnonzero(np.abs(alpha - target) <= tolerance)
        if len(indices) == 0:
            indicators[name] = _not_evaluable(target, "target_not_resolvable")
            continue
        best_pair = None
        best_value = -np.inf
        for alpha_index in indices:
            carrier_index = int(np.argmax(scoh[alpha_index]))
            value = float(scoh[alpha_index, carrier_index])
            if value > best_value:
                best_value = value
                best_pair = (int(alpha_index), carrier_index)
        alpha_index, carrier_index = best_pair
        background_indices = np.flatnonzero(
            np.abs(alpha - target) > max(2.0 * tolerance, resolution)
        )
        if len(background_indices) == 0:
            indicators[name] = _not_evaluable(target, "insufficient_cyclic_background")
            continue
        coherence_background = float(np.median(scoh[background_indices, carrier_index]))
        sc_background = float(np.median(sc[background_indices, carrier_index]))
        scoh_peak = float(scoh[alpha_index, carrier_index])
        sc_peak = float(sc[alpha_index, carrier_index])
        coherence_ratio = _peak_background_ratio(scoh_peak, coherence_background)
        sc_ratio = _peak_background_ratio(sc_peak, sc_background)
        if coherence_ratio is None or sc_ratio is None:
            indicators[name] = _not_evaluable(
                target, "undefined_zero_peak_and_background"
            )
            continue
        peaks[name] = (alpha_index, carrier_index)
        indicators[name] = {
            "status": "evaluated",
            "evaluable": True,
            "reason": None,
            "theory_cyclic_frequency_hz": target,
            "detected_cyclic_frequency_hz": float(alpha[alpha_index]),
            "carrier_frequency_hz": float(
                representation.carrier_frequencies_hz[carrier_index]
            ),
            "scoh_peak": scoh_peak,
            "sc_peak": sc_peak,
            "coherence_background_ratio": coherence_ratio,
            "sc_background_ratio": sc_ratio,
            "metric_kind": "complex_sc_and_spectral_coherence_not_envelope_snr",
            "significant": bool(
                scoh_peak >= coherence_threshold
                and coherence_ratio >= background_ratio_threshold
                and sc_ratio >= background_ratio_threshold
            ),
        }

    # 不同理论目标不得复用同一个二维 SC/SCoh 峰。
    seen: dict[tuple[int, int], str] = {}
    for name, pair in peaks.items():
        if pair in seen:
            for duplicated_name in (seen[pair], name):
                target = float(candidates[duplicated_name])
                indicators[duplicated_name] = _not_evaluable(
                    target, "shared_cyclic_peak"
                )
        else:
            seen[pair] = name
    status = (
        "evaluated"
        if any(item.get("evaluable") for item in indicators.values())
        else "indeterminate"
    )
    return CyclicEvaluation(status=status, indicators=indicators)


class CyclostationaryPipeline:
    method = "Complex frequency-shift SC/SCoh + dedicated cyclic evaluation"

    def run(
        self,
        signal: NDArray[np.float64],
        sample_rate_hz: float,
        candidates: Optional[Mapping[str, float]] = None,
        geometry: Optional[BearingGeometry] = None,
        rot_frequency_hz: Optional[float] = None,
        segment_length: int = 512,
        overlap_ratio: float = 0.75,
        relative_tolerance: float = 0.03,
    ) -> CyclostationaryResult:
        if candidates is None and geometry is not None and rot_frequency_hz is not None:
            frequencies = geometry.fault_frequencies(rot_frequency_hz)
            candidates = {
                name: frequencies[name] for name in ("BPFO", "BPFI", "BSF", "FTF")
            }
        if not candidates:
            return CyclostationaryResult(
                status="indeterminate",
                method=self.method,
                representation=None,
                evaluation=CyclicEvaluation(status="indeterminate", indicators={}),
                reason="missing_cyclic_candidates_or_geometry_and_rotation",
            )
        if not np.isfinite(relative_tolerance) or relative_tolerance <= 0:
            raise ValueError("循环频率相对容差必须为有限正数")

        candidates = {name: float(target) for name, target in candidates.items()}
        nyquist = sample_rate_hz / 2.0
        failure_reasons: dict[str, str] = {}
        for name, target in candidates.items():
            if not np.isfinite(target) or target <= 0.0:
                failure_reasons[name] = "invalid_target_frequency"
            elif target > nyquist:
                failure_reasons[name] = "target_above_analysis_bandwidth"
        if len(failure_reasons) == len(candidates):
            unique_reasons = set(failure_reasons.values())
            reason = (
                unique_reasons.pop()
                if len(unique_reasons) == 1
                else "no_valid_cyclic_candidates"
            )
            return CyclostationaryResult(
                status="indeterminate",
                method=self.method,
                representation=None,
                evaluation=CyclicEvaluation(
                    status="indeterminate",
                    indicators={
                        name: _not_evaluable(target, failure_reasons[name])
                        for name, target in candidates.items()
                    },
                ),
                reason=reason,
            )

        x = np.asarray(signal, dtype=np.float64)
        n = len(x) if x.ndim == 1 else 0
        step = (
            max(1, int(round(segment_length * (1.0 - overlap_ratio))))
            if isinstance(segment_length, int)
            else 1
        )
        segment_count = (
            len(np.arange(0, n - segment_length + 1, step))
            if n >= segment_length
            else 0
        )
        if n < 128 or segment_count < 4:
            return CyclostationaryResult(
                status="indeterminate",
                method=self.method,
                representation=None,
                evaluation=CyclicEvaluation(
                    status="indeterminate",
                    indicators={
                        name: _not_evaluable(
                            target,
                            failure_reasons.get(name, "insufficient_signal_length"),
                        )
                        for name, target in candidates.items()
                    },
                ),
                reason="insufficient_signal_length",
            )
        if not np.any(x - np.mean(x)):
            return CyclostationaryResult(
                status="indeterminate",
                method=self.method,
                representation=None,
                evaluation=CyclicEvaluation(
                    status="indeterminate",
                    indicators={
                        name: _not_evaluable(
                            target, failure_reasons.get(name, "zero_energy")
                        )
                        for name, target in candidates.items()
                    },
                ),
                reason="zero_energy",
            )

        duration = n / sample_rate_hz
        grid = set()
        for name, target in candidates.items():
            if name in failure_reasons:
                continue
            tolerance = target * relative_tolerance
            for multiplier in (-3.0, -1.0, 0.0, 1.0, 3.0):
                value = target + multiplier * tolerance
                if 0.0 < value <= nyquist:
                    grid.add(round(value, 12))
        representation = compute_sc_scoh(
            signal,
            sample_rate_hz,
            sorted(grid),
            segment_length=segment_length,
            overlap_ratio=overlap_ratio,
        )
        evaluation = evaluate_cyclic_candidates(
            representation,
            candidates,
            relative_tolerance=relative_tolerance,
        )
        return CyclostationaryResult(
            status="computed",
            method=self.method,
            representation=representation,
            evaluation=evaluation,
            metadata={
                "candidate_source": "explicit"
                if geometry is None
                else "bearing_geometry_and_rotation",
                "physical_cyclic_resolution_hz": 1.0 / duration,
            },
        )
