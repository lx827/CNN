"""Hyvärinen 固定点 symmetric FastICA，明确秩、白化、收敛与逆映射。"""

from dataclasses import dataclass

import numpy as np
from cnn_compute import diagnostic as native_diagnostic


@dataclass(frozen=True)
class FastICAParameters:
    components: int | None = None
    max_iterations: int = 200
    tolerance: float = 1e-6
    seed: int = 0

    def __post_init__(self):
        if self.components is not None and (
            isinstance(self.components, bool)
            or not isinstance(self.components, int)
            or self.components < 1
        ):
            raise ValueError("ICA components must be a positive integer or None")
        if (
            isinstance(self.max_iterations, bool)
            or not isinstance(self.max_iterations, int)
            or self.max_iterations < 1
        ):
            raise ValueError("ICA max_iterations must be positive")
        if not np.isfinite(self.tolerance) or self.tolerance <= 0:
            raise ValueError("ICA tolerance must be positive")


@dataclass(frozen=True)
class FastICAResult:
    status: str
    components: np.ndarray | None
    mixing: np.ndarray | None
    unmixing: np.ndarray | None
    mean: np.ndarray
    numerical_rank: int
    iterations: int
    converged: bool
    reason: str | None = None

    def reconstruct(self, indices):
        """回到观测通道的输入单位，不直接累加任意尺度的独立分量。"""
        if self.components is None or self.mixing is None:
            raise ValueError(self.reason or "ICA representation unavailable")
        selected = tuple(indices)
        if len(set(selected)) != len(selected) or any(
            not isinstance(i, (int, np.integer))
            or i < 0
            or i >= self.components.shape[1]
            for i in selected
        ):
            raise ValueError("invalid ICA component selection")
        if not selected:
            return np.zeros((len(self.components), len(self.mean)))
        return self.components[:, selected] @ self.mixing[:, selected].T


def compute_fast_ica(observations, parameters=FastICAParameters()):
    """原生logcosh symmetric FastICA，保留SVD秩与逆映射单位。

    seed在原生实现内可重复；不锁定NumPy随机序列或分量符号/排列。
    """
    components, mixing, unmixing, mean, rank, iterations, state = (
        native_diagnostic.fast_ica(
            observations,
            components=parameters.components or 0,
            max_iterations=parameters.max_iterations,
            tolerance=parameters.tolerance,
            seed=parameters.seed,
        )
    )
    if state in (2, 3):
        reason = (
            "rank_deficient_observations"
            if state == 2
            else "singular_ICA_fixed_point_update"
        )
        return FastICAResult(
            "indeterminate", None, None, None, mean, rank, iterations, False, reason
        )
    converged = state == 0
    return FastICAResult(
        "computed" if converged else "approximate",
        components,
        mixing,
        unmixing,
        mean,
        rank,
        iterations,
        converged,
        None if converged else "ICA_not_converged",
    )
