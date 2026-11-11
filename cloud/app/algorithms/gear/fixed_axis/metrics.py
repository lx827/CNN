"""定轴齿轮原始指标；本模块不包含告警阈值。"""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, hilbert, sosfiltfilt

from app.algorithms.order import OrderSpectrum

from .types import (
    MetricValue,
    SidebandAnalysis,
    SidebandObservation,
    TrendHistory,
    TSARepresentation,
)


def standardized_moment(signal: np.ndarray, order: int, name: str) -> MetricValue:
    """计算 E[(x-μ)^p]/Var(x)^(p/2)，p=4/6/8 分别对应 FM4/M6A/M8A。"""
    values = np.asarray(signal, dtype=np.float64)
    if values.ndim != 1 or len(values) < max(8, order) or not np.all(np.isfinite(values)):
        return MetricValue.unavailable(name, "invalid_or_short_signal")
    centered = values - np.mean(values)
    variance = float(np.mean(centered**2))
    if variance <= np.finfo(np.float64).tiny:
        return MetricValue.unavailable(name, "zero_variance")
    value = float(np.mean(centered**order) / variance ** (order / 2.0))
    return MetricValue(
        name=name,
        status="evaluated",
        value=value,
        details={
            "formula": f"mean(centered**{order})/variance**{order / 2.0}",
            "sample_count": len(values),
            "variance": variance,
            "signal_representation": "differential",
        },
    )


def compute_fm0(tsa: TSARepresentation) -> MetricValue:
    """FM0=TSA 峰峰值/各请求啮合谐波最大单边幅值之和。

    分子和分母严格来自同一个 TSARepresentation；任一谐波未覆盖时整体
    不可评估，不允许用原信号谱或部分谐波补算。
    """
    amplitudes = []
    for order in tsa.mesh_orders:
        if order + 0.5 > tsa.spectrum.order_bins[-1] + tsa.spectrum.order_resolution * 1e-9:
            return MetricValue.unavailable("FM0", "mesh_harmonic_above_order_coverage", mesh_order=order)
        mask = np.abs(tsa.spectrum.order_bins - order) <= 0.5
        if not np.any(mask):
            return MetricValue.unavailable("FM0", "mesh_harmonic_not_resolvable", mesh_order=order)
        amplitudes.append(float(np.max(tsa.spectrum.amplitude[mask])))
    denominator = float(sum(amplitudes))
    if denominator <= np.finfo(np.float64).tiny:
        return MetricValue.unavailable("FM0", "zero_mesh_harmonic_amplitude")
    peak_to_peak = float(np.ptp(tsa.synchronous.tsa_signal))
    return MetricValue(
        name="FM0",
        status="evaluated",
        value=peak_to_peak / denominator,
        details={
            "peak_to_peak": peak_to_peak,
            "harmonic_amplitudes": amplitudes,
            "harmonic_amplitude_sum": denominator,
            "spectrum_scaling": tsa.spectrum.scaling,
            "amplitude_unit": tsa.spectrum.amplitude_unit,
            "representation": "same_tsa_for_numerator_and_denominator",
        },
    )


def _peak_in_window(spectrum: OrderSpectrum, center: float, half_width: float) -> float:
    mask = np.abs(spectrum.order_bins - center) <= half_width
    if not np.any(mask):
        raise ValueError("阶次窗内没有谱点")
    return float(np.max(spectrum.amplitude[mask]))


