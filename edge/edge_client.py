"""
边端采集客户端（多设备 + 多数据源版本）

安装在风机现场的工业网关，负责：
1. 读取本地真实 .npy 振动数据（支持 CW / WTgearbox 多数据源）
2. 打包并压缩数据
3. 通过 HTTP POST 上传到云端

设备分配方案：
  WTG-001: CW 轴承健康 (H)       — 仅配置轴承参数 (6205-2RS)
  WTG-002: CW 轴承内圈故障 (I)   — 仅配置轴承参数
  WTG-003: CW 轴承外圈故障 (O)   — 仅配置轴承参数
  WTG-004: WTgearbox 断齿 (Br)     — 仅配置齿轮参数（行星齿轮箱）
  WTG-005: WTgearbox 缺齿 (Mi)       — 仅配置齿轮参数
  WTG-006: WTgearbox 齿根裂纹 (Rc)   — 仅配置齿轮参数
  WTG-007: WTgearbox 磨损 (We)       — 仅配置齿轮参数
  WTG-008: WTgearbox 健康 (He)       — 仅配置齿轮参数（健康参考）
  WTG-009: 混合通道（CW轴承+WTgearbox齿轮）— 配置轴承+齿轮参数
  WTG-010: 离线模拟（不上传数据）

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

# 加载 .env 文件（脚本所在目录）
script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, ".env")
if os.path.isfile(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()

# ========== 云端配置 ==========
CLOUD_BASE_URL = os.getenv("CLOUD_BASE_URL", "http://localhost:8000")
CLOUD_INGEST_URL = os.getenv("CLOUD_INGEST_URL", f"{CLOUD_BASE_URL}/api/ingest/")
CLOUD_TASKS_URL = os.getenv("CLOUD_TASKS_URL", f"{CLOUD_BASE_URL}/api/collect/tasks")
CLOUD_CONFIG_URL = os.getenv("CLOUD_CONFIG_URL", f"{CLOUD_BASE_URL}/api/devices/edge/config")

# 设备列表（环境变量覆盖默认）
DEVICE_IDS_STR = os.getenv("DEVICE_IDS", "WTG-001,WTG-002,WTG-003,WTG-004,WTG-005,WTG-006,WTG-007,WTG-008,WTG-009")
DEVICE_IDS = [d.strip() for d in DEVICE_IDS_STR.split(",") if d.strip()]

# ========== 数据源路径 ==========
CW_DATA_DIR = os.getenv("CW_DATA_DIR", r"D:\code\CNN\CW\down8192_CW")
WTGEAR_DATA_DIR = os.getenv("WTGEAR_DATA_DIR", r"D:\code\wavelet_study\dataset\WTgearbox\down8192")

# ========== 边端运行参数 ==========
DEFAULT_UPLOAD_INTERVAL = int(os.getenv("UPLOAD_INTERVAL", "10"))
DEFAULT_TASK_POLL_INTERVAL = int(os.getenv("TASK_POLL_INTERVAL", "5"))
COMPRESSION_ENABLED = os.getenv("COMPRESSION_ENABLED", "true").lower() in ("true", "1", "yes")
SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "25600"))
DURATION = int(os.getenv("DURATION", "10"))
DOWNSAMPLE_RATIO = int(os.getenv("DOWNSAMPLE_RATIO", "8"))

# ========== 真实数据参数 ==========
REAL_SAMPLE_RATE = int(os.getenv("REAL_SAMPLE_RATE", "8192"))
REAL_DURATION = 10  # 真实数据固定 10 秒

MAX_SECONDS_SIGNAL = 5  # 云端截断到 5 秒

# ========== 离线检测与超时配置 ==========
CONNECT_TIMEOUT = float(os.getenv("CONNECT_TIMEOUT", "10.0"))
READ_TIMEOUT = float(os.getenv("READ_TIMEOUT", "180.0"))
OFFLINE_THRESHOLD = int(os.getenv("OFFLINE_THRESHOLD", "3"))
OFFLINE_POLL_INTERVAL = int(os.getenv("OFFLINE_POLL_INTERVAL", "60"))

# ========== 边端认证 ==========
EDGE_API_KEY = os.getenv("EDGE_API_KEY", "turbine-edge-secret")
EDGE_HEADERS = {"X-Edge-Key": EDGE_API_KEY}

CONFIG_REFRESH_INTERVAL = 30

# ==================== 设备 → 数据源映射 ====================
# 格式: {device_id: (data_dir, prefix_filter, channel_count)}
DEVICE_DATA_MAP = {
    # CW 轴承数据集（3通道，变速工况）— 仅配置轴承参数
    "WTG-001": (CW_DATA_DIR, "H", 3),
    "WTG-002": (CW_DATA_DIR, "I", 3),
    "WTG-003": (CW_DATA_DIR, "O", 3),
    # WTgearbox 行星齿轮箱数据集（2通道，恒速工况）— 仅配置齿轮参数
    "WTG-004": (WTGEAR_DATA_DIR, "Br", 2),
    "WTG-005": (WTGEAR_DATA_DIR, "Mi", 2),
    "WTG-006": (WTGEAR_DATA_DIR, "Rc", 2),
    "WTG-007": (WTGEAR_DATA_DIR, "We", 2),
    "WTG-008": (WTGEAR_DATA_DIR, "He", 2),
    # 混合设备：轴承故障通道 + 齿轮故障通道 — 配置轴承+齿轮参数
    "WTG-009": ("mixed", "mixed", 3),
}

# WTG-010 不参与上传（离线模拟设备）


# ==================== 数据扫描与读取 ====================

def scan_data_groups(data_dir):
    """
    扫描数据目录，按文件名前缀分组
    CW 文件: H-A-1.npy → prefix=H-A, ch=1
    WTgearbox 文件: Br_B1_20-c1.npy → prefix=Br_B1_20, ch=c1
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
        if len(parts) < 2:
            continue
        ch_str = parts[-1]  # 通道号（c1, c2 或 1, 2, 3）
        prefix = "-".join(parts[:-1])
        groups.setdefault(prefix, {})[ch_str] = fpath

    return groups


