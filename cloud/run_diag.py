import numpy as np
import os, sys
sys.path.insert(0, '.')

data_dir = r"D:\code\wavelet_study\dataset\CW\down8192_CW"
files = sorted(os.listdir(data_dir))
print("=== ALL FILES ===")
for f in files:
    print(f"  {f}")

firsts = {}
for f in files:
    cls = f.split("-")[0]
    if cls not in firsts:
        firsts[cls] = os.path.join(data_dir, f)
print(f'\nSelected: { {k: os.path.basename(v) for k, v in firsts.items()} }')

from app.services.diagnosis.engine import DiagnosisEngine
fs = 8192

for cls in ["H", "I", "O"]:
    if cls not in firsts:
        continue
    path = firsts[cls]
    data = np.load(path)
    print(f"\n=== {cls}: {os.path.basename(path)} ===")
    print(f"  shape={data.shape}, dtype={data.dtype}, len={len(data)}, dur={len(data)/fs:.1f}s")
    
    engine = DiagnosisEngine(
        strategy="advanced",
        bearing_method="kurtogram",
        gear_method="standard",
        denoise_method="none",
        bearing_params={"n": 9, "d": 7.94, "D": 38.52, "alpha": 0},
        gear_teeth=None,
    )
    result = engine.analyze_comprehensive(data.astype(np.float64), fs)
    hs = result["health_score"]
    st = result["status"]
    rf = result["bearing"].get("rot_freq_hz")
    print(f"  health_score: {hs}")
    print(f"  status: {st}")
    print(f"  rot_freq_hz: {rf}")
    ind = result["bearing"].get("fault_indicators", {})
    for name, info in ind.items():
        if isinstance(info, dict):
            sig = "SIGNIFICANT" if info.get("significant") else "ok"
            harmonics = info.get("harmonic_snrs", [])
            snr = info.get("snr", 0)
            th = info.get("theory_hz")
            det = info.get("detected_hz")
            print(f"  {name}: SNR={snr}, {sig}, theory={th}, detected={det}, harmonics={harmonics}")
