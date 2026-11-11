"""实倒谱表示：只计算对数幅值谱的逆 FFT，不检测峰或判断故障。"""
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.fft import fft, ifft
from scipy.signal import windows


FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class CepstrumRepresentation:
    quefrency_s: FloatArray
    amplitude: FloatArray
    quefrency_unit: str = "s"
    amplitude_unit: str = "log_input_amplitude"
    window: str = "periodic_hann"
    log_spectrum: str = "demeaned_log_magnitude"

    def __post_init__(self) -> None:
        if self.quefrency_s.ndim != 1 or self.amplitude.ndim != 1:
            raise ValueError("倒频率轴和倒谱幅值必须是一维数组")
        if len(self.quefrency_s) != len(self.amplitude) or len(self.quefrency_s) == 0:
            raise ValueError("倒频率轴和倒谱幅值必须是非空等长数组")
        if not np.all(np.isfinite(self.quefrency_s)) or not np.all(np.isfinite(self.amplitude)):
            raise ValueError("倒谱表示不能包含 NaN 或无穷值")

    def truncated(self, max_quefrency_s: float) -> "CepstrumRepresentation":
        """按秒截断表示，不重算倒谱。"""
        if not np.isfinite(max_quefrency_s) or max_quefrency_s <= 0:
            raise ValueError("最大倒频率必须是有限正数")
        mask = self.quefrency_s <= max_quefrency_s
        if not np.any(mask):
            raise ValueError("最大倒频率低于倒谱第一个点")
        return CepstrumRepresentation(
            quefrency_s=self.quefrency_s[mask],
            amplitude=self.amplitude[mask],
        )


def compute_cepstrum(
    signal: FloatArray,
    sample_rate_hz: float,
) -> CepstrumRepresentation:
    """周期 Hann → FFT → 去均值 log(|X|+1e-10) → 实 IFFT。

    返回非负倒频率半轴，单位为秒；该表示是 log-amplitude 实倒谱，
    不将其误称为 log-power 倒谱，也不包含峰值或故障阈值。
    """
    values = np.asarray(signal, dtype=np.float64)
    if values.ndim != 1 or len(values) < 2:
        raise ValueError("倒谱输入必须是一维且至少包含 2 个采样点")
    if not np.all(np.isfinite(values)):
        raise ValueError("输入信号不能包含 NaN 或无穷值")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("采样率必须是有限正数")

    windowed = values * windows.hann(len(values), sym=False)
    log_spectrum = np.log(np.abs(fft(windowed)) + 1e-10)
    log_spectrum -= np.mean(log_spectrum)
    cepstrum = np.real(ifft(log_spectrum))
    half = len(values) // 2
    quefrency = np.arange(half, dtype=np.float64) / sample_rate_hz
    return CepstrumRepresentation(
        quefrency_s=quefrency,
        amplitude=np.asarray(cepstrum[:half], dtype=np.float64),
    )
