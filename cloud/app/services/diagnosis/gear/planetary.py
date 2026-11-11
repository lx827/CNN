"""设备配置和 JSON 读模型适配；行星数学与评估只在 algorithms 内实现。"""

from dataclasses import asdict
from typing import Mapping

import numpy as np

from app.algorithms.gear.planetary.types import (
    PlanetaryAnalysis,
    PlanetaryBaseline,
    PlanetaryMomentHistory,
    PlanetaryParameters,
)
from app.algorithms.mechanics.planetary import PlanetaryGearGeometry
from app.algorithms.order import OrderAnalysis, ScalarSpeed
from app.algorithms.pipelines.gear.planetary import (
    PlanetaryGearDiagnosis,
    PlanetaryGearPipeline,
)
from app.algorithms.transforms.display import decimate_extrema


def is_planetary_config(values: Mapping | None) -> bool:
    """存在行星专属配置即走行星门控；缺参数不能误落入定轴路径。"""
    if not isinstance(values, Mapping) or values.get("gear_type") == "fixed_axis":
        return False
    return values.get("gear_type") == "planetary" or any(
        values.get(key) is not None
        for key in (
            "sun",
            "ring",
            "planet",
            "planet_count",
            "reference_axis",
            "fixed_member",
        )
    )


def gear_config_for_channel(values: Mapping | None, channel: int) -> dict:
    """设备级参数完整传递；通道级只选择当前通道，不借用第一通道几何。"""
    if not isinstance(values, Mapping):
        return {}
    if any(key in values for key in ("input", "output")) or is_planetary_config(values):
        return dict(values)
    selected = values.get(str(channel), {})
    return dict(selected) if isinstance(selected, Mapping) else {}


def planetary_geometry_from_config(
    values: Mapping | None,
    *,
    reference_axis: str | None = None,
    fixed_member: str | None = None,
) -> PlanetaryGearGeometry:
    """完整齿数、轴和固定构件均须显式来自设备或调用契约，不按 input 猜 sun。"""
    values = values or {}

    def teeth(key: str) -> int:
        value = values.get(key)
        if isinstance(value, bool) or value is None:
            raise ValueError(f"missing_or_invalid_planetary_{key}")
        numeric = float(value)
        if not np.isfinite(numeric) or not numeric.is_integer():
            raise ValueError(f"invalid_planetary_{key}")
        return int(numeric)

    axis = values.get("reference_axis", reference_axis)
    fixed = values.get("fixed_member", fixed_member)
    if axis is None or fixed is None:
        raise ValueError("missing_planetary_reference_axis_or_fixed_member")
    return PlanetaryGearGeometry(
        teeth("sun"), teeth("ring"), teeth("planet"), teeth("planet_count"), axis, fixed
    )


