import sqlite3
conn = sqlite3.connect('/opt/CNN/cloud/turbine.db')
conn.execute('UPDATE devices SET is_online=0')
conn.commit()
rows = conn.execute('SELECT device_id, is_online FROM devices').fetchall()
for r in rows: print(f"{r[0]} online={r[1]}")
conn.close()