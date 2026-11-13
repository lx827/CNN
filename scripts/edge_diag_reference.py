"""边端诊断 POC 的云端参照 JSON 生成脚本。

用法: uv run python scripts/edge_diag_reference.py <输入.f64> <采样率Hz> [输出.json]

输入为单通道 float64 小端裸二进制(np.fromfile(dtype='<f8'));输出与边端 Rust CLI
同字段名的参照 JSON(参照侧无 timings_ms/peak_rss_kb,对比脚本忽略额外字段)。
全部数值计算调用 cnn_compute pybind 包,C++ 内核与边端 C ABI 同源,不 import cloud.app。

契约管线各步对应的 pybind 入口(逐步标注,无缺口):
1. 线性去趋势         cnn_compute.filtering.detrend(x, linear=True)
2. 时域统计(去趋势后)  cnn_compute.numeric.statistics(d) →
                      [peak, rms, kurtosis, skewness, margin, shape, impulse, crest]
3. Butterworth 带通    cnn_compute.filtering.butterworth(4, 500, 3000, fs)
                      + cnn_compute.filtering.sosfiltfilt(SOS 零相位,padlen 取默认)
4. 谱(去趋势后)        cnn_compute.fourier.rfft(d) → np.abs
5. 包络谱             cnn_compute.numeric.hilbert_envelope(带通后,Hilbert→abs 在核内)
                      → cnn_compute.fourier.rfft → np.abs
6. 转速               cnn_compute.rotation.spectrum_speed(x, fs, 10.0, 100.0),
                      harmonics/bandwidth/smoothing 两侧一致地取默认(5/3.0/1.5)

与 C ABI 面的差异记录:
- pybind 覆盖全部六步,没有因入口缺失而置 null 的字段。
- 幅度谱的 abs() 在宿主侧计算:pybind(fourier.rfft)与 C ABI(cnn_rfft)一样只返回
  复数谱,两侧约定各自对同一复数谱取模,不构成数值差异。
- 契约步骤 3/6 未标注中间信号(步骤 2/4/5 均显式标注"去趋势后/带通后"),取原始
  输入信号;步骤 3 的 500 Hz 高通自身消除趋势差异,步骤 6 的候选仲裁在核内处理均值。
- spectrum_speed 仲裁不可判定(reason 非空)或频率非有限时 speed_hz 置 null:
  浮点 NaN 无法写入 JSON,边端同规则,对比脚本把双方 null/null 视为跳过。
"""

from __future__ import annotations

import json
import math
import sys

import numpy as np

from cnn_compute import filtering, fourier, numeric, rotation

# 管线参数,与 edge-diag crate 保持一致
BANDPASS_ORDER = 4        # Butterworth 阶数
BANDPASS_LOW_HZ = 500.0   # 带通下限 Hz
BANDPASS_HIGH_HZ = 3000.0 # 带通上限 Hz
SPEED_LOW_HZ = 10.0       # 转频搜索下限 Hz
SPEED_HIGH_HZ = 100.0     # 转频搜索上限 Hz


def build_reference(path: str, fs: float) -> dict:
    """对单个 .f64 文件执行契约管线,返回参照 dict。"""
    x = np.fromfile(path, dtype="<f8")
    d = filtering.detrend(x, linear=True)
    peak, rms, kurtosis, skewness, _margin, _shape, _impulse, crest = numeric.statistics(d)
    sos = filtering.butterworth(BANDPASS_ORDER, BANDPASS_LOW_HZ, BANDPASS_HIGH_HZ, fs)
    bandpassed = filtering.sosfiltfilt(sos, x)
    envelope = numeric.hilbert_envelope(bandpassed)
    speed_hz, _source, reason = rotation.spectrum_speed(x, fs, SPEED_LOW_HZ, SPEED_HIGH_HZ)
    return {
        "input": {"file": path, "fs": fs, "n": int(x.size)},
        "metrics": {
            "rms": rms,
            "peak": peak,
            "crest": crest,
            "kurtosis": kurtosis,
            "skewness": skewness,
        },
        "spectrum": np.abs(fourier.rfft(d)).tolist(),
        "envelope_spectrum": np.abs(fourier.rfft(envelope)).tolist(),
        "speed_hz": None if reason or not math.isfinite(speed_hz) else speed_hz,
    }


def main(argv: list[str]) -> int:
    if len(argv) not in (3, 4):
        print("用法: uv run python scripts/edge_diag_reference.py <输入.f64> <采样率Hz> [输出.json]", file=sys.stderr)
        return 2
    path, fs = argv[1], float(argv[2])
    output = argv[3] if len(argv) == 4 else path.rsplit(".", 1)[0] + ".json"
    reference = build_reference(path, fs)
    with open(output, "w", encoding="utf-8") as stream:
        json.dump(reference, stream)
        stream.write("\n")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
