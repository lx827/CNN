"""通用带通 Hilbert 包络时域表示，不附加诊断低通、指标或故障结论。"""

import numpy as np
from numpy.typing import NDArray

from app.algorithms.core import FrequencyBand
from cnn_compute.filtering import butterworth, detrend, sosfiltfilt
from cnn_compute.numeric import hilbert_envelope


def compute_bandpass_hilbert_envelope(
    signal: NDArray[np.float64],
    sample_rate_hz: float,
    band: FrequencyBand,
    *,
    filter_order: int = 4,
) -> NDArray[np.float64]:
    """去均值后执行 Butterworth SOS 带通与 Hilbert 幅值，输出保持输入单位。"""
    values = np.asarray(signal, dtype=np.float64)
    if values.ndim != 1 or len(values) < 64:
        raise ValueError("带通包络输入必须是一维且至少包含 64 个采样点")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("采样率必须是有限正数")
    if band.high_hz >= sample_rate_hz / 2.0:
        raise ValueError("带通上限必须低于 Nyquist 频率")
    if (
        isinstance(filter_order, bool)
        or not isinstance(filter_order, int)
        or filter_order <= 0
    ):
        raise ValueError("滤波器阶数必须是正整数")

    sos = butterworth(filter_order, band.low_hz, band.high_hz, sample_rate_hz)
    return hilbert_envelope(sosfiltfilt(sos, detrend(values)))
