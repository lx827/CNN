"""本地 emd 0.8.1 mask、NHT 和二层组合的数值/所有权验证。"""

import gc
import unittest
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import test_compute_emd as _reference

from cnn_compute import emd, transforms

HAS_REFERENCE = _reference.HAS_REFERENCE
assert_budget = _reference.assert_budget


def oscillation(size=512):
    t = np.arange(size, dtype=np.float64)
    return (
        np.cos(2 * np.pi * 0.17 * t) * (1 + 0.15 * np.cos(2 * np.pi * 0.007 * t))
        + 0.35 * np.cos(2 * np.pi * 0.052 * t)
        + 0.1 * np.cos(2 * np.pi * 0.019 * t)
    )


@unittest.skipUnless(HAS_REFERENCE, "需 emd-reference 可选组，不以 PyEMD 替代")
class MaskReferenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _reference.EMDReferenceTest.setUpClass()
        cls.reference = _reference.EMDReferenceTest.reference

    def test_mask_explicit_and_automatic_frequency(self):
        x = oscillation()
        for frequencies in ([0.2, 0.09, 0.035], "zc", "if"):
            with self.subTest(frequencies=frequencies):
                options = {
                    "max_imfs": 3,
                    "mask_freqs": frequencies,
                    "ret_mask_freq": True,
                }
                actual, masks = emd.mask_sift(x, **options)
                expected, expected_masks = self.reference.sift.mask_sift(x, **options)
                assert_budget(self, actual, expected, x)
                assert_budget(self, masks, expected_masks, x, "local")

    def test_mask_single_imf_and_amplitude_modes(self):
        x = oscillation(257)
        expected, expected_more = self.reference.sift.get_next_imf_mask(
            x, 0.2, 1.2, nphases=3
        )
        actual, more = emd.get_next_imf_mask(x, 0.2, 1.2, nphases=3)
        assert_budget(self, actual, expected, x)
        self.assertEqual(more, expected_more)
        for mode in ("abs", "ratio_sig", "ratio_imf"):
            with self.subTest(mode=mode):
                options = {
                    "max_imfs": 3,
                    "mask_freqs": [0.2, 0.09, 0.035],
                    "mask_amp": [1.0, 0.7, 0.4],
                    "mask_amp_mode": mode,
                }
                assert_budget(
                    self,
                    emd.mask_sift(x, **options),
                    self.reference.sift.mask_sift(x, **options),
                    x,
                )

    def test_hilbert_nht_odd_and_even_lengths(self):
        from scipy.signal import hilbert

        for length in (257, 512):
            x = oscillation(length)
            assert_budget(
                self, transforms.analytic_signal(x).real, hilbert(x).real, x, "local"
            )
            assert_budget(
                self, transforms.analytic_signal(x).imag, hilbert(x).imag, x, "local"
            )
            assert_budget(
                self,
                transforms.amplitude_normalise(x),
                self.reference.imftools.amplitude_normalise(x[:, None])[:, 0],
                x,
                "local",
            )
            for method in ("hilbert", "nht"):
                with self.subTest(length=length, method=method):
                    actual = transforms.frequency_transform(x, method=method)
                    expected = self.reference.spectra.frequency_transform(
                        x[:, None], 1, method
                    )
                    for array, reference in zip(actual, expected):
                        assert_budget(self, array, reference[:, 0], x, "local")

    def test_iterated_mask_convergence_and_iteration_limit(self):
        x = oscillation()
        for kwargs in (
            {"max_iter": 1, "iter_th": 1e-15},
            {
                "max_iter": 3,
                "iter_th": 10.0,
                "N_avg": 2,
                "exclude_edges": True,
                "sample_rate": 64.0,
            },
        ):
            with self.subTest(kwargs=kwargs):
                options = dict(
                    mask_0=[0.2, 0.09, 0.035], max_imfs=3, ret_mask_freq=True, **kwargs
                )
                actual, masks = emd.iterated_mask_sift(x, **options)
                expected, expected_masks = self.reference.sift.iterated_mask_sift(
                    x, **options
                )
                assert_budget(self, actual, expected, x)
                assert_budget(self, masks, expected_masks, x)
                detailed = emd.iterated_mask_sift_detailed(
                    x, **{k: v for k, v in options.items() if k != "ret_mask_freq"}
                )
                self.assertEqual(detailed.converged, kwargs["iter_th"] > 1)

    def test_random_initial_mask_matches_local_reference_without_global_rng_effect(
        self,
    ):
        x = oscillation()
        options = {
            "mask_0": "random",
            "max_imfs": 3,
            "sample_rate": 64.0,
            "seed": 4,
            "max_iter": 1,
            "ret_mask_freq": True,
        }
        expected, expected_masks = self.reference.sift.iterated_mask_sift(x, **options)
        np.random.seed(23)
        before = np.random.get_state()
        actual, masks = emd.iterated_mask_sift(x, **options)
        after = np.random.get_state()
        assert_budget(self, actual, expected, x)
        assert_budget(self, masks, expected_masks, x)
        for left, right in zip(before, after):
            np.testing.assert_array_equal(left, right)

    def test_second_layer_success_domains(self):
        x = oscillation()
        columns = np.column_stack([x, x * 0.7])
        options = {"max_imfs": 2, "energy_thresh": 1.0}
        expected = self.reference.sift.sift_second_layer(columns, sift_args=options)
        assert_budget(self, emd.sift_second_layer(columns, options), expected, x)
        mask_options = {"max_imfs": 2}
        masks = [0.2, 0.09, 0.035]
        expected = self.reference.sift.mask_sift_second_layer(
            columns, masks, sift_args=mask_options
        )
        assert_budget(
            self, emd.mask_sift_second_layer(columns, masks, mask_options), expected, x
        )

        # 每列模态上限独立于 first-layer 列数，不复刻参考的越界/漏列缺陷。
        actual = emd.sift_second_layer(columns, {"max_imfs": 1})
        expected_columns = [
            emd.sift(columns[:, i], max_imfs=1) for i in range(columns.shape[1])
        ]
        self.assertEqual(
            actual.shape[2], max(column.shape[1] for column in expected_columns)
        )
        for i, column in enumerate(expected_columns):
            np.testing.assert_array_equal(actual[:, i, : column.shape[1]], column)
        larger = emd.sift_second_layer(columns, {"max_imfs": 3})
        self.assertEqual(larger.shape[1], columns.shape[1])


