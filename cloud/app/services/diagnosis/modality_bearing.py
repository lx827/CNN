"""模态轴承分析业务适配，分解结果和敏感分量 Pipeline 保持 NumPy 表示。"""

import numpy as np
from app.algorithms.decomposition.emd import (
    EMDParameters,
    EnsembleParameters,
    decompose_emd,
    decompose_ceemdan,
)
from app.algorithms.decomposition.vmd import VMDParameters, decompose_vmd
from app.algorithms.pipelines.decomposition import SensitiveComponentEnvelopePipeline


def envelope_response(analysis, method, max_freq, **metadata):
    """仅在业务响应边界转换数组；展示截断不影响完整指标分析。"""
    if not np.isfinite(max_freq) or max_freq <= 0:
        raise ValueError("展示最大频率必须为有限正数")
    selection = analysis.selection
    common = {
        "method": method,
        "status": selection.status,
        "reason": selection.reason,
        "quality_status": selection.quality_status,
        "valid_interval": [
            selection.valid_interval.start_index,
            selection.valid_interval.stop_index,
        ],
        "amplitude_unit": "input_signal",
        "amplitude_scaling": "single_sided_peak_amplitude",
        **metadata,
    }
    if analysis.spectrum is None or selection.quality_status != "accepted":
        return {
            **common,
            "status": "indeterminate",
            "envelope_freq": [],
            "envelope_amp": [],
            "error": selection.reason or "no_eligible_components",
        }
    mask = analysis.spectrum.frequency_hz <= max_freq
    return {
        **common,
        "envelope_freq": analysis.spectrum.frequency_hz[mask].tolist(),
        "envelope_amp": analysis.spectrum.amplitude[mask].tolist(),
    }


def emd_bearing_analysis(
    signal,
    fs,
    max_imfs=8,
    max_sifts=50,
    top_n=1,
    f_low_pass=2000.0,
    max_freq=1000.0,
    use_rilling=False,
):
    """EMD 分解→原时间轴敏感 IMF→包络指标；未提供几何参数不命名轴承故障。"""
    arr = np.asarray(signal, dtype=float)
    arr = arr - np.mean(arr)
    result = decompose_emd(
        arr,
        fs,
        EMDParameters(
            max_imfs=max_imfs,
            max_sifts=max_sifts,
            stopping_rule="rilling" if use_rilling else "sd",
        ),
    )
    analysis = SensitiveComponentEnvelopePipeline().analyze(
        result.imfs,
        arr,
        fs,
        top_n=top_n,
        envelope_low_pass_hz=f_low_pass,
        decomposition=result,
    )
    return envelope_response(
        analysis,
        "EMD Sensitive IMF Envelope",
        max_freq,
        n_imfs=len(result.imfs),
        selected_imfs=list(analysis.selection.selected_indices),
        imf_scores=list(analysis.selection.scores),
        decomposition_reason=result.reason,
    )


def ceemdan_bearing_analysis(
    signal,
    fs,
    max_imfs=8,
    ensemble_size=30,
    noise_std=0.2,
    top_n=1,
    f_low_pass=2000.0,
    max_freq=1000.0,
    *,
    seed=0,
):
    """CEEMDAN 敏感 IMF；显式 seed 保证可复现，集成次数不证明效果稳定性。"""
    arr = np.asarray(signal, dtype=float)
    arr = arr - np.mean(arr)
    result = decompose_ceemdan(
        arr,
        fs,
        seed=seed,
        parameters=EnsembleParameters(
            EMDParameters(max_imfs=max_imfs), ensemble_size, noise_std
        ),
    )
    analysis = SensitiveComponentEnvelopePipeline().analyze(
        result.imfs,
        arr,
        fs,
        top_n=top_n,
        envelope_low_pass_hz=f_low_pass,
        decomposition=result,
    )
    return envelope_response(
        analysis,
        "CEEMDAN Sensitive IMF Envelope",
        max_freq,
        n_imfs=len(result.imfs),
        selected_imfs=list(analysis.selection.selected_indices),
        imf_scores=list(analysis.selection.scores),
        ensemble_size=ensemble_size,
        seed=seed,
        decomposition_reason=result.reason,
    )


def vmd_bearing_analysis(
    signal, fs, K=5, alpha=2000, top_n=1, f_low_pass=2000.0, max_freq=1000.0
):
    """VMD Hz 中心频率直接进入选择；只分析显式有效窗口，不补零尾部。"""
    arr = np.asarray(signal, dtype=float)
    arr = arr - np.mean(arr)
    result = decompose_vmd(arr, fs, VMDParameters(modes=K, alpha=alpha))
    interval = result.valid_interval
    analysis = SensitiveComponentEnvelopePipeline().analyze(
        result.modes,
        arr[interval.start_index : interval.stop_index],
        fs,
        top_n=top_n,
        center_frequencies_hz=result.center_frequencies_hz,
        envelope_low_pass_hz=f_low_pass,
        decomposition=result,
    )
    return envelope_response(
        analysis,
        "VMD Sensitive Mode Envelope",
        max_freq,
        K=K,
        selected_modes=list(analysis.selection.selected_indices),
        mode_scores=list(analysis.selection.scores),
        mode_center_freqs=result.center_frequencies_hz.tolist(),
        input_length=result.input_length,
        decomposition_reason=result.reason,
    )
