"""对比 He_N1 和 He_N2 的 c2 通道特征"""
import os, sys, glob, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'cloud'))
from app.services.diagnosis.features import compute_time_features

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

print("He_N1 c2通道 vs c1通道:")
for speed in [20, 40, 55]:
    prefix = f"He_N1_{speed}"
    if prefix in groups:
        for ch in ['c1', 'c2']:
            signal = np.load(groups[prefix][ch])[:FS*5]
            tf = compute_time_features(signal)
            print(f"  {prefix}-{ch}: kurt={tf.get('kurtosis',0):.2f}, crest={tf.get('crest_factor',0):.2f}, rms={tf.get('rms',0):.4f}")

print("\nHe_N2 c2通道 vs c1通道:")
for speed in [20, 40, 55]:
    prefix = f"He_N2_{speed}"
    if prefix in groups:
        for ch in ['c1', 'c2']:
            signal = np.load(groups[prefix][ch])[:FS*5]
            tf = compute_time_features(signal)
            print(f"  {prefix}-{ch}: kurt={tf.get('kurtosis',0):.2f}, crest={tf.get('crest_factor',0):.2f}, rms={tf.get('rms',0):.4f}")

print("\nBr_B1 c2通道:")
for speed in [20, 35, 55]:
    prefix = f"Br_B1_{speed}"
    if prefix in groups:
        for ch in ['c1', 'c2']:
            signal = np.load(groups[prefix][ch])[:FS*5]
            tf = compute_time_features(signal)
            print(f"  {prefix}-{ch}: kurt={tf.get('kurtosis',0):.2f}, crest={tf.get('crest_factor',0):.2f}, rms={tf.get('rms',0):.4f}")