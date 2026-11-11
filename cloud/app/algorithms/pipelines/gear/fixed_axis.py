"""定轴齿轮“表示→原始指标→独立评估”的诊断 Pipeline。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.algorithms.gear.fixed_axis.cepstrum import (
    CARParameters,
    compute_car,
    compute_real_cepstrum,
)
from app.algorithms.gear.fixed_axis.evaluation import (
    FixedAxisEvaluation,
    evaluate_fixed_axis,
)
from app.algorithms.gear.fixed_axis.metrics import (
    analyze_fixed_axis_sidebands,
    analyze_order_statistics,
    compute_fm0,
    compute_na4,
    compute_nb4,
    standardized_moment,
)
from app.algorithms.gear.fixed_axis.tsa import (
    compute_synchronous_average,
    compute_tsa_representation,
)
from app.algorithms.gear.fixed_axis.types import (
    FixedAxisAnalysis,
    MetricValue,
    SidebandAnalysis,
    TSAParameters,
    TrendHistory,
)
from app.algorithms.mechanics import FixedAxisGearGeometry
from app.algorithms.order import (
    ConstantSpeedOrderPipeline,
    LocalSpeedEstimates,
    OrderAnalysis,
    OrderParameters,
    ScalarSpeed,
    SpeedTrajectory,
    compute_order_spectrum,
)


@dataclass(frozen=True)
class FixedAxisGearDiagnosis:
    analysis: FixedAxisAnalysis
    evaluation: FixedAxisEvaluation


class FixedAxisGearPipeline:
    """按各指标前提独立计算，不强迫所有方法经过同一条 TSA 流程。"""

    def __init__(
        self,
        geometry: FixedAxisGearGeometry | None = None,
        tsa_parameters: TSAParameters = TSAParameters(),
        car_parameters: CARParameters = CARParameters(),
        n_sidebands: int = 6,
    ) -> None:
        self.geometry = geometry
        self.tsa_parameters = tsa_parameters
        self.car_parameters = car_parameters
        self.n_sidebands = n_sidebands

    def required_max_order(self, include_tsa: bool) -> float:
        """只覆盖本次实际请求的指标；standard 不承担 TSA 谐波前提。"""
        mesh_order = self.geometry.mesh_order if self.geometry else None
        sideband_maximum = (
            mesh_order + self.n_sidebands + 0.25
            if mesh_order is not None
            else self.tsa_parameters.max_order
        )
        if not include_tsa or mesh_order is None:
            return sideband_maximum
        return max(
            sideband_maximum,
            self.tsa_parameters.max_order,
            mesh_order * self.tsa_parameters.mesh_harmonics
            + self.tsa_parameters.regular_sideband_order,
        )

    @staticmethod
    def _speed_summary(order: OrderAnalysis) -> tuple[float | None, float]:
        if isinstance(order.speed, ScalarSpeed):
            return order.speed.frequency_hz, 0.0
        if isinstance(order.speed, LocalSpeedEstimates):
            return order.speed.median_hz, order.speed.std_hz
        if isinstance(order.speed, SpeedTrajectory):
            return float(np.median(order.speed.frequency_hz)), float(
                np.std(order.speed.frequency_hz)
            )
        return None, 0.0

    def analyze(
        self,
        signal: np.ndarray,
        sample_rate_hz: float,
        speed: ScalarSpeed | None = None,
        order_analysis: OrderAnalysis | None = None,
        include_tsa: bool = False,
        history: TrendHistory | None = None,
    ) -> FixedAxisAnalysis:
        """计算原始指标。

        SER 可消费恒速、多帧或连续相位补偿阶次谱；CAR/TSA 只接受准确
        标量恒速和真实角域表示。多帧中位转频、快速变速轨迹均不会触发
        TSA。NA4/NB4 仅由显式 TrendHistory 启用。
        """
        if order_analysis is None:
            if speed is None:
                raise ValueError("定轴分析需要有效阶次分析或标量转频")
            order_analysis = ConstantSpeedOrderPipeline(
                OrderParameters(
                    samples_per_revolution=self.tsa_parameters.samples_per_revolution,
                    max_order=self.required_max_order(include_tsa),
                )
            ).run(signal, sample_rate_hz, speed)
        if order_analysis.status != "valid" or order_analysis.spectrum is None:
            raise ValueError(order_analysis.reason or "定轴阶次分析不可判定")

        spectrum = order_analysis.spectrum
        if (
            spectrum.order_bins[-1] + spectrum.order_resolution * 1e-9
            < self.required_max_order(include_tsa)
            and order_analysis.angle_domain is not None
        ):
            # 非整数转数时目标阶次通常落在相邻 FFT bin 之间；多保留一个真实
            # 谱点以覆盖请求窗口，而不是放宽 SER 的覆盖判定或虚构谱值。
            spectrum = compute_order_spectrum(
                order_analysis.angle_domain,
                self.required_max_order(include_tsa) + spectrum.order_resolution,
            )

        mesh_order = self.geometry.mesh_order if self.geometry else None
        if mesh_order is None:
            sideband = SidebandAnalysis(
                status="not_evaluable",
                mesh_amplitude=None,
                ser=MetricValue.unavailable("SER", "missing_fixed_axis_geometry"),
            )
        else:
            sideband = analyze_fixed_axis_sidebands(
                spectrum,
                mesh_order=mesh_order,
                n_sidebands=self.n_sidebands,
            )

        tsa = None
        tsa_status = "not_requested" if not include_tsa else "not_evaluable"
        tsa_reason = None if include_tsa else "standard_method_does_not_request_tsa"
        fm0 = MetricValue.unavailable("FM0", "tsa_not_requested")
        fm4 = MetricValue.unavailable("FM4", "tsa_not_requested")
        m6a = MetricValue.unavailable("M6A", "tsa_not_requested")
        m8a = MetricValue.unavailable("M8A", "tsa_not_requested")
        na4 = MetricValue.unavailable("NA4", "tsa_not_requested")
        nb4 = MetricValue.unavailable("NB4", "tsa_not_requested")
        if include_tsa:
            if mesh_order is None:
                tsa_reason = "missing_fixed_axis_geometry"
            elif order_analysis.angle_domain is None or not isinstance(
                order_analysis.speed, ScalarSpeed
            ):
                tsa_reason = (
                    "tsa_requires_accurate_constant_speed_with_continuous_phase"
                )
            if tsa_reason is not None:
                fm0 = MetricValue.unavailable("FM0", tsa_reason)
                fm4 = MetricValue.unavailable("FM4", tsa_reason)
                m6a = MetricValue.unavailable("M6A", tsa_reason)
                m8a = MetricValue.unavailable("M8A", tsa_reason)
                na4 = MetricValue.unavailable("NA4", tsa_reason)
                nb4 = MetricValue.unavailable("NB4", tsa_reason)
            else:
                try:
                    synchronous = compute_synchronous_average(
                        order_analysis.angle_domain,
                        self.tsa_parameters.min_revolutions,
                    )
                    tsa = compute_tsa_representation(
                        synchronous,
                        mesh_order=mesh_order,
                        mesh_harmonics=self.tsa_parameters.mesh_harmonics,
                        regular_sideband_order=self.tsa_parameters.regular_sideband_order,
                        max_order=self.required_max_order(include_tsa=True),
                    )
                    tsa_status = "evaluated"
                    fm0 = compute_fm0(tsa)
                    fm4 = standardized_moment(tsa.differential_signal, 4, "FM4")
                    m6a = standardized_moment(tsa.differential_signal, 6, "M6A")
                    m8a = standardized_moment(tsa.differential_signal, 8, "M8A")
                    na4 = compute_na4(tsa, history)
                    nb4 = compute_nb4(tsa, history)
                except ValueError as exc:
                    tsa_reason = str(exc)
                    fm0 = MetricValue.unavailable("FM0", tsa_reason)
                    fm4 = MetricValue.unavailable("FM4", tsa_reason)
                    m6a = MetricValue.unavailable("M6A", tsa_reason)
                    m8a = MetricValue.unavailable("M8A", tsa_reason)
                    na4 = MetricValue.unavailable("NA4", tsa_reason)
                    nb4 = MetricValue.unavailable("NB4", tsa_reason)

        cepstrum = None
        if (
            isinstance(order_analysis.speed, ScalarSpeed)
            and order_analysis.tracking_method == "single_frame"
        ):
            try:
                cepstrum = compute_real_cepstrum(signal, sample_rate_hz)
                car = compute_car(
                    cepstrum, order_analysis.speed.frequency_hz, self.car_parameters
                )
            except ValueError as exc:
                car = MetricValue.unavailable("CAR", str(exc))
        else:
            car = MetricValue.unavailable("CAR", "car_requires_accurate_constant_speed")

        rot_frequency, rot_std = self._speed_summary(order_analysis)
        return FixedAxisAnalysis(
            order=order_analysis,
            spectrum=spectrum,
            mesh_order=mesh_order,
            tsa=tsa,
            cepstrum=cepstrum,
            order_statistics=analyze_order_statistics(spectrum),
            fm0=fm0,
            fm4=fm4,
            m6a=m6a,
            m8a=m8a,
            na4=na4,
            nb4=nb4,
            car=car,
            sideband_analysis=sideband,
            tsa_status=tsa_status,
            tsa_reason=tsa_reason,
            rot_frequency_hz=rot_frequency,
            rot_frequency_std_hz=rot_std,
        )

    def evaluate(self, analysis: FixedAxisAnalysis) -> FixedAxisEvaluation:
        """直接重评已有原始指标，不重新计算 FFT/TSA。"""
        return evaluate_fixed_axis(analysis)

    def run(
        self,
        signal: np.ndarray,
        sample_rate_hz: float,
        speed: ScalarSpeed | None = None,
        order_analysis: OrderAnalysis | None = None,
        include_tsa: bool = False,
        history: TrendHistory | None = None,
    ) -> FixedAxisGearDiagnosis:
        analysis = self.analyze(
            signal,
            sample_rate_hz,
            speed=speed,
            order_analysis=order_analysis,
            include_tsa=include_tsa,
            history=history,
        )
        return FixedAxisGearDiagnosis(
            analysis=analysis, evaluation=self.evaluate(analysis)
        )
