"""
真实数据边端模拟客户端
从本地 .npy 文件读取真实风机振动数据，模拟边端采集上传到云端

使用方式：
  1. 配置 edge/.env 中的 DATA_DIR 指向数据目录
  2. 运行：python edge_real_data_client.py

数据文件命名约定（示例）：
  H-A-1.npy  H-A-2.npy  H-A-3.npy
  ^  ^  ^
  |  |  └── 通道号 (1/2/3)
  |  └───── 工况/状态 (A/B/C/D...)
  └──────── 类别 (H/I/O...)

每组需要包含同前缀的 3 个通道文件，程序会自动识别分组。
"""
import os
import time
import random
import glob
import requests
import numpy as np
from datetime import datetime
from dotenv import load_dotenv
from compressor import compress_payload

# 加载 .env 文件（如果存在）
load_dotenv()

# ========== 配置（可通过环境变量或 .env 修改）==========
DATA_DIR = os.getenv("DATA_DIR", r"D:\code\wavelet_study\dataset\CW\down8192_CW")

# 多设备配置：每个设备会随机分配一种工况数据
DEVICE_IDS_STR = os.getenv("DEVICE_IDS", os.getenv("DEVICE_ID", "WTG-001"))
DEVICE_IDS = [d.strip() for d in DEVICE_IDS_STR.split(",") if d.strip()]

CLOUD_BASE_URL = os.getenv("CLOUD_BASE_URL", "http://localhost:8000")
CLOUD_INGEST_URL = os.getenv("CLOUD_INGEST_URL", f"{CLOUD_BASE_URL}/api/ingest/")
CLOUD_CONFIG_URL = os.getenv("CLOUD_CONFIG_URL", f"{CLOUD_BASE_URL}/api/devices/edge/config")

UPLOAD_INTERVAL = int(os.getenv("UPLOAD_INTERVAL", "10"))
COMPRESSION_ENABLED = os.getenv("COMPRESSION_ENABLED", "true").lower() in ("true", "1", "yes")
SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "8192"))
DURATION = 10  # 数据固定为 10 秒（8192 * 10 = 81920 点）

# 边端 API Key（用于访问受密码保护的云端接口）
EDGE_API_KEY = "turbine-edge-secret"
EDGE_HEADERS = {"X-Edge-Key": EDGE_API_KEY}


# ==================== 数据扫描与读取 ====================

def scan_data_groups(data_dir):
    """
    扫描数据目录，按文件名前缀分组
    
    Returns:
        dict: {"H-A": {"1": "path/to/H-A-1.npy", "2": "...", "3": "..."}, ...}
    """
    if not os.path.isdir(data_dir):
        raise ValueError(f"[错误] 数据目录不存在: {data_dir}")

    npy_files = glob.glob(os.path.join(data_dir, "*.npy"))
    if not npy_files:
        raise ValueError(f"[错误] 目录中未找到 .npy 文件: {data_dir}")

    groups = {}
    for fpath in sorted(npy_files):
        fname = os.path.basename(fpath)
        name_no_ext = fname.replace(".npy", "")
        parts = name_no_ext.split("-")
        if len(parts) < 3:
            continue
        prefix = "-".join(parts[:-1])   # 例如 "H-A"
        ch = parts[-1]                   # 通道号 "1"
        groups.setdefault(prefix, {})[ch] = fpath

    # 只保留包含至少 3 个通道的完整组
    valid_groups = {}
    for prefix, channels in groups.items():
        if len(channels) >= 3:
            valid_groups[prefix] = channels

    print(f"[数据扫描] 目录: {data_dir}")
    print(f"[数据扫描] 原始文件数: {len(npy_files)}")
    print(f"[数据扫描] 有效工况组: {len(valid_groups)} 组")
    for prefix in sorted(valid_groups.keys()):
        print(f"  - {prefix}: 通道 {sorted(valid_groups[prefix].keys())}")
    return valid_groups


def load_group_data(groups, prefix):
    """
    读取指定工况前缀的 3 个通道数据
    
    Returns:
        dict: {"ch1": [float, ...], "ch2": [...], "ch3": [...]}
    """
    if prefix not in groups:
        raise ValueError(f"[错误] 工况 {prefix} 不存在")

    channels = {}
    for ch_num, fpath in sorted(groups[prefix].items()):
        data = np.load(fpath)

        # 验证数据长度
        expected_len = SAMPLE_RATE * DURATION
        if len(data) != expected_len:
            print(f"[警告] {prefix} 通道 {ch_num} 长度 {len(data)} != 预期 {expected_len}，将进行截断/填充")
            if len(data) > expected_len:
                data = data[:expected_len]
            else:
                # 用末尾值填充
                pad = np.full(expected_len - len(data), data[-1] if len(data) > 0 else 0.0)
                data = np.concatenate([data, pad])

        key = f"ch{ch_num}"
        channels[key] = data.tolist()

    return channels


