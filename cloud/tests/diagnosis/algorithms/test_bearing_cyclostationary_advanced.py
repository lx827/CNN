"""SC/SCoh 复频移、非整数循环频率、专属评估及不可分辨反例。"""
import os
import sys
import unittest

import numpy as np
from scipy.signal import butter, sosfiltfilt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.algorithms.bearing.cyclostationary import (
    CyclostationaryPipeline,
    compute_sc_scoh,
    evaluate_cyclic_candidates,
)


FS = 2048.0


def _modulated_noise(alpha: float | None, duration: float = 4.0, seed: int = 4) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(FS * duration)
    carrier = sosfiltfilt(
        butter(4, [650.0, 850.0], btype="bandpass", fs=FS, output="sos"),
        rng.standard_normal(n),
    )
    carrier /= np.std(carrier)
    if alpha is None:
        return carrier
    t = np.arange(n) / FS
    return (1.0 + 0.85 * np.cos(2 * np.pi * alpha * t + 0.31)) * carrier


class CyclostationaryTests(unittest.TestCase):
    def test_non_integer_cyclic_frequency_has_complex_sc_peak(self):
        alpha = 47.3
        signal = _modulated_noise(alpha)
        representation = compute_sc_scoh(
            signal,
            FS,
            cyclic_frequencies_hz=[alpha, 63.7],
            segment_length=256,
            overlap_ratio=0.75,
        )
        self.assertEqual(representation.spectral_correlation.dtype, np.dtype(np.complex128))
        self.assertEqual(representation.spectral_correlation.shape, (2, 129))
        index = int(np.argmax(representation.spectral_coherence[0]))
        self.assertGreater(representation.spectral_coherence[0, index], 0.35)
        self.assertGreater(
            representation.spectral_coherence[0, index],
            4.0 * float(np.max(representation.spectral_coherence[1])),
        )
        self.assertGreater(float(np.max(np.abs(representation.spectral_correlation[0]))), 0.0)

    def test_dedicated_evaluation_uses_sc_and_scoh_background_not_envelope_snr(self):
        alpha = 47.3
        signal = _modulated_noise(alpha, seed=12)
        representation = compute_sc_scoh(
            signal,
            FS,
            cyclic_frequencies_hz=[31.0, 39.0, alpha, 55.0, 63.0, 71.0],
            segment_length=256,
        )
        evaluation = evaluate_cyclic_candidates(representation, {"BPFI": alpha})
        self.assertEqual(evaluation.status, "evaluated")
        indicator = evaluation.indicators["BPFI"]
        self.assertEqual(indicator["status"], "evaluated")
        self.assertTrue(indicator["significant"])
        self.assertAlmostEqual(indicator["detected_cyclic_frequency_hz"], alpha)
        self.assertIn("coherence_background_ratio", indicator)
        self.assertIn("sc_background_ratio", indicator)
        self.assertNotIn("envelope_peak_snr", indicator)

    def test_stationary_noise_is_evaluated_negative_control(self):
        representation = compute_sc_scoh(
            _modulated_noise(None, seed=22),
            FS,
            cyclic_frequencies_hz=[31.0, 39.0, 47.3, 55.0, 63.0, 71.0],
            segment_length=256,
        )
        evaluation = evaluate_cyclic_candidates(representation, {"BPFO": 47.3})
        self.assertEqual(evaluation.status, "evaluated")
        self.assertFalse(evaluation.indicators["BPFO"]["significant"])

    def test_coarse_resolution_and_shared_peak_are_not_evaluable(self):
        short = _modulated_noise(40.0, duration=0.25)
        coarse = compute_sc_scoh(short, FS, [32.0, 40.0, 48.0], segment_length=64, overlap_ratio=0.5)
        evaluation = evaluate_cyclic_candidates(coarse, {"BPFO": 40.0})
        self.assertEqual(evaluation.status, "indeterminate")
        self.assertEqual(
            evaluation.indicators["BPFO"]["reason"],
            "insufficient_cyclic_frequency_resolution",
        )

        signal = _modulated_noise(47.3)
        shared = compute_sc_scoh(signal, FS, [39.0, 47.3, 55.0, 63.0], segment_length=256)
        evaluation = evaluate_cyclic_candidates(shared, {"BPFO": 47.3, "BPFI": 47.3})
        self.assertEqual(evaluation.status, "indeterminate")
        self.assertEqual(evaluation.indicators["BPFO"]["reason"], "shared_cyclic_target")

    def test_above_bandwidth_and_missing_parameters_are_indeterminate(self):
        signal = _modulated_noise(47.3, duration=2.0)
        representation = compute_sc_scoh(signal, FS, [40.0, 47.3, 55.0], segment_length=256)
        evaluation = evaluate_cyclic_candidates(representation, {"BPFO": 900.0})
        self.assertEqual(evaluation.status, "indeterminate")
        self.assertEqual(evaluation.indicators["BPFO"]["reason"], "target_above_analysis_bandwidth")

        result = CyclostationaryPipeline().run(signal, FS)
        self.assertEqual(result.status, "indeterminate")
        self.assertEqual(result.reason, "missing_cyclic_candidates_or_geometry_and_rotation")
        self.assertIsNone(result.representation)

    def test_pipeline_uses_explicit_candidates_without_guessing_geometry(self):
        result = CyclostationaryPipeline().run(
            _modulated_noise(47.3, duration=3.0),
            FS,
            candidates={"known_fault": 47.3},
            segment_length=256,
        )
        self.assertEqual(result.status, "computed", result.reason)
        self.assertIsNotNone(result.representation)
        self.assertEqual(result.evaluation.indicators["known_fault"]["status"], "evaluated")
        self.assertNotIn("BPFO_est", result.evaluation.indicators)

    def test_normalized_metrics_and_significance_are_amplitude_scale_invariant(self):
        frequencies = [31.0, 39.0, 47.3, 55.0, 63.0, 71.0]
        signal = _modulated_noise(47.3, seed=731)
        reference = compute_sc_scoh(signal, FS, frequencies, segment_length=256)
        reference_indicator = evaluate_cyclic_candidates(reference, {"BPFO": 47.3}).indicators["BPFO"]

        for scale in (1e-6, 1e-8, 1e8):
            with self.subTest(scale=scale):
                scaled = compute_sc_scoh(signal * scale, FS, frequencies, segment_length=256)
                indicator = evaluate_cyclic_candidates(scaled, {"BPFO": 47.3}).indicators["BPFO"]
                np.testing.assert_allclose(
                    scaled.spectral_coherence,
                    reference.spectral_coherence,
                    rtol=1e-8,
                    atol=1e-12,
                )
                # SC 是二阶幅值量；独立数学缩放律为 SC(s*x)=s^2*SC(x)。
                np.testing.assert_allclose(
                    scaled.spectral_correlation,
                    reference.spectral_correlation * scale**2,
                    rtol=1e-8,
                    atol=0.0,
                )
                self.assertAlmostEqual(
                    indicator["coherence_background_ratio"],
                    reference_indicator["coherence_background_ratio"],
                    places=8,
                )
                self.assertAlmostEqual(
                    indicator["sc_background_ratio"],
                    reference_indicator["sc_background_ratio"],
                    places=8,
                )
                self.assertEqual(indicator["significant"], reference_indicator["significant"])

    def test_zero_energy_is_not_a_valid_negative_control(self):
        frequencies = [31.0, 39.0, 47.3, 55.0, 63.0, 71.0]
        representation = compute_sc_scoh(np.zeros(8192), FS, frequencies, segment_length=256)
        evaluation = evaluate_cyclic_candidates(representation, {"BPFO": 47.3})
        self.assertEqual(evaluation.status, "indeterminate")
        self.assertEqual(evaluation.indicators["BPFO"]["status"], "not_evaluable")
        self.assertEqual(evaluation.indicators["BPFO"]["reason"], "zero_energy")
        self.assertIsNone(evaluation.indicators["BPFO"]["significant"])

        result = CyclostationaryPipeline().run(
            np.zeros(8192), FS, candidates={"BPFO": 47.3}, segment_length=256
        )
        self.assertEqual(result.status, "indeterminate")
        self.assertEqual(result.reason, "zero_energy")
        self.assertIsNone(result.representation)

    def test_all_invalid_or_above_bandwidth_candidates_return_not_evaluable(self):
        signal = _modulated_noise(47.3, duration=2.0)
        for target in (np.nan, np.inf, 0.0, -47.3):
            with self.subTest(target=target):
                result = CyclostationaryPipeline().run(
                    signal, FS, candidates={"BPFO": target}, segment_length=256
                )
                self.assertEqual(result.status, "indeterminate")
                self.assertEqual(result.reason, "invalid_target_frequency")
                self.assertEqual(result.evaluation.indicators["BPFO"]["reason"], "invalid_target_frequency")
                self.assertIsNone(result.representation)

        result = CyclostationaryPipeline().run(
            signal, FS, candidates={"BPFO": 9000.0}, segment_length=256
        )
        self.assertEqual(result.status, "indeterminate")
        self.assertEqual(result.reason, "target_above_analysis_bandwidth")
        self.assertEqual(result.evaluation.indicators["BPFO"]["reason"], "target_above_analysis_bandwidth")
        self.assertIsNone(result.representation)

    def test_mixed_candidates_duplicates_empty_and_short_signal_keep_explicit_semantics(self):
        signal = _modulated_noise(47.3, duration=2.0)
        mixed = CyclostationaryPipeline().run(
            signal,
            FS,
            candidates={"BPFO": np.nan, "BPFI": 47.3, "BSF": 9000.0},
            segment_length=256,
        )
        self.assertEqual(mixed.status, "computed", mixed.reason)
        self.assertEqual(mixed.evaluation.indicators["BPFO"]["reason"], "invalid_target_frequency")
        self.assertEqual(mixed.evaluation.indicators["BPFI"]["status"], "evaluated")
        self.assertEqual(mixed.evaluation.indicators["BSF"]["reason"], "target_above_analysis_bandwidth")

        duplicated = CyclostationaryPipeline().run(
            signal, FS, candidates={"BPFO": 47.3, "BPFI": 47.3}, segment_length=256
        )
        self.assertEqual(duplicated.evaluation.status, "indeterminate")
        self.assertTrue(all(
            item["reason"] == "shared_cyclic_target"
            for item in duplicated.evaluation.indicators.values()
        ))

        empty = CyclostationaryPipeline().run(signal, FS, candidates={}, segment_length=256)
        self.assertEqual(empty.status, "indeterminate")
        self.assertEqual(empty.reason, "missing_cyclic_candidates_or_geometry_and_rotation")

        short = CyclostationaryPipeline().run(
            signal[:64], FS, candidates={"BPFO": 47.3}, segment_length=256
        )
        self.assertEqual(short.status, "indeterminate")
        self.assertEqual(short.reason, "insufficient_signal_length")
        self.assertIsNone(short.representation)


if __name__ == "__main__":
    unittest.main(verbosity=2)
