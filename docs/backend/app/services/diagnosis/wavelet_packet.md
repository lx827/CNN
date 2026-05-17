# `wavelet_packet.py` — 小波包


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/wavelet_packet.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `wavelet_packet_decompose` | `wavelet_packet_decompose(signal, wavelet="db8", level=3) -> Tuple` | 小波包分解 |
| `compute_wavelet_packet_energy_entropy` | `compute_wavelet_packet_energy_entropy(signal, fs, wavelet="db8", level=3, gear_mesh_freq) -> dict` | 小波包能量熵（齿轮频带能量重分布检测） |
| `wavelet_packet_denoise` | `wavelet_packet_denoise(signal, wavelet="db8", level=3, energy_threshold_ratio=0.05) -> Tuple[np.ndarray, Dict]` | 小波包降噪 |
| `compute_mswpee` | `compute_mswpee(signal, fs, wavelet="db8", level=3, scales=[1,2,3]) -> dict` | 多尺度小波包能量熵 |

| `_coarse_grain` | `_coarse_grain(signal: np.ndarray, scale: int) -> np.ndarray` | 粗粒化处理（多尺度） |

### `_coarse_grain`

```python
def _coarse_grain(signal: np.ndarray, scale: int) -> np.ndarray
```

- **参数**:
  - `signal` (`np.ndarray`): 输入信号
  - `scale` (`int`): 粗粒化尺度因子（τ=1 为原信号，τ=2 每 2 点取平均）
- **返回值**：`np.ndarray` — 粗粒化后的序列（长度 ≈ N/scale）
- **说明**：多尺度小波包能量熵的预处理步骤。按 scale 分段平均，抑制高频随机噪声，凸显低频调制特征。
