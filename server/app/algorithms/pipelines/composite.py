"""明确研究限定的组合 Pipeline；不输出生产故障阈值或独立投票。

AM/FM、MSB、CVS→MED→MSB、VMD→ICA 和 MSWPEE 各自保留真实阶段链。
共享信号/分解/包络的结果属于同一 evidence_family，不能按方法数量重复投票。
"""

from dataclasses import dataclass, field

import numpy as np

from app.algorithms.composite.amfm import demodulate_amfm, analyze_modulation_peak
from app.algorithms.composite.cvs import (
    CVSAlignment,
    reconstruct_continuous_planet_signal,
)
from app.algorithms.composite.ica import FastICAParameters, compute_fast_ica
from app.algorithms.composite.msb import (
    MSBParameters,
    compute_modulation_bispectrum,
    analyze_msb_slice,
)
from app.algorithms.bearing.deconvolution import (
    MEDParameters,
    minimum_entropy_deconvolution,
)
from app.algorithms.decomposition.vmd import VMDParameters, decompose_vmd
from app.algorithms.mechanics import FixedAxisGearGeometry
from app.algorithms.mechanics.planetary import PlanetaryGearGeometry
from app.algorithms.order import ScalarSpeed
from app.algorithms.pipelines.decomposition import (
    select_ranked_components,
    WaveletPacketEnergyPipeline,
)


@dataclass(frozen=True)
class CompositeStage:
    name: str
    status: str
    reason: str | None = None


@dataclass(frozen=True)
class CompositeAnalysis:
    method: str
    status: str
    stages: tuple[CompositeStage, ...]
    data: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    reason: str | None = None
    research_only: bool = True
    production_eligible: bool = False
    evidence_family: str = "shared_signal_decomposition_demodulation"


@dataclass(frozen=True)
class CompositeEvaluation:
    status: str
    reason: str
    indicators: dict
    diagnosis_conclusion: str = "unknown"
    production_eligible: bool = False


@dataclass(frozen=True)
class CompositeDiagnosis:
    analysis: CompositeAnalysis
    evaluation: CompositeEvaluation


class ResearchCompositePipeline:
    def evaluate(self, analysis: CompositeAnalysis) -> CompositeEvaluation:
        """只重评已有原始指标。当前无设备基线/效果标定，阈值与结论保持未知。"""
        return CompositeEvaluation(
            "not_evaluable",
            analysis.reason or "research_combination_has_no_validated_fault_thresholds",
            {
                key: {
                    "value": value,
                    "warning": None,
                    "critical": None,
                    "status": "raw_only",
                }
                for key, value in analysis.metrics.items()
            },
        )

    def run(self, *args, **kwargs):
        analysis = self.analyze(*args, **kwargs)
        return CompositeDiagnosis(analysis, self.evaluate(analysis))


def _failed(method, stages, reason, data=None):
    return CompositeAnalysis(
        method, "indeterminate", tuple(stages), data or {}, reason=reason
    )


def _bounded_vmd(parameters):
    if (
        parameters.modes > 5
        or parameters.max_samples is None
        or parameters.max_samples > 51200
    ):
        raise ValueError(
            "research VMD requires modes<=5 and explicit window<=51200 samples"
        )
    if parameters.max_iterations > 500:
        raise ValueError("research VMD iteration limit must not exceed 500")


def _targets(geometry, speed):
    if not isinstance(speed, ScalarSpeed):
        raise ValueError(
            "AM/FM requires explicit constant ScalarSpeed, not trajectory median"
        )
    if isinstance(geometry, PlanetaryGearGeometry):
        return geometry.mesh_order * speed.frequency_hz, {
            key: order * speed.frequency_hz
            for key, order in geometry.event_orders.items()
        }
    if isinstance(geometry, FixedAxisGearGeometry):
        targets = {"input_rotation": speed.frequency_hz}
        if geometry.output_teeth is not None:
            targets["output_rotation"] = (
                speed.frequency_hz * geometry.input_teeth / geometry.output_teeth
            )
        return geometry.mesh_frequency_hz(speed.frequency_hz), targets
    raise ValueError("AM/FM requires validated fixed-axis or planetary geometry")


