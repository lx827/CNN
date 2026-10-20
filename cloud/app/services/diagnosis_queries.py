"""诊断摘要读模型：在数据库筛选最新记录，仅加载页面需要的字段。"""
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, aliased

from app.models import Diagnosis


def latest_diagnosis_summaries(db: Session, device_ids, *, per_batch: bool = False):
    """返回各设备（或各设备批次）的最新摘要，时间相同时以 id 决定顺序。

    空时间早于有效时间。不读取 order_analysis、engine_result、full_analysis。
    使用关联 EXISTS，兼容 SQLite 和不支持窗口函数的 MySQL。
    """
    if not device_ids:
        return []
    newer = aliased(Diagnosis)
    same_group = [newer.device_id == Diagnosis.device_id]
    if per_batch:
        same_group.append(newer.batch_index == Diagnosis.batch_index)
    newer_timestamp = or_(
        newer.analyzed_at > Diagnosis.analyzed_at,
        and_(Diagnosis.analyzed_at.is_(None), newer.analyzed_at.is_not(None)),
    )
    same_timestamp = or_(
        newer.analyzed_at == Diagnosis.analyzed_at,
        and_(newer.analyzed_at.is_(None), Diagnosis.analyzed_at.is_(None)),
    )
    has_newer = select(newer.id).where(
        *same_group,
        or_(newer_timestamp, and_(same_timestamp, newer.id > Diagnosis.id)),
    ).correlate(Diagnosis).exists()
    return db.query(
        Diagnosis.device_id, Diagnosis.batch_index, Diagnosis.health_score,
        Diagnosis.status, Diagnosis.fault_probabilities, Diagnosis.analyzed_at,
    ).filter(Diagnosis.device_id.in_(device_ids), ~has_newer).all()
