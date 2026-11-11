"""VMD 去噪业务参数适配；不再提供旧 tuple 分解或频率单位不明的入口。"""

import numpy as np
from app.algorithms.decomposition.vmd import VMDParameters
from app.algorithms.pipelines.decomposition import (
    VMDDenoisingPipeline,
    require_representation,
)


def vmd_denoise(
    signal,
    K=5,
    alpha=2000,
    corr_threshold=0.3,
    kurt_threshold=3.0,
    reference_signal=None,
):
    """Pearson 峭度去噪策略。完整长度数组入口拒绝超过 51200 点，禁止隐式截断补零。

    需要窗口分析时直接使用带 valid_interval 的 VMDDenoisingPipeline。
    这里不解释物理频率，1 Hz 仅标记无时间参数的内部相对轴。
    """
    arr = np.asarray(signal, dtype=float)
    if len(arr) > 51200:
        raise ValueError(
            "VMD 去噪输入超过 51200 点；请显式截取业务窗口或使用带有效区间的 Pipeline"
        )
    pipeline = VMDDenoisingPipeline(
        VMDParameters(modes=K, alpha=alpha, max_samples=None)
    )
    _, selection = pipeline.run(
        arr,
        1.0,
        reference_signal=reference_signal,
        correlation_threshold=corr_threshold,
        kurtosis_threshold=kurt_threshold,
    )
    return require_representation(selection)
