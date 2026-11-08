"""包络指标与评估的独立数学测试；频谱和期望值均手工构造。"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.algorithms.bearing.analysis import (
    SidebandObservation,
    SidebandTarget,
    analyze_envelope_spectrum,
    compute_sideband_metrics,
)
from app.algorithms.bearing.evaluation import evaluate_envelope, evaluate_sideband_evidence
from app.algorithms.core import Spectrum
from app.algorithms.mechanics import BearingGeometry
from app.services.diagnosis.ensemble import _bearing_confidence
from app.services.diagnosis.health_score_continuous import compute_continuous_deductions


GEOMETRY = BearingGeometry(9, 7.94, 38.52, 0.0)


def manual_spectrum(max_frequency=1000.0, resolution=1.0):
    frequency = np.arange(0.0, max_frequency + resolution, resolution, dtype=np.float64)
    return Spectrum(frequency_hz=frequency, amplitude=np.ones(len(frequency)))


def set_amplitude(spectrum, target, value):
    index = int(np.argmin(np.abs(spectrum.frequency_hz - target)))
    spectrum.amplitude[index] = value


def as_targets(observations):
    return tuple(
        SidebandTarget(item.order, item.side, item.theory_frequency_hz)
        for item in observations
    )


def evaluate(spectrum, rot=25.0):
    return evaluate_envelope(
        analyze_envelope_spectrum(spectrum, geometry=GEOMETRY, rot_frequency_hz=rot)
    )


class BearingEnvelopeAnalysisMathTest(unittest.TestCase):
    def test_fault_frequency_formula_has_independent_expectations(self):
        geometry = BearingGeometry(8, 5.0, 20.0, 0.0)
        ratio = 5.0 / 20.0
        expected = {
            "BPFO": 4 * 10.0 * (1.0 - ratio),
            "BPFI": 4 * 10.0 * (1.0 + ratio),
            "BSF": 20.0 / (2.0 * 5.0) * 10.0 * (1.0 - ratio**2),
            "FTF": 0.5 * 10.0 * (1.0 - ratio),
        }
        actual = geometry.fault_frequencies(10.0)
        for name, value in expected.items():
            self.assertAlmostEqual(actual[name], value)

    def test_coarse_resolution_is_not_evaluable(self):
        spectrum = Spectrum(
            frequency_hz=np.array([0.0, 100.0, 200.0]),
            amplitude=np.array([0.0, 100.0, 1.0]),
        )
        result = evaluate(spectrum)
        self.assertEqual(result.status, "indeterminate")
        for name in ("BPFO", "BPFI", "BSF"):
            item = result.indicators[name]
            self.assertEqual(item["status"], "not_evaluable")
            self.assertEqual(item["reason"], "shared_spectral_bin")
            self.assertIsNone(item["significant"])
            self.assertIsNone(item["snr"])

    def test_target_above_analysis_bandwidth_is_not_evaluable(self):
        spectrum = manual_spectrum(max_frequency=100.0)
        set_amplitude(spectrum, 89.0, 20.0)
        result = evaluate(spectrum)
        item = result.indicators["BPFI"]
        self.assertEqual(item["status"], "not_evaluable")
        self.assertEqual(item["reason"], "target_above_analysis_bandwidth")
        self.assertIsNone(item["significant"])
        self.assertEqual(result.indicators["BSF"]["status"], "evaluated")

    def test_bpfi_sideband_evidence_survives_dominance_filter(self):
        spectrum = manual_spectrum()
        frequencies = GEOMETRY.fault_frequencies(25.0)
        set_amplitude(spectrum, frequencies["BPFO"], 100.0)
        set_amplitude(spectrum, frequencies["BPFI"], 4.4)
        set_amplitude(spectrum, frequencies["BPFI"] - 25.0, 10.0)
        set_amplitude(spectrum, frequencies["BPFI"] + 25.0, 10.0)
        item = evaluate(spectrum).indicators["BPFI"]
        self.assertFalse(item["carrier_significant"])
        self.assertTrue(item["sideband_significant"])
        self.assertTrue(item["significant"])
        self.assertEqual(len(item["sideband_snrs"]), 2)

    def test_non_fault_low_frequency_peak_is_not_rotation_harmonic(self):
        spectrum = manual_spectrum()
        set_amplitude(spectrum, 60.0, 100.0)
        result = evaluate(spectrum)
        low = result.indicators["low_freq_ratio_stat"]
        self.assertGreater(low["value"], 0.9)
        self.assertLess(low["rotation_harmonic_energy_ratio"], 0.01)
        self.assertFalse(low["rotation_harmonic_dominant"])
        for name in ("BPFO", "BPFI", "BSF"):
            self.assertFalse(result.indicators[name]["significant"])
        # 物理峰不显著不得清除原始统计显著性。
        self.assertTrue(result.indicators["envelope_peak_snr_stat"]["significant"])

    def test_manual_threshold_boundary_and_non_snr_scores(self):
        spectrum = manual_spectrum()
        set_amplitude(spectrum, GEOMETRY.fault_frequencies(25.0)["BPFO"], 4.5)
        result = evaluate(spectrum)
        bpfo = result.indicators["BPFO"]
        self.assertFalse(bpfo["carrier_significant"])
        self.assertFalse(bpfo["significant"])
        self.assertEqual(bpfo["snr_kind"], "linear_peak_to_background_not_db")
        self.assertIn("score", result.indicators["envelope_kurtosis_stat"])
        self.assertNotIn("snr", result.indicators["envelope_kurtosis_stat"])

    def test_sideband_observable_denominator_and_missing_side(self):
        observations = (
            SidebandObservation(1, "upper", 100.0, 10.0),
            SidebandObservation(2, "upper", 125.0, 4.0),
            SidebandObservation(1, "lower", 50.0, 2.0),
        )
        result = evaluate_sideband_evidence(
            compute_sideband_metrics(observations, as_targets(observations))
        )
        self.assertEqual(result["sideband_observable_count"], 3)
        self.assertEqual(result["sideband_significant_count"], 2)
        self.assertAlmostEqual(result["sideband_density"], 2.0 / 3.0)

        upper_only = compute_sideband_metrics(observations[:1], as_targets(observations[:1]))
        self.assertIsNone(upper_only.asymmetry)
        self.assertIsNone(evaluate_sideband_evidence(upper_only)["high_asymmetry"])
        empty = evaluate_sideband_evidence(compute_sideband_metrics((), ()))
        self.assertIsNone(empty["sideband_density"])

    def test_sideband_asymmetry_formula(self):
        evidence = compute_sideband_metrics((
            SidebandObservation(1, "upper", 100.0, 10.0),
            SidebandObservation(1, "lower", 50.0, 4.0),
        ), (
            SidebandTarget(1, "upper", 100.0),
            SidebandTarget(1, "lower", 50.0),
        ))
        self.assertAlmostEqual(evidence.asymmetry, 6.0 / 14.0)

    def test_shifted_local_peak_is_selected_within_tolerance(self):
        spectrum = manual_spectrum(max_frequency=200.0)
        set_amplitude(spectrum, 90.0, 2.0)
        set_amplitude(spectrum, 91.0, 100.0)
        item = evaluate(spectrum).indicators["BPFO"]
        self.assertEqual(item["detected_hz"], 91.0)
        self.assertTrue(item["significant"])

    def test_strict_background_sideband_uses_real_observable_set(self):
        spectrum = manual_spectrum(max_frequency=500.0)
        spectrum.amplitude[:] = np.linspace(1.0, 501.0, 501)
        bpfi = GEOMETRY.fault_frequencies(25.0)["BPFI"]
        set_amplitude(spectrum, bpfi + 25.0, 1000.0)
        analysis = analyze_envelope_spectrum(
            spectrum,
            geometry=GEOMETRY,
            rot_frequency_hz=25.0,
        )
        evidence = analysis.features.sidebands["BPFI"]
        self.assertEqual(evidence.observable_count, 10)
        self.assertEqual(len(evidence.observations), 1)
        result = evaluate_envelope(analysis)
        self.assertAlmostEqual(result.indicators["BPFI"]["sideband_density"], 0.1)
        # 基波在单调背景中没有局部峰，是可评估的有效阴性。
        self.assertTrue(result.indicators["BPFI"]["evaluable"])
        self.assertFalse(result.indicators["BPFI"]["significant"])

    def test_suffixed_low_frequency_key_controls_health_and_ensemble(self):
        spectrum = manual_spectrum(max_frequency=100.0)
        set_amplitude(spectrum, 25.0, 16.0)
        result = evaluate(spectrum)
        low = result.indicators["low_freq_ratio_stat"]
        self.assertTrue(low["rotation_harmonic_dominant"])
        deductions = compute_continuous_deductions(
            {"kurtosis": 8.0, "crest_factor": 12.0},
            None,
            {"evaluation": {"indicators": result.indicators}},
            {"fault_indicators": {}},
        )
        self.assertNotIn(
            "bearing_statistical_abnormal",
            {name for name, _ in deductions},
        )
        self.assertNotIn(
            "bearing_statistical_hint",
            {name for name, _ in deductions},
        )
        # 精确覆盖 stat_hits=1 的降权分支，低频键来自真实提取结果。
        vote_indicators = {
            "low_freq_ratio_stat": low,
            "moderate_kurtosis_stat": {
                **result.indicators["moderate_kurtosis_stat"],
                "significant": True,
                "score": 16.0,
            },
        }
        vote = _bearing_confidence(
            {"evaluation": {"indicators": vote_indicators}},
            {"kurtosis": 8.0, "crest_factor": 12.0},
        )
        self.assertEqual(vote["confidence"], 0.28)

    def test_power_proxy_name_unit_and_nonuniform_validation(self):
        spectrum = Spectrum(
            frequency_hz=np.array([0.0, 100.0, 200.0]),
            amplitude=np.array([0.0, 100.0, 1.0]),
        )
        analysis = analyze_envelope_spectrum(spectrum)
        self.assertEqual(analysis.features.spectral_power_proxy, 10001.0)
        self.assertEqual(analysis.features.spectral_power_unit, "input_signal^2")
        self.assertNotIn("total_env_energy", analysis.features.as_dict())
        with self.assertRaises(ValueError):
            Spectrum(frequency_hz=np.array([0.0, 1.0, 3.0]), amplitude=np.ones(3))
        with self.assertRaises(ValueError):
            Spectrum(frequency_hz=np.array([0.0, 1.0]), amplitude=np.array([0.0, np.nan]))

    def test_geometry_validation(self):
        with self.assertRaises(ValueError):
            BearingGeometry(9.5, 7.94, 38.52)
        with self.assertRaises(ValueError):
            BearingGeometry(9, 40.0, 38.52)
        with self.assertRaises(ValueError):
            BearingGeometry(9, 7.94, 38.52, 90.0)
        with self.assertRaises(ValueError):
            BearingGeometry(9, np.inf, 38.52)


if __name__ == "__main__":
    unittest.main()
