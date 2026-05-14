import sqlite3, json, sys

conn = sqlite3.connect('/opt/CNN/cloud/turbine.db')
rows = conn.execute('SELECT device_id, batch_index, channel, health_score, status, engine_result FROM diagnosis ORDER BY analyzed_at DESC LIMIT 10').fetchall()
for r in rows:
    print(f"device={r[0]} batch={r[1]} ch={r[2]} hs={r[3]} status={r[4]}")
    er = json.loads(r[5]) if r[5] else {}
    tf = er.get("time_features", {})
    print(f"  kurt={tf.get('kurtosis')} crest={tf.get('crest_factor')} kurt_mad_z={tf.get('kurtosis_mad_z')}")
    print(f"  rms_mad_z={tf.get('rms_mad_z')} ewma_drift={tf.get('ewma_drift')} cusum_score={tf.get('cusum_score')}")
    bi = er.get("bearing", {}).get("fault_indicators", {})
    sig_indicators = [k for k,v in bi.items() if isinstance(v, dict) and v.get("significant")]
    print(f"  bearing significant: {sig_indicators}")
    low_freq = bi.get("low_freq_ratio", {})
    if isinstance(low_freq, dict):
        print(f"  low_freq_ratio={low_freq.get('value')} rotation_dominant={low_freq.get('rotation_harmonic_dominant')}")
    gi = er.get("gear", {}).get("fault_indicators", {})
    sig_gear = [k for k,v in gi.items() if isinstance(v, dict) and v.get("significant")]
    print(f"  gear significant: {sig_gear}")
    print()
conn.close()