import sqlite3
conn = sqlite3.connect('/opt/CNN/cloud/turbine.db')
rows = conn.execute('SELECT device_id, batch_index, channel, denoise_method, health_score, status FROM diagnosis ORDER BY device_id, batch_index, channel LIMIT 20').fetchall()
for r in rows:
    print(f"{r[0]} batch={r[1]} ch={r[2]} denoise={r[3]} hs={r[4]} status={r[5]}")
conn.close()