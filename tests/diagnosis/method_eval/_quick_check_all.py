import sys
sys.path.insert(0, r'd:/code/CNN/cloud')
from pathlib import Path
import numpy as np
from app.services.diagnosis.engine import DiagnosisEngine, BearingMethod, DiagnosisStrategy, DenoiseMethod
from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum

SAMPLE_RATE = 8192
MAX_SAMPLES = SAMPLE_RATE * 5
BEARING_PARAMS = {"n": 9, "d": 7.94, "D": 38.52}

data_dir = Path(r'D:\code\wavelet_study\dataset\HUSTbear\down8192')

# 检查所有健康样本
print("=== 所有健康样本 health_score ===")
healthy_ok = 0
healthy_fail = 0
for f in sorted(data_dir.glob('H*-X.npy')):
    sig = np.load(f)[:MAX_SAMPLES]
    rf = estimate_rot_freq_spectrum(sig, SAMPLE_RATE)
    engine = DiagnosisEngine(strategy=DiagnosisStrategy.ADVANCED, bearing_method=BearingMethod.ENVELOPE,
                             denoise_method=DenoiseMethod.NONE, bearing_params=BEARING_PARAMS)
    comp = engine.analyze_comprehensive(sig, SAMPLE_RATE, rot_freq=rf)
    hs = int(comp.get("health_score", 100))
    status = "OK" if hs >= 85 else "FAIL"
    if status == "OK": healthy_ok += 1
    else: healthy_fail += 1
    print(f"  {f.name}: rf={rf:.1f}Hz, hs={hs} [{status}]")

print(f"\n健康样本统计: OK={healthy_ok}, FAIL={healthy_fail}")

# 检查故障样本中 health_score >= 85 的（漏检）
print("\n=== 故障样本中 health_score >= 85 的 (漏检) ===")
fault_miss = 0
fault_detect = 0
for f in sorted(data_dir.glob('*-X.npy')):
    if 'H' in f.name.split('-')[0]:
        continue  # skip healthy
    sig = np.load(f)[:MAX_SAMPLES]
    rf = estimate_rot_freq_spectrum(sig, SAMPLE_RATE)
    engine = DiagnosisEngine(strategy=DiagnosisStrategy.ADVANCED, bearing_method=BearingMethod.ENVELOPE,
                             denoise_method=DenoiseMethod.NONE, bearing_params=BEARING_PARAMS)
    comp = engine.analyze_comprehensive(sig, SAMPLE_RATE, rot_freq=rf)
    hs = int(comp.get("health_score", 100))
    if hs >= 85:
        fault_miss += 1
        parts = f.name.split('-')[0].split('_')
        ft = [s for s in parts if s in ('B','IR','O','OR','C','I','N')]
        print(f"  [LEAK] {f.name}: rf={rf:.1f}Hz, hs={hs}, fault={ft}")
    else:
        fault_detect += 1

print(f"\n故障样本统计: detected={fault_detect}, missed={fault_miss}")
