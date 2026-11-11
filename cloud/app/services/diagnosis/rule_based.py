"""标准对象 Pipeline 的轻量业务回退；不另建频谱、包络或阶次算法。"""
import logging
from dataclasses import asdict
from typing import Dict, List

import numpy as np

from app.algorithms.mechanics import FixedAxisGearGeometry
from app.algorithms.order import (
    AutomaticOrderPipeline, LocalSpeedEstimates, OrderParameters, ScalarSpeed, SpeedTrajectory,
)
from app.algorithms.pipelines.bearing import BearingEnvelopePipeline
from app.algorithms.pipelines.gear.fixed_axis import FixedAxisGearPipeline
from app.algorithms.statistics import analyze_time_domain
from app.algorithms.transforms import compute_spectrum
from .engine import bearing_geometry_from_config
from .features import _get_channel_params
from .health_score import _compute_health_score, _has_diagnosis_evidence
from .probability_calibration import calibrate_fault_probabilities
from .signal_utils import prepare_signal

logger = logging.getLogger(__name__)


def _indeterminate(reason: str) -> dict:
    """前提失败不能经外层异常兜底变成正常诊断。"""
    return {
        "health_score": None, "fault_probabilities": {}, "imf_energy": {},
        "status": "indeterminate",
        "order_analysis": {"status": "indeterminate", "reason": reason}, "rot_freq": None,
    }


