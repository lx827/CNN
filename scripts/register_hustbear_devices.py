"""在云端现有数据库中一次性注册五台 HUSTbear 设备；不覆盖已有设备。"""
import os
from pathlib import Path
import sys


SPECS = [
    ("HUST-001", "健康"), ("HUST-002", "球故障"),
    ("HUST-003", "内圈故障"), ("HUST-004", "外圈故障"),
    ("HUST-005", "复合故障"),
]
PARAMS = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}


def register_devices(db):
    """事务内仅新增缺失设备；已有同编号配置不一致则回滚，禁止覆盖。"""
    from app.models import Device
    created = []
    try:
        for dev, label in SPECS:
            existing = db.query(Device).filter(Device.device_id == dev).first()
            if existing:
                if (existing.bearing_params != PARAMS or existing.gear_teeth
                        or existing.channel_names != {"1": "X", "2": "Y", "3": "Z"}
                        or existing.sample_rate != 8192 or existing.channel_count != 3
                        or existing.name != f"HUSTbear轴承-{label}"):
                    raise ValueError(f"{dev} 已存在且配置不同，未覆盖，请人工核对")
                continue
            db.add(Device(
                device_id=dev, name=f"HUSTbear轴承-{label}",
                location="HUSTbear 数据集回放（非现场硬件）", channel_count=3,
                channel_names={"1": "X", "2": "Y", "3": "Z"},
                sample_rate=8192, window_seconds=5, bearing_params=PARAMS.copy(),
                gear_teeth=None, is_online=0, last_seen_at=None,
                # 维持现有演示配置的采集节奏，不引入持续高频分析负载。
                upload_interval=108000, task_poll_interval=5,
                compression_enabled=1, downsample_ratio=8,
            ))
            created.append(dev)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return created


if __name__ == "__main__":
    # 跟随后端的 .env 与连接方式；无需写死 SQLite 路径，兼容既有 MySQL 配置。
    cloud = Path(os.environ["CNN_CLOUD_DIR"]) if os.environ.get("CNN_CLOUD_DIR") else Path(__file__).resolve().parents[1] / "cloud"
    os.chdir(cloud)
    sys.path.insert(0, str(cloud))
    from app.database import SessionLocal
    with SessionLocal() as session:
        created = register_devices(session)
    print(f"注册完成，新增 {len(created)} 台设备: {', '.join(created) or '无（已存在）'}")
