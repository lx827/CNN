"""用真实 MSVC/Ninja 验证根构建配置在 GBK/UTF-8 控制台下的生成与头依赖。"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == "win32", "仅验证 Windows MSVC 构建")
class MsvcNinjaBuildTests(unittest.TestCase):
    def test_console_codepages_clean_build_and_indirect_header_rebuild(self) -> None:
        for codepage in (936, 65001):
            with self.subTest(codepage=codepage):
                self.check_build(codepage)

    def check_build(self, codepage: int) -> None:
        cmake = shutil.which("cmake")
        ninja = shutil.which("ninja")
        self.assertIsNotNone(cmake, "需要 CMake")
        self.assertIsNotNone(ninja, "需要 Ninja")
        self.assertIsNotNone(shutil.which("cl"), "需要 MSVC 开发环境")
        kernel = ctypes.windll.kernel32
        original_codepage = kernel.GetConsoleOutputCP()
        self.assertNotEqual(original_codepage, 0, "需要 Windows 控制台")
        scratch = ROOT / ".temp"
        scratch.mkdir(exist_ok=True)
        env = dict(os.environ, VSLANG="2052")

        def run(*command: str) -> str:
            result = subprocess.run(
                command, check=False, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
            output = result.stdout.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, output)
            return output

        try:
            self.assertTrue(kernel.SetConsoleOutputCP(codepage))
            with tempfile.TemporaryDirectory(prefix="msvc-ninja-", dir=scratch) as directory:
                source = Path(directory)
                build = source / "build"
                # 直接执行根配置的工具链部分，省去与此回归无关的 Eigen/Python 依赖。
                platform_config, separator, _ = (ROOT / "CMakeLists.txt").read_text(
                    encoding="utf-8",
                ).partition("add_subdirectory(lib)")
                self.assertTrue(separator, "根配置的数值库入口已变化，需同步测试边界")
                (source / "cmake").mkdir()
                for helper in ("DetectMsvcIncludes.cmake", "msvc_include_probe.ps1"):
                    shutil.copy2(ROOT / "cmake" / helper, source / "cmake" / helper)
                (source / "CMakeLists.txt").write_text(
                    platform_config + "\nadd_library(probe STATIC probe.cpp)\n",
                    encoding="utf-8",
                )
                (source / "probe.cpp").write_text(
                    '#include "public.hpp"\nint probe() { return value; }\n',
                    encoding="utf-8",
                )
                (source / "public.hpp").write_text(
                    '#include "detail.hpp"\n', encoding="utf-8",
                )
                header = source / "detail.hpp"
                header.write_text("constexpr int value = 1;\n", encoding="utf-8")
                run(cmake, "-S", str(source), "-B", str(build), "-G", "Ninja",
                    f"-DCMAKE_MAKE_PROGRAM={ninja}", "-DCNN_COMPUTE_BUILD_PYTHON=OFF")
                self.assertTrue((build / "CMakeFiles/rules.ninja").is_file())
                run(ninja, "-C", str(build))
                dependencies = run(ninja, "-C", str(build), "-t", "deps")
                self.assertIn("detail.hpp", dependencies)
                obj = next(build.rglob("probe.cpp.obj"))
                first_write = obj.stat().st_mtime_ns
                header.write_text("constexpr int value = 2;\n", encoding="utf-8")
                self.assertIn("probe.cpp.obj", run(ninja, "-C", str(build), "-n"))
                run(ninja, "-C", str(build))
                self.assertGreater(obj.stat().st_mtime_ns, first_write)
        finally:
            kernel.SetConsoleOutputCP(original_codepage)


if __name__ == "__main__":
    unittest.main()
