import sqlite3, json
conn = sqlite3.connect('/opt/CNN/cloud/turbine.db')
rows = conn.execute('SELECT device_id, batch_index, health_score, status FROM diagnosis ORDER BY device_id, batch_index').fetchall()
for r in rows:
    print(f"{r[0]} batch={r[1]} hs={r[2]} status={r[3]}")
conn.close()