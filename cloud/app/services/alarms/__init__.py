"""
告警生成服务包
统一导出 generate_alarms 入口和公共工具函数
"""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from app.models import Alarm, Device
from app.core.websocket import manager
from app.core.thresholds import ALARM_THRESHOLDS
from app.services.offline_guard import is_device_offline

logger = logging.getLogger(__name__)

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
    db: Session, device_id: str, category: str, level: str, channel: int = None, hours: int = 1
) -> bool:
    """
    检查该设备最近 hours 小时内是否已有同类未处理告警。
    通道级告警用 device_id + channel + category + level 去重。
    设备级告警用 device_id + category + level 去重。
    """
    since = datetime.utcnow() - timedelta(hours=hours)
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


def generate_alarms(
    db: Session,
    device_id: str,
    health_score: int,
    fault_probabilities: dict,
    channel_features: dict = None,
    batch_index: int = None,
    order_analysis: dict = None,
    channel_diagnosis: dict = None,
):
    """
    综合告警生成入口

    参数：
      device_id: 设备ID
      health_score: 健康度
      fault_probabilities: 故障概率字典
      channel_features: 通道级特征，格式 {ch_name: {rms:..., peak:..., ...}}
      batch_index: 关联的数据批次号
      order_analysis: 阶次分析结果
      channel_diagnosis: 通道级诊断结果，格式 {ch_name: {gear: {...}, bearing: {...}}}
    """
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        return []

    # 离线设备禁止产生新的监测告警，避免旧数据触发异常告警
    if is_device_offline(device):
        return []

    new_alarms = []

    # 1. 通道级振动特征阈值告警
    if channel_features:
        from .channel import _check_feature_alarms
        channel_names = device.channel_names or {}
        for ch_key, features in channel_features.items():
            # ch_key 可能是 "ch1", "ch2"...
            ch_num = int(ch_key.replace("ch", "")) if ch_key.startswith("ch") else 1
            ch_name = channel_names.get(str(ch_num), f"通道{ch_num}")
            alarms = _check_feature_alarms(db, device, ch_num, ch_name, features, batch_index)
            new_alarms.extend(alarms)

    # 2. 通道级齿轮诊断告警
    if channel_diagnosis:
        from .channel import _check_gear_alarms
        gear_alarms = _check_gear_alarms(db, device, channel_diagnosis, batch_index)
        new_alarms.extend(gear_alarms)

    # 3. 设备级综合健康度告警
    from .device import _check_device_alarms
    device_alarms = _check_device_alarms(
        db, device, health_score, fault_probabilities, batch_index, order_analysis
    )
    new_alarms.extend(device_alarms)

    # 4. 诊断结果（故障概率）告警
    from .diagnosis import _check_diagnosis_alarms
    diag_alarms = _check_diagnosis_alarms(db, device, fault_probabilities, batch_index)
    new_alarms.extend(diag_alarms)

    if new_alarms:
        db.commit()
        # WebSocket 推送
        for alarm in new_alarms:
            msg = {
                "type": "new_alarm",
                "data": {
                    "id": alarm.id,
                    "title": alarm.title,
                    "level": alarm.level,
                    "channel": alarm.channel,
                    "channel_name": alarm.channel_name,
                    "created_at": alarm.created_at.isoformat() if alarm.created_at else None,
                }
            }
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(manager.broadcast(msg))
            except Exception:
                pass

    return new_alarms