def analyze_fixed_axis_sidebands(
    spectrum: OrderSpectrum,
    mesh_order: float,
    n_sidebands: int = 6,
    sideband_half_width_order: float = 0.25,
    mesh_half_width_order: float = 0.25,
) -> SidebandAnalysis:
    """计算定轴 SER 幅值和比；边带间隔固定为输入轴 1×。

    每个分子窗口取最大单边幅值后求和，分母为啮合窗最大单边幅值。
    窗口不得相互重叠，全部请求啮合/边带必须处于谱覆盖内；否则 SER
    为 not_evaluable，不做截断求和，也不与行星 carrier 间隔混用。
    """
    unavailable = SidebandAnalysis(
        status="not_evaluable",
        mesh_amplitude=None,
        ser=MetricValue.unavailable("SER", "invalid_sideband_parameters"),
    )
    if spectrum.scaling != "single_sided_amplitude":
        unavailable.ser.details["reason_detail"] = "需要一致的单边峰值幅值谱"
        return unavailable
    if (
        not np.isfinite(mesh_order)
        or mesh_order < 2
        or isinstance(n_sidebands, bool)
        or n_sidebands < 1
        or not 0 < sideband_half_width_order < 0.5
        or not 0 < mesh_half_width_order < 0.5
        or mesh_half_width_order + sideband_half_width_order >= 1.0
    ):
        return unavailable
    maximum_order = mesh_order + n_sidebands + sideband_half_width_order
    minimum_order = mesh_order - n_sidebands - sideband_half_width_order
    if minimum_order < 0 or maximum_order > spectrum.order_bins[-1] + spectrum.order_resolution * 1e-9:
        return SidebandAnalysis(
            status="not_evaluable",
            mesh_amplitude=None,
            ser=MetricValue.unavailable(
                "SER",
                "requested_mesh_or_sidebands_above_order_coverage",
                minimum_required_order=minimum_order,
                maximum_required_order=maximum_order,
                spectrum_maximum_order=float(spectrum.order_bins[-1]),
            ),
            amplitude_unit=spectrum.amplitude_unit,
        )
    try:
        mesh_amplitude = _peak_in_window(spectrum, mesh_order, mesh_half_width_order)
    except ValueError:
        return SidebandAnalysis(
            status="not_evaluable",
            mesh_amplitude=None,
            ser=MetricValue.unavailable("SER", "mesh_window_not_resolvable"),
            amplitude_unit=spectrum.amplitude_unit,
        )
    if mesh_amplitude <= np.finfo(np.float64).tiny:
        return SidebandAnalysis(
            status="not_evaluable",
            mesh_amplitude=mesh_amplitude,
            ser=MetricValue.unavailable("SER", "zero_mesh_amplitude"),
            amplitude_unit=spectrum.amplitude_unit,
        )

    observations = []
    numerator = 0.0
    occupied_bins: set[int] = set()
    for sideband_order in range(1, n_sidebands + 1):
        lower_order = mesh_order - sideband_order
        upper_order = mesh_order + sideband_order
        windows = (
            (lower_order, sideband_half_width_order),
            (upper_order, sideband_half_width_order),
        )
        for center, half_width in windows:
            indices = set(np.flatnonzero(np.abs(spectrum.order_bins - center) <= half_width).tolist())
            if not indices or occupied_bins & indices:
                return SidebandAnalysis(
                    status="not_evaluable",
                    mesh_amplitude=mesh_amplitude,
                    ser=MetricValue.unavailable("SER", "overlapping_or_unresolvable_sideband_windows"),
                    amplitude_unit=spectrum.amplitude_unit,
                )
            occupied_bins |= indices
        lower = _peak_in_window(spectrum, lower_order, sideband_half_width_order)
        upper = _peak_in_window(spectrum, upper_order, sideband_half_width_order)
        numerator += lower + upper
        observations.append(SidebandObservation(
            order=sideband_order,
            lower_order=float(lower_order),
            upper_order=float(upper_order),
            lower_amplitude=lower,
            upper_amplitude=upper,
            asymmetry=abs(lower - upper) / (lower + upper + np.finfo(np.float64).tiny),
        ))
    return SidebandAnalysis(
        status="evaluated",
        mesh_amplitude=mesh_amplitude,
        ser=MetricValue(
            name="SER",
            status="evaluated",
            value=float(numerator / mesh_amplitude),
            details={
                "sideband_peak_amplitude_sum": float(numerator),
                "mesh_peak_amplitude": mesh_amplitude,
                "ratio_semantics": "amplitude_sum_ratio_not_energy_ratio",
                "sideband_spacing_order": 1.0,
                "non_overlapping_windows": True,
                "spectrum_scaling": spectrum.scaling,
            },
        ),
        sidebands=tuple(observations),
        amplitude_unit=spectrum.amplitude_unit,
    )


def _historical_denominator(values: tuple[float, ...]) -> float:
    return float(np.mean(np.asarray(values, dtype=np.float64))) ** 2


def _history_is_compatible(tsa: TSARepresentation, history: TrendHistory) -> bool:
    """方差只有来自完全相同的 regular 定义和实际平均转数才可比。"""
    return (
        history.samples_per_revolution == tsa.synchronous.angle_domain.samples_per_revolution
        and history.mesh_order == tsa.mesh_order
        and history.mesh_harmonics == len(tsa.mesh_orders)
        and history.regular_sideband_order == tsa.regular_sideband_order
        and history.revolutions == tsa.synchronous.revolutions
        and history.input_unit == tsa.amplitude_unit
    )


