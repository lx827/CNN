"""实际cmd入口检查：不打开浏览器或连接硬件，防止批处理编码/行尾回归。"""

import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import MagicMock, mock_open, patch
from urllib.error import URLError
import importlib.util

ROOT = Path(__file__).resolve().parents[2]


class DC24StartTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows批处理入口")
    def test_batch_check_entry_runs_real_launcher_without_starting_services(self):
        if not (ROOT / ".venv/Scripts/python.exe").exists():
            self.skipTest("本机 uv workspace 环境不存在（先 uv sync）")
        result = subprocess.run(
            ["cmd", "/d", "/c", "call", str(ROOT / "start_dc24.bat"), "--check"],
            cwd=ROOT,
            capture_output=True,
            timeout=20,
        )
        output = result.stdout.decode("utf-8", errors="replace")
        self.assertEqual(
            result.returncode,
            0,
            output + result.stderr.decode("utf-8", errors="replace"),
        )
        self.assertIn("依赖路径检查通过", output)
        self.assertNotIn("not recognized", output)

    def test_launcher_forces_local_mode_and_loopback_backend(self):
        spec = importlib.util.spec_from_file_location(
            "dc24_start", ROOT / "scripts/dc24_start.py"
        )
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        process = MagicMock()
        process.poll.side_effect = [None, 0, 0]
        online_agent = {
            "id": launcher.AGENT,
            "online": True,
            "state": {"version": 3, "transport": "python_tcp"},
        }
        with (
            patch.dict(
                os.environ,
                {"DEPLOYMENT_MODE": "cloud", "API_HOST": "0.0.0.0"},
                clear=True,
            ),
            patch.object(launcher.sys, "argv", ["dc24_start.py", "--no-browser"]),
            patch.object(launcher, "bundle_stale", return_value=False),
            patch.object(launcher, "dotenv_values", return_value={}),
            patch.object(
                launcher,
                "call",
                side_effect=[
                    URLError("not running"),
                    {"version": 2},
                    [online_agent],
                    {"session": None},
                ],
            ),
            patch.object(launcher.socket, "socket") as socket_factory,
            patch.object(launcher.subprocess, "Popen", return_value=process) as popen,
            patch("pathlib.Path.open", mock_open()),
        ):
            socket_factory.return_value.__enter__.return_value.connect_ex.return_value = 1
            launcher.main()
        command, kwargs = popen.call_args
        self.assertEqual(command[0][command[0].index("--host") + 1], "127.0.0.1")
        self.assertEqual(kwargs["env"]["DEPLOYMENT_MODE"], "local")


if __name__ == "__main__":
    unittest.main()
