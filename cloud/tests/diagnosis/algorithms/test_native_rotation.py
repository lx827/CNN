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


def test_chirp_z_exclusive_nyquist_endpoint_keeps_full_sinusoid_amplitude():
    from scipy.signal import ZoomFFT
    from app.algorithms.gear.fixed_axis import ZoomParameters, compute_zoom_spectrum

    count, points, fs = 262144, 16, 2048.0
    resolution = fs / count
    low, high = fs / 2 - points * resolution, fs / 2
    frequency = high - resolution
    samples = np.sin(2 * np.pi * frequency / fs * np.arange(count))
    expected_axis = np.linspace(low, high, points, endpoint=False)
    # 官方ZoomFFT的频率点排除high；末点仍是普通正频率，不是Nyquist。
    official = ZoomFFT(count, [low, high], points, fs=fs, endpoint=False)
    assert_allclose(official.points(), np.exp(2j * np.pi * expected_axis / fs), atol=2e-14)
    result = compute_zoom_spectrum(samples, fs, ZoomParameters((low + high) / 2, high - low, points))
    assert_allclose(result.spectrum.frequency_hz, expected_axis, atol=0)
    assert result.spectrum.frequency_hz[-1] < fs / 2
    assert_allclose(result.spectrum.amplitude[-1], 1.0, atol=2e-9)
    # 真正的DC不翻倍；与区间上限相邻的正频率规则分开。
    dc = rotation.zoom_spectrum(np.ones(64), fs, 0.0, fs / 4, points)
    assert_allclose(dc[0], 1.0, atol=1e-14)


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


def test_public_numeric_boundary_rejects_undefined_inputs():
    # 绑定只建立布局前提；公开核必须承担数值前提，不能把NaN吞成零CUSUM或空峰。
    operations = [
        lambda: sequence.regression([0.0, np.nan], [1.0, 2.0]),
        lambda: sequence.cusum([0.0, np.nan]),
        lambda: sequence.mann_whitney_z(np.arange(12.0), [np.nan], 4),
        lambda: sequence.window_moments([0.0, np.nan], 2),
        lambda: sequence.robust_standardize([0.0, np.nan]),
        lambda: rotation.window_peaks([0.0, 1.0], [1.0, 2.0], [np.nan], 0.1),
        lambda: rotation.local_peak([0.0, 1.0], [1.0, 2.0], 1.0, 0.1, exclusions=[np.nan]),
    ]
    for operation in operations:
        with np.testing.assert_raises(ValueError):
            operation()
