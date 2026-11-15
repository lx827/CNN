"""恒速、缓变与快速变速阶次分析的独立 Pipeline。"""

from __future__ import annotations

from cnn_compute import rotation as native

from typing import Optional

import numpy as np
from numpy.typing import NDArray

from .estimation import estimate_spectrum_speed, estimate_stft_speed_trajectory
from .resampling import (
    compute_order_spectrum,
    integrate_speed_trajectory,
    resample_constant_speed,
    resample_to_phase,
)
from .types import (
    FrameParameters,
    LocalSpeedEstimates,
    OrderAnalysis,
    OrderParameters,
    OrderSpectrum,
    RidgeParameters,
    ScalarSpeed,
    SpeedSearchRange,
)


FloatArray = NDArray[np.float64]


def select_retained_speed_frames(
    frequencies_hz: FloatArray,
    reliable_mask: NDArray[np.bool_],
    parameters: FrameParameters = FrameParameters(),
) -> NDArray[np.bool_]:
    """用带正下限的 MAD 容差选择帧；MAD=0 时仍能排除真正离群值。"""
    frequencies = np.asarray(frequencies_hz, dtype=np.float64)
    reliable = np.asarray(reliable_mask, dtype=bool)
    if frequencies.ndim != 1 or reliable.ndim != 1 or len(frequencies) != len(reliable):
        raise ValueError("局部转频与可靠掩码必须是一维等长数组")
    retained = reliable.copy()
    if not np.any(reliable):
        return retained
    reliable_frequencies = frequencies[reliable]
    if not np.all(np.isfinite(reliable_frequencies)) or np.any(
        reliable_frequencies <= 0
    ):
        raise ValueError("可靠局部转频必须是有限正数")
    median = float(np.median(reliable_frequencies))
    mad = float(np.median(np.abs(reliable_frequencies - median)))
    tolerance = max(
        parameters.mad_threshold * mad,
        parameters.relative_mad_floor * abs(median),
        parameters.absolute_mad_floor_hz,
    )
    retained[reliable] = np.abs(reliable_frequencies - median) <= tolerance
    return retained


class ConstantSpeedOrderPipeline:
    """已知准确标量转频的无 tach 恒速阶次分析。"""

    def __init__(self, parameters: OrderParameters = OrderParameters()) -> None:
        self.parameters = parameters

    def run(
        self,
        signal: FloatArray,
        sample_rate_hz: float,
        speed: ScalarSpeed,
    ) -> OrderAnalysis:
        if speed.status != "valid":
            return OrderAnalysis.failed(
                "single_frame", speed, speed.reason or "标量转频不可判定"
            )
        angle_domain, phase = resample_constant_speed(
            signal,
            sample_rate_hz,
            speed,
            self.parameters.samples_per_revolution,
        )
        spectrum = compute_order_spectrum(angle_domain, self.parameters.max_order)
        return OrderAnalysis(
            status="valid",
            tracking_method="single_frame",
            speed=speed,
            spectrum=spectrum,
            phase=phase,
            angle_domain=angle_domain,
        )


