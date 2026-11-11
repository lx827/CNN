"""已有对象证据的单源重评、评分和建议；不导入算法或重新读取信号。"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Mapping
from app.core.config import DIAGNOSIS_WEIGHTS

from .domain import (
    Deduction, Diagnosis, DiagnosisConclusion, Evaluation, EvaluationStatus, Evidence,
    FaultProposition, FusionResult,
)
from .fusion.evidence import fuse_evidence


@dataclass(frozen=True)
class DeductionPolicy:
    weight_key: str
    default_weight: float
    description: str


# 名称和权重一一对应；未知请求必须报错，不能回退到 kurtosis。
DEDUCTION_POLICIES = {
    "bearing_outer": DeductionPolicy("bpfo", 1.2, "外圈故障频率证据"),
    "bearing_inner": DeductionPolicy("bpfi", 1.2, "内圈故障频率证据"),
    "bearing_rolling": DeductionPolicy("bsf", 1.0, "滚动体故障频率证据"),
    "bearing_cage": DeductionPolicy("bsf", 1.0, "保持架故障频率证据"),
    "bearing_statistical": DeductionPolicy("kurtosis", 1.0, "轴承统计异常"),
    "bearing_cyclic": DeductionPolicy("scoh_evidence", .8, "轴承循环频率证据"),
    "gear_ser": DeductionPolicy("ser", .9, "啮合边带幅值比"),
    "gear_sideband": DeductionPolicy("gear_sideband", .8, "啮合边带结构"),
    "gear_fm0": DeductionPolicy("fm4", .8, "齿轮 FM0 评估"),
    "gear_fm4": DeductionPolicy("fm4", .8, "齿轮 FM4 评估"),
    "gear_car": DeductionPolicy("car", .7, "齿轮周期族 CAR 评估"),
    "gear_order_statistics": DeductionPolicy("car", .7, "齿轮阶次统计评估"),
    "planetary_baseline": DeductionPolicy("fm4", .8, "行星可比健康基线偏移"),
    "time_kurtosis": DeductionPolicy("kurtosis", 1.0, "时域峭度阈值证据"),
    "time_crest": DeductionPolicy("crest_factor", .8, "峰值因子阈值证据"),
    "time_rms": DeductionPolicy("rms", .6, "RMS 基线证据"),
    "time_peak": DeductionPolicy("peak", .5, "峰值阈值证据"),
    "trend_baseline": DeductionPolicy("kurtosis", 1.0, "已评估趋势/基线证据"),
    "evidence_conflict": DeductionPolicy("ds_conflict", 8.0, "独立证据冲突审计"),
}


@dataclass(frozen=True)
class AssessmentPolicy:
    """业务工程策略，不声称具有跨设备、跨数据集的诊断效果保证。"""
    weights: Mapping[str, float] = field(default_factory=lambda: dict(DIAGNOSIS_WEIGHTS))
    conflict_limit: float = .8

    def __post_init__(self) -> None:
        valid = {value.weight_key for value in DEDUCTION_POLICIES.values()}
        if set(self.weights) - valid:
            raise ValueError("unknown_diagnosis_weight")
        if any(not isfinite(value) or value < 0 for value in self.weights.values()):
            raise ValueError("diagnosis_weights_must_be_finite_nonnegative")
        if not isfinite(self.conflict_limit) or not 0 < self.conflict_limit <= 1:
            raise ValueError("invalid_conflict_limit")

    def weight(self, code: str) -> float:
        definition = DEDUCTION_POLICIES[code]
        return float(self.weights.get(definition.weight_key, definition.default_weight))


SEVERITY = {DiagnosisConclusion.NORMAL: 0, DiagnosisConclusion.WARNING: 1, DiagnosisConclusion.FAULT: 2}


def evaluate_object(object_id: str, evidence: tuple[Evidence, ...], policy: AssessmentPolicy) -> Evaluation:
    if any(value.object_id != object_id for value in evidence):
        raise ValueError("evidence_object_identity_mismatch")
    for value in evidence:
        for request in value.penalties:
            if request.code not in DEDUCTION_POLICIES or request.code == "evidence_conflict":
                raise ValueError(f"unknown_or_reserved_deduction:{request.code}")
    observed = tuple(value for value in evidence if value.evaluation_status == EvaluationStatus.EVALUATED)
    fusion = fuse_evidence(evidence)
    if not observed:
        state = EvaluationStatus.INDETERMINATE if any(value.evaluation_status == EvaluationStatus.INDETERMINATE for value in evidence) else EvaluationStatus.NOT_EVALUABLE
        return Evaluation(object_id, state, DiagnosisConclusion.UNKNOWN, evidence, fusion, "no_observable_object_evidence")
    if fusion.conflict >= policy.conflict_limit:
        return Evaluation(object_id, EvaluationStatus.INDETERMINATE, DiagnosisConclusion.UNKNOWN, evidence, fusion, "conflicting_object_evidence")
    conclusion = max((value.diagnosis_conclusion for value in observed), key=SEVERITY.__getitem__)
    return Evaluation(object_id, EvaluationStatus.EVALUATED, conclusion, evidence, fusion)


def _object_deductions(evaluation: Evaluation, policy: AssessmentPolicy) -> tuple[Deduction, ...]:
    """每个共同依赖组只取最大加权扣分，不按相似算法数量累计。"""
    by_id = {value.evidence_id: value for value in evaluation.evidence}
    deductions = []
    for group in evaluation.fusion.groups:
        candidates = [(request.amount * policy.weight(request.code), request.code, request.amount)
                      for identity in group.evidence_ids for request in by_id[identity].penalties]
        if not candidates:
            continue
        weighted, code, amount = max(candidates)
        definition = DEDUCTION_POLICIES[code]
        deductions.append(Deduction(code, evaluation.object_id, group.evidence_ids, amount, definition.weight_key, policy.weight(code), weighted))
    if evaluation.fusion.conflict > 0:
        # 原量是冲突系数；ds_conflict=8 是一次乘数，不再先扣8分后再乘8。
        amount = evaluation.fusion.conflict
        deductions.append(Deduction("evidence_conflict", evaluation.object_id, tuple(by_id), amount, "ds_conflict", policy.weight("evidence_conflict"), amount * policy.weight("evidence_conflict")))
    return tuple(deductions)


def _recommendation(conclusion: DiagnosisConclusion, evaluations: tuple[Evaluation, ...]) -> str:
    available = [value.object_id for value in evaluations if value.evaluation_status == EvaluationStatus.EVALUATED]
    unavailable = [value.object_id for value in evaluations if value.evaluation_status != EvaluationStatus.EVALUATED]
    if conclusion == DiagnosisConclusion.UNKNOWN:
        if any(value.reason == "conflicting_object_evidence" for value in evaluations):
            return "有效证据相互冲突，当前不能形成可靠诊断；请核对工况和传感器，并安排复核。"
        return "缺少可观测诊断证据；请核对机械参数、转速、数据质量和所需健康基线。"
    subject = "、".join(available)
    if conclusion == DiagnosisConclusion.NORMAL:
        message = f"已评估对象（{subject}）未见阈值异常，建议按周期监测。"
    elif conclusion == DiagnosisConclusion.WARNING:
        message = f"已评估对象（{subject}）存在预警证据，建议关注工况并安排检查。"
    else:
        message = f"已评估对象（{subject}）存在故障级证据，建议及时检查并由维护人员确认。"
    if unavailable:
        message += f" 对象（{"、".join(unavailable)}）尚不可判定，本结论不覆盖这些对象。"
    return message


def assess_evidence(evidence_by_object: Mapping[str, tuple[Evidence, ...]], policy: AssessmentPolicy | None = None) -> Diagnosis:
    """直接对已有证据重评；混合局部未知不抹掉其他对象的有效评估。

    评分只加权扣分一次，诊断结论来自对象评估的严重级别，绝不再按分数
    或原始指标重判一次；分数是工程强度展示，不是已校准故障概率。
    """
    policy = policy or AssessmentPolicy()
    evaluations = tuple(evaluate_object(key, tuple(values), policy) for key, values in sorted(evidence_by_object.items()))
    available = tuple(value for value in evaluations if value.evaluation_status == EvaluationStatus.EVALUATED)
    if not available:
        state = EvaluationStatus.INDETERMINATE if any(value.evaluation_status == EvaluationStatus.INDETERMINATE for value in evaluations) else EvaluationStatus.NOT_EVALUABLE
        return Diagnosis(state, DiagnosisConclusion.UNKNOWN, None, evaluations, (), _recommendation(DiagnosisConclusion.UNKNOWN, evaluations), reason="no_evaluated_object")
    conclusion = max((value.diagnosis_conclusion for value in available), key=SEVERITY.__getitem__)
    deductions = tuple(item for value in available for item in _object_deductions(value, policy))
    score = round(max(0.0, 100.0 - sum(value.weighted_amount for value in deductions)), 2)
    propositions = tuple(sorted({proposition for value in available for item in value.evidence if item.evaluation_status == EvaluationStatus.EVALUATED for proposition in item.propositions}, key=lambda value: value.value))
    return Diagnosis(EvaluationStatus.EVALUATED, conclusion, score, evaluations, deductions, _recommendation(conclusion, evaluations), propositions, "complete" if len(available) == len(evaluations) else "partial")


def reassess_diagnosis(payload: Mapping, policy: AssessmentPolicy | None = None) -> Diagnosis:
    """持久化规范证据直接重评，不接受旧 status 读模型或重新调用算法。"""
    if payload.get("contract_version") != 1 or "status" in payload:
        raise ValueError("incompatible_diagnosis_contract_reanalysis_required")
    return assess_evidence({
        value["object_id"]: tuple(Evidence.from_dict(item) for item in value["evidence"])
        for value in payload["evaluations"]
    }, policy)