def planetary_diagnosis_to_dict(diagnosis: PlanetaryGearDiagnosis) -> dict:
    """边界才把绘图数组转 list，内部谱和角域样本始终保持 ndarray。"""
    analysis, evaluation = diagnosis.analysis, diagnosis.evaluation
    geometry = analysis.geometry
    methods = {}
    for method in analysis.methods:
        item = {
            "method": method.method,
            "status": method.status,
            "reason": method.reason,
            "reference_axis": method.reference_axis,
            "peaks": [asdict(peak) for peak in method.peaks],
            "metrics": {key: asdict(value) for key, value in method.metrics.items()},
            "details": method.details,
        }
        if method.spectrum:
            item["spectrum"] = {
                "points": decimate_extrema(
                    method.spectrum.order_bins, method.spectrum.amplitude, maximum=1200
                ).tolist(),
                "order_resolution": method.spectrum.order_resolution,
                "total_revolutions": method.spectrum.total_revolutions,
                "amplitude_scaling": method.spectrum.scaling,
                "samples_per_revolution": method.spectrum.samples_per_revolution,
            }
        methods[method.method] = item
    return {
        "method": "planetary_gear",
        "is_planetary": True,
        "planet_count": geometry.planet_count if geometry else None,
        "analysis_status": analysis.status,
        "evaluation_status": evaluation.status,
        "diagnosis_conclusion": evaluation.conclusion,
        "status": evaluation.status,
        "reason": analysis.reason or evaluation.reason,
        "rot_freq_hz": analysis.reference_speed_hz,
        "mesh_order": geometry.mesh_order if geometry else None,
        "mesh_freq_hz": geometry.mesh_order * analysis.reference_speed_hz
        if geometry and analysis.reference_speed_hz
        else None,
        "mechanical_model": {
            "topology": "simple_planetary_fixed_ring",
            "reference_axis": geometry.reference_axis,
            "sun_teeth": geometry.sun_teeth,
            "ring_teeth": geometry.ring_teeth,
            "planet_teeth": geometry.planet_teeth,
            "planet_count": geometry.planet_count,
            "carrier_order": geometry.carrier_order,
            "sun_relative_to_carrier_order": geometry.sun_relative_order,
            "planet_relative_to_carrier_order": geometry.planet_relative_order,
            "planet_absolute_signed_order": geometry.axis_order("planet"),
            "event_order_candidates": geometry.event_orders,
            "limitation": "kinematic_candidates_do_not_identify_arbitrary_planet_local_damage",
        }
        if geometry
        else None,
        "metrics": {key: asdict(metric) for key, metric in analysis.metrics.items()},
        "sideband_analysis": {
            "ser": asdict(analysis.sidebands.ser),
            "spacing_order": analysis.sidebands.spacing_order,
            "mesh_amplitude": analysis.sidebands.mesh_amplitude,
            "observations": list(analysis.sidebands.observations),
        }
        if analysis.sidebands
        else None,
        "planetary_methods": methods,
        "tsa": {
            "reference_axis": analysis.tsa_reference_axis,
            "revolutions": analysis.synchronous.revolutions,
            "samples_per_revolution": analysis.synchronous.angle_domain.samples_per_revolution,
        }
        if analysis.synchronous
        else None,
        "evaluation": asdict(evaluation),
        "fault_indicators": evaluation.indicators,
        "validation": {
            "physical_synthetic_vectors": True,
            "real_dataset_effectiveness": "not_validated",
            "uncalibrated_metrics_do_not_trigger_alarms": True,
        },
    }


def analyze_planetary_gear(
    signal: np.ndarray,
    sample_rate_hz: float,
    gear_teeth: Mapping | None,
    *,
    speed: ScalarSpeed | None = None,
    order_analysis: OrderAnalysis | None = None,
    include_tsa: bool = True,
    reference_axis: str | None = None,
    fixed_member: str | None = None,
    parameters: PlanetaryParameters = PlanetaryParameters(),
    baseline: PlanetaryBaseline | None = None,
    history: PlanetaryMomentHistory | None = None,
    methods: tuple[str, ...] = ("narrowband", "fullband", "highpass", "tsa_residual"),
) -> dict:
    """业务唯一入口；单方法研究调用也走同一个对象分析/评估 Pipeline。"""
    try:
        geometry = planetary_geometry_from_config(
            gear_teeth, reference_axis=reference_axis, fixed_member=fixed_member
        )
    except (TypeError, ValueError, OverflowError) as exc:
        analysis = PlanetaryAnalysis("not_evaluable", None, None, reason=str(exc))
        pipeline = PlanetaryGearPipeline(None, parameters)
        return planetary_diagnosis_to_dict(
            PlanetaryGearDiagnosis(analysis, pipeline.evaluate(analysis, baseline))
        )
    return planetary_diagnosis_to_dict(
        PlanetaryGearPipeline(geometry, parameters).run(
            signal,
            sample_rate_hz,
            speed,
            order_analysis=order_analysis,
            include_tsa=include_tsa,
            baseline=baseline,
            history=history,
            methods=methods,
        )
    )
