"""MED/MCKD 数学反例、留一更新和 BPFO/BPFI 目标周期。"""
import os
import sys
import unittest

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.algorithms.bearing.deconvolution import (
    MCKDParameters,
    MCKDEnvelopePipeline,
    MEDParameters,
    MEDEnvelopePipeline,
    _mckd_filter_update,
    correlated_kurtosis,
    normalized_kurtosis,
)
from app.algorithms.mechanics import BearingGeometry


class DeconvolutionObjectiveTests(unittest.TestCase):
    def test_periodic_and_random_impulses_separate_med_from_mckd_objective(self):
        periodic = np.zeros(81)
        periodic[[10, 20, 30, 40, 50, 60]] = [1.0, -0.8, 1.1, 0.9, -1.0, 0.7]
        random = np.zeros_like(periodic)
        random[[10, 13, 29, 47, 53, 80]] = periodic[periodic != 0]

        # 两者仅位置不同，MED 的全局峭度相同；MCKD 只对 T=10 的周期序列给出正目标。
        self.assertAlmostEqual(normalized_kurtosis(periodic), normalized_kurtosis(random), places=12)
        self.assertGreater(correlated_kurtosis(periodic, period=10, shift_order=1), 0.0)
        self.assertAlmostEqual(correlated_kurtosis(random, period=10, shift_order=1), 0.0, places=12)

    def test_mckd_update_contains_leave_one_product_and_delayed_input(self):
        x = np.array([0.5, -1.0, 2.0, 0.25, 1.5, -0.5, 1.0, 0.75])
        f = np.array([0.2, -0.4, 0.3])
        period = 2
        shift_order = 1
        X = sliding_window_view(x, len(f))
        y = X @ f
        start = period * shift_order
        valid = len(y) - start
        shifted = [y[start - m * period: len(y) - m * period] for m in range(shift_order + 1)]
        beta = np.prod(np.vstack(shifted), axis=0)

        expected_rhs = np.zeros(len(f))
        for m in range(shift_order + 1):
            leave_one = np.ones(valid)
            for k in range(shift_order + 1):
                if k != m:
                    leave_one *= shifted[k]
            alpha_m = beta * leave_one
            delayed_X = X[start - m * period: len(X) - m * period]
            expected_rhs += delayed_X.T @ alpha_m
        expected = np.linalg.solve(
            X.T @ X,
            (np.sum(y**2) / (2.0 * np.sum(beta**2))) * expected_rhs,
        )
        actual = _mckd_filter_update(X, f, period=period, shift_order=shift_order, ridge=0.0)
        np.testing.assert_allclose(actual, expected, rtol=1e-11, atol=1e-11)

        # 旧错误把 alpha 直接放到未延迟的 X0 上；反例必须能区分两种公式。
        wrong_rhs = X[start:].T @ (2.0 * beta) + X[:valid].T @ (2.0 * beta)
        wrong = np.linalg.solve(
            X.T @ X,
            (np.sum(y**2) / (2.0 * np.sum(beta**2))) * wrong_rhs,
        )
        self.assertGreater(float(np.linalg.norm(actual - wrong)), 1e-3)


class DeconvolutionPipelineTests(unittest.TestCase):
    def setUp(self):
        self.fs = 2048.0
        t = np.arange(4096) / self.fs
        self.signal = np.sin(2 * np.pi * 700.0 * t) * (1 + np.cos(2 * np.pi * 80.0 * t))

    def test_mckd_explicit_bpfo_and_bpfi_have_distinct_periods(self):
        bpfo = MCKDEnvelopePipeline().run(
            self.signal,
            self.fs,
            MCKDParameters(target_fault="BPFO", target_frequency_hz=80.0, filter_length=16, max_iterations=3),
        )
        bpfi = MCKDEnvelopePipeline().run(
            self.signal,
            self.fs,
            MCKDParameters(target_fault="BPFI", target_frequency_hz=128.0, filter_length=16, max_iterations=3),
        )
        self.assertEqual(bpfo.status, "computed", bpfo.reason)
        self.assertEqual(bpfi.status, "computed", bpfi.reason)
        self.assertEqual(bpfo.metadata["target_fault"], "BPFO")
        self.assertEqual(bpfi.metadata["target_fault"], "BPFI")
        self.assertEqual(bpfo.metadata["period_samples"], round(self.fs / 80.0))
        self.assertEqual(bpfi.metadata["period_samples"], round(self.fs / 128.0))
        self.assertNotEqual(bpfo.metadata["period_samples"], bpfi.metadata["period_samples"])

    def test_mckd_can_derive_requested_fault_from_real_geometry(self):
        geometry = BearingGeometry(9, 7.94, 38.52, 0.0)
        expected = geometry.fault_frequencies(25.0)["BPFI"]
        result = MCKDEnvelopePipeline().run(
            self.signal,
            self.fs,
            MCKDParameters(target_fault="BPFI", filter_length=16, max_iterations=2),
            geometry=geometry,
            rot_frequency_hz=25.0,
        )
        self.assertEqual(result.status, "computed", result.reason)
        self.assertAlmostEqual(result.metadata["target_frequency_hz"], expected)
        self.assertEqual(result.metadata["period_samples"], round(self.fs / expected))

    def test_missing_mckd_parameters_is_not_med_fallback(self):
        result = MCKDEnvelopePipeline().run(
            self.signal,
            self.fs,
            MCKDParameters(target_fault="BPFO", filter_length=16, max_iterations=2),
        )
        self.assertEqual(result.status, "indeterminate")
        self.assertEqual(result.reason, "missing_target_frequency_or_period")
        self.assertIsNone(result.representation)
        self.assertNotIn("MED", result.method)

    def test_med_pipeline_has_isolated_impulse_objective_and_no_period(self):
        result = MEDEnvelopePipeline().run(
            self.signal,
            self.fs,
            MEDParameters(filter_length=16, max_iterations=3),
        )
        self.assertEqual(result.status, "computed", result.reason)
        self.assertEqual(result.metadata["objective"], "normalized_kurtosis")
        self.assertNotIn("period_samples", result.metadata)
        self.assertIsNotNone(result.representation)


if __name__ == "__main__":
    unittest.main(verbosity=2)
