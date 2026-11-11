"""敏感分量原始指标测试；不引入选择去噪阈值。"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.algorithms.decomposition.selection import (
    compute_component_metrics,
    compute_component_metrics_batch,
)


class ComponentRawMetricsTest(unittest.TestCase):
    def test_sine_metrics_have_independent_expected_values(self):
        fs = 1000.0
        t = np.arange(1000) / fs
        component = np.sin(2 * np.pi * 50.0 * t)
        metrics = compute_component_metrics(component, fs, reference=component)
        self.assertAlmostEqual(metrics.correlation, 1.0, places=12)
        self.assertAlmostEqual(metrics.energy_ratio, 1.0, places=12)
        self.assertAlmostEqual(metrics.center_frequency_hz, 50.0, places=10)
        self.assertAlmostEqual(metrics.kurtosis_pearson, 1.5, places=10)
        self.assertAlmostEqual(metrics.kurtosis_excess, -1.5, places=10)
        self.assertGreater(metrics.envelope_entropy, 0.0)
        self.assertAlmostEqual(metrics.energy, 500.0, places=10)

    def test_impulse_kurtosis_and_negative_control(self):
        impulse = np.zeros(1000)
        impulse[123] = 2.0
        metrics = compute_component_metrics(impulse, 1000.0)
        expected_pearson = len(impulse) - 2.0 + 1.0 / (len(impulse) - 1.0)
        self.assertAlmostEqual(metrics.kurtosis_pearson, expected_pearson, places=8)
        self.assertAlmostEqual(metrics.kurtosis_excess, expected_pearson - 3.0, places=8)
        zero = compute_component_metrics(np.zeros(1000), 1000.0, reference=np.zeros(1000))
        self.assertIsNone(zero.correlation)
        self.assertIsNone(zero.kurtosis_pearson)
        self.assertIsNone(zero.kurtosis_excess)
        self.assertIsNone(zero.center_frequency_hz)
        self.assertIsNone(zero.envelope_entropy)
        self.assertEqual(zero.energy, 0.0)
        self.assertIsNone(zero.energy_ratio)

    def test_time_axis_mismatch_is_rejected_instead_of_truncating(self):
        reference = np.arange(128, dtype=float)
        with self.assertRaises(ValueError):
            compute_component_metrics(np.arange(32, dtype=float), 1000.0, reference=reference)
        with self.assertRaises(ValueError):
            compute_component_metrics_batch(
                [np.arange(32, dtype=float), np.arange(64, dtype=float)],
                1000.0, reference=reference,
            )

    def test_invalid_inputs_fail(self):
        with self.assertRaises(ValueError):
            compute_component_metrics([1.0, 2.0], 1000.0)
        with self.assertRaises(ValueError):
            compute_component_metrics(np.ones(16), 0.0)
        with self.assertRaises(ValueError):
            compute_component_metrics([0.0, np.nan] * 8, 1000.0)


if __name__ == "__main__":
    unittest.main()
