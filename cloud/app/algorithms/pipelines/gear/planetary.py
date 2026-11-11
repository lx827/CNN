"""固定齿圈行星排：机械模型→独立方法表示与指标→可直接重评的评估。"""
from dataclasses import dataclass, replace

import numpy as np
from scipy.signal import butter, hilbert, sosfiltfilt

from app.algorithms.core import FrequencyBand
from app.algorithms.gear.fixed_axis.cepstrum import CARParameters, compute_car, compute_real_cepstrum
from app.algorithms.gear.fixed_axis.metrics import compute_fm0, residual_envelope
from app.algorithms.gear.fixed_axis.tsa import compute_synchronous_average, compute_tsa_representation
from app.algorithms.gear.fixed_axis.types import MetricValue
from app.algorithms.gear.planetary.analysis import analyze_planetary_sidebands, modulation_peaks, normalized_moment
from app.algorithms.gear.planetary.evaluation import evaluate_planetary
from app.algorithms.gear.planetary.types import (
    PlanetaryAnalysis, PlanetaryBaseline, PlanetaryEvaluation, PlanetaryMethodAnalysis,
    PlanetaryMomentHistory, PlanetaryParameters,
)
from app.algorithms.mechanics.planetary import PlanetaryGearGeometry
from app.algorithms.order import AngleDomainSignal, OrderAnalysis, ScalarSpeed, compute_order_spectrum, resample_constant_speed
from app.algorithms.transforms.envelope import compute_bandpass_hilbert_envelope


@dataclass(frozen=True)
class PlanetaryGearDiagnosis:
    analysis: PlanetaryAnalysis
    evaluation: PlanetaryEvaluation


