"""MED/MCKD 数学反例、留一更新和 BPFO/BPFI 目标周期。"""

import os
import sys
import unittest
from unittest import mock

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
    maximum_correlated_kurtosis_deconvolution,
    minimum_entropy_deconvolution,
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
        self.assertAlmostEqual(
            normalized_kurtosis(periodic), normalized_kurtosis(random), places=12
        )
        self.assertGreater(correlated_kurtosis(periodic, period=10, shift_order=1), 0.0)
        self.assertAlmostEqual(
            correlated_kurtosis(random, period=10, shift_order=1), 0.0, places=12
        )

    def test_mckd_update_contains_leave_one_product_and_delayed_input(self):
        x = np.array([0.5, -1.0, 2.0, 0.25, 1.5, -0.5, 1.0, 0.75])
        f = np.array([0.2, -0.4, 0.3])
        period = 2
        shift_order = 1
        X = sliding_window_view(x, len(f))
        y = X @ f
        start = period * shift_order
        valid = len(y) - start
        shifted = [
            y[start - m * period : len(y) - m * period] for m in range(shift_order + 1)
        ]
        beta = np.prod(np.vstack(shifted), axis=0)

        expected_rhs = np.zeros(len(f))
        for m in range(shift_order + 1):
            leave_one = np.ones(valid)
            for k in range(shift_order + 1):
                if k != m:
                    leave_one *= shifted[k]
            alpha_m = beta * leave_one
            delayed_X = X[start - m * period : len(X) - m * period]
            expected_rhs += delayed_X.T @ alpha_m
        expected = np.linalg.solve(
            X.T @ X,
            (np.sum(y**2) / (2.0 * np.sum(beta**2))) * expected_rhs,
        )
        actual = _mckd_filter_update(
            X, f, period=period, shift_order=shift_order, ridge=0.0
        )
        np.testing.assert_allclose(actual, expected, rtol=1e-11, atol=1e-11)

        # 旧错误把 alpha 直接放到未延迟的 X0 上；反例必须能区分两种公式。
        wrong_rhs = X[start:].T @ (2.0 * beta) + X[:valid].T @ (2.0 * beta)
        wrong = np.linalg.solve(
            X.T @ X,
            (np.sum(y**2) / (2.0 * np.sum(beta**2))) * wrong_rhs,
        )
        self.assertGreater(float(np.linalg.norm(actual - wrong)), 1e-3)

    def test_normalized_objectives_obey_amplitude_scale_invariance(self):
        periodic = np.zeros(81)
        periodic[[10, 20, 30, 40, 50, 60]] = [1.0, -0.8, 1.1, 0.9, -1.0, 0.7]
        reference_kurtosis = normalized_kurtosis(periodic)
        reference_ck = correlated_kurtosis(periodic, period=10, shift_order=1)
        for scale in (1e-150, 1e-8, 1e8, 1e150):
            with self.subTest(scale=scale):
                self.assertAlmostEqual(
                    normalized_kurtosis(periodic * scale), reference_kurtosis, places=11
                )
                self.assertAlmostEqual(
                    correlated_kurtosis(periodic * scale, period=10, shift_order=1),
                    reference_ck,
                    places=11,
                )


