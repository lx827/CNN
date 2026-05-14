"""服务器端：直接调用 analyzer 重新诊断"""
import sys
sys.path.insert(0, "/opt/CNN/cloud")

from app.database import SessionLocal
from app.models import Device, Diagnosis, SensorData
from app.services.analyzer import analyze_device
from sqlalchemy import desc
import json

db = SessionLocal()

gear_devices = ["WTG-004", "WTG-005", "WTG-006", "WTG-007", "WTG-008", "WTG-009"]

for dev_id in gear_devices:
    device = db.query(Device).filter(Device.device_id == dev_id).first()
    if not device:
        print(f"  {dev_id}: 设备不存在")
        continue

    # 获取传感器数据
    channels_data = {}
    batches = db.query(SensorData.batch_index).filter(
        SensorData.device_id == dev_id, SensorData.is_special == 0
    ).distinct().all()
    
    if not batches:
        print(f"  {dev_id}: 无数据")
        continue

    results_summary = []
    for batch_idx in [b[0] for b in batches]:
        records = db.query(SensorData).filter(
            SensorData.device_id == dev_id, SensorData.batch_index == batch_idx
        ).all()
        for rec in records:
            channels_data[f"ch{rec.channel}"] = rec.data
        
        sample_rate = records[0].sample_rate if records else 8192

        try:
            result = analyze_device(channels_data, sample_rate, device)
            hs = result["health_score"]
            status = result["status"]
            fp = result.get("fault_probabilities", {})
            oa = result.get("order_analysis", {})
            
            # 查看诊断详情
            channels_info = oa.get("channels", {})
            for ch, ch_result in channels_info.items():
                tf = ch_result.get("time_features", {})
                ens = ch_result.get("ensemble", {})
                gear_ind = ch_result.get("gear", {}).get("fault_indicators", {})
                
                kurt = tf.get("kurtosis", "?")
                crest = tf.get("crest_factor", "?")
                gear_conf = ens.get("gear_confidence", "?")
                skip_b = ens.get("skip_bearing", "?")
                skip_g = ens.get("skip_gear", "?")
                
                # 检查齿轮指标的 warning/critical 状态
                gear_flags = {}
                for name, val in gear_ind.items():
                    if isinstance(val, dict):
                        gear_flags[name] = f"w={val.get('warning')},c={val.get('critical')}"

                results_summary.append(
                    f"  {dev_id} batch={batch_idx} ch={ch}: hs={ch_result.get('health_score', '?')} "
                    f"kurt={kurt} crest={crest} gear_conf={gear_conf} "
                    f"skip_b={skip_b} skip_g={skip_g} "
                    f"gear_ind={gear_flags}"
                )
            
            results_summary.append(
                f"  → 设备级: hs={hs} status={status} fp={sorted(fp.items(), key=lambda x: -x[1])[:3]}"
            )
        except Exception as e:
            results_summary.append(f"  {dev_id} batch={batch_idx}: 异常 {e}")

    for line in results_summary:
        print(line)

db.close()