def load_group_data(groups, prefix, target_duration=None, expected_channels=None):
    """读取指定工况前缀的通道数据， """
    if prefix not in groups:
        raise ValueError(f"[错误] 工况 {prefix} 不存在")

    duration = target_duration if target_duration is not None else REAL_DURATION
    expected_len = REAL_SAMPLE_RATE * duration

    channels = {}
    for ch_key, fpath in sorted(groups[prefix].items()):
        data = np.load(fpath)
        if len(data) != expected_len:
            if len(data) > expected_len:
                data = data[:expected_len]
            elif len(data) > 0:
                repeats = int(np.ceil(expected_len / len(data)))
                data = np.tile(data, repeats)[:expected_len]
            else:
                data = np.zeros(expected_len)
        channels[ch_key] = data.tolist()

    # 通道键统一为 ch1, ch2, ch3...
    # WTgearbox 用 c1/c2, CW 用 1/2/3
    normalized = {}
    for ch_key, data in channels.items():
        num = ch_key.replace("c", "").replace("ch", "")
        normalized[f"ch{num}"] = data

    # 不足通道用零填充
    if expected_channels and len(normalized) < expected_channels:
        for i in range(len(normalized) + 1, expected_channels + 1):
            normalized[f"ch{i}"] = [0.0] * expected_len

    return normalized


