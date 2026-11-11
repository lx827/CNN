"""原生四种筛分配置与公开 EMD 族差分，不修改冻结预算。"""

import gc
import hashlib
import json
import os
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np
from app.algorithms.decomposition.emd import (
    EMDParameters,
    EnsembleParameters,
    NativeEMDImplementation,
    decompose_ceemdan,
    decompose_eemd,
    decompose_emd,
)
from app.algorithms.decomposition.emd.python_adapter import (
    _envelopes,
    _sift,
    rilling_stop,
)
from app.algorithms.decomposition.selection import compute_component_metrics_batch
from app.algorithms.pipelines.decomposition import (
    DecompositionDenoisingAnalysis,
    EMDDenoisingPipeline,
)
from scipy.interpolate import CubicSpline, PchipInterpolator
from tests.diagnosis.algorithms.emd_reference_contract import (
    assert_array_close,
    assert_result_close,
    reference_signals,
)

from cnn_compute import _native, build_info, sift_imf, sift_pchip_sd


class NativeEMDTests(unittest.TestCase):
    def test_public_emd_matches_frozen_signal_contract(self):
        implementation = NativeEMDImplementation()
        for name, signal in reference_signals().items():
            for max_sifts, threshold in ((100, 0.2), (1, 1e-30), (4, 1e6)):
                with self.subTest(signal=name, max_sifts=max_sifts):
                    parameters = EMDParameters(
                        max_imfs=4, max_sifts=max_sifts, sd_threshold=threshold
                    )
                    original = signal.copy()
                    expected = decompose_emd(signal, 512, parameters)
                    actual = decompose_emd(signal, 512, parameters, implementation)
                    assert_result_close(self, actual, expected, signal)
                    np.testing.assert_array_equal(signal, original)

    def test_local_envelopes_and_imf_match_stricter_budget(self):
        parameters = EMDParameters()
        for name, signal in reference_signals().items():
            values = np.ascontiguousarray(signal)
            values.flags.writeable = False
            with self.subTest(signal=name):
                expected = _envelopes(values, parameters)
                actual = _native._envelopes_pchip(values, 3)
                if expected is None:
                    self.assertIsNone(actual)
                else:
                    for first, second in zip(actual, expected):
                        assert_array_close(self, first, second, values, stage="local")
                reference = _sift(values, parameters)
                candidate = sift_pchip_sd(values)
                if reference is None:
                    self.assertIsNone(candidate)
                else:
                    self.assertEqual(candidate[1:], reference[1:])
                    assert_array_close(
                        self, candidate[0], reference[0], values, stage="local"
                    )

    def test_pchip_nonuniform_nodes_small_cases_and_extrapolation(self):
        rng = np.random.default_rng(20261112)
        cases = [
            (np.array([0.0, 2.0]), np.array([1.0, 5.0])),
            (np.array([0.0, 1.0, 3.0]), np.array([0.0, 1.0, 5.0])),
            (
                np.array([0.0, 1e-7, 0.2, 0.8, 4.0]),
                np.array([0.0, 0.0, 2.0, 1.0, -1.0]),
            ),
        ]
        for length in (4, 19, 257):
            cases.append(
                (np.cumsum(rng.uniform(0.01, 1, length)), rng.normal(size=length))
            )
        for x, y in cases:
            query = np.concatenate((x, np.linspace(x[0] - 0.1, x[-1] + 0.1, 173)))
            query = query[::-1].copy()
            expected = PchipInterpolator(x, y, extrapolate=True)(query)
            actual = _native._pchip(x, y, query)
            assert_array_close(self, actual, expected, expected, stage="local")

    def test_boundary_validation_and_output_owner(self):
        parent = np.column_stack((reference_signals()["two_tones"], np.zeros(256)))
        sliced = parent[:, 0]
        original = parent.copy()
        first = sift_pchip_sd(sliced)
        np.testing.assert_array_equal(parent, original)
        self.assertFalse(np.shares_memory(first[0], parent))
        preserved = first[0].copy()
        del parent, sliced
        gc.collect()
        sift_pchip_sd(np.random.default_rng(2).normal(size=256))
        np.testing.assert_array_equal(first[0], preserved)
        self.assertTrue(first[0].flags.c_contiguous)
        self.assertIsNotNone(first[0].base)
        for invalid in (np.ones(12, dtype=np.float32), [0.0] * 12):
            with self.assertRaises(TypeError):
                sift_pchip_sd(invalid)
        for invalid in (np.zeros((4, 4)), np.ones(7), np.array([np.nan] * 8)):
            with self.assertRaises(ValueError):
                sift_pchip_sd(invalid)
        for kwargs in (
            {"max_sifts": 0},
            {"mirror_extrema": -1},
            {"sd_threshold": np.nan},
        ):
            with self.assertRaises(ValueError):
                sift_pchip_sd(np.ones(8), **kwargs)
        with self.assertRaises(TypeError):
            _native.sift_pchip_sd(np.ones(32)[::2], 100, 3, 0.2)
        with self.assertRaises(RuntimeError):
            _native._pchip(
                np.array([0.0, 1e-300]), np.array([-1e308, 1e308]), np.array([0.5])
            )

    def test_all_configurations_through_public_emd(self):
        for method in ("pchip", "cubic"):
            for rule in ("sd", "rilling"):
                for name, signal in reference_signals().items():
                    with self.subTest(
                        interpolation=method, stopping_rule=rule, signal=name
                    ):
                        parameters = EMDParameters(
                            max_imfs=4, interpolation=method, stopping_rule=rule
                        )
                        expected = decompose_emd(signal, 512, parameters)
                        actual = decompose_emd(
                            signal, 512, parameters, NativeEMDImplementation()
                        )
                        assert_result_close(self, actual, expected, signal)

    def test_all_configurations_local_envelopes_and_sift(self):
        for method in ("pchip", "cubic"):
            for rule in ("sd", "rilling"):
                parameters = EMDParameters(interpolation=method, stopping_rule=rule)
                for name, signal in reference_signals().items():
                    values = np.ascontiguousarray(signal)
                    with self.subTest(
                        interpolation=method, stopping_rule=rule, signal=name
                    ):
                        expected = _envelopes(values, parameters)
                        actual = _native._envelopes(values, 3, method)
                        if expected is None:
                            self.assertIsNone(actual)
                        else:
                            for observed, reference in zip(actual, expected):
                                assert_array_close(
                                    self, observed, reference, values, stage="local"
                                )
                        expected_sift = _sift(values, parameters)
                        actual_sift = sift_imf(
                            values, interpolation=method, stopping_rule=rule
                        )
                        if expected_sift is None:
                            self.assertIsNone(actual_sift)
                        else:
                            self.assertEqual(actual_sift[1:], expected_sift[1:])
                            assert_array_close(
                                self,
                                actual_sift[0],
                                expected_sift[0],
                                values,
                                stage="local",
                            )

    def test_cubic_not_a_knot_small_nodes_and_extrapolation(self):
        rng = np.random.default_rng(20261112)
        cases = [
            (np.array([-2.0, 3.0]), lambda x: 3 * x - 2),
            (np.array([-2.0, -0.5, 3.0]), lambda x: 2 * x * x + 3 * x - 1),
            (np.array([-2.0, -1.5, 0.0, 2.0, 4.0]), lambda x: 3 * x**3 - 2 * x * x + 7),
        ]
        query = np.array([-3.0, -2.0, -0.7, 0.5, 1.0, 5.0])
        for x, function in cases:
            y = function(x)
            expected = function(query)
            assert_array_close(
                self, _native._cubic(x, y, query), expected, expected, stage="local"
            )
        for size in (3, 4, 19, 257):
            x = np.cumsum(rng.uniform(0.01, 1, size))
            y = rng.normal(size=size)
            query = np.concatenate((x, np.linspace(x[0] - 0.1, x[-1] + 0.1, 173)))[
                ::-1
            ].copy()
            expected = CubicSpline(x, y, extrapolate=True)(query)
            assert_array_close(
                self, _native._cubic(x, y, query), expected, expected, stage="local"
            )

    def test_rilling_zero_amplitude_threshold_and_fraction_boundaries(self):
        thresholds = (0.05, 0.5, 0.05)
        cases = [
            (np.zeros(20), np.zeros(20)),
            (np.ones(20), np.ones(20)),
            (np.ones(20), -np.ones(20)),
        ]
        for mean in (0.05, np.nextafter(0.05, np.inf), 0.5, np.nextafter(0.5, np.inf)):
            upper, lower = np.ones(20), -np.ones(20)
            upper[0], lower[0] = 1.0 + mean, -1.0 + mean
            cases.append((upper, lower))
        rng = np.random.default_rng(3)
        cases.extend((rng.normal(size=29), rng.normal(size=29)) for _ in range(20))
        for upper, lower in cases:
            self.assertEqual(
                _native._rilling_stop(upper, lower, thresholds),
                rilling_stop(upper, lower, thresholds),
            )
        upper, lower = np.ones(20), -np.ones(20)
        upper[0], lower[0] = 1.5, -0.5
        self.assertTrue(_native._rilling_stop(upper, lower, thresholds))
        upper[0] = np.nextafter(1.5, np.inf)
        self.assertFalse(_native._rilling_stop(upper, lower, thresholds))
        upper[:2], lower[:2] = 1.1, -0.9
        self.assertFalse(_native._rilling_stop(upper, lower, thresholds))

    def test_ensemble_candidates_keep_fixed_seed_formulas_and_repeatability(self):
        signal = reference_signals()["trend"]
        for method in ("pchip", "cubic"):
            for rule in ("sd", "rilling"):
                parameters = EnsembleParameters(
                    emd=EMDParameters(
                        max_imfs=3,
                        max_sifts=50,
                        interpolation=method,
                        stopping_rule=rule,
                    ),
                    ensemble_size=4,
                    noise_scale=0.15,
                )
                for decompose in (decompose_eemd, decompose_ceemdan):
                    with self.subTest(
                        interpolation=method,
                        stopping_rule=rule,
                        method=decompose.__name__,
                    ):
                        expected = decompose(
                            signal, 512, seed=20261112, parameters=parameters
                        )
                        actual = decompose(
                            signal,
                            512,
                            seed=20261112,
                            parameters=parameters,
                            implementation=NativeEMDImplementation(),
                        )
                        repeated = decompose(
                            signal,
                            512,
                            seed=20261112,
                            parameters=parameters,
                            implementation=NativeEMDImplementation(),
                        )
                        assert_result_close(self, actual, expected, signal)
                        for first, second in zip(actual.imfs, repeated.imfs):
                            np.testing.assert_array_equal(first, second)
                        np.testing.assert_array_equal(
                            actual.residual, repeated.residual
                        )

    def test_generic_boundary_validation_has_no_silent_fallback(self):
        signal = reference_signals()["two_tones"]
        for kwargs in (
            {"interpolation": "natural"},
            {"stopping_rule": "other"},
            {"rilling_thresholds": (0.0, 0.5, 0.05)},
            {"rilling_thresholds": (0.05, 0.5, np.nan)},
        ):
            with self.assertRaises(ValueError):
                sift_imf(signal, **kwargs)

    def test_nonconverged_candidate_remains_quality_insufficient(self):
        signal = reference_signals()["two_tones"]
        for method in ("pchip", "cubic"):
            for rule in ("sd", "rilling"):
                parameters = EMDParameters(
                    max_imfs=2,
                    max_sifts=1,
                    sd_threshold=1e-30,
                    interpolation=method,
                    stopping_rule=rule,
                    rilling_thresholds=(1e-30, 1e-29, 0.0),
                )
                pipeline = EMDDenoisingPipeline(parameters)
                result = decompose_emd(
                    signal, 512, parameters, NativeEMDImplementation()
                )
                analysis = DecompositionDenoisingAnalysis(
                    result,
                    compute_component_metrics_batch(result.imfs, 512, signal),
                    signal,
                )
                selection = pipeline.evaluate(analysis, correlation_threshold=0)
                self.assertEqual(selection.quality_status, "insufficient")
                self.assertEqual(selection.reason, "maximum_sifts_reached")

    def test_build_reports_floating_point_policy_and_simd(self):
        info = build_info()
        self.assertTrue(info["simd"])
        if expected_arch := os.environ.get("CNN_COMPUTE_ARCH"):
            self.assertEqual(info["arch_policy"], expected_arch)
        self.assertIn(
            "/fp:strict" if os.name == "nt" else "-ffp-contract=off",
            info["compile_options"],
        )


