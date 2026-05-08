"""
边端采集客户端（多设备版本）
模拟安装在风机现场的工业网关，负责：
1. 生成风机振动信号
2. 打包并压缩数据
3. 通过 HTTP POST 上传到云端

支持多设备：一个边端实例可同时为多个设备（WTG-001 ~ WTG-005）采集和上传数据。
支持云端动态配置：启动时及运行中定期从云端拉取上传间隔等参数。

运行方式：python edge_client.py
"""
import os
import time
import requests
from datetime import datetime
from dotenv import load_dotenv
from signal_generator import generate_signals
from compressor import compress_payload

# 加载 .env 文件（如果存在）
load_dotenv()

# 从环境变量读取配置
CLOUD_BASE_URL = os.getenv("CLOUD_BASE_URL", "http://localhost:8000")
CLOUD_INGEST_URL = os.getenv("CLOUD_INGEST_URL", f"{CLOUD_BASE_URL}/api/ingest/")
CLOUD_TASKS_URL = os.getenv("CLOUD_TASKS_URL", f"{CLOUD_BASE_URL}/api/collect/tasks")
CLOUD_CONFIG_URL = os.getenv("CLOUD_CONFIG_URL", f"{CLOUD_BASE_URL}/api/devices/edge/config")

# 支持多设备：DEVICE_IDS=WTG-001,WTG-002,WTG-003,WTG-004,WTG-005
# 兼容旧配置 DEVICE_ID（单设备）
DEVICE_IDS_STR = os.getenv("DEVICE_IDS", os.getenv("DEVICE_ID", "WTG-001"))
DEVICE_IDS = [d.strip() for d in DEVICE_IDS_STR.split(",") if d.strip()]

# 本地默认值（当云端不可达或设备未配置时使用）
DEFAULT_UPLOAD_INTERVAL = int(os.getenv("UPLOAD_INTERVAL", "10"))
DEFAULT_TASK_POLL_INTERVAL = int(os.getenv("TASK_POLL_INTERVAL", "5"))
COMPRESSION_ENABLED = os.getenv("COMPRESSION_ENABLED", "true").lower() in ("true", "1", "yes")
SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "25600"))
DURATION = int(os.getenv("DURATION", "10"))
DOWNSAMPLE_RATIO = int(os.getenv("DOWNSAMPLE_RATIO", "8"))
CHANNEL_COUNT = int(os.getenv("CHANNEL_COUNT", "3"))


def get_device_channel_count(device_id):
    """
    获取指定设备的通道数。
    优先读取环境变量 WTG-XXX_CHANNELS，没有则使用全局 CHANNEL_COUNT。
    """
    env_key = f"{device_id}_CHANNELS".replace("-", "_").upper()
    val = os.getenv(env_key)
    if val:
        try:
            return int(val)
        except ValueError:
            pass
    return CHANNEL_COUNT

# 配置刷新间隔（秒）
CONFIG_REFRESH_INTERVAL = 30


