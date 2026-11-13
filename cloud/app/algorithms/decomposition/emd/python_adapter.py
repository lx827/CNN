"""NumPy/SciPy EMD 族实现；镜像、极值精化和 SD 停止均在本 adapter 内完成。

上游移植参照（未安装、未调用、未换库）：EMD-signal/PyEMD 1.10.0，
源码 https://github.com/laszukdawid/PyEMD ，Apache-2.0 许可证。
算法依据：Huang et al. (1998) EMD、Wu & Huang (2009) EEMD、
Torres et al. (2011) CEEMDAN。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import numpy as np
from scipy.interpolate import CubicSpline, PchipInterpolator

from ..types import ValidInterval
from .core import EMDParameters, EMDResult, EnsembleParameters, FloatArray


def _extrema(signal: FloatArray) -> tuple[np.ndarray, np.ndarray]:
    difference = np.diff(signal)
    maxima = np.flatnonzero((difference[:-1] > 0.0) & (difference[1:] <= 0.0)) + 1
    minima = np.flatnonzero((difference[:-1] < 0.0) & (difference[1:] >= 0.0)) + 1
    return maxima, minima


def _refine_extrema(
    signal: FloatArray, indices: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """用三点抛物线同时精化位置和幅值，返回值会实际进入包络插值。"""
    locations = indices.astype(np.float64)
    values = signal[indices].copy()
    for offset, index in enumerate(indices):
        left, center, right = signal[index - 1 : index + 2]
        denominator = left - 2.0 * center + right
        if abs(denominator) <= np.finfo(np.float64).eps:
            continue
        shift = 0.5 * (left - right) / denominator
        if abs(shift) > 0.5:
            continue
        quadratic_b = (right - left) / 2.0
        quadratic_a = denominator / 2.0
        locations[offset] = float(index) + shift
        values[offset] = center - quadratic_b * quadratic_b / (4.0 * quadratic_a)
    return locations, values


def _unique_locations(
    locations: np.ndarray, values: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    order = np.argsort(locations)
    locations, values = locations[order], values[order]
    unique, indices = np.unique(locations, return_index=True)
    return unique, values[indices]


def _mirror_extrema(
    signal: FloatArray,
    maxima: tuple[np.ndarray, np.ndarray],
    minima: tuple[np.ndarray, np.ndarray],
    width: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """把真实极值的镜像点加入插值网格，包含位于信号内部的对称轴情况。"""
    max_locs, max_vals = maxima
    min_locs, min_vals = minima
    if signal[0] > max_vals[0]:
        left_axis = max_locs[0]
    elif signal[0] < min_vals[0]:
        left_axis = min_locs[0]
    else:
        left_axis = 0.0
    if signal[-1] < max_vals[-1]:
        right_axis = max_locs[-1]
    elif signal[-1] > min_vals[-1]:
        right_axis = min_locs[-1]
    else:
        right_axis = float(len(signal) - 1)

    padded = []
    for locations, values in ((max_locs, max_vals), (min_locs, min_vals)):
        left_locations = []
        left_values = []
        for location, value in zip(locations[: width + 1], values[: width + 1]):
            mirrored = 2.0 * left_axis - location
            if mirrored < locations[0] and not np.isclose(mirrored, locations[0]):
                left_locations.append(mirrored)
                left_values.append(value)
        right_locations = []
        right_values = []
        for location, value in zip(
            locations[-width - 1 :][::-1], values[-width - 1 :][::-1]
        ):
            mirrored = 2.0 * right_axis - location
            if mirrored > locations[-1] and not np.isclose(mirrored, locations[-1]):
                right_locations.append(mirrored)
                right_values.append(value)
        all_locations = np.concatenate(
            (left_locations[::-1], locations, right_locations)
        )
        all_values = np.concatenate((left_values[::-1], values, right_values))
        padded.extend(_unique_locations(all_locations, all_values))
    return padded[0], padded[1], padded[2], padded[3]


def _envelopes(
    signal: FloatArray, parameters: EMDParameters
) -> tuple[FloatArray, FloatArray] | None:
    maxima_indices, minima_indices = _extrema(signal)
    if len(maxima_indices) < 2 or len(minima_indices) < 2:
        return None
    maxima = _refine_extrema(signal, maxima_indices)
    minima = _refine_extrema(signal, minima_indices)
    max_locs, max_vals, min_locs, min_vals = _mirror_extrema(
        signal,
        maxima,
        minima,
        parameters.mirror_extrema,
    )
    coordinates = np.arange(len(signal), dtype=np.float64)
    interpolator = (
        PchipInterpolator if parameters.interpolation == "pchip" else CubicSpline
    )
    upper = interpolator(max_locs, max_vals, extrapolate=True)(coordinates)
    lower = interpolator(min_locs, min_vals, extrapolate=True)(coordinates)
    if not np.all(np.isfinite(upper)) or not np.all(np.isfinite(lower)):
        raise RuntimeError("EMD 包络插值产生非有限值")
    return upper, lower


def _envelope_mean(signal: FloatArray, parameters: EMDParameters) -> FloatArray | None:
    envelopes = _envelopes(signal, parameters)
    return None if envelopes is None else (envelopes[0] + envelopes[1]) / 2.0


def rilling_stop(
    upper: FloatArray, lower: FloatArray, thresholds: tuple[float, float, float]
) -> bool:
    """Rilling 包络对称性判据；零包络幅值且非零均值的点不满足判据。"""
    sd1, sd2, fraction = thresholds
    mean = np.abs((upper + lower) / 2.0)
    amplitude = np.abs(upper - lower) / 2.0
    ratio = np.divide(
        mean, amplitude, out=np.full_like(mean, np.inf), where=amplitude > 0
    )
    ratio[(mean == 0) & (amplitude == 0)] = 0
    return bool(np.mean(ratio > sd1) <= fraction and np.all(ratio <= sd2))


def _sift(
    signal: FloatArray, parameters: EMDParameters
) -> tuple[FloatArray, int, bool] | None:
    if len(_extrema(signal)[0]) < 2 or len(_extrema(signal)[1]) < 2:
        return None
    current = signal.copy()
    for iteration in range(1, parameters.max_sifts + 1):
        envelopes = _envelopes(current, parameters)
        if envelopes is None:
            return current, iteration - 1, True
        upper, lower = envelopes
        mean = (upper + lower) / 2.0
        updated = current - mean
        denominator = float(np.sum(current * current))
        if denominator <= np.finfo(np.float64).tiny:
            return updated, iteration, True
        sd = float(np.sum((updated - current) ** 2) / denominator)
        # SD 描述上一轮与本轮之差；满足准则后必须接受 updated，而非丢弃本轮。
        current = updated
        stop = (
            sd < parameters.sd_threshold
            if parameters.stopping_rule == "sd"
            else rilling_stop(
                upper,
                lower,
                parameters.rilling_thresholds,
            )
        )
        if stop:
            return current, iteration, True
    return current, parameters.max_sifts, False


_SiftKernel = Callable[[FloatArray, EMDParameters], tuple[FloatArray, int, bool] | None]


def _indeterminate(
    method: str, signal: FloatArray, fs: float, reason: str, seed: int | None = None
) -> EMDResult:
    return EMDResult(
        method=method,
        status="indeterminate",
        input_length=len(signal),
        sample_rate_hz=fs,
        imfs=(),
        residual=signal.copy(),
        valid_interval=ValidInterval(0, len(signal)),
        sift_iterations=(),
        converged=(),
        seed=seed,
        reason=reason,
    )


def _emd(
    signal: FloatArray,
    fs: float,
    parameters: EMDParameters,
    method: str = "emd",
    *,
    sift_kernel: _SiftKernel = _sift,
) -> EMDResult:
    amplitude = float(np.max(np.abs(signal)))
    if amplitude == 0 or float(np.std(signal / amplitude)) == 0:
        return _indeterminate(method, signal, fs, "zero_variance")
    imfs = []
    iterations = []
    converged = []
    residual = signal / amplitude
    for _ in range(parameters.max_imfs):
        sifted = sift_kernel(residual, parameters)
        if sifted is None:
            break
        imf, count, did_converge = sifted
        if float(np.std(imf)) <= np.finfo(np.float64).eps * float(
            np.std(signal / amplitude)
        ):
            break
        imfs.append(imf)
        iterations.append(count)
        converged.append(did_converge)
        residual = residual - imf
        maxima, minima = _extrema(residual)
        if len(maxima) < 2 or len(minima) < 2:
            break
    if not imfs:
        return _indeterminate(method, signal, fs, "insufficient_extrema")
    return EMDResult(
        method=method,
        status="valid",
        input_length=len(signal),
        sample_rate_hz=fs,
        imfs=tuple(imf * amplitude for imf in imfs),
        residual=residual * amplitude,
        valid_interval=ValidInterval(0, len(signal)),
        sift_iterations=tuple(iterations),
        converged=tuple(converged),
        reason=None if all(converged) else "maximum_sifts_reached",
    )


class PythonEMDImplementation:
    """仓库内纯 Python 实现；不是 EMD-signal/PyEMD 的包装或依赖。"""

    def __init__(self, *, sift_kernel: _SiftKernel = _sift) -> None:
        """共享 Python 外层，仅替换单 IMF 筛分核。

        核接收已归一化的一维有限数组和筛分参数，借用只读输入；返回独立
        IMF 数组、迭代次数与收敛标志，或以 None 表示初始极值不足。
        默认核保持现有数学行为。核中的异常直接向调用方传播。
        """
        self._sift_kernel = sift_kernel

    def emd(
        self, signal: FloatArray, sample_rate_hz: float, parameters: EMDParameters
    ) -> EMDResult:
        if not np.all(np.isfinite(signal)):
            raise ValueError("输入信号不能包含 NaN 或无穷值")
        return _emd(signal, sample_rate_hz, parameters, sift_kernel=self._sift_kernel)

    def eemd(
        self,
        signal: FloatArray,
        sample_rate_hz: float,
        parameters: EnsembleParameters,
        seed: int,
    ) -> EMDResult:
        if not np.all(np.isfinite(signal)):
            raise ValueError("输入信号不能包含 NaN 或无穷值")
        scale = float(np.std(signal))
        if scale == 0.0:
            return _indeterminate("eemd", signal, sample_rate_hz, "zero_variance", seed)
        if parameters.noise_scale == 0.0:
            result = _emd(
                signal,
                sample_rate_hz,
                parameters.emd,
                method="eemd",
                sift_kernel=self._sift_kernel,
            )
            return replace(result, seed=seed)
        normalized = signal / scale
        rng = np.random.default_rng(seed)
        members = []
        for _ in range(parameters.ensemble_size):
            noise = rng.normal(0.0, parameters.noise_scale, len(signal))
            result = _emd(
                normalized + noise,
                sample_rate_hz,
                parameters.emd,
                sift_kernel=self._sift_kernel,
            )
            if result.imfs:
                members.append(result)
        if not members:
            return _indeterminate(
                "eemd", signal, sample_rate_hz, "no_valid_ensemble_member", seed
            )
        count = max(len(member.imfs) for member in members)
        imfs = []
        iterations = []
        converged = []
        for index in range(count):
            selected = [member for member in members if len(member.imfs) > index]
            imfs.append(np.mean([member.imfs[index] for member in selected], axis=0))
            iterations.append(max(member.sift_iterations[index] for member in selected))
            converged.append(all(member.converged[index] for member in selected))
        residual = normalized - sum(imfs, start=np.zeros(len(signal)))
        return EMDResult(
            method="eemd",
            status="valid",
            input_length=len(signal),
            sample_rate_hz=sample_rate_hz,
            imfs=tuple(imf * scale for imf in imfs),
            residual=residual * scale,
            valid_interval=ValidInterval(0, len(signal)),
            sift_iterations=tuple(iterations),
            converged=tuple(converged),
            seed=seed,
            reason=None if all(converged) else "maximum_sifts_reached",
        )

    def ceemdan(
        self,
        signal: FloatArray,
        sample_rate_hz: float,
        parameters: EnsembleParameters,
        seed: int,
    ) -> EMDResult:
        if not np.all(np.isfinite(signal)):
            raise ValueError("输入信号不能包含 NaN 或无穷值")
        scale = float(np.std(signal))
        if scale == 0.0:
            return _indeterminate(
                "ceemdan", signal, sample_rate_hz, "zero_variance", seed
            )
        if parameters.noise_scale == 0.0:
            result = _emd(
                signal,
                sample_rate_hz,
                parameters.emd,
                method="ceemdan",
                sift_kernel=self._sift_kernel,
            )
            return replace(result, seed=seed)
        normalized = signal / scale
        rng = np.random.default_rng(seed)
        noise_modes = []
        white_noises = []
        for _ in range(parameters.ensemble_size):
            noise = rng.normal(0.0, 1.0, len(signal))
            white_noises.append(noise)
            result = _emd(
                noise,
                sample_rate_hz,
                parameters.emd,
                sift_kernel=self._sift_kernel,
            )
            noise_modes.append(result.imfs)

        residual = normalized.copy()
        imfs = []
        iterations = []
        converged = []
        single_mode_parameters = replace(parameters.emd, max_imfs=1)
        for order in range(parameters.emd.max_imfs):
            first_imfs = []
            member_iterations = []
            member_converged = []
            amplitude = 1.0 if order == 0 else float(np.std(residual))
            for white_noise, modes in zip(white_noises, noise_modes):
                # Torres 2011: 第一次对原白噪声取 E1；之后取 E_k(白噪声)。
                # 不把局部均值平均的 improved-CEEMDAN 变体冒称为该公式。
                if order == 0:
                    noise = white_noise
                elif order - 1 < len(modes) and np.std(modes[order - 1]) > 0:
                    noise = modes[order - 1] / np.std(modes[order - 1])
                else:
                    noise = np.zeros(len(signal))
                trial = residual + parameters.noise_scale * amplitude * noise
                result = _emd(
                    trial,
                    sample_rate_hz,
                    single_mode_parameters,
                    sift_kernel=self._sift_kernel,
                )
                if not result.imfs:
                    continue
                first_imfs.append(result.imfs[0])
                member_iterations.append(result.sift_iterations[0])
                member_converged.append(result.converged[0])
            if not first_imfs:
                break
            imf = np.mean(first_imfs, axis=0)
            if np.std(imf) <= np.finfo(np.float64).eps:
                break
            imfs.append(imf)
            iterations.append(max(member_iterations))
            converged.append(all(member_converged))
            residual = residual - imf
            maxima, minima = _extrema(residual)
            if len(maxima) < 2 or len(minima) < 2:
                break
        if not imfs:
            return _indeterminate(
                "ceemdan", signal, sample_rate_hz, "no_valid_ensemble_member", seed
            )
        return EMDResult(
            method="ceemdan",
            status="valid",
            input_length=len(signal),
            sample_rate_hz=sample_rate_hz,
            imfs=tuple(imf * scale for imf in imfs),
            residual=residual * scale,
            valid_interval=ValidInterval(0, len(signal)),
            sift_iterations=tuple(iterations),
            converged=tuple(converged),
            seed=seed,
            reason=None if all(converged) else "maximum_sifts_reached",
        )
