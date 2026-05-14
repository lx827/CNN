import sqlite3, json

conn = sqlite3.connect('/opt/CNN/cloud/turbine.db')
rows = conn.execute('SELECT device_id, batch_index, channel, health_score, status, fault_probabilities FROM diagnosis WHERE device_id="WTG-004" ORDER BY batch_index LIMIT 10').fetchall()
for r in rows:
    fp = r[5] if r[5] else "None"
    print(f"{r[0]} batch={r[1]} ch={r[2]} hs={r[3]} status={r[4]} fault_probabilities={fp}")
conn.close()