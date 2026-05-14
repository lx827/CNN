"""查看He_N1各转速时域特征明细"""
import os, sys, glob, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'cloud'))
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

print("He_N1 时域特征（健康行星齿轮箱，c1通道）:")
print(f"{'工况':<15} {'kurtosis':<12} {'crest':<12} {'rms':<12} {'skew':<12}")
for speed in [20, 25, 30, 35, 40, 45, 50, 55]:
    prefix = f"He_N1_{speed}"
    if prefix in groups:
        first_ch = sorted(groups[prefix].keys())[0]
        signal = np.load(groups[prefix][first_ch])[:FS*5]
        tf = compute_time_features(signal)
        print(f"{prefix:<15} {tf.get('kurtosis',0):<12.4f} {tf.get('crest_factor',0):<12.4f} {tf.get('rms',0):<12.6f} {tf.get('skewness',0):<12.4f}")

print("\nHe_N2 时域特征（健康行星齿轮箱，c1通道）:")
for speed in [20, 25, 30, 35, 40, 45, 50, 55]:
    prefix = f"He_N2_{speed}"
    if prefix in groups:
        first_ch = sorted(groups[prefix].keys())[0]
        signal = np.load(groups[prefix][first_ch])[:FS*5]
        tf = compute_time_features(signal)
        print(f"{prefix:<15} {tf.get('kurtosis',0):<12.4f} {tf.get('crest_factor',0):<12.4f} {tf.get('rms',0):<12.6f} {tf.get('skewness',0):<12.4f}")

# 也看故障数据
print("\nBr_B1 断齿时域特征（c1通道）:")
for speed in [20, 25, 30, 35, 40, 45, 50, 55]:
    prefix = f"Br_B1_{speed}"
    if prefix in groups:
        first_ch = sorted(groups[prefix].keys())[0]
        signal = np.load(groups[prefix][first_ch])[:FS*5]
        tf = compute_time_features(signal)
        print(f"{prefix:<15} {tf.get('kurtosis',0):<12.4f} {tf.get('crest_factor',0):<12.4f} {tf.get('rms',0):<12.6f} {tf.get('skewness',0):<12.4f}")

print("\nMi_M1 缺齿时域特征（c1通道）:")
for speed in [20, 25, 30, 35, 40, 45, 50, 55]:
    prefix = f"Mi_M1_{speed}"
    if prefix in groups:
        first_ch = sorted(groups[prefix].keys())[0]
        signal = np.load(groups[prefix][first_ch])[:FS*5]
        tf = compute_time_features(signal)
        print(f"{prefix:<15} {tf.get('kurtosis',0):<12.4f} {tf.get('crest_factor',0):<12.4f} {tf.get('rms',0):<12.6f} {tf.get('skewness',0):<12.4f}")

print("\nWe_W1 磨损时域特征（c1通道）:")
for speed in [20, 25, 30, 35, 40, 45, 50, 55]:
    prefix = f"We_W1_{speed}"
    if prefix in groups:
        first_ch = sorted(groups[prefix].keys())[0]
        signal = np.load(groups[prefix][first_ch])[:FS*5]
        tf = compute_time_features(signal)
        print(f"{prefix:<15} {tf.get('kurtosis',0):<12.4f} {tf.get('crest_factor',0):<12.4f} {tf.get('rms',0):<12.6f} {tf.get('skewness',0):<12.4f}")

print("\nRc_R1 齿根裂纹时域特征（c1通道）:")
for speed in [20, 25, 30, 35, 40, 45, 50, 55]:
    prefix = f"Rc_R1_{speed}"
    if prefix in groups:
        first_ch = sorted(groups[prefix].keys())[0]
        signal = np.load(groups[prefix][first_ch])[:FS*5]
        tf = compute_time_features(signal)
        print(f"{prefix:<15} {tf.get('kurtosis',0):<12.4f} {tf.get('crest_factor',0):<12.4f} {tf.get('rms',0):<12.6f} {tf.get('skewness',0):<12.4f}")