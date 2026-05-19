"""运行 analyze_device 并展示每通道详情"""
import sys, json
sys.path.insert(0, '/opt/CNN/cloud')
sys.path.insert(0, '/opt/CNN')
import numpy as np
from app.database import SessionLocal
from app.models import SensorData, Device
from app.services.analyzer import analyze_device

db = SessionLocal()
dev = db.query(Device).filter(Device.device_id == 'WTG-008').first()
recs = db.query(SensorData).filter(
    SensorData.device_id == 'WTG-008', SensorData.batch_index == 4
).all()

channels = {}
for r in recs:
    channels[f"ch{r.channel}"] = r.data
sr = recs[0].sample_rate or dev.sample_rate or 25600

print(f'WTG-008: sr={sr}, bearing={dev.bearing_params}, gear={dev.gear_teeth}')
print(f'channels={len(channels)}, samples={[len(v) for v in channels.values()]}')
print()

# 只查每通道基础的 run_research_ensemble
from app.services.diagnosis.ensemble import run_research_ensemble
from app.services.diagnosis.features import has_bearing_params, has_gear_params

for ch_name, sig in channels.items():
    sig_arr = np.array(sig, dtype=np.float64)
    print(f'--- {ch_name} ---')
    
    bp = dev.bearing_params or {}
    gt = dev.gear_teeth or {}
    hb = has_bearing_params(bp)
    hg = has_gear_params(gt)
    print(f'  has_bearing={hb}, has_gear={hg}')
    
    r = run_research_ensemble(sig_arr, sr, bearing_params=bp, gear_teeth=gt, max_seconds=5.0)
    print(f'  hs={r.get("health_score")} status={r.get("status")}')
    tf = r.get('time_features', {})
    print(f'  kurt={tf.get("kurtosis")}, crest={tf.get("crest_factor")}')
    
    ens = r.get('ensemble', {})
    print(f'  bearing_conf={ens.get("bearing_confidence")}, gear_conf={ens.get("gear_confidence")}, time_conf={ens.get("time_confidence")}')
    print(f'  skip_bearing={ens.get("skip_bearing")}, skip_gear={ens.get("skip_gear")}')
    
    gear = r.get('gear', {})
    inds = gear.get('fault_indicators', {})
    for k, v in inds.items():
        if isinstance(v, dict):
            w = v.get('warning'); c = v.get('critical')
            if w or c:
                print(f'  !! {k}: val={v.get("value")}, w={w}, c={c}')

db.close()