# ==================== 多数据源管理 ====================
class DataSourceManager:
    """管理多个数据源的扫描和分配"""

    def __init__(self):
        self.sources = {}  # {data_dir: groups_dict}
        self._scan_all()

    def _scan_all(self):
        for dev_id, (data_dir, prefix_filter, _) in DEVICE_DATA_MAP.items():
            if data_dir == "mixed":
                continue
            if data_dir not in self.sources:
                try:
                    groups = scan_data_groups(data_dir)
                    self.sources[data_dir] = groups
                    print(f"[数据源] {data_dir}: {len(groups)} 个工况组")
                except ValueError as e:
                    print(f"[数据源] {e}")

    def get_signal_for_device(self, device_id):
        """为指定设备生成信号数据"""
        if device_id not in DEVICE_DATA_MAP:
            raise ValueError(f"设备 {device_id} 未分配数据源")

        data_dir, prefix_filter, ch_count = DEVICE_DATA_MAP[device_id]

        if data_dir == "mixed":
            return self._generate_mixed_signal(device_id)

        groups = self.sources.get(data_dir, {})
        if not groups:
            raise ValueError(f"数据源 {data_dir} 未扫描到数据")

        candidates = [p for p in groups.keys() if p.startswith(prefix_filter)]
        if not candidates:
            raise ValueError(f"数据源 {data_dir} 中无匹配前缀 {prefix_filter}")

        prefix = random.choice(candidates)
        channels = load_group_data(groups, prefix, MAX_SECONDS_SIGNAL, ch_count)
        return channels, REAL_SAMPLE_RATE, MAX_SECONDS_SIGNAL

    def _generate_mixed_signal(self, device_id):
        """
        WTG-009 混合设备：
          ch1: CW 内圈故障 (I)
          ch2: WTgearbox 断齿 (Br)
          ch3: WTgearbox 磨损 (We)
        """
        duration = MAX_SECONDS_SIGNAL
        expected_len = REAL_SAMPLE_RATE * duration
        channels = {}

        # ch1: CW 内圈故障
        cw_groups = self.sources.get(CW_DATA_DIR, {})
        cw_candidates = [p for p in cw_groups.keys() if p.startswith("I")]
        if cw_candidates:
            cw_prefix = random.choice(cw_candidates)
            cw_data = load_group_data(cw_groups, cw_prefix, duration, 3)
            # 取第一个通道
            first_ch = sorted(cw_data.keys())[0]
            channels["ch1"] = cw_data[first_ch]
        else:
            channels["ch1"] = [0.0] * expected_len

        # ch2: WTgearbox 断齿
        wt_groups = self.sources.get(WTGEAR_DATA_DIR, {})
        br_candidates = [p for p in wt_groups.keys() if p.startswith("Br")]
        if br_candidates:
            br_prefix = random.choice(br_candidates)
            br_data = load_group_data(wt_groups, br_prefix, duration, 2)
            first_ch = sorted(br_data.keys())[0]
            channels["ch2"] = br_data[first_ch]
        else:
            channels["ch2"] = [0.0] * expected_len

        # ch3: WTgearbox 磨损
        we_candidates = [p for p in wt_groups.keys() if p.startswith("We")]
        if we_candidates:
            we_prefix = random.choice(we_candidates)
            we_data = load_group_data(wt_groups, we_prefix, duration, 2)
            first_ch = sorted(we_data.keys())[0]
            channels["ch3"] = we_data[first_ch]
        else:
            channels["ch3"] = [0.0] * expected_len

        return channels, REAL_SAMPLE_RATE, duration


# ==================== 设备配置 ====================
def fetch_device_config(device_id):
    try:
        response = requests.get(
            f"{CLOUD_CONFIG_URL}?device_id={device_id}",
            headers=EDGE_HEADERS, timeout=(CONNECT_TIMEOUT, 5)
        )
        if response.status_code == 200:
            data = response.json()
            config = data.get("data", {})
            return config if config else {}
    except requests.exceptions.Timeout:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [{device_id}] 拉取配置超时")
    except requests.exceptions.ConnectionError:
        pass
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [{device_id}] 拉取配置异常: {e}")
    return {}


# ==================== 上传 ====================
def upload_data(device_id, signals, sample_rate, is_special=False, task_id=None, config=None):
    comp_enabled = COMPRESSION_ENABLED
    ratio = DOWNSAMPLE_RATIO
    if config:
        cloud_comp = config.get("compression_enabled")
        if cloud_comp is not None:
            comp_enabled = bool(cloud_comp)

    if comp_enabled:
        compressed_info = compress_payload(signals, sample_rate=sample_rate, downsample_ratio=ratio)
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
            "channels": signals,
            "sample_rate": sample_rate,
            "is_special": 1 if is_special else 0,
        }

    if task_id:
        payload["task_id"] = task_id

    try:
        response = requests.post(
            CLOUD_INGEST_URL, json=payload, headers=EDGE_HEADERS,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT)
        )
        if response.status_code == 200:
            mode_str = "[特殊采集]" if is_special else "[自动采集]"
            orig = payload.get("original_points", len(next(iter(signals.values()))) if signals else 0)
            comp = payload.get("compressed_points", orig)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {mode_str} [{device_id}] 上传成功: "
                  f"{len(signals)} 通道, 原始 {orig} → 压缩后 {comp} 点, {sample_rate}Hz"
                  + (f", 任务ID={task_id}" if task_id else ""))
            return True
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [{device_id}] 上传失败: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [{device_id}] 连接失败")
        return False
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [{device_id}] 异常: {e}")
        return False


def poll_tasks(device_id):
    try:
        response = requests.get(
            f"{CLOUD_TASKS_URL}?device_id={device_id}",
            headers=EDGE_HEADERS, timeout=(CONNECT_TIMEOUT, 5)
        )
        if response.status_code == 200:
            data = response.json()
            task_data = data.get("data", {})
            if task_data.get("has_task"):
                return True, task_data
        return False, None
    except Exception:
        return False, None


