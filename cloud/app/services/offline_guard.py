"""
设备离线守卫模块 (Offline Guard)

职责：
  提供统一、独立的设备离线状态判断。所有与“设备是否离线”相关的判断
  必须走此模块，禁止在其他地方内联实现离线逻辑。

设计原则：
  - 零业务依赖：不导入分析、告警、诊断等任何业务服务。
  - 单一职责：只回答“设备当前是否离线”。
  - 防篡改：接口极简（一个函数），后续修改其他功能时极难误伤。

使用位置（守卫入口）：
  - lifespan.py    : 后台分析 worker 跳过离线设备
  - alarms/__init__: 禁止为离线设备生成新告警
  - diagnosis_ops  : 禁止对离线设备执行重新诊断
  - dashboard.py   : 设备总览离线状态渲染
"""
from datetime import datetime, timedelta
from typing import Optional

from app.models import Device

DEFAULT_OFFLINE_MIN_SECONDS = 300  # 默认 5 分钟


def _get_offline_threshold(device: Device, now: datetime) -> datetime:
    """
    根据设备通信间隔计算离线阈值。
    以任务轮询间隔（实际心跳）为主，以上传间隔为辅，最少 5 分钟。
    """
    base_seconds = DEFAULT_OFFLINE_MIN_SECONDS
    if device.task_poll_interval and device.task_poll_interval > 0:
        base_seconds = max(base_seconds, device.task_poll_interval * 3 + 60)
    if device.upload_interval and device.upload_interval > 0:
        base_seconds = max(base_seconds, device.upload_interval * 2 + 60)
    return now - timedelta(seconds=base_seconds)


def is_device_offline(device: Optional[Device], now: Optional[datetime] = None) -> bool:
    """
    判断设备是否离线。

    参数:
        device: Device 模型实例；None 视为离线。
        now:    可选的当前时间，默认 utcnow()。

    返回:
        True  = 离线（从未上线 或 超过阈值未通信）
        False = 在线
    """
    if device is None:
        return True

    last_seen = device.last_seen_at
    if last_seen is None:
        return True

    # 去除时区，确保与 naive datetime 安全比较
    if last_seen.tzinfo is not None:
        last_seen = last_seen.replace(tzinfo=None)

    threshold = _get_offline_threshold(device, now or datetime.utcnow())
    return last_seen < threshold
