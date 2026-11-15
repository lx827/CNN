"""转速/相位垂直切片的独立合成正确性测试，不使用旧输出作 golden。"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.algorithms.order import (
    AutomaticOrderPipeline,
    ConstantSpeedOrderPipeline,
    FastVaryingSpeedOrderPipeline,
    FrameParameters,
    LocalSpeedEstimates,
    OrderAnalysis,
    OrderParameters,
    PhaseTrajectory,
    RidgeParameters,
    ScalarSpeed,
    SlowVaryingSpeedOrderPipeline,
    SpeedSearchRange,
    SpeedTrajectory,
    compute_order_spectrum,
    integrate_speed_trajectory,
    resolve_stft_window_samples,
    select_retained_speed_frames,
)
from app.algorithms.order.estimation import _speed_range_violation
from tests.diagnosis.foundation.layer1.synthetic_signals import bearing_outer_race


def _amplitude_at(spectrum, order):
    index = int(np.argmin(np.abs(spectrum.order_bins - order)))
    return float(spectrum.order_bins[index]), float(spectrum.amplitude[index])


def _triangle_speed(time_s, low=12.0, high=36.0):
    duration = float(time_s[-1]) + float(time_s[1] - time_s[0])
    half = duration / 2
    return np.where(
        time_s < half,
        low + (high - low) * time_s / half,
        high - (high - low) * (time_s - half) / half,
    )


def _linear_revolutions(time_s, initial_hz, acceleration_hz_s):
    """线性扫频的解析累计转数，不与被测梯形积分共用实现。"""
    return initial_hz * time_s + 0.5 * acceleration_hz_s * time_s**2


def _triangle_revolutions(time_s, low=12.0, high=36.0):
    """分段线性三角扫频的解析积分。"""
    duration = float(time_s[-1]) + float(time_s[1] - time_s[0])
    half = duration / 2
    slope = (high - low) / half
    before = time_s <= half
    revolutions = np.empty_like(time_s)
    revolutions[before] = _linear_revolutions(time_s[before], low, slope)
    tau = time_s[~before] - half
    half_revolutions = low * half + 0.5 * slope * half**2
    revolutions[~before] = half_revolutions + high * tau - 0.5 * slope * tau**2
    return revolutions


def test_constant_speed_axis_and_single_sided_amplitude():
    fs, rot_freq, samples_per_rev = 8192.0, 20.0, 256
    time_s = np.arange(int(fs * 4) + 1) / fs
    # 4 秒共 80 转，3 阶正弦严格落在 FFT bin；期望幅值来自 A=0.75。
    signal = 0.75 * np.sin(2 * np.pi * 3.0 * rot_freq * time_s)
    result = ConstantSpeedOrderPipeline(
        OrderParameters(samples_per_revolution=samples_per_rev, max_order=20),
    ).run(signal, fs, ScalarSpeed(rot_freq, "test_known"))
    assert result.status == "valid"
    assert result.phase is not None and result.angle_domain is not None
    angle = result.angle_domain
    spectrum = result.spectrum
    assert angle.angle_revolutions[0] == 0
    assert angle.angle_revolutions[1] == 1 / samples_per_rev
    assert np.isclose(spectrum.order_resolution, 1 / 80)
    assert np.isclose(spectrum.order_bins[240], 3.0)
    assert np.isclose(spectrum.order_bins[320], 4.0)
    order, amplitude = _amplitude_at(spectrum, 3.0)
    assert np.isclose(order, 3.0, atol=1e-12)
    assert np.isclose(amplitude, 0.75, atol=0.01), amplitude
    assert spectrum.scaling == "single_sided_amplitude"
    assert spectrum.amplitude_unit == "input_signal"
    # 非法/未知标量转频不能被替换为 10 Hz。
    try:
        ScalarSpeed(-1.0, "invalid")
        raise AssertionError("负转频应被拒绝")
    except ValueError:
        pass


def test_nearby_order_bins_match_hand_calculation():
    fs, rot_freq, samples_per_rev = 8192.0, 16.0, 512
    time_s = np.arange(fs + 1) / fs  # 含末端共 16 转，FFT 阶次分辨率=1/16。
    signal = 0.6 * np.sin(2 * np.pi * 3.0 * rot_freq * time_s) + 0.4 * np.sin(
        2 * np.pi * 3.5 * rot_freq * time_s
    )
    result = ConstantSpeedOrderPipeline(
        OrderParameters(samples_per_revolution=samples_per_rev, max_order=10),
    ).run(signal, fs, ScalarSpeed(rot_freq, "test_known"))
    assert np.isclose(result.spectrum.order_resolution, 1 / 16)
    for expected_order, expected_amplitude in ((3.0, 0.6), (3.5, 0.4)):
        order, amplitude = _amplitude_at(result.spectrum, expected_order)
        assert np.isclose(order, expected_order, atol=1e-12)
        assert np.isclose(amplitude, expected_amplitude, atol=0.015), (order, amplitude)


def test_phase_integration_uses_analytic_integral():
    time_s = np.linspace(0, 2, 2001)
    speed_hz = 10 + 2 * time_s
    phase = integrate_speed_trajectory(
        SpeedTrajectory(time_s, speed_hz, "test_formula")
    )
    expected_revolutions = 10 * time_s + time_s**2
    assert np.allclose(phase.revolutions, expected_revolutions, atol=1e-12)
    assert np.allclose(phase.phase_rad, 2 * np.pi * expected_revolutions, atol=1e-11)


def test_fast_triangular_sweep_tracks_speed_phase_and_orders():
    fs, duration = 8192.0, 8.0
    time_s = np.arange(int(fs * duration)) / fs
    speed_hz = _triangle_speed(time_s)
    revolutions = _triangle_revolutions(time_s)
    rng = np.random.default_rng(20261108)
    signal = (
        np.sin(2 * np.pi * revolutions)
        + 0.5 * np.sin(2 * np.pi * 3.5 * revolutions)
        + 0.01 * rng.standard_normal(len(time_s))
    )
    result = FastVaryingSpeedOrderPipeline(
        OrderParameters(samples_per_revolution=512, max_order=10),
        SpeedSearchRange(8, 42),
    ).run(signal, fs)
    assert result.status == "valid", result.reason
    assert isinstance(result.speed, SpeedTrajectory)
    assert result.phase is not None and result.angle_domain is not None
    assert result.speed.stft_window_samples > 512
    speed_error = np.abs(result.speed.frequency_hz - speed_hz)
    assert np.percentile(speed_error, 90) < 1.0, np.percentile(speed_error, 90)
    # 首尾也纳入：轨迹积分必须逼近解析累计转数，不能只验证中段谱形。
    phase_error = np.abs(result.phase.revolutions - revolutions)
    assert np.max(phase_error) < 0.25, np.max(phase_error)
    assert abs(result.phase.revolutions[-1] - revolutions[-1]) < 0.25
    for expected_order, minimum_amplitude in ((1.0, 0.75), (3.5, 0.30)):
        order, amplitude = _amplitude_at(result.spectrum, expected_order)
        assert abs(order - expected_order) <= result.spectrum.order_resolution
        assert amplitude > minimum_amplitude, (expected_order, order, amplitude)


def test_single_frame_cannot_claim_slow_cv_and_uses_fast_double_order():
    fs = 8192.0
    time_s = np.arange(int(fs)) / fs
    speed_hz = 12.0 + 12.0 * time_s
    revolutions = _linear_revolutions(time_s, 12.0, 12.0)
    signal = np.sin(2 * np.pi * revolutions) + 0.6 * np.sin(2 * np.pi * 2 * revolutions)
    result = AutomaticOrderPipeline(
        OrderParameters(samples_per_revolution=256, max_order=8),
        search=SpeedSearchRange(8, 42),
    ).run(signal, fs)
    assert result.status == "valid", result.reason
    assert result.tracking_method == "varying_speed"
    assert np.max(np.abs(result.phase.revolutions - revolutions)) < 0.20
    assert np.max(np.abs(result.speed.frequency_hz - speed_hz)) < 1.0
    for order, minimum in ((1.0, 0.75), (2.0, 0.35)):
        _, amplitude = _amplitude_at(result.spectrum, order)
        assert amplitude > minimum, (order, amplitude)


def test_stft_sustained_search_range_exit_is_indeterminate():
    fs = 8192.0
    time_s = np.arange(int(fs * 2)) / fs
    revolutions = _linear_revolutions(time_s, 12.0, 24.0)  # 12→60Hz，后段超过42Hz。
    signal = np.sin(2 * np.pi * revolutions)
    result = FastVaryingSpeedOrderPipeline(
        OrderParameters(samples_per_revolution=128, max_order=8),
        SpeedSearchRange(8, 42),
    ).run(signal, fs)
    assert result.status == "indeterminate"
    assert result.spectrum is None
    assert "边界" in result.reason or "越出" in result.reason


def test_zero_mad_still_rejects_true_outlier():
    frequencies = np.array([20.0, 20.0, 20.0, 20.0, 40.0])
    retained = select_retained_speed_frames(
        frequencies,
        np.ones(5, dtype=bool),
        FrameParameters(),
    )
    assert retained.tolist() == [True, True, True, True, False]


def test_narrow_band_pure_tone_is_reliable_at_both_sample_rates():
    for fs in (8192.0, 25600.0):
        time_s = np.arange(int(fs * 2)) / fs
        signal = np.sin(2 * np.pi * 20 * time_s)
        result = FastVaryingSpeedOrderPipeline(
            OrderParameters(samples_per_revolution=128, max_order=5),
            SpeedSearchRange(15, 25),
        ).run(signal, fs)
        assert result.status == "valid", (fs, result.reason)
        assert np.max(np.abs(result.speed.frequency_hz - 20.0)) < 0.05
        expected_revolutions = 20.0 * time_s
        assert np.max(np.abs(result.phase.revolutions - expected_revolutions)) < 0.02


def test_near_boundary_but_inside_search_range_remains_valid():
    fs = 8192.0
    time_s = np.arange(int(fs)) / fs  # 末端真值 24.99939Hz，仍在 [15,25] 内。
    speed_hz = 20.0 + 5.0 * time_s
    revolutions = _linear_revolutions(time_s, 20.0, 5.0)
    signal = np.sin(2 * np.pi * revolutions)
    result = FastVaryingSpeedOrderPipeline(
        OrderParameters(samples_per_revolution=128, max_order=5),
        SpeedSearchRange(15, 25),
    ).run(signal, fs)
    assert result.status == "valid", result.reason
    assert np.max(np.abs(result.phase.revolutions - revolutions)) < 0.20


def test_edge_outside_run_uses_sample_count_and_rejects_long_or_internal():
    time_s = np.arange(100) / 100.0
    stft_times = np.array([0.5, 0.75])
    frequency = np.full(100, 20.0)
    frequency[:20] = 14.0
    assert (
        _speed_range_violation(
            frequency,
            time_s,
            stft_times,
            SpeedSearchRange(15, 25),
            maximum_edge_outside_samples=25,
        )
        is None
    )
    frequency[:30] = 14.0
    assert "边缘长时间" in _speed_range_violation(
        frequency,
        time_s,
        stft_times,
        SpeedSearchRange(15, 25),
        maximum_edge_outside_samples=25,
    )
    frequency = np.full(100, 20.0)
    frequency[60] = 30.0
    assert "记录内部" in _speed_range_violation(
        frequency,
        time_s,
        np.array([0.25, 0.75]),
        SpeedSearchRange(15, 25),
        maximum_edge_outside_samples=25,
    )

    # 实际 STFT 信号：只在首尾 0.1 秒短边缘略越界，不能按两个采样点误拒。
    fs = 8192.0
    time_s = np.arange(int(fs)) / fs
    revolutions = _linear_revolutions(time_s, 14.9, 10.2)
    signal = np.sin(2 * np.pi * revolutions)
    result = FastVaryingSpeedOrderPipeline(
        OrderParameters(samples_per_revolution=128, max_order=5),
        SpeedSearchRange(15, 25),
    ).run(signal, fs)
    assert result.status == "valid", result.reason


def test_slow_failure_still_attempts_fast_pipeline():
    fs = 8192.0
    time_s = np.arange(int(fs)) / fs
    revolutions = _linear_revolutions(time_s, 12.0, 24.0)  # 1秒12→36Hz。
    signal = np.sin(2 * np.pi * revolutions) + 0.4 * np.sin(2 * np.pi * 2 * revolutions)

    class FailedSlowPipeline:
        def run(self, signal, sample_rate_hz, estimation_signal=None):
            speed = ScalarSpeed.indeterminate("test_slow_failure", "测试强制 slow 失败")
            return OrderAnalysis.failed("multi_frame", speed, "测试强制 slow 失败")

    pipeline = AutomaticOrderPipeline(
        OrderParameters(samples_per_revolution=256, max_order=8),
        search=SpeedSearchRange(8, 42),
    )
    pipeline.slow_pipeline = FailedSlowPipeline()
    result = pipeline.run(signal, fs)
    assert result.status == "valid", result.reason
    assert result.tracking_method == "varying_speed"
    assert np.max(np.abs(result.phase.revolutions - revolutions)) < 0.25


def test_multi_frame_near_zero_mad_keeps_normal_small_changes():
    fs = 8192.0
    frame_count, frame_duration = 5, 1.0
    # 每帧只有 0.001 Hz 的确定性差异，MAD 可近零，但这些帧全部正常。
    sections = []
    for index in range(frame_count):
        time_s = np.arange(int(fs * frame_duration)) / fs
        frequency = 20.0 + index * 0.001
        sections.append(np.sin(2 * np.pi * frequency * time_s))
    signal = np.concatenate(sections)
    result = SlowVaryingSpeedOrderPipeline(
        OrderParameters(samples_per_revolution=256, max_order=10),
        FrameParameters(frame_duration_s=1.0, overlap=0.0),
        SpeedSearchRange(15, 25),
    ).run(signal, fs)
    assert result.status == "valid", result.reason
    assert isinstance(result.speed, LocalSpeedEstimates)
    assert np.all(result.speed.retained_mask == result.speed.reliable_mask)
    assert np.all(result.speed.retained_mask)
    assert result.phase is None and result.angle_domain is None
    assert np.isclose(result.spectrum.order_resolution, 1 / result.speed.median_hz)


def test_indeterminate_never_becomes_normal_spectrum():
    fs = 8192.0
    zeros = np.zeros(int(fs * 2))
    automatic = AutomaticOrderPipeline(
        OrderParameters(samples_per_revolution=128, max_order=20),
        search=SpeedSearchRange(10, 50),
    ).run(zeros, fs)
    assert automatic.status == "indeterminate"
    assert automatic.spectrum is None
    rng = np.random.default_rng(9)
    noise = rng.standard_normal(int(fs * 2))
    fast = FastVaryingSpeedOrderPipeline(
        OrderParameters(samples_per_revolution=128, max_order=20),
        SpeedSearchRange(10, 50),
    ).run(noise, fs)
    assert fast.status == "indeterminate"
    assert fast.spectrum is None
    assert fast.reason


def test_automatic_fast_failure_does_not_return_slow_spectrum():
    fs = 8192.0
    time_s = np.arange(int(fs * 6)) / fs
    speed_hz = _triangle_speed(time_s)
    revolutions = _triangle_revolutions(time_s)
    signal = np.sin(2 * np.pi * revolutions)

    class FailedFastPipeline:
        def run(self, signal, sample_rate_hz, estimation_signal=None):
            speed = ScalarSpeed.indeterminate("test_no_ridge", "测试强制无可靠脊线")
            return OrderAnalysis.failed("varying_speed", speed, "测试强制无可靠脊线")

    pipeline = AutomaticOrderPipeline(
        OrderParameters(samples_per_revolution=128, max_order=10),
        search=SpeedSearchRange(8, 42),
    )
    pipeline.fast_pipeline = FailedFastPipeline()
    result = pipeline.run(signal, fs)
    assert result.status == "indeterminate"
    assert result.tracking_method == "varying_speed"
    assert result.spectrum is None
    assert "测试强制无可靠脊线" in result.reason


def test_stft_resolution_depends_on_sample_rate_not_fixed_512():
    parameters = RidgeParameters(
        target_frequency_resolution_hz=0.5,
        maximum_window_duration_s=0.5,
    )
    for fs, expected_window in ((8192.0, 4096), (25600.0, 12800)):
        window, hop = resolve_stft_window_samples(int(fs * 4), fs, parameters)
        assert window == expected_window
        assert np.isclose(fs / window, 2.0)
        assert hop == int(round(window * (1 - parameters.overlap)))


def test_bearing_fault_modulation_is_not_mistaken_for_shaft_speed():
    np.random.seed(7)
    signal, fs, truth = bearing_outer_race(
        bpfo=90.0,
        rot_freq=25.0,
        duration=3.0,
        fs=8192,
        snr_db=15,
    )
    result = AutomaticOrderPipeline(
        OrderParameters(samples_per_revolution=256, max_order=20),
        search=SpeedSearchRange(10, 100),
    ).run(signal, fs)
    assert result.status == "valid", result.reason
    assert result.tracking_method == "multi_frame"
    assert abs(result.speed.median_hz - truth["rot_freq"]) < 1.0, (
        result.speed.frequency_hz
    )


def test_estimation_signal_is_separate_from_fault_enhancement():
    fs = 8192.0
    time_s = np.arange(fs * 2) / fs
    raw = np.sin(2 * np.pi * 20 * time_s)
    enhanced = np.zeros_like(raw)
    result = AutomaticOrderPipeline(
        OrderParameters(samples_per_revolution=128, max_order=10),
        search=SpeedSearchRange(15, 25),
    ).run(enhanced, fs, estimation_signal=raw)
    assert result.status == "valid"
    assert np.isclose(result.speed.median_hz, 20.0, atol=0.03)
    assert np.allclose(result.spectrum.amplitude, 0.0)


def run_all_tests():
    tests = [
        test_constant_speed_axis_and_single_sided_amplitude,
        test_nearby_order_bins_match_hand_calculation,
        test_phase_integration_uses_analytic_integral,
        test_fast_triangular_sweep_tracks_speed_phase_and_orders,
        test_single_frame_cannot_claim_slow_cv_and_uses_fast_double_order,
        test_stft_sustained_search_range_exit_is_indeterminate,
        test_zero_mad_still_rejects_true_outlier,
        test_narrow_band_pure_tone_is_reliable_at_both_sample_rates,
        test_near_boundary_but_inside_search_range_remains_valid,
        test_edge_outside_run_uses_sample_count_and_rejects_long_or_internal,
        test_slow_failure_still_attempts_fast_pipeline,
        test_multi_frame_near_zero_mad_keeps_normal_small_changes,
        test_indeterminate_never_becomes_normal_spectrum,
        test_automatic_fast_failure_does_not_return_slow_spectrum,
        test_stft_resolution_depends_on_sample_rate_not_fixed_512,
        test_bearing_fault_modulation_is_not_mistaken_for_shaft_speed,
        test_estimation_signal_is_separate_from_fault_enhancement,
    ]
    for test in tests:
        test()
        print(f"  [PASS] {test.__name__}")
    print(f"order pipeline: {len(tests)} tests passed")


if __name__ == "__main__":
    run_all_tests()
