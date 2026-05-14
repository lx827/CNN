from app.database import SessionLocal
from app.models import Device
from app.services.offline_monitor import _is_device_offline, _get_offline_threshold
from datetime import datetime

db = SessionLocal()
now = datetime.utcnow()
print(f"now = {now}")

for device in db.query(Device).all():
    last_seen = device.last_seen_at
    threshold = _get_offline_threshold(device, now)
    is_offline = _is_device_offline(device, now)
    print(f"{device.device_id}: last_seen={last_seen}, threshold={threshold}, is_offline={is_offline}")
    print(f"  upload_interval={device.upload_interval}, task_poll_interval={device.task_poll_interval}")

db.close()