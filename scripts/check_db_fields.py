import sqlite3, json

conn = sqlite3.connect('/opt/CNN/cloud/turbine.db')
# Check all fields of a diagnosis record
rows = conn.execute('SELECT * FROM diagnosis ORDER BY analyzed_at DESC LIMIT 1').fetchall()
cols = [d[0] for d in conn.execute('SELECT * FROM diagnosis LIMIT 0').description]
for r in rows:
    for i, c in enumerate(cols):
        val = r[i]
        if val and len(str(val)) > 200:
            print(f"  {c}: (len={len(str(val))}) first 200 chars: {str(val)[:200]}")
        else:
            print(f"  {c}: {val}")
    print()
conn.close()