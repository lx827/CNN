"""小波轴承分析业务适配：只消费原时间轴重构分量，复用敏感包络 Pipeline。"""
import numpy as np
from app.algorithms.decomposition.wavelet import decompose_dwt, decompose_wavelet_packet
from app.algorithms.pipelines.decomposition import SensitiveComponentEnvelopePipeline
from .modality_bearing import envelope_response


def wavelet_packet_bearing_analysis(signal, fs, wavelet="db8", level=3, top_n=1,
                                    f_low_pass=2000.0, max_freq=1000.0, target_freq=0.0):
    """WP 自然序路径与频率序分开；相关、峭度均在原时间轴重构上测量。"""
    arr = np.asarray(signal, dtype=float)
    arr = arr - np.mean(arr)
    decomposition = decompose_wavelet_packet(arr, fs, wavelet, level)
    centers = [sum(node.frequency_band_hz) / 2 for node in decomposition.nodes]
    analysis = SensitiveComponentEnvelopePipeline().analyze(
        [node.reconstructed for node in decomposition.nodes], arr, fs, top_n=top_n,
        target_frequency_hz=target_freq, center_frequencies_hz=centers,
        envelope_low_pass_hz=f_low_pass)
    paths = [decomposition.nodes[i].path for i in analysis.selection.selected_indices]
    return envelope_response(analysis, "Wavelet Packet Envelope", max_freq,
        wp_level=level, wp_wavelet=wavelet, selected_nodes=paths,
        node_scores=list(analysis.selection.scores),
        node_center_freqs={node.path: center for node, center in zip(decomposition.nodes, centers)},
        target_freq=target_freq, n_selected=len(paths))


def dwt_bearing_analysis(signal, fs, wavelet="db8", level=5, top_n=1,
                         f_low_pass=2000.0, max_freq=1000.0):
    """只允许细节带进入选择和重构，未选 approximation 不再泄漏到包络。"""
    arr = np.asarray(signal, dtype=float)
    arr = arr - np.mean(arr)
    decomposition = decompose_dwt(arr, fs, wavelet, level)
    centers = [sum(detail.frequency_band_hz) / 2 for detail in decomposition.details]
    analysis = SensitiveComponentEnvelopePipeline().analyze(
        [detail.reconstructed for detail in decomposition.details], arr, fs,
        top_n=top_n, center_frequencies_hz=centers, envelope_low_pass_hz=f_low_pass)
    layers = [decomposition.details[i].level for i in analysis.selection.selected_indices]
    scores = [{**score, "layer": detail.level, "freq_range": list(detail.frequency_band_hz)}
              for score, detail in zip(analysis.selection.scores, decomposition.details)]
    return envelope_response(analysis, "DWT Sensitive Layer Envelope", max_freq,
        dwt_level=level, dwt_wavelet=wavelet, selected_layers=layers, layer_scores=scores,
        best_layer=max((score for score in scores if score["score"] is not None),
                       key=lambda score: score["score"], default=None))
