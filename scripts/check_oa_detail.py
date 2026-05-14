import sqlite3, json

conn = sqlite3.connect('/opt/CNN/cloud/turbine.db')
rows = conn.execute('SELECT device_id, batch_index, channel, health_score, status, order_analysis FROM diagnosis WHERE health_score < 80 ORDER BY analyzed_at DESC LIMIT 3').fetchall()
for r in rows:
    print(f"device={r[0]} batch={r[1]} ch={r[2]} db_hs={r[3]} db_status={r[4]}")
    oa = json.loads(r[5]) if r[5] else {}
    er = oa.get("engine_result", {})
    tf = er.get("time_features", {})
    print(f"  engine_result hs={er.get('health_score')} status={er.get('status')}")
    print(f"  kurt={tf.get('kurtosis')} crest={tf.get('crest_factor')}")
    print(f"  kurt_mad_z={tf.get('kurtosis_mad_z')} rms_mad_z={tf.get('rms_mad_z')}")
    print(f"  cusum_score={tf.get('cusum_score')} ewma_drift={tf.get('ewma_drift')}")
    
    bi = er.get("bearing", {}).get("fault_indicators", {})
    sig_b = [k for k,v in bi.items() if isinstance(v, dict) and v.get("significant")]
    print(f"  bearing significant: {sig_b}")
    lfr = bi.get("low_freq_ratio", {})
    if isinstance(lfr, dict):
        print(f"  low_freq_ratio={lfr.get('value')} rotation_dominant={lfr.get('rotation_harmonic_dominant')}")
    
    gi = er.get("gear", {}).get("fault_indicators", {})
    sig_g = [k for k,v in gi.items() if isinstance(v, dict) and v.get("significant")]
    print(f"  gear significant: {sig_g}")
    
    # Check fault_probabilities
    fp = er.get("fault_likelihood")
    fl = er.get("fault_label")
    print(f"  fault_likelihood={fp} fault_label={fl}")
    print()
conn.close()