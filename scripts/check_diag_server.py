"""服务器端诊断状态检查"""
from app.database import SessionLocal
from app.models import Device, Diagnosis, SensorData
from sqlalchemy import func, desc

db = SessionLocal()

# 1. 设备状态
print("=== 设备状态 ===")
for d in db.query(Device).all():
    print(f"  {d.device_id}: online={d.is_online}, hs={d.health_score}, status={d.status}, last_seen={d.last_seen_at}")

# 2. 诊断记录概览
print("\n=== 最近诊断记录 ===")
diags = db.query(Diagnosis).order_by(desc(Diagnosis.analyzed_at)).limit(30).all()
for diag in diags:
    skip_b = ""
    if diag.engine_result and isinstance(diag.engine_result, dict):
        ens = diag.engine_result.get("ensemble", {})
        skip_b = f", skip_b={ens.get('skip_bearing')}, skip_g={ens.get('skip_gear')}"
    print(f"  {diag.device_id} batch={diag.batch_index} ch={diag.channel} hs={diag.health_score} status={diag.status} denoise={diag.denoise_method}{skip_b}")

# 3. WTG-004~008 齿轮设备诊断详情
print("\n=== 齿轮设备(WTG-004~008)诊断详情 ===")
for dev_id in ["WTG-004", "WTG-005", "WTG-006", "WTG-007", "WTG-008"]:
    diags = db.query(Diagnosis).filter(Diagnosis.device_id == dev_id).order_by(desc(Diagnosis.analyzed_at)).limit(3).all()
    if not diags:
        print(f"  {dev_id}: 无诊断记录")
        continue
    for diag in diags:
        er = diag.engine_result or {}
        tf = er.get("time_features", {})
        gear_ind = er.get("gear", {}).get("fault_indicators", {})
        ens = er.get("ensemble", {})
        kurt = tf.get("kurtosis", "?")
        crest = tf.get("crest_factor", "?")
        gear_conf = ens.get("gear_confidence", "?")
        skip_g = ens.get("skip_gear", "?")
        print(f"  {dev_id} batch={diag.batch_index} ch={diag.channel}: hs={diag.health_score} status={diag.status} "
              f"kurt={kurt} crest={crest} gear_conf={gear_conf} skip_g={skip_g}")
        # 齿轮指标
        for name, val in gear_ind.items():
            if isinstance(val, dict):
                print(f"    {name}: value={val.get('value', '?')}, warning={val.get('warning', '?')}, critical={val.get('critical', '?')}")

# 4. 数据批次概览
print("\n=== 传感器数据批次 ===")
for dev_id in ["WTG-001", "WTG-004", "WTG-009", "WTG-010"]:
    batches = db.query(SensorData.batch_index, SensorData.is_analyzed, func.count(SensorData.channel)).filter(
        SensorData.device_id == dev_id
    ).group_by(SensorData.batch_index, SensorData.is_analyzed).all()
    total = sum(c for _, _, c in batches)
    print(f"  {dev_id}: {len(batches)} 个批次, {total} 条记录")

db.close()