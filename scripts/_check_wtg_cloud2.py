"""排查 WTG 健康诊断 hs 偏低原因"""
import sys, json
sys.path.insert(0, '/opt/CNN')
sys.path.insert(0, '/opt/CNN/cloud')
from app.database import SessionLocal
from app.models import Diagnosis, Device

db = SessionLocal()

# 查设备配置
devs = db.query(Device).filter(Device.device_id.like('WTG%')).all()
for dev in devs:
    bp = dev.bearing_params or {}
    gt = dev.gear_teeth or {}
    print(f'设备 {dev.device_id}: bearing={bp}, gear={gt}')

# 查最新诊断详情
diag = db.query(Diagnosis).filter(
    Diagnosis.device_id == 'WTG-008',
    Diagnosis.batch_index == 4, 
    Diagnosis.channel == 0
).first()

if diag:
    er = diag.engine_result
    if er:
        erd = json.loads(er) if isinstance(er, str) else er
        tf = erd.get('time_features', {})
        print(f'\nWTG-008 batch=4 详情:')
        print(f'  health_score={diag.health_score} status={diag.status}')
        print(f'  kurtosis={tf.get("kurtosis")} crest={tf.get("crest_factor")}')
        print(f'  rms={tf.get("rms")} rms_mad_z={tf.get("rms_mad_z")}')
        
        ens = erd.get('ensemble', {})
        ds = ens.get('ds_fusion', {})
        print(f'  bearing_conf={ens.get("bearing_confidence")} gear_conf={ens.get("gear_confidence")}')
        print(f'  fault_label={erd.get("fault_label")}')
        print(f'  has_bearing={ens.get("has_bearing_params")} has_gear={ens.get("has_gear_params")}')
        print(f'  skip_bearing={ens.get("skip_bearing")} skip_gear={ens.get("skip_gear")}')
        
        # ds_fusion details
        if isinstance(ds, dict):
            print(f'  ds_dominant={ds.get("dominant_fault")} ds_conflict={ds.get("conflict")}')
        
        # 看所有 gear indicators
        gear = erd.get('gear', {})
        inds = gear.get('fault_indicators', {})
        print(f'  gear_indicators ({len(inds)}):')
        for k, v in inds.items():
            if isinstance(v, dict):
                w = v.get('warning', False)
                c = v.get('critical', False)
                val = v.get('value', '-')
                tag = '⚠' if w or c else ' '
                print(f'    [{tag}] {k}: {val}')

db.close()
