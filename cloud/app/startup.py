"""
启动初始化模块
负责数据库初始化和默认设备创建
"""
import logging
from datetime import datetime

from app.database import init_db, SessionLocal
from app.models import Device
from app.core.config import SENSOR_SAMPLE_RATE, SENSOR_WINDOW_SECONDS

logger = logging.getLogger(__name__)


def init_database():
    """初始化数据库表结构"""
    init_db()


def create_initial_devices():
    """
    插入默认设备（如果不存在）。

    注意：新设备默认不预填 bearing_params 和 gear_teeth，
    避免用户误以为已配置真实机械参数。
    当设备未配置机械参数时，诊断系统会自动触发"默认诊断逻辑"
    （使用内置默认参数执行诊断），详见 DIAGNOSIS_LOGIC.md。
    """
    db = SessionLocal()
    try:
        default_devices = [
            {
                "device_id": "WTG-001",
                "name": "风机齿轮箱 #01",
                "location": "某风电场 A 区 03 号机组",
                "health_score": 87,
                "status": "normal",
                "runtime_hours": 3456,
            },
            {
                "device_id": "WTG-002",
                "name": "风机齿轮箱 #02",
                "location": "某风电场 A 区 04 号机组",
                "health_score": 92,
                "status": "normal",
                "runtime_hours": 2890,
            },
            {
                "device_id": "WTG-003",
                "name": "风机齿轮箱 #03",
                "location": "某风电场 A 区 05 号机组",
                "health_score": 65,
                "status": "warning",
                "runtime_hours": 4102,
            },
            {
                "device_id": "WTG-004",
                "name": "风机齿轮箱 #04",
                "location": "某风电场 B 区 01 号机组",
                "health_score": 78,
                "status": "normal",
                "runtime_hours": 1567,
            },
            {
                "device_id": "WTG-005",
                "name": "风机齿轮箱 #05",
                "location": "某风电场 B 区 02 号机组",
                "health_score": 45,
                "status": "fault",
                "runtime_hours": 5234,
            },
        ]

        for dev_info in default_devices:
            existing = db.query(Device).filter(Device.device_id == dev_info["device_id"]).first()
            if not existing:
                device = Device(
                    device_id=dev_info["device_id"],
                    name=dev_info["name"],
                    location=dev_info["location"],
                    channel_count=3,
                    channel_names={"1": "轴承附近", "2": "驱动端", "3": "风扇端"},
                    sample_rate=SENSOR_SAMPLE_RATE,
                    window_seconds=SENSOR_WINDOW_SECONDS,
                    health_score=dev_info["health_score"],
                    status=dev_info["status"],
                    runtime_hours=dev_info["runtime_hours"],
                    upload_interval=10,
                    task_poll_interval=5,
                    alarm_thresholds={},
                    compression_enabled=1,
                    downsample_ratio=8,
                    is_online=1,
                    last_seen_at=datetime.utcnow(),
                )
                db.add(device)
                logger.info(
                    f"[启动] 创建设备: {dev_info['device_id']} "
                    f"(健康度 {dev_info['health_score']}, 状态 {dev_info['status']})"
                )
            else:
                # 给已有设备补齐缺失的非机械参数字段
                updated = False
                if not existing.alarm_thresholds:
                    existing.alarm_thresholds = {}
                    updated = True
                if not existing.channel_names:
                    existing.channel_names = {"1": "轴承附近", "2": "驱动端", "3": "风扇端"}
                    updated = True
                if existing.compression_enabled is None:
                    existing.compression_enabled = 1
                    updated = True
                if existing.downsample_ratio is None:
                    existing.downsample_ratio = 8
                    updated = True
                if existing.is_online is None:
                    existing.is_online = 1
                    updated = True
                if updated:
                    logger.info(f"[启动] 为已有设备 {dev_info['device_id']} 补齐默认配置")

        db.commit()
    finally:
        db.close()
