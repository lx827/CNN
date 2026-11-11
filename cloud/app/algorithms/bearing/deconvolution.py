"""MED 与 MCKD 纯数值解卷积及各自独立的包络 Pipeline。

MED 最大化全局归一化峭度，面向孤立冲击；MCKD 最大化带显式周期 T 的
相关峭度，面向周期冲击。二者不共享目标函数或故障周期假设。
"""
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from numpy.typing import NDArray
from scipy.signal import fftconvolve

from app.algorithms.bearing.envelope import EnvelopeRepresentation, compute_envelope
from app.algorithms.mechanics import BearingGeometry


@dataclass(frozen=True)
class MEDParameters:
    filter_length: int = 64
    max_iterations: int = 30
    tolerance: float = 1e-6
    ridge: float = 1e-8


@dataclass(frozen=True)
class MCKDParameters:
    target_fault: str
    target_frequency_hz: Optional[float] = None
    period_samples: Optional[int] = None
    filter_length: int = 64
    shift_order: int = 1
    max_iterations: int = 30
    tolerance: float = 1e-6
    ridge: float = 1e-8


@dataclass(frozen=True)
class DeconvolutionResult:
    signal: NDArray[np.float64]
    filter_coefficients: NDArray[np.float64]
    objective_history: tuple[float, ...]
    iterations: int
    converged: bool


@dataclass(frozen=True)
class DeconvolutionEnvelopeResult:
    status: str
    method: str
    representation: Optional[EnvelopeRepresentation]
    reason: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class _ZeroEnergyError(ValueError):
    """去均值后严格为零的输入或输出。"""


def _input_and_filter_length(signal, filter_length: int) -> tuple[np.ndarray, int, float]:
    arr = np.asarray(signal, dtype=np.float64)
    if arr.ndim != 1 or len(arr) < 64:
        raise ValueError("解卷积输入必须是一维且至少 64 点")
    if not np.all(np.isfinite(arr)):
        raise ValueError("输入信号不能包含 NaN 或无穷值")
    if isinstance(filter_length, bool) or not isinstance(filter_length, int) or filter_length < 2:
        raise ValueError("FIR 滤波器长度必须是至少为 2 的整数")
    if filter_length >= len(arr) // 2:
        raise ValueError("FIR 滤波器长度必须小于输入长度的一半")
    arr = arr - np.mean(arr)
    input_scale = float(np.max(np.abs(arr)))
    if input_scale == 0.0:
        raise _ZeroEnergyError("零能量信号无法解卷积")
    return arr, filter_length, input_scale


def normalized_kurtosis(values: NDArray[np.float64]) -> float:
    """E[y^4]/E[y^2]^2；不减 3，也不在迭代中做非线性去均值。"""
    y = np.asarray(values, dtype=np.float64)
    if y.ndim != 1 or len(y) < 2 or not np.all(np.isfinite(y)):
        raise ValueError("峭度输入必须是一维有限数组")
    scale = float(np.max(np.abs(y)))
    if scale == 0.0:
        raise _ZeroEnergyError("零能量输出无法计算峭度")
    normalized = y / scale
    power = float(np.mean(normalized**2))
    if power == 0.0 or not np.isfinite(power):
        raise ValueError("输出数值退化，无法计算峭度")
    return float(np.mean(normalized**4) / power**2)


def correlated_kurtosis(values: NDArray[np.float64], period: int, shift_order: int = 1) -> float:
    """CK_M=sum(beta_n^2)/(sum(y_n^2)^(M+1))，beta 为 M+1 个延迟输出之积。"""
    y = np.asarray(values, dtype=np.float64)
    if y.ndim != 1 or not np.all(np.isfinite(y)):
        raise ValueError("相关峭度输入必须是一维有限数组")
    if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
        raise ValueError("故障周期必须是正整数采样点")
    if isinstance(shift_order, bool) or not isinstance(shift_order, int) or shift_order < 1:
        raise ValueError("移位阶数必须是正整数")
    start = period * shift_order
    if len(y) <= start:
        raise ValueError("信号长度不足以覆盖指定周期和移位阶数")
    scale = float(np.max(np.abs(y)))
    if scale == 0.0:
        raise _ZeroEnergyError("零能量输出无法计算相关峭度")
    normalized = y / scale
    energy = float(np.sum(normalized**2))
    if energy == 0.0 or not np.isfinite(energy):
        raise ValueError("输出数值退化，无法计算相关峭度")
    shifted = [
        normalized[start - m * period: len(y) - m * period]
        for m in range(shift_order + 1)
    ]
    beta = np.prod(np.vstack(shifted), axis=0)
    return float(np.sum(beta**2) / energy ** (shift_order + 1))


