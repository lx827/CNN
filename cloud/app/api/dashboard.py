"""
设备总览接口
给 Dashboard 页面提供数据
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import Device, Diagnosis, Alarm
from datetime import datetime, timedelta
from typing import Dict

router = APIRouter(prefix="/api/dashboard", tags=["设备总览"])

def _get_offline_threshold(device: Device, now: datetime) -> datetime:
    """
    根据设备通信间隔计算离线阈值。
    以任务轮询间隔（实际心跳）为主，以上传间隔为辅，最少 5 分钟。
    """
    base_seconds = 300  # 默认 5 分钟
    # 任务轮询是边端和云端的实际通信频率，以此为基准
    if device.task_poll_interval and device.task_poll_interval > 0:
        base_seconds = max(base_seconds, device.task_poll_interval * 3 + 60)
    # 如果上传间隔更大，也要兜底覆盖
    if device.upload_interval and device.upload_interval > 0:
        base_seconds = max(base_seconds, device.upload_interval * 2 + 60)
    return now - timedelta(seconds=base_seconds)


@router.get("/")
def get_dashboard(db: Session = Depends(get_db)):
    """
    返回设备总览所需的所有数据
    """
    # 1. 设备列表（含离线判断）
    now = datetime.utcnow()
    devices = db.query(Device).all()
    device_list = []
    for d in devices:
        offline_threshold = _get_offline_threshold(d, now)
        # 判断离线：last_seen_at 为空 或 超过阈值未上传
        is_offline = d.last_seen_at is None or d.last_seen_at < offline_threshold
        effective_status = "offline" if is_offline else d.status
        device_list.append({
            "device_id": d.device_id,
            "name": d.name,
            "health_score": None if is_offline else d.health_score,
            "status": effective_status,
            "original_status": d.status,
            "is_offline": is_offline,
            "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
            "runtime_hours": d.runtime_hours,
            "channel_count": d.channel_count,
            "channel_names": d.channel_names,
        })

    # 2. 最新诊断结果（取每个设备最新一条）
    latest_diag = {}
    for d in devices:
        offline_threshold = _get_offline_threshold(d, now)
        is_offline = d.last_seen_at is None or d.last_seen_at < offline_threshold
        diag = db.query(Diagnosis).filter(Diagnosis.device_id == d.device_id) \
            .order_by(Diagnosis.analyzed_at.desc()).first()
        if diag:
            latest_diag[d.device_id] = {
                "health_score": diag.health_score,
                "fault_probabilities": diag.fault_probabilities or {},
                "status": diag.status,
            }
        elif is_offline:
            # 离线设备不给默认值，标记为无数据
            latest_diag[d.device_id] = {
                "health_score": None,
                "fault_probabilities": {},
                "status": "offline",
            }
        else:
            # 还没有分析过，给默认值
            latest_diag[d.device_id] = {
                "health_score": 87,
                "fault_probabilities": {"齿轮磨损": 0.15, "轴承内圈故障": 0.05, "正常运行": 0.80},
                "status": "normal",
            }

    # 3. 告警统计
    alarm_stats = {
        "total": db.query(Alarm).count(),
        "warning": db.query(Alarm).filter(Alarm.level == "warning").count(),
        "critical": db.query(Alarm).filter(Alarm.level == "critical").count(),
        "unresolved": db.query(Alarm).filter(Alarm.is_resolved == 0).count(),
    }

    return {
        "code": 200,
        "data": {
            "devices": device_list,
            "diagnosis": latest_diag,
            "alarm_stats": alarm_stats,
        }
    }
