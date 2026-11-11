"""Hyvärinen 固定点 symmetric FastICA，明确秩、白化、收敛与逆映射。"""

from dataclasses import dataclass

import numpy as np


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
    """X 为 samples×observations；S白化到单位方差，A保存物理尺度。

    使用SVD数值秩 eps*max(shape)*σmax；不以正则项把缺失观测维度伪造成可分离源。
    logcosh 固定点更新 g=tanh，symmetric decorrelation W←(WWᵀ)^(-1/2)W。
    """
    values = np.asarray(observations, dtype=float)
    if values.ndim != 2 or min(values.shape) < 2 or not np.all(np.isfinite(values)):
        raise ValueError(
            "ICA requires finite samples×channels with both dimensions >=2"
        )
    if values.shape[1] > 32:
        raise ValueError("ICA observation count exceeds bounded research workload")
    mean = np.mean(values, axis=0)
    centered = values - mean
    _, singular, vt = np.linalg.svd(centered, full_matrices=False)
    tolerance = np.finfo(float).eps * max(centered.shape) * singular[0]
    rank = int(np.count_nonzero(singular > tolerance))
    count = (
        parameters.components if parameters.components is not None else values.shape[1]
    )
    if count > rank:
        return FastICAResult(
            "indeterminate",
            None,
            None,
            None,
            mean,
            rank,
            0,
            False,
            "rank_deficient_observations",
        )
    whitening = vt[:count].T * (np.sqrt(len(values)) / singular[:count])
    z = centered @ whitening
    rng = np.random.default_rng(parameters.seed)
    w = rng.standard_normal((count, count))
    u, _, v = np.linalg.svd(w, full_matrices=False)
    w = u @ v
    converged = False
    for iteration in range(1, parameters.max_iterations + 1):
        projection = z @ w.T
        g = np.tanh(projection)
        update = g.T @ z / len(z) - np.mean(1 - g**2, axis=0)[:, None] * w
        u, singular_update, vt_update = np.linalg.svd(update, full_matrices=False)
        if (
            not np.all(np.isfinite(singular_update))
            or singular_update[-1] <= np.finfo(float).eps * count * singular_update[0]
        ):
            return FastICAResult(
                "indeterminate",
                None,
                None,
                None,
                mean,
                rank,
                iteration,
                False,
                "singular_ICA_fixed_point_update",
            )
        updated = u @ vt_update
        change = float(np.max(np.abs(np.abs(np.diag(updated @ w.T)) - 1)))
        w = updated
        if change < parameters.tolerance:
            converged = True
            break
    unmixing = w @ whitening.T
    components = centered @ unmixing.T
    mixing = np.linalg.pinv(unmixing)
    return FastICAResult(
        "computed" if converged else "approximate",
        components,
        mixing,
        unmixing,
        mean,
        rank,
        iteration,
        converged,
        None if converged else "ICA_not_converged",
    )
