"""MED 与 MCKD 纯数值解卷积及各自独立的包络 Pipeline。

MED 最大化全局归一化峭度，面向孤立冲击；MCKD 最大化带显式周期 T 的
相关峭度，面向周期冲击。二者不共享目标函数或故障周期假设。
"""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from cnn_compute import diagnostic as native_diagnostic
from numpy.typing import NDArray

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


def normalized_kurtosis(values):
    """E[y^4]/E[y^2]^2；原生缩放归约，不减3。"""
    try:
        return native_diagnostic.normalized_kurtosis(values)
    except ValueError as error:
        if "零能量" in str(error):
            raise _ZeroEnergyError(str(error)) from error
        raise


def correlated_kurtosis(values, period, shift_order=1):
    """平方周期乘积相关峭度，周期和移位阶数显式提供。"""
    try:
        return native_diagnostic.correlated_kurtosis(values, period, shift_order)
    except ValueError as error:
        if "零能量" in str(error):
            raise _ZeroEnergyError(str(error)) from error
        raise


def _mckd_filter_update(X, filter_coefficients, period, shift_order, ridge):
    """独立更新原语复用完整MCKD的同一原生留一乘积/薄SVD实现。"""
    return native_diagnostic.mckd_update(
        X, filter_coefficients, period, shift_order, ridge
    )


def minimum_entropy_deconvolution(signal, parameters=None) -> DeconvolutionResult:
    """MED全局归一化峭度；固定设计矩阵只在C++准备一次薄SVD。"""
    params = parameters or MEDParameters()
    try:
        output, coefficients, history, iterations, converged = (
            native_diagnostic.deconvolve(
                signal,
                filter_length=params.filter_length,
                max_iterations=params.max_iterations,
                tolerance=params.tolerance,
                ridge=params.ridge,
            )
        )
    except ValueError as error:
        if "零能量" in str(error):
            raise _ZeroEnergyError(str(error)) from error
        raise
    return DeconvolutionResult(
        output, coefficients, tuple(history), iterations, converged
    )


def maximum_correlated_kurtosis_deconvolution(
    signal, period_samples, parameters=None
) -> DeconvolutionResult:
    """MCKD显式周期留一乘积更新；全部迭代复用一次薄SVD。"""
    params = parameters or MCKDParameters(
        target_fault="CUSTOM_PERIOD", period_samples=period_samples
    )
    if (
        isinstance(period_samples, bool)
        or not isinstance(period_samples, int)
        or period_samples <= 0
    ):
        raise ValueError("MCKD故障周期必须是正整数采样点")
    try:
        output, coefficients, history, iterations, converged = (
            native_diagnostic.deconvolve(
                signal,
                filter_length=params.filter_length,
                max_iterations=params.max_iterations,
                tolerance=params.tolerance,
                ridge=params.ridge,
                period=period_samples,
                shift_order=params.shift_order,
            )
        )
    except ValueError as error:
        if "零能量" in str(error):
            raise _ZeroEnergyError(str(error)) from error
        raise
    return DeconvolutionResult(
        output, coefficients, tuple(history), iterations, converged
    )


class MEDEnvelopePipeline:
    method = "MED (isolated-impulse normalized kurtosis) + Envelope"

    def run(
        self, signal, sample_rate_hz: float, parameters: Optional[MEDParameters] = None
    ) -> DeconvolutionEnvelopeResult:
        params = parameters or MEDParameters()
        try:
            result = minimum_entropy_deconvolution(signal, params)
        except _ZeroEnergyError:
            return DeconvolutionEnvelopeResult(
                status="indeterminate",
                method=self.method,
                representation=None,
                reason="zero_energy",
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
        if (
            target_frequency is None
            and geometry is not None
            and rot_frequency_hz is not None
        ):
            target_frequency = geometry.fault_frequencies(rot_frequency_hz)[
                parameters.target_fault
            ]
        period = parameters.period_samples
        if target_frequency is None and period is None:
            return DeconvolutionEnvelopeResult(
                status="indeterminate",
                method=self.method,
                representation=None,
                reason="missing_target_frequency_or_period",
            )
        if target_frequency is not None and (
            not np.isfinite(target_frequency) or target_frequency <= 0
        ):
            raise ValueError("MCKD 目标故障频率必须为有限正数")
        if (
            target_frequency is not None
            and target_frequency > sample_rate_hz / 2
            or period is not None
            and period < 2
        ):
            return DeconvolutionEnvelopeResult(
                status="indeterminate",
                method=self.method,
                representation=None,
                reason="target_above_analysis_bandwidth",
            )
        if (
            period is not None
            and target_frequency is not None
            and period != int(round(sample_rate_hz / target_frequency))
        ):
            raise ValueError("MCKD 显式频率与采样周期不一致")
        if period is None:
            period = int(round(sample_rate_hz / target_frequency))
        try:
            result = maximum_correlated_kurtosis_deconvolution(
                signal, period, parameters
            )
        except _ZeroEnergyError:
            return DeconvolutionEnvelopeResult(
                status="indeterminate",
                method=self.method,
                representation=None,
                reason="zero_energy",
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