class PlanetaryGearPipeline:
    """只接受明确恒速；多帧摘要与快速变速谱不能给解调冒充连续恒速。

    所有计算最多 5 秒并串行执行。narrowband/fullband/highpass 与 TSA
    residual 是不同证据，未迁移的 VMD/SC/MSB/CVS 不在该评估闭环内。
    """

    def __init__(self, geometry: PlanetaryGearGeometry | None, parameters: PlanetaryParameters = PlanetaryParameters()) -> None:
        self.geometry = geometry
        self.parameters = parameters

    def _envelope_analysis(self, envelope: np.ndarray, frequency_hz: float, sample_rate: float, geometry: PlanetaryGearGeometry, method: str, usable_max: float, details: dict | None = None, angle: AngleDomainSignal | None = None) -> PlanetaryMethodAnalysis:
        if angle is None:
            angle, _ = resample_constant_speed(envelope, sample_rate, ScalarSpeed(frequency_hz, "explicit_constant_speed"), self.parameters.samples_per_revolution)
        else:
            angle = AngleDomainSignal(angle.angle_revolutions, envelope, angle.samples_per_revolution)
        maximum = min(usable_max, angle.samples_per_revolution / 2 - 1)
        spectrum = compute_order_spectrum(angle, maximum)
        metric = normalized_moment(envelope, 4, "envelope_kurtosis", f"{method}_centered_envelope")
        return PlanetaryMethodAnalysis(method, "computed", geometry.reference_axis, spectrum, modulation_peaks(spectrum, geometry.event_orders, usable_max), {"envelope_kurtosis": metric}, details=details or {})

    def analyze(self, signal: np.ndarray, sample_rate_hz: float, speed: ScalarSpeed | None = None, *, order_analysis: OrderAnalysis | None = None, include_tsa: bool = True, history: PlanetaryMomentHistory | None = None, input_unit: str = "input_signal", methods: tuple[str, ...] = ("narrowband", "fullband", "highpass", "tsa_residual")) -> PlanetaryAnalysis:
        """指标与谱均为纯计算结果；失败返回不可评估，不以零值表示健康。

        speed 的单位是 geometry.reference_axis 的 Hz。order_analysis 只用于
        工况门控，不拿缓存中位转速或缓存谱替代本记录的相位与样本。
        """
        geometry = self.geometry
        if geometry is None:
            return PlanetaryAnalysis("not_evaluable", None, None, reason="missing_complete_planetary_geometry")
        if order_analysis is not None:
            if order_analysis.status != "valid" or order_analysis.tracking_method != "single_frame" or not isinstance(order_analysis.speed, ScalarSpeed):
                return PlanetaryAnalysis("not_evaluable", geometry, None, reason="planetary_demodulation_requires_explicit_constant_speed")
            if speed is not None and speed != order_analysis.speed:
                return PlanetaryAnalysis("not_evaluable", geometry, None, reason="conflicting_reference_speed")
            speed = order_analysis.speed
        if not isinstance(speed, ScalarSpeed) or speed.status != "valid" or speed.frequency_hz is None:
            return PlanetaryAnalysis("not_evaluable", geometry, None, reason="missing_valid_reference_speed")
        if not set(methods) <= {"narrowband", "fullband", "highpass", "tsa_residual"}:
            raise ValueError("未迁移行星方法不属于该 Pipeline")
        values = np.asarray(signal, dtype=np.float64)
        if values.ndim != 1 or len(values) < 64 or not np.all(np.isfinite(values)):
            return PlanetaryAnalysis("not_evaluable", geometry, speed.frequency_hz, reason="invalid_or_short_signal")
        if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
            return PlanetaryAnalysis("not_evaluable", geometry, speed.frequency_hz, reason="invalid_sample_rate")
        values = values[:int(sample_rate_hz * self.parameters.max_duration_s)]
        if len(values) < 64:
            return PlanetaryAnalysis("not_evaluable", geometry, speed.frequency_hz, reason="invalid_or_short_signal")
        values = values - np.mean(values)
        reference_hz = float(speed.frequency_hz)
        available_order = sample_rate_hz / (2 * reference_hz)
        required = geometry.mesh_order + (self.parameters.n_sidebands + .4) * geometry.carrier_order
        if required >= available_order or required >= self.parameters.samples_per_revolution / 2:
            return PlanetaryAnalysis("not_evaluable", geometry, reference_hz, reason="mesh_sidebands_above_physical_nyquist")
        if not np.any(values):
            return PlanetaryAnalysis("not_evaluable", geometry, reference_hz, reason="zero_signal_energy")
        try:
            angle, _ = resample_constant_speed(values, sample_rate_hz, speed, self.parameters.samples_per_revolution)
        except ValueError as exc:
            return PlanetaryAnalysis("not_evaluable", geometry, reference_hz, reason=str(exc))
        resolution = angle.samples_per_revolution / len(angle.samples)
        spectrum = compute_order_spectrum(angle, required + resolution)
        sidebands = analyze_planetary_sidebands(spectrum, geometry.mesh_order, geometry.carrier_order, self.parameters.n_sidebands)
        # 完整表示键约束历史与阈值的可比性，不允许跨参考轴/速度/记录长度使用。
        key = (geometry.signature, reference_hz, sample_rate_hz, len(values), input_unit, self.parameters, include_tsa, tuple(methods))
        analyses = []
        max_envelope = min(available_order * .95, geometry.mesh_order, angle.samples_per_revolution / 2 - 1)
        for method in methods:
            if method == "tsa_residual":
                continue
            try:
                details = {"kurtosis_convention": "Pearson", "fault_localization": "candidate_event_order_not_tooth_damage_type"}
                if method == "narrowband":
                    # 最大事件候选两侧都留出局部背景；固定 ±4 sun阶会让
                    # 3.125阶太阳事件虽落在通带内却没有可观测背景窗。
                    half = max(4.0 * geometry.axis_order("sun"), 2.0 * max(geometry.event_orders.values()))
                    low, high = geometry.mesh_order - half, geometry.mesh_order + half
                    if low <= 0 or high >= available_order:
                        raise ValueError("narrowband_mesh_band_outside_physical_nyquist")
                    envelope = compute_bandpass_hilbert_envelope(values, sample_rate_hz, FrequencyBand(low * reference_hz, high * reference_hz))
                    # 仅承诺通带内调制，两侧完整边带均须保留；避开 Butterworth 过渡区。
                    usable = half * .8
                    details["bandpass_hz"] = (low * reference_hz, high * reference_hz)
                elif method == "highpass":
                    cutoff = 1.5 * geometry.mesh_order * reference_hz
                    if cutoff >= sample_rate_hz * .45:
                        raise ValueError("insufficient_highpass_carrier_band")
                    sos = butter(4, cutoff, btype="highpass", fs=sample_rate_hz, output="sos")
                    envelope = np.abs(hilbert(sosfiltfilt(sos, values)))
                    usable = max_envelope
                    details["highpass_cutoff_hz"] = cutoff
                    details["interpretation"] = "broadband_envelope_not_single_carrier_demodulation"
                else:
                    envelope = np.abs(hilbert(values))
                    usable = max_envelope
                    details["interpretation"] = "multicomponent_cross_terms_possible"
                # 双向滤波和 Hilbert 的边界不当成周期冲击；统一去掉两端 20 ms。
                trim = max(1, int(sample_rate_hz * .02))
                envelope = envelope[trim:-trim]
                if len(envelope) < 64:
                    raise ValueError("insufficient_signal_after_edge_trim")
                analyses.append(self._envelope_analysis(envelope, reference_hz, sample_rate_hz, geometry, method, usable, details))
            except ValueError as exc:
                analyses.append(PlanetaryMethodAnalysis(method, "not_evaluable", geometry.reference_axis, reason=str(exc)))

        metrics = {}
        synchronous = None
        tsa_axis = self.parameters.tsa_reference_axis
        if include_tsa:
            tsa_geometry = PlanetaryGearGeometry(geometry.sun_teeth, geometry.ring_teeth, geometry.planet_teeth, geometry.planet_count, tsa_axis)
            tsa_hz = reference_hz * geometry.axis_order(tsa_axis)
            try:
                tsa_angle, _ = resample_constant_speed(values, sample_rate_hz, ScalarSpeed(tsa_hz, "kinematic_reference_transform"), self.parameters.samples_per_revolution)
                synchronous = replace(compute_synchronous_average(tsa_angle, self.parameters.min_tsa_revolutions), synchronous_shaft=tsa_axis)
                residual = synchronous.nonsynchronous_signal
                if "tsa_residual" in methods:
                    if np.var(residual) <= np.var(synchronous.angle_domain.samples) * 1e-12:
                        analyses.append(PlanetaryMethodAnalysis("tsa_residual", "not_evaluable", tsa_axis, reason="no_observable_nonsynchronous_energy"))
                    else:
                        envelope = np.abs(hilbert(residual))
                        method = self._envelope_analysis(envelope, tsa_hz, self.parameters.samples_per_revolution, tsa_geometry, "tsa_residual", min(sample_rate_hz / (2 * tsa_hz) * .95, self.parameters.samples_per_revolution / 2 - 1), {"synchronization_axis": tsa_axis, "revolutions": synchronous.revolutions, "angular_sample_rate_points_per_revolution": self.parameters.samples_per_revolution, "residual_semantics": "original_angle_signal_minus_tiled_synchronous_average", "synchronous_events": "retained_in_TSA_and_suppressed_in_nonsynchronous_residual"}, angle=synchronous.angle_domain)
                        analyses.append(replace(method, metrics={**method.metrics, "residual_kurtosis": normalized_moment(residual, 4, "residual_kurtosis", f"{tsa_axis}_nonsynchronous_residual")}))
                # 只有啮合与同步轴整比时，经典整数啮合梳构造才有明确语义。
                if not float(tsa_geometry.mesh_order).is_integer():
                    raise ValueError("noninteger_mesh_order_for_selected_tsa_axis")
                maximum = tsa_geometry.mesh_order * self.parameters.mesh_harmonics + self.parameters.regular_sidebands
                if maximum >= sample_rate_hz / (2 * tsa_hz):
                    raise ValueError("tsa_mesh_harmonics_above_physical_nyquist")
                representation = compute_tsa_representation(synchronous, tsa_geometry.mesh_order, self.parameters.mesh_harmonics, self.parameters.regular_sidebands, maximum + 1)
                metrics["fm0"] = compute_fm0(representation)
                for name, degree in (("fm4", 4), ("m6a", 6), ("m8a", 8)):
                    if np.var(representation.differential_signal) <= np.var(synchronous.tsa_signal) * 1e-12:
                        metrics[name] = MetricValue.unavailable(name.upper(), "no_observable_differential_energy")
                    else:
                        metrics[name] = normalized_moment(representation.differential_signal, degree, name.upper(), f"{tsa_axis}_TSA_regular_minus_mesh")
                env_residual = residual_envelope(representation)
                for name, array, variances in (("na4", representation.residual_signal, history.residual_variances if history else ()), ("nb4", env_residual, history.envelope_variances if history else ())):
                    if history is None or not variances:
                        metrics[name] = MetricValue.unavailable(name.upper(), "missing_comparable_planetary_variance_history")
                    elif history.representation_key != key:
                        metrics[name] = MetricValue.unavailable(name.upper(), "incompatible_planetary_variance_history")
                    else:
                        centered = array - np.mean(array)
                        denominator = float(np.mean(variances))
                        metrics[name] = MetricValue(name.upper(), "evaluated", float(np.mean((centered / np.sqrt(denominator)) ** 4)), details={"history_source": history.source, "history_count": len(variances), "tsa_reference_axis": tsa_axis})
            except ValueError as exc:
                for name in ("fm0", "fm4", "m6a", "m8a", "na4", "nb4"):
                    metrics.setdefault(name, MetricValue.unavailable(name.upper(), str(exc)))
                if "tsa_residual" in methods and not any(a.method == "tsa_residual" for a in analyses):
                    analyses.append(PlanetaryMethodAnalysis("tsa_residual", "not_evaluable", tsa_axis, reason=str(exc)))
        else:
            for name in ("fm0", "fm4", "m6a", "m8a", "na4", "nb4"):
                metrics[name] = MetricValue.unavailable(name.upper(), "tsa_not_requested")
        try:
            # 通用倒谱计算只一份；CAR 在这里明确观察 carrier 周期族且不定位故障。
            carrier_hz = reference_hz * geometry.carrier_order
            metrics["car"] = compute_car(compute_real_cepstrum(values, sample_rate_hz), carrier_hz, CARParameters(tolerance_s=min(.002, .1 / carrier_hz)))
        except ValueError as exc:
            metrics["car"] = MetricValue.unavailable("CAR", str(exc))
        return PlanetaryAnalysis("computed", geometry, reference_hz, spectrum, sidebands, tuple(analyses), metrics, synchronous, tsa_axis if include_tsa else None, representation_key=key)

    def evaluate(self, analysis: PlanetaryAnalysis, baseline: PlanetaryBaseline | None = None) -> PlanetaryEvaluation:
        return evaluate_planetary(analysis, baseline)

    def run(self, signal: np.ndarray, sample_rate_hz: float, speed: ScalarSpeed | None = None, *, baseline: PlanetaryBaseline | None = None, **analysis_options) -> PlanetaryGearDiagnosis:
        analysis = self.analyze(signal, sample_rate_hz, speed, **analysis_options)
        return PlanetaryGearDiagnosis(analysis, self.evaluate(analysis, baseline))
