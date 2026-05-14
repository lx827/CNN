"""服务器端：查看诊断记录完整字段"""
from app.database import SessionLocal
from app.models import Diagnosis
from sqlalchemy import desc
import json

db = SessionLocal()

# 查看最近几条齿轮设备的诊断记录
for dev_id in ["WTG-004", "WTG-005", "WTG-008"]:
    diag = db.query(Diagnosis).filter(Diagnosis.device_id == dev_id).order_by(desc(Diagnosis.id)).first()
    if not diag:
        print(f"{dev_id}: 无记录")
        continue

    print(f"\n=== {dev_id} batch={diag.batch_index} ch={diag.channel} ===")
    print(f"  health_score={diag.health_score}, status={diag.status}")
    print(f"  denoise_method={diag.denoise_method}")
    print(f"  rot_freq={diag.rot_freq}")

    # engine_result
    er = diag.engine_result or {}
    if er:
        print(f"  engine_result keys: {list(er.keys())[:15]}")
        tf = er.get("time_features", {})
        print(f"  time_features: kurt={tf.get('kurtosis')}, crest={tf.get('crest_factor')}")
        ens = er.get("ensemble", {})
        print(f"  ensemble: gear_conf={ens.get('gear_confidence')}, skip_b={ens.get('skip_bearing')}, skip_g={ens.get('skip_gear')}")
        gear = er.get("gear", {})
        gear_ind = gear.get("fault_indicators", {})
        if gear_ind:
            print(f"  gear fault_indicators:")
            for name, val in gear_ind.items():
                if isinstance(val, dict):
                    print(f"    {name}: value={val.get('value')}, warning={val.get('warning')}, critical={val.get('critical')}")

    # full_analysis
    fa = diag.full_analysis or {}
    if fa:
        print(f"  full_analysis keys: {list(fa.keys())[:10]}")

    # fault_probabilities
    fp = diag.fault_probabilities or {}
    if fp:
        top3 = sorted(fp.items(), key=lambda x: x[1], reverse=True)[:3]
        print(f"  fault_probabilities top3: {top3}")

db.close()