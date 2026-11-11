"""分解后的选择/重构 Pipeline；工程选择策略不等价于故障评估。

所有分量必须共享原采样率、长度和时间轴。WP/DWT 只接受重构分量。
选择失败时 representation=None，调用方不能把零数组当成健康信号。
"""
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from app.algorithms.decomposition.selection import compute_component_metrics_batch
from app.algorithms.decomposition.selection.metrics import ComponentMetrics
from app.algorithms.decomposition.types import ValidInterval


BEARING_WEIGHTS = {"corr": .30, "kurt": .45, "env_entropy": .15, "energy": .05, "freq_match": .05}
GEAR_WEIGHTS = {"corr": .20, "kurt": .30, "env_entropy": .10, "energy": .25, "freq_match": .15}


@dataclass(frozen=True)
class ComponentSelection:
    status: str
    representation: np.ndarray | None
    selected_indices: tuple[int, ...]
    metrics: tuple[ComponentMetrics, ...]
    scores: tuple[dict, ...]
    valid_interval: ValidInterval
    reason: str | None = None


def _normalize(values):
    valid = [value for value in values if value is not None and np.isfinite(value)]
    if not valid:
        return [0.0] * len(values)
    lower, upper = min(valid), max(valid)
    return [0.0 if value is None or not np.isfinite(value) else
            (0.5 if upper == lower else (value - lower) / (upper - lower)) for value in values]


def frequency_match(center_hz, target_hz):
    """工程相对距离分数；目标未知时不生成频率匹配证据。"""
    if center_hz is None or center_hz <= 0 or target_hz <= 0:
        return 0.0
    return float(np.clip(1 - 2 * abs(center_hz - target_hz) / target_hz, 0, 1))


def score_aligned_components(components, reference, fs, target_freq=0.0,
                             mode="bearing", weights=None, center_frequencies_hz=None):
    """返回原始指标与工程排序；kurt 字段明确为 Fisher/excess。"""
    if mode not in ("bearing", "gear"):
        raise ValueError("未知分量选择模式")
    reference = np.asarray(reference, dtype=float)
    if reference.ndim != 1 or len(reference) < 8 or not np.all(np.isfinite(reference)):
        raise ValueError("参考信号必须为至少8点的一维有限数组")
    if not np.isfinite(fs) or fs <= 0:
        raise ValueError("采样率必须为有限正数")
    if not np.isfinite(target_freq) or target_freq < 0:
        raise ValueError("目标频率必须为有限非负数")
    metrics = compute_component_metrics_batch(components, fs, reference)
    if center_frequencies_hz is not None and len(center_frequencies_hz) != len(metrics):
        raise ValueError("中心频率数量与分量数量不一致")
    centers = [metric.center_frequency_hz for metric in metrics] if center_frequencies_hz is None else list(center_frequencies_hz)
    if any(center is not None and (not np.isfinite(center) or center < 0 or center > fs / 2) for center in centers):
        raise ValueError("分量中心频率必须位于物理频带 [0, Nyquist]")
    matches = [frequency_match(center, target_freq) for center in centers]
    raw = {"corr": [m.correlation for m in metrics], "kurt": [m.kurtosis_excess for m in metrics],
           "env_entropy": [m.envelope_entropy for m in metrics], "energy": [m.energy_ratio for m in metrics],
           "freq_match": matches}
    normalized = {key: _normalize(values) for key, values in raw.items()}
    normalized["env_entropy"] = [0.0 if raw["env_entropy"][i] is None else 1 - value
                                  for i, value in enumerate(normalized["env_entropy"])]
    selected_weights = weights if weights is not None else (BEARING_WEIGHTS if mode == "bearing" else GEAR_WEIGHTS)
    if any(not np.isfinite(value) or value < 0 for value in selected_weights.values()):
        raise ValueError("选择权重必须为有限非负数")
    scores = []
    for index, metric in enumerate(metrics):
        valid = metric.kurtosis_pearson is not None and metric.energy > 0
        score = sum(selected_weights.get(key, 0) * values[index] for key, values in normalized.items())
        scores.append({"index": index, "score": float(score) if valid else None,
                       "corr": metric.correlation, "kurt": metric.kurtosis_excess,
                       "kurtosis_pearson": metric.kurtosis_pearson,
                       "env_entropy": metric.envelope_entropy, "energy_ratio": metric.energy_ratio,
                       "center_freq": centers[index], "freq_match": matches[index], "valid": valid})
    return metrics, scores


