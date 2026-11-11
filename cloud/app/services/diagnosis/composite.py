"""复合流程研究服务与显式 JSON 边界；不参与生产评分、投票或告警。"""
from dataclasses import fields, is_dataclass, replace
from collections.abc import Mapping

import numpy as np

from app.algorithms.composite.cvs import CVSAlignment
from app.algorithms.composite.ica import FastICAParameters
from app.algorithms.composite.msb import MSBParameters
from app.algorithms.bearing.deconvolution import MEDParameters
from app.algorithms.decomposition.vmd import VMDParameters
from app.algorithms.mechanics.planetary import PlanetaryGearGeometry
from app.algorithms.order import ScalarSpeed
from app.algorithms.pipelines.composite import (
    CompositeAnalysis, CompositeDiagnosis, ResearchCompositePipeline, VMDAMFMPipeline,
    ModulationBispectrumPipeline, CVSMEDMSBPipeline, VMDICAPipeline, MSWPEEPipeline,
)


RESEARCH_COMPOSITE_METHODS = ("vmd_amfm", "modulation_bispectrum", "cvs_med_msb", "vmd_ica", "mswpee")


def analyze_composite_research(method, signal, sample_rate_hz, *, geometry=None, speed=None,
                               alignment: CVSAlignment | None = None, options=None) -> CompositeDiagnosis:
    """研究入口先限五秒，再执行串行阶段；返回 dataclass/NumPy，不写数据库。

    AM/FM、MSB和CVS要求调用方提供机械对象与真实标量恒速。CVS还要求
    传感器方位、特定行星编号与两个实测连续相位，不能从振动自动捏造零位。
    调用方必须显式展示 research_only，不得把该结果送入生产融合器。
    """
    if method not in RESEARCH_COMPOSITE_METHODS:
        raise ValueError("unknown_research_composite_method")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be positive")
    values = np.asarray(signal, dtype=float)
    if values.ndim != 1 or len(values) < 64 or not np.all(np.isfinite(values)):
        raise ValueError("research composite input must have >=64 finite samples")
    values = values[:int(sample_rate_hz * 5)]
    options = options or {}
    if not isinstance(options, Mapping):
        raise ValueError("research options must be a mapping")
    if method == "mswpee":
        return MSWPEEPipeline(options.get("wavelet", "db8"), options.get("level", 3),
                              options.get("max_scale", 5)).run(values, sample_rate_hz)
    vmd = VMDParameters(modes=options.get("modes", 3), alpha=options.get("alpha", 2000.0),
                        max_iterations=options.get("vmd_iterations", 200),
                        tolerance=options.get("vmd_tolerance", 1e-7), max_samples=51200)
    if method == "vmd_ica":
        return VMDICAPipeline(vmd, FastICAParameters(
            max_iterations=options.get("ica_iterations", 200), tolerance=options.get("ica_tolerance", 1e-6),
            seed=options.get("seed", 0)), top_n=options.get("top_n", 1)).run(values, sample_rate_hz)
    if method == "vmd_amfm":
        return VMDAMFMPipeline(vmd).run(values, sample_rate_hz, geometry, speed)
    if geometry is None or not isinstance(speed, ScalarSpeed):
        analysis = CompositeAnalysis(method, "indeterminate", (), reason="missing_geometry_or_constant_reference_speed")
        return CompositeDiagnosis(analysis, ResearchCompositePipeline().evaluate(analysis))
    mesh_hz = geometry.mesh_order * speed.frequency_hz
    if isinstance(geometry, PlanetaryGearGeometry):
        targets = {name: order * speed.frequency_hz for name, order in geometry.event_orders.items()}
    else:
        targets = {"input_rotation": speed.frequency_hz}
    segment_length = options.get("segment_length", 1024)
    msb = MSBParameters(segment_length, options.get("overlap", .5))
    # 候选与局部背景处于同一modulation轴。指定候选保留真实Hz，不把超带宽值夹到Nyquist。
    df = sample_rate_hz / segment_length
    upper = min(mesh_hz * .8, max(targets.values()) * 2)
    grid = np.unique(np.r_[np.arange(df, upper, df), list(targets.values())])
    if len(grid) > 1024:
        raise ValueError("requested_MSB_background_grid_is_too_large")
    if method == "modulation_bispectrum":
        return ModulationBispectrumPipeline(msb).run(values, sample_rate_hz, [mesh_hz], grid)
    if not isinstance(geometry, PlanetaryGearGeometry):
        analysis = CompositeAnalysis(method, "indeterminate", (), reason="CVS_requires_planetary_geometry")
        return CompositeDiagnosis(analysis, ResearchCompositePipeline().evaluate(analysis))
    if alignment is not None:
        if len(alignment.planet_azimuths_rad) != geometry.planet_count or not np.isclose(
            alignment.planet_relative_frequency_hz, geometry.planet_relative_order * speed.frequency_hz, rtol=.01):
            analysis = CompositeAnalysis(method, "indeterminate", (), reason="CVS_alignment_does_not_match_planetary_kinematics")
            return CompositeDiagnosis(analysis, ResearchCompositePipeline().evaluate(analysis))
        carrier_phase = np.asarray(alignment.carrier_phase_rad)
        if carrier_phase.ndim != 1 or not np.allclose(
            np.diff(carrier_phase) * sample_rate_hz / (2 * np.pi),
            geometry.carrier_order * speed.frequency_hz, rtol=.01, atol=0):
            analysis = CompositeAnalysis(method, "indeterminate", (), reason="CVS_carrier_phase_does_not_match_reference_speed")
            return CompositeDiagnosis(analysis, ResearchCompositePipeline().evaluate(analysis))
        alignment = replace(alignment, carrier_phase_rad=carrier_phase[:len(values)],
                            planet_phase_rad=np.asarray(alignment.planet_phase_rad)[:len(values)])
    med = MEDParameters(filter_length=options.get("filter_length", 30),
                        max_iterations=options.get("med_iterations", 30), ridge=options.get("ridge", 1e-8))
    return CVSMEDMSBPipeline(med, msb).run(values, sample_rate_hz, alignment, [mesh_hz], grid)


def composite_to_dict(diagnosis: CompositeDiagnosis) -> dict:
    """只有HTTP/持久化边界调用；不使用asdict深拷贝大型NumPy表示。"""
    def convert(value):
        if is_dataclass(value):
            return {item.name: convert(getattr(value, item.name)) for item in fields(value)}
        if isinstance(value, np.ndarray):
            if np.iscomplexobj(value):
                return {"real": convert(value.real), "imag": convert(value.imag)}
            return convert(value.tolist())
        if isinstance(value, Mapping):
            return {str(key): convert(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [convert(item) for item in value]
        if isinstance(value, (float, np.floating)):
            return float(value) if np.isfinite(value) else None
        if isinstance(value, (np.integer, np.bool_)):
            return value.item()
        return value
    return {"method": diagnosis.analysis.method, "status": diagnosis.analysis.status,
            "analysis": convert(diagnosis.analysis), "evaluation": convert(diagnosis.evaluation),
            "research_only": True, "production_eligible": False,
            "evidence_family": diagnosis.analysis.evidence_family,
            "health_score": None, "fault_probabilities": {}, "fault_indicators": {},
            "validation": {"real_dataset_effectiveness": "not_validated",
                           "fault_thresholds": "not_calibrated", "independent_vote": False}}
