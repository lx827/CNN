"""行星 carrier 边带和包络局部证据；所有窗口互斥且检查真实分辨率。"""
import numpy as np

from app.algorithms.gear.fixed_axis.types import MetricValue
from app.algorithms.order import OrderSpectrum

from .types import ModulationPeak, PlanetarySidebands


def analyze_planetary_sidebands(spectrum: OrderSpectrum, mesh_order: float, carrier_order: float, n_sidebands: int = 6) -> PlanetarySidebands:
    """SER=不重叠 carrier 间隔边带峰值之和/啮合峰值，非能量比。

    Hann 主瓣至少需要 ±2 个 bin，半窗固定为 0.4 carrier，故要求
    Δorder<=0.2 carrier。天然传递路径边带只描述，不附加告警阈值。
    """
    def unavailable(reason: str) -> PlanetarySidebands:
        return PlanetarySidebands(MetricValue.unavailable("SER", reason), carrier_order)
    if (not np.isfinite(mesh_order) or not np.isfinite(carrier_order) or carrier_order <= 0 or mesh_order <= 0 or isinstance(n_sidebands, bool) or not isinstance(n_sidebands, int) or n_sidebands < 1):
        return unavailable("invalid_planetary_sideband_parameters")
    if spectrum.scaling != "single_sided_amplitude":
        return unavailable("requires_single_sided_amplitude")
    width = 0.4 * carrier_order
    if spectrum.order_resolution > width / 2 * (1 + 1e-9):
        return unavailable("carrier_sidebands_not_resolvable")
    centers = [mesh_order] + [mesh_order + sign * n * carrier_order for n in range(1, n_sidebands + 1) for sign in (-1, 1)]
    if min(centers) - width <= 0 or max(centers) + width > spectrum.order_bins[-1] + spectrum.order_resolution * 1e-9:
        return unavailable("requested_planetary_sidebands_outside_spectrum")
    amplitudes = []
    occupied: set[int] = set()
    for center in centers:
        indices = set(np.flatnonzero(np.abs(spectrum.order_bins - center) <= width).tolist())
        if not indices or occupied & indices:
            return unavailable("overlapping_or_empty_planetary_windows")
        occupied |= indices
        amplitudes.append(float(np.max(spectrum.amplitude[list(indices)])))
    mesh = amplitudes[0]
    if mesh <= float(np.max(spectrum.amplitude)) * 1e-10 or mesh <= np.finfo(float).tiny:
        return unavailable("no_observable_mesh_carrier")
    observations = []
    for index in range(n_sidebands):
        low, high = amplitudes[1 + 2 * index:3 + 2 * index]
        observations.append({
            "order": index + 1, "spacing": carrier_order,
            "order_low": centers[1 + 2 * index], "order_high": centers[2 + 2 * index],
            "amp_low": low, "amp_high": high,
            "relative_amplitude": max(low, high) / mesh,
            "asymmetry": abs(low - high) / (low + high) if low + high else 0.0,
            # 谱线存在并不等于行星故障，供旧展示读取时保持不告警。
            "significant": False,
        })
    return PlanetarySidebands(
        MetricValue("SER", "evaluated", float(sum(amplitudes[1:]) / mesh), details={
            "ratio_semantics": "planetary_carrier_spaced_peak_amplitude_sum_ratio",
            "sideband_spacing_order": carrier_order,
            "half_width_order": width,
            "non_overlapping_windows": True,
            "threshold_status": "requires_comparable_planetary_baseline",
        }), carrier_order, mesh, tuple(observations),
    )


def modulation_peaks(spectrum: OrderSpectrum, targets: dict[str, float], usable_max_order: float) -> tuple[ModulationPeak, ...]:
    """峰/邻域幅值均值，不冒充功率 SNR；不在近零局部背景上除固定常数。"""
    result = []
    centers = list(targets.values())
    for name, center in targets.items():
        spacing = min([center] + [abs(center - other) for other in centers if abs(center - other) > 1e-12])
        width = 0.2 * spacing
        reason = None
        if any(abs(center - other) < 1e-12 for other_name, other in targets.items() if other_name != name):
            reason = "coincident_event_orders_not_identifiable"
        elif 2 * spectrum.order_resolution > width * (1 + 1e-9):
            reason = "event_orders_not_resolvable"
        elif center + 4 * width > min(usable_max_order, float(spectrum.order_bins[-1])) or center - 4 * width <= 0:
            reason = "insufficient_local_background_coverage"
        if reason:
            result.append(ModulationPeak(name, center, "not_evaluable", reason=reason))
            continue
        distance = np.abs(spectrum.order_bins - center)
        target_mask = distance <= width
        background_mask = (distance >= 2 * width) & (distance <= 4 * width)
        for other in centers:
            background_mask &= np.abs(spectrum.order_bins - other) > width
        if np.count_nonzero(background_mask) < 4 or not np.any(target_mask):
            result.append(ModulationPeak(name, center, "not_evaluable", reason="insufficient_independent_background_bins"))
            continue
        indices = np.flatnonzero(target_mask)
        peak_index = int(indices[np.argmax(spectrum.amplitude[indices])])
        amplitude = float(spectrum.amplitude[peak_index])
        background = float(np.mean(spectrum.amplitude[background_mask]))
        scale = float(np.max(spectrum.amplitude))
        if background <= max(scale * 1e-10, np.finfo(float).tiny):
            result.append(ModulationPeak(name, center, "not_evaluable", amplitude=amplitude, peak_order=float(spectrum.order_bins[peak_index]), background=background, reason="no_measurable_local_background"))
        else:
            result.append(ModulationPeak(name, center, "computed", amplitude, float(spectrum.order_bins[peak_index]), background, amplitude / background))
    return tuple(result)


def normalized_moment(values: np.ndarray, degree: int, name: str, representation: str) -> MetricValue:
    """先缩放再标准化，避免小量纲的四/六/八阶矩下溢。"""
    centered = values - np.mean(values)
    scale = float(np.max(np.abs(centered)))
    if scale <= np.finfo(float).tiny:
        return MetricValue.unavailable(name, "zero_variance")
    normalized = centered / scale
    variance = float(np.mean(normalized ** 2))
    if variance <= np.finfo(float).tiny:
        return MetricValue.unavailable(name, "zero_variance")
    value = float(np.mean(normalized ** degree) / variance ** (degree / 2))
    return MetricValue(name, "evaluated", value, details={"signal_representation": representation, "central_moment_degree": degree, "kurtosis_convention": "Pearson" if degree == 4 else None})
