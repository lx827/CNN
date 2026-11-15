"""原生高级计算的接口/生命周期和自适应更新上限，不复制完整算法测试。"""

import unittest

import numpy as np
from cnn_compute import diagnostic


class NativeDiagnosticContracts(unittest.TestCase):
    def test_spectral_kurtosis_is_invariant_across_finite_amplitude_scales(self):
        signal = np.array([1 + 2j, 3 + 1j, 2 - 4j, 0.5 + 0.25j])
        power = np.abs(signal) ** 2
        expected = len(signal) * np.sum(power**2) / np.sum(power) ** 2 - 2
        for scale in (1.0, 1e-200, 1e160):
            with self.subTest(scale=scale):
                self.assertAlmostEqual(
                    diagnostic.complex_spectral_kurtosis(signal * scale), expected, places=13
                )

    def test_adaptive_one_update_uses_final_weights_for_remaining_samples(self):
        signal = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        # L=1、delay=1，第一轮e=2，w=0.1*2*1=0.2；之后不再更新。
        expected = np.array(
            [1.0, 2.0, 3.0 - 0.2 * 2, 4.0 - 0.2 * 3, 5.0 - 0.2 * 4, 6.0 - 0.2 * 5]
        )
        expected -= np.mean(expected)
        actual = diagnostic.adaptive_filter(
            signal, filter_length=1, step_size=0.1, delay=1, max_updates=1
        )
        np.testing.assert_allclose(actual, expected, rtol=1e-14, atol=1e-14)

    def test_result_owner_and_input_survive_subsequent_calls(self):
        signal = np.arange(100.0, dtype=float)[::2]
        original = signal.copy()
        first = diagnostic.teager(signal)
        saved = first.copy()
        diagnostic.teager(np.ones(73))
        np.testing.assert_array_equal(first, saved)
        np.testing.assert_array_equal(signal, original)
        self.assertFalse(np.shares_memory(first, signal))
        self.assertIsNotNone(first.base)

    def test_ica_rank_failure_has_reason_without_components(self):
        channel = np.linspace(-1.0, 1.0, 100)
        result = diagnostic.fast_ica(np.column_stack([channel, channel]))
        self.assertEqual(result[-1], 2)
        self.assertEqual(result[-3], 1)
        self.assertEqual(result[0].size, 0)


if __name__ == "__main__":
    unittest.main()