class DeconvolutionPipelineTests(unittest.TestCase):
    def setUp(self):
        self.fs = 2048.0
        t = np.arange(4096) / self.fs
        self.signal = np.sin(2 * np.pi * 700.0 * t) * (1 + np.cos(2 * np.pi * 80.0 * t))

    def test_mckd_explicit_bpfo_and_bpfi_have_distinct_periods(self):
        bpfo = MCKDEnvelopePipeline().run(
            self.signal,
            self.fs,
            MCKDParameters(
                target_fault="BPFO",
                target_frequency_hz=80.0,
                filter_length=16,
                max_iterations=3,
            ),
        )
        bpfi = MCKDEnvelopePipeline().run(
            self.signal,
            self.fs,
            MCKDParameters(
                target_fault="BPFI",
                target_frequency_hz=128.0,
                filter_length=16,
                max_iterations=3,
            ),
        )
        self.assertEqual(bpfo.status, "computed", bpfo.reason)
        self.assertEqual(bpfi.status, "computed", bpfi.reason)
        self.assertEqual(bpfo.metadata["target_fault"], "BPFO")
        self.assertEqual(bpfi.metadata["target_fault"], "BPFI")
        self.assertEqual(bpfo.metadata["period_samples"], round(self.fs / 80.0))
        self.assertEqual(bpfi.metadata["period_samples"], round(self.fs / 128.0))
        self.assertNotEqual(
            bpfo.metadata["period_samples"], bpfi.metadata["period_samples"]
        )

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

    def test_filter_normalization_iteration_and_objective_histories_are_scale_invariant(
        self,
    ):
        cases = (
            (
                minimum_entropy_deconvolution,
                MEDParameters(filter_length=16, max_iterations=3),
                None,
            ),
            (
                maximum_correlated_kurtosis_deconvolution,
                MCKDParameters(target_fault="BPFO", filter_length=16, max_iterations=3),
                26,
            ),
        )
        for function, parameters, period in cases:
            reference = (
                function(self.signal, parameters)
                if period is None
                else function(self.signal, period, parameters)
            )
            for scale in (1e-8, 1e8):
                with self.subTest(function=function.__name__, scale=scale):
                    scaled = (
                        function(self.signal * scale, parameters)
                        if period is None
                        else function(self.signal * scale, period, parameters)
                    )
                    self.assertEqual(scaled.iterations, reference.iterations)
                    self.assertEqual(scaled.converged, reference.converged)
                    np.testing.assert_allclose(
                        scaled.objective_history,
                        reference.objective_history,
                        rtol=1e-8,
                        atol=1e-12,
                    )
                    np.testing.assert_allclose(
                        scaled.filter_coefficients,
                        reference.filter_coefficients,
                        rtol=2e-3,
                        atol=2e-3,
                    )
                    expected_signal = reference.signal * scale
                    np.testing.assert_allclose(
                        scaled.signal,
                        expected_signal,
                        rtol=2e-3,
                        atol=max(
                            float(np.max(np.abs(expected_signal))) * 2e-3,
                            np.finfo(float).tiny,
                        ),
                    )

    def test_single_harmonic_unregularized_rank_deficiency_is_not_a_finite_success(
        self,
    ):
        fs = 1000.0
        signal = np.sin(2.0 * np.pi * 50.0 * np.arange(1024) / fs)
        X = sliding_window_view(signal - np.mean(signal), 16)
        initial_filter = np.zeros(16)
        initial_filter[8] = 1.0
        y = X @ initial_filter
        normal = X.T @ X
        rhs = (np.sum(y**2) / np.sum(y**4)) * (X.T @ (y**3))
        # 独立前提：真实数值秩亏，但普通 solve 并不抛异常且返回有限解。
        self.assertLess(np.linalg.matrix_rank(normal), 16)
        self.assertTrue(np.all(np.isfinite(np.linalg.solve(normal, rhs))))

        cases = (
            (
                MEDEnvelopePipeline(),
                MEDParameters(filter_length=16, max_iterations=3, ridge=0.0),
            ),
            (
                MCKDEnvelopePipeline(),
                MCKDParameters(
                    target_fault="BPFO",
                    target_frequency_hz=50.0,
                    filter_length=16,
                    max_iterations=3,
                    ridge=0.0,
                ),
            ),
        )
        for pipeline, parameters in cases:
            with self.subTest(pipeline=pipeline.method):
                result = pipeline.run(signal, fs, parameters)
                self.assertEqual(result.status, "indeterminate")
                self.assertEqual(result.reason, "numerical_deconvolution_failure")
                self.assertIsNone(result.representation)

    def test_positive_ridge_defines_regularized_solution_for_same_harmonic(self):
        fs = 1000.0
        signal = np.sin(2.0 * np.pi * 50.0 * np.arange(1024) / fs)
        cases = (
            (
                MEDEnvelopePipeline(),
                MEDParameters(filter_length=16, max_iterations=3, ridge=1e-8),
            ),
            (
                MCKDEnvelopePipeline(),
                MCKDParameters(
                    target_fault="BPFO",
                    target_frequency_hz=50.0,
                    filter_length=16,
                    max_iterations=3,
                    ridge=1e-8,
                ),
            ),
        )
        for pipeline, parameters in cases:
            with self.subTest(pipeline=pipeline.method):
                result = pipeline.run(signal, fs, parameters)
                self.assertEqual(result.status, "computed", result.reason)
                self.assertIsNotNone(result.representation)

    def test_full_rank_periodic_impulses_remain_computable_without_ridge(self):
        fs = 1000.0
        rng = np.random.default_rng(73)
        impulses = np.zeros(2048)
        impulses[np.arange(20, len(impulses), 20)] = 1.0
        ringing_time = np.arange(16) / fs
        ringing = np.exp(-180.0 * ringing_time) * np.sin(
            2.0 * np.pi * 180.0 * ringing_time
        )
        signal = np.convolve(
            impulses, ringing, mode="same"
        ) + 0.01 * rng.standard_normal(len(impulses))
        result = MCKDEnvelopePipeline().run(
            signal,
            fs,
            MCKDParameters(
                target_fault="BPFO",
                target_frequency_hz=50.0,
                filter_length=16,
                max_iterations=3,
                ridge=0.0,
            ),
        )
        self.assertEqual(result.status, "computed", result.reason)
        self.assertGreaterEqual(result.metadata["iterations"], 2)
        self.assertEqual(
            len(result.metadata["objective_history"]), result.metadata["iterations"]
        )
        self.assertIsNotNone(result.representation)

    def test_zero_energy_and_numerically_undefined_updates_are_not_computed(self):
        for pipeline, parameters in (
            (MEDEnvelopePipeline(), MEDParameters(filter_length=16, max_iterations=3)),
            (
                MCKDEnvelopePipeline(),
                MCKDParameters(
                    target_fault="BPFO",
                    target_frequency_hz=80.0,
                    filter_length=16,
                    max_iterations=3,
                ),
            ),
        ):
            with self.subTest(pipeline=pipeline.method):
                zero = pipeline.run(np.zeros(4096), self.fs, parameters)
                self.assertEqual(zero.status, "indeterminate")
                self.assertEqual(zero.reason, "zero_energy")
                self.assertIsNone(zero.representation)

        with mock.patch(
            "app.algorithms.bearing.deconvolution.native_diagnostic.deconvolve",
            side_effect=np.linalg.LinAlgError("singular normal equation"),
        ):
            undefined = MCKDEnvelopePipeline().run(
                self.signal,
                self.fs,
                MCKDParameters(
                    target_fault="BPFO",
                    target_frequency_hz=80.0,
                    filter_length=16,
                    max_iterations=3,
                ),
            )
        self.assertEqual(undefined.status, "indeterminate")
        self.assertEqual(undefined.reason, "numerical_deconvolution_failure")
        self.assertIsNone(undefined.representation)


if __name__ == "__main__":
    unittest.main(verbosity=2)
