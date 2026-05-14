import sqlite3
conn = sqlite3.connect('/opt/CNN/cloud/turbine.db')
rows = conn.execute('SELECT device_id, is_online, last_seen_at FROM devices').fetchall()
for r in rows: print(f"{r[0]} online={r[1]} last_seen={r[2]}")
conn.close()