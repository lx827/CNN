"""
设备总览接口
给 Dashboard 页面提供数据
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import case, func
from app.database import get_db
from app.models import Device, Diagnosis, Alarm
from datetime import datetime, timezone
from typing import Dict
from app.services.diagnosis_queries import latest_diagnosis_summaries

router = APIRouter(prefix="/api/dashboard", tags=["设备总览"])

# 有效故障类型白名单
VALID_FAULT_TYPES = {
    "正常运行",
    "齿轮磨损",
    "轴承内圈故障",
    "轴承外圈故障",
    "滚动体故障",
    "齿轮断齿",
    "齿轮缺齿",
    "齿轮齿根裂纹",
    "轴承BPFO",
    "轴承BPFI",
    "轴承BSF",
    "轴承异常",
    "齿轮ser",
    "齿轮fm0",
    "齿轮car",
    "齿轮sideband_count",
    "齿轮order_kurtosis",
    "齿轮order_peak_concentration",
}

# 轴承频率指示器 → 中文故障名映射
BEARING_FAULT_MAP = {
    "轴承BPFO": "轴承外圈故障",
    "轴承BPFI": "轴承内圈故障",
    "轴承BSF": "滚动体故障",
}


@router.get("/")
def get_dashboard(db: Session = Depends(get_db)):
    """
    返回设备总览所需的所有数据
    """
    from app.services.diagnosis_store import summary_state

    devices = db.query(Device).all()
    device_list = [
        {
            "device_id": device.device_id,
            "name": device.name,
            **summary_state(device),
            "is_offline": device.is_online == 0,
            "last_seen_at": device.last_seen_at,
            "runtime_hours": device.runtime_hours,
            "channel_count": device.channel_count,
            "channel_names": device.channel_names,
        }
        for device in devices
    ]
    summaries = latest_diagnosis_summaries(db, [device.device_id for device in devices])
    by_device = {value.device_id: value for value in summaries}
    latest_diag = {
        device.device_id: summary_state(by_device.get(device.device_id))
        for device in devices
    }

    # 3. 告警统计
    counts = db.query(
        func.count(Alarm.id),
        func.sum(case((Alarm.level == "warning", 1), else_=0)),
        func.sum(case((Alarm.level == "critical", 1), else_=0)),
        func.sum(case((Alarm.is_resolved == 0, 1), else_=0)),
    ).one()
    alarm_stats = dict(
        zip(
            ("total", "warning", "critical", "unresolved"),
            (int(value or 0) for value in counts),
        )
    )

    return {
        "code": 200,
        "data": {
            "devices": device_list,
            "diagnosis": latest_diag,
            "alarm_stats": alarm_stats,
        },
    }
