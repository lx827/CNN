"""
诊断方法评估框架 — 全局配置

包含：
- 数据集路径
- 轴承/齿轮/去噪方法列表
- 标签映射
- 输出目录
- 评估参数
"""
import os
from pathlib import Path
from typing import Dict, List, Tuple

# ═══════════════════════════════════════════════════════════
# 项目路径
# ═══════════════════════════════════════════════════════════
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CLOUD_PATH = PROJECT_ROOT / "cloud"

# ═══════════════════════════════════════════════════════════
# 数据集路径（支持环境变量覆盖）
# ═══════════════════════════════════════════════════════════
HUSTBEAR_DIR = Path(os.environ.get(
    "HUSTBEAR_DIR",
    r"D:\code\wavelet_study\dataset\HUSTbear\down8192"
))

CW_DIR = Path(os.environ.get(
    "CW_DIR",
    r"D:\code\CNN\CW\down8192_CW"
))

WTGEARBOX_DIR = Path(os.environ.get(
    "WTGEARBOX_DIR",
    r"D:\code\wavelet_study\dataset\WTgearbox\down8192"
))

# ═══════════════════════════════════════════════════════════
# 信号参数
# ═══════════════════════════════════════════════════════════
SAMPLE_RATE = 8192          # 所有数据集均为 8192 Hz
MAX_SAMPLES = SAMPLE_RATE * 5  # 截断到 5 秒（服务器限制）

# ═══════════════════════════════════════════════════════════
# 机械参数
# ═══════════════════════════════════════════════════════════
# ER-16K 轴承参数（HUSTbear / CW 共用）
BEARING_PARAMS = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}

# WTgearbox 行星齿轮箱参数
GEAR_PARAMS = {"input": 28, "ring": 100, "planet": 36, "num_planets": 4}

# 理论故障频率系数
BEARING_FREQ_COEFFS = {"BPFI": 5.43, "BPFO": 3.57, "BSF": 4.71, "FTF": 0.40}
MESH_FREQ_COEFF = 21.875  # 行星箱啮合频率系数

# ═══════════════════════════════════════════════════════════
# 输出目录
# ═══════════════════════════════════════════════════════════
OUTPUT_DIR = PROJECT_ROOT / "tests" / "output" / "method_eval"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 各实验子目录
EXP_DIRS = {
    "bearing_hustbear":  OUTPUT_DIR / "bearing_hustbear",
    "bearing_cw":        OUTPUT_DIR / "bearing_cw",
    "gear_wtgearbox":    OUTPUT_DIR / "gear_wtgearbox",
    "binary_all":        OUTPUT_DIR / "binary_all",
}
for d in EXP_DIRS.values():
    d.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════
# 轴承诊断方法列表（13 种 + Ensemble）
# ═══════════════════════════════════════════════════════════
# 格式：(显示名, BearingMethod枚举值, 是否仅包络类)
# 注：SC_SCOH 计算量极大，默认跳过
BEARING_METHODS = [
    ("标准包络",       "envelope"),
    ("Kurtogram",      "kurtogram"),
    ("CPW预白化",      "cpw"),
    ("MED增强",        "med"),
    ("MCKD",           "mckd"),
    ("Teager",         "teager"),
    ("谱峭度重加权",   "spectral_kurtosis"),
    # ("SC-SCoh",     "sc_scoh"),        # 计算量极大，跳过
    ("小波包",         "wp"),
    ("DWT",            "dwt"),
    ("EMD",            "emd_envelope"),
    ("CEEMDAN",        "ceemdan_envelope"),
    ("VMD",            "vmd_envelope"),
]

# ═══════════════════════════════════════════════════════════
# 齿轮诊断方法列表（2 种 + Ensemble）
# ═══════════════════════════════════════════════════════════
GEAR_METHODS = [
    ("标准边频分析",   "standard"),
    ("高级综合",       "advanced"),
]

# ═══════════════════════════════════════════════════════════
# 去噪方法（4 种基础）
# ═══════════════════════════════════════════════════════════
DENOISE_METHODS = [
    ("无去噪",         "none"),
    ("小波去噪",       "wavelet"),
    ("VMD去噪",        "vmd"),
    ("小波+VMD级联",   "wavelet_vmd"),
]

# ═══════════════════════════════════════════════════════════
# 标签体系
# ═══════════════════════════════════════════════════════════

