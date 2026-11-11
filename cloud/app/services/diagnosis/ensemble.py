"""业务编排只选取并串行运行对象 Pipeline；评估/融合/评分只有 assessment 一份。"""
from __future__ import annotations

from dataclasses import replace
from typing import Dict
import numpy as np

from .engine import BearingMethod, GearMethod, DenoiseMethod, DiagnosisEngine
from .features import compute_time_features
from .domain import DiagnosisKey
from .adapters import combine_method_results
from .gear.planetary import is_planetary_config
from .assessment import SEVERITY
from .domain import DiagnosisConclusion

def _safe_denoise(value):
    return DenoiseMethod(value)

def _profile_config(profile: str, denoise_method: str) -> Dict[str, list]:
    if profile not in {"runtime", "balanced", "exhaustive"}:
        raise ValueError("unknown_diagnosis_profile")
    configured_denoise = _safe_denoise(denoise_method).value
    denoise_methods = ["none"]
    if configured_denoise != "none":
        denoise_methods.append(configured_denoise)

    if profile == "exhaustive":
        return {
            "denoise": list(dict.fromkeys(denoise_methods + ["wavelet", "vmd", "wavelet_vmd", "wavelet_lms", "emd", "ceemdan", "savgol", "wavelet_packet", "eemd"])),
            "bearing": [
                BearingMethod.ENVELOPE,
                BearingMethod.FILTER_BANK_SK,
                BearingMethod.CPW,
                BearingMethod.TEAGER,
                BearingMethod.SPECTRAL_KURTOSIS,
                BearingMethod.MED,
                BearingMethod.SC_SCOH,
                BearingMethod.MCKD,
                BearingMethod.WP,
                BearingMethod.DWT,
                BearingMethod.EMD_ENVELOPE,
                BearingMethod.CEEMDAN_ENVELOPE,
                BearingMethod.VMD_ENVELOPE,
            ],
            "gear": [GearMethod.STANDARD, GearMethod.ADVANCED],
        }

    if profile == "balanced":
        return {
            "denoise": denoise_methods,
            "bearing": [
                BearingMethod.ENVELOPE,
                BearingMethod.FILTER_BANK_SK,
                BearingMethod.CPW,
                BearingMethod.TEAGER,
                BearingMethod.SPECTRAL_KURTOSIS,
                BearingMethod.MCKD,
                BearingMethod.EMD_ENVELOPE,
                BearingMethod.VMD_ENVELOPE,
            ],
            "gear": [GearMethod.ADVANCED],
        }

    return {
        "denoise": [configured_denoise],
        "bearing": [
            BearingMethod.ENVELOPE,
            BearingMethod.FILTER_BANK_SK,
            BearingMethod.CPW,
            BearingMethod.TEAGER,
        ],
        "gear": [GearMethod.ADVANCED],
    }



def run_research_ensemble(signal, fs, bearing_params=None, gear_teeth=None,
                          denoise_method="none", rot_freq=None, profile="runtime",
                          max_seconds=5.0, bearing_options=None, diagnosis_key=None):
    arr = np.asarray(signal, dtype=float)
    if arr.ndim != 1:
        raise ValueError("diagnosis_signal_requires_one_dimension")
    if not np.isfinite(fs) or fs <= 0:
        raise ValueError("invalid_sample_rate")
    arr = arr[:int(fs * min(max_seconds or 5., 5.))]
    config = _profile_config(profile, denoise_method)
    key = diagnosis_key or DiagnosisKey("interactive", 1, 1, denoise_method)
    bearing_results, gear_results = {}, {}
    selected_bearing = bool(bearing_params) or not gear_teeth
    selected_gear = bool(gear_teeth) or not bearing_params
    # 去噪参数改变计算表示，但不改变原始记录的共同依赖；不得增加独立票数。
    for denoise in config["denoise"]:
        local_key = replace(key, denoise_method=denoise)
        if selected_bearing:
            for method in config["bearing"]:
                effective = BearingMethod.MED if method == BearingMethod.MCKD and not (bearing_options or {}).get("target_fault") else method
                name = f"{denoise}:{effective.value}"
                if name in bearing_results:
                    continue
                engine = DiagnosisEngine(bearing_method=effective, denoise_method=denoise,
                                         bearing_params=bearing_params, gear_teeth=gear_teeth,
                                         bearing_options=bearing_options, diagnosis_key=local_key)
                bearing_results[name] = engine.analyze_bearing(arr, fs, rot_freq)
        if selected_gear:
            gear_methods = [config["gear"][-1]] if is_planetary_config(gear_teeth) else config["gear"]
            for method in gear_methods:
                name = f"{denoise}:{method.value}"
                engine = DiagnosisEngine(gear_method=method, denoise_method=denoise,
                                         bearing_params=bearing_params, gear_teeth=gear_teeth,
                                         diagnosis_key=local_key)
                gear_results[name] = engine.analyze_gear(arr, fs, rot_freq)
    assessment = combine_method_results({**bearing_results, **gear_results})
    def representative(values):
        if not values:
            return {}
        return max(values.values(), key=lambda item: SEVERITY.get(DiagnosisConclusion(item["diagnosis_conclusion"]), -1))
    return {
        **assessment,
        "bearing": representative(bearing_results), "gear": representative(gear_results),
        "bearing_results": bearing_results, "gear_results": gear_results,
        "time_features": compute_time_features(arr) if len(arr) else {},
        "rot_freq_hz": rot_freq,
        "ensemble": {"profile": profile, "dependency_policy": "shared_raw_record_not_independent_variants",
                     "object_fusion": {item["object_id"]: item["fusion"] for item in assessment["evaluations"]}},
    }
