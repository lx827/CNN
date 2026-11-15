"""VMD 双模态、Hz 单位、奇数与长输入有效区间测试。"""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.algorithms.decomposition.vmd import VMDParameters, decompose_vmd


class VMDDecompositionTest(unittest.TestCase):
    @staticmethod
    def signal(length=1000, fs=1000.0):
        t = np.arange(length) / fs
        return np.sin(2 * np.pi * 30.0 * t) + 0.6 * np.sin(2 * np.pi * 150.0 * t)

    def test_dual_modes_are_sorted_and_centers_are_hz(self):
        fs = 1000.0
        result = decompose_vmd(
            self.signal(),
            fs,
            VMDParameters(modes=2, alpha=2000.0, tolerance=1e-7, max_iterations=300),
        )
        self.assertEqual(result.status, "valid")
        self.assertEqual(result.modes.shape, (2, 1000))
        self.assertEqual(result.center_frequencies_hz.shape, (2,))
        self.assertEqual(result.center_frequency_history_hz.shape[1], 2)
        np.testing.assert_allclose(
            result.center_frequencies_hz, [30.0, 150.0], atol=8.0
        )
        self.assertTrue(np.all(np.diff(result.center_frequencies_hz) >= 0.0))
        self.assertEqual(result.valid_interval.stop_index, 1000)
        self.assertEqual(len(result.residual), 1000)
        np.testing.assert_allclose(
            result.modes.sum(axis=0) + result.residual,
            self.signal(),
            atol=1e-10,
        )

    def test_odd_input_keeps_every_original_sample(self):
        signal = self.signal(1001)
        result = decompose_vmd(
            signal, 1000.0, VMDParameters(modes=2, max_iterations=150)
        )
        self.assertEqual(result.modes.shape, (2, 1001))
        self.assertEqual(len(result.residual), 1001)
        self.assertEqual(result.valid_interval.stop_index, 1001)
        self.assertGreater(np.std(result.modes[:, -32:]), 1e-4)

    def test_long_input_returns_explicit_window_without_zero_padding(self):
        signal = self.signal(1200)
        result = decompose_vmd(
            signal,
            1000.0,
            VMDParameters(modes=2, max_iterations=100, max_samples=256),
        )
        self.assertEqual(result.input_length, 1200)
        self.assertEqual(result.modes.shape, (2, 256))
        self.assertEqual(result.valid_interval.start_index, 0)
        self.assertEqual(result.valid_interval.stop_index, 256)
        np.testing.assert_allclose(
            result.modes.sum(axis=0) + result.residual,
            signal[:256],
            atol=1e-10,
        )

    def test_invalid_and_zero_inputs(self):
        with self.assertRaises(ValueError):
            decompose_vmd([], 1000.0)
        with self.assertRaises(ValueError):
            decompose_vmd(self.signal(64), 1000.0, VMDParameters(modes=0))
        with self.assertRaises(ValueError):
            decompose_vmd(self.signal(64), -1000.0)
        with self.assertRaises(ValueError):
            decompose_vmd(self.signal(64), 1000.0, VMDParameters(max_samples=8))
        result = decompose_vmd(np.zeros(128), 1000.0)
        self.assertEqual(result.status, "indeterminate")
        self.assertEqual(result.modes.shape, (0, 128))
        np.testing.assert_array_equal(result.residual, np.zeros(128))
        self.assertIsNotNone(result.reason)


if __name__ == "__main__":
    unittest.main()