class VMDAMFMPipeline(ResearchCompositePipeline):
    def __init__(
        self, parameters=VMDParameters(modes=3), *, mode_tolerance_fraction=0.25
    ):
        _bounded_vmd(parameters)
        if (
            not np.isfinite(mode_tolerance_fraction)
            or not 0 < mode_tolerance_fraction < 1
        ):
            raise ValueError("mode tolerance must be within (0,1)")
        self.parameters, self.mode_tolerance_fraction = (
            parameters,
            mode_tolerance_fraction,
        )

    def analyze(self, signal, sample_rate_hz, geometry, speed, *, decomposition=None):
        method = (
            "vmd_amfm_planetary"
            if isinstance(geometry, PlanetaryGearGeometry)
            else "vmd_amfm_fixed_axis"
        )
        carrier_hz, targets = _targets(geometry, speed)
        if carrier_hz >= sample_rate_hz / 2:
            return _failed(method, (), "mesh_carrier_above_Nyquist")
        result = (
            decomposition
            if decomposition is not None
            else decompose_vmd(signal, sample_rate_hz, self.parameters)
        )
        stages = [CompositeStage("VMD", result.status, result.reason)]
        data = {
            "decomposition": result,
            "vmd_parameters": self.parameters,
            "mesh_frequency_hz": carrier_hz,
            "reference_frequency_hz": speed.frequency_hz,
            "modulation_targets_hz": targets,
        }
        if result.status != "valid" or not len(result.modes):
            return _failed(method, stages, result.reason or "VMD_unavailable", data)
        if not np.isclose(result.sample_rate_hz, sample_rate_hz):
            raise ValueError("VMD sample rate does not match AM/FM input")
        selected = int(np.argmin(np.abs(result.center_frequencies_hz - carrier_hz)))
        data["selected_mode"] = selected
        if (
            abs(result.center_frequencies_hz[selected] - carrier_hz)
            > carrier_hz * self.mode_tolerance_fraction
        ):
            return _failed(method, stages, "no_VMD_mode_near_mesh_carrier", data)
        stages.append(CompositeStage("mesh_mode_selection", "computed"))
        try:
            representation = demodulate_amfm(result.modes[selected], sample_rate_hz)
        except ValueError as exc:
            return _failed(
                method,
                stages + [CompositeStage("AM_FM", "indeterminate", str(exc))],
                str(exc),
                data,
            )
        data["demodulation"] = representation
        data["amplitude_peaks"] = {
            key: analyze_modulation_peak(
                representation.amplitude_spectrum,
                target,
                reference_hz=speed.frequency_hz,
            )
            for key, target in targets.items()
        }
        data["frequency_peaks"] = {
            key: analyze_modulation_peak(
                representation.frequency_spectrum,
                target,
                reference_hz=speed.frequency_hz,
            )
            for key, target in targets.items()
        }
        stages.append(CompositeStage("AM_FM", "computed"))
        status = "computed" if result.converged else "approximate"
        metrics = {
            f"{kind}_{key}_amplitude": peak.amplitude
            for kind, peaks in (
                ("AM", data["amplitude_peaks"]),
                ("FM", data["frequency_peaks"]),
            )
            for key, peak in peaks.items()
        }
        return CompositeAnalysis(
            method,
            status,
            tuple(stages),
            data,
            metrics,
            None if result.converged else "VMD_not_converged",
        )


class ModulationBispectrumPipeline(ResearchCompositePipeline):
    def __init__(self, parameters=MSBParameters()):
        self.parameters = parameters

    def analyze(
        self, signal, sample_rate_hz, carrier_frequencies_hz, modulation_frequencies_hz
    ):
        try:
            representation = compute_modulation_bispectrum(
                signal,
                sample_rate_hz,
                carrier_frequencies_hz,
                modulation_frequencies_hz,
                self.parameters,
            )
        except ValueError as exc:
            return _failed(
                "modulation_bispectrum",
                (CompositeStage("MSB", "indeterminate", str(exc)),),
                str(exc),
            )
        if not np.any(representation.valid):
            return _failed(
                "modulation_bispectrum",
                (CompositeStage("MSB", "indeterminate"),),
                "no_observable_MSB_frequency_pairs",
                {"representation": representation},
            )
        analysis = analyze_msb_slice(representation)
        usable = representation.coherence[np.isfinite(representation.coherence)]
        metrics = {
            "maximum_phase_coherence": float(np.max(usable)) if len(usable) else None,
            "fourth_order_background": analysis["background"],
        }
        return CompositeAnalysis(
            "modulation_bispectrum",
            "computed",
            (CompositeStage("MSB", "computed"),),
            {
                "representation": representation,
                "slice": analysis,
                "parameters": self.parameters,
            },
            metrics,
        )


