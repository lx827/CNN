"""VMD 计算时间测试"""
import sys, time
sys.path.insert(0, r"D:\code\CNN\cloud")
import numpy as np
from app.services.diagnosis.gear.planetary_demod import planetary_vmd_demod_analysis

GEAR = {"sun": 28, "ring": 100, "planet": 36, "planet_count": 4}
FS = 8192
DATA_DIR = r"D:\code\wavelet_study\dataset\WTgearbox\down8192"

test_files = [
    ("He_N1_20-c1.npy", 20.0),
    ("He_N2_35-c1.npy", 35.0),
    ("Br_B1_20-c1.npy", 20.0),
    ("Mi_M2_35-c1.npy", 35.0),
    ("We_W1_40-c1.npy", 40.0),
    ("Rc_R1_35-c1.npy", 35.0),
]

for fn, rot_freq in test_files:
    sig = np.load(f"{DATA_DIR}\\{fn}")
    sig = sig[:FS * 5]
    t0 = time.perf_counter()
    r = planetary_vmd_demod_analysis(sig, FS, rot_freq, GEAR)
    elapsed = time.perf_counter() - t0
    err = r.get("error", "none")
    print(f"{fn}: {elapsed:.2f}s, error={err}")