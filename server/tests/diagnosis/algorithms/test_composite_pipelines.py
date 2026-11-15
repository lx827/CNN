"""#75已知解、物理前提、真实阶段链与研究隔离的集中验证。无真实数据效果断言。"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.algorithms.composite.amfm import demodulate_amfm
from app.algorithms.composite.cvs import (
    CVSAlignment,
    reconstruct_continuous_planet_signal,
)
from app.algorithms.composite.ica import FastICAParameters, compute_fast_ica
from app.algorithms.composite.msb import (
    MSBParameters,
    compute_modulation_bispectrum,
    analyze_msb_slice,
)
from app.algorithms.decomposition.types import ValidInterval
from app.algorithms.decomposition.vmd import VMDResult, VMDParameters
from app.algorithms.bearing.deconvolution import (
    MEDParameters,
    minimum_entropy_deconvolution,
)
from app.algorithms.mechanics import FixedAxisGearGeometry
from app.algorithms.mechanics.planetary import PlanetaryGearGeometry
from app.algorithms.order import ScalarSpeed
from app.algorithms.pipelines import composite
from app.algorithms.pipelines.composite import (
    VMDAMFMPipeline,
    ModulationBispectrumPipeline,
    CVSMEDMSBPipeline,
    VMDICAPipeline,
    MSWPEEPipeline,
    coarse_grain,
)
from app.services.diagnosis.composite import (
    analyze_composite_research,
    composite_to_dict,
)


def known_decomposition(modes, fs, centers, *, converged=True):
    modes = np.asarray(modes)
    return VMDResult(
        "valid",
        modes.shape[1],
        fs,
        modes,
        np.asarray(centers),
        np.asarray([centers]),
        np.zeros(modes.shape[1]),
        ValidInterval(0, modes.shape[1]),
        1,
        converged,
        None if converged else "VMD_not_converged",
    )


def phase_segments(coupled, *, count=8):
    fs = 256
    time = np.arange(fs) / fs
    rng = np.random.default_rng(2026)
    pieces = []
    for index in range(count):
        carrier_phase, modulation_phase = rng.uniform(-np.pi, np.pi, 2)
        extra = 0 if coupled else (index % 2) * np.pi
        pieces.append(
            np.cos(2 * np.pi * 40 * time + carrier_phase)
            + np.cos(2 * np.pi * 45 * time + carrier_phase + modulation_phase)
            + np.cos(2 * np.pi * 35 * time + carrier_phase - modulation_phase + extra)
        )
    return np.concatenate(pieces), fs


def cvs_fixture():
    fs = 2048
    time = np.arange(fs * 4) / fs
    carrier = 2 * np.pi * 2 * time
    planet_hz = 2 * 54 / 17
    planet = 2 * np.pi * planet_hz * time
    signal = np.cos(17 * planet) + 0.2 * np.cos(planet)
    context = CVSAlignment(carrier, planet, (0, np.pi), 0, 0, 1.0, planet_hz, 512)
    return signal, fs, context


class AMFMTests(unittest.TestCase):
    def test_real_vmd_adapter_amfm_and_ica_combinations_and_ablation(self):
        fs = 2048
        time = np.arange(fs * 2) / fs
        carrier = (1 + 0.4 * np.cos(2 * np.pi * 8 * time)) * np.cos(
            2 * np.pi * 256 * time
        )
        signal = carrier + 0.2 * np.cos(2 * np.pi * 32 * time)
        parameters = VMDParameters(modes=2, tolerance=1e-6, max_iterations=500)
        pipeline = VMDAMFMPipeline(parameters)
        result = pipeline.run(
            signal,
            fs,
            FixedAxisGearGeometry(32),
            ScalarSpeed(8, "known_physical_speed"),
        )
        self.assertEqual(result.analysis.status, "computed", result.analysis.reason)
        peak = result.analysis.data["amplitude_peaks"]["input_rotation"]
        self.assertAlmostEqual(peak.observed_frequency_hz, 8, delta=0.51)
        self.assertGreater(peak.amplitude, 0.3)
        self.assertLess(peak.amplitude, 0.5)
        # 同一个真实分解复用到BSS；不重复耗时VMD。
        bss = VMDICAPipeline(parameters).run(
            signal, fs, decomposition=result.analysis.data["decomposition"]
        )
        self.assertEqual(bss.analysis.status, "computed", bss.analysis.reason)
        raw = demodulate_amfm(signal, fs)
        index = np.argmin(np.abs(raw.amplitude_spectrum.frequency_hz - 8))
        print(
            "SYNTHETIC_ABLATION "
            + json.dumps(
                {
                    "signal": "256Hz_carrier_8Hz_AM_plus_32Hz_interference",
                    "known_AM_amplitude": 0.4,
                    "VMD_AMFM_amplitude": peak.amplitude,
                    "without_VMD_AMFM_amplitude": float(
                        raw.amplitude_spectrum.amplitude[index]
                    ),
                    "without_AMFM": "carrier_mode_has_no_modulation_spectrum",
                    "BSS_status": bss.analysis.status,
                    "without_ICA": "VMD_modes_only_no_source_unmixing",
                    "without_VMD_BSS": "single_observation_does_not_identify_two_sources",
                    "effectiveness_claim": False,
                }
            )
        )

    def test_amfm_known_carrier_modulation_and_frequency_units(self):
        fs = 8192
        time = np.arange(fs * 2) / fs
        mode = (1 + 0.4 * np.cos(2 * np.pi * 25 * time)) * np.cos(
            2 * np.pi * 1000 * time + 0.2 * np.sin(2 * np.pi * 25 * time)
        )
        interference = 0.15 * np.cos(2 * np.pi * 60 * time)
        decomposition = known_decomposition([interference, mode], fs, [60, 1000])
        pipeline = VMDAMFMPipeline()
        diagnosis = pipeline.run(
            mode + interference,
            fs,
            FixedAxisGearGeometry(40),
            ScalarSpeed(25, "physical_truth"),
            decomposition=decomposition,
        )
        data = diagnosis.analysis.data
        self.assertEqual(data["selected_mode"], 1)
        am, fm = (
            data["amplitude_peaks"]["input_rotation"],
            data["frequency_peaks"]["input_rotation"],
        )
        self.assertAlmostEqual(am.observed_frequency_hz, 25.0, places=8)
        self.assertAlmostEqual(am.amplitude, 0.4, places=6)
        self.assertAlmostEqual(fm.amplitude, 5.0, delta=0.01)
        self.assertEqual(fm.amplitude_unit, "Hz")
        self.assertEqual(am.target_order, 1)
        self.assertEqual(data["modulation_targets_hz"], {"input_rotation": 25})
        # 评估已有指标时不重新做Hilbert/VMD/FFT。
        with patch.object(
            composite, "demodulate_amfm", side_effect=AssertionError("recomputed")
        ):
            evaluation = pipeline.evaluate(diagnosis.analysis)
        self.assertEqual(evaluation.status, "not_evaluable")
        self.assertFalse(evaluation.production_eligible)
        self.assertTrue(
            all(item["warning"] is None for item in evaluation.indicators.values())
        )

    def test_planetary_centers_and_modulation_targets_are_physical_hz(self):
        fs = 4096
        time = np.arange(fs * 2) / fs
        geometry = PlanetaryGearGeometry(20, 54, 17, 2, "carrier")
        mode = (1 + 0.3 * np.cos(2 * np.pi * 5 * time)) * np.cos(2 * np.pi * 270 * time)
        diagnosis = VMDAMFMPipeline().run(
            mode,
            fs,
            geometry,
            ScalarSpeed(5, "physical_truth"),
            decomposition=known_decomposition([mode], fs, [270]),
        )
        self.assertEqual(diagnosis.analysis.status, "computed")
        self.assertEqual(diagnosis.analysis.data["mesh_frequency_hz"], 270)
        peak = diagnosis.analysis.data["amplitude_peaks"]["carrier_transfer"]
        self.assertAlmostEqual(peak.amplitude, 0.3, places=6)
        self.assertEqual(peak.target_frequency_hz, 5)
        self.assertAlmostEqual(
            diagnosis.analysis.data["modulation_targets_hz"]["planet_single_mesh"],
            270 / 17,
        )

    def test_amfm_negative_controls_and_unconverged_vmd(self):
        with self.assertRaisesRegex(ValueError, "amplitude_null"):
            demodulate_amfm(np.zeros(1024), 1024)
        time = np.arange(2048) / 2048
        mode = np.cos(2 * np.pi * 200 * time)
        result = VMDAMFMPipeline().run(
            mode,
            2048,
            FixedAxisGearGeometry(10),
            ScalarSpeed(20, "truth"),
            decomposition=known_decomposition([mode], 2048, [200], converged=False),
        )
        self.assertEqual(result.analysis.status, "approximate")
        self.assertEqual(result.evaluation.diagnosis_conclusion, "unknown")
        result = VMDAMFMPipeline().analyze(
            mode,
            2048,
            FixedAxisGearGeometry(10),
            ScalarSpeed(20, "truth"),
            decomposition=known_decomposition([mode], 2048, [20]),
        )
        self.assertEqual(result.reason, "no_VMD_mode_near_mesh_carrier")


class MSBTests(unittest.TestCase):
    def test_complex_average_precedes_absolute_and_phase_uncoupling_cancels(self):
        coupled, fs = phase_segments(True)
        uncoupled, _ = phase_segments(False)
        parameters = MSBParameters(256, 0, 8)
        good = compute_modulation_bispectrum(coupled, fs, [40], [5], parameters)
        bad = compute_modulation_bispectrum(uncoupled, fs, [40], [5], parameters)
        # 正弦A=1的复系数为1/2，四阶耦合精确值(1/2)^4=1/16。
        self.assertAlmostEqual(good.complex_mean[0, 0].real, 1 / 16, places=12)
        self.assertAlmostEqual(good.coherence[0, 0], 1, places=12)
        self.assertLess(bad.magnitude[0, 0], 1e-12)
        self.assertLess(bad.coherence[0, 0], 1e-10)
        scaled = compute_modulation_bispectrum(3 * coupled, fs, [40], [5], parameters)
        self.assertAlmostEqual(
            scaled.magnitude[0, 0] / good.magnitude[0, 0], 3**4, places=10
        )
        self.assertEqual(scaled.amplitude_unit, "input_signal^4")

    def test_background_has_same_fourth_order_units_and_invalid_targets_are_not_zero(
        self,
    ):
        signal, fs = phase_segments(True)
        parameters = MSBParameters(256, 0, 8)
        representation = compute_modulation_bispectrum(
            signal, fs, [40], [3, 4, 5, 6, 7, 50], parameters
        )
        scaled = compute_modulation_bispectrum(
            2 * signal, fs, [40], [3, 4, 5, 6, 7, 50], parameters
        )
        metrics, scaled_metrics = (
            analyze_msb_slice(representation),
            analyze_msb_slice(scaled),
        )
        self.assertFalse(representation.valid[0, -1])
        self.assertTrue(np.isnan(representation.magnitude[0, -1]))
        self.assertAlmostEqual(
            scaled_metrics["background"] / metrics["background"], 16, places=10
        )
        np.testing.assert_allclose(
            metrics["peak_to_background"],
            scaled_metrics["peak_to_background"],
            equal_nan=True,
        )
        with self.assertRaisesRegex(ValueError, "insufficient_segments"):
            compute_modulation_bispectrum(signal[:128], fs, [40], [5], parameters)


class CVSTests(unittest.TestCase):
    def test_spatially_aligned_windows_reassemble_independent_complete_planet_cycles(
        self,
    ):
        signal, fs, context = cvs_fixture()
        result = reconstruct_continuous_planet_signal(signal, fs, context)
        self.assertEqual(result.status, "computed")
        self.assertGreaterEqual(result.cycles, 2)
        phase = (
            np.arange(len(result.signal))
            * 2
            * np.pi
            / context.samples_per_planet_revolution
        )
        expected = np.cos(17 * phase) + 0.2 * np.cos(phase)
        np.testing.assert_allclose(result.signal, expected, atol=0.02, rtol=0)
        self.assertEqual(
            result.sample_rate_hz, context.planet_relative_frequency_hz * 512
        )
        # 另一个行星通过时的任意干扰不能进入本行星窗口。
        other = np.abs(np.angle(np.exp(1j * (context.carrier_phase_rad + np.pi)))) < 0.8
        contaminated = signal + np.where(other, 100.0, 0.0)
        comparison = reconstruct_continuous_planet_signal(contaminated, fs, context)
        np.testing.assert_array_equal(result.signal, comparison.signal)

    def test_missing_phase_and_incomplete_coverage_never_fall_back_to_original(self):
        from dataclasses import replace

        signal, fs, context = cvs_fixture()
        for invalid in (
            None,
            replace(context, passage_half_width_rad=0.001),
            replace(context, planet_phase_rad=context.planet_phase_rad[:-1]),
            replace(context, passage_half_width_rad=2.0),
        ):
            result = reconstruct_continuous_planet_signal(signal, fs, invalid)
            self.assertEqual(result.status, "indeterminate")
            self.assertIsNone(result.signal)

    def test_real_cvs_med_msb_chain_consumes_every_stage_output_and_ablation(self):
        signal, fs, context = cvs_fixture()
        pipeline = CVSMEDMSBPipeline(
            MEDParameters(8, 8, 1e-5, 1e-5), MSBParameters(512, 0.5, 3)
        )
        carrier = [17 * context.planet_relative_frequency_hz]
        modulation = np.arange(1, 5) * context.planet_relative_frequency_hz
        with (
            patch.object(
                composite,
                "minimum_entropy_deconvolution",
                wraps=minimum_entropy_deconvolution,
            ) as med_call,
            patch.object(
                composite,
                "compute_modulation_bispectrum",
                wraps=compute_modulation_bispectrum,
            ) as msb_call,
        ):
            result = pipeline.run(signal, fs, context, carrier, modulation)
        self.assertIn(result.analysis.status, ("computed", "approximate"))
        data = result.analysis.data
        self.assertIs(med_call.call_args.args[0], data["cvs"].signal)
        self.assertIs(msb_call.call_args.args[0], data["med"].signal)
        self.assertEqual(msb_call.call_args.args[1], data["cvs"].sample_rate_hz)
        self.assertEqual(
            [stage.name for stage in result.analysis.stages], ["CVS", "MED", "MSB"]
        )
        no_med = ModulationBispectrumPipeline(MSBParameters(512, 0.5, 3)).analyze(
            data["cvs"].signal, data["cvs"].sample_rate_hz, carrier, modulation
        )
        no_cvs = pipeline.analyze(signal, fs, None, carrier, modulation)
        self.assertEqual(no_cvs.status, "indeterminate")
        full_magnitude = data["msb"].data["representation"].magnitude
        no_med_magnitude = no_med.data["representation"].magnitude
        difference = float(np.linalg.norm(full_magnitude - no_med_magnitude))
        self.assertGreater(difference, 0)
        print(
            "SYNTHETIC_ABLATION "
            + json.dumps(
                {
                    "signal": "single_planet_17th_harmonic_plus_rotation",
                    "cvs_cycles": data["cvs"].cycles,
                    "full_status": result.analysis.status,
                    "without_cvs": no_cvs.reason,
                    "without_med_MSB_magnitude_l2_difference": difference,
                    "without_msb": "no_phase_coupling_representation",
                    "effectiveness_claim": False,
                    "real_data": "not_validated",
                }
            )
        )


class ICAAndMultiscaleTests(unittest.TestCase):
    def test_fast_ica_recovers_known_independent_sources_and_preserves_inverse_units(
        self,
    ):
        rng = np.random.default_rng(5)
        sources = np.column_stack([rng.laplace(size=12000), rng.uniform(-2, 2, 12000)])
        observations = sources @ np.array([[2.0, 0.6], [0.4, 1.5]]).T + np.array(
            [10, -4]
        )
        result = compute_fast_ica(observations)
        self.assertEqual(result.status, "computed")
        correlation = np.abs(np.corrcoef(sources.T, result.components.T)[:2, 2:])
        self.assertTrue(np.all(np.max(correlation, axis=1) > 0.99), correlation)
        np.testing.assert_allclose(
            result.reconstruct([0, 1]) + result.mean,
            observations,
            rtol=1e-12,
            atol=1e-12,
        )
        singular = compute_fast_ica(np.column_stack([sources[:, 0], sources[:, 0]]))
        self.assertEqual(singular.status, "indeterminate")
        self.assertIsNone(singular.components)
        approximate = compute_fast_ica(
            observations, FastICAParameters(max_iterations=1, tolerance=1e-16)
        )
        self.assertFalse(approximate.converged)

    def test_vmd_channel_expansion_ica_selection_uses_physical_contributions(self):
        rng = np.random.default_rng(10)
        modes = np.vstack([rng.laplace(size=4096), rng.uniform(-1, 1, 4096)])
        signal = np.sum(modes, axis=0)
        result = VMDICAPipeline(top_n=2).run(
            signal, 2048, decomposition=known_decomposition(modes, 2048, [100, 500])
        )
        self.assertEqual(result.analysis.status, "computed")
        data = result.analysis.data
        np.testing.assert_allclose(
            np.sum(data["source_contributions"], axis=0),
            signal - np.mean(signal),
            atol=1e-12,
        )
        np.testing.assert_allclose(
            data["selection"].representation, signal - np.mean(signal), atol=1e-12
        )
        self.assertFalse(result.evaluation.production_eligible)

    def test_coarse_graining_and_haar_entropy_have_hand_computed_answers(self):
        np.testing.assert_array_equal(coarse_grain(np.arange(7), 2), [0.5, 2.5, 4.5])
        with self.assertRaises(ValueError):
            coarse_grain(np.arange(7), 0)
        signal = np.tile([3.0, -1.0], 256)  # a=1,b=2: Haar低/高能量比1:4
        result = MSWPEEPipeline("haar", 1, 2).run(signal, 512)
        expected = -(0.2 * np.log2(0.2) + 0.8 * np.log2(0.8))
        np.testing.assert_allclose(
            result.analysis.data["normalized_entropy_vector"], [expected, 0], atol=1e-12
        )
        self.assertEqual(result.analysis.data["scales"][1]["sample_rate_hz"], 256)
        zero = MSWPEEPipeline("haar", 1, 2).run(np.zeros(512), 512)
        self.assertEqual(zero.analysis.status, "indeterminate")
        self.assertIsNone(zero.analysis.metrics["mean_normalized_entropy"])


class CompositeBoundaryTests(unittest.TestCase):
    def test_research_limit_serialization_and_missing_cvs_context(self):
        signal = np.tile([3.0, -1.0], 512)
        result = analyze_composite_research(
            "mswpee",
            signal,
            100,
            options={"wavelet": "haar", "level": 1, "max_scale": 2},
        )
        self.assertEqual(result.analysis.data["scales"][0]["coarse_samples"], 500)
        payload = composite_to_dict(result)
        json.dumps(payload, allow_nan=False)
        self.assertTrue(payload["research_only"])
        self.assertFalse(payload["production_eligible"])
        self.assertEqual(payload["fault_indicators"], {})
        self.assertEqual(payload["fault_probabilities"], {})
        self.assertIsNone(payload["health_score"])
        self.assertFalse(payload["validation"]["independent_vote"])
        signal, fs, _ = cvs_fixture()
        result = analyze_composite_research(
            "cvs_med_msb",
            signal,
            fs,
            geometry=PlanetaryGearGeometry(20, 54, 17, 2, "carrier"),
            speed=ScalarSpeed(2, "truth"),
        )
        self.assertEqual(result.analysis.status, "indeterminate")
        self.assertIsNone(result.analysis.data["cvs"].signal)
        self.assertEqual(result.evaluation.diagnosis_conclusion, "unknown")


if __name__ == "__main__":
    unittest.main(verbosity=2)
