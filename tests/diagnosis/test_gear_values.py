"""齿轮指标值对比：健康 vs 故障"""
import os, sys, glob, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'cloud'))

from app.services.diagnosis.engine import DiagnosisEngine, DiagnosisStrategy, DenoiseMethod, GearMethod
from app.services.diagnosis.features import compute_time_features

WTGEAR_GEAR_TEETH = {"sun": 28, "ring": 100, "planet": 36, "planet_count": 4, "input": 28}
WTGEAR_DATA_DIR = r"D:\code\wavelet_study\dataset\WTgearbox\down8192"
FS = 8192

groups = {}
for fpath in sorted(glob.glob(os.path.join(WTGEAR_DATA_DIR, "*.npy"))):
    fname = os.path.basename(fpath)
    name_no_ext = fname.replace(".npy", "")
    parts = name_no_ext.split("-")
    ch = parts[-1]
    prefix = "-".join(parts[:-1])
    groups.setdefault(prefix, {})[ch] = fpath

cases = [
    ("He_N2_40", "健康N2@40Hz"),  # 正常基线
    ("He_N1_40", "健康N1@40Hz"),  # 高峭度健康
    ("Br_B1_35", "断齿@35Hz"),    # crest最高的断齿
    ("Mi_M1_20", "缺齿@20Hz"),    # 明显故障
    ("We_W1_20", "磨损@20Hz"),    # 明显故障
    ("Rc_R1_55", "裂纹@55Hz"),    # 微弱故障
]

print(f"{'工况':<20} {'SER':<10} {'CAR':<15} {'sideband':<10} {'peak_conc':<10} {'order_kurt':<12} {'FM0':<10}")
for prefix, desc in cases:
    if prefix not in groups:
        continue
    first_ch = sorted(groups[prefix].keys())[0]
    signal = np.load(groups[prefix][first_ch])[:FS*5]

    engine = DiagnosisEngine(
        strategy=DiagnosisStrategy.STANDARD,
        gear_method=GearMethod.ADVANCED,
        bearing_params=None,
        gear_teeth=WTGEAR_GEAR_TEETH,
    )
    proc = engine.preprocess(signal)
    rf = 40.0  # 固定40Hz用于对比

    result = engine.analyze_gear(proc, FS, rf, preprocess=False)

    gear = result.get("gear_result", result)
    ind = result.get("fault_indicators", {})

    ser_val = ind.get("ser", {}).get("value", 0) if isinstance(ind.get("ser"), dict) else 0
    car_val = ind.get("car", {}).get("value", 0) if isinstance(ind.get("car"), dict) else 0
    sb_val = ind.get("sideband_count", {}).get("value", 0) if isinstance(ind.get("sideband_count"), dict) else 0
    peak_val = ind.get("order_peak_concentration", {}).get("value", 0) if isinstance(ind.get("order_peak_concentration"), dict) else 0
    kurt_val = ind.get("order_kurtosis", {}).get("value", 0) if isinstance(ind.get("order_kurtosis"), dict) else 0
    fm0_val = ind.get("fm0", {}).get("value", 0) if isinstance(ind.get("fm0"), dict) else 0

    print(f"{desc:<20} {ser_val:<10.4f} {car_val:<15.4f} {sb_val:<10} {peak_val:<10.4f} {kurt_val:<12.2f} {fm0_val:<10.4f}")