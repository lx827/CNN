"""轴承包络指标评估；阈值只消费已提取指标，不执行信号变换。"""

from dataclasses import dataclass
from typing import Optional

import numpy as np

from app.algorithms.bearing.analysis import EnvelopeAnalysis, SidebandEvidence


@dataclass(frozen=True)
class EnvelopeEvaluation:
    """evaluated 表示可评估，indeterminate 表示缺少必要输入或全部不可分辨。"""

    status: str
    indicators: dict[str, dict]


def evaluate_sideband_evidence(evidence: Optional[SidebandEvidence]) -> dict:
    """应用边带显著性规则；分母只包含可观测目标。"""
    observations = evidence.observations if evidence else ()
    significant_count = sum(item.snr > 3.0 for item in observations)
    observable_count = evidence.observable_count if evidence else 0
    density = significant_count / observable_count if observable_count else None
    asymmetry = evidence.asymmetry if evidence else None
    return {
        "sideband_density": density,
        "sideband_significant_count": significant_count,
        "sideband_observable_count": observable_count,
        "sideband_asymmetry": asymmetry,
        "high_density": density >= 0.3 if density is not None else None,
        "high_asymmetry": asymmetry > 0.3 if asymmetry is not None else None,
    }


def _statistical_indicators(analysis: EnvelopeAnalysis) -> dict[str, dict]:
    stats = analysis.features.statistics
    harmonic_ratio = stats.rotation_harmonic_energy_ratio or 0.0
    rotation_dominant = harmonic_ratio > 0.4
    return {
        "envelope_peak_snr": {
            "value": stats.peak_snr,
            "snr": stats.peak_snr,
            "snr_kind": "linear_peak_to_background_not_db",
            "significant": bool(stats.peak_snr > 20.0),
        },
        "envelope_kurtosis": {
            "value": stats.kurtosis,
            "score": max(0.0, stats.kurtosis),
            "significant": bool(stats.kurtosis > 15.0),
        },
        "moderate_kurtosis": {
            "value": stats.kurtosis,
            "score": max(0.0, stats.kurtosis),
            "significant": bool(stats.kurtosis > 5.0 and stats.peak_snr > 15.0),
        },
        "low_freq_ratio": {
            "value": stats.low_frequency_ratio or 0.0,
            "score": (1.0 - (stats.low_frequency_ratio or 0.0)) * 10.0,
            "significant": False,
            "rotation_harmonic_energy_ratio": harmonic_ratio,
            "rotation_harmonic_dominant": rotation_dominant,
        },
        "high_freq_ratio": {
            "value": stats.high_frequency_ratio or 0.0,
            "score": (stats.high_frequency_ratio or 0.0) * 10.0,
            "significant": bool(
                (stats.high_frequency_ratio or 0.0) > 0.65 and not rotation_dominant
            ),
        },
        "peak_concentration": {
            "value": stats.peak_concentration,
            "score": stats.peak_concentration * 10.0,
            "significant": bool(
                stats.peak_concentration > 0.6 and not rotation_dominant
            ),
        },
        "envelope_crest_factor": {
            "value": stats.crest_factor,
            "score": stats.crest_factor,
            "significant": bool(stats.crest_factor > 35.0 and not rotation_dominant),
        },
    }


def _not_evaluable(
    theory: float, reason: str, sidebands: Optional[SidebandEvidence]
) -> dict:
    return {
        "status": "not_evaluable",
        "evaluable": False,
        "reason": reason,
        "theory_hz": theory,
        "detected_hz": None,
        "peak_amp": None,
        "snr": None,
        "significant": None,
        "carrier_significant": None,
        "sideband_significant": None,
        **evaluate_sideband_evidence(sidebands),
    }


def evaluate_envelope(analysis: EnvelopeAnalysis) -> EnvelopeEvaluation:
    """评估已有包络指标；不可分辨与真实未检出使用不同结果。"""
    if analysis.rot_frequency_hz is None:
        return EnvelopeEvaluation(status="indeterminate", indicators={})

    features = analysis.features
    statistics = _statistical_indicators(analysis)
    if not features.fault_frequency_hz:
        return EnvelopeEvaluation(status="evaluated", indicators=statistics)

    param_indicators = {}
    amplitude = analysis.spectrum.amplitude
    for name in ("BPFO", "BPFI", "BSF"):
        theory = features.fault_frequency_hz[name]
        sidebands = features.sidebands.get(name)
        issue = features.peak_issues.get(name)
        peak = features.peaks.get(name)
        if issue:
            param_indicators[name] = _not_evaluable(
                theory,
                issue,
                sidebands,
            )
            continue

        snr = peak.snr if peak else 0.0
        carrier_significant = bool(snr > 4.5)
        sideband_significant = None
        if name == "BPFI":
            strong_sidebands = sum(value > 3.0 for value in features.bpfi_sideband_snrs)
            envelope_kurt = float(
                np.mean(amplitude**4) / (np.mean(amplitude**2) ** 2 + 1e-12)
            )
            sideband_significant = bool(
                strong_sidebands >= 2 and snr > 4.3 and envelope_kurt > 5.0
            )
        param_indicators[name] = {
            "status": "evaluated",
            "evaluable": True,
            "theory_hz": theory,
            "detected_hz": peak.frequency_hz if peak else None,
            "peak_amp": peak.amplitude if peak else 0.0,
            "snr": snr,
            "snr_kind": "linear_peak_to_background_not_db",
            "carrier_significant": carrier_significant,
            "sideband_significant": sideband_significant,
            "significant": carrier_significant or bool(sideband_significant),
            "harmonic_snrs": list(features.harmonic_snrs.get(name, ())),
            "sideband_snrs": list(features.bpfi_sideband_snrs)
            if name == "BPFI"
            else None,
            **evaluate_sideband_evidence(sidebands),
        }

    # 主导过滤只作用于载波证据，不得覆盖 BPFI 的边带补救结论。
    evaluable = {
        name: values for name, values in param_indicators.items() if values["evaluable"]
    }
    if evaluable:
        ordered = sorted((values["snr"] for values in evaluable.values()), reverse=True)
        maximum = ordered[0]
        second = ordered[1] if len(ordered) > 1 else 1.0
        dominant_ratio = maximum / max(second, 1.0)
        for values in evaluable.values():
            snr = values["snr"]
            values["dominant_ratio"] = dominant_ratio
            values["carrier_significant"] = bool(
                (snr > 4.5 and snr == maximum and dominant_ratio > 1.5) or snr > 15.0
            )
            values["significant"] = bool(
                values["carrier_significant"] or values["sideband_significant"]
            )

    # 统计显著性保持原始阈值结果，不再被物理峰结果清除。
    status = "evaluated" if evaluable else "indeterminate"
    return EnvelopeEvaluation(
        status=status,
        indicators={
            **param_indicators,
            **{f"{name}_stat": values for name, values in statistics.items()},
        },
    )
