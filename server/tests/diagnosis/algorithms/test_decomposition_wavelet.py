"""DWT/WP 数学、频率映射、时间轴与重构的独立测试。"""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.algorithms.decomposition.wavelet import (
    decompose_dwt,
    decompose_wavelet_packet,
    reconstruct_dwt,
    reconstruct_wavelet_packet,
)


class WaveletDecompositionTest(unittest.TestCase):
    def test_wp_natural_paths_have_explicit_gray_frequency_order(self):
        result = decompose_wavelet_packet(
            np.arange(256, dtype=np.float64),
            1024.0,
            wavelet="haar",
            level=3,
        )
        natural_paths = tuple(node.path for node in result.nodes)
        self.assertEqual(
            natural_paths,
            ("aaa", "aad", "ada", "add", "daa", "dad", "dda", "ddd"),
        )
        self.assertEqual(
            tuple(node.frequency_index for node in result.nodes),
            (0, 1, 3, 2, 7, 6, 4, 5),
        )
        self.assertEqual(
            tuple(node.path for node in result.nodes_in_frequency_order),
            ("aaa", "aad", "add", "ada", "dda", "ddd", "dad", "daa"),
        )
        for node in result.nodes:
            expected_low = node.frequency_index * 1024.0 / 16.0
            self.assertEqual(
                node.frequency_band_hz, (expected_low, expected_low + 64.0)
            )

    def test_wp_coefficient_rate_and_original_rate_reconstruction(self):
        signal = np.sin(2 * np.pi * 170.0 * np.arange(513) / 1024.0)
        result = decompose_wavelet_packet(signal, 1024.0, wavelet="db2", level=2)
        for node in result.nodes:
            self.assertEqual(node.coefficient_sample_rate_hz, 256.0)
            self.assertEqual(len(node.reconstructed), len(signal))
            self.assertEqual(node.valid_interval.start_index, 0)
            self.assertEqual(node.valid_interval.stop_index, len(signal))
        target = result.node_for_frequency(170.0)
        self.assertEqual(target.path, "ad")
        reconstructed = reconstruct_wavelet_packet(result, ("ad",))
        np.testing.assert_allclose(reconstructed, target.reconstructed, atol=1e-10)
        full = reconstruct_wavelet_packet(
            result, tuple(node.path for node in result.nodes)
        )
        np.testing.assert_allclose(full, signal, atol=1e-9)

    def test_dwt_selected_detail_excludes_approximation_and_other_details(self):
        fs = 1024.0
        t = np.arange(1024) / fs
        low = np.sin(2 * np.pi * 32.0 * t)
        high = 0.4 * np.sin(2 * np.pi * 320.0 * t)
        signal = low + high
        result = decompose_dwt(
            signal, fs, wavelet="haar", level=1, mode="periodization"
        )

        self.assertEqual(tuple(detail.level for detail in result.details), (1,))
        self.assertEqual(result.details[0].coefficient_sample_rate_hz, 512.0)
        self.assertEqual(result.approximation.coefficient_sample_rate_hz, 512.0)
        for band in (result.approximation, *result.details):
            self.assertEqual(len(band.reconstructed), len(signal))

        detail_1 = reconstruct_dwt(result, detail_levels=(1,))
        np.testing.assert_allclose(
            detail_1, result.details[0].reconstructed, atol=1e-10
        )
        spectrum = np.abs(np.fft.rfft(detail_1))
        peak_hz = np.fft.rfftfreq(len(detail_1), 1.0 / fs)[np.argmax(spectrum)]
        self.assertEqual(peak_hz, 320.0)
        # 有限长小波不是理想砖墙滤波器，但低频近似投影应被强烈抑制。
        self.assertLess(abs(np.dot(detail_1, low) / np.dot(low, low)), 0.02)
        np.testing.assert_array_equal(
            reconstruct_dwt(result, detail_levels=(), include_approximation=False),
            np.zeros(len(signal)),
        )

    def test_invalid_inputs_and_unknown_nodes_fail(self):
        with self.assertRaises(ValueError):
            decompose_dwt([1.0, 2.0, 3.0], 100.0, level=0)
        with self.assertRaises(ValueError):
            decompose_wavelet_packet([1.0, np.nan] * 16, 100.0, level=1)
        result = decompose_wavelet_packet(np.arange(64, dtype=float), 100.0, level=1)
        with self.assertRaises(ValueError):
            reconstruct_wavelet_packet(result, ("not-a-node",))
        with self.assertRaises(ValueError):
            result.node_for_frequency(60.0)


if __name__ == "__main__":
    unittest.main()
