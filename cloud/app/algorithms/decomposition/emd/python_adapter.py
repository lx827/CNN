"""NumPy/SciPy EMD 族实现；镜像、极值精化和 SD 停止均在本 adapter 内完成。

上游移植参照（未安装、未调用、未换库）：EMD-signal/PyEMD 1.10.0，
源码 https://github.com/laszukdawid/PyEMD ，Apache-2.0 许可证。
算法依据：Huang et al. (1998) EMD、Wu & Huang (2009) EEMD、
Torres et al. (2011) CEEMDAN。
"""
from __future__ import annotations

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


def _refine_extrema(signal: FloatArray, indices: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """用三点抛物线同时精化位置和幅值，返回值会实际进入包络插值。"""
    locations = indices.astype(np.float64)
    values = signal[indices].copy()
    for offset, index in enumerate(indices):
        left, center, right = signal[index - 1:index + 2]
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


def _unique_locations(locations: np.ndarray, values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
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
        for location, value in zip(locations[:width + 1], values[:width + 1]):
            mirrored = 2.0 * left_axis - location
            if mirrored < locations[0] and not np.isclose(mirrored, locations[0]):
                left_locations.append(mirrored)
                left_values.append(value)
        right_locations = []
        right_values = []
        for location, value in zip(locations[-width - 1:][::-1], values[-width - 1:][::-1]):
            mirrored = 2.0 * right_axis - location
            if mirrored > locations[-1] and not np.isclose(mirrored, locations[-1]):
                right_locations.append(mirrored)
                right_values.append(value)
        all_locations = np.concatenate((left_locations[::-1], locations, right_locations))
        all_values = np.concatenate((left_values[::-1], values, right_values))
        padded.extend(_unique_locations(all_locations, all_values))
    return padded[0], padded[1], padded[2], padded[3]


def _envelope_mean(signal: FloatArray, parameters: EMDParameters) -> FloatArray | None:
    maxima_indices, minima_indices = _extrema(signal)
    if len(maxima_indices) < 2 or len(minima_indices) < 2:
        return None
    maxima = _refine_extrema(signal, maxima_indices)
    minima = _refine_extrema(signal, minima_indices)
    max_locs, max_vals, min_locs, min_vals = _mirror_extrema(
        signal, maxima, minima, parameters.mirror_extrema,
    )
    coordinates = np.arange(len(signal), dtype=np.float64)
    interpolator = PchipInterpolator if parameters.interpolation == "pchip" else CubicSpline
    upper = interpolator(max_locs, max_vals, extrapolate=True)(coordinates)
    lower = interpolator(min_locs, min_vals, extrapolate=True)(coordinates)
    if not np.all(np.isfinite(upper)) or not np.all(np.isfinite(lower)):
        raise RuntimeError("EMD 包络插值产生非有限值")
    return (upper + lower) / 2.0


def _sift(signal: FloatArray, parameters: EMDParameters) -> tuple[FloatArray, int, bool] | None:
    if len(_extrema(signal)[0]) < 2 or len(_extrema(signal)[1]) < 2:
        return None
    current = signal.copy()
    for iteration in range(1, parameters.max_sifts + 1):
        mean = _envelope_mean(current, parameters)
        if mean is None:
            return current, iteration - 1, True
        updated = current - mean
        denominator = float(np.sum(current * current))
        if denominator <= np.finfo(np.float64).tiny:
            return updated, iteration, True
        sd = float(np.sum((updated - current) ** 2) / denominator)
        # SD 描述上一轮与本轮之差；满足准则后必须接受 updated，而非丢弃本轮。
        current = updated
        if sd < parameters.sd_threshold:
            return current, iteration, True
    return current, parameters.max_sifts, False


def _indeterminate(method: str, signal: FloatArray, fs: float, reason: str, seed: int | None = None) -> EMDResult:
    return EMDResult(
        method=method, status="indeterminate", input_length=len(signal), sample_rate_hz=fs,
        imfs=(), residual=signal.copy(), valid_interval=ValidInterval(0, len(signal)),
        sift_iterations=(), converged=(), seed=seed, reason=reason,
    )


def _emd(signal: FloatArray, fs: float, parameters: EMDParameters, method: str = "emd") -> EMDResult:
    if float(np.std(signal)) <= np.finfo(np.float64).eps:
        return _indeterminate(method, signal, fs, "zero_variance")
    imfs = []
    iterations = []
    converged = []
    residual = signal.copy()
    for _ in range(parameters.max_imfs):
        sifted = _sift(residual, parameters)
        if sifted is None:
            break
        imf, count, did_converge = sifted
        if float(np.std(imf)) <= np.finfo(np.float64).eps:
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
        method=method, status="valid", input_length=len(signal), sample_rate_hz=fs,
        imfs=tuple(imfs), residual=residual, valid_interval=ValidInterval(0, len(signal)),
        sift_iterations=tuple(iterations), converged=tuple(converged),
        reason=None if all(converged) else "maximum_sifts_reached",
    )


class PythonEMDImplementation:
    """仓库内纯 Python 实现；不是 EMD-signal/PyEMD 的包装或依赖。"""

    def emd(self, signal: FloatArray, sample_rate_hz: float, parameters: EMDParameters) -> EMDResult:
        return _emd(signal, sample_rate_hz, parameters)

    def eemd(
        self, signal: FloatArray, sample_rate_hz: float,
        parameters: EnsembleParameters, seed: int,
    ) -> EMDResult:
        scale = float(np.std(signal))
        if scale <= np.finfo(np.float64).eps:
            return _indeterminate("eemd", signal, sample_rate_hz, "zero_variance", seed)
        if parameters.noise_scale == 0.0:
            result = _emd(signal, sample_rate_hz, parameters.emd, method="eemd")
            return replace(result, seed=seed)
        normalized = signal / scale
        rng = np.random.default_rng(seed)
        members = []
        for _ in range(parameters.ensemble_size):
            noise = rng.normal(0.0, parameters.noise_scale, len(signal))
            result = _emd(normalized + noise, sample_rate_hz, parameters.emd)
            if result.imfs:
                members.append(result)
        if not members:
            return _indeterminate("eemd", signal, sample_rate_hz, "no_valid_ensemble_member", seed)
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
            method="eemd", status="valid", input_length=len(signal), sample_rate_hz=sample_rate_hz,
            imfs=tuple(imf * scale for imf in imfs), residual=residual * scale,
            valid_interval=ValidInterval(0, len(signal)), sift_iterations=tuple(iterations),
            converged=tuple(converged), seed=seed,
            reason=None if all(converged) else "maximum_sifts_reached",
        )

    def ceemdan(
        self, signal: FloatArray, sample_rate_hz: float,
        parameters: EnsembleParameters, seed: int,
    ) -> EMDResult:
        scale = float(np.std(signal))
        if scale <= np.finfo(np.float64).eps:
            return _indeterminate("ceemdan", signal, sample_rate_hz, "zero_variance", seed)
        if parameters.noise_scale == 0.0:
            result = _emd(signal, sample_rate_hz, parameters.emd, method="ceemdan")
            return replace(result, seed=seed)
        normalized = signal / scale
        rng = np.random.default_rng(seed)
        noise_modes = []
        for _ in range(parameters.ensemble_size):
            noise = rng.normal(0.0, 1.0, len(signal))
            result = _emd(noise, sample_rate_hz, parameters.emd)
            noise_modes.append(result.imfs)

        residual = normalized.copy()
        imfs = []
        iterations = []
        converged = []
        single_mode_parameters = replace(parameters.emd, max_imfs=1)
        for order in range(parameters.emd.max_imfs):
            local_means = []
            member_iterations = []
            member_converged = []
            source = normalized if order == 0 else residual
            amplitude = 1.0 if order == 0 else float(np.std(residual))
            for modes in noise_modes:
                if order >= len(modes) or np.std(modes[order]) <= np.finfo(np.float64).eps:
                    continue
                noise = parameters.noise_scale * amplitude * modes[order] / np.std(modes[order])
                trial = source + noise
                result = _emd(trial, sample_rate_hz, single_mode_parameters)
                if not result.imfs:
                    continue
                local_means.append(trial - result.imfs[0])
                member_iterations.append(result.sift_iterations[0])
                member_converged.append(result.converged[0])
            if not local_means:
                break
            local_mean = np.mean(local_means, axis=0)
            imf = residual - local_mean
            if np.std(imf) <= np.finfo(np.float64).eps:
                residual = local_mean
                break
            imfs.append(imf)
            iterations.append(max(member_iterations))
            converged.append(all(member_converged))
            residual = local_mean
            maxima, minima = _extrema(residual)
            if len(maxima) < 2 or len(minima) < 2:
                break
        if not imfs:
            return _indeterminate("ceemdan", signal, sample_rate_hz, "no_valid_ensemble_member", seed)
        return EMDResult(
            method="ceemdan", status="valid", input_length=len(signal), sample_rate_hz=sample_rate_hz,
            imfs=tuple(imf * scale for imf in imfs), residual=residual * scale,
            valid_interval=ValidInterval(0, len(signal)), sift_iterations=tuple(iterations),
            converged=tuple(converged), seed=seed,
            reason=None if all(converged) else "maximum_sifts_reached",
        )
