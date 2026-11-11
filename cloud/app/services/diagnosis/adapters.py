"""对象 Pipeline 评估到业务 Evidence 的唯一边界；不从原始数值重新应用阈值。"""
from __future__ import annotations

from collections.abc import Mapping
import numpy as np

from .assessment import AssessmentPolicy, assess_evidence
from .domain import (
    DiagnosisConclusion as C, DiagnosisKey, EvaluationStatus as S, Evidence,
    PenaltyRequest, canonical_proposition,
)


def unavailable_result(reason: str, *, key: DiagnosisKey, object_id: str, method: str, indeterminate: bool = False) -> dict:
    value = Evidence(f"{key.record_id}:{key.denoise_method}:{object_id}:{method}", key, object_id, method,
                     frozenset({f"{key.record_id}:{object_id}:raw_signal"}),
                     S.INDETERMINATE if indeterminate else S.NOT_EVALUABLE, C.UNKNOWN, None, None, reason=reason)
    return {**assess_evidence({object_id: (value,)}).to_dict(), "method": method, "reason": reason,
            "evaluation": {"evaluation_status": value.evaluation_status.value, "indicators": {}},
            "analysis": {"status": "unavailable", "reason": reason}, "production_eligible": True}


def adapt_method_result(result: Mapping, *, key: DiagnosisKey, object_id: str, method: str, signal: np.ndarray, physical_parameters: bool) -> dict:
    """仅读取实际对象评估的标志；未阈值原始指标、研究组合和失败不投票。"""
    raw = dict(result)
    selected_method = str(raw.get("method") or method).casefold()
    if selected_method == "planetary_gear":
        method = selected_method
    # MCKD 无显式目标实际已运行 MED，证据标识跟随实际方法。
    elif method == "mckd" and selected_method == "med":
        method = selected_method
    if raw.get("research_only") or raw.get("production_eligible") is False:
        return {**raw, **assess_evidence({}).to_dict(), "research_only": True, "production_eligible": False}
    evaluation = raw.get("evaluation") or {}
    state = evaluation.get("status", evaluation.get("evaluation_status", raw.get("evaluation_status")))
    indicators = evaluation.get("indicators", raw.get("fault_indicators", {}))
    if not isinstance(indicators, Mapping):
        indicators = {}
    observed = []
    for name, item in indicators.items():
        if not isinstance(item, Mapping) or item.get("evaluable") is False or item.get("status", item.get("evaluation_status")) in {"not_evaluable", "indeterminate"}:
            continue
        # None 不是已评估阴性；只有评估器明确给出的 bool 才能形成证据。
        flags = [item.get(flag) for flag in ("significant", "warning", "critical")]
        if any(isinstance(flag, (bool, np.bool_)) for flag in flags):
            observed.append((name, item))
    values = np.asarray(signal, dtype=float)
    rms = float(np.sqrt(np.mean(values ** 2))) if values.size and values.ndim == 1 and np.all(np.isfinite(values)) else 0.
    reason = raw.get("reason") or evaluation.get("reason")
    if rms <= 0 or not np.isfinite(rms):
        reason = "zero_or_invalid_signal_energy"
    elif state != "evaluated":
        reason = reason or "object_evaluation_not_available"
    elif not physical_parameters:
        reason = "missing_physical_parameters"
    elif not observed:
        reason = "no_observable_thresholded_metric"
    else:
        reason = None
    identity = f"{key.record_id}:{key.denoise_method}:{object_id}:{method}"
    dependency = frozenset({f"{key.record_id}:{object_id}:raw_signal"})
    if reason:
        evidence = Evidence(identity, key, object_id, method, dependency,
                            S.INDETERMINATE if state == "indeterminate" else S.NOT_EVALUABLE,
                            C.UNKNOWN, None, rms or None, reason=reason)
    else:
        active = [(name, item) for name, item in observed if any(isinstance(item.get(flag), (bool, np.bool_)) and bool(item[flag]) for flag in ("significant", "warning", "critical"))]
        critical = any(bool(item.get("critical", False)) for _, item in active)
        conclusion = C.FAULT if critical else C.WARNING if active else C.NORMAL
        propositions = []
        penalties = []
        for name, item in active:
            if object_id.startswith("bearing"):
                if str(name).casefold() in {"bpfo", "bpfi", "bsf", "ftf"}:
                    proposition = canonical_proposition(name)
                    code = "bearing_cyclic" if method == "sc_scoh" else proposition.value
                else:
                    proposition = canonical_proposition("bearing_anomaly")
                    code = "bearing_cyclic" if method == "sc_scoh" else "bearing_statistical"
            else:
                proposition = canonical_proposition("gear_anomaly")
                code = "planetary_baseline" if method == "planetary_gear" else {
                    "ser": "gear_ser", "sideband_count": "gear_sideband", "fm0": "gear_fm0",
                    "fm4": "gear_fm4", "car": "gear_car", "order_peak_concentration": "gear_order_statistics",
                    "order_kurtosis": "gear_order_statistics",
                }.get(name)
                if code is None:
                    # 不为未登记的原始指标或未来字段凭空创造扣分与故障证据。
                    continue
            propositions.append(proposition)
            penalties.append(PenaltyRequest(code, 25. if bool(item.get("critical", False)) else 12.))
        if active and not propositions:
            evidence = Evidence(identity, key, object_id, method, dependency, S.NOT_EVALUABLE, C.UNKNOWN, None, rms, reason="unregistered_active_metric")
        else:
            evidence = Evidence(identity, key, object_id, method, dependency, S.EVALUATED, conclusion, .8, rms, tuple(propositions), tuple(penalties))
    assessment = assess_evidence({object_id: (evidence,)})
    # 原始计算表示保留数学状态；诊断领域不再同时携带旧 status。
    original_analysis = dict(raw.pop("analysis", {}))
    original_analysis.setdefault("status", raw.pop("analysis_status", "computed" if state == "evaluated" else "unavailable"))
    raw.pop("status", None)
    raw.pop("evaluation_status", None)
    raw.pop("diagnosis_conclusion", None)
    raw["evaluation"] = {"evaluation_status": evidence.evaluation_status.value, "indicators": dict(indicators), "reason": evidence.reason}
    return {**raw, **assessment.to_dict(), "reason": evidence.reason,
            "method": method, "analysis": original_analysis, "production_eligible": True}


def combine_method_results(results: Mapping[str, dict], policy: AssessmentPolicy | None = None) -> dict:
    """保留所有局部结果，消费其规范证据；不重复评分、不重复调用算法。"""
    by_object = {}
    seen = set()
    for result in results.values():
        if result.get("production_eligible") is False or result.get("research_only"):
            continue
        for evaluation in result.get("evaluations", ()):
            values = by_object.setdefault(evaluation["object_id"], [])
            for item in evaluation["evidence"]:
                if item["evidence_id"] in seen:
                    continue
                seen.add(item["evidence_id"])
                values.append(Evidence.from_dict(item))
    return assess_evidence({key: tuple(values) for key, values in by_object.items()}, policy).to_dict()
