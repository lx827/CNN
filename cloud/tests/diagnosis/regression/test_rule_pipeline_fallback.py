"""规则回退业务证据：消费对象 Pipeline，参数、工况、数组与评分保持同一语义。"""
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.algorithms.order import ConstantSpeedOrderPipeline, OrderParameters, ScalarSpeed
from app.algorithms.pipelines.bearing import BearingEnvelopePipeline
from app.algorithms.pipelines.gear.fixed_axis import FixedAxisGearPipeline
from app.services.diagnosis import rule_based
from app.services.diagnosis.engine import bearing_geometry_from_config
from app.services.diagnosis.health_score import _compute_health_score
from app.services.diagnosis.signal_utils import prepare_signal

FS = 8192
PARAMS = {"n": 9, "d": 7.94, "D": 39.04, "alpha": None}


def carrier_signal():
    time = np.arange(FS * 3) / FS
    bpfo = bearing_geometry_from_config(PARAMS).fault_frequencies(25.0)["BPFO"]
    return (
        np.sin(2 * np.pi * 25.0 * time)
        + (1.0 + 0.65 * np.cos(2 * np.pi * bpfo * time)) * np.sin(2 * np.pi * 2500 * time)
    )


class RulePipelineFallbackTests(unittest.TestCase):
    def test_bearing_consumes_actual_channel_geometry_and_central_score(self):
        signal = carrier_signal()
        device = SimpleNamespace(
            bearing_params={"1": {"n": None}, "2": PARAMS}, gear_teeth=None,
        )
        order = ConstantSpeedOrderPipeline().run(signal, FS, ScalarSpeed(25.0, "test_truth"))
        with patch.object(rule_based.AutomaticOrderPipeline, "run", return_value=order), \
                patch.object(rule_based.BearingEnvelopePipeline, "run", autospec=True,
                             side_effect=BearingEnvelopePipeline.run) as bearing_run:
            result = rule_based._rule_based_analyze({"ch2": signal}, FS, device)
        self.assertIsInstance(bearing_run.call_args.args[1], np.ndarray)
        report = result["order_analysis"]
        self.assertEqual(report["channel"], 2)
        expected = BearingEnvelopePipeline(bearing_geometry_from_config(PARAMS)).run(
            prepare_signal(signal, detrend=True), FS, 25.0,
        )
        self.assertEqual(report["bearing"]["evaluation"]["indicators"], expected.evaluation.indicators)
        self.assertAlmostEqual(
            report["bearing"]["features"]["BPFO_env_ratio"],
            expected.analysis.envelope_analysis.features.energy_ratios["BPFO"],
        )
        health, status, _ = _compute_health_score(None, report["time_features"], report["bearing"], {})
        self.assertEqual((result["health_score"], result["status"]), (health, status))
        self.assertAlmostEqual(sum(result["imf_energy"].values()), 100.0, places=1)
        self.assertEqual(result["imf_energy_kind"], "five_equal_frequency_bands_power_percent")
        json.dumps(result, allow_nan=False)

    def test_gear_uses_existing_order_and_covers_mesh_above_order_50(self):
        time = np.arange(FS * 3) / FS
        signal = np.sin(2 * np.pi * 25 * time) + np.sin(2 * np.pi * 1500 * time)
        device = SimpleNamespace(gear_teeth={"input": 60}, bearing_params=None)
        order = ConstantSpeedOrderPipeline(OrderParameters(max_order=70)).run(
            signal, FS, ScalarSpeed(25.0, "test_truth"),
        )
        with patch.object(rule_based.AutomaticOrderPipeline, "run", return_value=order), \
                patch.object(rule_based.FixedAxisGearPipeline, "run", autospec=True,
                             side_effect=FixedAxisGearPipeline.run) as gear_run:
            result = rule_based._rule_based_analyze({"ch1": signal}, FS, device)
        self.assertIs(gear_run.call_args.kwargs["order_analysis"], order)
        self.assertEqual(result["order_analysis"]["gear"]["analysis_status"], "evaluated")
        self.assertTrue(result["order_analysis"]["gear"]["fault_indicators"]["ser"]["evaluable"])

    def test_unknown_geometry_does_not_invent_bearing_fault_labels(self):
        signal = carrier_signal()
        result = rule_based._rule_based_analyze({"ch1": signal}, FS)
        self.assertNotEqual(result["status"], "indeterminate")
        self.assertNotIn("轴承外圈故障", result["fault_probabilities"])
        self.assertNotIn("轴承内圈故障", result["fault_probabilities"])
        self.assertNotIn("滚动体故障", result["fault_probabilities"])

    def test_invalid_missing_and_unsupported_inputs_are_not_healthy(self):
        cases = [({}, None), ({"ch1": []}, None), ({"ch1": np.zeros(1024)}, None),
                 ({"ch1": np.ones(1024)}, None), ({"ch1": [np.nan] * 1024}, None),
                 ({"ch1": carrier_signal()}, SimpleNamespace(
                     gear_teeth={"input": None, "output": None}, bearing_params=None)),
                 ({"ch1": carrier_signal()}, SimpleNamespace(
                     gear_teeth=None, bearing_params={"n": 9, "d": None, "D": 39.04})),
                 ({"ch1": carrier_signal()}, SimpleNamespace(
                     gear_teeth={"sun": 28, "ring": 100, "planet_count": 3}, bearing_params=None))]
        for channels, device in cases:
            with self.subTest(device=device, channels=list(channels)):
                result = rule_based._rule_based_analyze(channels, FS, device)
                self.assertEqual(result["status"], "indeterminate")
                self.assertIsNone(result["health_score"])
                self.assertEqual(result["fault_probabilities"], {})

    def test_fast_speed_summary_is_not_sent_to_bearing_pipeline(self):
        from tests.diagnosis.algorithms.test_order_integration import _fast_signal
        signal = _fast_signal()
        with patch.object(rule_based.BearingEnvelopePipeline, "run") as bearing_run:
            result = rule_based._rule_based_analyze({"ch1": signal}, FS)
        bearing_run.assert_not_called()
        self.assertEqual(result["status"], "indeterminate")
        self.assertIsNone(result["health_score"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
