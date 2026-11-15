"""复频谱频移 SC/SCoh 估计、候选循环频率搜索与专属评估。"""

from dataclasses import dataclass, field
from typing import Optional, Mapping

import numpy as np
from cnn_compute import diagnostic as native_diagnostic
from numpy.typing import NDArray

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
    signal,
    sample_rate_hz,
    cyclic_frequencies_hz,
    segment_length=512,
    overlap_ratio=0.75,
) -> CyclicRepresentation:
    """全局时间复频移SC/SCoh；原生逐段复归约，物理分辨率由记录时长决定。"""
    if (
        isinstance(segment_length, bool)
        or not isinstance(segment_length, int)
        or segment_length < 32
    ):
        raise ValueError("分段长度必须是至少为32的整数")
    if not np.isfinite(overlap_ratio) or not 0 <= overlap_ratio < 1:
        raise ValueError("重叠率必须位于[0,1)")
    alpha = np.asarray(
        sorted(set(float(value) for value in cyclic_frequencies_hz)), dtype=np.float64
    )
    step = max(1, int(round(segment_length * (1 - overlap_ratio))))
    sc, scoh, count, scale = native_diagnostic.sc_scoh(
        signal, sample_rate_hz, alpha, segment_length, step
    )
    n = len(signal)
    return CyclicRepresentation(
        alpha,
        np.fft.rfftfreq(segment_length, 1 / sample_rate_hz),
        sc,
        scoh,
        float(sample_rate_hz / n),
        count,
        float(sample_rate_hz),
        float(n / sample_rate_hz),
        scale,
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
