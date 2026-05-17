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
- **响应 data**：`{device_id, batch_index, channel, channel_name, sample_rate, is_special, method, envelope_freq, envelope_amp, optimal_fc, optimal_bw, max_kurtosis, comb_frequencies, med_filter_len, kurtosis_before, kurtosis_after, teager_rms, reweighted_score, spectral_kurtosis_bands, features, fault_indicators}`
- **说明**：包络谱分析（13 种轴承方法）
