"""仅基准使用的 EMD-signal 1.9.0 参照；不是生产默认实现。

保留库本身的筛分/停止语义。参数名字相近不等于公式相同，因此不实现
生产 EMDImplementation，也不为库未报告的每 IMF 收敛状态填写 True。
"""

from dataclasses import dataclass

import numpy as np
from PyEMD import CEEMDAN, EEMD, EMD


@dataclass(frozen=True)
class ReferenceDecomposition:
    components: np.ndarray
    residual: np.ndarray
    metadata: dict


def decompose(signal, sample_rate_hz, method, parameters, ensemble, seed):
    """float64 原时间轴；显式串行、固定噪声种子，返回库原始残差。

    EEMD 的 noise_width 以输入峰峰值为基准，转换为仓库的 std 比例。
    CEEMDAN 的 epsilon 以 std 为基准；库使用 improved CEEMDAN 局部均值公式，
    与仓库 Torres 2011 公式不同，不宣称逐模态等价。库 CEEMDAN 返回的最后
    一行是最终残差，将其从 IMF 中分离，而非误记为又一个振荡模态。
    """
    emd = EMD(
        spline_kind=parameters["interpolation"],
        nbsym=parameters["mirror_extrema"],
        extrema_detection="parabol",
        std_thr=parameters["sd_threshold"],
        MAX_ITERATION=parameters["max_sifts"],
        DTYPE=np.float64,
    )
    time_s = np.arange(len(signal), dtype=np.float64) / sample_rate_hz
    metadata = {
        "parallel": False,
        "reported_convergence": None,
        "reported_sift_iterations": None,
        "stopping_semantics": "PyEMD native multi-test; not repository SD/Rilling",
    }
    if method == "emd":
        emd.emd(signal, time_s, max_imf=parameters["max_imfs"])
        modes, residual = emd.get_imfs_and_residue()
    elif method == "eemd":
        width = ensemble["noise_scale"] * np.std(signal) / np.ptp(signal)
        instance = EEMD(
            trials=ensemble["ensemble_size"],
            noise_width=width,
            ext_EMD=emd,
            parallel=False,
        )
        instance.noise_seed(seed)
        instance.eemd(signal, time_s, max_imf=parameters["max_imfs"])
        modes, residual = instance.get_imfs_and_residue()
        metadata["noise_width_range_fraction"] = float(width)
        metadata["noise_std_input_fraction"] = ensemble["noise_scale"]
    elif method == "ceemdan":
        instance = CEEMDAN(
            trials=ensemble["ensemble_size"],
            epsilon=ensemble["noise_scale"],
            ext_EMD=emd,
            parallel=False,
            beta_progress=True,
        )
        instance.noise_seed(seed)
        rows = instance.ceemdan(signal, time_s, max_imf=parameters["max_imfs"])
        modes, residual = rows[:-1], rows[-1].copy()
        metadata["formula"] = "PyEMD improved CEEMDAN local mean; beta_progress=True"
    else:
        raise ValueError(method)
    return ReferenceDecomposition(modes, residual, metadata)
