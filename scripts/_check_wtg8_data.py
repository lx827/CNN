import sys, json
sys.path.insert(0, '/opt/CNN/cloud')
sys.path.insert(0, '/opt/CNN')
from app.database import SessionLocal
from app.models import SensorData, Device
import numpy as np

db = SessionLocal()

# 查设备
dev = db.query(Device).filter(Device.device_id == 'WTG-008').first()
print('WTG-008: sr={} ch_count={} bearing={} gear={}'.format(
    dev.sample_rate, dev.channel_count, dev.bearing_params, dev.gear_teeth))

# 查 batch=4 数据
recs = db.query(SensorData).filter(
    SensorData.device_id == 'WTG-008',
    SensorData.batch_index == 4
).all()
print('batch=4: {} records'.format(len(recs)))
for r in recs:
    d = r.data
    if isinstance(d, list):
        arr = np.array(d[:100] if len(d) > 100 else d)
        print('  ch{}: len={} dtype=list first5={}'.format(r.channel, len(d), arr[:5]))
    elif isinstance(d, bytes):
        print('  ch{}: len={} dtype=bytes'.format(r.channel, len(d)))
    elif isinstance(d, str):
        d2 = json.loads(d) if len(d) < 200 else None
        if d2:
            print('  ch{}: len={} dtype=str_json'.format(r.channel, len(d)))
        else:
            print('  ch{}: len={} dtype=str'.format(r.channel, len(d)))
    else:
        print('  ch{}: type={}'.format(r.channel, type(d)))
db.close()
