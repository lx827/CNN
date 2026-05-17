# `wavelet_packet.py` — 小波包

**对应源码**：`cloud/app/services/diagnosis/wavelet_packet.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `wavelet_packet_decompose` | `wavelet_packet_decompose(signal, wavelet="db8", level=3) -> Tuple` | 小波包分解 |
| `compute_wavelet_packet_energy_entropy` | `compute_wavelet_packet_energy_entropy(signal, fs, wavelet="db8", level=3, gear_mesh_freq) -> dict` | 小波包能量熵（齿轮频带能量重分布检测） |
| `wavelet_packet_denoise` | `wavelet_packet_denoise(signal, wavelet="db8", level=3, energy_threshold_ratio=0.05) -> Tuple[np.ndarray, Dict]` | 小波包降噪 |
| `compute_mswpee` | `compute_mswpee(signal, fs, wavelet="db8", level=3, scales=[1,2,3]) -> dict` | 多尺度小波包能量熵 |
