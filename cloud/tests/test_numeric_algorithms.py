"""云端通用数值原语的独立数学测试，不依赖数据集或数据库。"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cloud"))

from app.algorithms.cepstrum import CepstrumRepresentation, analyze_cepstrum, compute_cepstrum
from app.algorithms.statistics import analyze_time_domain
from app.algorithms.transforms import compute_spectrum, compute_stft
from app.services import acquisition_analysis


class NumericAlgorithmTests(unittest.TestCase):
    def test_fft_sine_dc_nyquist_amplitude_and_power(self):
        fs, count = 1024.0, 1024
        time = np.arange(count) / fs
        sine = 2.5 * np.sin(2 * np.pi * 64 * time)
        spectrum = compute_spectrum(sine, fs)
        index = np.argmin(np.abs(spectrum.frequency_hz - 64.0))
        self.assertAlmostEqual(spectrum.amplitude[index], 2.5, places=12)
        self.assertAlmostEqual(spectrum.power[index], 2.5**2 / 2, places=12)
        self.assertEqual(spectrum.amplitude_unit, "input_signal")
        self.assertEqual(spectrum.power_unit, "input_signal^2")

        dc = compute_spectrum(np.full(count, 3.0), fs, remove_mean=False)
        self.assertAlmostEqual(dc.amplitude[0], 3.0, places=12)
        self.assertAlmostEqual(dc.power[0], 9.0, places=12)
        self.assertAlmostEqual(np.sum(dc.amplitude[2:]), 0.0, places=12)

        nyquist = compute_spectrum(4.0 * (-1.0) ** np.arange(count), fs, remove_mean=False)
        self.assertAlmostEqual(nyquist.amplitude[-1], 4.0, places=12)
        self.assertAlmostEqual(nyquist.power[-1], 16.0, places=12)
        self.assertAlmostEqual(nyquist.frequency_hz[-1], fs / 2, places=12)

    def test_stft_frequency_time_axes_and_amplitude(self):
        fs, count = 1024.0, 1024
        signal = np.sin(2 * np.pi * 64 * np.arange(count) / fs)
        result = compute_stft(signal, fs, nperseg=256, noverlap=128, nfft=256)
        self.assertEqual(result.amplitude.shape, (len(result.frequency_hz), len(result.time_s)))
        self.assertEqual(len(result.frequency_hz), 129)
        self.assertEqual(len(result.time_s), 9)
        self.assertAlmostEqual(result.time_s[0], 0.0, places=12)
        self.assertAlmostEqual(result.time_s[1] - result.time_s[0], 0.125, places=12)
        frequency_index = np.argmin(np.abs(result.frequency_hz - 64.0))
        self.assertAlmostEqual(np.max(result.amplitude[frequency_index]), 1.0, places=12)
        self.assertAlmostEqual(np.max(result.amplitude_db()), 0.0, places=8)
        self.assertEqual(result.amplitude_unit, "input_signal")

    def test_cepstrum_units_and_manual_peak_analysis(self):
        fs = 1024.0
        representation = compute_cepstrum(np.sin(np.arange(512)), fs)
        self.assertEqual(representation.quefrency_unit, "s")
        self.assertEqual(len(representation.quefrency_s), 256)
        self.assertAlmostEqual(representation.quefrency_s[1], 1 / fs, places=12)
        self.assertAlmostEqual(representation.amplitude[0], 0.0, places=12)

        amplitude = np.zeros(256)
        amplitude[20], amplitude[100] = 1.0, 0.75
        manual = CepstrumRepresentation(
            quefrency_s=np.arange(256) / fs,
            amplitude=amplitude,
        )
        analysis = analyze_cepstrum(manual, max_quefrency_s=0.5)
        self.assertEqual(len(analysis.peaks), 2)
        self.assertAlmostEqual(analysis.peaks[0].quefrency_s, 20 / fs, places=12)
        self.assertAlmostEqual(analysis.peaks[0].frequency_hz, fs / 20, places=12)
        self.assertAlmostEqual(analysis.peaks[1].amplitude, 0.75, places=12)

    def test_time_domain_statistics_and_window_series(self):
        fs = 100.0
        signal = np.sin(2 * np.pi * 5 * np.arange(400) / fs)
        result = analyze_time_domain(signal, fs, window_size=100, step=50)
        self.assertAlmostEqual(result.overall.rms, 1 / np.sqrt(2), places=12)
        self.assertAlmostEqual(result.overall.peak, 1.0, places=12)
        self.assertEqual(result.window_size, 100)
        self.assertEqual(result.step, 50)
        np.testing.assert_allclose(result.windowed.time_s, [0, 0.5, 1, 1.5, 2, 2.5, 3])
        self.assertEqual(result.windowed.rms.shape, result.windowed.time_s.shape)

    def test_dc24_four_channel_counts_rms_segments_and_full_arrays(self):
        rate, count = 1000, 1500
        time = np.arange(count) / rate
        values = np.column_stack([
            np.rint(100 * (channel + 1) * np.sin(2 * np.pi * 50 * time))
            for channel in range(4)
        ])
        options = {"fft": True, "rms": True, "envelope": False}
        result, arrays = acquisition_analysis.analyze_counts(values, rate, options)
        self.assertEqual(result["unit"], "ADC counts")
        self.assertNotIn("health_score", result)
        self.assertEqual(len(result["channels"]), 4)
        for channel, item in enumerate(result["channels"]):
            expected_amplitude = 100 * (channel + 1)
            self.assertAlmostEqual(item["rms"], np.std(values[:, channel]), places=12)
            frequency = arrays[f"ch{channel}_fft_frequency_hz"]
            amplitude = arrays[f"ch{channel}_fft_amplitude_counts"]
            self.assertEqual(len(frequency), count // 2 + 1)
            self.assertEqual(len(amplitude), count // 2 + 1)
            peak_index = np.argmax(amplitude)
            self.assertAlmostEqual(frequency[peak_index], 50.0, places=12)
            self.assertAlmostEqual(amplitude[peak_index], expected_amplitude, delta=0.5)
            curve = arrays[f"ch{channel}_rms_curve"]
            np.testing.assert_allclose(curve[:, 0], [0.5, 1.25])
            np.testing.assert_allclose(curve[:, 1], np.std(values[:, channel]), rtol=1e-12)

    def test_dc24_rejects_invalid_envelope_bands(self):
        values = np.zeros((64, 4))
        for low, high in [(None, 100), (0, 100), (200, 100), (100, 500)]:
            with self.subTest(low=low, high=high):
                with self.assertRaises(ValueError):
                    acquisition_analysis.analyze_counts(values, 1000, {
                        "fft": False, "rms": False, "envelope": True,
                        "band_low": low, "band_high": high,
                    })

    def test_display_decimation_does_not_change_full_analysis(self):
        rate = 1000
        values = np.column_stack([
            np.arange(1500) % 17 * (channel + 1) for channel in range(4)
        ])
        options = {"fft": True, "rms": True, "envelope": False}
        _, full_arrays = acquisition_analysis.analyze_counts(values, rate, options)
        with patch.object(acquisition_analysis, "display_points", return_value=[]):
            result, decimated_arrays = acquisition_analysis.analyze_counts(values, rate, options)
        self.assertTrue(all(not item["waveform"] for item in result["channels"]))
        self.assertEqual(full_arrays.keys(), decimated_arrays.keys())
        for key in full_arrays:
            np.testing.assert_array_equal(full_arrays[key], decimated_arrays[key])


if __name__ == "__main__":
    unittest.main(verbosity=2)
