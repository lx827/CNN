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


# 机械参数常量
CW_BEARING_PARAMS = {"n": 9, "d": 7.94, "D": 39.04, "alpha": 0}
WTGEAR_GEAR_TEETH = {"sun": 28, "ring": 100, "planet": 36, "planet_count": 4, "input": 28}
MIXED_BEARING_PARAMS = {"n": 9, "d": 7.94, "D": 39.04, "alpha": 0}
MIXED_GEAR_TEETH = {"sun": 28, "ring": 100, "planet": 36, "planet_count": 4, "input": 28}


def create_initial_devices():
    """
    插入默认设备（如果不存在）。

    设备分配方案（与边端模拟对应）：
      WTG-001: CW 轴承健康 (H)      — 仅配置轴承参数（6205-2RS）
      WTG-002: CW 轴承内圈故障 (I)   — 仅配置轴承参数
      WTG-003: CW 轴承外圈故障 (O)   — 仅配置轴承参数
      WTG-004: WTgearbox 断齿 (Br)         — 仅配置齿轮参数（行星齿轮箱）
      WTG-005: WTgearbox 缺齿 (Mi)         — 仅配置齿轮参数
      WTG-006: WTgearbox 齿根裂纹 (Rc)     — 仅配置齿轮参数
      WTG-007: WTgearbox 磨损 (We)         — 仅配置齿轮参数
      WTG-008: WTgearbox 健康 (He)          — 仅配置齿轮参数
      WTG-009: 混合（轴承+齿轮故障通道）   — 配置轴承+齿轮参数
      WTG-010: 离线模拟（不上传）         — 无机械参数

    注意：新设备默认不预填 bearing_params 和 gear_teeth，
    避免用户误以为已配置真实机械参数。
    当设备未配置机械参数时，诊断系统只使用统计指标判断是否异常，
    不再注入默认轴承型号或默认齿轮齿数。
    """
    db = SessionLocal()
    try:
        # 10 台设备：3 台 CW 轴承（仅轴承参数）+ 5 台 WTgearbox 齿轮（仅齿轮参数）+ 1 台混合 + 1 台离线
        default_devices = [
            # --- CW 轴承数据集设备（仅配置轴承参数，无齿轮参数）---
            {
                "device_id": "WTG-001",
                "name": "CW轴承-健康",
                "location": "CW数据集 · 恒速/变速工况 · 健康轴承",
                "health_score": 87,
                "status": "normal",
                "runtime_hours": 3456,
                "channel_count": 3,
                "bearing_params": CW_BEARING_PARAMS,
                "gear_teeth": None,  # 仅轴承诊断
            },
            {
                "device_id": "WTG-002",
                "name": "CW轴承-内圈故障",
                "location": "CW数据集 · 变速工况 · 内圈故障轴承",
                "health_score": 50,
                "status": "fault",
                "runtime_hours": 2890,
                "channel_count": 3,
                "bearing_params": CW_BEARING_PARAMS,
                "gear_teeth": None,  # 仅轴承诊断
            },
            {
                "device_id": "WTG-003",
                "name": "CW轴承-外圈故障",
                "location": "CW数据集 · 恒速/变速工况 · 外圈故障轴承",
                "health_score": 50,
                "status": "fault",
                "runtime_hours": 4102,
                "channel_count": 3,
                "bearing_params": CW_BEARING_PARAMS,
                "gear_teeth": None,  # 仅轴承诊断
            },
            # --- WTgearbox 齿轮箱数据集设备（仅配置齿轮参数，无轴承参数）---
            {
                "device_id": "WTG-004",
                "name": "WTgear-断齿",
                "location": "WTgearbox数据集 · 恒速工况 · 齿轮断齿故障",
                "health_score": 45,
                "status": "fault",
                "runtime_hours": 1567,
                "channel_count": 2,
                "bearing_params": None,  # 仅齿轮诊断
                "gear_teeth": WTGEAR_GEAR_TEETH,
            },
            {
                "device_id": "WTG-005",
                "name": "WTgear-缺齿",
                "location": "WTgearbox数据集 · 恒速工况 · 齿轮缺齿故障",
                "health_score": 45,
                "status": "fault",
                "runtime_hours": 2000,
                "channel_count": 2,
                "bearing_params": None,  # 仅齿轮诊断
                "gear_teeth": WTGEAR_GEAR_TEETH,
            },
            {
                "device_id": "WTG-006",
                "name": "WTgear-齿根裂纹",
                "location": "WTgearbox数据集 · 恒速工况 · 齿轮齿根裂纹",
                "health_score": 55,
                "status": "warning",
                "runtime_hours": 3000,
                "channel_count": 2,
                "bearing_params": None,  # 仅齿轮诊断
                "gear_teeth": WTGEAR_GEAR_TEETH,
            },
            {
                "device_id": "WTG-007",
                "name": "WTgear-磨损",
                "location": "WTgearbox数据集 · 恒速工况 · 齿轮磨损故障",
                "health_score": 60,
                "status": "warning",
                "runtime_hours": 4000,
                "channel_count": 2,
                "bearing_params": None,  # 仅齿轮诊断
                "gear_teeth": WTGEAR_GEAR_TEETH,
            },
            {
                "device_id": "WTG-008",
                "name": "WTgear-健康",
                "location": "WTgearbox数据集 · 恒速工况 · 健康齿轮箱",
                "health_score": 87,
                "status": "normal",
                "runtime_hours": 5000,
                "channel_count": 2,
                "bearing_params": None,  # 仅齿轮诊断
                "gear_teeth": WTGEAR_GEAR_TEETH,
            },
            # --- 混合设备（轴承 + 齿轮参数）---
            {
                "device_id": "WTG-009",
                "name": "混合-轴承+齿轮",
                "location": "混合数据 · 轴承故障通道 + 齿轮故障通道",
                "health_score": 60,
                "status": "warning",
                "runtime_hours": 6000,
                "channel_count": 3,
                "bearing_params": MIXED_BEARING_PARAMS,
                "gear_teeth": MIXED_GEAR_TEETH,
            },
            # --- 离线模拟设备（不上传数据）---
            {
                "device_id": "WTG-010",
                "name": "离线模拟",
                "location": "模拟离线 · 不上传数据 · 仅用于离线检测验证",
                "health_score": 87,
                "status": "normal",
                "runtime_hours": 100,
                "channel_count": 3,
                "bearing_params": None,  # 无参数 → 统计指标
                "gear_teeth": None,
            },
        ]

        for dev_info in default_devices:
            existing = db.query(Device).filter(Device.device_id == dev_info["device_id"]).first()
            if not existing:
                ch_count = dev_info.get("channel_count", 3)
                channel_names = (
                    {"1": "轴承附近", "2": "驱动端"}
                    if ch_count == 2 else
                    {"1": "轴承附近", "2": "驱动端", "3": "风扇端"}
                )
                device = Device(
                    device_id=dev_info["device_id"],
                    name=dev_info["name"],
                    location=dev_info["location"],
                    channel_count=ch_count,
                    channel_names=channel_names,
                    sample_rate=SENSOR_SAMPLE_RATE,
                    window_seconds=SENSOR_WINDOW_SECONDS,
                    health_score=dev_info["health_score"],
                    status=dev_info["status"],
                    runtime_hours=dev_info.get("runtime_hours", 0),
                    upload_interval=10,
                    task_poll_interval=5,
                    alarm_thresholds={},
                    compression_enabled=1,
                    downsample_ratio=8,
                    bearing_params=dev_info.get("bearing_params"),
                    gear_teeth=dev_info.get("gear_teeth"),
                    # 离线设备初始设为离线，其余设为在线
                    is_online=0 if dev_info["device_id"] == "WTG-010" else 1,
                    last_seen_at=None if dev_info["device_id"] == "WTG-010" else datetime.utcnow(),
                )
                db.add(device)
                bp_str = "有轴承参数" if dev_info.get("bearing_params") else "无轴承参数"
                gt_str = "有齿轮参数" if dev_info.get("gear_teeth") else "无齿轮参数"
                logger.info(
                    f"[启动] 创建设备: {dev_info['device_id']} "
                    f"(健康度 {dev_info['health_score']}, 状态 {dev_info['status']}, "
                    f"{bp_str}, {gt_str})"
                )
            else:
                # 给已有设备补齐缺失的非机械参数字段
                updated = False
                if not existing.alarm_thresholds:
                    existing.alarm_thresholds = {}
                    updated = True
                if not existing.channel_names:
                    ch_count = existing.channel_count or 3
                    existing.channel_names = (
                        {"1": "轴承附近", "2": "驱动端"}
                        if ch_count == 2 else
                        {"1": "轴承附近", "2": "驱动端", "3": "风扇端"}
                    )
                    updated = True
                if existing.compression_enabled is None:
                    existing.compression_enabled = 1
                    updated = True
                if existing.downsample_ratio is None:
                    existing.downsample_ratio = 8
                    updated = True
                # 不再在启动时强制设 is_online=1
                # 离线监测是 is_online 的唯一写者，启动初始化不应覆盖其判断
                if updated:
                    logger.info(f"[启动] 为已有设备 {dev_info['device_id']} 补齐默认配置")

        db.commit()
    finally:
        db.close()