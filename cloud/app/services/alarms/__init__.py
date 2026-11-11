"""告警只消费统一诊断结论，不对原始指标另套第二份阈值。"""

from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from app.models import Alarm, Device
from app.core.thresholds import ALARM_THRESHOLDS

DEFAULT_THRESHOLDS = ALARM_THRESHOLDS


def _get_threshold(device: Device, metric: str, level: str) -> float:
    """读取设备的阈值配置，未配置则使用默认值；显式置空(null)则禁用该级别告警"""
    thresholds = device.alarm_thresholds or {}
    metric_cfg = thresholds.get(metric)
    if metric_cfg is not None:
        val = metric_cfg.get(level)
        if val is not None:
            return val
        # 用户配置了该指标但此级别为 null，返回极大值（不触发此级别告警）
        return 99999
    return ALARM_THRESHOLDS.get(metric, {}).get(level, 99999)


def _has_recent_unresolved_alarm(
    db: Session,
    device_id: str,
    category: str,
    level: str,
    channel: int = None,
    hours: int = 1,
) -> bool:
    """
    检查该设备最近 hours 小时内是否已有同类未处理告警。
    通道级告警用 device_id + channel + category + level 去重。
    设备级告警用 device_id + category + level 去重。
    """
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    query = db.query(Alarm).filter(
        Alarm.device_id == device_id,
        Alarm.category == category,
        Alarm.level == level,
        Alarm.is_resolved == 0,
        Alarm.created_at >= since,
    )
    if channel is not None:
        query = query.filter(Alarm.channel == channel)
    else:
        query = query.filter(Alarm.channel.is_(None))
    return query.first() is not None


def generate_alarms(db, device_id, diagnosis, *, batch_index=None):
    from app.services.diagnosis_store import validate_payload

    validate_payload(diagnosis)
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if device is None or device.is_online == 0:
        return []
    results = [(None, diagnosis)] + [
        (int(key.removeprefix("ch")), value)
        for key, value in diagnosis.get("channels", {}).items()
    ]
    alarms = []
    for channel, result in results:
        validate_payload(result)
        if result.get("evaluation_status") != "evaluated" or result.get(
            "diagnosis_conclusion"
        ) not in {"warning", "fault"}:
            continue
        level = "critical" if result["diagnosis_conclusion"] == "fault" else "warning"
        category = "设备诊断" if channel is None else "通道诊断"
        if _has_recent_unresolved_alarm(db, device_id, category, level, channel):
            continue
        channel_name = (
            (device.channel_names or {}).get(str(channel), f"通道{channel}")
            if channel is not None
            else device.name
        )
        alarm = Alarm(
            device_id=device_id,
            level=level,
            category=category,
            channel=channel,
            channel_name=channel_name,
            batch_index=batch_index,
            title=f"{channel_name}诊断{'故障' if level == 'critical' else '预警'}",
            description=f"评估结论：{result['diagnosis_conclusion']}；覆盖：{result.get('coverage', 'unknown')}。原始指标不单独重新触发告警。",
            suggestion=result["recommendation"],
        )
        db.add(alarm)
        alarms.append(alarm)
    return alarms
