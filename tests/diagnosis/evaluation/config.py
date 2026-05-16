"""
评价框架配置常量
"""
from pathlib import Path

# 路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
OUTPUT_DIR = Path(__file__).parent.parent / "output" / "evaluation"
CACHE_DIR = OUTPUT_DIR / "cache"

# 数据集路径
HUSTBEAR_DIR = Path(r"D:\code\wavelet_study\dataset\HUSTbear\down8192")
CW_DIR = Path(r"D:\code\CNN\CW\down8192_CW")
WTGEARBOX_DIR = Path(r"D:\code\wavelet_study\dataset\WTgearbox\down8192")

# 信号参数
SAMPLE_RATE = 8192
MAX_SECONDS = 5.0
MAX_SAMPLES = int(SAMPLE_RATE * MAX_SECONDS)

# 轴承参数 (ER-16K)
HUSTBEAR_BEARING = {"n": 9, "d": 7.94, "D": 38.52}
CW_BEARING = {"n": 9, "d": 7.94, "D": 38.52}

# 齿轮参数 (WTgearbox 行星齿轮箱)
WTGEARBOX_GEAR = {"input": 28, "ring": 100, "planet": 36, "num_planets": 4}

# 轴承理论故障频率系数（相对转频）
BEARING_FREQ_COEFFS = {
    "BPFI": 5.43,
    "BPFO": 3.57,
    "BSF": 4.71,
    "FTF": 0.40,
}

# WTgearbox 啮合频率系数 = ring*sun/(sun+ring) = 100*28/(28+100) = 21.875
MESH_FREQ_COEFF = 21.875

# 健康度阈值
HEALTH_THRESHOLD = 85

# 创建目录
for sub in ["denoise", "bearing", "gear", "comprehensive", "robustness"]:
    (OUTPUT_DIR / sub).mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
