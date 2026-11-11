"""从公开 EMD 族入口核对筛分替换、固定随机序列和冻结误差预算。"""

import unittest
from dataclasses import replace

import numpy as np
from scipy.interpolate import CubicSpline, PchipInterpolator

from app.algorithms.decomposition.emd import (
    EMDParameters,
    EnsembleParameters,
    PythonEMDImplementation,
    decompose_ceemdan,
    decompose_eemd,
    decompose_emd,
)
from app.algorithms.decomposition.emd.python_adapter import _sift, rilling_stop
from tests.diagnosis.algorithms.emd_reference_contract import (
    CONTRACT,
    SAMPLE_RATE_HZ,
    assert_array_close,
    assert_result_close,
    reference_signals,
)


def run_family(method, signal, parameters, implementation=None, *, noise_scale=0.15):
    """所有对照都经过现有公开分解入口和参数校验。"""
    if method == "emd":
        return decompose_emd(signal, SAMPLE_RATE_HZ, parameters, implementation)
    entry = decompose_eemd if method == "eemd" else decompose_ceemdan
    return entry(
        signal,
        SAMPLE_RATE_HZ,
        seed=CONTRACT["seed"],
        parameters=EnsembleParameters(
            emd=parameters, ensemble_size=3, noise_scale=noise_scale
        ),
        implementation=implementation,
    )


class RecordingKernel:
    """记录实际筛分输入，同时验证借用输入没有被核修改。"""

    def __init__(self):
        self.inputs = []

    def __call__(self, values, parameters):
        before = values.copy()
        self.inputs.append(before)
        readonly = values.view()
        readonly.flags.writeable = False
        result = _sift(readonly, parameters)
        np.testing.assert_array_equal(values, before)
        return result


