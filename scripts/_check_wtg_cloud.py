"""排查 WTG 健康诊断报黄原因"""
import sys, json
sys.path.insert(0, '/opt/CNN')
sys.path.insert(0, '/opt/CNN/cloud')
from app.database import SessionLocal
from app.models import Diagnosis

db = SessionLocal()
diags = db.query(Diagnosis).filter(
    Diagnosis.device_id.like('WTG%')
).order_by(Diagnosis.analyzed_at.desc()).limit(5).all()

for d in diags:
    print(f'device={d.device_id} batch={d.batch_index} ch={d.channel} hs={d.health_score} status={d.status}')
    er = d.engine_result
    if er:
        erd = json.loads(er) if isinstance(er, str) else er
        # 看 gear indicators 中哪些 warning
        gear = erd.get('gear', {})
        inds = gear.get('fault_indicators', {})
        any_warn = False
        for k, v in inds.items():
            if isinstance(v, dict) and (v.get('warning') or v.get('critical')):
                if not any_warn:
                    print(f'  [WARN indicators]')
                    any_warn = True
                print(f'    {k}: value={v.get("value")}, warning={v.get("warning")}, critical={v.get("critical")}')
        # ensemble details
        ens = erd.get('ensemble', {})
        if ens:
            print(f'  bearing_confidence={ens.get("bearing_confidence")}, gear_confidence={ens.get("gear_confidence")}')
            print(f'  time_confidence={ens.get("time_confidence")}')
            print(f'  has_bearing={ens.get("has_bearing_params")}, has_gear={ens.get("has_gear_params")}')
            print(f'  skip_bearing={ens.get("skip_bearing")}, skip_gear={ens.get("skip_gear")}')
        print(f'  fault_label={erd.get("fault_label")}')
    print()

db.close()
