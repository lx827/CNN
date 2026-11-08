# `bearing.py` — 轴承复合方法调度

> 标准包络的算法实现已迁至 `cloud/app/algorithms/bearing/envelope.py`，对象化入口为 `cloud/app/algorithms/pipelines/bearing/`。
**对应源码**：`cloud/app/services/diagnosis/bearing.py`

本文件保留尚未独立迁移的选带和冲击增强方法。各方法通过内部 `_compute_envelope_result` 直接共享算法库的 `EnvelopeRepresentation`，不存在第二份包络数学实现，也不再提供旧 `envelope_analysis` 公共入口。

## 方法

| 函数 | 签名 | 说明 |
|------|------|------|
| `fast_kurtogram` | `fast_kurtogram(signal, fs, max_level=6, f_low=100.0) -> dict` | 当前为 STFT 近似选带，随后计算包络表示 |
| `cpw_envelope_analysis` | `cpw_envelope_analysis(signal, fs, comb_frequencies) -> dict` | CPW 后执行选带和包络计算 |
| `med_envelope_analysis` | `med_envelope_analysis(signal, fs, med_filter_len=64) -> dict` | MED 后计算包络表示 |
| `teager_envelope_analysis` | `teager_envelope_analysis(signal, fs) -> dict` | TEO 后执行选带和包络计算 |
| `spectral_kurtosis_envelope_analysis` | `spectral_kurtosis_envelope_analysis(signal, fs, max_level=6, f_low=100.0) -> dict` | 自定义重加权选带和包络计算 |

返回字典包含 `representation: EnvelopeRepresentation` 及各方法元数据。`representation.spectrum` 是带单位的 `Spectrum`，`representation.band` 是实际滤波频带。后续 Engine 统一完成指标提取与评估。
