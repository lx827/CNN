"""分解真实业务入口、物理量纲和已有指标重评的可执行证据。"""
import os
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.algorithms.decomposition.emd import EMDParameters, EnsembleParameters, decompose_emd, decompose_ceemdan
from app.algorithms.decomposition.vmd import VMDParameters, decompose_vmd
from app.algorithms.decomposition.wavelet import denoise_wavelet
from app.algorithms.pipelines.decomposition import (
    EMDDenoisingPipeline, VMDDenoisingPipeline, SensitiveComponentEnvelopePipeline,
    select_ranked_components, WaveletPacketEnergyPipeline,
)
from app.services.diagnosis.emd_denoise import emd_denoise
from app.services.diagnosis.vmd_denoise import vmd_denoise
from app.services.diagnosis.modality_bearing import emd_bearing_analysis, ceemdan_bearing_analysis, vmd_bearing_analysis
from app.services.diagnosis.wavelet_bearing import wavelet_packet_bearing_analysis, dwt_bearing_analysis
from app.services.diagnosis.wavelet_packet import compute_wavelet_packet_energy_entropy, wavelet_packet_denoise


FS = 1024.0


def signal(length=1024):
    t = np.arange(length) / FS
    return (1 + .4 * np.cos(2 * np.pi * 32 * t)) * np.cos(2 * np.pi * 192 * t) + .2 * np.sin(2 * np.pi * 8 * t)


