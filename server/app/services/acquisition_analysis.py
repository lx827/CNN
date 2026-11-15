"""原始 ADC counts 的可选显示分析；不作故障判定，不改变原始波形。"""

import numpy as np

from app.algorithms.core import FrequencyBand
from app.algorithms.statistics import centered_rms, segmented_rms
from app.algorithms.transforms import (
    compute_bandpass_hilbert_envelope,
    compute_spectrum,
    decimate_extrema,
)


def display_points(x, y, maximum=2400):
    """兼容实时示波调用；在服务/JSON 边界序列化绘图数组。"""
    return decimate_extrema(x, y, maximum).tolist()


def analyze_counts(values, rate, options):
    """四通道全长计算，返回 JSON 显示摘要及可无损保存的完整 NumPy 数组。"""
    values = np.asarray(values)
    if values.ndim != 2 or values.shape[1] != 4 or len(values) < 64:
        raise ValueError("至少需要四通道各64个样本")
    if not np.isfinite(values).all():
        raise ValueError("原始波形含非有限数值")
    if not np.isfinite(rate) or rate <= 0:
        raise ValueError("采样率必须是有限正数")

    envelope = options.get("envelope", False)
    low, high = options.get("band_low"), options.get("band_high")
    if envelope and (low is None or high is None or not 0 < low < high < rate / 2):
        raise ValueError("包络频带必须满足 0 < 下限 < 上限 < 采样率/2")
    band = FrequencyBand(float(low), float(high)) if envelope else None
    result = {
        "sample_rate": rate,
        "samples": len(values),
        "duration": len(values) / rate,
        "unit": "ADC counts",
        "options": options,
        "channels": [],
        "spectrum_method": "去均值、周期Hann窗、单边峰值幅值谱；完整记录计算",
        "rms_method": "去均值RMS；曲线按1秒分段，末段保留实际长度",
        "display_method": "图表长序列按块保留极值；完整数组可下载",
        "diagnosis": "本页仅作原始计数分析，不执行机械故障判定",
    }
    arrays = {}
    time = np.arange(len(values)) / rate
    for channel in range(4):
        counts = values[:, channel].astype(np.float64)
        item = {
            "channel": channel,
            "label": f"CH{channel + 1} / 原厂6-{channel + 1}",
            "samples": len(counts),
            "minimum": float(counts.min()),
            "maximum": float(counts.max()),
            "rail_samples": int(
                np.count_nonzero((counts == -8388608) | (counts == 8388607))
            ),
            "waveform": display_points(time, counts),
        }
        prefix = f"ch{channel}"
        if options.get("fft", False):
            spectrum = compute_spectrum(counts, rate, amplitude_unit="ADC counts")
            item["fft"] = display_points(
                spectrum.frequency_hz,
                spectrum.amplitude,
                4096,
            )
            arrays[prefix + "_fft_frequency_hz"] = spectrum.frequency_hz
            arrays[prefix + "_fft_amplitude_counts"] = spectrum.amplitude
        if options.get("rms", False):
            item["rms"] = centered_rms(counts)
            curve = segmented_rms(counts, rate)
            item["rms_curve"] = np.column_stack((curve.time_s, curve.rms)).tolist()
            arrays[prefix + "_rms_curve"] = np.column_stack((curve.time_s, curve.rms))
        if envelope:
            envelope_values = compute_bandpass_hilbert_envelope(counts, rate, band)
            spectrum = compute_spectrum(
                envelope_values,
                rate,
                amplitude_unit="ADC counts",
            )
            item["envelope"] = display_points(
                spectrum.frequency_hz,
                spectrum.amplitude,
                4096,
            )
            arrays[prefix + "_envelope_frequency_hz"] = spectrum.frequency_hz
            arrays[prefix + "_envelope_amplitude_counts"] = spectrum.amplitude
        result["channels"].append(item)
    return result, arrays
