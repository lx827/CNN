"""高级轴承谱峭度：高斯基准、真实滤波器组与已知共振带。"""
import os
import sys
import unittest

import numpy as np
from scipy.signal import butter, sosfiltfilt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.algorithms.bearing.spectral_kurtosis import (
    FilterBankKurtogramParameters,
    FilterBankKurtogramPipeline,
    ReweightedSpectralKurtosisPipeline,
    complex_spectral_kurtosis,
)


FS = 4096.0


def _resonant_impulses(seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(FS * 3.0)
    t = np.arange(n) / FS
    carrier = sosfiltfilt(
        butter(4, [1088.0, 1216.0], btype="bandpass", fs=FS, output="sos"),
        rng.standard_normal(n),
    )
    # 周期调制只产生带内 ±20/±40 Hz 边带，避免宽带冲击裙边干扰负对照。
    modulation = 0.3 + 1.8 * (0.5 + 0.5 * np.cos(2.0 * np.pi * 20.0 * t)) ** 2
    return modulation * carrier + 0.03 * rng.standard_normal(n)


class ComplexSpectralKurtosisTests(unittest.TestCase):
    def test_complex_gaussian_baseline_is_zero_not_pearson_minus_three(self):
        # 功率 [0,1,1,4] 的 <|z|^4>/<|z|^2>^2 恰为 2，因此复高斯基准形式为 0。
        z = np.array([0.0 + 0.0j, 1.0 + 0.0j, 1.0 + 0.0j, 2.0 + 0.0j])
        self.assertAlmostEqual(complex_spectral_kurtosis(z), 0.0, places=12)
        power = np.abs(z) ** 2
        pearson_minus_three = (
            np.mean((power - np.mean(power)) ** 4) / np.var(power) ** 2 - 3.0
        )
        self.assertLess(pearson_minus_three, -0.8)

        rng = np.random.default_rng(123)
        gaussian = (rng.standard_normal(100_000) + 1j * rng.standard_normal(100_000)) / np.sqrt(2.0)
        self.assertAlmostEqual(complex_spectral_kurtosis(gaussian), 0.0, delta=0.04)

    def test_constant_envelope_has_minus_one_baseline(self):
        z = np.exp(1j * np.arange(32) * 0.37)
        self.assertAlmostEqual(complex_spectral_kurtosis(z), -1.0, places=12)

    def test_complex_sk_is_invariant_to_nonzero_amplitude_scaling(self):
        rng = np.random.default_rng(912)
        z = rng.standard_normal(4096) + 1j * rng.standard_normal(4096)
        z[::97] += 8.0 + 2.0j
        reference = complex_spectral_kurtosis(z)
        for scale in (1e-150, 1e-12, 1e12, 1e150):
            with self.subTest(scale=scale):
                self.assertAlmostEqual(complex_spectral_kurtosis(z * scale), reference, places=11)
        with self.assertRaisesRegex(ValueError, "零能量"):
            complex_spectral_kurtosis(np.zeros(128, dtype=np.complex128))


class FilterBankKurtogramTests(unittest.TestCase):
    def test_known_resonance_band_is_selected_by_real_filter_bank(self):
        result = FilterBankKurtogramPipeline().run(
            _resonant_impulses(),
            FS,
            FilterBankKurtogramParameters(max_level=3, min_frequency_hz=100.0),
        )
        self.assertEqual(result.status, "computed", result.reason)
        self.assertIsNotNone(result.best_band)
        self.assertLess(result.best_band.low_hz, 1152.0)
        self.assertGreater(result.best_band.high_hz, 1152.0)
        self.assertGreater(result.max_spectral_kurtosis, 0.5)
        self.assertTrue(all(item.estimator == "complex_gaussian_sk_minus_2" for item in result.bands))
        self.assertIsNotNone(result.representation)

    def test_pure_noise_is_negative_control_without_fallback_band(self):
        rng = np.random.default_rng(91)
        noise = rng.standard_normal(int(FS * 2.0))
        result = FilterBankKurtogramPipeline().run(
            noise,
            FS,
            FilterBankKurtogramParameters(max_level=3, min_frequency_hz=100.0),
        )
        self.assertEqual(result.status, "indeterminate")
        self.assertEqual(result.reason, "no_impulsive_band_above_threshold")
        self.assertIsNone(result.best_band)
        self.assertIsNone(result.representation)

    def test_reweighted_score_uses_same_complex_sk_and_filter_bank(self):
        result = ReweightedSpectralKurtosisPipeline().run(
            _resonant_impulses(seed=19),
            FS,
            FilterBankKurtogramParameters(max_level=3, min_frequency_hz=100.0),
        )
        self.assertEqual(result.status, "computed", result.reason)
        self.assertLess(result.best_band.low_hz, 1152.0)
        self.assertGreater(result.best_band.high_hz, 1152.0)
        self.assertTrue(all(np.isfinite(item.reweighted_score) for item in result.bands))
        best = max(result.bands, key=lambda item: item.reweighted_score)
        self.assertEqual(best.band, result.best_band)
        self.assertGreaterEqual(best.impulsiveness, 1.0)

    def test_low_frequency_deterministic_tone_does_not_win(self):
        rng = np.random.default_rng(34)
        t = np.arange(int(FS * 3.0)) / FS
        low = 4.0 * np.sin(2.0 * np.pi * 180.0 * t)
        low = sosfiltfilt(butter(4, 350.0, btype="lowpass", fs=FS, output="sos"), low)
        result = FilterBankKurtogramPipeline().run(
            _resonant_impulses(seed=5) + low + 0.01 * rng.standard_normal(len(t)),
            FS,
            FilterBankKurtogramParameters(max_level=3, min_frequency_hz=100.0),
        )
        self.assertEqual(result.status, "computed", result.reason)
        self.assertGreater(result.best_band.center_hz, 500.0)

    def test_filter_bank_statistics_are_invariant_at_nonzero_tiny_scale(self):
        parameters = FilterBankKurtogramParameters(max_level=3, min_frequency_hz=100.0)
        signal = _resonant_impulses(seed=29)
        reference = FilterBankKurtogramPipeline().run(signal, FS, parameters)
        scaled = FilterBankKurtogramPipeline().run(signal * 1e-12, FS, parameters)
        self.assertEqual(scaled.status, reference.status)
        self.assertEqual(scaled.best_band, reference.best_band)
        np.testing.assert_allclose(
            [item.spectral_kurtosis for item in scaled.bands],
            [item.spectral_kurtosis for item in reference.bands],
            rtol=1e-8,
            atol=1e-10,
        )
        np.testing.assert_allclose(
            [item.impulsiveness for item in scaled.bands],
            [item.impulsiveness for item in reference.bands],
            rtol=1e-8,
            atol=1e-10,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