def select_ranked_components(components, reference, fs, *, top_n=1, target_freq=0.0,
                             mode="bearing", weights=None, center_frequencies_hz=None):
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n <= 0:
        raise ValueError("top_n 必须是正整数")
    metrics, scores = score_aligned_components(components, reference, fs, target_freq, mode, weights,
                                               center_frequencies_hz)
    selected = tuple(item["index"] for item in sorted(
        (item for item in scores if item["valid"]), key=lambda item: item["score"], reverse=True)[:top_n])
    return _selection(components, reference, selected, metrics, scores)


def select_denoising_components(components, reference, fs, *, correlation_threshold=.3,
                                kurtosis_threshold=3.0, kurtosis_kind="pearson"):
    """去噪阈值独立于敏感分量排序及诊断；无满足分量时明确失败，不强选。"""
    if not np.isfinite(correlation_threshold) or not 0 <= correlation_threshold <= 1:
        raise ValueError("相关阈值必须位于 [0, 1]")
    if kurtosis_kind not in ("pearson", "excess") or not np.isfinite(kurtosis_threshold):
        raise ValueError("峭度类型或阈值非法")
    metrics, scores = score_aligned_components(components, reference, fs)
    selected = tuple(index for index, metric in enumerate(metrics)
                     if scores[index]["valid"] and (
                         (metric.correlation is not None and metric.correlation > correlation_threshold)
                         or (getattr(metric, "kurtosis_" + kurtosis_kind) is not None
                             and getattr(metric, "kurtosis_" + kurtosis_kind) > kurtosis_threshold)))
    return _selection(components, reference, selected, metrics, scores)


def _selection(components, reference, selected, metrics, scores):
    interval = ValidInterval(0, len(reference))
    if not selected:
        return ComponentSelection("indeterminate", None, (), metrics, tuple(scores), interval,
                                  "no_eligible_components")
    representation = sum((components[i] for i in selected), start=np.zeros(len(reference)))
    return ComponentSelection("computed", representation, selected, metrics, tuple(scores), interval)


def require_representation(selection):
    """旧 ndarray 兼容边界无法携带失败状态，因此显式抛错供上层方法隔离。"""
    if selection.representation is None:
        raise ValueError(selection.reason or "decomposition_not_evaluable")
    return selection.representation


@dataclass(frozen=True)
class SensitiveEnvelopeAnalysis:
    selection: ComponentSelection
    spectrum: object | None
    envelope_analysis: object | None


