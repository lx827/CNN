"""VMD C++ 结果的领域适配；不在 Python 重算模态、筛选或迭代。"""

from cnn_compute.vmd import decompose

from ..types import ValidInterval
from .core import VMDResult


class NativeVMDImplementation:
    """默认 ADMM 实现；保留 Hz、有效窗口与未收敛原因。"""

    def vmd(self, signal, sample_rate_hz, parameters):
        result = decompose(
            signal, sample_rate_hz, modes=parameters.modes, alpha=parameters.alpha,
            tau=parameters.tau, tolerance=parameters.tolerance,
            max_iterations=parameters.max_iterations, dc=parameters.dc,
            max_samples=parameters.max_samples,
        )
        return VMDResult(
            status=result.status, input_length=result.input_length,
            sample_rate_hz=sample_rate_hz, modes=result.modes,
            center_frequencies_hz=result.center_frequencies_hz,
            center_frequency_history_hz=result.center_frequency_history_hz,
            residual=result.residual, valid_interval=ValidInterval(0, result.valid_length),
            iterations=result.iterations, converged=result.converged, reason=result.reason,
        )