def _solve_regularized_least_squares(
    X: NDArray[np.float64], target: NDArray[np.float64], ridge: float
) -> np.ndarray:
    """用 X 的 SVD 解 (X.T@X + ridge*I)f = X.T@target。

    ridge=0 时必须具有完整数值列秩；ridge>0 时所有零空间方向由正则化唯一确定。
    数值秩采用 LAPACK 常用的 eps*max(m,n)*sigma_max 判据，而非任意条件数阈值。
    """
    if not np.all(np.isfinite(target)):
        raise np.linalg.LinAlgError("解卷积正规方程右端包含非有限值")
    U, singular_values, Vt = np.linalg.svd(X, full_matrices=False)
    if len(singular_values) < X.shape[1] or not np.all(np.isfinite(singular_values)):
        raise np.linalg.LinAlgError("解卷积矩阵 SVD 数值退化")
    largest = float(singular_values[0])
    if largest == 0.0:
        raise np.linalg.LinAlgError("解卷积矩阵零能量，无法更新")
    rank_tolerance = np.finfo(np.float64).eps * max(X.shape) * largest
    numerical_rank = int(np.sum(singular_values > rank_tolerance))
    if ridge == 0.0 and numerical_rank < X.shape[1]:
        raise np.linalg.LinAlgError("无正则化解卷积矩阵数值秩亏，无法唯一更新")

    projected = U.T @ target
    if ridge == 0.0:
        factors = np.zeros_like(singular_values)
        np.divide(
            1.0,
            singular_values,
            out=factors,
            where=singular_values > rank_tolerance,
        )
    else:
        factors = singular_values / (singular_values**2 + float(ridge))
    return Vt.T @ (factors * projected)


def _mckd_filter_update(
    X: NDArray[np.float64],
    filter_coefficients: NDArray[np.float64],
    period: int,
    shift_order: int,
    ridge: float,
) -> np.ndarray:
    """McDonald(2012) 正规方程；显式使用留一乘积与 X_{mT} 延迟输入。"""
    y = X @ filter_coefficients
    start = period * shift_order
    valid = len(y) - start
    if valid <= 0:
        raise ValueError("卷积矩阵行数不足以覆盖 MCKD 延迟项")
    input_scale = float(np.max(np.abs(X)))
    if input_scale == 0.0 or not np.isfinite(input_scale):
        raise np.linalg.LinAlgError("MCKD 输入矩阵数值退化，无法更新")
    # 正规方程和 ridge 都作用于归一化输入；数学解与输入幅值尺度无关。
    X = X / input_scale
    y = y / input_scale
    shifted = [y[start - m * period: len(y) - m * period] for m in range(shift_order + 1)]
    beta = np.prod(np.vstack(shifted), axis=0)
    beta_energy = float(np.sum(beta**2))
    if beta_energy == 0.0 or not np.isfinite(beta_energy):
        raise np.linalg.LinAlgError("MCKD 周期乘积为零或数值退化，无法更新")

    target = np.zeros(X.shape[0], dtype=np.float64)
    for m in range(shift_order + 1):
        # 不执行 beta/y 除法：零输出附近直接计算留一乘积，数值稳定且符合定义。
        leave_one = np.ones(valid, dtype=np.float64)
        for k in range(shift_order + 1):
            if k != m:
                leave_one *= shifted[k]
        alpha_m = beta * leave_one
        # X_{mT}.T@alpha_m 等价于把 alpha_m 填回对应的延迟行后取 X.T@target。
        target[start - m * period: len(X) - m * period] += alpha_m

    target *= float(np.sum(y**2)) / (2.0 * beta_energy)
    return _solve_regularized_least_squares(X, target, ridge)


