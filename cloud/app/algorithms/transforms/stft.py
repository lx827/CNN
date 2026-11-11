"""实信号 STFT 表示；时间轴为帧中心秒，频率轴为 Hz。"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.signal import stft as scipy_stft
from scipy.signal import windows


FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class STFTRepresentation:
    """幅值矩阵形状固定为 (frequency, time)，单位与输入信号一致。"""

    time_s: FloatArray
    frequency_hz: FloatArray
    amplitude: FloatArray
    amplitude_unit: str = "input_signal"
    window: str = "periodic_hann"
    scaling: str = "single_sided_peak_amplitude"
    boundary: str = "zeros"
    padded: bool = True

    def __post_init__(self) -> None:
        if (
            self.time_s.ndim != 1
            or self.frequency_hz.ndim != 1
            or self.amplitude.ndim != 2
        ):
            raise ValueError("STFT 时间/频率轴必须是一维，幅值必须是二维矩阵")
        expected = (len(self.frequency_hz), len(self.time_s))
        if self.amplitude.shape != expected:
            raise ValueError(f"STFT 幅值形状必须为 {expected}")
        if not all(
            np.all(np.isfinite(values))
            for values in (
                self.time_s,
                self.frequency_hz,
                self.amplitude,
            )
        ):
            raise ValueError("STFT 表示不能包含 NaN 或无穷值")
        if np.any(self.amplitude < 0):
            raise ValueError("STFT 幅值不能为负数")

    def amplitude_db(self, floor: float = 1e-10) -> FloatArray:
        """返回 20·log10(amplitude + floor)，不改变线性幅值表示。"""
        if not np.isfinite(floor) or floor <= 0:
            raise ValueError("dB 下限必须是有限正数")
        return 20.0 * np.log10(self.amplitude + floor)


def compute_stft(
    signal: FloatArray,
    sample_rate_hz: float,
    *,
    nperseg: int,
    noverlap: int,
    nfft: int,
    amplitude_unit: str = "input_signal",
) -> STFTRepresentation:
    """用 SciPy STFT 计算周期 Hann 单边峰值幅值，显式保留两端补零语义。"""
    values = np.asarray(signal, dtype=np.float64)
    if values.ndim != 1 or len(values) < 2:
        raise ValueError("STFT 输入必须是一维且至少包含 2 个采样点")
    if not np.all(np.isfinite(values)):
        raise ValueError("输入信号不能包含 NaN 或无穷值")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("采样率必须是有限正数")
    if any(
        isinstance(value, bool) or not isinstance(value, (int, np.integer))
        for value in (nperseg, noverlap, nfft)
    ):
        raise ValueError("STFT 窗口、重叠和 FFT 点数必须是整数")
    if nperseg < 2 or nperseg > len(values):
        raise ValueError("STFT 窗口长度必须在 2 与信号长度之间")
    if noverlap < 0 or noverlap >= nperseg:
        raise ValueError("STFT 重叠长度必须满足 0 <= noverlap < nperseg")
    if nfft < nperseg:
        raise ValueError("STFT FFT 点数不能小于窗口长度")

    frequency, time, complex_spectrum = scipy_stft(
        values,
        fs=sample_rate_hz,
        window=windows.hann(nperseg, sym=False),
        nperseg=nperseg,
        noverlap=noverlap,
        nfft=nfft,
        detrend=False,
        return_onesided=True,
        boundary="zeros",
        padded=True,
        axis=-1,
        scaling="spectrum",
    )
    amplitude = np.abs(complex_spectrum)
    # SciPy spectrum 刻度的中间单边 bin 为 A/2；DC/Nyquist 不翻倍。
    if nfft % 2 == 0:
        if len(frequency) > 2:
            amplitude[1:-1, :] *= 2.0
    elif len(frequency) > 1:
        amplitude[1:, :] *= 2.0
    return STFTRepresentation(
        time_s=np.asarray(time, dtype=np.float64),
        frequency_hz=np.asarray(frequency, dtype=np.float64),
        amplitude=np.asarray(amplitude, dtype=np.float64),
        amplitude_unit=amplitude_unit,
    )
