"""CPW 稳定梳状前提与 TEO 负值/多分量组合语义。"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.algorithms.bearing.cepstral import CPWEnvelopePipeline, cepstral_pre_whitening
from app.algorithms.bearing.teo import TEOEnvelopePipeline, teager_energy_operator


class CPWTests(unittest.TestCase):
    def setUp(self):
        self.fs = 4096.0
        self.t = np.arange(8192) / self.fs
        rng = np.random.default_rng(42)
        comb = sum(
            (6.0 / k) * np.sin(2 * np.pi * 100.0 * k * self.t + 0.2 * k)
            for k in (1, 2, 3, 4)
        )
        impulses = np.zeros(len(self.t))
        impulses[np.arange(64, len(self.t) - 64, 83)] = 2.0
        rt = np.arange(160) / self.fs
        ringing = np.exp(-140.0 * rt) * np.sin(2 * np.pi * 1152.0 * rt)
        bearing = np.convolve(impulses, ringing, mode="same")
        self.signal = comb + bearing + 0.15 * rng.standard_normal(len(self.t))

    def test_stable_comb_is_attenuated(self):
        whitened = cepstral_pre_whitening(self.signal, self.fs, [100.0])
        frequency = np.fft.rfftfreq(len(self.t), 1.0 / self.fs)
        before = np.abs(np.fft.rfft(self.signal))
        after = np.abs(np.fft.rfft(whitened))
        indices = [int(np.argmin(np.abs(frequency - 100.0 * k))) for k in (1, 2, 3, 4)]
        self.assertLess(float(np.sum(after[indices] ** 2)), 0.35 * float(np.sum(before[indices] ** 2)))

    def test_empty_comb_is_explicitly_not_cpw(self):
        with self.assertRaisesRegex(ValueError, "梳状频率"):
            cepstral_pre_whitening(self.signal, self.fs, [])
        result = CPWEnvelopePipeline().run(self.signal, self.fs, comb_frequencies=[])
        self.assertEqual(result.status, "indeterminate")
        self.assertEqual(result.reason, "missing_stable_comb_frequencies")
        self.assertIsNone(result.representation)

    def test_time_varying_comb_does_not_claim_constant_frequency_cpw(self):
        result = CPWEnvelopePipeline().run(
            self.signal,
            self.fs,
            comb_frequencies=[100.0],
            comb_is_stable=False,
        )
        self.assertEqual(result.status, "indeterminate")
        self.assertEqual(result.reason, "time_varying_comb_requires_time_frequency_model")
        self.assertIsNone(result.representation)

    def test_stable_comb_pipeline_computes_filter_bank_envelope(self):
        result = CPWEnvelopePipeline().run(self.signal, self.fs, comb_frequencies=[100.0])
        self.assertEqual(result.status, "computed", result.reason)
        self.assertEqual(result.metadata["comb_frequencies_hz"], (100.0,))
        self.assertIsNotNone(result.representation)


class TEOTests(unittest.TestCase):
    def test_raw_teo_keeps_negative_values_and_cross_terms(self):
        rng = np.random.default_rng(8)
        signal = rng.standard_normal(128)
        raw = teager_energy_operator(signal)
        np.testing.assert_allclose(raw[1:-1], signal[1:-1] ** 2 - signal[:-2] * signal[2:])
        self.assertLess(float(np.min(raw)), 0.0)

        t = np.arange(2048) / 2048.0
        first = np.cos(2 * np.pi * 130.0 * t)
        second = np.cos(2 * np.pi * 211.0 * t)
        separate = teager_energy_operator(first) + teager_energy_operator(second)
        combined = teager_energy_operator(first + second)
        self.assertGreater(float(np.max(np.abs(combined - separate))), 0.1)

    def test_pipeline_clips_only_envelope_input_after_preserving_raw_teo(self):
        fs = 2048.0
        t = np.arange(8192) / fs
        signal = (1.0 + 0.8 * np.cos(2 * np.pi * 40.0 * t)) * np.sin(2 * np.pi * 700.0 * t)
        result = TEOEnvelopePipeline().run(signal, fs)
        self.assertEqual(result.status, "computed", result.reason)
        np.testing.assert_allclose(result.envelope_input, np.maximum(result.raw_teo, 0.0))
        self.assertGreaterEqual(float(np.min(result.envelope_input)), 0.0)
        self.assertEqual(result.metadata["negative_value_policy"], "clip_only_after_raw_teo")
        self.assertEqual(result.metadata["multi_component_policy"], "bandpass_before_teo_cross_terms_remain_engineering_approximation")
        self.assertNotIn("variable_speed", result.metadata)
        self.assertIsNotNone(result.representation)


if __name__ == "__main__":
    unittest.main(verbosity=2)