def _validate_iterations(max_iterations: int, tolerance: float, ridge: float) -> None:
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise ValueError("最大迭代次数必须是正整数")
    if not np.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("收敛容差必须为有限正数")
    if not np.isfinite(ridge) or ridge < 0:
        raise ValueError("正则化系数必须为有限非负数")


def _same_length_output(x: np.ndarray, coefficients: np.ndarray) -> np.ndarray:
    # X@f 是互相关形式，等价于与反转 FIR 系数卷积。
    return fftconvolve(x, coefficients[::-1], mode="same")


def minimum_entropy_deconvolution(
    signal: NDArray[np.float64], parameters: Optional[MEDParameters] = None
) -> DeconvolutionResult:
    """Wiggins MED / Endo-Randall 迭代，目标仅为全局归一化峭度。"""
    params = parameters or MEDParameters()
    _validate_iterations(params.max_iterations, params.tolerance, params.ridge)
    x, length, input_scale = _input_and_filter_length(signal, params.filter_length)
    X = sliding_window_view(x / input_scale, length)
    f = np.zeros(length)
    f[length // 2] = 1.0
    best_f = f.copy()
    best_objective = -np.inf
    history = []
    converged = False
    iterations = 0
    for iteration in range(params.max_iterations):
        iterations = iteration + 1
        y = X @ f
        objective = normalized_kurtosis(y)
        history.append(objective)
        if objective > best_objective:
            best_objective = objective
            best_f = f.copy()
        if len(history) > 1 and abs(history[-1] - history[-2]) <= params.tolerance * max(1.0, abs(history[-2])):
            converged = True
            break
        energy = float(np.sum(y**2))
        fourth = float(np.sum(y**4))
        if fourth == 0.0 or not np.isfinite(fourth):
            raise np.linalg.LinAlgError("MED 四阶矩为零或数值退化，无法更新")
        target = (energy / fourth) * y**3
        try:
            updated = _solve_regularized_least_squares(X, target, params.ridge)
        except np.linalg.LinAlgError as exc:
            raise np.linalg.LinAlgError("MED 最小二乘更新数值退化，无法更新") from exc
        norm = float(np.linalg.norm(updated))
        if not np.isfinite(norm) or norm == 0.0:
            raise np.linalg.LinAlgError("MED 滤波器更新为零或非有限值")
        f = updated / norm
    return DeconvolutionResult(_same_length_output(x, best_f), best_f, tuple(history), iterations, converged)


def maximum_correlated_kurtosis_deconvolution(
    signal: NDArray[np.float64], period_samples: int, parameters: Optional[MCKDParameters] = None
) -> DeconvolutionResult:
    """McDonald(2012) MCKD；period_samples 必须来自显式目标，不得默认。"""
    params = parameters or MCKDParameters(target_fault="CUSTOM_PERIOD", period_samples=period_samples)
    _validate_iterations(params.max_iterations, params.tolerance, params.ridge)
    if isinstance(period_samples, bool) or not isinstance(period_samples, int) or period_samples <= 0:
        raise ValueError("MCKD 故障周期必须是正整数采样点")
    if isinstance(params.shift_order, bool) or not isinstance(params.shift_order, int) or params.shift_order < 1:
        raise ValueError("MCKD 移位阶数必须是正整数")
    x, length, input_scale = _input_and_filter_length(signal, params.filter_length)
    X = sliding_window_view(x / input_scale, length)
    if len(X) <= period_samples * params.shift_order + 1:
        raise ValueError("输入长度不足以覆盖 MCKD 故障周期和移位阶数")
    f = np.zeros(length)
    f[length // 2] = 1.0
    best_f = f.copy()
    best_objective = -np.inf
    history = []
    converged = False
    iterations = 0
    for iteration in range(params.max_iterations):
        iterations = iteration + 1
        y = X @ f
        objective = correlated_kurtosis(y, period_samples, params.shift_order)
        history.append(objective)
        if objective > best_objective:
            best_objective = objective
            best_f = f.copy()
        if len(history) > 1 and abs(history[-1] - history[-2]) <= params.tolerance * max(1.0, abs(history[-2])):
            converged = True
            break
        try:
            updated = _mckd_filter_update(X, f, period_samples, params.shift_order, params.ridge)
        except np.linalg.LinAlgError as exc:
            raise np.linalg.LinAlgError("MCKD 正规方程数值退化，无法更新") from exc
        norm = float(np.linalg.norm(updated))
        if not np.isfinite(norm) or norm == 0.0:
            raise np.linalg.LinAlgError("MCKD 滤波器更新为零或非有限值")
        f = updated / norm
    return DeconvolutionResult(_same_length_output(x, best_f), best_f, tuple(history), iterations, converged)


class MEDEnvelopePipeline:
    method = "MED (isolated-impulse normalized kurtosis) + Envelope"

    def run(self, signal, sample_rate_hz: float, parameters: Optional[MEDParameters] = None) -> DeconvolutionEnvelopeResult:
        params = parameters or MEDParameters()
        try:
            result = minimum_entropy_deconvolution(signal, params)
        except _ZeroEnergyError:
            return DeconvolutionEnvelopeResult(
                status="indeterminate", method=self.method, representation=None, reason="zero_energy"
            )
        except np.linalg.LinAlgError:
            return DeconvolutionEnvelopeResult(
                status="indeterminate",
                method=self.method,
                representation=None,
                reason="numerical_deconvolution_failure",
            )
        representation = compute_envelope(result.signal, sample_rate_hz)
        return DeconvolutionEnvelopeResult(
            status="computed",
            method=self.method,
            representation=representation,
            metadata={
                "objective": "normalized_kurtosis",
                "objective_history": result.objective_history,
                "iterations": result.iterations,
                "converged": result.converged,
            },
        )


class MCKDEnvelopePipeline:
    method = "MCKD (explicit periodic-impact correlated kurtosis) + Envelope"

    def run(
        self,
        signal,
        sample_rate_hz: float,
        parameters: MCKDParameters,
        geometry: Optional[BearingGeometry] = None,
        rot_frequency_hz: Optional[float] = None,
    ) -> DeconvolutionEnvelopeResult:
        if parameters.target_fault not in {"BPFO", "BPFI", "BSF", "FTF"}:
            raise ValueError("MCKD 目标故障必须是 BPFO/BPFI/BSF/FTF")
        target_frequency = parameters.target_frequency_hz
        if target_frequency is None and geometry is not None and rot_frequency_hz is not None:
            target_frequency = geometry.fault_frequencies(rot_frequency_hz)[parameters.target_fault]
        period = parameters.period_samples
        if target_frequency is None and period is None:
            return DeconvolutionEnvelopeResult(
                status="indeterminate",
                method=self.method,
                representation=None,
                reason="missing_target_frequency_or_period",
            )
        if target_frequency is not None and (not np.isfinite(target_frequency) or target_frequency <= 0):
            raise ValueError("MCKD 目标故障频率必须为有限正数")
        if (target_frequency is not None and target_frequency > sample_rate_hz / 2
                or period is not None and period < 2):
            return DeconvolutionEnvelopeResult(
                status="indeterminate", method=self.method, representation=None,
                reason="target_above_analysis_bandwidth",
            )
        if period is not None and target_frequency is not None and period != int(round(sample_rate_hz / target_frequency)):
            raise ValueError("MCKD 显式频率与采样周期不一致")
        if period is None:
            period = int(round(sample_rate_hz / target_frequency))
        try:
            result = maximum_correlated_kurtosis_deconvolution(signal, period, parameters)
        except _ZeroEnergyError:
            return DeconvolutionEnvelopeResult(
                status="indeterminate", method=self.method, representation=None, reason="zero_energy"
            )
        except np.linalg.LinAlgError:
            return DeconvolutionEnvelopeResult(
                status="indeterminate",
                method=self.method,
                representation=None,
                reason="numerical_deconvolution_failure",
            )
        representation = compute_envelope(result.signal, sample_rate_hz)
        return DeconvolutionEnvelopeResult(
            status="computed",
            method=self.method,
            representation=representation,
            metadata={
                "objective": "correlated_kurtosis_squared_periodic_product",
                "target_fault": parameters.target_fault,
                "target_frequency_hz": target_frequency,
                "period_samples": period,
                "shift_order": parameters.shift_order,
                "objective_history": result.objective_history,
                "iterations": result.iterations,
                "converged": result.converged,
            },
        )
