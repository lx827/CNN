"""基于 PyWavelets 的 DWT/WP 实现；本文件是唯一 PyWavelets adapter。"""
from __future__ import annotations

import copy

import numpy as np
import pywt

from ..types import ValidInterval
from .core import (
    DWTBand,
    DWTDecomposition,
    FloatArray,
    WaveletPacketDecomposition,
    WaveletPacketNode,
)


def _original_axis(reconstructed: FloatArray, input_length: int) -> FloatArray:
    """只裁掉对称延拓产生的尾部；长度不足时禁止补零伪装。"""
    arr = np.asarray(reconstructed, dtype=np.float64)
    if len(arr) < input_length:
        raise RuntimeError("PyWavelets 重构短于输入有效区间，拒绝补零")
    return np.array(arr[:input_length], dtype=np.float64, copy=True)


class PyWaveletsImplementation:
    """无状态 PyWavelets 实现，可被同契约的 Rust/C++ 实现替换。"""

    def denoise(self, signal, wavelet, level, threshold_mode, threshold_scale):
        from scipy.special import expit
        wavelet_object = pywt.Wavelet(wavelet)
        maximum = pywt.dwt_max_level(len(signal), wavelet_object.dec_len)
        chosen = maximum if level is None else level
        if chosen < 1 or chosen > maximum:
            raise ValueError(f"DWT 层数必须位于 [1, {maximum}]")
        amplitude = float(np.max(np.abs(signal)))
        normalized = signal / amplitude if amplitude else signal
        coefficients = pywt.wavedec(normalized, wavelet_object, mode="symmetric", level=chosen)
        finest = coefficients[-1]
        sigma = np.median(np.abs(finest - np.median(finest))) / .6744897501960817
        threshold = threshold_scale * sigma * np.sqrt(2 * np.log(len(signal)))
        output = [coefficients[0]]
        for detail in coefficients[1:]:
            absolute = np.abs(detail)
            if threshold_mode == "soft":
                updated = np.sign(detail) * np.maximum(absolute - threshold, 0)
            elif threshold_mode == "hard":
                updated = detail * (absolute > threshold)
            else:
                updated = np.sign(detail) * np.maximum(
                    absolute - threshold * expit(-2 * (absolute - threshold)), 0)
            output.append(updated)
        return _original_axis(pywt.waverec(output, wavelet_object, mode="symmetric"), len(signal)) * amplitude

    def dwt(
        self, signal: FloatArray, sample_rate_hz: float,
        wavelet: str, level: int, mode: str,
    ) -> DWTDecomposition:
        wavelet_object = pywt.Wavelet(wavelet)
        max_level = pywt.dwt_max_level(len(signal), wavelet_object.dec_len)
        if level > max_level:
            raise ValueError(f"DWT 层数超过当前输入和小波允许的上限 {max_level}")
        coefficients = pywt.wavedec(signal, wavelet_object, mode=mode, level=level)
        valid = ValidInterval(0, len(signal))

        def reconstruct_band(index: int) -> FloatArray:
            selected = [np.zeros_like(item) for item in coefficients]
            selected[index] = coefficients[index]
            return _original_axis(pywt.waverec(selected, wavelet_object, mode=mode), len(signal))

        approximation = DWTBand(
            kind="approximation", level=level,
            coefficients=np.array(coefficients[0], dtype=np.float64, copy=True),
            reconstructed=reconstruct_band(0),
            coefficient_sample_rate_hz=sample_rate_hz / 2.0**level,
            frequency_band_hz=(0.0, sample_rate_hz / 2.0 ** (level + 1)),
            valid_interval=valid,
        )
        details = []
        for detail_level in range(1, level + 1):
            index = level - detail_level + 1
            details.append(DWTBand(
                kind="detail", level=detail_level,
                coefficients=np.array(coefficients[index], dtype=np.float64, copy=True),
                reconstructed=reconstruct_band(index),
                coefficient_sample_rate_hz=sample_rate_hz / 2.0**detail_level,
                frequency_band_hz=(
                    sample_rate_hz / 2.0 ** (detail_level + 1),
                    sample_rate_hz / 2.0**detail_level,
                ),
                valid_interval=valid,
            ))
        return DWTDecomposition(
            input_length=len(signal), sample_rate_hz=sample_rate_hz,
            wavelet=wavelet, mode=mode, level=level,
            approximation=approximation, details=tuple(details), valid_interval=valid,
        )

    def wavelet_packet(
        self, signal: FloatArray, sample_rate_hz: float,
        wavelet: str, level: int, mode: str,
    ) -> WaveletPacketDecomposition:
        wavelet_object = pywt.Wavelet(wavelet)
        max_level = pywt.dwt_max_level(len(signal), wavelet_object.dec_len)
        if level > max_level:
            raise ValueError(f"WP 层数超过当前输入和小波允许的上限 {max_level}")
        base = pywt.WaveletPacket(data=signal, wavelet=wavelet_object, mode=mode)
        source_nodes = base.get_level(level, order="natural")
        valid = ValidInterval(0, len(signal))
        nodes = []
        bandwidth = sample_rate_hz / 2.0 ** (level + 1)
        for natural_index, source in enumerate(source_nodes):
            tree = copy.deepcopy(base)
            for target in tree.get_level(level, order="natural"):
                if target.path != source.path:
                    target.data = np.zeros_like(target.data)
            reconstructed = _original_axis(tree.reconstruct(update=True), len(signal))
            # PyWavelets 的 freq -> natural 是 Gray 码，因此反向查表必须用逆 Gray。
            frequency_index = 0
            gray = natural_index
            while gray:
                frequency_index ^= gray
                gray >>= 1
            nodes.append(WaveletPacketNode(
                path=source.path, level=level,
                natural_index=natural_index, frequency_index=frequency_index,
                coefficients=np.array(source.data, dtype=np.float64, copy=True),
                reconstructed=reconstructed,
                coefficient_sample_rate_hz=sample_rate_hz / 2.0**level,
                frequency_band_hz=(frequency_index * bandwidth, (frequency_index + 1) * bandwidth),
                valid_interval=valid,
            ))
        return WaveletPacketDecomposition(
            input_length=len(signal), sample_rate_hz=sample_rate_hz,
            wavelet=wavelet, mode=mode, level=level,
            nodes=tuple(nodes), valid_interval=valid,
        )
