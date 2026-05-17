import sys
sys.path.insert(0, r'd:/code/CNN/cloud')
sys.path.insert(0, r'd:/code/CNN/tests/diagnosis')
from pathlib import Path
import numpy as np
from app.services.diagnosis.engine import DiagnosisEngine, BearingMethod, DiagnosisStrategy, DenoiseMethod
from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum
from evaluation.datasets import classify_hustbear

SAMPLE_RATE = 8192
MAX_SAMPLES = SAMPLE_RATE * 5
BEARING_PARAMS = {"n": 9, "d": 7.94, "D": 38.52}

data_dir = Path(r'D:\code\wavelet_study\dataset\HUSTbear\down8192')

healthy_ok = 0
healthy_fail = 0
fault_detect = 0
fault_miss = 0

for f in sorted(data_dir.glob('*-X.npy')):
    info = classify_hustbear(f.name)
    if info["label"] == "unknown":
        continue

    sig = np.load(f)[:MAX_SAMPLES]
    rf = estimate_rot_freq_spectrum(sig, SAMPLE_RATE)
    engine = DiagnosisEngine(strategy=DiagnosisStrategy.ADVANCED, bearing_method=BearingMethod.ENVELOPE,
                             denoise_method=DenoiseMethod.NONE, bearing_params=BEARING_PARAMS)
    comp = engine.analyze_comprehensive(sig, SAMPLE_RATE, rot_freq=rf)
    hs = int(comp.get("health_score", 100))

    if info["label"] == "healthy":
        if hs >= 85:
            healthy_ok += 1
        else:
            healthy_fail += 1
            print(f"  [健康误报] {f.name}: rf={rf:.1f}Hz, hs={hs}")
    else:
        if hs < 85:
            fault_detect += 1
        else:
            fault_miss += 1
            print(f"  [故障漏检] {f.name}: rf={rf:.1f}Hz, hs={hs}, true={info['label']}")

total = healthy_ok + healthy_fail + fault_detect + fault_miss
acc = (healthy_ok + fault_detect) / total if total > 0 else 0
print(f"\n统计: 健康OK={healthy_ok}, 健康误报={healthy_fail}, 故障检出={fault_detect}, 故障漏检={fault_miss}")
print(f"总样本={total}, 二分类准确率={acc:.2%}")
