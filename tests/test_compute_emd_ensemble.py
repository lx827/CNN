"""emd 0.8.1 集成筛分的差分、随机性与所有权契约。"""

import gc
import unittest
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from cnn_compute import _native, emd
import test_compute_emd as reference_contract

HAS_REFERENCE = reference_contract.HAS_REFERENCE
assert_budget = reference_contract.assert_budget
signal = reference_contract.signal


def complete_reference(module, values, options):
    """参考只指导公式：截取目标 IMF 数，再从输入重构对应残差。

    emd 0.8.1 的层号检查晚一轮，可能多产生一个 IMF；不把该缺陷作为
    原生接口契约，也不放宽数值容差来接受不同目标模态数。
    """
    reference = module.sift.complete_ensemble_sift(values, **options)
    maximum = options.get("max_imfs")
    if maximum is not None and reference.shape[1] - 1 > maximum:
        modes = reference[:, :maximum]
        return np.column_stack((modes, values - modes.sum(axis=1)))
    return reference


@unittest.skipUnless(HAS_REFERENCE, "需显式安装 emd-reference 可选组")
class EnsembleReferenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 共用已安装参考版本与测试预算。
        reference_contract.EMDReferenceTest.setUpClass.__func__(cls)

    def test_ensemble_single_flip_and_complete_match_local_reference(self):
        x = signal(257)
        for interpolation in ("splrep", "pchip"):
            options = {
                "nensembles": 3,
                "noise_seed": 20261112,
                "max_imfs": 3,
                "envelope_opts": {"interp_method": interpolation},
            }
            for mode in ("single", "flip"):
                with self.subTest(interpolation=interpolation, mode=mode):
                    expected = self.reference.sift.ensemble_sift(
                        x, noise_mode=mode, **options
                    )
                    actual = emd.ensemble_sift(x, noise_mode=mode, **options)
                    assert_budget(self, actual, expected, x)
            with self.subTest(interpolation=interpolation, method="complete"):
                expected = complete_reference(self.reference, x, options)
                actual = emd.complete_ensemble_sift(x, **options)
                assert_budget(self, actual, expected, x)

    def test_complete_limits_true_imf_count_and_reconstructs_residual(self):
        x = signal(512)
        for maximum in (1, 2):
            with self.subTest(max_imfs=maximum):
                options = {
                    "nensembles": 3,
                    "noise_seed": 42,
                    "max_imfs": maximum,
                }
                expected = complete_reference(self.reference, x, options)
                actual = emd.complete_ensemble_sift(x, **options)
                assert_budget(self, actual, expected, x)
                self.assertLessEqual(actual.shape[1], maximum + 1)
                # 重构仅为附加检查，不替代逐模态对照。
                np.testing.assert_allclose(actual.sum(axis=1), x, atol=1e-12)


class EnsembleLifecycleTest(unittest.TestCase):
    def test_seed_repeatability_input_owners_and_concurrent_calls(self):
        base = signal(512)
        values = base[::2]
        saved_input = values.copy()
        values.flags.writeable = False
        options = {"nensembles": 3, "noise_seed": 20261112, "max_imfs": 2}
        for method in ("ensemble_sift", "complete_ensemble_sift"):
            with self.subTest(method=method):
                detailed = getattr(emd, method + "_detailed")(values, **options)
                self.assertEqual(detailed.status, "success")
                self.assertEqual(detailed.iterations, ())
                saved = tuple(column.copy() for column in detailed.components)
                expected = detailed.as_array()
                for column in detailed.components:
                    self.assertFalse(np.shares_memory(values, column))
                with ThreadPoolExecutor(max_workers=2) as executor:
                    results = list(
                        executor.map(
                            lambda _: getattr(emd, method)(values, **options), range(4)
                        )
                    )
                for result in results:
                    np.testing.assert_array_equal(result, expected)
                gc.collect()
                for column, copy in zip(detailed.components, saved):
                    np.testing.assert_array_equal(column, copy)
        np.testing.assert_array_equal(values, saved_input)

    def test_global_random_state_is_untouched(self):
        x = signal(128)
        state = np.random.get_state()
        try:
            np.random.seed(523)
            expected = np.random.standard_normal(12)
            for function in (emd.ensemble_sift, emd.complete_ensemble_sift):
                for seed in (None, 31):
                    with self.subTest(method=function.__name__, seed=seed):
                        np.random.seed(523)
                        function(x, nensembles=2, noise_seed=seed, max_imfs=1)
                        np.testing.assert_array_equal(
                            np.random.standard_normal(12), expected
                        )
        finally:
            np.random.set_state(state)

    def test_failure_layout_and_execution_policy(self):
        x = signal(256)
        for function in (emd.ensemble_sift, emd.complete_ensemble_sift):
            with self.subTest(method=function.__name__):
                with self.assertRaises(ValueError):
                    function(x, nprocesses=2)
                with self.assertRaises(ValueError):
                    function(x, nensembles=0)
                with self.assertRaises(emd.ConvergenceError):
                    function(
                        x,
                        nensembles=2,
                        noise_seed=1,
                        imf_opts={"max_iters": 1, "sd_thresh": 1e-30},
                    )
        failed = emd.complete_ensemble_sift_detailed(
            np.ones(64), nensembles=2, noise_seed=1
        )
        self.assertEqual(failed.status, "numerical_failure")
        with self.assertRaises(emd.ConvergenceError):
            emd.complete_ensemble_sift(np.ones(64), nensembles=2, noise_seed=1)
        with self.assertRaises(ValueError):
            emd.ensemble_sift(x, noise_mode="unknown")
        options = _native.emd.EnsembleOptions()
        with self.assertRaises(ValueError):
            _native.emd.ensemble_sift(x, np.ones((len(x), 4)), options)
        with self.assertRaises(ValueError):
            _native.emd.ensemble_sift(x, np.full((4, len(x)), np.nan), options)


if __name__ == "__main__":
    unittest.main()
