"""带明确窗函数、单位和单边刻度的实信号 FFT。"""
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.fft import rfft, rfftfreq
from scipy.signal import windows


FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class FourierSpectrum:
    """同一 FFT 的峰值幅值与均方功率表示，数组不在算法层序列化。"""

    frequency_hz: FloatArray
    amplitude: FloatArray
    power: FloatArray
    amplitude_unit: str = "input_signal"
    power_unit: str = "input_signal^2"
    window: str = "periodic_hann"
    amplitude_scaling: str = "single_sided_peak_amplitude"
    power_scaling: str = "single_sided_mean_square"

    def __post_init__(self) -> None:
        if self.frequency_hz.ndim != 1 or self.amplitude.ndim != 1 or self.power.ndim != 1:
            raise ValueError("频谱频率轴、幅值和功率必须是一维数组")
        if not (len(self.frequency_hz) == len(self.amplitude) == len(self.power)):
            raise ValueError("频谱频率轴、幅值和功率长度必须一致")
        if len(self.frequency_hz) == 0:
            raise ValueError("频谱不能为空")
        if not all(np.all(np.isfinite(values)) for values in (
            self.frequency_hz, self.amplitude, self.power,
        )):
            raise ValueError("频谱不能包含 NaN 或无穷值")
        if np.any(self.amplitude < 0) or np.any(self.power < 0):
            raise ValueError("频谱幅值和功率不能为负数")

    def truncated(self, max_frequency_hz: float) -> "FourierSpectrum":
        """仅截取表示，不重算 FFT；调用方不能用展示截断替代全长分析。"""
        if not np.isfinite(max_frequency_hz) or max_frequency_hz <= 0:
            raise ValueError("最大频率必须是有限正数")
        mask = self.frequency_hz <= max_frequency_hz
        if not np.any(mask):
            raise ValueError("最大频率低于频谱第一个频率点")
        return FourierSpectrum(
            frequency_hz=self.frequency_hz[mask],
            amplitude=self.amplitude[mask],
            power=self.power[mask],
            amplitude_unit=self.amplitude_unit,
            power_unit=self.power_unit,
        )


def compute_spectrum(
    signal: FloatArray,
    sample_rate_hz: float,
    *,
    remove_mean: bool = True,
    amplitude_unit: str = "input_signal",
) -> FourierSpectrum:
    """周期 Hann 相干增益补偿，返回单边峰值幅值及对应均方功率。

    正弦 A·sin(ωt) 的非 DC/Nyquist bin 幅值为 A、功率为 A²/2；
    DC 的幅值为 |C|、功率为 C²，偶数点 Nyquist 的幅值为 A、功率为 A²。
    这里的 power 是各频 bin 的均方功率，不是按 Hz 归一化的 PSD。
    """
    values = np.asarray(signal, dtype=np.float64)
    if values.ndim != 1 or len(values) < 2:
        raise ValueError("FFT 输入必须是一维且至少包含 2 个采样点")
    if not np.all(np.isfinite(values)):
        raise ValueError("输入信号不能包含 NaN 或无穷值")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("采样率必须是有限正数")

    centered = values - np.mean(values) if remove_mean else values
    window = windows.hann(len(centered), sym=False)
    coherent_gain = float(np.sum(window))
    if coherent_gain <= 0:
        raise ValueError("输入信号过短，无法形成有效 Hann 窗")

    transformed = np.abs(rfft(centered * window)) * (2.0 / coherent_gain)
    amplitude = transformed
    amplitude[0] *= 0.5
    if len(centered) % 2 == 0:
        amplitude[-1] *= 0.5

    power = amplitude**2 / 2.0
    power[0] = amplitude[0] ** 2
    if len(centered) % 2 == 0:
        power[-1] = amplitude[-1] ** 2
    frequency = np.asarray(
        rfftfreq(len(centered), 1.0 / sample_rate_hz), dtype=np.float64,
    )
    return FourierSpectrum(
        frequency_hz=frequency,
        amplitude=amplitude,
        power=power,
        amplitude_unit=amplitude_unit,
        power_unit=f"{amplitude_unit}^2",
    )
