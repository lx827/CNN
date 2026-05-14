"""
设备离线监测器（独立子系统）

职责：
  - 定时扫描所有设备，根据 last_seen_at 动态更新数据库中的 is_online 字段
  - 设备状态变化（上线/下线）时通过 WebSocket 广播通知
  - 设备离线时自动清理待分析批次标记，防止恢复后旧数据触发异常监测

设计原则：
  - 完全独立：不依赖任何业务接口，不暴露判断函数给其他模块
  - 自包含：所有离线相关的维护逻辑都在此文件中
  - 低耦合：其他模块通过 device.is_online 字段感知状态，禁止调用此模块的任何函数
  - 防误改：此模块是 is_online 字段的唯一写者，其他模块只能读取

使用约束（重要）：
  - 禁止在任何业务模块中 import 本模块的函数
  - 需要标记设备上线时，直接设置 device.is_online = 1
  - 需要判断设备是否离线时，直接读取 device.is_online
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from app.database import SessionLocal
from app.models import Device
from app.core.websocket import manager

logger = logging.getLogger(__name__)

DEFAULT_OFFLINE_MIN_SECONDS = 300  # 默认 5 分钟
OFFLINE_CHECK_INTERVAL_SECONDS = 30  # 每 30 秒扫描一次


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


def _is_device_offline(device: Optional[Device], now: Optional[datetime] = None) -> bool:
    """
    判断设备是否离线（仅供本模块内部使用）。

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


async def offline_monitor_worker():
    """
    后台协程：定时扫描所有设备，更新 is_online 字段。

    启动位置：lifespan.py（与 analysis_worker 并列）
    """
    while True:
        try:
            await asyncio.sleep(OFFLINE_CHECK_INTERVAL_SECONDS)

            db = SessionLocal()
            try:
                now = datetime.utcnow()
                devices = db.query(Device).all()

                online_count = sum(1 for d in devices if d.is_online)
                offline_count = len(devices) - online_count
                logger.info(f"[离线监测] 扫描完成: {online_count} 在线, {offline_count} 离线")

                for device in devices:
                    was_online = bool(device.is_online)
                    is_now_offline = _is_device_offline(device, now)
                    is_now_online = not is_now_offline

                    if was_online and is_now_offline:
                        # 设备刚离线：更新数据库
                        device.is_online = 0
                        logger.info(f"[离线监测] {device.device_id} 已离线，last_seen={device.last_seen_at}")

                        # WebSocket 广播离线通知
                        try:
                            await manager.broadcast({
                                "type": "device_offline",
                                "data": {
                                    "device_id": device.device_id,
                                    "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
                                }
                            })
                        except Exception:
                            pass

                    elif not was_online and is_now_online:
                        # 设备刚上线：更新数据库
                        device.is_online = 1
                        logger.info(f"[离线监测] {device.device_id} 已恢复在线")

                        # WebSocket 广播上线通知
                        try:
                            await manager.broadcast({
                                "type": "device_online",
                                "data": {
                                    "device_id": device.device_id,
                                }
                            })
                        except Exception:
                            pass

                db.commit()

            except Exception as e:
                logger.error(f"[离线监测] 扫描异常: {e}", exc_info=True)
            finally:
                db.close()

        except asyncio.CancelledError:
            logger.info("[离线监测] 协程已取消")
            break
        except Exception as e:
            logger.error(f"[离线监测] 严重异常: {e}", exc_info=True)