def fetch_device_config(device_id):
    """
    从云端拉取某设备的最新配置
    """
    try:
        response = requests.get(
            f"{CLOUD_CONFIG_URL}?device_id={device_id}",
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


def upload_data(device_id, is_special=False, task_id=None, sample_rate=None, duration=None):
    """
    生成并上传一批数据（指定设备）
    """
    sr = sample_rate or SAMPLE_RATE
    dur = duration or DURATION

    signals = generate_signals(mode="auto", channel_count=get_device_channel_count(device_id))

    if COMPRESSION_ENABLED:
        compressed_info = compress_payload(
            signals,
            sample_rate=sr,
            downsample_ratio=DOWNSAMPLE_RATIO
        )
        payload = {
            "device_id": device_id,
            "timestamp": datetime.utcnow().isoformat(),
            "sample_rate": sr,
            "is_special": 1 if is_special else 0,
            **compressed_info
        }
    else:
        payload = {
            "device_id": device_id,
            "timestamp": datetime.utcnow().isoformat(),
            "channels": signals,
            "sample_rate": sr,
            "is_special": 1 if is_special else 0,
        }

    if task_id:
        payload["task_id"] = task_id

    try:
        response = requests.post(CLOUD_INGEST_URL, json=payload, timeout=15)
        if response.status_code == 200:
            mode_str = "[特殊采集]" if is_special else "[自动采集]"
            orig = payload.get("original_points", len(next(iter(signals.values()))) if signals else 0)
            comp = payload.get("compressed_points", orig)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {mode_str} [{device_id}] 上传成功: {len(signals)} 通道, "
                  f"原始 {orig} 点 → 压缩后 {comp} 点, "
                  f"采样率 {sr}Hz, 时长 {dur}s"
                  + (f", 任务ID={task_id}" if task_id else ""))
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
    """
    轮询某设备的待采集任务
    """
    try:
        response = requests.get(
            f"{CLOUD_TASKS_URL}?device_id={device_id}",
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


def main():
    print("=" * 60)
    print("风机边端数据采集客户端（多设备版）")
    print(f"设备列表: {', '.join(DEVICE_IDS)}")
    print(f"目标: {CLOUD_INGEST_URL}")
    print(f"默认采集频率: 每 {DEFAULT_UPLOAD_INTERVAL} 秒上传一批/设备")
    print(f"默认任务轮询频率: 每 {DEFAULT_TASK_POLL_INTERVAL} 秒查询一次")
    print(f"通道: {CHANNEL_COUNT} 通道")
    print(f"采样: {SAMPLE_RATE} Hz × {DURATION} s = {SAMPLE_RATE * DURATION} 点/通道")
    print(f"压缩: {'已启用（降采样 ' + str(DOWNSAMPLE_RATIO) + 'x + msgpack + zlib）' if COMPRESSION_ENABLED else '已关闭（原图JSON）'}")
    print(f"云端配置: 每 {CONFIG_REFRESH_INTERVAL} 秒刷新一次")
    print("=" * 60)
    print("提示: 请确保云端服务已启动 (cd cloud && python -m app.main)")
    print("按 Ctrl+C 停止")
    print("=" * 60)

    # 每个设备独立的上传时间戳、轮询时间戳和配置缓存
    device_states = {}
    for dev_id in DEVICE_IDS:
        # 启动时先拉取一次配置
        config = fetch_device_config(dev_id)
        upload_interval = config.get("upload_interval", DEFAULT_UPLOAD_INTERVAL)
        task_poll_interval = config.get("task_poll_interval", DEFAULT_TASK_POLL_INTERVAL)

        device_states[dev_id] = {
            "last_upload_time": 0,
            "last_poll_time": 0,
            "last_config_fetch": 0,
            "config": config,
        }

        print(f"[{datetime.now().strftime('%H:%M:%S')}] [{dev_id}] 初始配置: "
              f"上传间隔={upload_interval}s, 轮询间隔={task_poll_interval}s")

    while True:
        current_time = time.time()

        # 1. 轮询所有设备的采集任务（手动触发）
        for dev_id in DEVICE_IDS:
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
                    success = upload_data(
                        device_id=dev_id,
                        is_special=True,
                        task_id=task_id,
                        sample_rate=task_sr,
                        duration=task_dur
                    )
                    if success:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] [任务完成] [{dev_id}] 特殊采集数据已上传")
                    else:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] [任务失败] [{dev_id}] 特殊采集中断")
                    state["last_upload_time"] = current_time

        # 2. 普通定时采集（自动上传），每个设备独立判断
        for dev_id in DEVICE_IDS:
            state = device_states[dev_id]
            config = state.get("config", {})
            upload_interval = config.get("upload_interval", DEFAULT_UPLOAD_INTERVAL)

            if current_time - state["last_upload_time"] >= upload_interval:
                state["last_upload_time"] = current_time
                upload_data(device_id=dev_id, is_special=False)

        # 3. 定期刷新云端配置
        for dev_id in DEVICE_IDS:
            state = device_states[dev_id]
            if current_time - state["last_config_fetch"] >= CONFIG_REFRESH_INTERVAL:
                state["last_config_fetch"] = current_time
                new_config = fetch_device_config(dev_id)
                if new_config:
                    old_interval = state["config"].get("upload_interval", DEFAULT_UPLOAD_INTERVAL)
                    new_interval = new_config.get("upload_interval", DEFAULT_UPLOAD_INTERVAL)
                    if old_interval != new_interval:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] [配置更新] [{dev_id}] "
                              f"上传间隔: {old_interval}s → {new_interval}s")
                    state["config"] = new_config

        # 小睡眠避免CPU空转
        time.sleep(0.5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n边端客户端已停止")
