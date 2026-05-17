import sys
sys.path.insert(0, r'd:/code/CNN/cloud')
sys.path.insert(0, r'd:/code/CNN/tests/diagnosis')
from pathlib import Path
import numpy as np
from app.services.diagnosis.engine import DiagnosisEngine, BearingMethod, DiagnosisStrategy, DenoiseMethod
from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum

SAMPLE_RATE = 8192
MAX_SAMPLES = SAMPLE_RATE * 5
BEARING_PARAMS = {"n": 9, "d": 7.94, "D": 38.52}

data_dir = Path(r'D:\code\wavelet_study\dataset\HUSTbear\down8192')

print("=== 健康样本 health_score ===")
for f in sorted(data_dir.glob('H*-X.npy'))[:5]:
    sig = np.load(f)[:MAX_SAMPLES]
    rf = estimate_rot_freq_spectrum(sig, SAMPLE_RATE)
    engine = DiagnosisEngine(strategy=DiagnosisStrategy.ADVANCED, bearing_method=BearingMethod.ENVELOPE,
                             denoise_method=DenoiseMethod.NONE, bearing_params=BEARING_PARAMS)
    comp = engine.analyze_comprehensive(sig, SAMPLE_RATE, rot_freq=rf)
    hs = int(comp.get("health_score", 100))
    print(f"  {f.name}: hs={hs}, status={comp.get('status')}")

print("\n=== 故障样本 health_score ===")
for f in sorted(data_dir.glob('0.5X_O_20Hz-X.npy'))[:1]:
    sig = np.load(f)[:MAX_SAMPLES]
    rf = estimate_rot_freq_spectrum(sig, SAMPLE_RATE)
    engine = DiagnosisEngine(strategy=DiagnosisStrategy.ADVANCED, bearing_method=BearingMethod.ENVELOPE,
                             denoise_method=DenoiseMethod.NONE, bearing_params=BEARING_PARAMS)
    comp = engine.analyze_comprehensive(sig, SAMPLE_RATE, rot_freq=rf)
    hs = int(comp.get("health_score", 100))
    print(f"  {f.name}: hs={hs}, status={comp.get('status')}")
