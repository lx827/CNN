"""边端诊断 POC 的云端参照 JSON 生成脚本。

用法: uv run python scripts/edge_diag_reference.py <输入.f64> <采样率Hz> [输出.json]

输入为单通道 float64 小端裸二进制(np.fromfile(dtype='<f8'));输出与边端 Rust CLI
同字段名的参照 JSON(参照侧无 timings_ms/peak_rss_kb,对比脚本忽略额外字段)。
全部数值计算调用 cnn_compute pybind 包,C++ 内核与边端 C ABI 同源,不 import cloud.app。

一期契约管线各步对应的 pybind 入口(逐步标注,无缺口):
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

二期新增 stage 对应的 pybind 入口(输入除标注外均为原始信号 x):
7.  小波阈值去噪 wavelet    cnn_compute.wavelet.denoise(x),db8/最大允许层数/soft/1.0
    全默认;residual_rms=statistics(x-去噪)[1]、denoised_rms=statistics(去噪)[1],
    RMS 定义与步骤 2 同核。
8.  实倒谱 cepstrum         cnn_compute.numeric.cepstrum(x),周期 Hann、去均值 log
    幅度实倒谱,前 N//2 点数组原样输出。
9.  谱峭度图选带 kurtogram  cnn_compute.diagnostic.filter_bank_kurtogram(x, fs, 4,
    100.0, 4),逐带元组 (low_hz, high_hz, level, spectral_kurtosis,
    impulsiveness, signal_to_background);取 spectral_kurtosis 最大的带,映射
    best_low_hz=low_hz、best_high_hz=high_hz、max_kurtosis=spectral_kurtosis。
10. VMD                    cnn_compute.vmd.decompose(x[:min(n,51200)], fs),modes/
    alpha/tau/tolerance/max_iterations/dc/max_samples/initialization/seed 全默认;
    mode_energy_ratio[k]=Σu_k²/Σ_kΣu_k²(模态能量归一,和为 1),
    n_input=valid_length=min(n,51200)。显式切片与默认 max_samples=51200 一致,
    供边端在宿主侧对齐截断。
11. 阶次谱 order_spectrum  相位来源(未降级):pybind 面有与云端 order 管线同源的
    连续相位入口 rotation.integrate(time_s, frequency_hz),与
    cloud/app/algorithms/order 的 integrate_speed_trajectory 同入口同调用方式,
    此处喂恒速轨迹 frequency_hz(t)≡speed_hz;梯形积分对常速精确等于 f·t,数值
    上即契约降级规则中的恒速线性相位。等角重采样 rotation.angle_resample(x,
    revolutions, 1024) → rotation.amplitude_spectrum,按云端 compute_order_spectrum
    同规则截取 ≤50 阶:resolution=1024/len,保留 floor(50/resolution+1e-9)+1 点。
12. TSA                    rotation.tsa(角域信号, 1024),取返回的单圈平均波形
    (minimum_revolutions 默认 4)。优先入口 rotation.tsa_components 的签名强制
    mesh_orders/regular_orders 齿轮参数,边端 POC 无齿轮参数,按契约改用纯转
    平均入口 rotation.tsa(该入口存在,故 tsa 不置 null)。

与 C ABI 面的差异记录:
- pybind 覆盖全部六步,没有因入口缺失而置 null 的字段。
- 幅度谱的 abs() 在宿主侧计算:pybind(fourier.rfft)与 C ABI(cnn_rfft)一样只返回
  复数谱,两侧约定各自对同一复数谱取模,不构成数值差异。
- 契约步骤 3/6 未标注中间信号(步骤 2/4/5 均显式标注"去趋势后/带通后"),取原始
  输入信号;步骤 3 的 500 Hz 高通自身消除趋势差异,步骤 6 的候选仲裁在核内处理均值。
- spectrum_speed 仲裁不可判定(reason 非空)或频率非有限时 speed_hz 置 null:
  浮点 NaN 无法写入 JSON,边端同规则,对比脚本把双方 null/null 视为跳过。
- 二期:speed_hz 为 null 时 order_spectrum 与 tsa 均为 null,另加
  "order_skip_reason":"speed_null";speed_hz 有效时无该键。
"""

