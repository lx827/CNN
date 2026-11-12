"""本地 emd 0.8.1 集成语义的参数/噪声适配；全部分解循环在 C++。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from ._native import emd as _emd

if TYPE_CHECKING:
    from .emd import Decomposition, FloatArray


def _noise(nensembles, samples, noise_seed, nprocesses):
    if isinstance(nensembles, bool) or not isinstance(nensembles, int) or nensembles <= 0:
        raise ValueError("nensembles 必须为正整数")
    if isinstance(nprocesses, bool) or not isinstance(nprocesses, int) or nprocesses != 1:
        raise ValueError("原生集成调用只支持 nprocesses=1；并发由上层调度")
    # 与 np.random.seed(seed)/randn 的 legacy 序列一致，避免修改全局 RNG。
    return np.random.RandomState(noise_seed).standard_normal((nensembles, samples))


def ensemble_sift_detailed(
    signal,
    *,
    nensembles=4,
    ensemble_noise=0.2,
    noise_mode="single",
    noise_seed=None,
    nprocesses=1,
    sift_thresh=1e-8,
    max_imfs=None,
    imf_opts=None,
    envelope_opts=None,
    extrema_opts=None,
) -> Decomposition:
    """返回各列独立拥有的 EEMD 结果，迭代数为空而不伪造聚合收敛次数。

    仅生成一份 [nensembles,samples] legacy 标准正态噪声；合规输入和噪声
    在原生调用期间只读借用。正负噪声筛分、选模态数和聚合全部在 C++。
    noise_seed=None 创建独立随机源，不消费全局 np.random 状态。
    """
    from .emd import _options, _result, _signal

    values = _signal(signal)
    options = _emd.EnsembleOptions()
    options.sift = _options(
        max_imfs=max_imfs,
        sift_thresh=sift_thresh,
        imf_opts=imf_opts,
        envelope_opts=envelope_opts,
        extrema_opts=extrema_opts,
    )
    options.nensembles = nensembles
    options.ensemble_noise = ensemble_noise
    if noise_mode not in {"single", "flip"}:
        raise ValueError("noise_mode 只支持 single 或 flip")
    options.noise_mode = getattr(_emd.NoiseMode, noise_mode)
    noise = _noise(nensembles, len(values), noise_seed, nprocesses)
    return _result(_emd.ensemble_sift(values, noise, options), len(values))


def ensemble_sift(
    signal,
    nensembles=4,
    ensemble_noise=0.2,
    noise_mode="single",
    noise_seed=None,
    nprocesses=1,
    sift_thresh=1e-8,
    max_imfs=None,
    *,
    imf_opts=None,
    envelope_opts=None,
    extrema_opts=None,
) -> FloatArray:
    """返回 [samples,components]；二维组装复制一次，detailed 可避免该复制。

    相同显式 seed 可重复；不会修改全局 RNG。nprocesses 只允许 1。
    迭代耗尽或数值失败抛 ConvergenceError，不返回假成功。
    """
    from .emd import _require_success

    result = ensemble_sift_detailed(
        signal,
        nensembles=nensembles,
        ensemble_noise=ensemble_noise,
        noise_mode=noise_mode,
        noise_seed=noise_seed,
        nprocesses=nprocesses,
        sift_thresh=sift_thresh,
        max_imfs=max_imfs,
        imf_opts=imf_opts,
        envelope_opts=envelope_opts,
        extrema_opts=extrema_opts,
    )
    _require_success(result)
    return result.as_array()


def complete_ensemble_sift_detailed(
    signal,
    *,
    nensembles=4,
    ensemble_noise=0.2,
    nprocesses=1,
    noise_seed=None,
    sift_thresh=1e-8,
    energy_thresh=50,
    rilling_thresh=None,
    max_imfs=None,
    imf_opts=None,
    envelope_opts=None,
    extrema_opts=None,
) -> Decomposition:
    """返回 complete ensemble 的独立结果列，保留 emd 0.8.1 公式与边界。

    噪声逐行 zscore、噪声全分解和逐层局部均值计算均位于 C++。
    最后一列是残差；max_imfs 保留上游检查位置，不重新解释为严格列上限。
    噪声模态不足抛 IndexError，不补零；常量输入返回 numerical_failure。
    """
    from .emd import _options, _result, _signal

    values = _signal(signal)
    options = _emd.CompleteEnsembleOptions()
    options.sift = _options(
        max_imfs,
        sift_thresh,
        energy_thresh,
        rilling_thresh,
        imf_opts,
        envelope_opts,
        extrema_opts,
    )
    options.nensembles = nensembles
    options.ensemble_noise = ensemble_noise
    noise = _noise(nensembles, len(values), noise_seed, nprocesses)
    return _result(_emd.complete_ensemble_sift(values, noise, options), len(values))


def complete_ensemble_sift(
    signal,
    nensembles=4,
    ensemble_noise=0.2,
    nprocesses=1,
    noise_seed=None,
    sift_thresh=1e-8,
    energy_thresh=50,
    rilling_thresh=None,
    max_imfs=None,
    *,
    imf_opts=None,
    envelope_opts=None,
    extrema_opts=None,
) -> FloatArray:
    """返回 [samples,components]，末列残差，二维组装包含一次复制。

    固定 seed 使用独立 legacy RNG，原生循环释放 GIL，不创建内部线程。
    迭代/数值失败抛 ConvergenceError；上游噪声层越界保留为 IndexError。
    """
    from .emd import _require_success

    result = complete_ensemble_sift_detailed(
        signal,
        nensembles=nensembles,
        ensemble_noise=ensemble_noise,
        nprocesses=nprocesses,
        noise_seed=noise_seed,
        sift_thresh=sift_thresh,
        energy_thresh=energy_thresh,
        rilling_thresh=rilling_thresh,
        max_imfs=max_imfs,
        imf_opts=imf_opts,
        envelope_opts=envelope_opts,
        extrema_opts=extrema_opts,
    )
    _require_success(result)
    return result.as_array()
