import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('/opt/CNN/cloud/turbine.db')
now = datetime.utcnow()
print(f"now = {now}")

rows = conn.execute('SELECT device_id, is_online, last_seen_at, upload_interval, task_poll_interval FROM devices').fetchall()
for r in rows:
    device_id, is_online, last_seen_str, upload_interval, task_poll_interval = r
    last_seen = datetime.strptime(last_seen_str, "%Y-%m-%d %H:%M:%S.%f") if last_seen_str else None
    
    # 计算阈值
    base_seconds = 300  # 5 min
    if task_poll_interval and task_poll_interval > 0:
        base_seconds = max(base_seconds, task_poll_interval * 3 + 60)
    if upload_interval and upload_interval > 0:
        base_seconds = max(base_seconds, upload_interval * 2 + 60)
    threshold = now - timedelta(seconds=base_seconds)
    
    is_offline = last_seen is None or last_seen < threshold
    print(f"{device_id}: last_seen={last_seen}, threshold={threshold}, is_offline={is_offline}, base_seconds={base_seconds}")
    print(f"  upload_interval={upload_interval}, task_poll_interval={task_poll_interval}")
    if last_seen:
        delta = now - last_seen
        print(f"  delta = {delta.total_seconds()} seconds ({delta.total_seconds()/3600:.1f} hours)")

conn.close()