"""诊断读写唯一入口；准确缓存键与批次摘要隔离，不恢复旧状态协议。"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.json_utils import sanitize_for_json
from app.models import Diagnosis as DiagnosisRow, Device
from app.services.diagnosis.domain import DiagnosisKey, EvaluationStatus, DiagnosisConclusion, Evidence, validate_state


def validate_payload(payload):
    if payload.get("contract_version") != 1 or "status" in payload:
        raise ValueError("incompatible_diagnosis_contract_reanalysis_required")
    validate_state(EvaluationStatus(payload["evaluation_status"]), DiagnosisConclusion(payload["diagnosis_conclusion"]), payload["health_score"], require_score=True)
    if payload.get("coverage") not in {"none", "partial", "complete"}:
        raise ValueError("invalid_diagnosis_coverage")
    for evaluation in payload["evaluations"]:
        values = [Evidence.from_dict(item) for item in evaluation["evidence"]]
        if any(item.object_id != evaluation["object_id"] for item in values):
            raise ValueError("persisted_evidence_object_identity_mismatch")
        validate_state(EvaluationStatus(evaluation["evaluation_status"]), DiagnosisConclusion(evaluation["diagnosis_conclusion"]))
        if evaluation["evaluation_status"] == "evaluated" and not any(item.evaluation_status == EvaluationStatus.EVALUATED for item in values):
            raise ValueError("evaluated_object_requires_observable_evidence")
    if payload["evaluation_status"] == "evaluated" and not any(value["evaluation_status"] == "evaluated" for value in payload["evaluations"]):
        raise ValueError("evaluated_diagnosis_requires_evaluated_object")
    if payload.get("research_only") or payload.get("production_eligible") is False:
        raise ValueError("research_result_cannot_be_persisted_as_production_diagnosis")


def cache_query(db: Session, key: DiagnosisKey):
    return db.query(DiagnosisRow).filter(
        DiagnosisRow.device_id == key.device_id, DiagnosisRow.batch_index == key.batch_index,
        DiagnosisRow.channel == key.channel, DiagnosisRow.denoise_method == key.denoise_method,
    ).order_by(DiagnosisRow.analyzed_at.desc(), DiagnosisRow.id.desc())


def save_diagnosis(db: Session, key: DiagnosisKey, payload: dict, *, update_device: bool = False):
    """追加历史行避免并发覆盖；调用者事务负责提交和告警一致性。"""
    validate_payload(payload)
    if update_device and key.channel != 0:
        raise ValueError("only_batch_summary_updates_device_diagnosis")
    for evaluation in payload["evaluations"]:
        for item in evaluation["evidence"]:
            source = DiagnosisKey(**item["key"])
            if (source.device_id, source.batch_index) != (key.device_id, key.batch_index) or (key.channel and source.channel != key.channel):
                raise ValueError("cache_evidence_record_identity_mismatch")
    safe = sanitize_for_json(payload)
    row = DiagnosisRow(
        device_id=key.device_id, batch_index=key.batch_index, channel=key.channel,
        denoise_method=key.denoise_method, evaluation_status=safe["evaluation_status"],
        diagnosis_conclusion=safe["diagnosis_conclusion"], health_score=safe["health_score"],
        coverage=safe["coverage"],
        engine_result=safe, rot_freq=safe.get("rot_freq_hz", safe.get("rot_freq")),
        analyzed_at=datetime.now(timezone.utc),
    )
    db.add(row)
    if update_device:
        device = db.query(Device).filter(Device.device_id == key.device_id).first()
        if device:
            device.evaluation_status = row.evaluation_status
            device.diagnosis_conclusion = row.diagnosis_conclusion
            device.health_score = row.health_score
            device.coverage = row.coverage
    return row


def save_batch(db: Session, device_id: str, batch_index: int, denoise: str, payload: dict):
    for channel_name, channel_result in payload.get("channels", {}).items():
        from app.services.analyzer import channel_number
        channel = channel_number(channel_name)
        save_diagnosis(db, DiagnosisKey(device_id, batch_index, channel, denoise), channel_result)
    return save_diagnosis(db, DiagnosisKey(device_id, batch_index, 0, denoise), payload, update_device=denoise == "none")


def read_diagnosis(db: Session, key: DiagnosisKey) -> dict | None:
    row = cache_query(db, key).first()
    if row is None:
        return None
    payload = row.engine_result
    if not isinstance(payload, dict) or payload.get("contract_version") != 1:
        from app.services.diagnosis.assessment import assess_evidence
        return {**assess_evidence({}).to_dict(), "reason": "stored_contract_requires_reanalysis"}
    try:
        validate_payload(payload)
    except (ValueError, KeyError, TypeError):
        from app.services.diagnosis.assessment import assess_evidence
        return {**assess_evidence({}).to_dict(), "reason": "stored_contract_requires_reanalysis"}
    return dict(payload)


def summary_state(row) -> dict:
    if row is None:
        return {"evaluation_status": "not_evaluable", "diagnosis_conclusion": "unknown", "health_score": None, "coverage": "none"}
    try:
        state = EvaluationStatus(row.evaluation_status)
        conclusion = DiagnosisConclusion(row.diagnosis_conclusion)
        validate_state(state, conclusion, row.health_score, require_score=True)
    except (ValueError, TypeError):
        return {"evaluation_status": "not_evaluable", "diagnosis_conclusion": "unknown", "health_score": None, "coverage": "none"}
    return {"evaluation_status": state.value, "diagnosis_conclusion": conclusion.value, "health_score": row.health_score,
            "coverage": getattr(row, "coverage", "none")}
