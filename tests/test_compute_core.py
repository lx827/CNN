"""公共数值接口、输出所有权和生成存根的安装契约。"""

import ast
import unittest
from importlib.metadata import distribution
from pathlib import Path

import numpy as np
from scipy.interpolate import CubicSpline, PchipInterpolator
from scipy.linalg import solve_banded

from cnn_compute import _native, core


class ComputeCoreTest(unittest.TestCase):
    def test_interpolation_matches_scipy_and_preserves_views(self):
        x = np.array([-2.0, -0.5, 0.0, 2.5, 4.0])
        y = np.array([3.0, -1.0, 2.0, 0.0, 7.0])
        query = np.linspace(-3.0, 5.0, 42)[::2]
        for actual, reference in (
            (core.pchip, PchipInterpolator),
            (core.cubic, CubicSpline),
        ):
            with self.subTest(method=actual.__name__):
                result = actual(x, y, query)
                np.testing.assert_allclose(
                    result, reference(x, y)(query), rtol=1e-12, atol=1e-12
                )
                self.assertFalse(np.shares_memory(result, y))
                self.assertTrue(result.flags.c_contiguous)
        with self.assertRaises(TypeError):
            core.pchip(x.astype(np.float32), y, query)
        with self.assertRaises(ValueError):
            core.cubic(x[::-1], y, query)

    def test_tridiagonal_matches_banded_reference_with_pivots(self):
        rng = np.random.default_rng(20261112)
        for size in (4, 17, 100):
            lower = rng.normal(size=size - 1)
            diagonal = rng.normal(size=size)
            diagonal[0] = 0.0  # 强制首行换主元。
            upper = rng.normal(size=size - 1)
            rhs = rng.normal(size=size)
            arrays = (lower, diagonal, upper, rhs)
            originals = [array.copy() for array in arrays]
            for array in arrays:
                array.flags.writeable = False
            bands = np.zeros((3, size))
            bands[0, 1:], bands[1], bands[2, :-1] = upper, diagonal, lower
            expected = solve_banded((1, 1), bands, rhs)
            observed = core.solve_tridiagonal(*arrays)
            np.testing.assert_allclose(observed, expected, rtol=1e-12, atol=1e-12)
            for array, original in zip(arrays, originals):
                np.testing.assert_array_equal(array, original)
                self.assertFalse(np.shares_memory(observed, array))
        with self.assertRaises(ValueError):
            core.solve_tridiagonal(np.ones(3), np.ones(5), np.ones(4), np.ones(5))
        with self.assertRaises(RuntimeError):
            core.solve_tridiagonal(np.zeros(3), np.zeros(4), np.zeros(3), np.ones(4))

    def test_installed_stubs_describe_real_exports(self):
        package = distribution("cnn-compute")
        files = {str(path).replace("\\", "/") for path in package.files}
        self.assertIn("cnn_compute/py.typed", files)
        for name, module in (("core", _native.core), ("emd", _native.emd)):
            relative = f"cnn_compute/_native/{name}.pyi"
            self.assertIn(relative, files)
            source = Path(package.locate_file(relative)).read_text(encoding="utf-8")
            declarations = {
                node.name: node
                for node in ast.parse(source).body
                if isinstance(node, ast.FunctionDef)
            }
            for name, declaration in declarations.items():
                self.assertTrue(callable(getattr(module, name)))
                self.assertIsNotNone(declaration.returns)
            if module is _native.emd:
                result = ast.unparse(declarations["sift_imf"].returns)
                self.assertIn("float64", result)
                self.assertIn("None", result)
        source = Path(
            package.locate_file("cnn_compute/_native/__init__.pyi")
        ).read_text(encoding="utf-8")
        self.assertIn("from cnn_compute._native.core import", source)
        self.assertNotIn("from _native.", source)
        self.assertIs(_native._pchip, _native.core.pchip)
        self.assertIs(_native.sift_imf, _native.emd.sift_imf)


if __name__ == "__main__":
    unittest.main()
