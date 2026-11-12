"""原生小波结果到带单位领域值的薄适配；不复制系数或全长波形。"""

from cnn_compute import wavelet as native

from ..types import ValidInterval
from .core import (
    DWTBand,
    DWTDecomposition,
    WaveletPacketDecomposition,
    WaveletPacketNode,
)


class NativeWaveletImplementation:
    """默认独立 C++ 实现；Python 仅添加原时间轴和频带元数据。"""

    def denoise(self, signal, wavelet, level, threshold_mode, threshold_scale):
        return native.denoise(signal, wavelet, level, threshold_mode, threshold_scale)

    def dwt(self, signal, sample_rate_hz, wavelet, level, mode):
        coefficients, reconstructed = native.dwt(signal, wavelet, level, mode)
        valid = ValidInterval(0, len(signal))
        approximation = DWTBand(
            "approximation", level, coefficients[0], reconstructed[0],
            sample_rate_hz / 2.0**level,
            (0.0, sample_rate_hz / 2.0 ** (level + 1)), valid,
        )
        details = tuple(
            DWTBand(
                "detail", j, coefficients[level - j + 1], reconstructed[level - j + 1],
                sample_rate_hz / 2.0**j,
                (sample_rate_hz / 2.0 ** (j + 1), sample_rate_hz / 2.0**j), valid,
            )
            for j in range(1, level + 1)
        )
        return DWTDecomposition(len(signal), sample_rate_hz, wavelet, mode, level,
                                approximation, details, valid)

    def wavelet_packet(self, signal, sample_rate_hz, wavelet, level, mode):
        coefficients, reconstructed = native.wavelet_packet(signal, wavelet, level, mode)
        valid = ValidInterval(0, len(signal))
        bandwidth = sample_rate_hz / 2.0 ** (level + 1)
        nodes = []
        for natural_index, (coefficient, component) in enumerate(zip(coefficients, reconstructed)):
            frequency_index, gray = 0, natural_index
            while gray:
                frequency_index ^= gray
                gray >>= 1
            path = format(natural_index, f"0{level}b").translate(str.maketrans("01", "ad"))
            nodes.append(WaveletPacketNode(
                path, level, natural_index, frequency_index, coefficient, component,
                sample_rate_hz / 2.0**level,
                (frequency_index * bandwidth, (frequency_index + 1) * bandwidth), valid,
            ))
        return WaveletPacketDecomposition(len(signal), sample_rate_hz, wavelet, mode,
                                          level, tuple(nodes), valid)
