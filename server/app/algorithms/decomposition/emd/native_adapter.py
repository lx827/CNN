"""默认完整原生 EMD 族；Python 仅映射配置、单位与结果状态。"""

from cnn_compute.emd_family import decompose

from ..types import ValidInterval
from .core import EMDResult


def _decompose(signal, sample_rate_hz, parameters, method, *, ensemble=None, seed=None):
    result = decompose(
        signal,
        method=method,
        max_imfs=parameters.max_imfs,
        max_sifts=parameters.max_sifts,
        mirror_extrema=parameters.mirror_extrema,
        sd_threshold=parameters.sd_threshold,
        interpolation=parameters.interpolation,
        stopping_rule=parameters.stopping_rule,
        rilling_thresholds=parameters.rilling_thresholds,
        **(
            {
                "ensemble_size": ensemble.ensemble_size,
                "noise_scale": ensemble.noise_scale,
                "seed": seed,
            }
            if ensemble is not None
            else {}
        ),
    )
    return EMDResult(
        method=method,
        status=result.status,
        input_length=len(signal),
        sample_rate_hz=sample_rate_hz,
        imfs=result.imfs,
        residual=result.residual,
        valid_interval=ValidInterval(0, len(signal)),
        sift_iterations=result.sift_iterations,
        converged=result.converged,
        seed=seed,
        reason=result.reason,
    )


class NativeEMDImplementation:
    """归一化、筛分、多 IMF、原生 RNG 与 EEMD/Torres CEEMDAN 均在 C++。

    不回退 Python，不替换为不同公式的 emd.sift 0.8.1 家族。
    """

    def emd(self, signal, sample_rate_hz, parameters):
        return _decompose(signal, sample_rate_hz, parameters, "emd")

    def eemd(self, signal, sample_rate_hz, parameters, seed):
        return _decompose(
            signal,
            sample_rate_hz,
            parameters.emd,
            "eemd",
            ensemble=parameters,
            seed=seed,
        )

    def ceemdan(self, signal, sample_rate_hz, parameters, seed):
        return _decompose(
            signal,
            sample_rate_hz,
            parameters.emd,
            "ceemdan",
            ensemble=parameters,
            seed=seed,
        )