class CVSMEDMSBPipeline(ResearchCompositePipeline):
    def __init__(
        self,
        med_parameters=MEDParameters(filter_length=30),
        msb_parameters=MSBParameters(),
    ):
        self.med_parameters, self.msb_parameters = med_parameters, msb_parameters

    def analyze(
        self,
        signal,
        sample_rate_hz,
        alignment: CVSAlignment | None,
        carrier_frequencies_hz,
        modulation_frequencies_hz,
    ):
        cvs = reconstruct_continuous_planet_signal(signal, sample_rate_hz, alignment)
        stages = [CompositeStage("CVS", cvs.status, cvs.reason)]
        data = {
            "cvs": cvs,
            "med_parameters": self.med_parameters,
            "msb_parameters": self.msb_parameters,
        }
        if cvs.signal is None:
            return _failed("cvs_med_msb", stages, cvs.reason, data)
        try:
            med = minimum_entropy_deconvolution(cvs.signal, self.med_parameters)
        except (ValueError, np.linalg.LinAlgError) as exc:
            return _failed(
                "cvs_med_msb",
                stages + [CompositeStage("MED", "indeterminate", str(exc))],
                str(exc),
                data,
            )
        data["med"] = med
        stages.append(
            CompositeStage("MED", "computed" if med.converged else "approximate")
        )
        # 此处严格消费MED输出及CVS重组后的采样率，不旁路原始signal。
        msb = ModulationBispectrumPipeline(self.msb_parameters).analyze(
            med.signal,
            cvs.sample_rate_hz,
            carrier_frequencies_hz,
            modulation_frequencies_hz,
        )
        data["msb"] = msb
        stages.extend(msb.stages)
        if msb.status == "indeterminate":
            return _failed("cvs_med_msb", stages, msb.reason, data)
        return CompositeAnalysis(
            "cvs_med_msb",
            "computed" if med.converged else "approximate",
            tuple(stages),
            data,
            msb.metrics,
            None if med.converged else "MED_not_converged",
        )


class VMDICAPipeline(ResearchCompositePipeline):
    def __init__(
        self,
        vmd_parameters=VMDParameters(modes=3),
        ica_parameters=FastICAParameters(),
        top_n=1,
    ):
        _bounded_vmd(vmd_parameters)
        self.vmd_parameters, self.ica_parameters, self.top_n = (
            vmd_parameters,
            ica_parameters,
            top_n,
        )

    def analyze(self, signal, sample_rate_hz, *, decomposition=None):
        result = (
            decomposition
            if decomposition is not None
            else decompose_vmd(signal, sample_rate_hz, self.vmd_parameters)
        )
        stages = [CompositeStage("VMD", result.status, result.reason)]
        data = {
            "decomposition": result,
            "vmd_parameters": self.vmd_parameters,
            "ica_parameters": self.ica_parameters,
            "observability": "single_sensor_virtual_channels_are_not_independent_measurements",
        }
        if result.status != "valid" or not result.converged:
            return _failed(
                "vmd_ica", stages, result.reason or "VMD_not_converged", data
            )
        if not np.isclose(result.sample_rate_hz, sample_rate_hz):
            raise ValueError("VMD sample rate does not match ICA input")
        ica = compute_fast_ica(result.modes.T, self.ica_parameters)
        data["ica"] = ica
        stages.append(CompositeStage("FastICA", ica.status, ica.reason))
        if ica.status != "computed" or ica.components is None:
            return _failed("vmd_ica", stages, ica.reason, data)
        # 每个独立分量逆映射到VMD观测通道后求和，保持输入物理单位。
        contributions = ica.components.T * np.sum(ica.mixing, axis=0)[:, None]
        reference = np.asarray(signal, dtype=float)[
            result.valid_interval.start_index : result.valid_interval.stop_index
        ]
        selection = select_ranked_components(
            contributions, reference, sample_rate_hz, top_n=self.top_n
        )
        data["source_contributions"], data["selection"] = contributions, selection
        stages.append(
            CompositeStage("component_selection", selection.status, selection.reason)
        )
        if selection.representation is None:
            return _failed("vmd_ica", stages, selection.reason, data)
        return CompositeAnalysis(
            "vmd_ica",
            "computed",
            tuple(stages),
            data,
            {"selected_components": selection.selected_indices},
        )


