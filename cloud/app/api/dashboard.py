"""
设备总览接口
给 Dashboard 页面提供数据
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import Device, Diagnosis, Alarm
from datetime import datetime
from typing import Dict

router = APIRouter(prefix="/api/dashboard", tags=["设备总览"])

# 有效故障类型白名单
VALID_FAULT_TYPES = {
    "正常运行", "齿轮磨损", "轴承内圈故障", "轴承外圈故障",
    "滚动体故障", "齿轮断齿", "齿轮缺齿", "齿轮齿根裂纹",
    "轴承BPFO", "轴承BPFI", "轴承BSF", "轴承异常",
    "齿轮ser", "齿轮fm0", "齿轮car", "齿轮sideband_count",
    "齿轮order_kurtosis", "齿轮order_peak_concentration",
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
    # 1. 设备列表（含离线判断）
    now = datetime.utcnow()
    devices = db.query(Device).all()
    device_list = []
    for d in devices:
        is_offline = not d.is_online
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
        is_offline = not d.is_online
        diag = db.query(Diagnosis).filter(Diagnosis.device_id == d.device_id) \
            .order_by(Diagnosis.analyzed_at.desc()).first()
        if diag:
            fault_probs = diag.fault_probabilities or {}
            # 将频率指示器（BPFO/BPFI/BSF）映射为标准中文故障名，合并同名概率
            mapped = {}
            for k, v in fault_probs.items():
                k_mapped = BEARING_FAULT_MAP.get(k, k)  # BPFO→外圈, BPFI→内圈, BSF→滚动体
                if k_mapped in VALID_FAULT_TYPES:
                    mapped[k_mapped] = max(mapped.get(k_mapped, 0), v)
            # 加上故障类型外的通用项
            if "正常运行" in fault_probs and "正常运行" not in mapped:
                mapped["正常运行"] = fault_probs["正常运行"]
            latest_diag[d.device_id] = {
                "health_score": diag.health_score,
                "fault_probabilities": mapped,
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
