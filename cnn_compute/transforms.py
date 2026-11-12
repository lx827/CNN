"""可独立使用的原生解析信号、幅度归一化和 Hilbert/NHT 频率变换。"""

from ._native import transforms as _native


def analytic_signal(signal):
    """返回一维 complex128 解析信号；最终复数缓冲区零复制交给 NumPy。"""
    from .emd import _signal

    return _native.analytic_signal(_signal(signal))


def amplitude_normalise(signal):
    """emd 0.8.1 默认 PCHIP combined 包络三轮幅度归一化；输出独立。"""
    from .emd import _signal

    return _native.amplitude_normalise(_signal(signal))


def frequency_transform(
    signal, sample_rate=1.0, method="nht", smooth_freq=3, smooth_phase=5
):
    """一维输入返回一维 (phase, frequency, amplitude)，全部数值在 C++。

    支持 hilbert 与 nht；phase 为 [0,2π) 升零相位，frequency 单位 Hz。
    smooth_phase 为零填充中值窗口，smooth_freq 为一阶 Savitzky-Golay 窗口。
    """
    from .emd import _signal

    if method not in {"hilbert", "nht"}:
        raise ValueError("method 必须为 hilbert 或 nht")
    return _native.frequency_transform(
        _signal(signal),
        sample_rate,
        method == "nht",
        smooth_phase,
        smooth_freq,
    )
