"""
大创答辩实验配置常量

继承 evaluation 模块的配置，增加答辩专用输出目录和样本选择策略。
"""
from pathlib import Path

# ── 项目路径 ──────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# ── 输出目录 ──────────────────────────────────────────────────
OUTPUT_DIR = PROJECT_ROOT / "tests" / "output" / "contest_plots"

# ── 子目录（对应6个实验） ──────────────────────────────────────
EXP_DIRS = {
    "a_bearing":    OUTPUT_DIR / "experiment_a_bearing",
    "b_gear":       OUTPUT_DIR / "experiment_b_gear",
    "c_denoise":    OUTPUT_DIR / "experiment_c_denoise",
    "d_robustness": OUTPUT_DIR / "experiment_d_robustness",
    "e_fusion":     OUTPUT_DIR / "experiment_e_fusion",
    "f_health":     OUTPUT_DIR / "experiment_f_health",
}

for d in EXP_DIRS.values():
    d.mkdir(parents=True, exist_ok=True)

# ── 数据集路径（继承 evaluation config） ──────────────────────
HUSTBEAR_DIR = Path(r"D:\code\wavelet_study\dataset\HUSTbear\down8192")
CW_DIR       = Path(r"D:\code\CNN\CW\down8192_CW")
WTGEARBOX_DIR = Path(r"D:\code\wavelet_study\dataset\WTgearbox\down8192")

# ── 信号参数 ──────────────────────────────────────────────────
SAMPLE_RATE  = 8192
MAX_SECONDS  = 5.0
MAX_SAMPLES  = int(SAMPLE_RATE * MAX_SECONDS)

# ── 轴承参数 (ER-16K) ────────────────────────────────────────
HUSTBEAR_BEARING = {"n": 9, "d": 7.94, "D": 38.52}
CW_BEARING        = {"n": 9, "d": 7.94, "D": 38.52}

# ── 齿轮参数 (WTgearbox 行星齿轮箱) ──────────────────────────
WTGEARBOX_GEAR = {"input": 28, "ring": 100, "planet": 36, "num_planets": 4}

# ── 理论故障频率系数 ──────────────────────────────────────────
BEARING_FREQ_COEFFS = {"BPFI": 5.43, "BPFO": 3.57, "BSF": 4.71, "FTF": 0.40}
MESH_FREQ_COEFF    = 21.875

# ── 健康度阈值 ────────────────────────────────────────────────
HEALTH_THRESHOLD = 85

# ── 样本选择策略（答辩用，数量更少以控制时间） ────────────────────
MAX_PER_CLASS_HUSTBEAR   = 3   # 每类3个，快速验证
MAX_PER_CLASS_CW         = 2   # 每类每转速模式2个
MAX_PER_CLASS_WTGEARBOX  = 3   # 每类3个

# ── SNR 测试级别 ──────────────────────────────────────────────
SNR_LEVELS = [20, 10, 5, 0, -5, -10]  # dB，用于鲁棒性曲线

# ── 轴承故障标签（5类） ──────────────────────────────────────
BEARING_LABELS = ["healthy", "ball", "inner", "outer", "composite"]

# ── 齿轮故障标签（5类） ──────────────────────────────────────
GEAR_LABELS = ["healthy", "break", "missing", "crack", "wear"]

# ── 中文标签映射 ──────────────────────────────────────────────
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
    "fault":     "故障",
}

# ── 需要对比的轴承方法 ────────────────────────────────────────
BEARING_METHODS_COMPARE = [
    ("FFT频谱", "fft_threshold"),
    ("包络分析", "envelope"),
    ("Kurtogram", "kurtogram"),
    ("MED增强", "med"),
    ("MCKD", "mckd"),
    ("CPW预白化", "cpw"),
    ("Teager", "teager"),
    ("谱峭度重加权", "spectral_kurtosis"),
    ("集成Ensemble", "ensemble"),
]

# ── 需要对比的齿轮方法 ────────────────────────────────────────
GEAR_METHODS_COMPARE = [
    ("SER", "ser"),
    ("FM4", "fm4"),
    ("TSA残差峭度", "tsa_kurt"),
    ("CAR", "car"),
    ("综合诊断", "comprehensive"),
]

# ── 需要对比的去噪方法 ────────────────────────────────────────
DENOISE_METHODS_COMPARE = [
    ("无去噪", "none"),
    ("小波去噪", "wavelet"),
    ("VMD去噪", "vmd"),
    ("MED去噪", "med"),
    ("小波+VMD级联", "wavelet_vmd"),
]