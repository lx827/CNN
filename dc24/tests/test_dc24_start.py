"""实际cmd入口检查：不打开浏览器或连接硬件，防止批处理编码/行尾回归。"""
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


class DC24StartTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows批处理入口')
    def test_batch_check_entry_runs_real_launcher_without_starting_services(self):
        if not (ROOT/'.venv/Scripts/python.exe').exists():
            self.skipTest('本机 uv workspace 环境不存在（先 uv sync）')
        result = subprocess.run(['cmd', '/d', '/c', 'start_dc24.bat', '--check'], cwd=ROOT,
                                capture_output=True, timeout=20)
        output = result.stdout.decode('utf-8', errors='replace')
        self.assertEqual(result.returncode, 0, output+result.stderr.decode('utf-8', errors='replace'))
        self.assertIn('依赖路径检查通过', output)
        self.assertNotIn('not recognized', output)


if __name__ == '__main__':
    unittest.main()
