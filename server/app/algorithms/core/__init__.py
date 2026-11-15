"""算法层共享数据类型。数组字段保存引用，不因构造对象而复制数据。"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class Spectrum:
    """单边频谱；amplitude 的单位与输入信号一致。"""

    frequency_hz: NDArray[np.float64]
    amplitude: NDArray[np.float64]
    amplitude_unit: str = "input_signal"
    scaling: str = "single_sided_amplitude"

    def __post_init__(self) -> None:
        if self.frequency_hz.ndim != 1 or self.amplitude.ndim != 1:
            raise ValueError("频谱频率轴和幅值必须是一维数组")
        if len(self.frequency_hz) != len(self.amplitude):
            raise ValueError("频谱频率轴和幅值长度必须一致")
        if len(self.frequency_hz) == 0:
            raise ValueError("频谱不能为空")
        if not np.all(np.isfinite(self.frequency_hz)) or not np.all(
            np.isfinite(self.amplitude)
        ):
            raise ValueError("频谱不能包含 NaN 或无穷值")
        if len(self.frequency_hz) > 1 and np.any(np.diff(self.frequency_hz) <= 0):
            raise ValueError("频谱频率轴必须严格递增")
        if np.any(self.amplitude < 0):
            raise ValueError("频谱幅值不能为负数")
        if len(self.frequency_hz) > 2:
            intervals = np.diff(self.frequency_hz)
            if not np.allclose(intervals, intervals[0], rtol=1e-6, atol=1e-12):
                raise ValueError("当前 FFT 分析要求频率轴等间隔")

    def truncated(self, max_frequency_hz: float) -> "Spectrum":
        """返回不超过指定频率的频谱切片。"""
        if not np.isfinite(max_frequency_hz) or max_frequency_hz <= 0:
            raise ValueError("最大频率必须是有限正数")
        mask = self.frequency_hz <= max_frequency_hz
        if not np.any(mask):
            raise ValueError("最大频率低于频谱第一个频率点")
        return Spectrum(
            frequency_hz=self.frequency_hz[mask],
            amplitude=self.amplitude[mask],
            amplitude_unit=self.amplitude_unit,
            scaling=self.scaling,
        )


@dataclass(frozen=True)
class FrequencyBand:
    """实际执行的频带，单位为 Hz。"""

    low_hz: float
    high_hz: float

    def __post_init__(self) -> None:
        if not np.isfinite(self.low_hz) or not np.isfinite(self.high_hz):
            raise ValueError("频带边界必须是有限数")
        if self.low_hz <= 0 or self.high_hz <= self.low_hz:
            raise ValueError("频带必须满足 0 < low_hz < high_hz")

    @property
    def center_hz(self) -> float:
        return (self.low_hz + self.high_hz) / 2.0

    @property
    def width_hz(self) -> float:
        return self.high_hz - self.low_hz


@dataclass(frozen=True)
class SpectralPeak:
    """谱峰及其相对背景幅值比。"""

    frequency_hz: float
    amplitude: float
    snr: float