@unittest.skipUnless(
    os.environ.get("CNN_DATA_ROOT"), "设置 CNN_DATA_ROOT 验证既有固定性能向量"
)
class NativeEMDFixedVectorTests(unittest.TestCase):
    def test_fixed_vectors_all_configurations_and_ensemble_formulas(self):
        campaign = (
            Path(os.environ["CNN_DATA_ROOT"]) / "real_diagnosis/performance/20261112"
        )
        vectors = json.loads((campaign / "vectors.json").read_text(encoding="utf-8"))
        selected = [entry for entry in vectors if entry["id"].endswith("__short")]
        self.assertEqual(len(selected), 5)
        config = json.loads((campaign / "config.json").read_text(encoding="utf-8"))
        for entry in selected:
            vector = np.load(
                campaign / entry["file"].replace("\\", "/"), allow_pickle=False
            )
            self.assertEqual(
                hashlib.sha256(np.asarray(vector, dtype="<f8").tobytes()).hexdigest(),
                entry["sha256_float64_le"],
            )
            fs = entry["sample_rate_hz"]
            for method in ("pchip", "cubic"):
                for rule in ("sd", "rilling"):
                    parameters = replace(
                        EMDParameters(**config["emd"]),
                        interpolation=method,
                        stopping_rule=rule,
                    )
                    with self.subTest(
                        vector=entry["id"],
                        interpolation=method,
                        stopping_rule=rule,
                        family="emd",
                    ):
                        expected = decompose_emd(vector, fs, parameters)
                        actual = decompose_emd(
                            vector, fs, parameters, NativeEMDImplementation()
                        )
                        assert_result_close(self, actual, expected, vector)
                    ensemble = EnsembleParameters(emd=parameters, **config["ensemble"])
                    for decompose in (decompose_eemd, decompose_ceemdan):
                        with self.subTest(
                            vector=entry["id"],
                            interpolation=method,
                            stopping_rule=rule,
                            family=decompose.__name__,
                        ):
                            expected = decompose(
                                vector, fs, seed=config["seed"], parameters=ensemble
                            )
                            actual = decompose(
                                vector,
                                fs,
                                seed=config["seed"],
                                parameters=ensemble,
                                implementation=NativeEMDImplementation(),
                            )
                            assert_result_close(self, actual, expected, vector)

    def test_five_fixed_short_vectors_by_sha256(self):
        campaign = (
            Path(os.environ["CNN_DATA_ROOT"]) / "real_diagnosis/performance/20261112"
        )
        vectors = json.loads((campaign / "vectors.json").read_text(encoding="utf-8"))
        selected = [entry for entry in vectors if entry["id"].endswith("__short")]
        self.assertEqual(len(selected), 5)
        config = json.loads((campaign / "config.json").read_text(encoding="utf-8"))
        parameters = EMDParameters(**config["emd"])
        for entry in selected:
            with self.subTest(vector=entry["id"]):
                vector = np.load(
                    campaign / entry["file"].replace("\\", "/"), allow_pickle=False
                )
                digest = hashlib.sha256(
                    np.asarray(vector, dtype="<f8").tobytes()
                ).hexdigest()
                self.assertEqual(digest, entry["sha256_float64_le"])
                self.assertEqual(len(vector), 4096)
                fs = entry["sample_rate_hz"]
                expected = decompose_emd(vector, fs, parameters)
                actual = decompose_emd(
                    vector, fs, parameters, NativeEMDImplementation()
                )
                assert_result_close(self, actual, expected, vector)


if __name__ == "__main__":
    unittest.main()