class SensitiveComponentEnvelopePipeline:
    """对既有分解分量作敏感选择→Hilbert→统一单边谱→轴承指标分析。

    分解结果由算法族 adapter 提供，可复用而不重复分解。该类的 evaluate
    只读取已提取的包络指标，排序权重不构成故障阈值或独立诊断证据。
    """
    def analyze(self, components, reference, sample_rate_hz, *, top_n=1,
                target_frequency_hz=0.0, center_frequencies_hz=None,
                envelope_low_pass_hz=2000.0, geometry=None, rot_frequency_hz=None):
        from scipy.signal import hilbert, butter, sosfiltfilt
        from app.algorithms.transforms.spectrum import compute_spectrum
        from app.algorithms.core import Spectrum
        from app.algorithms.bearing.analysis import analyze_envelope_spectrum

        if not np.isfinite(envelope_low_pass_hz) or envelope_low_pass_hz <= 0:
            raise ValueError("包络低通频率必须为有限正数")
        selection = select_ranked_components(components, reference, sample_rate_hz,
            top_n=top_n, target_freq=target_frequency_hz,
            center_frequencies_hz=center_frequencies_hz)
        if selection.representation is None:
            return SensitiveEnvelopeAnalysis(selection, None, None)
        signal = selection.representation
        envelope = np.abs(hilbert(signal - np.mean(signal)))
        if envelope_low_pass_hz < sample_rate_hz / 2:
            envelope = sosfiltfilt(butter(4, envelope_low_pass_hz, fs=sample_rate_hz,
                                         btype="lowpass", output="sos"), envelope)
        fourier = compute_spectrum(envelope, sample_rate_hz)
        limit = min(envelope_low_pass_hz, sample_rate_hz / 2)
        mask = fourier.frequency_hz <= limit
        spectrum = Spectrum(fourier.frequency_hz[mask], fourier.amplitude[mask])
        extracted = analyze_envelope_spectrum(spectrum, geometry=geometry,
                                              rot_frequency_hz=rot_frequency_hz)
        return SensitiveEnvelopeAnalysis(selection, spectrum, extracted)

    def evaluate(self, analysis):
        """不重复分解、选择、Hilbert 或 FFT，直接重评已有指标。"""
        from app.algorithms.bearing.evaluation import evaluate_envelope, EnvelopeEvaluation
        if analysis.envelope_analysis is None:
            return EnvelopeEvaluation("indeterminate", {})
        return evaluate_envelope(analysis.envelope_analysis)

    def run(self, components, reference, sample_rate_hz, **parameters):
        analysis = self.analyze(components, reference, sample_rate_hz, **parameters)
        return analysis, self.evaluate(analysis)


@dataclass(frozen=True)
class DecompositionDenoisingAnalysis:
    decomposition: object
    metrics: tuple[ComponentMetrics, ...]
    reference: np.ndarray


def _evaluate_denoising(analysis, correlation_threshold, kurtosis_threshold, kurtosis_kind):
    """只消费已有指标，可改变选择阈值而不再分解或提取指标。"""
    if not np.isfinite(correlation_threshold) or not 0 <= correlation_threshold <= 1:
        raise ValueError("相关阈值必须位于 [0, 1]")
    if kurtosis_kind not in ("pearson", "excess") or not np.isfinite(kurtosis_threshold):
        raise ValueError("峭度类型或阈值非法")
    result = analysis.decomposition
    components = result.imfs if hasattr(result, "imfs") else result.modes
    selected = tuple(i for i, metric in enumerate(analysis.metrics)
                     if metric.kurtosis_pearson is not None and metric.energy > 0 and (
                         (metric.correlation is not None and metric.correlation > correlation_threshold)
                         or getattr(metric, "kurtosis_" + kurtosis_kind) > kurtosis_threshold))
    return _selection(components, analysis.reference, selected, analysis.metrics, ())


class EMDDenoisingPipeline:
    """EMD族分析提取分量与指标；evaluate 只按明确 excess 去噪阈值选择。"""
    def __init__(self, parameters=None, ensemble_parameters=None):
        from app.algorithms.decomposition.emd import EMDParameters, EnsembleParameters
        self.parameters = parameters or EMDParameters()
        self.ensemble_parameters = ensemble_parameters or EnsembleParameters(emd=self.parameters)

    def analyze(self, signal, sample_rate_hz, *, method="emd", seed=0):
        from app.algorithms.decomposition.emd import decompose_emd, decompose_eemd, decompose_ceemdan
        reference = np.asarray(signal, dtype=float)
        if method == "emd":
            result = decompose_emd(reference, sample_rate_hz, self.parameters)
        elif method in ("eemd", "ceemdan"):
            function = decompose_eemd if method == "eemd" else decompose_ceemdan
            result = function(reference, sample_rate_hz, seed=seed, parameters=self.ensemble_parameters)
        else:
            raise ValueError("未知 EMD 方法")
        metrics = compute_component_metrics_batch(result.imfs, sample_rate_hz, reference)
        return DecompositionDenoisingAnalysis(result, metrics, reference)

    def evaluate(self, analysis, *, correlation_threshold=.35, kurtosis_threshold=3.5):
        return _evaluate_denoising(analysis, correlation_threshold, kurtosis_threshold, "excess")

    def run(self, signal, sample_rate_hz, *, method="emd", seed=0,
            correlation_threshold=.35, kurtosis_threshold=3.5):
        analysis = self.analyze(signal, sample_rate_hz, method=method, seed=seed)
        return analysis, self.evaluate(analysis, correlation_threshold=correlation_threshold,
                                      kurtosis_threshold=kurtosis_threshold)


