# `metrics.py` — 齿轮指标


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/gear/metrics.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `compute_tsa_residual_order` | `compute_tsa_residual_order(signal, fs, rot_freq, samples_per_rev=1024) -> dict` | TSA+残余+差分（阶次域） |
| `compute_fm4` | `compute_fm4(differential_signal) -> float` | FM4 局部故障检测（差分信号峭度） |
| `compute_m6a` | `compute_m6a(differential_signal) -> float` | M6A 六阶矩 |
| `compute_m8a` | `compute_m8a(differential_signal) -> float` | M8A 八阶矩 |
| `compute_car` | `compute_car(cepstrum, quefrency, rot_freq, n_harmonics=5) -> float` | 倒频谱幅值比 |
| `compute_ser_order` | `compute_ser_order(order_axis, spectrum, mesh_order, carrier_order, n_sidebands=6) -> float` | 阶次域 SER |
| `analyze_sidebands_order` | `analyze_sidebands_order(order_axis, spectrum, mesh_order, n_sidebands=6, spacing=1.0) -> dict` | 阶次域边频分析 |
| `compute_fm0_order` | `compute_fm0_order(tsa_signal, order_axis, order_spectrum, mesh_order, n_harmonics=5) -> float` | 阶次域 FM0 |
| `compute_na4` | `compute_na4(residual_signal, historical_residuals) -> float` | NA4 趋势型故障检测 |
| `compute_nb4` | `compute_nb4(envelope_signal, historical_envelopes) -> float` | NB4 包络域局部齿损坏 |
| `analyze_sidebands_zoom_fft` | `analyze_sidebands_zoom_fft(signal, fs, mesh_freq, rot_freq, n_sidebands=6) -> dict` | ZOOM-FFT 高分辨率边频 |

| `_order_band_amplitude` | `_order_band_amplitude(order_axis, spectrum, center_order: float, bandwidth: float) -> float` | 指定阶次带幅值和（非能量和） |

### `_order_band_amplitude`

```python
def _order_band_amplitude(order_axis, spectrum, center_order: float, bandwidth: float) -> float
```

- **参数**:
  - `order_axis` — 阶次轴（一维数组）
  - `spectrum` — 阶次谱幅值（一维数组）
  - `center_order` (`float`): 目标中心阶次
  - `bandwidth` (`float`): 搜索带宽（单边宽度）
- **返回值**：`float` — 指定阶次带内的幅值绝对值之和
- **说明**：计算指定阶次带幅值和（非能量和），用于阶次域边频带分析和啮合频率幅值提取。
