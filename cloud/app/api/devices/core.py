"""
设备 CRUD 接口
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Device

router = APIRouter()


@router.get("/")
def get_devices(db: Session = Depends(get_db)):
    """
    获取所有设备列表
    """
    devices = db.query(Device).all()
    return {
        "code": 200,
        "data": [
            {
                "id": d.id,
                "device_id": d.device_id,
                "name": d.name,
                "location": d.location,
                "channel_count": d.channel_count,
                "channel_names": d.channel_names,
                "sample_rate": d.sample_rate,
                "window_seconds": d.window_seconds,
                "health_score": d.health_score,
                "status": d.status,
                "runtime_hours": d.runtime_hours,
                "upload_interval": d.upload_interval,
                "task_poll_interval": d.task_poll_interval,
                "alarm_thresholds": d.alarm_thresholds,
                "gear_teeth": d.gear_teeth,
                "bearing_params": d.bearing_params,
                "compression_enabled": d.compression_enabled,
                "downsample_ratio": d.downsample_ratio,
                "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
            }
            for d in devices
        ]
    }
