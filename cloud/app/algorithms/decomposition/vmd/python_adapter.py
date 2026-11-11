"""内存有界的 NumPy VMD 实现；只保留前后两轮模态频谱。"""
from __future__ import annotations

import numpy as np

from ..types import ValidInterval
from .core import FloatArray, VMDParameters, VMDResult


def _real_modes(positive_spectra: np.ndarray) -> np.ndarray:
    """把单边解析频谱恢复为实模态，分别处理奇偶长度及 Nyquist  bin。"""
    length, count = positive_spectra.shape
    unshifted = np.fft.ifftshift(positive_spectra, axes=0)
    output = np.empty((count, length), dtype=np.float64)
    for mode in range(count):
        spectrum = np.zeros(length, dtype=np.complex128)
        source = unshifted[:, mode]
        spectrum[0] = source[0].real
        if length % 2 == 0:
            nyquist = length // 2
            positive = np.arange(1, nyquist)
            spectrum[nyquist] = source[nyquist].real
        else:
            positive = np.arange(1, (length + 1) // 2)
        spectrum[positive] = source[positive]
        spectrum[-positive] = np.conj(source[positive])
        output[mode] = np.fft.ifft(spectrum).real
    return output


class PythonVMDImplementation:
    """Dragomiretskiy & Zosso (2014) ADMM 更新；频率内部单位为 cycles/sample。"""

    def vmd(self, signal: FloatArray, sample_rate_hz: float, parameters: VMDParameters) -> VMDResult:
        input_length = len(signal)
        valid_length = input_length if parameters.max_samples is None else min(
            input_length, parameters.max_samples,
        )
        valid = ValidInterval(0, valid_length)
        segment = signal[:valid_length]
        scale = float(np.max(np.abs(segment)))
        if scale == 0 or float(np.std(segment / scale)) == 0:
            return VMDResult(
                status="indeterminate", input_length=input_length, sample_rate_hz=sample_rate_hz,
                modes=np.empty((0, valid_length), dtype=np.float64),
                center_frequencies_hz=np.empty(0, dtype=np.float64),
                center_frequency_history_hz=np.empty((0, 0), dtype=np.float64),
                residual=segment.copy(), valid_interval=valid,
                iterations=0, converged=False, reason="zero_variance",
            )

        normalized = segment / scale
        # 归一化后执行 ADMM，使固定收敛容差不依赖振动幅值单位。
        # 奇数输入左右各镜像 floor(N/2) 点；原区间始终精确取 N 点。
        left = valid_length // 2
        mirrored = np.concatenate((normalized[:left][::-1], normalized, normalized[-left:][::-1]))
        length = len(mirrored)
        frequencies = np.fft.fftshift(np.fft.fftfreq(length))
        spectrum_plus = np.fft.fftshift(np.fft.fft(mirrored))
        spectrum_plus[:length // 2] = 0.0
        positive_slice = slice(length // 2, length)
        positive_frequencies = frequencies[positive_slice]

        count = parameters.modes
        alpha = np.full(count, parameters.alpha, dtype=np.float64)
        centers = (0.5 / count) * np.arange(count, dtype=np.float64)
        if parameters.dc:
            centers[0] = 0.0
        previous = np.zeros((length, count), dtype=np.complex128)
        current = np.zeros_like(previous)
        dual = np.zeros(length, dtype=np.complex128)
        sum_modes = np.zeros(length, dtype=np.complex128)
        history = np.empty((parameters.max_iterations, count), dtype=np.float64)
        converged = False
        iterations = 0

        for iteration in range(parameters.max_iterations):
            for mode in range(count):
                if mode == 0:
                    sum_modes = previous[:, -1] + sum_modes - previous[:, 0]
                else:
                    sum_modes = current[:, mode - 1] + sum_modes - previous[:, mode]
                current[:, mode] = (
                    spectrum_plus - sum_modes - dual / 2.0
                ) / (1.0 + alpha[mode] * (frequencies - centers[mode]) ** 2)
                if mode > 0 or not parameters.dc:
                    power = np.abs(current[positive_slice, mode]) ** 2
                    denominator = float(np.sum(power))
                    if denominator > np.finfo(np.float64).tiny:
                        centers[mode] = float(np.dot(positive_frequencies, power) / denominator)
            dual = dual + parameters.tau * (np.sum(current, axis=1) - spectrum_plus)
            difference = float(np.spacing(1))
            for mode in range(count):
                delta = current[:, mode] - previous[:, mode]
                difference += float(np.vdot(delta, delta).real / length)
            history[iteration] = centers
            previous, current = current, previous
            current.fill(0.0)
            iterations = iteration + 1
            if difference <= parameters.tolerance:
                converged = True
                break

        modes = _real_modes(previous)[:, left:left + valid_length] * scale
        centers_hz = centers * sample_rate_hz
        history_hz = history[:iterations] * sample_rate_hz
        order = np.argsort(centers_hz)
        modes = modes[order]
        centers_hz = centers_hz[order]
        history_hz = history_hz[:, order]
        residual = segment - np.sum(modes, axis=0)
        return VMDResult(
            status="valid", input_length=input_length, sample_rate_hz=sample_rate_hz,
            modes=modes, center_frequencies_hz=centers_hz,
            center_frequency_history_hz=history_hz,
            residual=residual, valid_interval=valid,
            iterations=iterations, converged=converged,
            reason=None if converged else "maximum_iterations_reached",
        )
