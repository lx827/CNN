"""高级轴承的真实业务入口：前提、目标选择、专属评估及不可评估投票。"""
import os
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.algorithms.mechanics import BearingGeometry
from app.algorithms.pipelines.bearing import BearingEnvelopePipeline
from app.services.diagnosis.engine import DiagnosisEngine
from app.services.diagnosis.ensemble import _bearing_confidence, _fault_label, run_research_ensemble
from app.services.diagnosis.health_score_continuous import compute_continuous_deductions


FS = 2048
PARAMS = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}


def impulses():
    x = np.zeros(2048)
    x[50::32] = 1
    carrier = np.exp(-np.arange(60) / 12) * np.sin(2 * np.pi * 600 * np.arange(60) / FS)
    return np.convolve(x, carrier)[:len(x)] + 0.01 * np.random.default_rng(9).normal(size=len(x))


class AdvancedBearingBusinessTests(unittest.TestCase):
    def test_cpw_requires_explicit_stable_comb_even_with_gear_parameters(self):
        for options in ({}, {"comb_frequencies_hz": [25]}, {"comb_is_stable": True}):
            result = DiagnosisEngine(bearing_method="cpw", gear_teeth={"input": 18},
                                     bearing_options=options).analyze_bearing(impulses(), FS, 25)
            self.assertEqual(result["evaluation"]["status"], "indeterminate")
            self.assertIsNone(result["spectrum"])
        stable = DiagnosisEngine(bearing_method="cpw", bearing_options={
            "comb_frequencies_hz": [25], "comb_is_stable": True,
        }).analyze_bearing(impulses(), FS, 25)
        self.assertEqual(stable["comb_frequencies_hz"], (25.0,))
        self.assertEqual(stable["comb_model"], "constant_frequency")

    def test_mckd_explicit_target_and_med_fallback_use_real_method_labels(self):
        signal = impulses()
        fallback = DiagnosisEngine(bearing_method="mckd").analyze_bearing(signal, FS, 25)
        self.assertEqual(fallback["method"], "med")
        self.assertEqual(fallback["requested_method"], "mckd")
        self.assertEqual(fallback["objective"], "normalized_kurtosis")
        for fault in ("BPFO", "BPFI"):
            result = DiagnosisEngine(bearing_method="mckd", bearing_params=PARAMS,
                                     bearing_options={"target_fault": fault}).analyze_bearing(signal, FS, 25)
            expected = BearingGeometry(9, 7.94, 38.52).fault_frequencies(25)[fault]
            self.assertEqual(result["method"], "mckd")
            self.assertEqual(result["target_fault"], fault)
            self.assertEqual(result["period_samples"], round(FS / expected))
        missing = DiagnosisEngine(bearing_method="mckd", bearing_options={"target_fault": "BPFI"})
        result = missing.analyze_bearing(signal, FS, 25)
        self.assertEqual(result["reason"], "missing_target_frequency_or_period")
        outside = DiagnosisEngine(bearing_method="mckd", bearing_options={
            "target_fault": "BPFI", "target_frequency_hz": FS,
        }).analyze_bearing(signal, FS, 25)
        self.assertEqual(outside["reason"], "target_above_analysis_bandwidth")

    def test_sc_scoh_keeps_dedicated_metrics_and_rejects_missing_candidates(self):
        t = np.arange(4096) / FS
        signal = (1 + 0.8 * np.cos(2 * np.pi * 47.3 * t)) * np.sin(2 * np.pi * 700 * t)
        engine = DiagnosisEngine(bearing_method="sc_scoh", bearing_options={"cyclic_candidates_hz": {"known": 47.3}})
        with patch.object(BearingEnvelopePipeline, "evaluate", side_effect=AssertionError("SC must not run envelope evaluation")):
            result = engine.analyze_bearing(signal, FS, 25)
        self.assertEqual(result["evaluation_kind"], "sc_scoh")
        indicator = result["evaluation"]["indicators"]["known"]
        self.assertEqual(indicator["metric_kind"], "complex_sc_and_spectral_coherence_not_envelope_snr")
        self.assertNotIn("snr", indicator)
        self.assertNotIn("sc_scoh_indicators", result)
        self.assertGreaterEqual(min(result["cyclic_spectrum"]["carrier_frequency_hz"]), 0)
        missing = DiagnosisEngine(bearing_method="sc_scoh").analyze_bearing(signal, FS, 25)
        self.assertEqual(missing["evaluation"]["status"], "indeterminate")

    def test_indeterminate_methods_do_not_vote_or_reduce_valid_vote_fraction(self):
        features = {"rms": 1, "kurtosis": 3, "crest_factor": 3}
        unavailable = {"analysis_status": "indeterminate", "evaluation": {"status": "indeterminate", "indicators": {}}}
        self.assertFalse(_bearing_confidence(unavailable, features)["evaluable"])
        config = {"denoise": ["none"], "bearing": [], "gear": []}
        # 真实集成调度仅选本切片的两条无前提路径，避免用模态分解做替身。
        from app.services.diagnosis.engine import BearingMethod
        config["bearing"] = [BearingMethod.CPW, BearingMethod.SC_SCOH]
        with patch("app.services.diagnosis.ensemble._profile_config", return_value=config):
            result = run_research_ensemble(impulses(), FS, rot_freq=25, profile="runtime")
        self.assertEqual(result["status"], "indeterminate")
        self.assertIsNone(result["health_score"])
        self.assertTrue(all(not vote["evaluable"] for vote in result["ensemble"]["bearing_votes"].values()))
        self.assertEqual(result["ensemble"]["ds_fusion"].get("method_count", 0), 0)

    def test_cyclic_fault_label_uses_cyclic_strength_not_absent_envelope_snr(self):
        result = {"evaluation_kind": "sc_scoh", "evaluation": {"indicators": {
            "BPFO": {"significant": True, "coherence_background_ratio": 4},
            "BPFI": {"significant": True, "coherence_background_ratio": 9},
        }}}
        self.assertEqual(_fault_label(result, {}, .65, 0), "bearing_bpfi")

    def test_ensemble_runs_med_once_when_mckd_has_no_selected_target(self):
        from app.services.diagnosis.engine import BearingMethod
        config = {"denoise": ["none"], "bearing": [BearingMethod.MED, BearingMethod.MCKD], "gear": []}
        with patch("app.services.diagnosis.ensemble._profile_config", return_value=config):
            result = run_research_ensemble(impulses(), FS, rot_freq=25)
        self.assertEqual(list(result["bearing_results"]), ["none:med"])
        self.assertEqual(list(result["ensemble"]["bearing_votes"]), ["none:med"])

    def test_sc_health_deduction_requires_dedicated_significance(self):
        for significant in (False, None):
            result = {"method": "sc_scoh", "evaluation_kind": "sc_scoh", "evaluation": {
                "indicators": {"BPFO": {"evaluable": significant is not None, "scoh_peak": 0.99, "significant": significant}},
            }}
            deductions = compute_continuous_deductions({"kurtosis": 3, "crest_factor": 3}, None, result, {})
            self.assertNotIn("bearing_sc_scoh_evidence", {name for name, _ in deductions})

    def test_zero_energy_and_teo_units_are_explicit(self):
        for method in ("filter_bank_sk", "spectral_kurtosis", "cpw", "med", "mckd", "teager", "sc_scoh"):
            result = DiagnosisEngine(bearing_method=method).analyze_bearing(np.zeros(512), FS, 25)
            self.assertEqual(result["evaluation"]["status"], "indeterminate")
        teo = DiagnosisEngine(bearing_method="teager").analyze_bearing(impulses(), FS, 25)
        self.assertEqual(teo["spectrum"]["amplitude_unit"], "input_signal^2")
        self.assertEqual(teo["features"]["spectral_power_unit"], "(input_signal^2)^2")
        self.assertIn("negative_value_policy", teo)


if __name__ == "__main__":
    unittest.main()
