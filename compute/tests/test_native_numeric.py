"""原生公共数值边界：数学刻度、奇偶长度、布局与最终 owner。"""

import gc
import unittest

import numpy as np
from numpy.testing import assert_allclose
from scipy import signal, stats

from cnn_compute import filtering, fourier, numeric


class NativeNumericTests(unittest.TestCase):
    def test_fourier_real_complex_and_hermitian_inverse(self):
        rng = np.random.default_rng(129)
        for n in (1, 2, 63, 64, 101):
            x = rng.normal(size=n)
            assert_allclose(fourier.fft(x), np.fft.fft(x), atol=2e-13)
            assert_allclose(fourier.rfft(x), np.fft.rfft(x), atol=2e-13)
            assert_allclose(fourier.irfft(fourier.rfft(x), n), x, atol=2e-13)
            z = x + 1j * rng.normal(size=n)
            assert_allclose(fourier.fft(z), np.fft.fft(z), atol=2e-13)
            assert_allclose(fourier.ifft(z), np.fft.ifft(z), atol=2e-13)
        assert_allclose(fourier.convolve(x, x[:7]), np.convolve(x, x[:7]), atol=2e-13)

    def test_stft_odd_even_frames_and_amplitude(self):
        for size, window, overlap, nfft in (
            (103, 31, 13, 47),
            (103, 32, 13, 64),
            (5, 4, 0, 4),
            (7, 5, 0, 7),
        ):
            x = np.random.default_rng(1).normal(size=size)
            freq, time, z = signal.stft(
                x, fs=1000, nperseg=window, noverlap=overlap, nfft=nfft
            )
            amp = np.abs(z)
            amp[1 : -(1 if nfft % 2 == 0 else 0) or None] *= 2
            actual_time, actual_freq, actual_amp = numeric.stft(
                x, 1000, window, overlap, nfft
            )
            assert_allclose(actual_time, time, atol=1e-15)
            assert_allclose(actual_freq, freq, atol=1e-12)
            assert_allclose(actual_amp, amp, atol=2e-14)

    def test_statistics_window_and_tail_rms(self):
        x = np.random.default_rng(2).normal(size=257)
        s = numeric.statistics(x)
        assert_allclose(
            s[:4],
            [
                np.max(np.abs(x)),
                np.sqrt(np.mean(x * x)),
                stats.kurtosis(x, fisher=False),
                stats.skew(x),
            ],
            atol=1e-13,
        )
        overall, t, matrix, window, step = numeric.time_domain(x, 1000, 31, 9)
        self.assertEqual((window, step), (31, 9))
        assert_allclose(overall, s, atol=1e-13)
        for row, start in enumerate(range(0, len(x) - 30, 9)):
            assert_allclose(
                matrix[row],
                numeric.statistics(
                    x[start : start + 31] * signal.windows.hann(31, sym=False)
                ),
                atol=1e-13,
            )
            self.assertEqual(t[row], start / 1000)
        rms = numeric.segmented_rms(x, 1000, 100)
        assert_allclose(
            rms[:, 1], [np.std(x[:100]), np.std(x[100:200]), np.std(x[200:])]
        )
        self.assertTrue(np.isnan(numeric.statistics(np.ones(5))[2]))

    def test_filtering_against_scipy(self):
        x = np.random.default_rng(3).normal(size=513)
        for order in (3, 4):
            for lo, hi, band in (
                (0, 150, "lowpass"),
                (150, 500, "highpass"),
                (50, 150, "bandpass"),
            ):
                sos = filtering.butterworth(order, lo, hi, 1000)
                cutoff = [lo, hi] if band == "bandpass" else hi if lo == 0 else lo
                reference = signal.butter(
                    order, cutoff, btype=band, fs=1000, output="sos"
                )
                assert_allclose(
                    filtering.sosfiltfilt(sos, x),
                    signal.sosfiltfilt(reference, x),
                    atol=2e-12,
                )
        for derivative in (0, 1, 2):
            assert_allclose(
                filtering.savgol(x, 31, 3, derivative, 0.5),
                signal.savgol_filter(x, 31, 3, derivative, delta=0.5),
                atol=2e-12,
            )
        assert_allclose(filtering.detrend(x, True), signal.detrend(x), atol=1e-14)

    def test_cepstrum_hilbert_and_autocorrelation(self):
        x = np.random.default_rng(4).normal(size=127)
        log = np.log(
            np.abs(np.fft.fft(x * signal.windows.hann(len(x), sym=False))) + 1e-10
        )
        assert_allclose(
            numeric.cepstrum(x),
            np.fft.ifft(log - log.mean()).real[: len(x) // 2],
            atol=3e-14,
        )
        assert_allclose(
            numeric.hilbert_envelope(x), np.abs(signal.hilbert(x)), atol=2e-13
        )
        centered = x - x.mean()
        assert_allclose(
            numeric.autocorrelation(x),
            np.correlate(centered, centered, "full")[len(x) - 1 :],
            atol=2e-13,
        )

    def test_borrowed_input_and_owned_results_survive_reuse(self):
        base = np.arange(129, dtype=np.float64)
        base.setflags(write=False)
        freq, amp, power = numeric.spectrum(base, 1000)
        saved = amp.copy()
        self.assertIsNotNone(amp.base)
        self.assertFalse(amp.flags.owndata)
        del base, freq, power
        gc.collect()
        numeric.spectrum(np.ones(2048), 1000)
        assert_allclose(amp, saved)
        strided = np.arange(258, dtype=np.float64)[::2]
        assert_allclose(numeric.spectrum(strided, 1000)[1], amp * 2)

    def test_public_validation(self):
        for call in (
            lambda: fourier.fft([]),
            lambda: numeric.statistics([1, np.nan]),
            lambda: filtering.savgol([1, 2, 3], 2, 1),
            lambda: numeric.stft([1, 2], 1000, 3, 1, 4),
        ):
            with self.assertRaises(ValueError):
                call()


if __name__ == "__main__":
    unittest.main()
