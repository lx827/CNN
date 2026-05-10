"""
告警接口
给 Alarm 页面提供分页告警列表
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Alarm
from typing import Optional

router = APIRouter(prefix="/api/alarms", tags=["告警管理"])


@router.get("/")
def get_alarms(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    level: Optional[str] = Query(default=None, description="过滤级别: warning/critical"),
    resolved: Optional[int] = Query(default=None, description="过滤是否已处理: 0/1"),
    device_id: Optional[str] = Query(default=None, description="过滤设备ID"),
    db: Session = Depends(get_db)
):
    """
    分页获取告警列表
    """
    query = db.query(Alarm)

    if level:
        query = query.filter(Alarm.level == level)
    if resolved is not None:
        query = query.filter(Alarm.is_resolved == resolved)
    if device_id:
        query = query.filter(Alarm.device_id == device_id)

    total = query.count()
    items = query.order_by(Alarm.created_at.desc()) \
        .offset((page - 1) * size).limit(size).all()

    return {
        "code": 200,
        "data": {
            "total": total,
            "page": page,
            "size": size,
            "items": [
                {
                    "id": a.id,
                    "device_id": a.device_id,
                    "level": a.level,
                    "category": a.category,
                    "title": a.title,
                    "description": a.description,
                    "suggestion": a.suggestion,
                    "channel": a.channel,
                    "channel_name": a.channel_name,
                    "is_resolved": a.is_resolved,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                    "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
                }
                for a in items
            ]
        }
    }


@router.post("/{alarm_id}/resolve")
def resolve_alarm(alarm_id: int, db: Session = Depends(get_db)):
    """
    处理（关闭）一条告警
    """
    from datetime import datetime
    alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
    if not alarm:
        return {"code": 404, "message": "告警不存在"}

    alarm.is_resolved = 1
    alarm.resolved_at = datetime.utcnow()
    db.commit()

    return {"code": 200, "message": "告警已处理"}