class DecompositionBusinessTest(unittest.TestCase):
    def test_known_am_envelope_uses_peak_amplitude_units(self):
        t = np.arange(1024) / FS
        mode = (1 + .4 * np.cos(2 * np.pi * 32 * t)) * np.cos(2 * np.pi * 192 * t)
        result = SensitiveComponentEnvelopePipeline().analyze([mode], mode, FS,
            envelope_low_pass_hz=FS / 2)
        index = int(np.argmin(abs(result.spectrum.frequency_hz - 32)))
        self.assertAlmostEqual(result.spectrum.amplitude[index], .4, places=10)
        self.assertEqual(result.selection.status, "computed")

    def test_zero_and_failed_selection_never_become_fake_zero_outputs(self):
        arr = np.zeros(1024)
        for function, kwargs in ((emd_denoise, {"method": "emd"}),
                                 (vmd_denoise, {"K": 2}), (wavelet_packet_denoise, {})):
            with self.assertRaises(ValueError):
                function(arr, **kwargs)
        for function in (emd_bearing_analysis, vmd_bearing_analysis, wavelet_packet_bearing_analysis, dwt_bearing_analysis):
            result = function(arr, FS)
            self.assertEqual(result["status"], "indeterminate")
            self.assertEqual(result["envelope_amp"], [])
        selection = select_ranked_components([arr], arr, FS)
        self.assertIsNone(selection.representation)
        self.assertEqual(selection.selected_indices, ())

    def test_wp_frequency_order_and_original_axis_reconstruction(self):
        t = np.arange(4096) / FS
        arr = np.sin(2 * np.pi * 160 * t)
        result = compute_wavelet_packet_energy_entropy(arr, FS, wavelet="db8", level=3, gear_mesh_freq=160)
        # 第2个从0开始的理想频率带 [128,192] 对应 Gray路径 add，非自然序 ada。
        self.assertEqual(result["node_frequency_bands_hz"]["add"], [128, 192])
        self.assertGreater(result["mesh_band_concentration"], .7)
        response = wavelet_packet_bearing_analysis(arr, FS, level=3)
        self.assertEqual(response["node_center_freqs"]["add"], 160)
        self.assertEqual(response["status"], "computed")

    def test_misaligned_coefficients_cannot_be_scored_as_time_series(self):
        with self.assertRaises(ValueError):
            select_ranked_components([signal(128)], signal(1024), FS)

    def test_vmd_business_uses_hz_and_explicit_valid_window(self):
        result = vmd_bearing_analysis(signal(1025), FS, K=2)
        self.assertEqual(result["status"], "computed")
        self.assertEqual(result["valid_interval"], [0, 1025])
        self.assertEqual(len(result["mode_center_freqs"]), 2)
        self.assertLess(min(abs(np.asarray(result["mode_center_freqs"]) - 192)), 8)
        with self.assertRaises(ValueError):
            vmd_denoise(signal(51201), K=2)
        analysis = VMDDenoisingPipeline(VMDParameters(modes=2, max_samples=256)).analyze(signal(1025), FS)
        self.assertEqual(analysis.decomposition.valid_interval.stop_index, 256)
        self.assertEqual(analysis.reference.shape, (256,))

    def test_existing_metrics_can_be_reselected_without_decomposition(self):
        pipeline = EMDDenoisingPipeline(EMDParameters(max_imfs=3, max_sifts=30))
        analysis = pipeline.analyze(signal(), FS)
        with patch("app.algorithms.decomposition.emd.decompose_emd", side_effect=AssertionError("must not decompose")):
            permissive = pipeline.evaluate(analysis, correlation_threshold=0, kurtosis_threshold=100)
            rejected = pipeline.evaluate(analysis, correlation_threshold=1, kurtosis_threshold=1e9)
        self.assertEqual(permissive.status, "computed")
        self.assertEqual(rejected.status, "indeterminate")
        self.assertIsNone(rejected.representation)

    def test_bearing_evaluate_existing_analysis_does_not_repeat_hilbert(self):
        pipeline = SensitiveComponentEnvelopePipeline()
        analysis = pipeline.analyze([signal()], signal(), FS)
        with patch("scipy.signal.hilbert", side_effect=AssertionError("must not transform")):
            result = pipeline.evaluate(analysis)
        self.assertEqual(result.status, "indeterminate")  # 未提供真实轴承几何和转频

    def test_ceemdan_first_imf_matches_torres_ensemble_mean(self):
        arr = signal(256)
        params = EnsembleParameters(EMDParameters(max_imfs=1, max_sifts=20), 3, .15)
        actual = decompose_ceemdan(arr, FS, seed=23, parameters=params)
        rng = np.random.default_rng(23)
        scale = np.std(arr)
        firsts = [decompose_emd(arr / scale + .15 * rng.normal(size=len(arr)), FS, params.emd).imfs[0]
                  for _ in range(3)]
        np.testing.assert_allclose(actual.imfs[0], np.mean(firsts, axis=0) * scale, atol=1e-12)
        np.testing.assert_allclose(actual.reconstructed, arr, atol=1e-12)

    def test_decomposition_and_thresholds_do_not_depend_on_amplitude_units(self):
        arr = signal(512)
        params = EMDParameters(max_imfs=3, max_sifts=30)
        first = decompose_emd(arr, FS, params)
        small = decompose_emd(arr * 1e-9, FS, params)
        np.testing.assert_allclose(np.asarray(first.imfs), np.asarray(small.imfs) / 1e-9, atol=1e-8)
        vmd_params = VMDParameters(modes=2, max_iterations=100)
        original = decompose_vmd(arr, FS, vmd_params)
        scaled = decompose_vmd(arr * 1e-9, FS, vmd_params)
        np.testing.assert_allclose(original.center_frequencies_hz, scaled.center_frequencies_hz, atol=1e-8)
        np.testing.assert_allclose(original.modes, scaled.modes / 1e-9, atol=1e-8)
        np.testing.assert_allclose(denoise_wavelet(arr), denoise_wavelet(arr * 1e-9) / 1e-9, atol=1e-10)

    def test_noise_assisted_business_is_reproducible_with_explicit_seed(self):
        first = ceemdan_bearing_analysis(signal(256), FS, max_imfs=3, ensemble_size=3, seed=17)
        second = ceemdan_bearing_analysis(signal(256), FS, max_imfs=3, ensemble_size=3, seed=17)
        self.assertEqual(first, second)
        self.assertEqual(first["seed"], 17)


if __name__ == "__main__":
    unittest.main()
