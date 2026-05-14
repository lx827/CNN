import sqlite3, json

conn = sqlite3.connect('/opt/CNN/cloud/turbine.db')
row = conn.execute('SELECT order_analysis FROM diagnosis WHERE device_id="WTG-001" AND batch_index=7 LIMIT 1').fetchone()
oa = json.loads(row[0]) if row else {}
er = oa.get("engine_result", {})

# Print the full structure with types and leaf values
def walk(obj, prefix="", depth=0):
    if depth > 4:
        print(f"{prefix}... (depth limit)")
        return
    for k, v in obj.items():
        key_str = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            print(f"{key_str}: dict({len(v)} keys)")
            walk(v, key_str, depth+1)
        elif isinstance(v, list):
            print(f"{key_str}: list({len(v)} items)")
            if len(v) <= 4:
                for i, item in enumerate(v):
                    if isinstance(item, dict):
                        print(f"  {key_str}[{i}]: dict({len(item)} keys) -> {list(item.keys())[:5]}")
                    else:
                        print(f"  {key_str}[{i}]: {item}")
        elif isinstance(v, str) and len(v) > 100:
            print(f"{key_str}: str({len(v)} chars)")
        else:
            print(f"{key_str}: {v}")

walk(er)
conn.close()