"""测试 FM4/M6A/M8A 对行星齿轮箱的区分力"""
import os, sys, glob, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'cloud'))

from app.services.diagnosis.gear.metrics import compute_tsa_residual_order, compute_fm4, compute_m6a, compute_m8a

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
    ("He_N2_40", "健康N2@40Hz"),
    ("He_N1_40", "健康N1@40Hz"),
    ("He_N1_55", "健康N1@55Hz"),
    ("Br_B1_35", "断齿@35Hz"),
    ("Br_B2_40", "断齿B2@40Hz"),
    ("Mi_M1_40", "缺齿@40Hz"),
    ("We_W1_40", "磨损@40Hz"),
    ("Rc_R1_40", "裂纹@40Hz"),
]

print(f"{'工况':<20} {'FM4':<10} {'M6A':<12} {'M8A':<12}")
for prefix, desc in cases:
    if prefix not in groups:
        continue
    first_ch = sorted(groups[prefix].keys())[0]
    signal = np.load(groups[prefix][first_ch])[:FS*5]

    # 从文件名推断转速
    speed = int(prefix.split("_")[-1])
    rf = float(speed)

    tsa_result = compute_tsa_residual_order(signal, FS, rf)
    if not tsa_result.get("valid"):
        print(f"{desc:<20} TSA无效: {tsa_result.get('reason')}")
        continue

    residual = tsa_result["residual"]
    differential = tsa_result["differential"]

    fm4 = compute_fm4(differential)
    m6a = compute_m6a(differential)
    m8a = compute_m8a(differential)

    print(f"{desc:<20} {fm4:<10.4f} {m6a:<12.4f} {m8a:<12.4f}")