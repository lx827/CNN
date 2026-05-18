# `envelope.py` — 包络谱分析

> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/api/data_view/envelope.py`

## 路由端点

### `GET /{device_id}/{batch_index}/{channel}/envelope`

```python
@router.get("/{device_id}/{batch_index}/{channel}/envelope")
async def get_channel_envelope(
    device_id: str,
    batch_index: int,
    channel: int,
    max_freq: Optional[int] = 1000,
    detrend: bool = Query(default=False),
    method: str = Query(default="envelope"),
    denoise: str = Query(default="none"),
    db: Session = Depends(get_db)
) -> dict
```

- **async**：✅
- **参数 method 可选值**：`envelope` | `kurtogram` | `cpw` | `med` | `teager` | `spectral_kurtosis` | `sc_scoh` | `mckd` | `wp` | `dwt` | `emd_envelope` | `ceemdan_envelope` | `vmd_envelope`
- **参数 denoise 可选值**：`none` | `wavelet` | `vmd` | `wavelet_vmd` | `wavelet_lms` | `emd` | `ceemdan` | `savgol` | `wavelet_packet` | `ceemdan_wp` | `eemd`
- **参数 max_freq**：包络谱返回的最大频率（Hz），默认 `1000`。当前端点接收此参数，实际计算由诊断引擎内部默认 `1000.0` 处理。
- **响应 data**：`{device_id, batch_index, channel, channel_name, sample_rate, is_special, method, envelope_freq, envelope_amp, optimal_fc, optimal_bw, max_kurtosis, comb_frequencies, med_filter_len, kurtosis_before, kurtosis_after, teager_rms, reweighted_score, spectral_kurtosis_bands, features, fault_indicators}`
- **错误码**：
  - `404`：数据不存在
  - `400`：信号长度不足（少于 64 采样点）
  - `500`：计算过程异常（已增强底层鲁棒性，极端场景下仍可能返回）
- **说明**：包络谱分析（13 种轴承方法）。信号会先被截断到最多 5 秒长度，再进行计算。

## 内部辅助函数

> `_extract_device_param` 已统一到 `__init__.py`。本模块通过 `from . import _extract_device_param` 导入。
