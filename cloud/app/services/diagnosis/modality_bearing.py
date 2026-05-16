"""
模态分解轴承故障诊断模块 (Modality-based Bearing Diagnosis)

基于 EMD/CEEMDAN/VMD 分解的轴承诊断方法:
1. 信号分解 → IMF/mode 列表
2. 敏感分量选择（综合评分: 峭度+相关性+包络熵+能量+频率匹配）
3. 对敏感分量做 Hilbert 包络分析
4. 包络谱故障特征频率匹配

参考: wavelet_and_modality_decomposition.md §11

与 emd_denoise.py 的区别:
- emd_denoise.py: 降噪（筛去低相关/低峭度 IMF，重构降噪信号）
- 本模块: 诊断（选最敏感 IMF → 包络谱 → 故障频率匹配）

返回格式与 bearing.py 现有方法一致:
    {envelope_freq, envelope_amp, method, ...}
"""
import numpy as np
from typing import Dict, List, Optional

from .signal_utils import remove_dc, lowpass_filter
from .sensitive_selector import select_emd_sensitive_imfs, select_vmd_sensitive_modes


# ═══════════════════════════════════════════════════════════
# 共用包络谱计算
# ═══════════════════════════════════════════════════════════

def _compute_envelope_spectrum(
    signal: np.ndarray,
    fs: float,
    f_low_pass: float = 2000.0,
    max_freq: float = 1000.0,
) -> Dict:
    """Hilbert 包络 → 低通 → FFT 包络谱"""
    from scipy.signal import hilbert
    from scipy.fft import rfft, rfftfreq

    N = len(signal)
    analytic = hilbert(signal)
    envelope = np.abs(analytic)
    envelope = envelope - np.mean(envelope)

    if f_low_pass < fs / 2:
        envelope = lowpass_filter(envelope, fs, f_low_pass)

    yf = np.abs(rfft(envelope))
    xf = rfftfreq(N, 1.0 / fs)

    freq_list = [f for f, a in zip(xf, yf) if f <= max_freq]
    amp_list = [a for f, a in zip(xf, yf) if f <= max_freq]

    return {"envelope_freq": freq_list, "envelope_amp": amp_list}


def _reconstruct_selected_components(
    components: List[np.ndarray],
    indices: List[int],
    target_length: int,
) -> np.ndarray:
    """从选中分量重构窄带信号"""
    selected = [components[i] for i in indices if i < len(components)]
    if not selected:
        return np.zeros(target_length)
    reconstructed = np.sum(selected, axis=0)
    if len(reconstructed) < target_length:
        out = np.zeros(target_length)
        out[:len(reconstructed)] = reconstructed
        return out
    return reconstructed[:target_length]


# ═══════════════════════════════════════════════════════════
# EMD 轴承诊断
# ═══════════════════════════════════════════════════════════

def emd_bearing_analysis(
    signal: np.ndarray,
    fs: float,
    max_imfs: int = 8,
    max_sifts: int = 50,
    top_n: int = 1,
    f_low_pass: float = 2000.0,
    max_freq: float = 1000.0,
    use_rilling: bool = False,
) -> Dict:
    """
    EMD 敏感 IMF 轴承诊断（§11.2 + §11.3）

    流程:
    1. EMD 分解 → IMF 列表
    2. 综合评分选择敏感 IMF（排除 IMF1噪声 + 末尾趋势）
    3. 重构敏感 IMF 窄带信号
    4. Hilbert 包络 → 包络谱

    Args:
        signal: 输入振动信号
        fs: 采样率
        max_imfs: 最大 IMF 数
        max_sifts: 单 IMF 最大筛分次数
        top_n: 选择前 N 个敏感 IMF
        f_low_pass: 包络低通截止频率
        max_freq: 包络谱最大显示频率
        use_rilling: 是否使用 Rilling 停止准则

    Returns:
        {
            envelope_freq, envelope_amp,  # 标准包络谱
            method,                        # "EMD Sensitive IMF Envelope"
            n_imfs,                        # 分解出的 IMF 数
            selected_imfs,                 # 选中的 IMF 索引
            imf_scores,                    # 各 IMF 评分详情
        }
    """
    from .emd_denoise import emd_decompose

    arr = remove_dc(np.asarray(signal, dtype=np.float64))

    # 分解
    imfs, residue = emd_decompose(
        arr, max_imfs=max_imfs, max_sifts=max_sifts,
        use_rilling=use_rilling, use_pchip=True,
    )

    if not imfs:
        return {
            "envelope_freq": [], "envelope_amp": [],
            "method": "EMD Sensitive IMF Envelope",
            "n_imfs": 0, "selected_imfs": [], "imf_scores": [],
            "error": "EMD 分解无有效 IMF",
        }

    # 敏感 IMF 选择
    selected_indices, imf_scores = select_emd_sensitive_imfs(
        imfs, arr, fs, mode="bearing", target_freq=0.0, top_n=top_n
    )

    # 重构 + 包络
    reconstructed = _reconstruct_selected_components(imfs, selected_indices, len(arr))
    env_result = _compute_envelope_spectrum(reconstructed, fs, f_low_pass, max_freq)

    return {
        "envelope_freq": env_result["envelope_freq"],
        "envelope_amp": env_result["envelope_amp"],
        "method": "EMD Sensitive IMF Envelope",
        "n_imfs": len(imfs),
        "selected_imfs": selected_indices,
        "imf_scores": imf_scores,
    }


# ═══════════════════════════════════════════════════════════
# CEEMDAN 轴承诊断
# ═══════════════════════════════════════════════════════════

