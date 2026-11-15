"""安装后的包行为：构建信息来自真实原生模块，分发依赖保持独立。"""

import unittest
from importlib.metadata import distribution

from cnn_compute import build_info


class ComputePackageTest(unittest.TestCase):
    def test_installed_native_backend_reports_its_target(self):
        info = build_info()
        self.assertEqual(info["schema"], 1)
        self.assertIn(info["compiler_id"], {"MSVC", "GNU", "Clang", "AppleClang"})
        self.assertTrue(info["compiler_version"])
        self.assertTrue(info["target_arch"])
        self.assertIn(info["arch_policy"], {"baseline", "avx2"})
        self.assertTrue(info["simd"])
        self.assertEqual(tuple(info["eigen_version"]), (3, 4, 0))

    def test_library_metadata_has_no_application_dependencies(self):
        requirements = distribution("cnn-compute").requires
        self.assertEqual(len(requirements), 1)
        self.assertTrue(requirements[0].lower().startswith("numpy"))


if __name__ == "__main__":
    unittest.main()
