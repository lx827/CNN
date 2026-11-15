"""EMD/EEMD/CEEMDAN 的分解、边界、停止和固定种子测试。"""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.algorithms.decomposition.emd import (
    EMDParameters,
    EnsembleParameters,
    decompose_ceemdan,
    decompose_eemd,
    decompose_emd,
)


FS = 1000.0


def two_tones(length=1000):
    t = np.arange(length) / FS
    high = 0.6 * np.sin(2 * np.pi * 80.0 * t + 0.2)
    low = np.sin(2 * np.pi * 8.0 * t - 0.3)
    return high + low, high, low


class EMDDecompositionTest(unittest.TestCase):
    def test_simple_imfs_and_completeness(self):
        signal, high, low = two_tones()
        result = decompose_emd(
            signal,
            FS,
            EMDParameters(max_imfs=4, max_sifts=100, sd_threshold=0.2),
        )
        self.assertEqual(result.status, "valid")
        self.assertGreaterEqual(len(result.imfs), 2)
        np.testing.assert_allclose(result.reconstructed, signal, atol=1e-10)
        high_correlations = [abs(np.corrcoef(imf, high)[0, 1]) for imf in result.imfs]
        self.assertGreater(max(high_correlations), 0.85)
        low_remainder = signal - result.imfs[int(np.argmax(high_correlations))]
        self.assertGreater(abs(np.corrcoef(low_remainder, low)[0, 1]), 0.9)
        self.assertTrue(all(len(imf) == len(signal) for imf in result.imfs))

    def test_mirror_boundary_and_sd_stop_accept_a_real_nonzero_round(self):
        t = np.arange(600) / FS
        signal = np.sin(2 * np.pi * 20.0 * t) + 0.2 * np.linspace(-1.0, 1.0, len(t))
        result = decompose_emd(
            signal,
            FS,
            EMDParameters(max_imfs=2, max_sifts=20, sd_threshold=1e6),
        )
        self.assertEqual(result.status, "valid")
        self.assertEqual(result.sift_iterations[0], 1)
        self.assertTrue(np.all(result.converged))
        self.assertGreater(np.std(result.imfs[0]), 0.1)
        self.assertLess(np.max(np.abs(result.imfs[0])), 5.0)
        np.testing.assert_allclose(result.reconstructed, signal, atol=1e-10)

    def test_monotonic_constant_and_short_inputs_are_not_fake_imfs(self):
        for signal in (np.linspace(-2.0, 3.0, 128), np.ones(128) * 4.0):
            result = decompose_emd(signal, FS)
            self.assertEqual(result.status, "indeterminate")
            self.assertEqual(result.imfs, ())
            np.testing.assert_array_equal(result.residual, signal)
            np.testing.assert_array_equal(result.reconstructed, signal)
            self.assertIsNotNone(result.reason)
        with self.assertRaises(ValueError):
            decompose_emd([1.0, 2.0, 3.0], FS)
        with self.assertRaises(ValueError):
            decompose_emd([0.0, np.inf] * 16, FS)

    def test_eemd_seed_reproducibility_and_completeness(self):
        signal, _, _ = two_tones(300)
        params = EnsembleParameters(
            emd=EMDParameters(max_imfs=3, max_sifts=40),
            ensemble_size=4,
            noise_scale=0.15,
        )
        first = decompose_eemd(signal, FS, seed=123, parameters=params)
        second = decompose_eemd(signal, FS, seed=123, parameters=params)
        different = decompose_eemd(signal, FS, seed=124, parameters=params)
        self.assertEqual(first.status, "valid")
        self.assertEqual(first.seed, 123)
        np.testing.assert_allclose(first.reconstructed, signal, atol=1e-10)
        np.testing.assert_array_equal(first.imfs, second.imfs)
        np.testing.assert_array_equal(first.residual, second.residual)
        self.assertFalse(np.array_equal(first.imfs, different.imfs))

    def test_ceemdan_seed_reproducibility_and_completeness(self):
        signal, _, _ = two_tones(300)
        params = EnsembleParameters(
            emd=EMDParameters(max_imfs=3, max_sifts=40),
            ensemble_size=4,
            noise_scale=0.15,
        )
        first = decompose_ceemdan(signal, FS, seed=321, parameters=params)
        second = decompose_ceemdan(signal, FS, seed=321, parameters=params)
        self.assertEqual(first.status, "valid")
        self.assertGreaterEqual(len(first.imfs), 1)
        self.assertTrue(any(np.std(imf) > 1e-6 for imf in first.imfs))
        np.testing.assert_allclose(first.reconstructed, signal, atol=1e-10)
        np.testing.assert_array_equal(first.imfs, second.imfs)
        np.testing.assert_array_equal(first.residual, second.residual)


if __name__ == "__main__":
    unittest.main()
