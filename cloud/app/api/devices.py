"""
设备管理接口
提供设备列表查询、边端配置读写
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Device

router = APIRouter(prefix="/api/devices", tags=["设备管理"])


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
                "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
            }
            for d in devices
        ]
    }


# ========== 边端专用接口（必须放在 /{device_id}/config 之前）==========

@router.get("/edge/config")
def get_edge_config(device_id: str, db: Session = Depends(get_db)):
    """
    边端拉取配置接口（edge_client.py 调用）
    返回该设备的全部运行参数
    """
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    return {
        "code": 200,
        "data": {
            "device_id": device.device_id,
            "upload_interval": device.upload_interval or 10,
            "task_poll_interval": device.task_poll_interval or 5,
            "sample_rate": device.sample_rate or 25600,
            "window_seconds": device.window_seconds or 10,
            "channel_count": device.channel_count or 3,
        }
    }


@router.get("/{device_id}/config")
def get_device_config(device_id: str, db: Session = Depends(get_db)):
    """
    获取某设备的边端配置参数（前端调用）
    """
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    return {
        "code": 200,
        "data": {
            "device_id": device.device_id,
            "upload_interval": device.upload_interval,
            "task_poll_interval": device.task_poll_interval,
            "sample_rate": device.sample_rate,
            "window_seconds": device.window_seconds,
            "channel_count": device.channel_count,
            "channel_names": device.channel_names,
        }
    }


@router.put("/{device_id}/config")
def update_device_config(device_id: str, payload: dict, db: Session = Depends(get_db)):
    """
    更新某设备的边端配置参数（前端调用）

    可更新字段：
    - upload_interval: 自动采集上传间隔(秒)，建议 >= 5
    - task_poll_interval: 任务轮询间隔(秒)，建议 >= 3
    - sample_rate: 采样率 Hz
    - window_seconds: 采集窗口秒数
    - channel_count: 通道数
    """
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    # 更新允许的字段
    allowed_fields = [
        "upload_interval", "task_poll_interval",
        "sample_rate", "window_seconds", "channel_count", "channel_names"
    ]
    updated = {}
    for field in allowed_fields:
        if field in payload:
            value = payload[field]
            # 基础校验
            if field in ("upload_interval", "task_poll_interval") and value < 1:
                raise HTTPException(status_code=422, detail=f"{field} 必须 >= 1")
            if field in ("sample_rate", "window_seconds", "channel_count") and value < 1:
                raise HTTPException(status_code=422, detail=f"{field} 必须 >= 1")
            if field == "channel_names" and not isinstance(value, dict):
                raise HTTPException(status_code=422, detail="channel_names 必须为对象")
            setattr(device, field, value)
            updated[field] = value

    db.commit()

    return {
        "code": 200,
        "message": "配置已更新",
        "data": {
            "device_id": device.device_id,
            "updated": updated,
        }
    }


# ========== 告警阈值配置接口 ==========

@router.get("/{device_id}/alarm-thresholds")
def get_alarm_thresholds(device_id: str, db: Session = Depends(get_db)):
    """
    获取设备的告警阈值配置
    返回用户自定义配置 + 实际生效阈值（含默认值回退）
    """
    from app.services.alarm_service import DEFAULT_THRESHOLDS
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    user_cfg = device.alarm_thresholds or {}
    default_keys = ["rms", "peak", "kurtosis", "crest_factor"]

    # 计算实际生效的阈值（用户配置 + 默认值回退）
    effective = {}
    for key in default_keys:
        user_metric = user_cfg.get(key, {})
        default_metric = DEFAULT_THRESHOLDS.get(key, {})
        effective[key] = {
            "warning": user_metric.get("warning") if user_metric.get("warning") is not None else default_metric.get("warning"),
            "critical": user_metric.get("critical") if user_metric.get("critical") is not None else default_metric.get("critical"),
        }
        if key not in user_cfg:
            user_cfg[key] = {"warning": None, "critical": None}

    return {
        "code": 200,
        "data": {
            "device_id": device.device_id,
            "alarm_thresholds": user_cfg,
            "effective_thresholds": effective,
        }
    }


@router.put("/{device_id}/alarm-thresholds")
def update_alarm_thresholds(device_id: str, payload: dict, db: Session = Depends(get_db)):
    """
    更新设备的告警阈值配置

    请求体示例：
    {
        "rms": {"warning": 5.0, "critical": 10.0},
        "peak": {"warning": 15.0, "critical": 30.0},
        "kurtosis": {"warning": 4.0, "critical": 6.0},
        "crest_factor": {"warning": 6.0, "critical": 10.0}
    }
    """
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    new_thresholds = payload.get("alarm_thresholds", payload)
    if not isinstance(new_thresholds, dict):
        raise HTTPException(status_code=422, detail="阈值配置必须为对象")

    allowed_metrics = {"rms", "peak", "kurtosis", "crest_factor"}
    validated = {}

    for metric, levels in new_thresholds.items():
        if metric not in allowed_metrics:
            continue
        if not isinstance(levels, dict):
            continue
        warning = levels.get("warning")
        critical = levels.get("critical")

        # 校验：如果都填了，必须 warning < critical
        if warning is not None and critical is not None and warning >= critical:
            raise HTTPException(
                status_code=422,
                detail=f"{metric} 的预警阈值必须小于严重阈值"
            )
        validated[metric] = {
            "warning": float(warning) if warning is not None else None,
            "critical": float(critical) if critical is not None else None,
        }

    device.alarm_thresholds = validated
    db.commit()

    return {
        "code": 200,
        "message": "告警阈值已更新",
        "data": {
            "device_id": device.device_id,
            "alarm_thresholds": validated,
        }
    }
