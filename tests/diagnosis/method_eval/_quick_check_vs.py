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

print("=== 变速健康样本 ===")
for f in sorted(data_dir.glob('H*VS*-X.npy')):
    sig = np.load(f)[:MAX_SAMPLES]
    rf = estimate_rot_freq_spectrum(sig, SAMPLE_RATE)
    engine = DiagnosisEngine(strategy=DiagnosisStrategy.ADVANCED, bearing_method=BearingMethod.ENVELOPE,
                             denoise_method=DenoiseMethod.NONE, bearing_params=BEARING_PARAMS)
    comp = engine.analyze_comprehensive(sig, SAMPLE_RATE, rot_freq=rf)
    hs = int(comp.get("health_score", 100))
    print(f"  {f.name}: rf={rf:.1f}Hz, hs={hs}, status={comp.get('status')}")

print("\n=== 变速故障样本 ===")
for f in sorted(data_dir.glob('*VS*-X.npy'))[:5]:
    sig = np.load(f)[:MAX_SAMPLES]
    rf = estimate_rot_freq_spectrum(sig, SAMPLE_RATE)
    engine = DiagnosisEngine(strategy=DiagnosisStrategy.ADVANCED, bearing_method=BearingMethod.ENVELOPE,
                             denoise_method=DenoiseMethod.NONE, bearing_params=BEARING_PARAMS)
    comp = engine.analyze_comprehensive(sig, SAMPLE_RATE, rot_freq=rf)
    hs = int(comp.get("health_score", 100))
    parts = f.name.split('-')[0].split('_')
    ft = [s for s in parts if s in ('B','IR','O','OR','C','I','H','N')]
    print(f"  {f.name}: rf={rf:.1f}Hz, hs={hs}, status={comp.get('status')}, fault={ft}")