def _rule_based_analyze(
    channels_data: Dict[str, List[float]], sample_rate: int = 25600, device=None,
):
    """以首个实际通道的对象参数执行回退，其他通道仅参与时域均值。

    数值表示始终保留 NumPy；这里只返回持久化需要的标量指标。没有几何
    参数时仅允许通用统计证据，不猜测轴承故障类型；行星箱不套用定轴模型。
    ``imf_energy`` 沿用展示字段名，实际是五个等宽频带的功率百分比，并非 IMF。
    """
    if not channels_data:
        return _indeterminate("missing_channel_signal")
    try:
        prepared = {}
        time_features = []
        for name, signal in channels_data.items():
            values = np.asarray(signal, dtype=np.float64)
            if values.ndim != 1 or len(values) < 64 or not np.all(np.isfinite(values)):
                return _indeterminate("invalid_channel_signal")
            arr = prepare_signal(values, detrend=True)
            prepared[name] = arr
            time_features.append(asdict(analyze_time_domain(arr, sample_rate).overall))

        first_name, arr = next(iter(prepared.items()))
        channel_index = int(str(first_name).removeprefix("ch"))
        gear_config = getattr(device, "gear_teeth", None) if device else None
        if gear_config is not None:
            if not isinstance(gear_config, dict):
                return _indeterminate("invalid_gear_configuration")
            if str(channel_index) in gear_config:
                gear_config = gear_config[str(channel_index)]
            elif any(str(key).isdigit() for key in gear_config):
                gear_config = None
        bearing_config = _get_channel_params(device, channel_index, "bearing_params")
        if gear_config and any(gear_config.get(key) for key in ("sun", "ring", "planet_count", "n_planets")):
            return _indeterminate("planetary_fallback_requires_planetary_pipeline")
        bearing_geometry = bearing_geometry_from_config(bearing_config)
        gear_geometry = None
        if gear_config:
            # 畸形/缺项配置保留不可判定；不把 None 齿数当作正常证据。
            raw_teeth = gear_config.get("input")
            if isinstance(raw_teeth, bool) or raw_teeth is None:
                return _indeterminate("invalid_fixed_axis_geometry")
            teeth = float(raw_teeth)
            if not np.isfinite(teeth) or not teeth.is_integer():
                return _indeterminate("invalid_fixed_axis_geometry")
            gear_geometry = FixedAxisGearGeometry(input_teeth=int(teeth))

        gear_pipeline = FixedAxisGearPipeline(geometry=gear_geometry)
        max_order = max(50.0, gear_pipeline.required_max_order(False)) if gear_geometry else 50.0
        order = AutomaticOrderPipeline(
            parameters=OrderParameters(samples_per_revolution=1024, max_order=max_order),
        ).run(arr, sample_rate)
        if order.status != "valid" or order.spectrum is None:
            return _indeterminate(order.reason or "unavailable_order_analysis")
        if isinstance(order.speed, ScalarSpeed):
            rot_freq, rot_std = float(order.speed.frequency_hz), 0.0
        elif isinstance(order.speed, LocalSpeedEstimates):
            rot_freq, rot_std = order.speed.median_hz, order.speed.std_hz
        elif isinstance(order.speed, SpeedTrajectory):
            rot_freq = float(np.median(order.speed.frequency_hz))
            rot_std = float(np.std(order.speed.frequency_hz))
        else:
            return _indeterminate("missing_speed_representation")

        bearing_result = {
            "evaluation": {"status": "indeterminate", "indicators": {}},
            "reason": "bearing_requires_constant_or_slowly_varying_speed",
        }
        # 连续相位只为阶次谱提供补偿，不能将轨迹中位数当成轴承恒速前提。
        if not isinstance(order.speed, SpeedTrajectory):
            bearing = BearingEnvelopePipeline(geometry=bearing_geometry).run(
                arr, sample_rate, rot_frequency_hz=rot_freq, rot_frequency_std_hz=rot_std,
            )
            bearing_result = {
                "features": bearing.analysis.envelope_analysis.features.as_dict(),
                "evaluation": {
                    "status": bearing.evaluation.status, "indicators": bearing.evaluation.indicators,
                },
            }
        gear_result = {}
        if gear_geometry:
            gear = gear_pipeline.run(arr, sample_rate, order_analysis=order)
            gear_result = {
                "analysis_status": gear.evaluation.status,
                "fault_indicators": gear.evaluation.indicators,
                "evaluation": {
                    "status": gear.evaluation.status, "indicators": gear.evaluation.indicators,
                },
            }

        averaged = {
            key: float(np.mean([features[key] for features in time_features]))
            for key in time_features[0]
        }
        if not _has_diagnosis_evidence((bearing_result, gear_result), averaged):
            return _indeterminate("no_evaluable_diagnosis_evidence")
        health_score, status, _ = _compute_health_score(
            gear_config, averaged, bearing_result, gear_result,
        )
        fault_scores = {}
        labels = {"BPFO": "轴承外圈故障", "BPFI": "轴承内圈故障", "BSF": "滚动体故障"}
        for name, indicator in bearing_result["evaluation"]["indicators"].items():
            if name in labels and indicator.get("significant"):
                fault_scores[labels[name]] = min(1.0, float(indicator.get("snr") or 0.0) / 10.0)
        for indicator in gear_result.get("fault_indicators", {}).values():
            severity = 0.6 if indicator.get("critical") else 0.3 if indicator.get("warning") else 0.0
            if severity:
                fault_scores["齿轮磨损"] = max(fault_scores.get("齿轮磨损", 0.0), severity)

        fourier = compute_spectrum(arr, sample_rate)
        # 五等宽频带用于既有能量图；复用同一带单位功率表示，包含 Nyquist。
        band_edges = np.linspace(0.0, sample_rate / 2.0, 6)
        band_index = np.minimum(np.searchsorted(band_edges, fourier.frequency_hz, side="right") - 1, 4)
        band_power = np.bincount(band_index, weights=fourier.power, minlength=5)
        total_power = float(np.sum(band_power))
        energy = {
            f"IMF{index + 1}": round(float(value) / total_power * 100.0, 2) if total_power > 0 else 0.0
            for index, value in enumerate(band_power)
        }
        return {
            "health_score": health_score,
            "fault_probabilities": calibrate_fault_probabilities(fault_scores),
            "imf_energy": energy,
            "imf_energy_kind": "five_equal_frequency_bands_power_percent",
            "status": status,
            "order_analysis": {
                "rot_freq_hz": round(rot_freq, 3), "rot_rpm": round(rot_freq * 60.0, 1),
                "tracking_method": order.tracking_method, "channel": channel_index,
                "time_features": averaged, "bearing": bearing_result, "gear": gear_result,
            },
            "rot_freq": rot_freq,
        }
    except (TypeError, ValueError, OverflowError) as exc:
        logger.warning("规则回退前提不满足: %s", exc)
        return _indeterminate(str(exc))
