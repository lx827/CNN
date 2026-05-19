import sys, json, traceback
sys.path.insert(0, '/opt/CNN/cloud')
sys.path.insert(0, '/opt/CNN')
import numpy as np
from app.database import SessionLocal
from app.models import SensorData, Device
from app.services.analyzer import analyze_device

db = SessionLocal()

# 查设备
dev = db.query(Device).filter(Device.device_id == 'WTG-008').first()
recs = db.query(SensorData).filter(
    SensorData.device_id == 'WTG-008', SensorData.batch_index == 4
).all()

channels = {}
for r in recs:
    channels[f"ch{r.channel}"] = r.data
sr = recs[0].sample_rate or dev.sample_rate or 25600

print('analyzing WTG-008 batch=4 with sr={}...'.format(sr))
try:
    result = analyze_device(channels, sr, dev, rot_freq=None)
    print('hs={} status={}'.format(result.get('health_score'), result.get('status')))
    tf = result.get('time_features', {})
    print('kurt={} crest={} rms_mad_z={}'.format(tf.get('kurtosis'), tf.get('crest_factor'), tf.get('rms_mad_z')))
    
    ens = result.get('ensemble', {})
    print('bearing_conf={} gear_conf={} time_conf={}'.format(
        ens.get('bearing_confidence'), ens.get('gear_confidence'), ens.get('time_confidence')))
    print('skip_bearing={} skip_gear={} has_bearing={} has_gear={}'.format(
        ens.get('skip_bearing'), ens.get('skip_gear'), ens.get('has_bearing_params'), ens.get('has_gear_params')))
    
    gear = result.get('gear', {})
    inds = gear.get('fault_indicators', {})
    print('gear indicators:')
    for k, v in inds.items():
        if isinstance(v, dict):
            w = v.get('warning', False)
            c = v.get('critical', False)
            tag = '!!' if w or c else '  '
            print('  [{}] {}: val={}'.format(tag, k, v.get('value')))
except Exception as e:
    traceback.print_exc()

db.close()
