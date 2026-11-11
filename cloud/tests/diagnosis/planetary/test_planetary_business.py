"""真实业务调度与不可评估语义；物理算法向量在 test_planetary_pipeline。"""
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from app.algorithms.order import OrderAnalysis, ScalarSpeed, SpeedTrajectory
from app.algorithms.pipelines.gear.planetary import PlanetaryGearPipeline
from app.services.analyzer import analyze_device
from app.services.diagnosis import DiagnosisEngine, GearMethod
from app.services.diagnosis.ensemble import _gear_confidence, run_research_ensemble
from app.services.diagnosis.gear.planetary import gear_config_for_channel, planetary_geometry_from_config

GEOMETRY = {"sun": 28, "ring": 100, "planet": 36, "planet_count": 4, "reference_axis": "sun", "fixed_member": "ring"}
FS = 4096
TIME = np.arange(5 * FS) / FS
SIGNAL = (1 + .2 * np.cos(2 * np.pi * 4.375 * TIME)) * np.sin(2 * np.pi * 437.5 * TIME)


class PlanetaryBusinessTests(unittest.TestCase):
    def test_engine_dispatches_object_pipeline_without_old_flat_protocol(self):
        result = DiagnosisEngine(gear_teeth=GEOMETRY, gear_method=GearMethod.ADVANCED).analyze_gear(SIGNAL, FS, 20)
        self.assertEqual(result["method"], "planetary_gear")
        self.assertEqual(result["mechanical_model"]["reference_axis"], "sun")
        self.assertAlmostEqual(result["sideband_analysis"]["spacing_order"], 7 / 32)
        self.assertIn("fullband", result["planetary_methods"])
        self.assertNotIn("planetary_narrowband_demod", result)
        self.assertNotIn("sun_fault_order", result)
        self.assertNotIn("ser", result)
        self.assertEqual(result["evaluation_status"], "not_evaluable")
        self.assertEqual(result["diagnosis_conclusion"], "unknown")

    def test_reference_axis_and_planet_teeth_are_required_not_guessed(self):
        for missing in ("reference_axis", "fixed_member", "planet", "sun"):
            values = {key: value for key, value in GEOMETRY.items() if key != missing}
            values["input"] = 28
            result = DiagnosisEngine(gear_teeth=values).analyze_gear(SIGNAL, FS, 20)
            self.assertEqual(result["analysis_status"], "not_evaluable", missing)
            self.assertEqual(result["diagnosis_conclusion"], "unknown")

    def test_varying_order_result_does_not_become_constant_speed_summary(self):
        varying = OrderAnalysis.failed("varying_speed", SpeedTrajectory(np.array([0., 5.]), np.array([20., 40.]), "ramp"), "explicit_ramp")
        result = DiagnosisEngine(gear_teeth=GEOMETRY).analyze_gear(SIGNAL, FS, _cached_order=varying)
        self.assertEqual(result["reason"], "planetary_demodulation_requires_explicit_constant_speed")

    def test_channel_geometry_never_comes_from_first_other_channel(self):
        values = {"1": {"input": 18}, "2": GEOMETRY}
        self.assertEqual(gear_config_for_channel(values, 2), GEOMETRY)
        self.assertEqual(gear_config_for_channel(values, 3), {})

    def test_existing_analysis_can_be_reassessed_without_analysis_call(self):
        pipeline = PlanetaryGearPipeline(planetary_geometry_from_config(GEOMETRY))
        analysis = pipeline.analyze(SIGNAL, FS, ScalarSpeed(20., "known"), methods=(), include_tsa=False)
        with patch.object(pipeline, "analyze", side_effect=AssertionError("must not recompute")):
            self.assertEqual(pipeline.evaluate(analysis).conclusion, "unknown")

    def test_same_record_has_one_vote_and_unknown_never_becomes_healthy(self):
        with patch("app.services.diagnosis.ensemble._profile_config", return_value={"denoise": ["none", "wavelet"], "bearing": [], "gear": [GearMethod.STANDARD, GearMethod.ADVANCED]}):
            result = run_research_ensemble(SIGNAL, FS, gear_teeth=GEOMETRY, rot_freq=20)
        self.assertEqual(len(result["gear_results"]), 1)
        self.assertEqual(len(result["ensemble"]["gear_votes"]), 1)
        self.assertFalse(next(iter(result["ensemble"]["gear_votes"].values()))["evaluable"])
        self.assertEqual(result["status"], "indeterminate")
        self.assertIsNone(result["health_score"])
        self.assertIsNone(result["fault_likelihood"])
        self.assertEqual(result["fault_label"], "unknown")

    def test_analyzer_keeps_unknown_channel_without_fallback_or_int_none(self):
        device = SimpleNamespace(gear_teeth=GEOMETRY, bearing_params={})
        with patch("app.services.analyzer.nn_predict", return_value=None), patch("app.services.analyzer._rule_based_analyze", side_effect=AssertionError("must not fall back")):
            result = analyze_device({"c1": SIGNAL}, FS, device, rot_freq=20, denoise_method="none")
        self.assertEqual(result["status"], "indeterminate")
        self.assertIsNone(result["health_score"])
        self.assertEqual(result["fault_probabilities"], {})
        self.assertIn("c1", result["order_analysis"]["channels"])

    def test_raw_kurtosis_and_legacy_field_cannot_trigger_planetary_vote(self):
        vote = _gear_confidence({"is_planetary": True, "evaluation": {"status": "not_evaluable", "conclusion": "unknown"}, "planetary_tsa_demod": {"residual_kurtosis": 1000}, "fault_indicators": {}}, True, {"kurtosis": 1000, "crest_factor": 1000})
        self.assertFalse(vote["evaluable"])
        self.assertEqual(vote["confidence"], 0)

    def test_all_and_comprehensive_do_not_get_healthy_from_unconfigured_bearing(self):
        engine = DiagnosisEngine(gear_teeth=GEOMETRY, gear_method=GearMethod.ADVANCED)
        for result in (engine.analyze_comprehensive(SIGNAL, FS, 20), engine.analyze_all_methods(SIGNAL, FS, 20)):
            self.assertEqual(result["status"], "indeterminate")
            self.assertIsNone(result["health_score"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