class MaskLifecycleTest(unittest.TestCase):
    def test_result_ownership_and_concurrent_calls(self):
        x = oscillation(1024)[::2]
        x.flags.writeable = False
        original = x.copy()
        options = {"max_imfs": 3, "mask_freqs": [0.2, 0.09, 0.035]}
        detailed = emd.mask_sift_detailed(x, **options)
        saved = [a.copy() for a in detailed.decomposition.components]
        expected = detailed.decomposition.as_array()
        with ThreadPoolExecutor(max_workers=2) as executor:
            outputs = list(
                executor.map(lambda _: emd.mask_sift(x, **options), range(4))
            )
        for output in outputs:
            np.testing.assert_array_equal(output, expected)
        gc.collect()
        for array, saved_array in zip(detailed.decomposition.components, saved):
            self.assertFalse(np.shares_memory(array, x))
            np.testing.assert_array_equal(array, saved_array)
        np.testing.assert_array_equal(x, original)

    def test_invalid_and_upstream_failure_domains_are_explicit(self):
        with self.assertRaises(ValueError):
            emd.mask_sift(oscillation(), nprocesses=2)
        with self.assertRaises(ValueError):
            emd.mask_sift(oscillation(), mask_amp=[1], max_imfs=0)
        with self.assertRaises(ValueError):
            emd.sift_second_layer(
                np.column_stack([oscillation(), oscillation()]), {"max_imfs": -1}
            )
        with self.assertRaises(emd.ConvergenceError):
            emd.mask_sift(
                oscillation(), max_imfs=2, imf_opts={"max_iters": 1, "sd_thresh": 1e-30}
            )


if __name__ == "__main__":
    unittest.main()