class SlowVaryingSpeedOrderPipeline:
    """分帧标量估计、MAD 异常帧处理和各帧角域单边幅值谱平均。"""

    def __init__(
        self,
        parameters: OrderParameters = OrderParameters(),
        frame_parameters: FrameParameters = FrameParameters(),
        search: SpeedSearchRange = SpeedSearchRange(),
    ) -> None:
        self.parameters = parameters
        self.frame_parameters = frame_parameters
        self.search = search

    def run(
        self,
        signal: FloatArray,
        sample_rate_hz: float,
        estimation_signal: Optional[FloatArray] = None,
    ) -> OrderAnalysis:
        arr = np.asarray(signal, dtype=np.float64)
        estimation_arr = (
            arr
            if estimation_signal is None
            else np.asarray(estimation_signal, dtype=np.float64)
        )
        if arr.ndim != 1 or estimation_arr.ndim != 1 or len(arr) != len(estimation_arr):
            raise ValueError("阶次信号与转速估计信号必须是一维等长数组")
        if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
            raise ValueError("采样率必须是有限正数")
        frame_length = max(
            1, int(round(self.frame_parameters.frame_duration_s * sample_rate_hz))
        )
        if frame_length >= len(arr):
            starts = np.array([0], dtype=int)
            frame_length = len(arr)
        else:
            hop = max(
                1, int(round(frame_length * (1.0 - self.frame_parameters.overlap)))
            )
            starts = np.arange(0, len(arr) - frame_length + 1, hop, dtype=int)

        frequencies = np.full(len(starts), np.nan, dtype=np.float64)
        reliable = np.zeros(len(starts), dtype=bool)
        for index, start in enumerate(starts):
            estimate = estimate_spectrum_speed(
                estimation_arr[start : start + frame_length],
                sample_rate_hz,
                self.search,
            )
            if estimate.status == "valid":
                frequencies[index] = float(estimate.frequency_hz)
                reliable[index] = True

        retained = select_retained_speed_frames(
            frequencies,
            reliable,
            self.frame_parameters,
        )

        spectra: list[OrderSpectrum] = []
        retained_indices: list[int] = []
        for index in np.flatnonzero(retained):
            start = int(starts[index])
            speed = ScalarSpeed(float(frequencies[index]), "frame_spectrum")
            try:
                angle_domain, _ = resample_constant_speed(
                    arr[start : start + frame_length],
                    sample_rate_hz,
                    speed,
                    self.parameters.samples_per_revolution,
                )
                spectrum = compute_order_spectrum(
                    angle_domain, self.parameters.max_order
                )
            except ValueError:
                retained[index] = False
                continue
            spectra.append(spectrum)
            retained_indices.append(int(index))

        local_speeds = self._local_speeds(
            starts, frame_length, sample_rate_hz, frequencies, reliable, retained
        )
        if not spectra:
            return OrderAnalysis.failed(
                "multi_frame", local_speeds, "可靠帧的转数不足以形成阶次谱"
            )
        resolution = 1.0 / ((frame_length / sample_rate_hz) * local_speeds.median_hz)
        point_count = int(np.floor(self.parameters.max_order / resolution)) + 1
        common_orders = np.arange(point_count, dtype=np.float64) * resolution
        interpolated = [
            native.interpolate(spectrum.order_bins, spectrum.amplitude, common_orders, zero_outside=True)
            for spectrum in spectra
        ]
        average = np.mean(np.asarray(interpolated), axis=0)
        averaged_spectrum = OrderSpectrum(
            order_bins=common_orders,
            amplitude=average,
            order_resolution=float(resolution),
            samples_per_revolution=self.parameters.samples_per_revolution,
            total_revolutions=float(
                np.mean([spectrum.total_revolutions for spectrum in spectra])
            ),
        )
        return OrderAnalysis(
            status="valid",
            tracking_method="multi_frame",
            speed=local_speeds,
            spectrum=averaged_spectrum,
        )

    @staticmethod
    def _local_speeds(
        starts: NDArray[np.int_],
        frame_length: int,
        sample_rate_hz: float,
        frequencies: FloatArray,
        reliable: NDArray[np.bool_],
        retained: NDArray[np.bool_],
    ) -> LocalSpeedEstimates:
        start_s = starts.astype(np.float64) / sample_rate_hz
        return LocalSpeedEstimates(
            frame_start_s=start_s,
            frame_time_s=start_s + frame_length / (2.0 * sample_rate_hz),
            frequency_hz=frequencies,
            reliable_mask=reliable,
            retained_mask=retained,
        )