class VMDDenoisingPipeline:
    """VMD 分解/原始指标与 Pearson 去噪阈值分离；有效区间不补零。"""
    def __init__(self, parameters=None):
        from app.algorithms.decomposition.vmd import VMDParameters
        self.parameters = parameters or VMDParameters()

    def analyze(self, signal, sample_rate_hz, *, reference_signal=None):
        from app.algorithms.decomposition.vmd import decompose_vmd
        result = decompose_vmd(signal, sample_rate_hz, self.parameters)
        original = np.asarray(signal, dtype=float)
        reference = original if reference_signal is None else np.asarray(reference_signal, dtype=float)
        if reference.shape != original.shape:
            raise ValueError("VMD 参考信号必须与输入同长同时间轴")
        interval = result.valid_interval
        reference = reference[interval.start_index:interval.stop_index]
        metrics = compute_component_metrics_batch(result.modes, sample_rate_hz, reference)
        return DecompositionDenoisingAnalysis(result, metrics, reference)

    def evaluate(self, analysis, *, correlation_threshold=.3, kurtosis_threshold=3.0):
        return _evaluate_denoising(analysis, correlation_threshold, kurtosis_threshold, "pearson")

    def run(self, signal, sample_rate_hz, *, reference_signal=None,
            correlation_threshold=.3, kurtosis_threshold=3.0):
        analysis = self.analyze(signal, sample_rate_hz, reference_signal=reference_signal)
        return analysis, self.evaluate(analysis, correlation_threshold=correlation_threshold,
                                      kurtosis_threshold=kurtosis_threshold)


@dataclass(frozen=True)
class WaveletPacketEnergyAnalysis:
    decomposition: object
    energies: np.ndarray
    energy_ratios: np.ndarray | None
    entropy_bits: float | None
    normalized_entropy: float | None


class WaveletPacketEnergyPipeline:
    """WP 能量分布指标与去噪选择分离；能量熵不直接命名齿轮故障。"""
    def __init__(self, wavelet="db8", level=3):
        self.wavelet, self.level = wavelet, level

    def analyze(self, signal, sample_rate_hz):
        from app.algorithms.decomposition.wavelet import decompose_wavelet_packet
        result = decompose_wavelet_packet(signal, sample_rate_hz, self.wavelet, self.level)
        # 统一在原时间轴重构计算能量，避免对称延拓系数个数影响能量定义。
        scale = max(float(np.max(np.abs(node.reconstructed))) for node in result.nodes)
        scaled = np.asarray([np.sum((node.reconstructed / scale)**2) for node in result.nodes]) if scale else np.zeros(len(result.nodes))
        energies = scaled * scale**2
        total = float(np.sum(scaled))
        if total == 0:
            return WaveletPacketEnergyAnalysis(result, energies, None, None, None)
        ratios = scaled / total
        positive = ratios[ratios > 0]
        entropy = float(-np.sum(positive * np.log2(positive)))
        return WaveletPacketEnergyAnalysis(result, energies, ratios, entropy, entropy / np.log2(len(ratios)))

    def select(self, analysis, *, energy_threshold_ratio=.05):
        from app.algorithms.decomposition.wavelet import reconstruct_wavelet_packet
        if not np.isfinite(energy_threshold_ratio) or not 0 <= energy_threshold_ratio <= 1:
            raise ValueError("节点能量阈值必须位于 [0, 1]")
        result = analysis.decomposition
        paths = [] if analysis.energy_ratios is None else [node.path for node, ratio in
            zip(result.nodes, analysis.energy_ratios) if ratio >= energy_threshold_ratio and ratio > 0]
        if not paths:
            return None, ()
        return reconstruct_wavelet_packet(result, paths), tuple(paths)