class SiftContractTests(unittest.TestCase):
    def test_public_family_uses_injected_kernel_without_changing_python_results(self):
        for interpolation in ("pchip", "cubic"):
            for stopping_rule in ("sd", "rilling"):
                params = EMDParameters(
                    max_imfs=3,
                    max_sifts=20,
                    interpolation=interpolation,
                    stopping_rule=stopping_rule,
                )
                for method in ("emd", "eemd", "ceemdan"):
                    signal = reference_signals()["two_tones"]
                    original = signal.copy()
                    recording_kernel = RecordingKernel()

                    with self.subTest(
                        interpolation=interpolation, rule=stopping_rule, method=method
                    ):
                        expected = run_family(method, signal, params)
                        actual = run_family(
                            method,
                            signal,
                            params,
                            PythonEMDImplementation(sift_kernel=recording_kernel),
                        )
                        self.assertTrue(recording_kernel.inputs)
                        assert_result_close(self, actual, expected, signal)
                        # 同一个 Python 核应完全保持运算次序；未来原生核使用冻结预算。
                        for observed, reference in zip(actual.imfs, expected.imfs):
                            np.testing.assert_array_equal(observed, reference)
                        np.testing.assert_array_equal(
                            actual.residual, expected.residual
                        )
                        np.testing.assert_array_equal(signal, original)

    def test_noise_free_branches_and_errors_use_the_instance_kernel(self):
        params = EMDParameters(max_imfs=2, max_sifts=10)
        signal = reference_signals()["two_tones"]

        def failing_kernel(values, parameters):
            raise RuntimeError("selected sift failed")

        for method in ("emd", "eemd", "ceemdan"):
            for noise_scale in (0.0, 0.15):
                with (
                    self.subTest(method=method, noise_scale=noise_scale),
                    self.assertRaisesRegex(RuntimeError, "selected sift failed"),
                ):
                    run_family(
                        method,
                        signal,
                        params,
                        PythonEMDImplementation(sift_kernel=failing_kernel),
                        noise_scale=noise_scale,
                    )

    def test_fixed_seed_preserves_each_sift_input_and_result(self):
        signal = reference_signals()["two_tones"]
        params = EMDParameters(max_imfs=3, max_sifts=12)
        for method in ("eemd", "ceemdan"):
            runs = []
            for _ in range(2):
                recording_kernel = RecordingKernel()

                result = run_family(
                    method,
                    signal,
                    params,
                    PythonEMDImplementation(sift_kernel=recording_kernel),
                )
                runs.append((recording_kernel.inputs, result))
            self.assertEqual(len(runs[0][0]), len(runs[1][0]))
            for first, second in zip(runs[0][0], runs[1][0]):
                np.testing.assert_array_equal(first, second)
            assert_result_close(self, runs[0][1], runs[1][1], signal)

    def test_reference_signals_cover_shape_scale_and_nonconvergence(self):
        params = EMDParameters(max_imfs=2, max_sifts=1, sd_threshold=1e-30)
        for name, signal in reference_signals().items():
            with self.subTest(signal=name):
                expected = run_family("emd", signal, params)
                actual = run_family(
                    "emd", signal, params, PythonEMDImplementation(sift_kernel=_sift)
                )
                assert_result_close(self, actual, expected, signal)
                self.assertEqual(actual.input_length, len(signal))
                if name in ("constant", "zero", "monotonic"):
                    self.assertEqual(actual.status, "indeterminate")
                    self.assertEqual(actual.imfs, ())
                    np.testing.assert_array_equal(actual.residual, signal)
                elif actual.imfs:
                    self.assertFalse(all(actual.converged))
                    self.assertEqual(actual.reason, "maximum_sifts_reached")

    def test_local_interpolators_have_independent_known_curves(self):
        coordinates = np.array([-3.0, -2.0, -0.7, 0.5, 1.0, 5.0])
        line = lambda x: 3 * x - 2
        quadratic = lambda x: 2 * x * x + 3 * x - 1
        cubic = lambda x: 3 * x**3 - 2 * x * x + 7
        cases = (
            (CubicSpline, np.array([-2.0, 3.0]), line),
            (CubicSpline, np.array([-2.0, -0.5, 3.0]), quadratic),
            (CubicSpline, np.array([-2.0, -1.5, 0.0, 2.0, 4.0]), cubic),
            (PchipInterpolator, np.array([-2.0, -1.5, 0.0, 2.0, 4.0]), line),
        )
        for interpolator, nodes, function in cases:
            expected = function(coordinates)
            actual = interpolator(nodes, function(nodes), extrapolate=True)(coordinates)
            assert_array_close(self, actual, expected, expected, stage="local")
        pchip = PchipInterpolator([0.0, 1.0, 3.0], [0.0, 1.0, 5.0])
        assert_array_close(
            self,
            pchip.derivative()([0.0, 1.0, 3.0]),
            np.array([2 / 3, 9 / 7, 8 / 3]),
            np.array([5.0]),
            stage="local",
        )
        self.assertAlmostEqual(float(pchip(0.5)), 71 / 168)

    def test_rilling_zero_amplitude_and_threshold_boundaries(self):
        thresholds = (0.05, 0.5, 0.05)
        self.assertTrue(rilling_stop(np.zeros(20), np.zeros(20), thresholds))
        self.assertFalse(rilling_stop(np.ones(20), np.ones(20), thresholds))
        self.assertTrue(rilling_stop(np.ones(20), -np.ones(20), thresholds))
        # ratio == sd1 合法；单点 ratio == sd2 且超标比例恰好等于 fraction 也合法。
        upper, lower = np.full(20, 1.0), np.full(20, -1.0)
        upper[0], lower[0] = 1.5, -0.5
        self.assertTrue(rilling_stop(upper, lower, thresholds))
        upper[0] = np.nextafter(1.5, np.inf)
        self.assertFalse(rilling_stop(upper, lower, thresholds))

    def test_completeness_cannot_hide_a_different_mode(self):
        signal = reference_signals()["two_tones"]
        reference = run_family("emd", signal, EMDParameters(max_imfs=3))
        change = np.sin(np.arange(len(signal))) * 0.01
        changed = replace(
            reference,
            imfs=(reference.imfs[0] + change, *reference.imfs[1:]),
            residual=reference.residual - change,
        )
        np.testing.assert_allclose(
            changed.reconstructed, reference.reconstructed, atol=1e-14
        )
        with self.assertRaises(AssertionError):
            assert_result_close(self, changed, reference, signal)
        small_change = np.full(len(signal), 1e-12)
        rounded = replace(reference, residual=reference.residual + small_change)
        assert_result_close(self, rounded, reference, signal)

    def test_near_zero_residual_uses_absolute_budget_but_rejects_excess_error(self):
        signal = np.ones(32)
        reference = np.full(32, 1e-24)
        absolute_budget = CONTRACT["decomposition"]["atol_scaled"]
        assert_array_close(self, reference + absolute_budget * 0.25, reference, signal)
        with self.assertRaises(AssertionError):
            assert_array_close(self, reference + absolute_budget * 2, reference, signal)


if __name__ == "__main__":
    unittest.main()
