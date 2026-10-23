"""Windows 实际 Vite 进程回归：正常返回和 Ctrl+C 都应释放进程与端口。"""
import os
from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "edge"))
import edge_client as edge
import replay


@unittest.skipUnless(os.name == "nt" and shutil.which("node"), "需要 Windows 和 Node.js")
class FrontendLifecycleTests(unittest.TestCase):
    def test_owned_vite_exits_on_return_and_keyboard_interrupt(self):
        if not (ROOT / "wind-turbine-diagnosis/node_modules/vite/bin/vite.js").is_file():
            self.skipTest("需要已安装的 Vite")
        if replay.frontend_ready():
            self.skipTest("保留用户已运行的前端，不占用 3000 端口测试")
        for interrupt in (False, True):
            with self.subTest(interrupt=interrupt):
                started = []
                original_popen = replay.subprocess.Popen

                def capture(*args, **kwargs):
                    process = original_popen(*args, **kwargs)
                    if str(args[0][0]).lower().endswith("node.exe"):
                        started.append(process)
                    return process

                def finish_edge():
                    self.assertTrue(replay.frontend_ready())
                    if interrupt:
                        raise KeyboardInterrupt

                with patch.object(sys, "argv", ["replay.py", "--dataset", "cw"]), \
                        patch.object(replay, "check_data"), patch.object(replay, "check_cloud"), \
                        patch.object(replay.webbrowser, "open"), \
                        patch.object(replay.subprocess, "Popen", side_effect=capture), \
                        patch.object(edge, "main", side_effect=finish_edge):
                    if interrupt:
                        with self.assertRaises(KeyboardInterrupt):
                            replay.main()
                    else:
                        replay.main()
                self.assertEqual(len(started), 1)
                self.assertIsNotNone(started[0].poll(), "Vite 的 Node 进程仍在运行")
                self.assertFalse(replay.frontend_ready(), "退出后端口仍在提供 Vite 服务")


if __name__ == "__main__":
    unittest.main()