# HUSTbear 5 类标签
HUSTBEAR_LABELS = ["healthy", "ball", "inner", "outer", "composite"]

# CW 3 类标签
CW_LABELS = ["healthy", "inner", "outer"]

# WTgearbox 5 类标签
WTGEARBOX_LABELS = ["healthy", "break", "missing", "crack", "wear"]

# 中文标签映射
LABEL_CN = {
    "healthy":   "健康",
    "ball":      "球故障",
    "inner":     "内圈故障",
    "outer":     "外圈故障",
    "composite": "复合故障",
    "break":     "断齿",
    "missing":   "缺齿",
    "crack":     "齿根裂纹",
    "wear":      "磨损",
}

# D-S 融合 dominant_fault → 轴承标签
DS_TO_BEARING = {
    "轴承外圈故障": "outer",
    "轴承内圈故障": "inner",
    "轴承滚动体故障": "ball",
    "正常": "healthy",
    "齿轮磨损": "composite",   # 轴承实验中齿轮异常归为复合
    "齿轮裂纹": "composite",
    "齿轮断齿": "composite",
}

# D-S 融合 dominant_fault → 齿轮标签
DS_TO_GEAR = {
    "齿轮断齿": "break",
    "齿轮磨损": "wear",
    "齿轮裂纹": "crack",
    "正常": "healthy",
    "轴承外圈故障": "missing",    # 齿轮实验中轴承异常归为缺齿
    "轴承内圈故障": "missing",
    "轴承滚动体故障": "missing",
}

# fault_label → 轴承标签
FAULT_LABEL_TO_BEARING = {
    "bearing_BPFO": "outer",
    "bearing_BPFI": "inner",
    "bearing_BSF": "ball",
    "bearing_BPFO_BPFI": "composite",
    "bearing_abnormal": "outer",
    "gear_abnormal": "composite",
    "unknown": "healthy",
    "正常": "healthy",
}

# fault_label → 齿轮标签
FAULT_LABEL_TO_GEAR = {
    "gear_abnormal": "break",
    "bearing_BPFO": "missing",
    "bearing_BPFI": "missing",
    "bearing_BSF": "missing",
    "bearing_abnormal": "missing",
    "unknown": "healthy",
    "正常": "healthy",
}

# fault_indicators 名称 → 轴承标签
INDICATOR_TO_BEARING = {
    "BPFO": "outer",
    "BPFI": "inner",
    "BSF": "ball",
    "FTF": "ball",
    "envelope_peak_snr": "outer",
    "envelope_kurtosis": "outer",
    "moderate_kurtosis": "outer",
    "high_freq_ratio": "inner",
    "peak_concentration": "outer",
}

# 齿轮 fault_indicators → 齿轮标签（简化）
INDICATOR_TO_GEAR = {
    "ser": "wear",
    "fm4": "crack",
    "fm0": "break",
    "car": "wear",
    "m6a": "crack",
    "m8a": "crack",
}

# ═══════════════════════════════════════════════════════════
# 评估参数
# ═══════════════════════════════════════════════════════════
HEALTH_THRESHOLD = 85       # 健康度阈值：>=85 为正常，<85 为故障
ENSEMBLE_PROFILE = "balanced"  # Ensemble 策略 profile
ENSEMBLE_MAX_SECONDS = 5.0     # Ensemble 最大处理秒数

# ═══════════════════════════════════════════════════════════
# 绘图风格
# ═══════════════════════════════════════════════════════════
STYLE = {
    "font.family": "Microsoft YaHei, SimHei, KaiTi, sans-serif",
    "font.size": 12,
    "axes.titlesize": 14,
    "axes.labelsize": 12,
    "figure.dpi": 300,
    "figure.figsize": (12, 8),
    "savefig.bbox": "tight",
    "savefig.format": "svg",
    "colors": {
        "our_method":   "#E74C3C",   # 红色 — Ensemble/我们的方法
        "baseline":     "#95A5A6",   # 灰色 — 单一方法
        "best_baseline":"#3498DB",   # 蓝色 — 最强 baseline
        "healthy":      "#2ECC71",   # 绿色 — 健康
        "warning":      "#F39C12",   # 橙色 — 预警
        "fault":        "#E74C3C",   # 红色 — 故障
        "diagonal":     "#CCCCCC",   # 浅灰 — 对角线
    },
}
