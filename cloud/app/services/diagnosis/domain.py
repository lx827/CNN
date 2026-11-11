"""业务诊断的唯一状态与证据契约；不推断物理阈值，不执行数值算法。"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from math import isfinite
from typing import Mapping


class EvaluationStatus(str, Enum):
    EVALUATED = "evaluated"
    INDETERMINATE = "indeterminate"
    NOT_EVALUABLE = "not_evaluable"


class DiagnosisConclusion(str, Enum):
    NORMAL = "normal"
    WARNING = "warning"
    FAULT = "fault"
    UNKNOWN = "unknown"


class FaultProposition(str, Enum):
    """可以共存的物理命题；不把内圈和外圈强行当作互斥 D-S 单例。"""
    BEARING_OUTER = "bearing_outer"
    BEARING_INNER = "bearing_inner"
    BEARING_ROLLING = "bearing_rolling"
    BEARING_CAGE = "bearing_cage"
    BEARING_ANOMALY = "bearing_anomaly"
    GEAR_ANOMALY = "gear_anomaly"
    STATISTICAL_ANOMALY = "statistical_anomaly"


class EvidenceFamily(str, Enum):
    BEARING_ENVELOPE = "bearing_envelope"
    BEARING_CYCLIC = "bearing_cyclic"
    GEAR_ORDER = "gear_order"
    PLANETARY = "planetary"
    STATISTICS = "statistics"


# 名称使用精确集合，不以字符串子串决定方法含义；调用方适配仅规范大小写。
METHOD_FAMILIES = {
    **dict.fromkeys(("envelope", "filter_bank_sk", "spectral_kurtosis", "cpw", "med", "mckd", "teager", "dwt", "wp", "emd_envelope", "ceemdan_envelope", "vmd_envelope"), EvidenceFamily.BEARING_ENVELOPE),
    "sc_scoh": EvidenceFamily.BEARING_CYCLIC,
    "standard": EvidenceFamily.GEAR_ORDER, "advanced": EvidenceFamily.GEAR_ORDER,
    "planetary_gear": EvidenceFamily.PLANETARY,
    "statistics": EvidenceFamily.STATISTICS,
}


def canonical_method(value: str) -> str:
    if not isinstance(value, str) or value.strip().casefold() not in METHOD_FAMILIES:
        raise ValueError(f"unknown_diagnosis_method:{value}")
    return value.strip().casefold()


def canonical_proposition(value: str | FaultProposition) -> FaultProposition:
    if isinstance(value, FaultProposition):
        return value
    if not isinstance(value, str):
        raise ValueError("invalid_fault_proposition")
    names = {"bpfo": "bearing_outer", "bpfi": "bearing_inner", "bsf": "bearing_rolling", "ftf": "bearing_cage"}
    normalized = value.strip().casefold()
    return FaultProposition(names.get(normalized, normalized))


@dataclass(frozen=True)
class DiagnosisKey:
    """通道缓存与批次摘要共用身份；channel=0 只表示批次摘要。"""
    device_id: str
    batch_index: int
    channel: int
    denoise_method: str

    def __post_init__(self) -> None:
        if not isinstance(self.device_id, str) or not self.device_id.strip():
            raise ValueError("missing_device_identity")
        for name, minimum in (("batch_index", 1), ("channel", 0)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"invalid_diagnosis_{name}")
        if not isinstance(self.denoise_method, str) or not self.denoise_method.strip():
            raise ValueError("missing_denoise_identity")
        object.__setattr__(self, "denoise_method", self.denoise_method.strip().casefold())

    @property
    def record_id(self) -> str:
        return f"{self.device_id}:{self.batch_index}:ch{self.channel}"


@dataclass(frozen=True)
class PenaltyRequest:
    """对象评估产生的业务扣分请求；权重只在 assessment 中乘一次。"""
    code: str
    amount: float

    def __post_init__(self) -> None:
        if not self.code or not isfinite(self.amount) or self.amount < 0:
            raise ValueError("invalid_penalty_request")


def validate_state(evaluation_status: EvaluationStatus, conclusion: DiagnosisConclusion, health_score: float | None = None, *, require_score: bool = False) -> None:
    if evaluation_status != EvaluationStatus.EVALUATED:
        if conclusion != DiagnosisConclusion.UNKNOWN or health_score is not None:
            raise ValueError("unavailable_diagnosis_requires_unknown_and_null_score")
    elif conclusion == DiagnosisConclusion.UNKNOWN:
        raise ValueError("evaluated_diagnosis_requires_explicit_conclusion")
    elif require_score and (health_score is None or not isfinite(health_score) or not 0 <= health_score <= 100):
        raise ValueError("evaluated_diagnosis_requires_finite_score")


@dataclass(frozen=True)
class Evidence:
    """一个方法的已评估证据；dependencies 标明共同原始记录/处理链。

    confidence 是显式工程可靠度，用于 D-S 支持量，不宣称已校准故障概率。
    正常必须来自可观测、正能量的有效阴性；空列表和算法失败不构成阴性。
    """
    evidence_id: str
    key: DiagnosisKey
    object_id: str
    method: str
    dependencies: frozenset[str]
    evaluation_status: EvaluationStatus
    diagnosis_conclusion: DiagnosisConclusion
    confidence: float | None
    signal_rms: float | None
    propositions: tuple[FaultProposition, ...] = ()
    penalties: tuple[PenaltyRequest, ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "method", canonical_method(self.method))
        object.__setattr__(self, "evaluation_status", EvaluationStatus(self.evaluation_status))
        object.__setattr__(self, "diagnosis_conclusion", DiagnosisConclusion(self.diagnosis_conclusion))
        object.__setattr__(self, "propositions", tuple(dict.fromkeys(canonical_proposition(value) for value in self.propositions)))
        object.__setattr__(self, "dependencies", frozenset(self.dependencies))
        if not self.evidence_id or not self.object_id or not self.dependencies or any(not isinstance(v, str) or not v for v in self.dependencies):
            raise ValueError("missing_evidence_identity_or_dependency")
        if self.key.channel == 0:
            raise ValueError("method_evidence_requires_real_channel")
        validate_state(self.evaluation_status, self.diagnosis_conclusion)
        if self.evaluation_status == EvaluationStatus.EVALUATED:
            if self.signal_rms is None or not isfinite(self.signal_rms) or self.signal_rms <= 0:
                raise ValueError("evaluated_evidence_requires_positive_signal_energy")
            if self.confidence is None or not isfinite(self.confidence) or not 0 < self.confidence <= 1:
                raise ValueError("evaluated_evidence_requires_explicit_reliability")
            if self.diagnosis_conclusion == DiagnosisConclusion.NORMAL and (self.propositions or self.penalties):
                raise ValueError("normal_evidence_cannot_carry_fault_or_penalty")
            if self.diagnosis_conclusion in {DiagnosisConclusion.WARNING, DiagnosisConclusion.FAULT} and not self.propositions:
                raise ValueError("anomalous_evidence_requires_explicit_proposition")
        elif self.confidence is not None or self.propositions or self.penalties or not self.reason:
            raise ValueError("unavailable_evidence_requires_reason_without_votes")

    @property
    def family(self) -> EvidenceFamily:
        return METHOD_FAMILIES[self.method]

    @classmethod
    def from_dict(cls, value: Mapping) -> "Evidence":
        return cls(
            evidence_id=value["evidence_id"], key=DiagnosisKey(**value["key"]),
            object_id=value["object_id"], method=value["method"], dependencies=frozenset(value["dependencies"]),
            evaluation_status=EvaluationStatus(value["evaluation_status"]),
            diagnosis_conclusion=DiagnosisConclusion(value["diagnosis_conclusion"]),
            confidence=value["confidence"], signal_rms=value["signal_rms"],
            propositions=tuple(canonical_proposition(item) for item in value.get("propositions", ())),
            penalties=tuple(PenaltyRequest(**item) for item in value.get("penalties", ())), reason=value.get("reason"),
        )


@dataclass(frozen=True)
class DependencyGroup:
    evidence_ids: tuple[str, ...]
    dependencies: tuple[str, ...]
    normal_mass: float
    anomaly_mass: float
    ignorance_mass: float
    internal_conflict: float = 0.0


@dataclass(frozen=True)
class FusionResult:
    groups: tuple[DependencyGroup, ...] = ()
    normal_mass: float = 0.0
    anomaly_mass: float = 0.0
    ignorance_mass: float = 1.0
    conflict: float = 0.0
    reason: str | None = None


@dataclass(frozen=True)
class Evaluation:
    """对象局部结论保留全部原始方法证据和依赖分组，不隐藏未评估方法。"""
    object_id: str
    evaluation_status: EvaluationStatus
    diagnosis_conclusion: DiagnosisConclusion
    evidence: tuple[Evidence, ...]
    fusion: FusionResult
    reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "evaluation_status", EvaluationStatus(self.evaluation_status))
        object.__setattr__(self, "diagnosis_conclusion", DiagnosisConclusion(self.diagnosis_conclusion))
        validate_state(self.evaluation_status, self.diagnosis_conclusion)
        if any(value.object_id != self.object_id for value in self.evidence):
            raise ValueError("evaluation_object_identity_mismatch")
        if self.evaluation_status == EvaluationStatus.EVALUATED and not any(value.evaluation_status == EvaluationStatus.EVALUATED for value in self.evidence):
            raise ValueError("evaluated_object_requires_observable_evidence")


@dataclass(frozen=True)
class Deduction:
    code: str
    object_id: str
    evidence_ids: tuple[str, ...]
    amount: float
    weight_key: str
    weight: float
    weighted_amount: float


@dataclass(frozen=True)
class Diagnosis:
    evaluation_status: EvaluationStatus
    diagnosis_conclusion: DiagnosisConclusion
    health_score: float | None
    evaluations: tuple[Evaluation, ...]
    deductions: tuple[Deduction, ...]
    recommendation: str
    fault_propositions: tuple[FaultProposition, ...] = ()
    coverage: str = "none"
    reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "evaluation_status", EvaluationStatus(self.evaluation_status))
        object.__setattr__(self, "diagnosis_conclusion", DiagnosisConclusion(self.diagnosis_conclusion))
        validate_state(self.evaluation_status, self.diagnosis_conclusion, self.health_score, require_score=True)
        if self.coverage not in {"none", "partial", "complete"}:
            raise ValueError("invalid_diagnosis_coverage")
        if self.evaluation_status == EvaluationStatus.EVALUATED and not any(value.evaluation_status == EvaluationStatus.EVALUATED for value in self.evaluations):
            raise ValueError("evaluated_diagnosis_requires_evaluated_object")

    def to_dict(self) -> dict:
        """API/缓存只序列化此契约；不输出旧 status 或正常默认值。"""
        def convert(value):
            if isinstance(value, Enum):
                return value.value
            if isinstance(value, Mapping):
                return {key: convert(item) for key, item in value.items()}
            if isinstance(value, (frozenset, set)):
                return [convert(item) for item in sorted(value)]
            if isinstance(value, (tuple, list)):
                return [convert(item) for item in value]
            return value
        return {"contract_version": 1, **convert(asdict(self))}