class FastVaryingSpeedOrderPipeline:
    """STFT 脊线 → 连续转速 → 梯形积分相位 → 等相位重采样。"""

    def __init__(
        self,
        parameters: OrderParameters = OrderParameters(),
        search: SpeedSearchRange = SpeedSearchRange(),
        ridge_parameters: RidgeParameters = RidgeParameters(),
    ) -> None:
        self.parameters = parameters
        self.search = search
        self.ridge_parameters = ridge_parameters

    def run(
        self,
        signal: FloatArray,
        sample_rate_hz: float,
        estimation_signal: Optional[FloatArray] = None,
    ) -> OrderAnalysis:
        arr = np.asarray(signal, dtype=np.float64)
        estimation_arr = (
            arr
            if estimation_signal is None
            else np.asarray(estimation_signal, dtype=np.float64)
        )
        if arr.ndim != 1 or estimation_arr.ndim != 1 or len(arr) != len(estimation_arr):
            raise ValueError("阶次信号与转速估计信号必须是一维等长数组")
        estimate = estimate_stft_speed_trajectory(
            estimation_arr,
            sample_rate_hz,
            self.search,
            self.ridge_parameters,
        )
        if estimate.status != "valid" or estimate.trajectory is None:
            return OrderAnalysis.failed(
                "varying_speed",
                ScalarSpeed.indeterminate(
                    "stft_ridge", estimate.reason or "转速轨迹不可判定"
                ),
                estimate.reason or "转速轨迹不可判定",
            )
        phase = integrate_speed_trajectory(estimate.trajectory)
        try:
            angle_domain = resample_to_phase(
                arr,
                phase,
                self.parameters.samples_per_revolution,
            )
            spectrum = compute_order_spectrum(angle_domain, self.parameters.max_order)
        except ValueError as exc:
            return OrderAnalysis.failed("varying_speed", estimate.trajectory, str(exc))
        return OrderAnalysis(
            status="valid",
            tracking_method="varying_speed",
            speed=estimate.trajectory,
            spectrum=spectrum,
            phase=phase,
            angle_domain=angle_domain,
        )


class AutomaticOrderPipeline:
    """先判别局部转速变化；快速变速失败时不得静默退回多帧正常结果。"""

    def __init__(
        self,
        parameters: OrderParameters = OrderParameters(),
        frame_parameters: FrameParameters = FrameParameters(),
        search: SpeedSearchRange = SpeedSearchRange(),
        ridge_parameters: RidgeParameters = RidgeParameters(),
    ) -> None:
        self.slow_pipeline = SlowVaryingSpeedOrderPipeline(
            parameters, frame_parameters, search
        )
        self.fast_pipeline = FastVaryingSpeedOrderPipeline(
            parameters, search, ridge_parameters
        )
        self.varying_speed_cv_threshold = frame_parameters.varying_speed_cv_threshold

    def run(
        self,
        signal: FloatArray,
        sample_rate_hz: float,
        estimation_signal: Optional[FloatArray] = None,
    ) -> OrderAnalysis:
        slow = self.slow_pipeline.run(signal, sample_rate_hz, estimation_signal)
        needs_fast = slow.status != "valid" or not isinstance(
            slow.speed, LocalSpeedEstimates
        )
        if not needs_fast:
            retained_count = int(np.sum(slow.speed.retained_mask))
            # 少于两个有效局部估计时无法判断 CV，不能拿 std=0 冒充恒速/缓变。
            needs_fast = retained_count < 2
        if not needs_fast:
            median = slow.speed.median_hz
            needs_fast = (
                median <= 0
                or slow.speed.std_hz / median > self.varying_speed_cv_threshold
            )
        if not needs_fast:
            return slow

        fast = self.fast_pipeline.run(signal, sample_rate_hz, estimation_signal)
        if fast.status != "valid":
            reason = "慢速估计不足或检测到快速变速"
            if slow.status == "valid" and isinstance(slow.speed, LocalSpeedEstimates):
                reason = "局部转频不足以确认缓变或检测到快速变速"
            return OrderAnalysis.failed(
                "varying_speed",
                slow.speed,
                f"{reason}，但连续转速轨迹不可判定: {fast.reason}",
            )
        return fast
