# `metrics.py` — 齿轮指标

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
