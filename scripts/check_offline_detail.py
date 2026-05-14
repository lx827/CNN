"""检查设备在线状态和离线阈值"""
from app.database import SessionLocal
from app.models import Device
from app.services.offline_monitor import _get_offline_threshold, _is_device_offline
from datetime import datetime

db = SessionLocal()
now = datetime.utcnow()
print(f"当前UTC时间: {now}")
print(f"\n{'设备':<10} {'在线':<6} {'last_seen':<28} {'离线秒数':<12} {'upload_int':<12} {'阈值秒数':<10} {'应离线':<8}")

for d in db.query(Device).all():
    diff = (now - d.last_seen_at).total_seconds() if d.last_seen_at else None
    threshold = _get_offline_threshold(d, now)
    should_offline = _is_device_offline(d, now)
    print(f"{d.device_id:<10} {d.is_online:<6} {str(d.last_seen_at):<28} {str(diff):<12} {d.upload_interval:<12} {threshold:<10} {should_offline:<8}")

db.close()