from __future__ import annotations

import json
import math
import sys

import numpy as np

from cnn_compute import diagnostic, filtering, fourier, numeric, rotation, vmd, wavelet

# 管线参数,与 edge-diag crate 保持一致
BANDPASS_ORDER = 4        # Butterworth 阶数
BANDPASS_LOW_HZ = 500.0   # 带通下限 Hz
BANDPASS_HIGH_HZ = 3000.0 # 带通上限 Hz
SPEED_LOW_HZ = 10.0       # 转频搜索下限 Hz
SPEED_HIGH_HZ = 100.0     # 转频搜索上限 Hz

# 二期 stage 参数,与 edge-diag crate 二期契约保持一致
VMD_MAX_INPUT = 51200          # VMD 输入截断点数(契约固定)
SAMPLES_PER_REVOLUTION = 1024  # 等角重采样每转点数
MAX_ORDER = 50.0               # 阶次谱保留阶次上限


def build_reference(path: str, fs: float) -> dict:
    """对单个 .f64 文件执行契约管线,返回参照 dict。"""
    x = np.fromfile(path, dtype="<f8")
    d = filtering.detrend(x, linear=True)
    peak, rms, kurtosis, skewness, _margin, _shape, _impulse, crest = numeric.statistics(d)
    sos = filtering.butterworth(BANDPASS_ORDER, BANDPASS_LOW_HZ, BANDPASS_HIGH_HZ, fs)
    bandpassed = filtering.sosfiltfilt(sos, x)
    envelope = numeric.hilbert_envelope(bandpassed)
    speed, _source, reason = rotation.spectrum_speed(x, fs, SPEED_LOW_HZ, SPEED_HIGH_HZ)
    speed_hz = None if reason or not math.isfinite(speed) else speed

    denoised = wavelet.denoise(x)
    bands = diagnostic.filter_bank_kurtogram(x, fs, 4, 100.0, 4)
    best_band = max(bands, key=lambda band: band[3])
    decomposition = vmd.decompose(x[: min(x.size, VMD_MAX_INPUT)], fs)
    mode_energy = np.sum(decomposition.modes**2, axis=1)

    if speed_hz is None:
        order_spectrum = None
        tsa_cycle = None
    else:
        times = np.arange(x.size, dtype=np.float64) / fs
        revolutions = rotation.integrate(times, np.full(x.size, speed_hz))
        angle_samples = rotation.angle_resample(x, revolutions, SAMPLES_PER_REVOLUTION)
        amplitude = rotation.amplitude_spectrum(angle_samples)
        resolution = SAMPLES_PER_REVOLUTION / angle_samples.size
        retained = min(amplitude.size, int(math.floor(MAX_ORDER / resolution + 1e-9)) + 1)
        order_spectrum = amplitude[:retained].tolist()
        tsa_cycle = rotation.tsa(angle_samples, SAMPLES_PER_REVOLUTION)[0].tolist()

    reference = {
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
        "speed_hz": speed_hz,
        "wavelet": {
            "residual_rms": numeric.statistics(x - denoised)[1],
            "denoised_rms": numeric.statistics(denoised)[1],
        },
        "cepstrum": numeric.cepstrum(x).tolist(),
        "kurtogram": {
            "best_low_hz": best_band[0],
            "best_high_hz": best_band[1],
            "max_kurtosis": best_band[3],
        },
        "vmd": {
            "mode_energy_ratio": (mode_energy / mode_energy.sum()).tolist(),
            "n_input": int(decomposition.valid_length),
        },
        "order_spectrum": order_spectrum,
        "tsa": tsa_cycle,
    }
    if speed_hz is None:
        reference["order_skip_reason"] = "speed_null"
    return reference


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
