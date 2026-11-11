"""EMD 去噪业务参数和响应适配；数学分解、指标与选择全部由 Pipeline 执行。"""

import numpy as np
from app.algorithms.decomposition.emd import EMDParameters, EnsembleParameters
from app.algorithms.decomposition.selection import compute_component_metrics
from app.algorithms.pipelines.decomposition import (
    EMDDenoisingPipeline,
    require_representation,
)


def emd_denoise(
    signal,
    method="ceemdan",
    corr_threshold=0.35,
    kurt_threshold=3.5,
    max_imfs=8,
    ensemble_size=50,
    noise_std=0.2,
    use_rilling=False,
    use_pchip=True,
    *,
    seed=0,
):
    """去噪阈值为 excess 峭度，seed 显式可控；选择失败抛错，不返回假零信号。"""
    arr = np.asarray(signal, dtype=float)
    parameters = EMDParameters(
        max_imfs=max_imfs,
        interpolation="pchip" if use_pchip else "cubic",
        stopping_rule="rilling" if use_rilling else "sd",
    )
    pipeline = EMDDenoisingPipeline(
        parameters, EnsembleParameters(parameters, ensemble_size, noise_std)
    )
    analysis, selection = pipeline.run(
        arr,
        1.0,
        method=method,
        seed=seed,
        correlation_threshold=corr_threshold,
        kurtosis_threshold=kurt_threshold,
    )
    output = require_representation(selection)
    result = analysis.decomposition
    return output, {
        "method": method,
        "status": selection.status,
        "reason": result.reason,
        "n_imfs": len(result.imfs),
        "selected_imfs": list(selection.selected_indices),
        "imfs_info": [
            {
                "index": i,
                "corr": metric.correlation,
                "kurtosis": metric.kurtosis_excess,
                "selected": i in selection.selected_indices,
            }
            for i, metric in enumerate(analysis.metrics)
        ],
        "kurtosis_before": compute_component_metrics(arr, 1.0).kurtosis_excess,
        "kurtosis_after": compute_component_metrics(output, 1.0).kurtosis_excess,
        "kurtosis_kind": "excess",
        "seed": result.seed,
        "valid_interval": [0, len(arr)],
    }
