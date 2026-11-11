"""只消费当前方法产出的数值；未验证健康基线不生成故障命名或告警。"""
from .types import PlanetaryAnalysis, PlanetaryBaseline, PlanetaryEvaluation


def collect_planetary_metrics(analysis: PlanetaryAnalysis) -> dict[str, float]:
    values = {}
    if analysis.sidebands and analysis.sidebands.ser.status == "evaluated":
        values["sidebands.ser"] = analysis.sidebands.ser.value
    for key, metric in analysis.metrics.items():
        if metric.status == "evaluated" and metric.value is not None:
            values[f"metrics.{key}"] = metric.value
    for method in analysis.methods:
        if method.status != "computed":
            continue
        for key, metric in method.metrics.items():
            if metric.status == "evaluated" and metric.value is not None:
                values[f"{method.method}.{key}"] = metric.value
        for peak in method.peaks:
            if peak.status == "computed" and peak.amplitude_to_background is not None:
                values[f"{method.method}.{peak.name}.amplitude_to_background"] = peak.amplitude_to_background
    return values


def evaluate_planetary(analysis: PlanetaryAnalysis, baseline: PlanetaryBaseline | None = None) -> PlanetaryEvaluation:
    """对已有分析直接重评。基线只判定异常，不把异常直接命名为断齿/裂纹。

    CAR、各阶矩和传递路径边带没有通用行星阈值；调用方必须提供相同
    representation_key 下经验证的界限。没有基线时保留证据且结论 unknown。
    """
    values = collect_planetary_metrics(analysis)
    if analysis.status != "computed":
        return PlanetaryEvaluation("not_evaluable", "unknown", {}, analysis.reason)
    if baseline is None:
        return PlanetaryEvaluation("not_evaluable", "unknown", {}, "missing_comparable_planetary_baseline", tuple(values))
    if baseline.representation_key != analysis.representation_key:
        return PlanetaryEvaluation("not_evaluable", "unknown", {}, "incompatible_planetary_baseline", tuple(values))
    indicators = {}
    for threshold in baseline.thresholds:
        key = threshold.metric_key
        if key not in values:
            indicators[key] = {"value": None, "status": "not_evaluable", "warning": False, "critical": False, "reason": "method_metric_not_available"}
            continue
        value = values[key]
        above = threshold.direction == "above"
        indicators[key] = {
            "value": value, "status": "evaluated",
            "warning": value > threshold.warning if above else value < threshold.warning,
            "critical": value > threshold.critical if above else value < threshold.critical,
            "evidence": key, "baseline_source": baseline.source,
            "interpretation": "planetary_baseline_deviation_not_fault_type_localization",
        }
    valid = [entry for entry in indicators.values() if entry["status"] == "evaluated"]
    unconsumed = tuple(key for key in values if key not in indicators)
    if not valid:
        return PlanetaryEvaluation("not_evaluable", "unknown", indicators, "no_available_calibrated_method_metric", unconsumed)
    conclusion = "anomaly" if any(v["warning"] or v["critical"] for v in valid) else "no_anomaly_in_calibrated_metrics"
    return PlanetaryEvaluation("evaluated", conclusion, indicators, unconsumed_metrics=unconsumed)
