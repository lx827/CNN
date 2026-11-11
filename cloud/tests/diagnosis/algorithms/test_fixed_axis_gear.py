"""定轴齿轮算法的独立数学与合成信号回归。"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.algorithms.gear.fixed_axis import (
    CARParameters,
    CepstrumRepresentation,
    TrendHistory,
    TSAParameters,
    ZoomParameters,
    analyze_fixed_axis_sidebands,
    compute_car,
    compute_fm0,
    compute_na4,
    compute_nb4,
    compute_real_cepstrum,
    compute_synchronous_average,
    compute_tsa_representation,
    compute_zoom_spectrum,
    standardized_moment,
)
from app.algorithms.mechanics import FixedAxisGearGeometry
from app.algorithms.order import (
    AngleDomainSignal,
    LocalSpeedEstimates,
    OrderAnalysis,
    OrderSpectrum,
    ScalarSpeed,
)
from app.algorithms.pipelines.gear.fixed_axis import FixedAxisGearPipeline


def _cycle_representation(include_other=True):
    spr = 64
    revolutions = 8
    angle = np.arange(spr * revolutions, dtype=np.float64) / spr
    phase = 2 * np.pi * np.arange(spr) / spr
    mesh = np.sin(4 * phase) + 0.5 * np.cos(8 * phase)
    sidebands = (
        0.2 * np.sin(3 * phase) + 0.3 * np.cos(5 * phase)
        + 0.1 * np.sin(7 * phase) + 0.1 * np.cos(9 * phase)
    )
    other = 0.4 * np.sin(2 * phase) if include_other else 0.0
    asynchronous = 0.25 * np.sin(2 * np.pi * 2.5 * angle)
    signal = np.tile(mesh + sidebands + other, revolutions) + asynchronous
    synchronous = compute_synchronous_average(AngleDomainSignal(angle, signal, spr), 4)
    return synchronous, mesh, sidebands, other


def test_tsa_components_and_invalid_conditions():
    synchronous, mesh, sidebands, other = _cycle_representation()
    # 非整数转周期成分经算术 TSA 消除，本轴周期成分完整保留。
    assert np.allclose(synchronous.tsa_cycle, mesh + sidebands + other, atol=1e-12)
    assert np.allclose(synchronous.nonsynchronous_signal,
                       synchronous.angle_domain.samples - synchronous.tsa_signal)
    tsa = compute_tsa_representation(synchronous, 4, mesh_harmonics=2, max_order=20)
    expected_mesh = np.tile(mesh, synchronous.revolutions)
    expected_sidebands = np.tile(sidebands, synchronous.revolutions)
    expected_residual = np.tile(other, synchronous.revolutions)
    assert np.allclose(tsa.mesh_signal, expected_mesh, atol=1e-12)
    assert np.allclose(tsa.differential_signal, expected_sidebands, atol=1e-12)
    assert np.allclose(tsa.residual_signal, expected_residual, atol=1e-12)
    assert np.allclose(tsa.regular_signal + tsa.residual_signal, tsa.synchronous.tsa_signal)
    assert np.allclose(tsa.mesh_signal + tsa.differential_signal, tsa.regular_signal)

    short = AngleDomainSignal(np.arange(64) / 64, np.zeros(64), 64)
    try:
        compute_synchronous_average(short, 2)
        raise AssertionError("少转数 TSA 必须失败")
    except ValueError:
        pass
    try:
        compute_tsa_representation(synchronous, 4.5, max_order=20)
        raise AssertionError("非整数定轴啮合阶次不能构造单转 regular")
    except ValueError:
        pass


def test_constant_speed_pipeline_uses_real_angle_domain():
    fs = 2048.0
    rot = 16.0
    t = np.arange(int(fs * 2.0)) / fs
    signal = np.sin(2 * np.pi * 4 * rot * t) + 0.2 * np.sin(2 * np.pi * 3 * rot * t)
    pipeline = FixedAxisGearPipeline(
        FixedAxisGearGeometry(4),
        tsa_parameters=TSAParameters(samples_per_revolution=64, max_order=20),
        n_sidebands=2,
    )
    diagnosis = pipeline.run(signal, fs, speed=ScalarSpeed(rot, "test"), include_tsa=True)
    assert diagnosis.analysis.tsa is not None
    assert diagnosis.analysis.tsa.synchronous.revolutions == 31
    assert diagnosis.analysis.tsa.synchronous.angle_domain.samples_per_revolution == 64
    assert diagnosis.analysis.fm0.status == "evaluated"
    assert diagnosis.analysis.sideband_analysis.ser.status == "evaluated"


def test_fm0_and_standardized_moments_manual_values():
    synchronous, _, _, _ = _cycle_representation(include_other=False)
    # 只保留 4/8/12 阶，幅值分别 1、0.5、0.25；regular 不需要边带。
    spr = synchronous.angle_domain.samples_per_revolution
    angle = synchronous.angle_domain.angle_revolutions
    signal = (
        np.sin(2 * np.pi * 4 * angle)
        + 0.5 * np.cos(2 * np.pi * 8 * angle)
        + 0.25 * np.sin(2 * np.pi * 12 * angle)
        + 0.2 * np.sin(2 * np.pi * 3 * angle)
    )
    synchronous = compute_synchronous_average(AngleDomainSignal(angle, signal, spr), 4)
    tsa = compute_tsa_representation(
        synchronous, 4, mesh_harmonics=3, regular_sideband_order=0, max_order=20,
    )
    fm0 = compute_fm0(tsa)
    expected = np.ptp(signal) / 1.75
    assert fm0.status == "evaluated" and np.isclose(fm0.value, expected, atol=1e-10)

    values = np.array([-2.0, -1.0, 0.0, 1.0, 2.0, 4.0, -3.0, 0.5])
    centered = values - values.mean()
    for order, name in ((4, "FM4"), (6, "M6A"), (8, "M8A")):
        n = len(values)
        expected_moment = (
            n ** (order // 2 - 1) * np.sum(centered**order)
            / np.sum(centered**2) ** (order // 2)
        )
        actual = standardized_moment(values, order, name)
        assert actual.status == "evaluated" and np.isclose(actual.value, expected_moment)
    assert standardized_moment(np.ones(16), 4, "FM4").status == "not_evaluable"


def test_na4_nb4_require_comparable_history():
    synchronous, _, _, _ = _cycle_representation()
    tsa = compute_tsa_representation(synchronous, 4, mesh_harmonics=2, max_order=20)
    assert compute_na4(tsa, None).status == "not_evaluable"
    assert compute_nb4(tsa, None).status == "not_evaluable"
    history = TrendHistory(
        64, 4, mesh_harmonics=2, regular_sideband_order=1, revolutions=8,
        residual_variances=(2.0, 4.0), envelope_variances=(1.0, 3.0),
    )
    na4 = compute_na4(tsa, history)
    centered = tsa.residual_signal - tsa.residual_signal.mean()
    expected_na4 = np.mean(centered**4) / 3.0**2
    assert na4.status == "evaluated" and np.isclose(na4.value, expected_na4)
    nb4 = compute_nb4(tsa, history)
    assert nb4.status == "evaluated" and np.isfinite(nb4.value)
    assert nb4.details["angular_sample_rate_points_per_revolution"] == 64
    assert nb4.details["mesh_center_order"] == 4
    assert nb4.details["bandpass_orders"] == [3.6, 4.4]
    wrong = TrendHistory(
        128, 4, mesh_harmonics=2, regular_sideband_order=1, revolutions=8,
        residual_variances=(2.0,), envelope_variances=(1.0,),
    )
    assert compute_na4(tsa, wrong).reason == "incompatible_residual_history_representation"
    assert compute_nb4(tsa, wrong).reason == "incompatible_envelope_history_representation"
    different_regular = TrendHistory(
        64, 4, mesh_harmonics=3, regular_sideband_order=0, revolutions=8,
        residual_variances=(2.0,), envelope_variances=(1.0,),
    )
    assert compute_na4(tsa, different_regular).status == "not_evaluable"
    assert compute_nb4(tsa, different_regular).status == "not_evaluable"
    different_sidebands = TrendHistory(
        64, 4, mesh_harmonics=2, regular_sideband_order=0, revolutions=8,
        residual_variances=(2.0,), envelope_variances=(1.0,),
    )
    assert compute_na4(tsa, different_sidebands).status == "not_evaluable"
    assert compute_nb4(tsa, different_sidebands).status == "not_evaluable"
    different_revolutions = TrendHistory(
        64, 4, mesh_harmonics=2, regular_sideband_order=1, revolutions=7,
        residual_variances=(2.0,), envelope_variances=(1.0,),
    )
    assert compute_na4(tsa, different_revolutions).status == "not_evaluable"
    assert compute_nb4(tsa, different_revolutions).status == "not_evaluable"


def test_car_quefrency_seconds_and_background_formula():
    quefrency = np.arange(501, dtype=np.float64) * 0.001
    amplitude = np.full(len(quefrency), 0.5)
    for target, peak in ((0.04, 4.0), (0.08, 6.0), (0.12, 8.0)):
        amplitude[np.argmin(np.abs(quefrency - target))] = peak
    cepstrum = CepstrumRepresentation(quefrency, amplitude, sample_rate_hz=1000.0)
    car = compute_car(cepstrum, 25.0, CARParameters(n_harmonics=3, tolerance_s=0.002))
    assert car.status == "evaluated" and np.isclose(car.value, 12.0)
    assert car.details["target_quefrencies_s"] == [0.04, 0.08, 0.12]
    assert car.details["tolerance_s"] == 0.002
    fs = 2000.0
    t = np.arange(4096) / fs
    periodic = np.sin(2 * np.pi * 25 * t) + 0.4 * np.sin(2 * np.pi * 50 * t)
    representation = compute_real_cepstrum(periodic, fs)
    assert np.isclose(representation.quefrency_s[1] - representation.quefrency_s[0], 1 / fs)
    assert compute_car(representation, 25.0).status == "evaluated"


def _manual_spectrum(max_order=20.0):
    resolution = 0.25
    orders = np.arange(0, max_order + resolution, resolution)
    amplitude = np.zeros(len(orders))
    def set_peak(order, value):
        amplitude[np.argmin(np.abs(orders - order))] = value
    set_peak(6, 2.0)
    set_peak(5, 0.5)
    set_peak(7, 0.25)
    set_peak(4, 1.0)
    set_peak(8, 0.75)
    return OrderSpectrum(orders, amplitude, resolution, 64, 8.0)


def test_ser_amplitude_ratio_nonoverlap_and_coverage():
    result = analyze_fixed_axis_sidebands(_manual_spectrum(), 6.0, n_sidebands=2)
    assert result.status == "evaluated"
    assert np.isclose(result.ser.value, 2.5 / 2.0)
    assert result.ser.details["ratio_semantics"] == "amplitude_sum_ratio_not_energy_ratio"
    assert result.ser.details["non_overlapping_windows"] is True
    overlap = analyze_fixed_axis_sidebands(
        _manual_spectrum(), 6.0, n_sidebands=2, sideband_half_width_order=0.5,
    )
    assert overlap.status == "not_evaluable"
    uncovered = analyze_fixed_axis_sidebands(_manual_spectrum(), 18.0, n_sidebands=3)
    assert uncovered.ser.reason == "requested_mesh_or_sidebands_above_order_coverage"


def test_chirp_z_close_peaks_and_frequency_axis():
    fs = 2048.0
    count = 8192
    t = np.arange(count) / fs
    signal = np.sin(2 * np.pi * 200.0 * t) + 0.8 * np.sin(2 * np.pi * 200.75 * t)
    zoom = compute_zoom_spectrum(signal, fs, ZoomParameters(200.5, 5.0, output_points=1001))
    frequency = zoom.spectrum.frequency_hz
    amplitude = zoom.spectrum.amplitude
    assert np.all(np.diff(frequency) > 0)
    assert np.isclose(frequency[0], 198.0) and frequency[-1] < 203.0
    assert np.isclose(zoom.rayleigh_resolution_hz, fs / count)
    assert zoom.frequency_step_hz < zoom.rayleigh_resolution_hz
    for target, expected_amplitude in ((200.0, 1.0), (200.75, 0.8)):
        mask = np.abs(frequency - target) < 0.15
        index = np.flatnonzero(mask)[np.argmax(amplitude[mask])]
        assert abs(frequency[index] - target) < 0.03
        assert np.isclose(amplitude[index], expected_amplitude, rtol=0.03)


def test_evaluation_reuses_metrics_without_fft():
    synchronous, _, _, _ = _cycle_representation()
    tsa = compute_tsa_representation(synchronous, 4, mesh_harmonics=2, max_order=20)
    spectrum = tsa.spectrum
    order = OrderAnalysis(
        status="valid",
        tracking_method="single_frame",
        speed=ScalarSpeed(10.0, "test"),
        spectrum=spectrum,
    )
    pipeline = FixedAxisGearPipeline(
        FixedAxisGearGeometry(4),
        tsa_parameters=TSAParameters(samples_per_revolution=64, max_order=20),
        n_sidebands=2,
    )
    analysis = pipeline.analyze(
        np.zeros(4096), 2048.0,
        order_analysis=OrderAnalysis(
            status="valid", tracking_method="single_frame", speed=order.speed,
            spectrum=spectrum, angle_domain=synchronous.angle_domain,
        ),
        include_tsa=True,
    )
    import app.algorithms.order.resampling as resampling
    original = resampling.rfft
    resampling.rfft = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("评估不得重算 FFT"))
    try:
        evaluation = pipeline.evaluate(analysis)
    finally:
        resampling.rfft = original
    assert evaluation.status == "evaluated"
    assert evaluation.indicators["m6a"]["warning"] is None
    assert evaluation.indicators["m8a"]["critical"] is None


def test_standard_high_teeth_does_not_require_tsa_harmonics():
    fs = 1024.0
    rot = 8.0
    t = np.arange(int(fs * 4) + 1) / fs
    signal = (
        np.sin(2 * np.pi * 40 * rot * t)
        + 0.3 * np.sin(2 * np.pi * 39 * rot * t)
        + 0.2 * np.sin(2 * np.pi * 41 * rot * t)
    )
    pipeline = FixedAxisGearPipeline(
        FixedAxisGearGeometry(40),
        tsa_parameters=TSAParameters(samples_per_revolution=128, max_order=50),
        n_sidebands=2,
    )
    diagnosis = pipeline.run(signal, fs, speed=ScalarSpeed(rot, "test"), include_tsa=False)
    assert diagnosis.analysis.sideband_analysis.ser.status == "evaluated"
    assert diagnosis.analysis.tsa_status == "not_requested"
    assert diagnosis.analysis.spectrum.order_bins[-1] < 64.0


def test_standard_non_integer_revolutions_cover_requested_sidebands():
    fs = 8192.0
    rot = 16.0
    t = np.arange(4096) / fs
    signal = (
        np.sin(2 * np.pi * 180 * rot * t)
        + 0.3 * np.sin(2 * np.pi * 174 * rot * t)
        + 0.2 * np.sin(2 * np.pi * 186 * rot * t)
    )
    pipeline = FixedAxisGearPipeline(FixedAxisGearGeometry(180), n_sidebands=6)
    diagnosis = pipeline.run(signal, fs, speed=ScalarSpeed(rot, "test"), include_tsa=False)
    spectrum = diagnosis.analysis.spectrum
    required_order = 186.25
    assert spectrum.order_bins[-1] >= required_order, (
        f"最外侧边带要求 {required_order} 阶，实际覆盖 {spectrum.order_bins[-1]} 阶，"
        f"阶次分辨率 {spectrum.order_resolution}"
    )
    assert diagnosis.analysis.sideband_analysis.ser.status == "evaluated"


def test_standard_other_non_integer_revolutions_cover_requested_sidebands():
    fs = 8192.0
    for sample_count, rot in ((5000, 16.0), (4096, 17.0)):
        t = np.arange(sample_count) / fs
        signal = (
            np.sin(2 * np.pi * 180 * rot * t)
            + 0.3 * np.sin(2 * np.pi * 174 * rot * t)
            + 0.2 * np.sin(2 * np.pi * 186 * rot * t)
        )
        pipeline = FixedAxisGearPipeline(FixedAxisGearGeometry(180), n_sidebands=6)
        diagnosis = pipeline.run(signal, fs, speed=ScalarSpeed(rot, "test"), include_tsa=False)
        spectrum = diagnosis.analysis.spectrum
        assert spectrum.order_bins[-1] >= 186.25, (
            f"样本数 {sample_count}、转频 {rot} Hz：实际覆盖 {spectrum.order_bins[-1]} 阶，"
            f"阶次分辨率 {spectrum.order_resolution}"
        )
        assert diagnosis.analysis.sideband_analysis.ser.status == "evaluated"


def test_zero_energy_statistics_and_evaluation_are_indeterminate():
    pipeline = FixedAxisGearPipeline(FixedAxisGearGeometry(18))
    diagnosis = pipeline.run(np.zeros(4096), 2048.0, speed=ScalarSpeed(16.0, "test"))
    assert diagnosis.analysis.order_statistics.status == "not_evaluable"
    assert diagnosis.analysis.order_statistics.peak_concentration is None
    assert diagnosis.analysis.order_statistics.kurtosis is None
    assert diagnosis.evaluation.status == "indeterminate"
    assert diagnosis.evaluation.indicators["order_kurtosis"]["warning"] is None


def test_multi_frame_spectrum_does_not_fake_tsa_or_car():
    spectrum = _manual_spectrum()
    speeds = LocalSpeedEstimates(
        frame_start_s=np.array([0.0, 0.5]),
        frame_time_s=np.array([0.25, 0.75]),
        frequency_hz=np.array([10.0, 10.2]),
        reliable_mask=np.array([True, True]),
        retained_mask=np.array([True, True]),
    )
    order = OrderAnalysis("valid", "multi_frame", speeds, spectrum)
    pipeline = FixedAxisGearPipeline(FixedAxisGearGeometry(4), n_sidebands=2)
    analysis = pipeline.analyze(np.zeros(4096), 2048.0, order_analysis=order, include_tsa=True)
    assert analysis.tsa is None
    assert analysis.tsa_reason == "tsa_requires_accurate_constant_speed_with_continuous_phase"
    assert analysis.fm4.status == "not_evaluable"
    assert analysis.fm4.reason == analysis.tsa_reason
    assert analysis.car.reason == "car_requires_accurate_constant_speed"


def main():
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"test_fixed_axis_gear: {len(tests)} passed")


if __name__ == "__main__":
    main()
