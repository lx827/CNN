"""原始计数的可选分析；不作故障判定，不改变原始波形。"""
import numpy as np
from scipy import signal


def display_points(x, y, maximum=2400):
    """按块保留极值及其真实横坐标，仅压缩绘图点，不压缩原始分析数据。"""
    x, y = np.asarray(x), np.asarray(y)
    if len(y) <= maximum:
        return np.column_stack((x, y)).tolist()
    size = int(np.ceil(len(y) / (maximum // 2)))
    indices = []
    for start in range(0, len(y), size):
        block = y[start:start+size]
        indices.extend(sorted({start+int(np.argmin(block)), start+int(np.argmax(block))}))
    return np.column_stack((x[indices], y[indices])).tolist()


def amplitude_spectrum(values, rate):
    """去均值、Hann 窗、单边幅值谱；保留 Nyquist 点的正确倍率。"""
    values = np.asarray(values, dtype=np.float64)
    window = signal.windows.hann(len(values), sym=False)
    amplitude = np.abs(np.fft.rfft((values-values.mean()) * window)) * 2 / window.sum()
    amplitude[0] /= 2
    if len(values) % 2 == 0:
        amplitude[-1] /= 2
    return np.fft.rfftfreq(len(values), 1/rate), amplitude


def analyze_counts(values, rate, options):
    """全长计算，返回绘图摘要及可无损保存的完整分析数组。"""
    values = np.asarray(values)
    if values.ndim != 2 or values.shape[1] != 4 or len(values) < 64:
        raise ValueError("至少需要四通道各64个样本")
    if not np.isfinite(values).all():
        raise ValueError("原始波形含非有限数值")
    envelope = options.get("envelope", False)
    low, high = options.get("band_low"), options.get("band_high")
    if envelope and (low is None or high is None or not 0 < low < high < rate/2):
        raise ValueError("包络频带必须满足 0 < 下限 < 上限 < 采样率/2")
    result = {"sample_rate": rate, "samples": len(values), "duration": len(values)/rate,
              "unit": "ADC counts", "options": options, "channels": [],
              "spectrum_method": "去均值、Hann窗、单边幅值谱；完整记录计算",
              "rms_method": "去均值RMS；曲线按1秒分段，末段保留实际长度",
              "display_method": "图表长序列按块保留极值；完整数组可下载",
              "diagnosis": "本页仅作原始计数分析，不执行机械故障判定"}
    arrays = {}
    time = np.arange(len(values))/rate
    sos = signal.butter(4, [low, high], btype="bandpass", fs=rate, output="sos") if envelope else None
    for channel in range(4):
        v = values[:, channel].astype(np.float64)
        item = {"channel": channel, "label": f"CH{channel+1} / 原厂6-{channel+1}",
                "samples": len(v), "minimum": float(v.min()), "maximum": float(v.max()),
                "rail_samples": int(np.count_nonzero((v == -8388608) | (v == 8388607))),
                "waveform": display_points(time, v)}
        prefix = f"ch{channel}"
        if options.get("fft", False):
            f, a = amplitude_spectrum(v, rate)
            item["fft"] = display_points(f, a, 4096)
            arrays[prefix+"_fft_frequency_hz"], arrays[prefix+"_fft_amplitude_counts"] = f, a
        if options.get("rms", False):
            item["rms"] = float(np.sqrt(np.mean((v-v.mean())**2)))
            curve = []
            for start in range(0, len(v), rate):
                block = v[start:start+rate]
                curve.append([(start+len(block)/2)/rate,
                              float(np.sqrt(np.mean((block-block.mean())**2)))])
            item["rms_curve"] = curve
            arrays[prefix+"_rms_curve"] = np.asarray(curve)
        if envelope:
            filtered = signal.sosfiltfilt(sos, v-v.mean())
            amplitude = np.abs(signal.hilbert(filtered))
            f, a = amplitude_spectrum(amplitude, rate)
            item["envelope"] = display_points(f, a, 4096)
            arrays[prefix+"_envelope_frequency_hz"], arrays[prefix+"_envelope_amplitude_counts"] = f, a
        result["channels"].append(item)
    return result, arrays
