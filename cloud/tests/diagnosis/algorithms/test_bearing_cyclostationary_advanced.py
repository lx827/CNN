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


if __name__ == "__main__":
    unittest.main(verbosity=2)
