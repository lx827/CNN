"""用真实 Vite 的浏览器探针验证快速启动只打开一次页面，不弹出实际浏览器。"""
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import time
import unittest
from urllib.request import urlopen
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "edge"))
import edge_client as edge
import replay


class BrowserOpenTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt" and shutil.which("node"), "需要 Windows 与 Node.js")
    def test_new_vite_does_not_open_second_browser(self):
        if not (ROOT / "wind-turbine-diagnosis/node_modules/vite/bin/vite.js").is_file():
            self.skipTest("需要 Vite 依赖")
        (ROOT / "tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as directory:
            directory = Path(directory)
            marker = directory / "vite-browser-opened.txt"
            probe = directory / "browser-probe.js"
            probe.write_text(
                "require('node:fs').writeFileSync(" + json.dumps(str(marker)) + ", 'opened');",
                encoding="utf-8",
            )
            config = directory / "vite.config.mjs"
            config.write_text("export default {server: {open: true}}", encoding="utf-8")
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            original_popen = replay.subprocess.Popen
            processes = []

            def spawn(*args, **kwargs):
                command = args[0]
                if str(command[0]).lower().endswith("node.exe"):
                    command = [*command, "--port", str(port), "--config", str(config)]
                    process = original_popen(command, **kwargs)
                    processes.append(process)
                    return process
                return original_popen(*args, **kwargs)

            def ready():
                try:
                    with urlopen(f"http://127.0.0.1:{port}/@vite/client", timeout=0.5) as response:
                        return response.status == 200
                except Exception:
                    return False

            def finish_edge():
                # 给 Vite 的异步浏览器脚本足够时间写入探针；不访问云端或上传。
                deadline = time.monotonic() + 1
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.05)

            with patch.dict(os.environ, {"BROWSER": str(probe)}), \
                    patch.object(sys, "argv", ["replay.py", "--dataset", "cw"]), \
                    patch.object(replay, "check_data"), patch.object(replay, "check_cloud"), \
                    patch.object(replay, "frontend_ready", side_effect=ready), \
                    patch.object(replay.subprocess, "Popen", side_effect=spawn), \
                    patch.object(replay.webbrowser, "open") as browser_open, \
                    patch.object(edge, "main", side_effect=finish_edge):
                replay.main()
                self.assertEqual(os.environ["BROWSER"], str(probe), "不能修改父进程浏览器设置")
            browser_open.assert_called_once_with("http://127.0.0.1:3000")
            self.assertFalse(marker.exists(), "Vite 又打开了一次浏览器")
            self.assertEqual(len(processes), 1)
            self.assertIsNotNone(processes[0].poll())

    def test_existing_frontend_opens_once_without_spawning_vite(self):
        with patch.object(sys, "argv", ["replay.py", "--dataset", "cw"]), \
                patch.object(replay, "check_data"), patch.object(replay, "check_cloud"), \
                patch.object(replay, "frontend_ready", return_value=True), \
                patch.object(replay.subprocess, "Popen") as spawn, \
                patch.object(replay.webbrowser, "open") as browser_open, \
                patch.object(edge, "main"):
            replay.main()
        spawn.assert_not_called()
        browser_open.assert_called_once_with("http://127.0.0.1:3000")


if __name__ == "__main__":
    unittest.main()
