"""后台设备编排：按真实通道号运行对象诊断并保留每个局部评估。"""
from __future__ import annotations
import re
from dataclasses import replace

from app.core.config import ANALYZE_DENOISE_METHOD
from app.services.diagnosis import DiagnosisEngine
from app.services.diagnosis.assessment import assess_evidence
from app.services.diagnosis.adapters import unavailable_result, combine_method_results
from app.services.diagnosis.domain import DiagnosisKey, Evidence
from app.services.diagnosis.gear.planetary import gear_config_for_channel

def channel_number(value):
    match = re.fullmatch(r"(?:ch)?([1-9][0-9]*)", str(value))
    if not match:
        raise ValueError(f"invalid_real_channel_identity:{value}")
    return int(match.group(1))

def analyze_device(channels_data, sample_rate=25600, device=None, rot_freq=None,
                   denoise_method="", batch_index=1):
    denoise = denoise_method or getattr(device, "denoise_method", None) or ANALYZE_DENOISE_METHOD
    device_id = getattr(device, "device_id", "interactive")
    channels, combined = {}, {}
    raw_bearing = getattr(device, "bearing_params", None) or {}
    for channel_key, signal in sorted(channels_data.items(), key=lambda item: channel_number(item[0])):
        channel = channel_number(channel_key)
        bearing = raw_bearing.get(str(channel), {}) if not any(key in raw_bearing for key in ("n", "d", "D")) else raw_bearing
        gear = gear_config_for_channel(getattr(device, "gear_teeth", None), channel)
        key = DiagnosisKey(device_id, batch_index, channel, denoise)
        try:
            engine = DiagnosisEngine(bearing_params=bearing, gear_teeth=gear, denoise_method=denoise, diagnosis_key=key)
            result = engine.analyze_research_ensemble(signal, sample_rate, rot_freq=rot_freq, profile="runtime")
        except Exception as exc:
            # 单个坏通道保留未知评估，不能清空其他通道的有效结果。
            local = {"bearing": unavailable_result(str(exc), key=key, object_id="bearing", method="envelope", indeterminate=True),
                     "gear": unavailable_result(str(exc), key=key, object_id="gear", method="advanced", indeterminate=True)}
            result = {**combine_method_results(local), **local, "reason": str(exc)}
        channels[f"ch{channel}"] = result
        for evaluation in result["evaluations"]:
            scoped_id = f"ch{channel}/{evaluation['object_id']}"
            # 对象身份包含真实通道，跨通道不当作同一个假设再次乘票。
            combined[scoped_id] = tuple(replace(Evidence.from_dict(value), object_id=scoped_id) for value in evaluation["evidence"])
    assessment = assess_evidence(combined).to_dict()
    return {**assessment, "channels": channels, "rot_freq": rot_freq,
            "aggregation": {"policy": "worst_valid_object_conclusion_with_partial_coverage",
                            "channel_numbers": [channel_number(key) for key in channels]}}
