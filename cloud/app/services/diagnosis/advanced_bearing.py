"""高级轴承业务适配：显式方法前提、独立评估和 JSON 边界。"""
from typing import Mapping, Optional

import numpy as np

from app.algorithms.bearing.cepstral import CPWEnvelopePipeline
from app.algorithms.bearing.cyclostationary import CyclostationaryPipeline
from app.algorithms.bearing.deconvolution import (
    MEDEnvelopePipeline, MCKDEnvelopePipeline, MCKDParameters,
)
from app.algorithms.pipelines.bearing import BearingEnvelopePipeline
from app.algorithms.bearing.spectral_kurtosis import (
    FilterBankKurtogramPipeline, ReweightedSpectralKurtosisPipeline,
)
from app.algorithms.bearing.teo import TEOEnvelopePipeline


ADVANCED_BEARING_METHODS = frozenset({
    "filter_bank_sk", "spectral_kurtosis", "cpw", "med", "mckd", "teager", "sc_scoh",
})


def unavailable(method: str, reason: str) -> dict:
    """计算或物理前提未满足时保留请求方法，不合成健康证据。"""
    return {
        "method": method, "analysis_status": "indeterminate", "reason": reason,
        "spectrum": None, "band": None, "features": {},
        "evaluation": {"status": "indeterminate", "indicators": {}},
    }


def _band_metadata(result) -> dict:
    return {
        "optimal_fc": result.best_band.center_hz if result.best_band else None,
        "optimal_bw": result.best_band.width_hz if result.best_band else None,
        "max_kurtosis": result.max_spectral_kurtosis,
        "band_candidates": [
            {"level": item.level, "fc": item.band.center_hz, "bw": item.band.width_hz,
             "spectral_kurtosis": item.spectral_kurtosis, "score": item.reweighted_score,
             "estimator": item.estimator}
            for item in sorted(result.bands, key=lambda item: item.reweighted_score, reverse=True)[:100]
        ],
    }


def run_enhancement(method, signal, fs, geometry=None, rot_freq=None, options=None):
    """返回独立 Pipeline 结果；不推断稳定梳状干扰，也不默认 MCKD 故障类型。"""
    options = options or {}
    if method == "filter_bank_sk":
        return FilterBankKurtogramPipeline().run(signal, fs)
    if method == "spectral_kurtosis":
        return ReweightedSpectralKurtosisPipeline().run(signal, fs)
    if method == "cpw":
        return CPWEnvelopePipeline().run(
            signal, fs, comb_frequencies=options.get("comb_frequencies_hz", ()),
            comb_is_stable=options.get("comb_is_stable") is True,
        )
    if method == "med":
        return MEDEnvelopePipeline().run(signal, fs)
    if method == "teager":
        return TEOEnvelopePipeline().run(signal, fs)
    if method == "mckd":
        return MCKDEnvelopePipeline().run(
            signal, fs, MCKDParameters(
                target_fault=options["target_fault"],
                target_frequency_hz=options.get("target_frequency_hz"),
                period_samples=options.get("period_samples"),
            ), geometry=geometry, rot_frequency_hz=rot_freq,
        )
    raise ValueError(f"未知高级轴承方法: {method}")


def analyze_advanced_bearing(
    method: str, signal, fs: float, geometry=None, rot_freq: Optional[float] = None,
    rot_std: float = 0.0, options: Optional[Mapping] = None, max_freq: float = 1000.0,
) -> dict:
    """增强类复用标准包络评估；SC/SCoh 始终保留专属循环频率评估。"""
    options = dict(options or {})
    signal = np.asarray(signal, dtype=np.float64)
    if signal.ndim != 1 or not np.all(np.isfinite(signal)):
        raise ValueError("高级轴承输入必须是一维有限数组")
    if not np.isfinite(fs) or fs <= 0:
        raise ValueError("采样率必须为有限正数")
    minimum = 256 if method in {"filter_bank_sk", "spectral_kurtosis", "cpw"} else 64
    if len(signal) < minimum:
        return unavailable(method, "insufficient_signal_length")
    if not np.any(signal - np.mean(signal)):
        return unavailable(method, "zero_energy")
    if method in {"mckd", "sc_scoh"} and rot_freq and rot_std / rot_freq > 0.1:
        return unavailable(method, "varying_speed_requires_continuous_phase_pipeline")
    if method == "mckd" and not options.get("target_fault"):
        result = analyze_advanced_bearing("med", signal, fs, geometry, rot_freq, rot_std, max_freq=max_freq)
        result.update(requested_method="mckd", fallback_reason="missing_explicit_target_fault")
        return result
    if method == "sc_scoh":
        cyclic = CyclostationaryPipeline().run(
            signal, fs, candidates=options.get("cyclic_candidates_hz"),
            geometry=geometry, rot_frequency_hz=rot_freq,
            segment_length=options.get("segment_length", 512),
        )
        result = unavailable(method, cyclic.reason)
        result.update(
            analysis_status=cyclic.status, algorithm=cyclic.method, evaluation_kind="sc_scoh",
            evaluation={"status": cyclic.evaluation.status, "indicators": cyclic.evaluation.indicators},
            **cyclic.metadata,
        )
        if cyclic.representation is not None:
            rep = cyclic.representation
            result["cyclic_spectrum"] = {
                "cyclic_frequency_hz": rep.cyclic_frequencies_hz.tolist(),
                "carrier_frequency_hz": rep.carrier_frequencies_hz.tolist(),
                "spectral_correlation_magnitude": np.abs(rep.spectral_correlation).tolist(),
                "spectral_correlation_unit": "input_signal^2/Hz",
                "spectral_coherence": rep.spectral_coherence.tolist(),
                "spectral_coherence_unit": "dimensionless",
                "cyclic_resolution_hz": rep.cyclic_resolution_hz,
            }
        return result

    enhanced = run_enhancement(method, signal, fs, geometry, rot_freq, options)
    result = unavailable(method, enhanced.reason)
    result.update(analysis_status=enhanced.status, algorithm=enhanced.method, evaluation_kind="envelope")
    result.update(getattr(enhanced, "metadata", {}))
    if method in {"filter_bank_sk", "spectral_kurtosis"}:
        result.update(_band_metadata(enhanced))
    if enhanced.representation is None:
        return result
    rep = enhanced.representation
    pipeline = BearingEnvelopePipeline(geometry=geometry)
    extracted = pipeline.analyze_representation(
        rep, rot_frequency_hz=rot_freq, rot_frequency_std_hz=rot_std,
    )
    analysis = extracted.envelope_analysis
    evaluation = pipeline.evaluate(extracted)
    displayed = rep.spectrum.truncated(max_freq)
    result.update(
        spectrum={"frequency_hz": displayed.frequency_hz.tolist(), "amplitude": displayed.amplitude.tolist(),
                  "amplitude_unit": displayed.amplitude_unit, "scaling": displayed.scaling},
        band={"low_hz": rep.band.low_hz, "high_hz": rep.band.high_hz,
              "center_hz": rep.band.center_hz, "width_hz": rep.band.width_hz},
        envelope_low_pass_hz=rep.envelope_low_pass_hz,
        features=analysis.features.as_dict(),
        evaluation={"status": evaluation.status, "indicators": evaluation.indicators},
    )
    return result