def ceemdan_bearing_analysis(
    signal: np.ndarray,
    fs: float,
    max_imfs: int = 8,
    ensemble_size: int = 30,
    noise_std: float = 0.2,
    top_n: int = 1,
    f_low_pass: float = 2000.0,
    max_freq: float = 1000.0,
) -> Dict:
    """
    CEEMDAN 敏感 IMF 轴承诊断（§11.2 + §11.3）

    与 EMD 版的区别: CEEMDAN 抑制模态混叠，IMF 更纯净，
    噪声辅助使分解更完备。

    注意: ensemble_size=30 以减少计算量（默认50用于降噪，
    诊断场景30已足够稳定）

    Args:
        signal: 输入振动信号
        fs: 采样率
        max_imfs: 最大 IMF 数
        ensemble_size: CEEMDAN 集成次数（诊断用30即可）
        noise_std: 噪声标准差比例
        top_n: 选择前 N 个敏感 IMF
        f_low_pass: 包络低通截止频率
        max_freq: 包络谱最大显示频率

    Returns:
        同 emd_bearing_analysis 格式
    """
    from .emd_denoise import ceemdan_decompose

    arr = remove_dc(np.asarray(signal, dtype=np.float64))

    # 分解（ensemble_size较小以减少2G服务器负担）
    imfs, residue = ceemdan_decompose(
        arr, max_imfs=max_imfs, ensemble_size=ensemble_size,
        noise_std=noise_std, use_rilling=False, use_pchip=True,
    )

    if not imfs:
        return {
            "envelope_freq": [], "envelope_amp": [],
            "method": "CEEMDAN Sensitive IMF Envelope",
            "n_imfs": 0, "selected_imfs": [], "imf_scores": [],
            "error": "CEEMDAN 分解无有效 IMF",
        }

    # 敏感 IMF 选择
    selected_indices, imf_scores = select_emd_sensitive_imfs(
        imfs, arr, fs, mode="bearing", target_freq=0.0, top_n=top_n
    )

    # 重构 + 包络
    reconstructed = _reconstruct_selected_components(imfs, selected_indices, len(arr))
    env_result = _compute_envelope_spectrum(reconstructed, fs, f_low_pass, max_freq)

    return {
        "envelope_freq": env_result["envelope_freq"],
        "envelope_amp": env_result["envelope_amp"],
        "method": "CEEMDAN Sensitive IMF Envelope",
        "n_imfs": len(imfs),
        "selected_imfs": selected_indices,
        "imf_scores": imf_scores,
        "ensemble_size": ensemble_size,
    }


# ═══════════════════════════════════════════════════════════
# VMD 轴承诊断
# ═══════════════════════════════════════════════════════════

def vmd_bearing_analysis(
    signal: np.ndarray,
    fs: float,
    K: int = 5,
    alpha: float = 2000,
    top_n: int = 1,
    f_low_pass: float = 2000.0,
    max_freq: float = 1000.0,
) -> Dict:
    """
    VMD 敏感模态轴承诊断（§11.2）

    与 EMD 版的区别:
    - VMD 频域自适应，模态中心频率由算法确定，频带更清晰
    - VMD 精确中心频率可增强 freq_match 评分
    - K≤5 限制以适配2G服务器

    Args:
        signal: 输入振动信号
        fs: 采样率
        K: 模态数（≤5）
        alpha: VMD 带宽惩罚参数
        top_n: 选择前 N 个敏感模态
        f_low_pass: 包络低通截止频率
        max_freq: 包络谱最大显示频率

    Returns:
        {
            envelope_freq, envelope_amp,
            method,                        # "VMD Sensitive Mode Envelope"
            K,                             # 模态数
            selected_modes,                # 选中的模态索引
            mode_scores,                   # 各模态评分详情
            mode_center_freqs,             # VMD 精确中心频率
        }
    """
    from .vmd_denoise import vmd_decompose

    arr = remove_dc(np.asarray(signal, dtype=np.float64))

    # 分解
    modes, omega, u_hat = vmd_decompose(arr, K=K, alpha=alpha)

    # omega 是中心频率演化矩阵，取最后一行作为各模态的最终中心频率（Hz）
    # omega 形状: (K, n_iter)，最终值 = omega[:, -1] * fs / 2（因 VMD 内部归一化到 Nyquist）
    center_freqs_hz = np.real(omega[:, -1]) * fs / 2.0

    if len(modes) == 0:
        return {
            "envelope_freq": [], "envelope_amp": [],
            "method": "VMD Sensitive Mode Envelope",
            "K": K, "selected_modes": [], "mode_scores": [],
            "mode_center_freqs": [],
            "error": "VMD 分解无有效模态",
        }

    # 敏感模态选择（利用 VMD 精确中心频率）
    selected_indices, mode_scores = select_vmd_sensitive_modes(
        modes, center_freqs_hz, arr, fs,
        mode="bearing", target_freq=0.0, top_n=top_n
    )

    # 重构 + 包络
    reconstructed = _reconstruct_selected_components(modes, selected_indices, len(arr))
    env_result = _compute_envelope_spectrum(reconstructed, fs, f_low_pass, max_freq)

    return {
        "envelope_freq": env_result["envelope_freq"],
        "envelope_amp": env_result["envelope_amp"],
        "method": "VMD Sensitive Mode Envelope",
        "K": K,
        "selected_modes": selected_indices,
        "mode_scores": mode_scores,
        "mode_center_freqs": [round(cf, 2) for cf in center_freqs_hz],
    }