def compute_na4(tsa: TSARepresentation, history: TrendHistory | None) -> MetricValue:
    """NA4 使用可比历史 residual 方差；无历史时绝不退化为 FM4。"""
    if history is None or not history.residual_variances:
        return MetricValue.unavailable("NA4", "missing_comparable_residual_history")
    if not _history_is_compatible(tsa, history):
        return MetricValue.unavailable("NA4", "incompatible_residual_history_representation")
    residual = tsa.residual_signal
    centered = residual - np.mean(residual)
    numerator = float(np.mean(centered**4))
    denominator = _historical_denominator(history.residual_variances)
    return MetricValue(
        name="NA4",
        status="evaluated",
        value=numerator / denominator,
        details={
            "fourth_central_moment": numerator,
            "historical_variance_mean": float(np.mean(history.residual_variances)),
            "history_count": len(history.residual_variances),
            "history_representation": "same_spr_mesh_regular_definition_revolutions_and_unit",
            "mesh_harmonics": history.mesh_harmonics,
            "regular_sideband_order": history.regular_sideband_order,
            "revolutions": history.revolutions,
        },
    )


def residual_envelope(tsa: TSARepresentation) -> np.ndarray:
    """在角域以点/转为 fs、以阶次为 mesh 频率滤波并取 Hilbert 包络。"""
    angular_sample_rate = tsa.synchronous.angle_domain.samples_per_revolution
    low_order = tsa.mesh_order * 0.9
    high_order = tsa.mesh_order * 1.1
    if low_order <= 0 or high_order >= angular_sample_rate / 2:
        raise ValueError("NB4 啮合带超出角域奈奎斯特范围")
    if len(tsa.residual_signal) < 32:
        raise ValueError("NB4 residual 信号过短")
    sos = butter(4, [low_order, high_order], btype="bandpass", fs=angular_sample_rate, output="sos")
    filtered = sosfiltfilt(sos, tsa.residual_signal)
    return np.asarray(np.abs(hilbert(filtered)), dtype=np.float64)


def compute_nb4(tsa: TSARepresentation, history: TrendHistory | None) -> MetricValue:
    """NB4 使用同角域、同啮合带的历史包络方差；无历史时不可判定。"""
    if history is None or not history.envelope_variances:
        return MetricValue.unavailable("NB4", "missing_comparable_envelope_history")
    if not _history_is_compatible(tsa, history):
        return MetricValue.unavailable("NB4", "incompatible_envelope_history_representation")
    try:
        envelope = residual_envelope(tsa)
    except ValueError as exc:
        return MetricValue.unavailable("NB4", str(exc))
    centered = envelope - np.mean(envelope)
    numerator = float(np.mean(centered**4))
    denominator = _historical_denominator(history.envelope_variances)
    return MetricValue(
        name="NB4",
        status="evaluated",
        value=numerator / denominator,
        details={
            "fourth_central_moment": numerator,
            "historical_variance_mean": float(np.mean(history.envelope_variances)),
            "history_count": len(history.envelope_variances),
            "mesh_harmonics": history.mesh_harmonics,
            "regular_sideband_order": history.regular_sideband_order,
            "revolutions": history.revolutions,
            "angular_sample_rate_points_per_revolution": tsa.synchronous.angle_domain.samples_per_revolution,
            "mesh_center_order": tsa.mesh_order,
            "bandpass_orders": [0.9 * tsa.mesh_order, 1.1 * tsa.mesh_order],
        },
    )


def analyze_order_statistics(spectrum: OrderSpectrum):
    from .types import OrderStatistics

    amplitude = spectrum.amplitude
    total = float(np.sum(amplitude**2))
    if total <= np.finfo(np.float64).tiny:
        return OrderStatistics(
            status="not_evaluable",
            peak_concentration=None,
            kurtosis=None,
            reason="zero_order_spectrum_energy",
        )
    top5 = float(np.sum(np.sort(amplitude)[::-1][:5] ** 2))
    normalized = amplitude / (np.mean(amplitude) + np.finfo(np.float64).tiny)
    kurtosis = float(np.mean(normalized**4) / (np.mean(normalized**2) ** 2 + 1e-12) - 2.0)
    return OrderStatistics(
        status="evaluated",
        peak_concentration=top5 / total,
        kurtosis=kurtosis,
    )
