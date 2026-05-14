import sqlite3, json

conn = sqlite3.connect('/opt/CNN/cloud/turbine.db')
row = conn.execute('SELECT order_analysis FROM diagnosis WHERE device_id="WTG-001" AND batch_index=7 LIMIT 1').fetchone()
oa = json.loads(row[0]) if row else {}
# Print the engine_result structure (this is what DiagnosisDetail receives via selectedBatch.order_analysis)
er = oa.get("engine_result", {})
print("=== engine_result top keys ===")
for k in er.keys():
    v = er[k]
    if isinstance(v, dict):
        print(f"  {k}: dict with {len(v)} keys -> {list(v.keys())[:8]}")
    elif isinstance(v, list):
        print(f"  {k}: list len={len(v)}")
    else:
        print(f"  {k}: {v}")

# Check if there's a nested order_analysis inside engine_result
inner_oa = er.get("order_analysis", {})
if isinstance(inner_oa, dict):
    print("\n=== engine_result.order_analysis keys ===")
    for k in inner_oa.keys():
        v = inner_oa[k]
        if isinstance(v, dict):
            print(f"  {k}: dict -> {list(v.keys())[:8]}")
        else:
            print(f"  {k}: {v}")

# Check spectrum/envelope/order features
sf = er.get("time_features", {})
print(f"\n=== time_features keys: {list(sf.keys())}")
conn.close()