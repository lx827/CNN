"""本机快速启动：选择数据集、检查数据与云端归属，再启动前端和边端。"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.request import urlopen
import webbrowser


ROOT = Path(__file__).resolve().parents[1]
HUST_PARAMS = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}


def check_data(edge):
    """验证所有工况的三通道和有限实数信号，不上传、不填充缺失通道。"""
    manager = edge.DataSourceManager()
    for dev, (directory, label, _) in edge.DEVICE_DATA_MAP.items():
        groups = manager.sources.get(directory, {})
        candidates = edge.matching_groups(groups, directory, label)
        if not candidates:
            raise ValueError(f"{dev}: 没有 {label} 工况，请检查数据目录 {directory}")
        expected = {"X", "Y", "Z"} if dev.startswith("HUST-") else {"1", "2", "3"}
        for prefix in candidates:
            if set(groups[prefix]) != expected:
                raise ValueError(f"{prefix}: 需要完整通道 {sorted(expected)}")
            for path in groups[prefix].values():
                data = edge.np.load(path, allow_pickle=False)
                if (data.ndim != 1 or not data.size or data.dtype.kind not in "fiu"
                        or not edge.np.isfinite(data).all()):
                    raise ValueError(f"无效的一维有限实数振动数据: {path}")
        print(f"[检查通过] {dev}: {len(candidates)} 个工况，3 通道，8192 Hz")
    return manager


def check_cloud(edge):
    """上传前确认所有设备已注册，HUSTbear 参数与轴方向匹配，禁止混写 CW。"""
    response = edge.requests.get(
        f"{edge.CLOUD_BASE_URL.rstrip('/')}/api/devices/",
        headers=edge.EDGE_HEADERS, timeout=(10, 30),
    )
    response.raise_for_status()
    devices = {d["device_id"]: d for d in response.json()["data"]}
    for dev in edge.DEVICE_IDS:
        if dev not in devices:
            raise ValueError(f"云端缺少 {dev}。请先按启动说明初始化 HUSTbear 设备，未上传任何数据。")
        if dev.startswith("HUST-"):
            item = devices[dev]
            if (item.get("bearing_params") != HUST_PARAMS or item.get("gear_teeth")
                    or item.get("channel_names") != {"1": "X", "2": "Y", "3": "Z"}
                    or item.get("sample_rate") != 8192 or item.get("channel_count") != 3):
                raise ValueError(f"{dev}: 云端轴承参数、采样率或轴方向不匹配，请核对配置。")
    print("[检查通过] 云端设备归属与参数")


def frontend_ready():
    """确认本机 3000 端口上的服务是 Vite，避免复用不明服务。"""
    try:
        with urlopen("http://127.0.0.1:3000/@vite/client", timeout=2) as response:
            return response.status == 200 and b"WebSocket" in response.read()
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=["cw", "hustbear", "both"])
    parser.add_argument("--check", action="store_true", help="仅检查本地数据，不联网、不上传")
    parser.add_argument("--once", action="store_true", help="每台设备上传一批后退出，不启动前端")
    parser.add_argument("--no-frontend", action="store_true", help="仅运行边端，手动打开云端页面")
    args = parser.parse_args()
    dataset = args.dataset
    if not dataset:
        print("边端回放数据集：\n  1. CW（三台设备）\n  2. HUSTbear（五台独立设备）\n  3. 两份同时回放（八台设备）")
        dataset = {"1": "cw", "2": "hustbear", "3": "both"}.get(input("请选择 1/2/3：").strip())
        if not dataset:
            raise ValueError("未选择有效数据集，已退出")

    # 启动器明确使用项目内的数据，防止旧终端或 .env 中的备份路径继续生效。
    os.environ.update({
        "REPLAY_DATASET": dataset,
        "CNN_DATA_ROOT": str(ROOT / "data"),
        "CW_DATA_DIR": str(ROOT / "data/CW/down8192_CW"),
        "HUSTBEAR_DIR": str(ROOT / "data/HUSTbear/down8192"),
        "REAL_SAMPLE_RATE": "8192",
    })
    import edge_client as edge
    if edge.REAL_SAMPLE_RATE != 8192:
        raise ValueError("回放数据采样率必须为 8192 Hz")
    manager = check_data(edge)
    if args.check:
        print("仅本地检查完成，未联网、未上传。")
        return
    check_cloud(edge)
    if args.once:
        failures = []
        for dev in edge.DEVICE_IDS:
            signals, rate, _ = manager.get_signal_for_device(dev)
            if not edge.upload_data(dev, signals, rate, config=edge.fetch_device_config(dev)):
                failures.append(dev)
        if failures:
            raise RuntimeError(f"上传失败: {', '.join(failures)}")
        return

    proc = None
    log = None
    try:
        if not args.no_frontend:
            if not frontend_ready():
                front = ROOT / "wind-turbine-diagnosis"
                if not (front / "node_modules").is_dir():
                    raise ValueError("缺少前端依赖，请在前端目录执行 npm install")
                node = shutil.which("node")
                vite = front / "node_modules/vite/bin/vite.js"
                if not node or not vite.is_file():
                    raise ValueError("找不到 Node.js 或 Vite，请检查前端环境")
                (ROOT / "tmp").mkdir(exist_ok=True)
                log = (ROOT / "tmp/quick-start-frontend.log").open("wb")
                proc = subprocess.Popen(
                    # 直接持有 Vite 的 Node 进程，避免 cmd/npm 提前退出后遗留子进程。
                    [node, str(vite), "--host", "127.0.0.1", "--strictPort"],
                    cwd=front, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                for _ in range(30):
                    if proc.poll() is not None:
                        raise RuntimeError("前端启动失败，请检查 tmp/quick-start-frontend.log（可能端口被占用）")
                    if frontend_ready():
                        break
                    time.sleep(0.5)
                else:
                    raise RuntimeError("前端启动超时，请检查 tmp/quick-start-frontend.log")
            webbrowser.open("http://127.0.0.1:3000")
        print("开始回放，上传间隔以云端配置为准。按 Ctrl+C 停止。")
        edge.main()
    finally:
        # 只停止本次启动器创建的前端进程树，保留用户原已运行的前端。
        if proc and proc.poll() is None:
            stopped = subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if stopped.returncode != 0 and proc.poll() is None:
                proc.terminate()
            proc.wait(timeout=10)
        if log:
            log.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已停止本机回放。")
    except Exception as exc:
        print(f"[启动失败] {exc}", file=sys.stderr)
        sys.exit(1)
