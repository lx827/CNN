"""行星排手算运动学、物理合成、反例与评估边界；不依赖真实数据。"""
from dataclasses import replace
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.algorithms.gear.fixed_axis.metrics import analyze_fixed_axis_sidebands
from app.algorithms.gear.planetary.analysis import analyze_planetary_sidebands, modulation_peaks
from app.algorithms.gear.planetary.evaluation import collect_planetary_metrics
from app.algorithms.gear.planetary.types import PlanetaryBaseline, PlanetaryMomentHistory, PlanetaryParameters, PlanetaryThreshold
from app.algorithms.mechanics.planetary import PlanetaryGearGeometry
from app.algorithms.order import OrderAnalysis, OrderSpectrum, ScalarSpeed, SpeedTrajectory, compute_order_spectrum
from app.algorithms.pipelines.gear.planetary import PlanetaryGearPipeline


WT = PlanetaryGearGeometry(28, 100, 36, 4, "sun")
FS = 8192
SPEED = ScalarSpeed(20.0, "physical_truth")


def signal(amplitude_modulation=.2, residual=False):
    time = np.arange(5 * FS) / FS
    fc = 20 * 7 / 32
    mesh = 20 * 175 / 8
    values = (1 + amplitude_modulation * np.cos(2 * np.pi * fc * time)) * np.sin(2 * np.pi * mesh * time)
    if residual:
        values += .3 * np.sin(2 * np.pi * 30.5 * fc * time)
    return values


def spectrum_with_sidebands(scale=1.0):
    delta = 1 / 640
    axis = np.arange(int(30 / delta) + 1) * delta
    values = np.zeros_like(axis)
    values[int(round(WT.mesh_order / delta))] = scale
    for n in range(1, 7):
        for sign in (-1, 1):
            values[int(round((WT.mesh_order + sign * n * WT.carrier_order) / delta))] = .1 * scale
    return OrderSpectrum(axis, values, delta, 1024, 640)


class PlanetaryKinematicsTests(unittest.TestCase):
    def test_wt_hand_computed_willis_and_events(self):
        self.assertEqual(WT.carrier_order, 7 / 32)
        self.assertEqual(WT.mesh_order, 175 / 8)
        self.assertEqual(WT.sun_relative_order, 25 / 32)
        self.assertEqual(WT.event_orders["sun_mesh_encounter"], 25 / 8)
        self.assertAlmostEqual(WT.planet_relative_order, 175 / 288)
        self.assertAlmostEqual(WT.axis_order("planet"), -7 / 18)
        self.assertNotEqual(WT.planet_relative_order, WT.sun_relative_order)
        self.assertAlmostEqual((WT.axis_order("sun") - WT.axis_order("carrier")) * 28, WT.axis_order("carrier") * 100)
        self.assertAlmostEqual((WT.axis_order("planet") - WT.axis_order("carrier")) * 36, -WT.mesh_order)

    def test_carrier_reference_changes_every_order_consistently(self):
        carrier = replace(WT, reference_axis="carrier")
        self.assertEqual(carrier.mesh_order, 100)
        self.assertEqual(carrier.carrier_order, 1)
        self.assertAlmostEqual(carrier.planet_relative_order, 25 / 9)
        for name, value in carrier.event_orders.items():
            self.assertAlmostEqual(value * WT.carrier_order, WT.event_orders[name])

    def test_complete_geometry_and_explicit_supported_axes(self):
        for values in ((28, 100, 35, 4, "sun"), (28, 100, 36, 4, "planet"), (28, 100, 36, 0, "sun"), (28.0, 100, 36, 4, "sun")):
            with self.assertRaises(ValueError):
                PlanetaryGearGeometry(*values)
        with self.assertRaises(ValueError):
            replace(WT, fixed_member="sun")


