"""完整原生业务族：实际入口、随机状态、生命周期和质量边界。"""

import gc
import unittest
from dataclasses import replace
from unittest.mock import patch

import numpy as np
from app.algorithms.decomposition.emd import (
    EMDParameters,
    EnsembleParameters,
    NativeEMDImplementation,
    PythonEMDImplementation,
    decompose_ceemdan,
    decompose_eemd,
    decompose_emd,
)

from cnn_compute.emd_family import decompose


class NativeFamilyTests(unittest.TestCase):
    def setUp(self):
        t = np.arange(512) / 512
        self.signal = np.sin(2 * np.pi * 64 * t) + 0.4 * np.sin(2 * np.pi * 8 * t)
        self.parameters = EMDParameters(max_imfs=3, max_sifts=40)
        self.ensemble = EnsembleParameters(
            self.parameters, ensemble_size=4, noise_scale=0.15
        )

    def test_default_never_calls_python_or_numpy_rng_and_owns_results(self):
        source = np.column_stack((self.signal, self.signal))
        values = source[:, 0]
        original = source.copy()
        with (
            patch.object(
                PythonEMDImplementation, "emd", side_effect=AssertionError("Python EMD")
            ),
            patch.object(
                PythonEMDImplementation,
                "eemd",
                side_effect=AssertionError("Python EEMD"),
            ),
            patch.object(
                PythonEMDImplementation,
                "ceemdan",
                side_effect=AssertionError("Python CEEMDAN"),
            ),
            patch("numpy.random.default_rng", side_effect=AssertionError("NumPy RNG")),
        ):
            results = [decompose_emd(values, 512, self.parameters)]
            results.extend(
                entry(values, 512, seed=2**200 + 123, parameters=self.ensemble)
                for entry in (decompose_eemd, decompose_ceemdan)
            )
        np.testing.assert_array_equal(source, original)
        for result in results:
            self.assertEqual(result.status, "valid")
            np.testing.assert_allclose(result.reconstructed, values, atol=1e-12)
            snapshots = [x.copy() for x in (*result.imfs, result.residual)]
            decompose(self.signal * 0.7, max_imfs=2)
            gc.collect()
            for output, snapshot in zip((*result.imfs, result.residual), snapshots):
                self.assertFalse(np.shares_memory(output, source))
                np.testing.assert_array_equal(output, snapshot)

    def test_noise_free_ensembles_equal_deterministic_emd(self):
        expected = decompose_emd(self.signal, 512, self.parameters)
        for entry in (decompose_eemd, decompose_ceemdan):
            actual = entry(
                self.signal,
                512,
                seed=11,
                parameters=replace(self.ensemble, noise_scale=0),
            )
            np.testing.assert_array_equal(actual.residual, expected.residual)
            for first, second in zip(actual.imfs, expected.imfs):
                np.testing.assert_array_equal(first, second)

    def test_native_boundary_and_failure_do_not_fallback(self):
        for input in (np.ones((8, 2)), np.ones(7), np.full(8, np.nan)):
            with self.assertRaises(ValueError):
                decompose(input)
        for options in (
            {"max_sifts": 0},
            {"max_imfs": 0},
            {"noise_scale": -1},
            {"rilling_thresholds": (0, 0.5, 0.05)},
            {"seed": -1},
            {"seed": True},
            {"interpolation": "bad"},
            {"method": "bad"},
        ):
            with self.assertRaises(ValueError):
                decompose(self.signal, **options)
        for implementation in (NativeEMDImplementation(), PythonEMDImplementation()):
            with self.assertRaises(ValueError):
                decompose_emd(np.full(16, np.inf), 512, implementation=implementation)
        with self.assertRaises(RuntimeError):
            decompose(
                self.signal,
                method="eemd",
                noise_scale=np.finfo(float).max,
                ensemble_size=3,
            )

    def test_status_and_scale_survive_complete_native_call(self):
        for method in ("emd", "eemd", "ceemdan"):
            for scale in (1e-150, 1e150):
                result = decompose(
                    self.signal * scale,
                    method=method,
                    max_imfs=2,
                    ensemble_size=3,
                    max_sifts=1,
                    sd_threshold=1e-30,
                )
                self.assertEqual(result.reason, "maximum_sifts_reached")
                self.assertFalse(all(result.converged))
                reconstructed = sum(result.imfs, start=result.residual.copy()) / scale
                np.testing.assert_allclose(reconstructed, self.signal, atol=1e-12)
            empty = decompose(np.ones(64), method=method)
            self.assertEqual(empty.status, "indeterminate")
            self.assertEqual(empty.reason, "zero_variance")


if __name__ == "__main__":
    unittest.main()
