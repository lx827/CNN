"""原生公开调用的独立数学向量和输出生命周期。"""
import numpy as np
from numpy.testing import assert_allclose

from cnn_compute import rotation, sequence


def test_phase_integral_and_angle_interpolation():
    time = np.arange(2001) / 1000
    speed = 10 + 3 * time
    phase = rotation.integrate(time, speed)
    assert_allclose(phase, 10 * time + 1.5 * time**2, atol=2e-13)
    samples = rotation.angle_resample(2 * phase - 7, phase, 128)
    assert_allclose(samples, 2 * np.arange(len(samples)) / 128 - 7, atol=1e-13)
    saved = samples.copy()
    rotation.angle_resample(time, phase, 64)
    assert_allclose(samples, saved, atol=0)  # 工作区复用不能覆盖已交接数组。


def test_tsa_shared_cycle_fft_preserves_long_hann_spectrum():
    # 含DC、mesh/sideband以及Nyquist，检查单圈DFT移频恒等式而非另一套TSA实现。
    spr, revolutions = 128, 5
    angle = np.arange(spr) / spr
    cycle = 3 + np.sin(2 * np.pi * 12 * angle) + .2 * np.cos(2 * np.pi * 11 * angle) + .1 * (-1.0)**np.arange(spr)
    mesh, regular, residual, differential, amplitude = rotation.tsa_components(cycle, [12], [11, 12], revolutions)
    assert_allclose(mesh, np.tile(np.sin(2 * np.pi * 12 * angle), revolutions), atol=1e-14)
    assert_allclose(regular - mesh, differential, atol=1e-14)
    assert_allclose(regular + residual, np.tile(cycle, revolutions), atol=1e-14)
    direct = rotation.amplitude_spectrum(np.tile(cycle, revolutions))
    assert_allclose(amplitude, direct, atol=3e-15)


def test_chirp_z_matches_direct_dft_on_non_fft_grid():
    count, points, fs = 127, 37, 1000
    signal = np.cos(2 * np.pi * 123.4 * np.arange(count) / fs)
    low, high = 100, 150
    frequency = low + np.arange(points) * (high - low) / points
    window = .5 - .5 * np.cos(2 * np.pi * np.arange(count) / count)
    truth = np.abs(np.exp(-2j * np.pi * frequency[:, None] * np.arange(count) / fs) @ (signal * window)) * 2 / window.sum()
    assert_allclose(rotation.zoom_spectrum(signal, fs, low, high, points), truth, rtol=2e-13, atol=2e-14)


def test_sequence_constants_cusum_and_scale_free_moments():
    scores, rates, variance = sequence.kalman(np.full(100, 37.0))
    assert_allclose(scores, 37, atol=0)
    assert_allclose(rates, 0, atol=0)
    assert 0 < variance < 25
    level, trend, season, fitted, forecast = sequence.holt(np.full(30, 42.0), 5, .3, .1, .05, 6, 0)
    assert_allclose(level, 42, atol=2e-14)
    assert_allclose(forecast, 42, atol=2e-14)
    positive, negative, final_positive, final_negative, _ = sequence.cusum(np.ones(8))
    assert (positive, negative, final_positive, final_negative) == (4, 0, 4, 0)
    phase = np.arange(1024) * 2 * np.pi / 1024
    moment, variance = sequence.central_moment(1e-50 * np.sin(phase), 4, scaled=True)
    assert_allclose(moment / variance**2, 1.5, atol=1e-14)
