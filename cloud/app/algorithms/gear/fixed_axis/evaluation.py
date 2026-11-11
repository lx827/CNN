"""定轴原始指标的独立阈值评估；不重算 FFT、TSA 或包络。"""

from __future__ import annotations

from dataclasses import dataclass

from .types import FixedAxisAnalysis, MetricValue


@dataclass(frozen=True)
class FixedAxisThresholds:
    """定轴专用工程阈值；M6A/M8A/NA4/NB4 不配置未验证阈值。"""

    ser_warning: float = 1.5
    ser_critical: float = 3.0
    fm0_warning: float = 5.0
    fm0_critical: float = 10.0
    fm4_warning: float = 5.0
    fm4_critical: float = 10.0
    car_warning: float = 10.0
    car_critical: float = 20.0
    sideband_relative_amplitude: float = 0.05
    sideband_count_warning: int = 2
    sideband_count_critical: int = 4
    order_concentration_warning: float = 0.5
    order_concentration_critical: float = 0.7
    order_kurtosis_warning: float = 5.0
    order_kurtosis_critical: float = 8.0


@dataclass(frozen=True)
class FixedAxisEvaluation:
    status: str
    indicators: dict[str, dict]
    significant_sideband_orders: tuple[int, ...] = ()


def _raw_only(metric: MetricValue) -> dict:
    return {
        "status": metric.status,
        "evaluable": metric.status == "evaluated",
        "value": metric.value,
        "unit": metric.unit,
        "reason": metric.reason,
        "warning": None,
        "critical": None,
        "details": metric.details,
    }


def _thresholded(
    metric: MetricValue,
    warning: float,
    critical: float,
) -> dict:
    result = _raw_only(metric)
    if metric.status == "evaluated":
        result["warning"] = bool(metric.value > warning)
        result["critical"] = bool(metric.value > critical)
    return result


def _statistic(
    name: str,
    value: float | None,
    warning: float,
    critical: float,
    status: str = "evaluated",
    reason: str | None = None,
) -> dict:
    if status != "evaluated" or value is None:
        return {
            "status": "not_evaluable",
            "evaluable": False,
            "value": None,
            "unit": "dimensionless",
            "reason": reason or "statistic_not_evaluable",
            "warning": None,
            "critical": None,
        }
    return {
        "status": "evaluated",
        "evaluable": True,
        "value": value,
        "unit": "dimensionless",
        "reason": None,
        "warning": bool(value > warning),
        "critical": bool(value > critical),
    }


def evaluate_fixed_axis(
    analysis: FixedAxisAnalysis,
    thresholds: FixedAxisThresholds = FixedAxisThresholds(),
) -> FixedAxisEvaluation:
    """只消费 FixedAxisAnalysis 中已提取指标；不可评估不等于健康。"""
    sideband = analysis.sideband_analysis
    significant_orders: tuple[int, ...] = ()
    if sideband.status == "evaluated" and sideband.mesh_amplitude is not None:
        significant_orders = tuple(
            item.order
            for item in sideband.sidebands
            if max(item.lower_amplitude, item.upper_amplitude)
            > thresholds.sideband_relative_amplitude * sideband.mesh_amplitude
        )
        sideband_count = _statistic(
            "sideband_count",
            float(len(significant_orders)),
            thresholds.sideband_count_warning - 1,
            thresholds.sideband_count_critical - 1,
        )
        # 计数采用 >= 语义，与通用 > 标量阈值分开处理。
        sideband_count["warning"] = (
            len(significant_orders) >= thresholds.sideband_count_warning
        )
        sideband_count["critical"] = (
            len(significant_orders) >= thresholds.sideband_count_critical
        )
        sideband_count["significant_orders"] = list(significant_orders)
        sideband_count["relative_amplitude_threshold"] = (
            thresholds.sideband_relative_amplitude
        )
    else:
        sideband_count = {
            "status": "not_evaluable",
            "evaluable": False,
            "value": None,
            "reason": sideband.ser.reason,
            "warning": None,
            "critical": None,
        }

    indicators = {
        "ser": _thresholded(
            sideband.ser, thresholds.ser_warning, thresholds.ser_critical
        ),
        "fm0": _thresholded(
            analysis.fm0, thresholds.fm0_warning, thresholds.fm0_critical
        ),
        "fm4": _thresholded(
            analysis.fm4, thresholds.fm4_warning, thresholds.fm4_critical
        ),
        "car": _thresholded(
            analysis.car, thresholds.car_warning, thresholds.car_critical
        ),
        # 未验证阈值的指标只输出原始数值，warning/critical 永远不是 False 结论。
        "m6a": _raw_only(analysis.m6a),
        "m8a": _raw_only(analysis.m8a),
        "na4": _raw_only(analysis.na4),
        "nb4": _raw_only(analysis.nb4),
        "sideband_count": sideband_count,
        "order_peak_concentration": _statistic(
            "order_peak_concentration",
            analysis.order_statistics.peak_concentration,
            thresholds.order_concentration_warning,
            thresholds.order_concentration_critical,
            status=analysis.order_statistics.status,
            reason=analysis.order_statistics.reason,
        ),
        "order_kurtosis": _statistic(
            "order_kurtosis",
            analysis.order_statistics.kurtosis,
            thresholds.order_kurtosis_warning,
            thresholds.order_kurtosis_critical,
            status=analysis.order_statistics.status,
            reason=analysis.order_statistics.reason,
        ),
    }
    evaluable = any(item.get("evaluable") for item in indicators.values())
    return FixedAxisEvaluation(
        status="evaluated" if evaluable else "indeterminate",
        indicators=indicators,
        significant_sideband_orders=significant_orders,
    )
