"""
云端配置文件
所有可变参数集中在这里，方便修改

数据库切换：
- 默认使用 SQLite（零配置，文件存储，适合开发调试）
- 生产环境可切换为 MySQL（需自行安装并修改下方配置）
"""
import os
from dotenv import load_dotenv

# 加载 .env 文件（如果存在）
load_dotenv()

# ========== 数据库配置 ==========
# 默认 SQLite：不需要安装任何数据库软件，数据存在 cloud/turbine.db 文件中
USE_SQLITE = os.getenv("USE_SQLITE", "true").lower() in ("true", "1", "yes")

if USE_SQLITE:
    # SQLite 配置：数据保存在 cloud 目录下的 turbine.db
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./turbine.db")
else:
    # MySQL 配置：需自行安装 MySQL 并创建数据库
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", 3306))
    DB_USER = os.getenv("DB_USER", "turbine")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "turbine1234")
    DB_NAME = os.getenv("DB_NAME", "turbine_db")
    DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"

# ========== 服务配置 ==========
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", 8000))
CORS_ORIGINS = [
    item.strip()
    for item in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:4173,http://127.0.0.1:4173,"
        "http://8.137.96.104,null",
    ).split(",")
    if item.strip()
]

# ========== 分析服务配置 ==========
ANALYZE_INTERVAL_SECONDS = 30  # 每 30 秒执行一次分析
SENSOR_SAMPLE_RATE = int(os.getenv("SENSOR_SAMPLE_RATE", "25600"))  # 采样率 Hz
SENSOR_WINDOW_SECONDS = int(os.getenv("SENSOR_WINDOW_SECONDS", "10"))  # 每次上传时长（秒）

# ========== 设备配置 ==========
DEVICE_ID = "WTG-001"
DEVICE_NAME = "风机齿轮箱 #1"

# ========== 神经网络配置 ==========
# 是否启用神经网络预测（需要训练好模型并放到指定路径）
NN_ENABLED = os.getenv("NN_ENABLED", "false").lower() in ("true", "1", "yes")
NN_MODEL_PATH = os.getenv("NN_MODEL_PATH", "./models/turbine_fault_model.onnx")

# ========== 认证配置 ==========
# 网页访问密码（通过 .env 修改，默认为 admin123）
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
# JWT 签名密钥（生产环境请务必修改为随机长字符串）
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production-please")

# ========== 边端认证 ==========
# 边端 API Key（云端和边端必须一致，通过 .env 修改）
EDGE_API_KEY = os.getenv("EDGE_API_KEY", "turbine-edge-secret")
