# `acquisition_analysis.py` — 原始计数可选分析

**对应源码**：`cloud/app/services/acquisition_analysis.py`

> 原始计数的可选分析；不作故障判定，不改变原始波形。被 `api/acquisition.py`（整包上传后分析）与 `api/acquisition_live.py`（实时窗口计算）共用。

## 函数

### `display_points(x, y, maximum=2400) -> list`

按块保留极值及其真实横坐标，仅压缩绘图点，不压缩原始分析数据。

### `amplitude_spectrum(values, rate) -> (freqs, amplitudes)`

去均值、Hann 窗、单边幅值谱；保留 Nyquist 点的正确倍率。

### `analyze_counts(values, rate, options) -> (result, arrays)`

全长计算，返回绘图摘要及可无损保存的完整分析数组。

- **参数**：`values` 四通道计数矩阵 `(N, 4)`（≥64 点、有限值）；`rate` 采样率；`options` dict（`fft` / `rms` / `envelope` / `band_low` / `band_high`，开包络须 `0 < low < high < rate/2`，否则 `ValueError`）
- **返回 result**：`sample_rate/samples/duration/unit/options`、每通道 `waveform`（抽点）、可选 `fft`（4096 点摘要）、`rms` 与按 1 秒分段的 `rms_curve`、可选 `envelope`（带通 + Hilbert 包络谱）；附 `spectrum_method/rms_method/display_method/diagnosis` 说明字段
- **返回 arrays**：完整无损数组（`chX_fft_*`、`chX_rms_curve`、`chX_envelope_*`），供 `analysis_arrays.npz` 落盘
