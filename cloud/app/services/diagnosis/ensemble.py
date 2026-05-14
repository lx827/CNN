"""Multi-method diagnosis ensemble for high-recall fault detection.

The module keeps the heavy, research-style algorithms callable without making
the real-time pages depend on a single fragile threshold. It uses weak voting:
each algorithm contributes evidence, but a channel is not marked faulty unless
several independent indicators agree.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from .engine import BearingMethod, DenoiseMethod, DiagnosisEngine, DiagnosisStrategy, GearMethod
from .features import compute_time_features
from .recommendation import _generate_recommendation


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _safe_denoise(value: str) -> DenoiseMethod:
    try:
        return DenoiseMethod(value)
    except ValueError:
        return DenoiseMethod.NONE


def _profile_config(profile: str, denoise_method: str) -> Dict[str, list]:
    configured_denoise = _safe_denoise(denoise_method).value
    denoise_methods = ["none"]
    if configured_denoise != "none":
        denoise_methods.append(configured_denoise)

    if profile == "exhaustive":
        return {
            "denoise": list(dict.fromkeys(denoise_methods + ["wavelet"])),
            "bearing": [
                BearingMethod.ENVELOPE,
                BearingMethod.KURTOGRAM,
                BearingMethod.CPW,
                BearingMethod.TEAGER,
                BearingMethod.SPECTRAL_KURTOSIS,
                BearingMethod.MED,
            ],
            "gear": [GearMethod.STANDARD, GearMethod.ADVANCED],
        }

    if profile == "balanced":
        return {
            "denoise": denoise_methods,
            "bearing": [
                BearingMethod.ENVELOPE,
                BearingMethod.KURTOGRAM,
                BearingMethod.CPW,
                BearingMethod.TEAGER,
                BearingMethod.SPECTRAL_KURTOSIS,
            ],
            "gear": [GearMethod.ADVANCED],
        }

    return {
        "denoise": denoise_methods[:1],
        "bearing": [
            BearingMethod.ENVELOPE,
            BearingMethod.KURTOGRAM,
            BearingMethod.CPW,
            BearingMethod.TEAGER,
        ],
        "gear": [GearMethod.ADVANCED],
    }


def _has_gear_params(gear_teeth: Optional[Dict]) -> bool:
    try:
        return bool(gear_teeth and float(gear_teeth.get("input") or 0) > 0)
    except (TypeError, ValueError):
        return False


def _bearing_confidence(result: Dict, time_features: Dict) -> Dict[str, Any]:
    indicators = result.get("fault_indicators", {}) or {}
    param_hits = 0
    stat_hits = 0
    strongest_snr = 0.0
    hit_names = []

    for name, item in indicators.items():
        if not isinstance(item, dict):
            continue
        significant = bool(item.get("significant"))
        strongest_snr = max(strongest_snr, _as_float(item.get("snr")))
        if name.endswith("_stat") or name in {
            "envelope_peak_snr",
            "envelope_kurtosis",
            "moderate_kurtosis",
            "envelope_crest_factor",
            "high_freq_ratio",
            "peak_concentration",
        }:
            if significant:
                stat_hits += 1
                hit_names.append(name)
        elif significant:
            param_hits += 1
            hit_names.append(name)

    kurt = _as_float(time_features.get("kurtosis"), 3.0)
    crest = _as_float(time_features.get("crest_factor"), 5.0)
    rms_mad_z = _as_float(time_features.get("rms_mad_z"), 0.0)
    cusum = _as_float(time_features.get("cusum_score"), 0.0)
    impulse_context = kurt > 5.0 or crest > 7.0 or rms_mad_z > 6.0 or cusum > 8.0

    # 低频优势度：仅用于弱证据（stat_hits=1）场景的辅助判断
    low_freq_dominance = False
    low_freq_indicator = indicators.get("low_freq_ratio", {})
    low_freq_ratio_raw = _as_float(low_freq_indicator.get("value") if isinstance(low_freq_indicator, dict) else low_freq_indicator, 0.0)
    if low_freq_ratio_raw > 0.55:
        low_freq_dominance = True

    confidence = 0.0
    if param_hits >= 2:
        confidence = 0.85
    elif param_hits == 1 and (stat_hits >= 1 or impulse_context):
        confidence = 0.65
    elif stat_hits >= 3 and impulse_context:
        confidence = 0.65
    elif stat_hits >= 2 and impulse_context:
        # 双统计指标 + 冲击背景：内圈/外圈/球故障典型模式
        # moderate_kurtosis 使外圈也能进入此路径
        confidence = 0.55
    elif stat_hits >= 1 and impulse_context and strongest_snr > 12:
        # 单统计指标 + 冲击背景 + 较显著 SNR：
        # 外圈故障仅触发 moderate_kurtosis 而无 envelope_kurtosis 时的兜底
        # 若包络谱低频占优（轴频谐波），则降权抑制误报
        if low_freq_dominance:
            confidence = 0.28
        else:
            confidence = 0.45
    elif stat_hits >= 2:
        confidence = 0.35
    elif strongest_snr > 18 and impulse_context:
        confidence = 0.5

    return {
        "confidence": round(float(confidence), 4),
        "param_hits": int(param_hits),
        "stat_hits": int(stat_hits),
        "strongest_snr": round(float(strongest_snr), 3),
        "hits": hit_names,
        "abnormal": bool(confidence >= 0.55),
    }


def _gear_confidence(result: Dict, has_gear_params: bool) -> Dict[str, Any]:
    indicators = result.get("fault_indicators", {}) or {}
    warning_hits = 0
    critical_hits = 0
    hit_names = []

    for name, item in indicators.items():
        if not isinstance(item, dict):
            continue
        if item.get("critical"):
            critical_hits += 1
            hit_names.append(name)
        elif item.get("warning"):
            warning_hits += 1
            hit_names.append(name)

    confidence = 0.0
    if has_gear_params:
        if critical_hits >= 1 and (warning_hits + critical_hits) >= 2:
            confidence = 0.8
        elif critical_hits >= 1 or warning_hits >= 2:
            confidence = 0.6
        elif warning_hits == 1:
            confidence = 0.35
    else:
        # Without gear geometry, CAR/order statistics are weak evidence only.
        if critical_hits >= 2:
            confidence = 0.35
        elif critical_hits == 1 and warning_hits >= 1:
            confidence = 0.3
        elif warning_hits >= 2:
            confidence = 0.25

    return {
        "confidence": round(float(confidence), 4),
        "warning_hits": int(warning_hits),
        "critical_hits": int(critical_hits),
        "hits": hit_names,
        "abnormal": bool(confidence >= 0.55),
    }


def _time_confidence(time_features: Dict) -> float:
    kurt = _as_float(time_features.get("kurtosis"), 3.0)
    crest = _as_float(time_features.get("crest_factor"), 5.0)
    rms_mad_z = _as_float(time_features.get("rms_mad_z"), 0.0)
    cusum = _as_float(time_features.get("cusum_score"), 0.0)

    score = 0.0
    if kurt > 20:
        score = max(score, 0.85)
    elif kurt > 12:
        score = max(score, 0.7)
    elif kurt > 8:
        score = max(score, 0.55)
    elif kurt > 5:
        score = max(score, 0.35)

    if crest > 15:
        score = max(score, 0.65)
    elif crest > 10:
        score = max(score, 0.45)

    if rms_mad_z > 6 or cusum > 10:
        score = max(score, 0.45)
    return round(float(score), 4)


def _fault_label(best_bearing: Dict, best_gear: Dict, bearing_score: float, gear_score: float) -> str:
    if gear_score > bearing_score and gear_score >= 0.55:
        return "gear_abnormal"

    indicators = best_bearing.get("fault_indicators", {}) if best_bearing else {}
    param_hits = [
        name for name, item in indicators.items()
        if isinstance(item, dict) and item.get("significant") and not name.endswith("_stat")
    ]
    if param_hits:
        return "bearing_" + "_".join(param_hits[:2])
    if bearing_score >= 0.55:
        return "bearing_abnormal"
    return "unknown"


def run_research_ensemble(
    signal: np.ndarray,
    fs: float,
    bearing_params: Optional[Dict] = None,
    gear_teeth: Optional[Dict] = None,
    denoise_method: str = "none",
    rot_freq: Optional[float] = None,
    profile: str = "runtime",
    max_seconds: float = 5.0,
) -> Dict[str, Any]:
    arr = np.array(signal, dtype=np.float64)
    if max_seconds and max_seconds > 0:
        max_samples = int(fs * max_seconds)
        if len(arr) > max_samples:
            arr = arr[:max_samples]

    config = _profile_config(profile, denoise_method)
    has_gear = _has_gear_params(gear_teeth)

    bearing_results: Dict[str, Dict] = {}
    gear_results: Dict[str, Dict] = {}
    bearing_votes: Dict[str, Dict] = {}
    gear_votes: Dict[str, Dict] = {}
    rot_freq_by_denoise: Dict[str, float] = {}

    best_time_features: Optional[Dict] = None
    best_bearing_key = None
    best_gear_key = None

    for denoise in config["denoise"]:
        base = DiagnosisEngine(
            strategy=DiagnosisStrategy.STANDARD,
            denoise_method=_safe_denoise(denoise),
            bearing_params=bearing_params,
            gear_teeth=gear_teeth,
        )
        proc = base.preprocess(arr)
        time_features = compute_time_features(proc)
        if best_time_features is None:
            best_time_features = time_features

        rf = rot_freq
        cached_oa = cached_os = None
        if rf is None:
            try:
                rf, cached_oa, cached_os, _ = base._estimate_rot_freq(proc, fs)
            except Exception:
                rf = 0.0
        rot_freq_by_denoise[denoise] = round(float(rf or 0.0), 3)

        for method in config["bearing"]:
            key = f"{denoise}:{method.value}"
            try:
                engine = DiagnosisEngine(
                    strategy=DiagnosisStrategy.STANDARD,
                    bearing_method=method,
                    denoise_method=_safe_denoise(denoise),
                    bearing_params=bearing_params,
                    gear_teeth=gear_teeth,
                )
                result = engine.analyze_bearing(proc, fs, rf, preprocess=False)
                result["denoise"] = denoise
                bearing_results[key] = result
                vote = _bearing_confidence(result, time_features)
                bearing_votes[key] = vote
                if best_bearing_key is None or vote["confidence"] > bearing_votes[best_bearing_key]["confidence"]:
                    best_bearing_key = key
            except Exception as exc:
                bearing_results[key] = {"error": str(exc), "denoise": denoise, "method": method.value}
                bearing_votes[key] = {"confidence": 0.0, "abnormal": False, "error": str(exc)}

        for method in config["gear"]:
            key = f"{denoise}:{method.value}"
            try:
                engine = DiagnosisEngine(
                    strategy=DiagnosisStrategy.STANDARD,
                    gear_method=method,
                    denoise_method=_safe_denoise(denoise),
                    bearing_params=bearing_params,
                    gear_teeth=gear_teeth,
                )
                result = engine.analyze_gear(
                    proc,
                    fs,
                    rf,
                    preprocess=False,
                    _cached_oa=cached_oa,
                    _cached_os=cached_os,
                )
                result["denoise"] = denoise
                gear_results[key] = result
                vote = _gear_confidence(result, has_gear)
                gear_votes[key] = vote
                if best_gear_key is None or vote["confidence"] > gear_votes[best_gear_key]["confidence"]:
                    best_gear_key = key
            except Exception as exc:
                gear_results[key] = {"error": str(exc), "denoise": denoise, "method": method.value}
                gear_votes[key] = {"confidence": 0.0, "abnormal": False, "error": str(exc)}

    time_features = best_time_features or compute_time_features(arr)
    time_score = _time_confidence(time_features)

    bearing_conf = [v.get("confidence", 0.0) for v in bearing_votes.values()]
    gear_conf = [v.get("confidence", 0.0) for v in gear_votes.values()]
    bearing_vote_fraction = (
        sum(1 for v in bearing_conf if v >= 0.55) / len(bearing_conf)
        if bearing_conf else 0.0
    )
    gear_vote_fraction = (
        sum(1 for v in gear_conf if v >= 0.55) / len(gear_conf)
        if gear_conf else 0.0
    )

    bearing_score = max(bearing_conf or [0.0]) * 0.55 + bearing_vote_fraction * 0.45
    gear_score = max(gear_conf or [0.0]) * 0.65 + gear_vote_fraction * 0.35
    likelihood = max(time_score * 0.6, bearing_score, gear_score)

    if likelihood >= 0.72 or (bearing_vote_fraction >= 0.5 and max(bearing_conf or [0]) >= 0.65):
        status = "fault"
    elif likelihood >= 0.45 or bearing_vote_fraction >= 0.35 or gear_vote_fraction >= 0.5:
        status = "warning"
    else:
        status = "normal"

    health_score = int(max(0, min(100, round(100 - likelihood * 72))))
    best_bearing = bearing_results.get(best_bearing_key, {}) if best_bearing_key else {}
    best_gear = gear_results.get(best_gear_key, {}) if best_gear_key else {}
    fault_label = _fault_label(best_bearing, best_gear, bearing_score, gear_score)

    return {
        "health_score": health_score,
        "status": status,
        "fault_likelihood": round(float(likelihood), 4),
        "fault_label": fault_label,
        "rot_freq_hz": next(iter(rot_freq_by_denoise.values()), None),
        "time_features": time_features,
        "bearing": best_bearing,
        "gear": best_gear,
        "bearing_results": bearing_results,
        "gear_results": gear_results,
        "ensemble": {
            "profile": profile,
            "rot_freq_by_denoise": rot_freq_by_denoise,
            "bearing_votes": bearing_votes,
            "gear_votes": gear_votes,
            "bearing_vote_fraction": round(float(bearing_vote_fraction), 4),
            "gear_vote_fraction": round(float(gear_vote_fraction), 4),
            "time_confidence": time_score,
            "bearing_confidence": round(float(bearing_score), 4),
            "gear_confidence": round(float(gear_score), 4),
            "best_bearing": best_bearing_key,
            "best_gear": best_gear_key,
        },
        "recommendation": _generate_recommendation(best_bearing, best_gear, status),
    }
