import sqlite3, json, sys

conn = sqlite3.connect('/opt/CNN/cloud/turbine.db')
rows = conn.execute('SELECT device_id, batch_index, channel, health_score, status, engine_result FROM diagnosis ORDER BY analyzed_at DESC LIMIT 2').fetchall()
for r in rows:
    print(f"device={r[0]} batch={r[1]} ch={r[2]} hs={r[3]} status={r[4]}")
    er = json.loads(r[5]) if r[5] else {}
    # Print top-level keys
    print(f"  engine_result keys: {list(er.keys())}")
    # Check if time_features is nested differently
    for key in er.keys():
        val = er[key]
        if isinstance(val, dict):
            print(f"  {key} keys: {list(val.keys())[:10]}")
        else:
            print(f"  {key}: {val}")
    print()
conn.close()