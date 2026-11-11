"""标准轴承包络 Pipeline 的算法契约测试，全部使用合成信号。"""
import os
import sys
import unittest
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.algorithms.bearing.envelope import EnvelopeParameters, compute_envelope
from app.algorithms.core import Spectrum
from app.algorithms.mechanics import BearingGeometry
from app.algorithms.pipelines.bearing import BearingEnvelopePipeline
from app.services.diagnosis import BearingMethod, DiagnosisEngine
from app.services.diagnosis.engine import bearing_geometry_from_config
from app.services.diagnosis.ensemble import run_research_ensemble
from app.services.diagnosis.assessment import reassess_diagnosis, AssessmentPolicy


FS = 8192.0


def modulated_carrier(fault_frequency_hz: float, modulation_depth: float = 0.5) -> np.ndarray:
    time = np.arange(int(FS * 2.0)) / FS
    carrier = np.sin(2.0 * np.pi * 2000.0 * time)
    modulation = 1.0 + modulation_depth * np.cos(2.0 * np.pi * fault_frequency_hz * time)
    rng = np.random.default_rng(20261108)
    return modulation * carrier + rng.normal(0.0, 0.001, len(time))


class BearingEnvelopePipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.parameters = EnvelopeParameters(
            band_center_hz=2000.0,
            band_width_hz=800.0,
            envelope_low_pass_hz=500.0,
        )

    def test_modulation_peak_and_single_sided_amplitude(self) -> None:
        result = compute_envelope(modulated_carrier(90.0), FS, self.parameters)
        peak_index = int(np.argmax(result.spectrum.amplitude))
        self.assertAlmostEqual(result.spectrum.frequency_hz[peak_index], 90.0, delta=1.0)
        # 调制深度 0.5，去除包络直流后，90 Hz 余弦峰值应接近 0.5。
        self.assertAlmostEqual(result.spectrum.amplitude[peak_index], 0.5, delta=0.08)
        self.assertEqual(result.spectrum.scaling, "single_sided_amplitude")
        self.assertEqual(result.spectrum.amplitude_unit, "input_signal")

    def test_actual_band_and_default_band(self) -> None:
        result = compute_envelope(modulated_carrier(90.0), FS, self.parameters)
        self.assertEqual((result.band.low_hz, result.band.high_hz), (1600.0, 2400.0))
        self.assertEqual(result.band.center_hz, 2000.0)
        self.assertEqual(result.band.width_hz, 800.0)

        default_result = compute_envelope(modulated_carrier(90.0), FS)
        self.assertAlmostEqual(default_result.band.low_hz, FS / 8.0)
        self.assertAlmostEqual(default_result.band.high_hz, FS * 3.0 / 8.0)

    def test_physical_fault_evaluation_and_direct_reevaluation(self) -> None:
        geometry = BearingGeometry(9, 7.94, 38.52, 0.0)
        bpfo = geometry.fault_frequencies(25.0)["BPFO"]
        pipeline = BearingEnvelopePipeline(geometry=geometry, parameters=self.parameters)
        analysis = pipeline.analyze(modulated_carrier(bpfo), FS, rot_frequency_hz=25.0)
        evaluation = pipeline.evaluate(analysis)
        self.assertEqual(evaluation.status, "evaluated")
        self.assertIn("BPFO", evaluation.indicators)
        self.assertGreater(evaluation.indicators["BPFO"]["snr"], 15.0)
        self.assertTrue(evaluation.indicators["BPFO"]["significant"])

        # 重评只消费已有指标，不允许再次进入滤波/FFT 所在 analyze。
        with mock.patch.object(pipeline, "analyze", side_effect=AssertionError("不应重新计算")):
            repeated = pipeline.evaluate(analysis)
        self.assertEqual(repeated.indicators, evaluation.indicators)

    def test_no_geometry_only_returns_statistical_evidence(self) -> None:
        pipeline = BearingEnvelopePipeline(parameters=self.parameters)
        diagnosis = pipeline.run(modulated_carrier(90.0), FS, rot_frequency_hz=25.0)
        self.assertEqual(diagnosis.evaluation.status, "evaluated")
        self.assertNotIn("BPFO", diagnosis.evaluation.indicators)
        self.assertIn("envelope_peak_snr", diagnosis.evaluation.indicators)
        self.assertIn("low_freq_ratio", diagnosis.evaluation.indicators)

    def test_unknown_speed_is_indeterminate_not_normal(self) -> None:
        pipeline = BearingEnvelopePipeline(parameters=self.parameters)
        diagnosis = pipeline.run(modulated_carrier(90.0), FS)
        self.assertEqual(diagnosis.evaluation.status, "indeterminate")
        self.assertEqual(diagnosis.evaluation.indicators, {})
        self.assertEqual(diagnosis.analysis.representation.spectrum.scaling, "single_sided_amplitude")

    def test_invalid_inputs_fail_explicitly(self) -> None:
        with self.assertRaises(ValueError):
            compute_envelope(np.zeros(63), FS)
        with self.assertRaises(ValueError):
            compute_envelope(np.zeros(128), 0.0)
        with self.assertRaises(ValueError):
            BearingEnvelopePipeline(parameters=self.parameters).run(
                np.zeros(128), FS, rot_frequency_hz=0.0
            )
        with self.assertRaises(ValueError):
            BearingEnvelopePipeline(parameters=self.parameters).run(
                np.zeros(128), FS, rot_frequency_std_hz=np.nan
            )
        with self.assertRaises(ValueError):
            BearingEnvelopePipeline(parameters=self.parameters).run(
                np.zeros(128), FS, rot_frequency_std_hz=np.inf
            )

    def test_dataclass_keeps_array_references(self) -> None:
        frequency = np.array([0.0, 1.0, 2.0])
        amplitude = np.array([0.0, 1.0, 0.0])
        spectrum = Spectrum(frequency_hz=frequency, amplitude=amplitude)
        self.assertIs(spectrum.frequency_hz, frequency)
        self.assertIs(spectrum.amplitude, amplitude)
    def test_engine_and_ensemble_use_new_result_contract(self) -> None:
        geometry = BearingGeometry(9, 7.94, 38.52, 0.0)
        bpfo = geometry.fault_frequencies(25.0)["BPFO"]
        params = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}
        engine = DiagnosisEngine(
            bearing_method=BearingMethod.ENVELOPE,
            bearing_params=params,
        )
        result = engine.analyze_bearing(
            modulated_carrier(bpfo), FS, rot_freq=25.0, max_freq=300.0
        )
        self.assertLessEqual(max(result["spectrum"]["frequency_hz"]), 300.0)
        self.assertIn("evaluation", result)
        self.assertNotIn("envelope_freq", result)
        self.assertNotIn("envelope_amp", result)
        self.assertNotIn("fault_indicators", result)

        ensemble = run_research_ensemble(
            modulated_carrier(bpfo),
            FS,
            bearing_params=params,
            rot_freq=25.0,
            profile="runtime",
            max_seconds=2.0,
        )
        self.assertIn("evaluation", ensemble["bearing"])
        self.assertIn("indicators", ensemble["bearing"]["evaluation"])

    def test_display_limit_does_not_change_diagnosis(self) -> None:
        geometry = BearingGeometry(9, 7.94, 38.52, 0.0)
        bpfo = geometry.fault_frequencies(25.0)["BPFO"]
        params = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}
        engine = DiagnosisEngine(
            bearing_method=BearingMethod.ENVELOPE,
            bearing_params=params,
        )
        signal = modulated_carrier(bpfo)
        narrow = engine.analyze_bearing(signal, FS, rot_freq=25.0, max_freq=100.0)
        wide = engine.analyze_bearing(signal, FS, rot_freq=25.0, max_freq=500.0)
        self.assertLessEqual(max(narrow["spectrum"]["frequency_hz"]), 100.0)
        self.assertLessEqual(max(wide["spectrum"]["frequency_hz"]), 500.0)
        self.assertEqual(narrow["evaluation"], wide["evaluation"])
        self.assertEqual(narrow["features"], wide["features"])

    def test_malformed_geometry_config_is_not_missing_config(self) -> None:
        self.assertIsNone(bearing_geometry_from_config(None))
        self.assertIsNone(bearing_geometry_from_config({}))
        for malformed in (
            {"n": 9, "d": 7.94},
            {"n": 9.5, "d": 7.94, "D": 38.52},
            {"n": 9, "d": 40.0, "D": 38.52},
            {"n": 9, "d": np.nan, "D": 38.52},
        ):
            with self.assertRaises(ValueError):
                bearing_geometry_from_config(malformed)

    def test_sc_scoh_evidence_uses_method_specific_channel(self) -> None:
        engine = DiagnosisEngine(bearing_method=BearingMethod.SC_SCOH, bearing_params={"n": 9, "d": 7.94, "D": 38.52})
        sc_result = {
            "method": "sc_scoh", "evaluation_kind": "sc_scoh", "analysis_status": "computed",
            "evaluation": {"status": "evaluated", "indicators": {
                "BPFO": {"scoh_peak": 0.8, "significant": True, "evaluable": True},
            }},
        }
        with mock.patch(
            "app.services.diagnosis.engine.analyze_advanced_bearing",
            return_value=sc_result,
        ):
            result = engine.analyze_bearing(
                np.sin(np.arange(128)), FS, rot_freq=25.0, preprocess=False
            )

        self.assertNotIn("fault_indicators", result)
        self.assertEqual(result["evaluation"]["indicators"], sc_result["evaluation"]["indicators"])
        self.assertNotIn("sc_scoh_indicators", result)
        reevaluated = reassess_diagnosis(result, AssessmentPolicy(weights={"scoh_evidence": 2., "bpfo": 100.}))
        self.assertEqual(reevaluated.health_score, 76.)
        self.assertEqual(reevaluated.deductions[0].code, "bearing_cyclic")


if __name__ == "__main__":
    unittest.main()