def coarse_grain(signal, scale):
    """非重叠block均值，尾部不足scale的样本明确丢弃；不是抗混叠抽取器。"""
    values = np.asarray(signal, dtype=float)
    if values.ndim != 1 or not len(values) or not np.all(np.isfinite(values)):
        raise ValueError("coarse graining requires a finite nonempty vector")
    if isinstance(scale, bool) or not isinstance(scale, int) or scale < 1:
        raise ValueError("coarse scale must be a positive integer")
    count = len(values) // scale
    if count < 2:
        raise ValueError("insufficient_samples_after_coarse_graining")
    return np.mean(values[: count * scale].reshape(count, scale), axis=1)


class MSWPEEPipeline(ResearchCompositePipeline):
    def __init__(self, wavelet="db8", level=3, max_scale=5):
        if (
            isinstance(max_scale, bool)
            or not isinstance(max_scale, int)
            or not 1 <= max_scale <= 64
        ):
            raise ValueError("MSWPEE max_scale must be an integer in [1,64]")
        self.wavelet, self.level, self.max_scale = wavelet, level, max_scale

    def analyze(self, signal, sample_rate_hz):
        if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
            raise ValueError("MSWPEE requires a positive sample rate")
        scales = []
        stages = []
        for scale in range(1, self.max_scale + 1):
            try:
                coarse = coarse_grain(signal, scale)
                result = WaveletPacketEnergyPipeline(self.wavelet, self.level).analyze(
                    coarse, sample_rate_hz / scale
                )
                normalized, entropy = result.normalized_entropy, result.entropy_bits
                reason = (
                    None if normalized is not None else "zero_wavelet_packet_energy"
                )
                detail = {
                    "scale": scale,
                    "sample_rate_hz": sample_rate_hz / scale,
                    "retained_input_samples": len(coarse) * scale,
                    "coarse_samples": len(coarse),
                    "entropy_bits": entropy,
                    "normalized_entropy": normalized,
                    "energy_ratios": result.energy_ratios,
                    "node_frequency_bands_hz": tuple(
                        node.frequency_band_hz for node in result.decomposition.nodes
                    ),
                }
            except ValueError as exc:
                normalized, reason = None, str(exc)
                detail = {
                    "scale": scale,
                    "sample_rate_hz": sample_rate_hz / scale,
                    "reason": reason,
                    "entropy_bits": None,
                    "normalized_entropy": None,
                }
            stages.append(
                CompositeStage(
                    f"coarse_grain_{scale}_WP_energy_entropy",
                    "computed" if normalized is not None else "indeterminate",
                    reason,
                )
            )
            scales.append(detail)
        valid = all(item["normalized_entropy"] is not None for item in scales)
        vector = np.asarray(
            [
                item["normalized_entropy"]
                if item["normalized_entropy"] is not None
                else np.nan
                for item in scales
            ]
        )
        return CompositeAnalysis(
            "mswpee",
            "computed" if valid else "indeterminate",
            tuple(stages),
            {
                "scales": tuple(scales),
                "normalized_entropy_vector": vector,
                "coarse_graining_is_box_average_not_anti_alias_resampling": True,
            },
            {"mean_normalized_entropy": float(np.mean(vector)) if valid else None},
            None if valid else "some_multiscale_entropies_are_not_evaluable",
        )
