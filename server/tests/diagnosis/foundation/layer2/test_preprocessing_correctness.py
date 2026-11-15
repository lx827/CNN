"""DWT 阈值去噪的已知合成信号；MED/CPW 数学验证归高级轴承专项。"""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from app.algorithms.decomposition.wavelet import denoise_wavelet


class WaveletDenoisingTest(unittest.TestCase):
    def test_known_low_frequency_tones_reduce_added_white_noise(self):
        fs = 8192
        time = np.arange(fs * 2) / fs
        clean = np.sin(2 * np.pi * 50 * time) + 0.5 * np.sin(2 * np.pi * 120 * time)
        noise = np.random.default_rng(42).normal(0, 0.8, len(time))
        output = denoise_wavelet(clean + noise, level=4)
        self.assertLess(np.mean((output - clean) ** 2), np.mean(noise**2))

    def test_zero_threshold_is_complete_reconstruction_and_odd_length_preserved(self):
        signal = np.random.default_rng(13).normal(size=1025)
        output = denoise_wavelet(signal, threshold_scale=0)
        np.testing.assert_allclose(output, signal, atol=1e-12)
        self.assertEqual(len(output), 1025)

    def test_unavailable_level_is_explicitly_rejected(self):
        with self.assertRaises(ValueError):
            denoise_wavelet([1, -1, 0.5, -0.5])
        with self.assertRaises(ValueError):
            denoise_wavelet(np.ones(128), threshold_mode="unknown")


if __name__ == "__main__":
    unittest.main()