# ==================== 主程序 ====================
def main():
    print("=" * 60)
    print("风机边端数据采集客户端（多数据源版）")
    print(f"设备列表: {', '.join(DEVICE_IDS)}")
    print(f"目标: {CLOUD_INGEST_URL}")
    print("=" * 60)
    print("提示: WTG-010 为离线模拟设备，不会上传数据")
    print("按 Ctrl+C 停止")
    print("=" * 60)

    ds_mgr = DataSourceManager()

    for dev_id in DEVICE_IDS:
        data_dir, prefix_filter, ch_count = DEVICE_DATA_MAP.get(dev_id, ("?", "?", 3))
        if data_dir == "mixed":
            print(f"[{dev_id}] 混合数据源: ch1=CW内圈, ch2=WTgear断齿, ch3=WTgear磨损, {ch_count}通道")
        else:
            print(f"[{dev_id}] 数据源: {os.path.basename(data_dir)}, 前缀: {prefix_filter}, {ch_count}通道")

    device_states = {}
    for dev_id in DEVICE_IDS:
        config = fetch_device_config(dev_id)
        device_states[dev_id] = {
            "last_upload_time": 0,
            "last_poll_time": 0,
            "last_config_fetch": 0,
            "config": config,
            "consecutive_failures": 0,
            "is_offline": False,
        }
        upload_interval = config.get("upload_interval", DEFAULT_UPLOAD_INTERVAL)
        task_poll_interval = config.get("task_poll_interval", DEFAULT_TASK_POLL_INTERVAL)
        print(f"[{dev_id}] 初始配置: 上传间隔={upload_interval}s, 轮询={task_poll_interval}s")

    while True:
        current_time = time.time()

        for dev_id in DEVICE_IDS:
            state = device_states[dev_id]
            config = state.get("config", {})
            poll_interval = OFFLINE_POLL_INTERVAL if state.get("is_offline") else config.get("task_poll_interval", DEFAULT_TASK_POLL_INTERVAL)

            if current_time - state["last_poll_time"] >= poll_interval:
                state["last_poll_time"] = current_time
                has_task, task_info = poll_tasks(dev_id)
                if has_task:
                    task_id = task_info.get("task_id")
                    try:
                        signals, sr, dur = ds_mgr.get_signal_for_device(dev_id)
                        success = upload_data(dev_id, signals, sr, is_special=True, task_id=task_id, config=config)
                        state["consecutive_failures"] = 0 if success else state.get("consecutive_failures", 0) + 1
                        state["last_upload_time"] = current_time
                    except Exception as e:
                        print(f"[{dev_id}] 特殊采集异常: {e}")

        for dev_id in DEVICE_IDS:
            state = device_states[dev_id]
            config = state.get("config", {})
            upload_interval = OFFLINE_POLL_INTERVAL if state.get("is_offline") else config.get("upload_interval", DEFAULT_UPLOAD_INTERVAL)
            window_seconds = config.get("window_seconds", DURATION)

            if current_time - state["last_upload_time"] >= upload_interval:
                state["last_upload_time"] = current_time
                try:
                    signals, sr, dur = ds_mgr.get_signal_for_device(dev_id)
                    success = upload_data(dev_id, signals, sr, config=config)
                    if success:
                        if state.get("is_offline"):
                            state["is_offline"] = False
                        state["consecutive_failures"] = 0
                    else:
                        state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
                        if state["consecutive_failures"] >= OFFLINE_THRESHOLD and not state.get("is_offline"):
                            state["is_offline"] = True
                except Exception as e:
                    print(f"[{dev_id}] 信号生成异常: {e}")

        for dev_id in DEVICE_IDS:
            state = device_states[dev_id]
            if current_time - state["last_config_fetch"] >= CONFIG_REFRESH_INTERVAL:
                state["last_config_fetch"] = current_time
                new_config = fetch_device_config(dev_id)
                if new_config:
                    old_interval = state["config"].get("upload_interval", DEFAULT_UPLOAD_INTERVAL)
                    new_interval = new_config.get("upload_interval", DEFAULT_UPLOAD_INTERVAL)
                    if old_interval != new_interval:
                        print(f"[配置更新] [{dev_id}] 上传间隔: {old_interval}s → {new_interval}s")
                    state["config"] = new_config

        time.sleep(0.5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n边端客户端已停止")