class PlanetarySidebandTests(unittest.TestCase):
    def test_carrier_spaced_nonoverlapping_amplitude_ratio(self):
        result = analyze_planetary_sidebands(spectrum_with_sidebands(), WT.mesh_order, WT.carrier_order)
        self.assertEqual(result.ser.status, "evaluated")
        self.assertAlmostEqual(result.ser.value, 1.2)
        self.assertTrue(result.ser.details["non_overlapping_windows"])
        self.assertEqual(len(result.observations), 6)
        self.assertFalse(any(item["significant"] for item in result.observations))

    def test_same_spectrum_does_not_use_fixed_axis_one_order_windows(self):
        spec = spectrum_with_sidebands()
        fixed = analyze_fixed_axis_sidebands(spec, WT.mesh_order, sideband_half_width_order=.005)
        self.assertAlmostEqual(fixed.ser.value, 0)
        self.assertAlmostEqual(analyze_planetary_sidebands(spec, WT.mesh_order, WT.carrier_order).ser.value, 1.2)

    def test_scale_invariance_and_no_hard_amplitude_floor(self):
        for scale in (1e-15, 1.0, 1e15):
            self.assertAlmostEqual(analyze_planetary_sidebands(spectrum_with_sidebands(scale), WT.mesh_order, WT.carrier_order).ser.value, 1.2)

    def test_low_carrier_insufficient_resolution_and_coverage_are_unavailable(self):
        spec = spectrum_with_sidebands()
        self.assertEqual(analyze_planetary_sidebands(spec, WT.mesh_order, .001).ser.reason, "carrier_sidebands_not_resolvable")
        axis = np.arange(251) * .1
        coarse = OrderSpectrum(axis, np.ones(len(axis)), .1, 1024, 10)
        self.assertEqual(analyze_planetary_sidebands(coarse, WT.mesh_order, WT.carrier_order).ser.status, "not_evaluable")
        short = replace(spec, order_bins=spec.order_bins[:14050], amplitude=spec.amplitude[:14050])
        self.assertEqual(analyze_planetary_sidebands(short, WT.mesh_order, WT.carrier_order).ser.reason, "requested_planetary_sidebands_outside_spectrum")

    def test_coincident_event_candidates_cannot_localize(self):
        spec = spectrum_with_sidebands()
        peaks = modulation_peaks(spec, {"a": 1., "b": 1.}, 20.)
        self.assertTrue(all(p.reason == "coincident_event_orders_not_identifiable" for p in peaks))


class PlanetaryPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipeline = PlanetaryGearPipeline(WT)
        cls.analysis = cls.pipeline.analyze(signal(residual=True), FS, SPEED)

    def test_tsa_has_actual_carrier_revolutions_and_angular_residual_peak(self):
        analysis = self.analysis
        self.assertEqual(analysis.status, "computed")
        self.assertEqual(analysis.tsa_reference_axis, "carrier")
        self.assertEqual(analysis.synchronous.synchronous_shaft, "carrier")
        self.assertEqual(analysis.synchronous.revolutions, 21)
        residual_angle = replace(analysis.synchronous.angle_domain, samples=analysis.synchronous.nonsynchronous_signal)
        spectrum = compute_order_spectrum(residual_angle, 110)
        peak = spectrum.order_bins[np.argmax(spectrum.amplitude)]
        self.assertAlmostEqual(peak, 30.5, delta=spectrum.order_resolution)
        # 原始 fs=8192 和角域1024点/架转不相同；错误传 fs 会放大8倍。
        self.assertEqual(spectrum.samples_per_revolution, 1024)
        self.assertLess(float(np.max(spectrum.amplitude[np.abs(spectrum.order_bins - 100) < .1])), .01)
        method = next(m for m in analysis.methods if m.method == "tsa_residual")
        self.assertEqual(method.reference_axis, "carrier")

    def test_carrier_tsa_classic_descriptors_have_explicit_representation(self):
        clean = self.pipeline.analyze(signal(), FS, SPEED, methods=())
        self.assertAlmostEqual(clean.metrics["fm4"].value, 2.25, delta=.025)
        self.assertAlmostEqual(clean.metrics["m6a"].value, 6.25, delta=.10)
        self.assertAlmostEqual(clean.metrics["m8a"].value, 19.140625, delta=.4)
        self.assertGreater(clean.metrics["fm0"].value, 2.38)
        self.assertLess(clean.metrics["fm0"].value, 2.41)
        self.assertEqual(clean.metrics["fm4"].details["signal_representation"], "carrier_TSA_regular_minus_mesh")
        self.assertEqual(clean.metrics["na4"].status, "not_evaluable")

    def test_sun_tsa_does_not_apply_integer_mesh_comb_to_fractional_mesh(self):
        analysis = PlanetaryGearPipeline(WT, PlanetaryParameters(tsa_reference_axis="sun")).analyze(signal(), FS, SPEED, methods=("tsa_residual",))
        self.assertEqual(analysis.tsa_reference_axis, "sun")
        self.assertEqual(analysis.metrics["fm4"].status, "not_evaluable")
        self.assertEqual(analysis.metrics["fm4"].reason, "noninteger_mesh_order_for_selected_tsa_axis")

    def test_missing_geometry_speed_fast_and_multiframe_never_become_healthy(self):
        cases = [PlanetaryGearPipeline(None).run(signal(), FS, SPEED), self.pipeline.run(signal(), FS)]
        trajectory = SpeedTrajectory(np.array([0., 5.]), np.array([20., 40.]), "synthetic_ramp")
        varying = OrderAnalysis.failed("varying_speed", trajectory, "explicit_ramp")
        cases.append(self.pipeline.run(signal(), FS, order_analysis=varying))
        for diagnosis in cases:
            self.assertEqual(diagnosis.evaluation.conclusion, "unknown")
            self.assertEqual(diagnosis.evaluation.status, "not_evaluable")

    def test_finite_but_insufficient_record_and_nyquist_are_not_healthy(self):
        short = self.pipeline.run(signal()[:128], FS, SPEED)
        self.assertEqual(short.analysis.sidebands.ser.status, "not_evaluable")
        self.assertEqual(short.evaluation.conclusion, "unknown")
        invalid = self.pipeline.run(signal(), 500., SPEED)
        self.assertEqual(invalid.analysis.reason, "mesh_sidebands_above_physical_nyquist")

    def test_narrowband_sun_event_peak_and_local_background_are_observable(self):
        time = np.arange(5 * FS) / FS
        rng = np.random.default_rng(72)
        values = (1 + .4 * np.cos(2 * np.pi * 62.5 * time)) * np.sin(2 * np.pi * 437.5 * time) + .02 * rng.normal(size=len(time))
        result = self.pipeline.analyze(values, FS, SPEED, include_tsa=False, methods=("narrowband",))
        method = result.methods[0]
        peak = next(item for item in method.peaks if item.name == "sun_mesh_encounter")
        self.assertEqual(peak.status, "computed")
        self.assertAlmostEqual(peak.peak_order, 25 / 8, delta=method.spectrum.order_resolution)
        self.assertGreater(peak.amplitude_to_background, 10)
        self.assertEqual(self.pipeline.evaluate(result).conclusion, "unknown")

    def test_too_few_angle_samples_return_explicit_unavailable(self):
        result = self.pipeline.run(signal(), FS, ScalarSpeed(1e-6, "near_standstill"))
        self.assertEqual(result.analysis.status, "not_evaluable")
        self.assertEqual(result.evaluation.conclusion, "unknown")

    def test_uncalibrated_rich_healthy_sidebands_do_not_alarm(self):
        evaluation = self.pipeline.evaluate(self.analysis)
        self.assertEqual(evaluation.status, "not_evaluable")
        self.assertEqual(evaluation.conclusion, "unknown")
        self.assertEqual(evaluation.indicators, {})
        self.assertIn("sidebands.ser", evaluation.unconsumed_metrics)

    def test_reassessment_consumes_only_selected_actual_metric(self):
        values = collect_planetary_metrics(self.analysis)
        for key, value in values.items():
            if value <= 0:
                continue
            baseline = PlanetaryBaseline(self.analysis.representation_key, (PlanetaryThreshold(key, value * .5, value * .75),), "synthetic_known_threshold_for_wiring_only")
            evaluation = self.pipeline.evaluate(self.analysis, baseline)
            self.assertTrue(evaluation.indicators[key]["critical"], key)
            self.assertEqual(evaluation.conclusion, "anomaly")
            self.assertEqual(len(evaluation.indicators), 1)
        baseline = PlanetaryBaseline(self.analysis.representation_key, (PlanetaryThreshold("vmd.unmigrated", 1., 2.),), "negative_control")
        self.assertEqual(self.pipeline.evaluate(self.analysis, baseline).conclusion, "unknown")

    def test_baseline_cannot_cross_geometry_record_length_speed_or_axis(self):
        baseline = PlanetaryBaseline(self.analysis.representation_key + ("wrong",), (PlanetaryThreshold("sidebands.ser", 1., 2.),), "mismatch")
        self.assertEqual(self.pipeline.evaluate(self.analysis, baseline).reason, "incompatible_planetary_baseline")

    def test_history_does_not_silently_degrade_into_current_moment(self):
        wrong = PlanetaryMomentHistory(("incompatible",), (1.,), (1.,), "synthetic_history")
        result = self.pipeline.analyze(signal(residual=True), FS, SPEED, history=wrong)
        self.assertEqual(result.metrics["na4"].reason, "incompatible_planetary_variance_history")
        history = replace(wrong, representation_key=self.analysis.representation_key)
        result = self.pipeline.analyze(signal(residual=True), FS, SPEED, history=history)
        self.assertEqual(result.metrics["na4"].status, "evaluated")


if __name__ == "__main__":
    unittest.main(verbosity=2)
