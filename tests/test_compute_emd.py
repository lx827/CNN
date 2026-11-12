"""以正确本地 emd 0.8.1 为 oracle 的独立数值与内存契约。"""

import gc
import importlib.util
import unittest
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from cnn_compute import _native, emd

CONTRACT = {
    "local": {"rtol": 1e-10, "atol_scaled": 1e-12, "relative_l2": 1e-10},
    "decomposition": {"rtol": 1e-7, "atol_scaled": 1e-9, "relative_l2": 1e-7},
}
HAS_REFERENCE = importlib.util.find_spec("emd") is not None


def signal(size=512):
    """稳定的多尺度 AM/FM 信号，不把重构完备性充当模态等价。"""
    t = np.arange(size, dtype=np.float64) / size
    return (
        (1 + 0.2 * np.cos(2 * np.pi * 3 * t)) * np.sin(2 * np.pi * 37 * t)
        + 0.4 * np.sin(2 * np.pi * 9 * t + 0.3)
        + 0.1 * t
    )


def assert_budget(test, actual, expected, original, kind="decomposition"):
    actual, expected = np.asarray(actual), np.asarray(expected)
    test.assertEqual(actual.shape, expected.shape)
    test.assertTrue(np.all(np.isfinite(actual)))
    scale = max(
        np.max(np.abs(original)), np.max(np.abs(expected)), np.finfo(float).tiny
    )
    budget = CONTRACT[kind]
    a, b = actual / scale, expected / scale
    np.testing.assert_allclose(a, b, rtol=budget["rtol"], atol=budget["atol_scaled"])
    test.assertLessEqual(
        np.linalg.norm(a - b),
        budget["relative_l2"] * np.linalg.norm(b)
        + budget["atol_scaled"] * np.sqrt(b.size),
    )


@unittest.skipUnless(HAS_REFERENCE, "需显式安装 emd-reference 可选组，不以 PyEMD 替代")
class EMDReferenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import emd as reference

        cls.reference = reference
        if reference.__version__ != "0.8.1":
            raise RuntimeError(f"参考版本不是 0.8.1: {reference.__version__}")

    def test_full_sift_matches_reference_options(self):
        x = signal()
        for method in ("splrep", "pchip", "mono_pchip"):
            for stop in ("sd", "rilling", "energy", "fixed"):
                with self.subTest(interpolation=method, stop=stop):
                    imf_opts = {"stop_method": stop}
                    if stop == "fixed":
                        imf_opts["max_iters"] = 5
                    options = {
                        "max_imfs": 3,
                        "imf_opts": imf_opts,
                        "envelope_opts": {"interp_method": method},
                    }
                    expected = self.reference.sift.sift(x, **options)
                    assert_budget(self, emd.sift(x, **options), expected, x)

    def test_single_imf_update_and_padding(self):
        x = signal(257)
        for stop in ("sd", "rilling", "fixed"):
            for padding, parabolic in (
                ("rilling", False),
                ("numpypad", False),
                ("numpypad", True),
            ):
                with self.subTest(stop=stop, padding=padding, parabolic=parabolic):
                    options = {
                        "stop_method": stop,
                        "max_iters": 7 if stop == "fixed" else 1000,
                        "env_step_size": 0.7,
                        "extrema_opts": {
                            "method": padding,
                            "parabolic_extrema": parabolic,
                        },
                    }
                    expected, more = self.reference.sift.get_next_imf(x, **options)
                    actual, actual_more = emd.get_next_imf(x, **options)
                    assert_budget(self, actual, expected, x, "local")
                    self.assertEqual(actual_more, more)

    def test_splrep_is_real_interpolation_and_strict_extrema(self):
        from scipy.interpolate import splev, splrep

        x = np.array([-3.0, -1.0, 0.5, 2.0, 4.0, 6.0])
        y = np.sin(x)
        q = np.linspace(-4, 7, 103)
        actual = _native.interpolation.interpolate(
            x, y, q, _native.interpolation.Method.splrep
        )
        assert_budget(self, actual, splev(q, splrep(x, y)), y, "local")
        plateau = np.array([0.0, 1.0, 1.0, 0.0, -1.0, -1.0, 0.0])
        loc, _ = _native.envelope.find_extrema(plateau)
        self.assertEqual(len(loc), 0)


class EMDLifecycleTest(unittest.TestCase):
    def test_independent_results_readonly_noncontiguous_and_concurrency(self):
        base = signal(1024)
        view = base[::2]
        original = view.copy()
        view.flags.writeable = False
        detailed = emd.sift_detailed(view, max_imfs=3)
        saved = tuple(x.copy() for x in detailed.components)
        self.assertEqual(detailed.status, "success")
        for component in detailed.components:
            self.assertFalse(np.shares_memory(component, view))
        expected = detailed.as_array()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: emd.sift(view, max_imfs=3), range(4)))
        for result in results:
            np.testing.assert_array_equal(result, expected)
        gc.collect()
        for component, copy in zip(detailed.components, saved):
            np.testing.assert_array_equal(component, copy)
        np.testing.assert_array_equal(view, original)

    def test_failure_is_explicit_and_calls_remain_reusable(self):
        x = signal()
        result = emd.sift_detailed(x, imf_opts={"max_iters": 1, "sd_thresh": 1e-30})
        self.assertEqual(result.status, "iteration_limit")
        with self.assertRaises(emd.ConvergenceError):
            emd.sift(x, imf_opts={"max_iters": 1, "sd_thresh": 1e-30})
        monotonic = np.linspace(0, 1, 32)
        result = emd.sift_detailed(monotonic)
        self.assertEqual(result.status, "insufficient_extrema")
        np.testing.assert_array_equal(result.components[0], monotonic)
        self.assertEqual(emd.sift_detailed(x, max_imfs=2).status, "success")
        with self.assertRaises(ValueError):
            emd.sift(np.array([0.0, np.nan, 1.0]))


if __name__ == "__main__":
    unittest.main()