# ==================== 上传与配置 ====================

def upload_data(device_id, channels, sample_rate, is_special=False):
    """
    将数据上传到云端 /api/ingest/
    """
    if COMPRESSION_ENABLED:
        # 使用默认降采样比例 8x（81920 → 10240 点）
        compressed_info = compress_payload(
            channels,
            sample_rate=sample_rate,
            downsample_ratio=8
        )
        payload = {
            "device_id": device_id,
            "timestamp": datetime.utcnow().isoformat(),
            "sample_rate": sample_rate,
            "is_special": 1 if is_special else 0,
            **compressed_info
        }
    else:
        payload = {
            "device_id": device_id,
            "timestamp": datetime.utcnow().isoformat(),
            "channels": channels,
            "sample_rate": sample_rate,
            "is_special": 1 if is_special else 0,
        }

    try:
        response = requests.post(
            CLOUD_INGEST_URL,
            json=payload,
            headers=EDGE_HEADERS,
            timeout=15
        )
        if response.status_code == 200:
            orig = payload.get("original_points", len(next(iter(channels.values()))))
            comp = payload.get("compressed_points", orig)
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] [{device_id}] 上传成功: "
                f"{len(channels)} 通道, 原始 {orig} 点 → 压缩后 {comp} 点, "
                f"{sample_rate}Hz x {DURATION}s"
            )
            return True
        else:
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] [{device_id}] 上传失败: "
                f"{response.status_code} - {response.text[:200]}"
            )
            return False
    except requests.exceptions.ConnectionError:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [{device_id}] 连接失败: 云端服务未启动？")
        return False
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [{device_id}] 异常: {e}")
        return False


def fetch_device_config(device_id):
    """从云端拉取设备配置"""
    try:
        response = requests.get(
            f"{CLOUD_CONFIG_URL}?device_id={device_id}",
            headers=EDGE_HEADERS,
            timeout=5
        )
        if response.status_code == 200:
            return response.json().get("data", {})
    except Exception:
        pass
    return {}


# ==================== 主程序 ====================

def main():
    print("=" * 60)
    print("真实数据边端模拟客户端")
    print(f"数据目录 : {DATA_DIR}")
    print(f"设备列表 : {', '.join(DEVICE_IDS)}")
    print(f"目标云端 : {CLOUD_INGEST_URL}")
    print(f"采样率   : {SAMPLE_RATE} Hz")
    print(f"数据时长 : {DURATION} s")
    print(f"上传间隔 : {UPLOAD_INTERVAL} s")
    print(f"压缩     : {'已启用' if COMPRESSION_ENABLED else '已关闭'}")
    print("=" * 60)

    # 扫描数据目录
    try:
        groups = scan_data_groups(DATA_DIR)
    except ValueError as e:
        print(e)
        return

    if not groups:
        print("[错误] 未找到有效的 3 通道数据组")
        return

    prefixes = list(groups.keys())

    # 为每个设备随机分配一种工况（可重复）
    device_assignments = {}
    for dev_id in DEVICE_IDS:
        prefix = random.choice(prefixes)
        device_assignments[dev_id] = prefix
        print(f"[{dev_id}] 分配工况: {prefix}")

    # 设备状态
    device_states = {}
    for dev_id in DEVICE_IDS:
        device_states[dev_id] = {
            "last_upload_time": 0,
            "prefix": device_assignments[dev_id],
        }

    print("=" * 60)
    print("提示: 请确保云端服务已启动 (cd cloud && python -m app.main)")
    print("按 Ctrl+C 停止")
    print("=" * 60)

    while True:
        current_time = time.time()

        for dev_id in DEVICE_IDS:
            state = device_states[dev_id]
            if current_time - state["last_upload_time"] >= UPLOAD_INTERVAL:
                state["last_upload_time"] = current_time

                # 读取该设备分配的工况数据
                prefix = state["prefix"]
                try:
                    channels = load_group_data(groups, prefix)
                except Exception as e:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{dev_id}] 数据读取失败: {e}")
                    continue

                # 上传
                upload_data(
                    device_id=dev_id,
                    channels=channels,
                    sample_rate=SAMPLE_RATE,
                    is_special=False
                )

        time.sleep(0.5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n客户端已停止")
