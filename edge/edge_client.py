"""
边端采集客户端（多设备版本）
模拟安装在风机现场的工业网关，负责：
1. 生成风机振动信号（模拟）或读取本地真实 .npy 数据
2. 打包并压缩数据
3. 通过 HTTP POST 上传到云端

支持多设备：一个边端实例可同时为多个设备（WTG-001 ~ WTG-005）采集和上传数据。
支持云端动态配置：启动时及运行中定期从云端拉取上传间隔等参数。
支持真实数据：通过 USE_REAL_DATA=true 切换到 .npy 文件读取模式。

运行方式：python edge_client.py
"""
import os
import time
import random
import glob
import requests
import numpy as np
from datetime import datetime
from dotenv import load_dotenv
from signal_generator import generate_signals
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

# 支持多设备：DEVICE_IDS=WTG-001,WTG-002,WTG-003,WTG-004,WTG-005
# 兼容旧配置 DEVICE_ID（单设备）
DEVICE_IDS_STR = os.getenv("DEVICE_IDS", os.getenv("DEVICE_ID", "WTG-001"))
DEVICE_IDS = [d.strip() for d in DEVICE_IDS_STR.split(",") if d.strip()]

# ========== 模拟信号参数 ==========
DEFAULT_UPLOAD_INTERVAL = int(os.getenv("UPLOAD_INTERVAL", "10"))
DEFAULT_TASK_POLL_INTERVAL = int(os.getenv("TASK_POLL_INTERVAL", "5"))
COMPRESSION_ENABLED = os.getenv("COMPRESSION_ENABLED", "true").lower() in ("true", "1", "yes")
SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "25600"))
DURATION = int(os.getenv("DURATION", "10"))
DOWNSAMPLE_RATIO = int(os.getenv("DOWNSAMPLE_RATIO", "8"))
CHANNEL_COUNT = int(os.getenv("CHANNEL_COUNT", "3"))

# ========== 真实数据参数 ==========
USE_REAL_DATA = os.getenv("USE_REAL_DATA", "false").lower() in ("true", "1", "yes")
DATA_DIR = os.getenv("DATA_DIR", r"D:\code\wavelet_study\dataset\CW\down8192_CW")
REAL_SAMPLE_RATE = int(os.getenv("REAL_SAMPLE_RATE", "8192"))
REAL_DURATION = 10  # 真实数据固定 10 秒

# ========== 模拟离线设备 ==========
SIMULATE_OFFLINE_DEVICE = os.getenv("SIMULATE_OFFLINE_DEVICE", "").strip()

# ========== 边端认证 ==========
EDGE_API_KEY = os.getenv("EDGE_API_KEY", "turbine-edge-secret")
EDGE_HEADERS = {"X-Edge-Key": EDGE_API_KEY}

# 配置刷新间隔（秒）
CONFIG_REFRESH_INTERVAL = 30


# ==================== 数据扫描与读取（真实数据模式）====================

