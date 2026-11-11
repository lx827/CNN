"""本机一次启动后端、已构建前端、真实硬件边端；复用已有服务。"""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import URLError
import webbrowser
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000"
AGENT = "dc24-" + re.sub(r"[^A-Za-z0-9_-]", "_", socket.gethostname())


def call(path, key, method="GET"):
    with urlopen(
        Request(
            BASE + "/api/acquisition" + path, headers={"X-Edge-Key": key}, method=method
        ),
        timeout=2,
    ) as response:
        return json.load(response).get("data")


def bundle_stale():
    front = ROOT / "wind-turbine-diagnosis"
    index = front / "dist/index.html"
    if not index.exists():
        return True
    sources = list((front / "src").rglob("*")) + [
        front / "index.html",
        front / "package.json",
    ]
    return any(
        p.is_file() and p.stat().st_mtime > index.stat().st_mtime for p in sources
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="只检查依赖，不启动服务或采集"
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="启动服务但不自动打开浏览器"
    )
    args = parser.parse_args()
    # 解释器:优先当前进程所在的 workspace 环境(uv run 启动时即如此),
    # 否则按平台回退到仓库根 .venv 内的解释器(uv sync 产出)
    fallback = (
        ROOT / ".venv/Scripts/python.exe"
        if os.name == "nt"
        else ROOT / ".venv/bin/python"
    )
    running = Path(sys.executable).resolve()
    workspace_python = (
        running if (ROOT / ".venv").resolve() in running.parents else fallback
    )
    if not workspace_python.exists():
        raise RuntimeError(
            "缺少 uv workspace 环境："
            + str(fallback)
            + "；请在仓库根目录运行 uv sync（或双击 start_dc24.bat，"
            "它会经 uv run 自动创建环境后再启动）"
        )
    vendor_root = (
        os.environ.get(
            "DC24_VENDOR_ROOT",
            dotenv_values(ROOT / "dc24/.env").get("DC24_VENDOR_ROOT"),
        )
        or ""
    )
    if vendor_root:
        vendor_path = Path(vendor_root).expanduser()
        if (
            not vendor_path.is_absolute()
            or not (vendor_path / "dll/JMServer.dll").is_file()
        ):
            raise RuntimeError(
                "DC24_VENDOR_ROOT 必须指向包含 dll/JMServer.dll 的原厂安装目录"
            )
    transport = "jmserver" if vendor_root else "python_tcp"
    print(
        "依赖路径检查通过；前端" + ("需要首次构建" if bundle_stale() else "可直接复用"),
        flush=True,
    )
    print(
        "边端采集模块：" + ("原厂 JMServer.dll" if vendor_root else "Python TCP"),
        flush=True,
    )
    if args.check:
        return
    if bundle_stale():
        node = shutil.which("node")
        vite = ROOT / "wind-turbine-diagnosis/node_modules/vite/bin/vite.js"
        if not node or not vite.exists():
            raise RuntimeError("前端需要构建，但未找到Node.js或已有Vite依赖")
        print("正在构建更新后的页面；后续启动将直接复用，不会每次重建。", flush=True)
        subprocess.run(
            [node, str(vite), "build"], cwd=ROOT / "wind-turbine-diagnosis", check=True
        )
    config = {**dotenv_values(ROOT / "cloud/.env"), **os.environ}
    key = config.get("EDGE_API_KEY") or "turbine-edge-secret"
    env = {
        **os.environ,
        **{k: str(v) for k, v in config.items() if v is not None},
        "USE_SQLITE": "true",
        "DATABASE_URL": "sqlite:///" + str(ROOT / "cloud/turbine.db"),
        "EDGE_API_KEY": key,
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "VIRTUAL_ENV": str(ROOT / ".venv"),
    }
    processes, logs = [], []
    started = time.monotonic()
    try:
        try:
            ready = call("/capabilities", key)
            if ready.get("service") != "cnn-dc24" or ready.get("version") != 2:
                raise RuntimeError("8000端口不是当前版本的采集后端")
            print("复用本机已启动的采集后端。", flush=True)
        except (URLError, TimeoutError):
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", 8000)) == 0:
                    raise RuntimeError(
                        "8000端口已被其他或旧版服务占用，请先结束旧服务；没有停止任何已有进程"
                    )
            output = ROOT / "tmp/dc24_live"
            output.mkdir(parents=True, exist_ok=True)
            log = (output / "local-backend.log").open("ab")
            logs.append(log)
            p = subprocess.Popen(
                [
                    str(workspace_python),
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8000",
                ],
                cwd=ROOT / "cloud",
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            processes.append(p)
            for _ in range(150):
                if p.poll() is not None:
                    raise RuntimeError(
                        "后端启动失败，见tmp/dc24_live/local-backend.log"
                    )
                try:
                    if call("/capabilities", key)["version"] == 2:
                        break
                except Exception:
                    pass
                time.sleep(0.2)
            else:
                raise RuntimeError("后端启动超时")
        agents = call("/agents", key)
        online = next((a for a in agents if a["id"] == AGENT and a["online"]), None)
        if online and online["state"].get("version", 0) < 3:
            raise RuntimeError(
                "旧输入配置的边端仍在运行，请先退出旧边端窗口，再双击start_dc24.bat加载IEPE配置；未停止已有进程"
            )
        if online and online["state"].get("transport", "python_tcp") != transport:
            raise RuntimeError(
                "已运行的边端使用另一种采集模块，请先退出其启动窗口，再双击start_dc24.bat"
            )
        if not online:
            output = ROOT / "tmp/dc24_live"
            output.mkdir(parents=True, exist_ok=True)
            log = (output / "local-agent.log").open("ab")
            logs.append(log)
            dc24_env = {
                **env,
                "VIRTUAL_ENV": str(ROOT / ".venv"),
                "DC24_VENDOR_ROOT": vendor_root,
            }
            p = subprocess.Popen(
                [
                    str(workspace_python),
                    str(ROOT / "dc24/dc24_agent.py"),
                    "--cloud",
                    BASE,
                    "--agent-id",
                    AGENT,
                    "--output",
                    str(ROOT / "data/dc24_recordings"),
                ],
                cwd=ROOT,
                env=dc24_env,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            processes.append(p)
            for _ in range(100):
                if p.poll() is not None:
                    raise RuntimeError("边端启动失败，见tmp/dc24_live/local-agent.log")
                if any(a["id"] == AGENT and a["online"] for a in call("/agents", key)):
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("边端未能上线")
        url = BASE + "/dc24/#/acquisition"
        print(f"已就绪，用时 {time.monotonic() - started:.1f} 秒：{url}", flush=True)
        print(
            "首次打开沿用系统登录。请选择示波或采集；此入口只连接真实DC24。Ctrl+C停止本次启动的服务。",
            flush=True,
        )
        if not args.no_browser:
            if os.name == "nt":
                os.startfile(
                    url, show_cmd=1
                )  # 用户明确要求弹出前端，显示正常浏览器窗口。
            elif not webbrowser.open(url):
                print("系统未能打开浏览器，请手动打开上面的本机地址。", flush=True)
        while all(p.poll() is None for p in processes):
            time.sleep(0.5)
    finally:
        # 先让设备正常停止并保存，随后只清理本启动器拥有的进程。
        if processes:
            try:
                current = call(f"/agents/{AGENT}/control", key).get("session")
                if current:
                    call(f"/sessions/{current['id']}/stop", key, "POST")
                    for wait_index in range(1200):
                        if call(f"/sessions/{current['id']}", key)["status"] in (
                            "stopped",
                            "failed",
                        ):
                            break
                        if wait_index and wait_index % 50 == 0:
                            print("设备正在停止或保存已有数据，请稍候。", flush=True)
                        time.sleep(0.1)
            except Exception:
                pass
        for p in reversed(processes):
            if p.poll() is None:
                p.terminate()
                p.wait(timeout=10)
        for log in logs:
            log.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已停止本次启动的现场服务，原始文件保留。")
    except Exception as exc:
        print("[启动失败] " + str(exc), file=sys.stderr)
        sys.exit(1)
