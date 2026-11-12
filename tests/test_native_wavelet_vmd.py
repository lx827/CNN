"""原生小波/VMD 的数学参考、业务状态与拥有权；不把参考末位当作规范。"""

import gc
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pywt

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cloud"))

from app.algorithms.decomposition.vmd import VMDParameters, decompose_vmd
from app.algorithms.decomposition.vmd.python_adapter import PythonVMDImplementation
from app.algorithms.decomposition.wavelet import (
    decompose_dwt,
    decompose_wavelet_packet,
    denoise_wavelet,
)
from app.algorithms.decomposition.wavelet.pywavelets_adapter import (
    PyWaveletsImplementation,
)

from cnn_compute import vmd, wavelet


class NativeWaveletTest(unittest.TestCase):
    def test_official_filter_families_modes_and_odd_reconstruction(self):
        rng = np.random.default_rng(124)
        for size in (1024, 1025):
            values = rng.normal(size=size)
            for name in ("haar", "db8", "sym5", "coif3", "bior3.5", "rbio2.2", "dmey"):
                for mode in pywt.Modes.modes:
                    with self.subTest(size=size, name=name, mode=mode):
                        native = decompose_dwt(values, 4096.0, name, 2, mode)
                        reference = decompose_dwt(values, 4096.0, name, 2, mode,
                                                  PyWaveletsImplementation())
                        for a, b in zip((native.approximation, *native.details),
                                        (reference.approximation, *reference.details)):
                            np.testing.assert_allclose(a.coefficients, b.coefficients, atol=1e-11, rtol=1e-11)
                            np.testing.assert_allclose(a.reconstructed, b.reconstructed, atol=1e-10, rtol=1e-10)
                        # dmey 是 FIR 近似，不把其本身的重构误差强制改成精确恒等。
                        if name != "dmey":
                            np.testing.assert_allclose(native.reconstructed, values, atol=1e-9, rtol=1e-9)

    def test_packet_paths_and_light_selected_reconstruction(self):
        values = np.random.default_rng(125).normal(size=1025)
        reference = decompose_wavelet_packet(values, 4096.0, "db8", 3,
                                             implementation=PyWaveletsImplementation())
        native = decompose_wavelet_packet(values, 4096.0, "db8", 3)
        for a, b in zip(native.nodes, reference.nodes):
            self.assertEqual((a.path, a.frequency_index), (b.path, b.frequency_index))
            np.testing.assert_allclose(a.coefficients, b.coefficients, atol=1e-11)
            np.testing.assert_allclose(a.reconstructed, b.reconstructed, atol=1e-10)
        light = wavelet.analyze_coefficients(values, level=3, packet=True)
        np.testing.assert_allclose(light.reconstruct([1, 4]),
                                   reference.nodes[1].reconstructed + reference.nodes[4].reconstructed,
                                   atol=1e-10)
        owned_view = light.coefficients[1]
        saved = owned_view.copy()
        del light
        gc.collect()
        np.testing.assert_array_equal(owned_view, saved)
        self.assertFalse(owned_view.flags.writeable)

    def test_thresholds_scale_and_input_ownership(self):
        values = np.random.default_rng(126).normal(size=2049)
        original = values.copy()
        for threshold in ("soft", "hard", "improved"):
            reference = denoise_wavelet(values, threshold_mode=threshold,
                                         implementation=PyWaveletsImplementation())
            native = denoise_wavelet(values, threshold_mode=threshold)
            np.testing.assert_allclose(native, reference, atol=1e-11, rtol=1e-10)
            np.testing.assert_allclose(denoise_wavelet(values * 1e-8, threshold_mode=threshold),
                                       native * 1e-8, atol=1e-19, rtol=1e-9)
        np.testing.assert_array_equal(values, original)
        retained = wavelet.denoise(values)
        saved = retained.copy()
        wavelet.denoise(values[::2])
        gc.collect()
        np.testing.assert_array_equal(retained, saved)


class NativeVMDTest(unittest.TestCase):
    @staticmethod
    def signal(size):
        time = np.arange(size) / 1024.0
        return np.sin(2 * np.pi * 30 * time) + 0.6 * np.sin(2 * np.pi * 150 * time)

    def test_admm_reference_even_odd_dc_and_window(self):
        for size, dc, tau, window in ((1024, False, 0, None), (1025, False, 0.01, None),
                                      (1400, True, 0, 1025)):
            values = self.signal(size)
            if dc:
                values += 0.4
            params = VMDParameters(modes=2, max_iterations=300, dc=dc, tau=tau, max_samples=window)
            native = decompose_vmd(values, 1024.0, params)
            reference = decompose_vmd(values, 1024.0, params, PythonVMDImplementation())
            self.assertEqual(native.status, reference.status)
            self.assertEqual(native.converged, reference.converged)
            self.assertEqual(native.valid_interval, reference.valid_interval)
            np.testing.assert_allclose(native.center_frequencies_hz, reference.center_frequencies_hz,
                                       atol=1e-5, rtol=1e-5)
            np.testing.assert_allclose(native.modes, reference.modes, atol=1e-5, rtol=1e-4)
            np.testing.assert_allclose(native.modes.sum(axis=0) + native.residual,
                                       values[:native.valid_interval.stop_index], atol=1e-12)

    def test_failure_iteration_state_and_lifetime(self):
        constant = vmd.decompose(np.ones(128), 1024)
        self.assertEqual(constant.status, "indeterminate")
        self.assertEqual(constant.modes.shape, (0, 128))
        np.testing.assert_array_equal(constant.residual, np.ones(128))
        values = self.signal(1025)
        original = values.copy()
        limited = vmd.decompose(values, 1024, max_iterations=1)
        self.assertFalse(limited.converged)
        self.assertEqual(limited.reason, "maximum_iterations_reached")
        saved = limited.modes.copy()
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda _: vmd.decompose(values, 1024, modes=2), range(2)))
        np.testing.assert_allclose(results[0].modes, results[1].modes)
        gc.collect()
        np.testing.assert_array_equal(limited.modes, saved)
        np.testing.assert_array_equal(values, original)


if __name__ == "__main__":
    unittest.main()