def scan_data_groups(data_dir):
    """
    扫描数据目录，按文件名前缀分组
    Returns: {"H-A": {"1": "path/to/H-A-1.npy", "2": "...", "3": "..."}, ...}
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
        prefix = "-".join(parts[:-1])
        ch = parts[-1]
        groups.setdefault(prefix, {})[ch] = fpath

    valid_groups = {k: v for k, v in groups.items() if len(v) >= 3}
    return valid_groups


def load_group_data(groups, prefix, target_duration=None):
    """
    读取指定工况前缀的 3 个通道数据
    target_duration: 云端配置的窗口秒数，覆盖 REAL_DURATION
    Returns: {"ch1": [float, ...], "ch2": [...], "ch3": [...]}
    """
    if prefix not in groups:
        raise ValueError(f"[错误] 工况 {prefix} 不存在")

    duration = target_duration if target_duration is not None else REAL_DURATION
    expected_len = REAL_SAMPLE_RATE * duration

    channels = {}
    for ch_num, fpath in sorted(groups[prefix].items()):
        data = np.load(fpath)
        if len(data) != expected_len:
            if len(data) > expected_len:
                data = data[:expected_len]
            else:
                # 数据不足时循环填充或零填充
                if len(data) > 0:
                    repeats = int(np.ceil(expected_len / len(data)))
                    data = np.tile(data, repeats)[:expected_len]
                else:
                    data = np.zeros(expected_len)
        key = f"ch{ch_num}"
        channels[key] = data.tolist()
    return channels


# ==================== 设备配置 ====================

def get_device_channel_count(device_id):
    """获取指定设备的通道数"""
    env_key = f"{device_id}_CHANNELS".replace("-", "_").upper()
    val = os.getenv(env_key)
    if val:
        try:
            return int(val)
        except ValueError:
            pass
    return CHANNEL_COUNT


def fetch_device_config(device_id):
    """从云端拉取某设备的最新配置"""
    try:
        response = requests.get(
            f"{CLOUD_CONFIG_URL}?device_id={device_id}",
            headers=EDGE_HEADERS,
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            config = data.get("data", {})
            if config:
                return config
    except requests.exceptions.ConnectionError:
        pass
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [{device_id}] 拉取配置异常: {e}")
    return {}


# ==================== 数据生成 ====================

def generate_device_signals(device_id, sample_rate, duration):
    """
    根据模式生成或读取信号
    - USE_REAL_DATA=true: 从 .npy 文件读取
    - USE_REAL_DATA=false: 用 signal_generator 模拟
    """
    if USE_REAL_DATA:
        char = device_data_assignments.get(device_id)
        if not char:
            raise ValueError(f"设备 {device_id} 未分配工况")
        # 从该前缀组中随机选一个具体工况（如 H 组下随机选 H-A/H-B/H-C/H-D）
        candidates = [p for p in data_groups.keys() if p.startswith(char)]
        prefix = random.choice(candidates)
        # 使用传入的 duration（云端配置的 window_seconds），而非固定 REAL_DURATION
        data = load_group_data(data_groups, prefix, target_duration=duration)
        return data, REAL_SAMPLE_RATE, duration
    else:
        signals = generate_signals(
            mode="auto",
            channel_count=get_device_channel_count(device_id),
            duration=duration,
            sample_rate=sample_rate
        )
        return signals, sample_rate, duration


# ==================== 上传 ====================

def upload_data(device_id, signals, sample_rate, is_special=False, task_id=None, config=None):
    """
    上传一批数据到云端
    config: 云端下发的配置字典，控制压缩行为
    """
    # 压缩参数优先使用云端配置，fallback 到 .env
    comp_enabled = COMPRESSION_ENABLED
    ratio = DOWNSAMPLE_RATIO
    if config:
        # 云端 compression_enabled 可能是 bool 或 int
        cloud_comp = config.get("compression_enabled")
        if cloud_comp is not None:
            comp_enabled = bool(cloud_comp)
        cloud_ratio = config.get("downsample_ratio")
        if cloud_ratio is not None:
            ratio = int(cloud_ratio)

    # 真实数据模式下：若云端未指定压缩比，默认不压缩（ratio=1）
    if USE_REAL_DATA and config and config.get("downsample_ratio") is None:
        ratio = 1

    if comp_enabled:
        compressed_info = compress_payload(
            signals,
            sample_rate=sample_rate,
            downsample_ratio=ratio
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
            "channels": signals,
            "sample_rate": sample_rate,
            "is_special": 1 if is_special else 0,
        }

    if task_id:
        payload["task_id"] = task_id

    try:
        response = requests.post(
            CLOUD_INGEST_URL, json=payload, headers=EDGE_HEADERS, timeout=15
        )
        if response.status_code == 200:
            mode_str = "[特殊采集]" if is_special else "[自动采集]"
            orig = payload.get("original_points", len(next(iter(signals.values()))) if signals else 0)
            comp = payload.get("compressed_points", orig)
            source = "[真实数据]" if USE_REAL_DATA else "[模拟信号]"
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] {mode_str} {source} [{device_id}] 上传成功: "
                f"{len(signals)} 通道, 原始 {orig} 点 → 压缩后 {comp} 点, "
                f"采样率 {sample_rate}Hz"
                + (f", 任务ID={task_id}" if task_id else "")
            )
            return True
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [{device_id}] 上传失败: {response.status_code} - {response.text}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [{device_id}] 连接失败: 云端服务未启动？")
        return False
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [{device_id}] 异常: {e}")
        return False


def poll_tasks(device_id):
    """轮询某设备的待采集任务"""
    try:
        response = requests.get(
            f"{CLOUD_TASKS_URL}?device_id={device_id}",
            headers=EDGE_HEADERS,
            timeout=5
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

# 全局状态：真实数据工况分配
data_groups = {}
device_data_assignments = {}


def main():
    global data_groups, device_data_assignments

    print("=" * 60)
    print("风机边端数据采集客户端（多设备版）")
    print(f"设备列表: {', '.join(DEVICE_IDS)}")
    if SIMULATE_OFFLINE_DEVICE:
        print(f"[模拟离线] 设备 {SIMULATE_OFFLINE_DEVICE} 被配置为模拟离线（不上传数据）")
    print(f"目标: {CLOUD_INGEST_URL}")
    print(f"数据模式: {'真实数据 (.npy)' if USE_REAL_DATA else '模拟信号 (生成器)'}")

    if USE_REAL_DATA:
        print(f"数据目录: {DATA_DIR}")
        print(f"真实采样率: {REAL_SAMPLE_RATE} Hz")
        # 扫描数据
        data_groups = scan_data_groups(DATA_DIR)
        # 按前缀首字母分组（H/I/O）
        prefix_by_char = {}
        for p in data_groups.keys():
            prefix_by_char.setdefault(p[0], []).append(p)
        sorted_chars = sorted(prefix_by_char.keys())
        print(f"有效工况组: {len(data_groups)} 组，前缀分类 -> { {k: v for k, v in prefix_by_char.items()} }")
        # 分配前缀：第1台→H（健康），其余设备→故障数据（I/O 循环）
        fault_chars = [c for c in sorted_chars if c != 'H']
        for i, dev_id in enumerate(DEVICE_IDS):
            if i == 0:
                char = 'H'
            else:
                char = fault_chars[(i - 1) % len(fault_chars)] if fault_chars else sorted_chars[i % len(sorted_chars)]
            device_data_assignments[dev_id] = char
            print(f"[{dev_id}] 分配前缀组: {char}（含 {prefix_by_char[char]}）")
    else:
        print(f"采样: {SAMPLE_RATE} Hz × {DURATION} s = {SAMPLE_RATE * DURATION} 点/通道")

    print(f"压缩: {'已启用' if COMPRESSION_ENABLED else '已关闭'}")
    print(f"云端配置: 每 {CONFIG_REFRESH_INTERVAL} 秒刷新一次")
    print("=" * 60)
    print("提示: 请确保云端服务已启动 (cd cloud && python -m app.main)")
    print("按 Ctrl+C 停止")
    print("=" * 60)

    # 每个设备独立的上传时间戳、轮询时间戳和配置缓存
    device_states = {}
    for dev_id in DEVICE_IDS:
        config = fetch_device_config(dev_id)
        upload_interval = config.get("upload_interval", DEFAULT_UPLOAD_INTERVAL)
        task_poll_interval = config.get("task_poll_interval", DEFAULT_TASK_POLL_INTERVAL)
        window_seconds = config.get("window_seconds", DURATION)

        device_states[dev_id] = {
            "last_upload_time": 0,
            "last_poll_time": 0,
            "last_config_fetch": 0,
            "config": config,
        }

        print(f"[{datetime.now().strftime('%H:%M:%S')}] [{dev_id}] 初始配置: "
              f"上传间隔={upload_interval}s, 轮询间隔={task_poll_interval}s, 窗口={window_seconds}s")

    while True:
        current_time = time.time()

        # 1. 轮询所有设备的采集任务（手动触发）
        for dev_id in DEVICE_IDS:
            if SIMULATE_OFFLINE_DEVICE and dev_id == SIMULATE_OFFLINE_DEVICE:
                continue

            state = device_states[dev_id]
            config = state.get("config", {})
            poll_interval = config.get("task_poll_interval", DEFAULT_TASK_POLL_INTERVAL)

            if current_time - state["last_poll_time"] >= poll_interval:
                state["last_poll_time"] = current_time
                has_task, task_info = poll_tasks(dev_id)
                if has_task:
                    task_id = task_info.get("task_id")
                    task_sr = task_info.get("sample_rate", SAMPLE_RATE)
                    task_dur = task_info.get("duration", DURATION)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] [任务响应] [{dev_id}] 收到采集任务 ID={task_id}, "
                          f"采样率={task_sr}Hz, 时长={task_dur}s")

                    try:
                        signals, sr, dur = generate_device_signals(dev_id, task_sr, task_dur)
                        success = upload_data(
                            device_id=dev_id,
                            signals=signals,
                            sample_rate=sr,
                            is_special=True,
                            task_id=task_id,
                            config=state.get("config")
                        )
                        if success:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] [任务完成] [{dev_id}] 特殊采集数据已上传")
                        else:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] [任务失败] [{dev_id}] 特殊采集中断")
                        state["last_upload_time"] = current_time
                    except Exception as e:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] [任务失败] [{dev_id}] 信号生成/读取异常: {e}")

        # 2. 普通定时采集（自动上传），每个设备独立判断
        for dev_id in DEVICE_IDS:
            if SIMULATE_OFFLINE_DEVICE and dev_id == SIMULATE_OFFLINE_DEVICE:
                continue

            state = device_states[dev_id]
            config = state.get("config", {})
            upload_interval = config.get("upload_interval", DEFAULT_UPLOAD_INTERVAL)
            window_seconds = config.get("window_seconds", DURATION)

            if current_time - state["last_upload_time"] >= upload_interval:
                state["last_upload_time"] = current_time
                try:
                    signals, sr, dur = generate_device_signals(dev_id, SAMPLE_RATE, window_seconds)
                    upload_data(
                        device_id=dev_id,
                        signals=signals,
                        sample_rate=sr,
                        is_special=False,
                        config=state.get("config")
                    )
                except Exception as e:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{dev_id}] 信号生成/读取异常: {e}")

        # 3. 定期刷新云端配置
        for dev_id in DEVICE_IDS:
            state = device_states[dev_id]
            if current_time - state["last_config_fetch"] >= CONFIG_REFRESH_INTERVAL:
                state["last_config_fetch"] = current_time
                new_config = fetch_device_config(dev_id)
                if new_config:
                    old_interval = state["config"].get("upload_interval", DEFAULT_UPLOAD_INTERVAL)
                    new_interval = new_config.get("upload_interval", DEFAULT_UPLOAD_INTERVAL)
                    old_window = state["config"].get("window_seconds", DURATION)
                    new_window = new_config.get("window_seconds", DURATION)
                    if old_interval != new_interval:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] [配置更新] [{dev_id}] "
                              f"上传间隔: {old_interval}s → {new_interval}s")
                    if old_window != new_window:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] [配置更新] [{dev_id}] "
                              f"窗口时长: {old_window}s → {new_window}s")
                    state["config"] = new_config

        # 小睡眠避免CPU空转
        time.sleep(0.5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n边端客户端已停止")
