"""
齿轮诊断最终效果测试 — 40Hz 和 55Hz 所有故障类型
"""
import sys
sys.path.insert(0, r"d:/code/CNN/cloud")
sys.path.insert(0, r"d:/code/CNN/tests/diagnosis")
from pathlib import Path
import numpy as np
from app.services.diagnosis.engine import DiagnosisEngine, GearMethod, DiagnosisStrategy, DenoiseMethod
from app.services.diagnosis.ensemble import run_research_ensemble

GEAR_PARAMS = {"input": 28, "ring": 100, "planet": 36, "planet_count": 4}
SAMPLE_RATE = 8192
MAX_SAMPLES = SAMPLE_RATE * 5

data_dir = Path(r"D:\code\wavelet_study\dataset\WTgearbox\down8192")

test_files = [
    ("He_N1_40-c1.npy", "健康", 40),
    ("He_N2_55-c1.npy", "健康", 55),
    ("Br_B1_40-c1.npy", "断齿", 40),
    ("Br_B2_55-c1.npy", "断齿", 55),
    ("Mi_M1_40-c1.npy", "缺齿", 40),
    ("Mi_M2_55-c1.npy", "缺齿", 55),
    ("Rc_R1_40-c1.npy", "齿根裂纹", 40),
    ("Rc_R2_55-c1.npy", "齿根裂纹", 55),
    ("We_W1_40-c1.npy", "磨损", 40),
    ("We_W2_55-c1.npy", "磨损", 55),
]

print("=" * 120)
print("齿轮诊断最终效果测试")
print("=" * 120)
print(f"{'文件名':<25} {'故障':<6} {'转速':>4} {'SER':>6} {'FM4':>6} {'order_kurt':>11} {'peak_conc':>10} {'SER⚠':>4} {'FM4⚠':>4} {'kurt⚠':>4} {'peak⚠':>4} {'hs':>4} {'status':<8}")
print("-" * 120)

for fname, label_cn, rot_freq in test_files:
    f = data_dir / fname
    if not f.exists():
        print(f"  [SKIP] {fname} 不存在")
        continue

    sig = np.load(f)[:MAX_SAMPLES]

    engine = DiagnosisEngine(
        strategy=DiagnosisStrategy.ADVANCED,
        gear_method=GearMethod.ADVANCED,
        denoise_method=DenoiseMethod.NONE,
        gear_teeth=GEAR_PARAMS,
    )
    result = engine.analyze_gear(sig, SAMPLE_RATE, rot_freq=rot_freq)

    ser = result.get("ser", 0)
    fm4 = result.get("fm4", 0)
    order_kurt = result.get("order_kurtosis", 0)
    peak_conc = result.get("order_peak_concentration", 0)

    indicators = result.get("fault_indicators", {})
    ser_w = indicators.get("ser", {}).get("warning", False)
    fm4_w = indicators.get("fm4", {}).get("warning", False)
    kurt_w = indicators.get("order_kurtosis", {}).get("warning", False)
    peak_w = indicators.get("order_peak_concentration", {}).get("warning", False)

    # Ensemble
    try:
        ens_result = run_research_ensemble(
            sig, SAMPLE_RATE,
            bearing_params=None,
            gear_teeth=GEAR_PARAMS,
            denoise_method="none",
            rot_freq=rot_freq,
            profile="balanced",
            max_seconds=5.0,
        )
        hs = ens_result.get("health_score", 100)
        status = ens_result.get("status", "normal")
    except:
        hs = 100
        status = "error"

    ser_sym = "⚠" if ser_w else ""
    fm4_sym = "⚠" if fm4_w else ""
    kurt_sym = "⚠" if kurt_w else ""
    peak_sym = "⚠" if peak_w else ""

    print(f"{fname:<25} {label_cn:<6} {rot_freq:>3}Hz {ser:>6.2f} {fm4:>6.2f} {order_kurt:>11.2f} {peak_conc:>10.4f} {ser_sym:>4} {fm4_sym:>4} {kurt_sym:>4} {peak_sym:>4} {hs:>4} {status:<8}")

print()
print("=" * 120)
print("总结：健康样本应无 warning，故障样本应有至少 1 个 warning")
print("=" * 120)
