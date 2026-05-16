# 齿轮诊断模块详细接口文档

> **文档用途**：详细记录 `cloud/app/services/diagnosis/gear/` 子目录下所有函数的完整签名、参数说明和返回值结构。
> **维护要求**：修改任何函数签名或行为时，同步更新本文档。

---

## 目录

1. [行星齿轮箱诊断 (`planetary_demod.py`)](#1-行星齿轮箱诊断-planetary_demodpy)
2. [定轴齿轮VMD解调 (`vmd_demod.py`)](#2-定轴齿轮vmd解调-vmd_demodpy)
3. [MSB残余边频带分析 (`msb.py`)](#3-msb残余边频带分析-msbpy)

---

## 1. 行星齿轮箱诊断 (planetary_demod.py)

### 模块概述

行星齿轮箱专用诊断算法模块，包含五级诊断方法：
- **Level 2**: 窄带包络阶次分析
- **Level 2b**: 全频带包络阶次分析
- **Level 2c**: TSA 中频包络阶次分析
- **Level 2d**: 高通滤波包络阶次分析
- **Level 3**: VMD 幅频联合解调
- **Level 4**: 谱相关/谱相干循环平稳分析
- **Level 5**: MSB 调制信号双谱分析
- **Level 5**: CVS+MED 连续振动分离+MED增强

---

### `_local_background`

```python
def _local_background(oa, os, center, half_bw=0.5, side_bw=1.5)
```

**功能**：局部背景估计，用目标阶次两侧 `±(half_bw+side_bw) ~ ±half_bw` 的幅值均值作为背景。

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `oa` | `np.ndarray` | — | 阶次轴 |
| `os` | `np.ndarray` | — | 阶次谱幅值 |
| `center` | `float` | — | 目标阶次中心 |
| `half_bw` | `float` | `0.5` | 目标半带宽（排除区域） |
| `side_bw` | `float` | `1.5` | 侧边带宽（统计区域） |

**返回值**：`float` — 局部背景幅值均值

**说明**：相比全局中位数，局部背景避免了窄带滤波后>5阶区域几乎无能量导致的SNR虚高问题。

---

### `_band_median_background`

```python
def _band_median_background(oa, os, max_order=5.0)
```

**功能**：频带内中位数背景，对阶次谱在 `0.5~max_order` 阶范围内取中位数。

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `oa` | `np.ndarray` | — | 阶次轴 |
| `os` | `np.ndarray` | — | 阶次谱幅值 |
| `max_order` | `float` | `5.0` | 最大统计阶次 |

**返回值**：`float` — 中位数背景

---

### `_envelope_order_spectrum`

```python
def _envelope_order_spectrum(
    signal: np.ndarray,
    fs: float,
    rot_freq: float,
) -> Tuple[np.ndarray, np.ndarray]
```

**功能**：对信号做 Hilbert 包络 → 去DC → 阶次谱。

**参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `signal` | `np.ndarray` | 输入时域信号 |
| `fs` | `float` | 采样率 Hz |
| `rot_freq` | `float` | 转频 Hz |

**返回值**：`(order_axis, envelope_order_spectrum)` — 阶次轴和包络阶次谱

---

### `planetary_envelope_order_analysis`

```python
def planetary_envelope_order_analysis(
    signal: np.ndarray,
    fs: float,
    rot_freq: float,
    gear_teeth: Dict,
) -> Dict
```

**功能**：Level 2 — 窄带包络阶次分析。对 `mesh_order` 附近频带做窄带滤波 → Hilbert 包络 → 阶次谱，搜索 sun/planet/carrier 故障阶次。

**参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `signal` | `np.ndarray` | 输入时域信号 |
| `fs` | `float` | 采样率 Hz |
| `rot_freq` | `float` | 转频 Hz |
| `gear_teeth` | `Dict` | 齿轮参数（sun, ring, planet, planet_count） |

**返回值** (`dict`)：

| 字段 | 类型 | 说明 |
|------|------|------|
| `method` | `str` | `"planetary_envelope_order"` |
| `order_axis` | `np.ndarray` | 阶次轴 |
| `order_spectrum` | `np.ndarray` | 包络阶次谱 |
| `sun_fault_order` | `float` | 太阳轮故障阶次 |
| `planet_fault_order` | `float` | 行星轮故障阶次 |
| `carrier_order` | `float` | 行星架阶次 |
| `sun_snr` | `float` | 太阳轮 SNR |
| `planet_snr` | `float` | 行星轮 SNR |
| `carrier_snr` | `float` | 行星架 SNR |
| `envelope_kurtosis` | `float` | 包络峭度 |
| `fault_indicators` | `dict` | 故障指示器汇总 |

---

### `planetary_fullband_envelope_order_analysis`

```python
def planetary_fullband_envelope_order_analysis(
    signal: np.ndarray,
    fs: float,
    rot_freq: float,
    gear_teeth: Dict,
) -> Dict
```

**功能**：Level 2b — 全频带包络阶次分析。不经过窄带滤波，直接对全频带信号做包络+阶次谱。

**参数**：同 `planetary_envelope_order_analysis`

**返回值**：同 `planetary_envelope_order_analysis`，`method` 字段为 `"planetary_fullband_envelope"`

---

### `planetary_vmd_demod_analysis`

```python
def planetary_vmd_demod_analysis(
    signal: np.ndarray,
    fs: float,
    rot_freq: float,
    gear_teeth: Dict,
    max_K: int = 5,
) -> Dict
```

**功能**：Level 3 — VMD 幅频联合解调（Feng, Zhang & Zuo 2017）。

**算法流程**：
1. VMD 分解：`K = min(max_K, int(fs / (2 * mesh_freq)))`
2. 选择中心频率最接近 `mesh_freq` 的敏感模态
3. Hilbert 包络 → 幅值解调谱
4. 瞬时频率 → 频率解调谱
5. 在两个解调谱中搜索故障特征阶次

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `signal` | `np.ndarray` | — | 输入时域信号 |
| `fs` | `float` | — | 采样率 Hz |
| `rot_freq` | `float` | — | 转频 Hz |
| `gear_teeth` | `Dict` | — | 齿轮参数 |
| `max_K` | `int` | `5` | VMD模态数上限（2GB服务器限制） |

**返回值** (`dict`)：

| 字段 | 类型 | 说明 |
|------|------|------|
| `method` | `str` | `"planetary_vmd_demod"` |
| `sensitive_mode_index` | `int` | 敏感模态索引 |
| `center_freq` | `float` | 敏感模态中心频率 |
| `amp_demod_freq` | `np.ndarray` | 幅值解调谱频率轴 |
| `amp_demod_spectrum` | `np.ndarray` | 幅值解调谱 |
| `freq_demod_freq` | `np.ndarray` | 频率解调谱频率轴 |
| `freq_demod_spectrum` | `np.ndarray` | 频率解调谱 |
| `sun_snr_amp` / `sun_snr_freq` | `float` | 太阳轮幅值/频率解调SNR |
| `planet_snr_amp` / `planet_snr_freq` | `float` | 行星轮幅值/频率解调SNR |
| `fault_indicators` | `dict` | 故障指示器汇总 |

---

### `planetary_tsa_envelope_analysis`

```python
def planetary_tsa_envelope_analysis(
    signal: np.ndarray,
    fs: float,
    rot_freq: float,
    gear_teeth: Dict,
) -> Dict
```

**功能**：Level 2c — TSA 中频包络阶次分析。先做时域同步平均提取啮合确定性分量，再对残余信号做包络阶次分析。

**参数**：同 `planetary_envelope_order_analysis`

**返回值**：同结构，`method` 为 `"planetary_tsa_envelope"`

---

### `planetary_hp_envelope_order_analysis`

```python
def planetary_hp_envelope_order_analysis(
    signal: np.ndarray,
    fs: float,
    rot_freq: float,
    gear_teeth: Dict,
) -> Dict
```

**功能**：Level 2d — 高通滤波包络阶次分析。用高通滤波去除低频啮合分量，保留高频冲击成分后做包络分析。

**参数**：同 `planetary_envelope_order_analysis`

**返回值**：同结构，`method` 为 `"planetary_hp_envelope"`

---

### `planetary_sc_scoh_analysis`

```python
def planetary_sc_scoh_analysis(
    signal: np.ndarray,
    fs: float,
    rot_freq: float,
    gear_teeth: Dict,
) -> Dict
```

**功能**：Level 4 — 谱相关/谱相干循环平稳分析（SC/SCoh）。分段FFT复数交叉谱平均+PSD频移归一化，搜索循环频率峰值。

**参数**：同 `planetary_envelope_order_analysis`

**返回值** (`dict`)：

| 字段 | 类型 | 说明 |
|------|------|------|
| `method` | `str` | `"planetary_sc_scoh"` |
| `alpha_axis` | `np.ndarray` | 循环频率轴 |
| `sc` | `np.ndarray` | 谱相关密度 |
| `scoh` | `np.ndarray` | 谱相干 |
| `sun_sc_snr` / `sun_scoh_snr` | `float` | 太阳轮SC/SCoh SNR |
| `planet_sc_snr` / `planet_scoh_snr` | `float` | 行星轮SC/SCoh SNR |
| `carrier_sc_snr` | `float` | 行星架SC SNR |
| `fault_indicators` | `dict` | 故障指示器汇总 |

---

### `planetary_msb_analysis`

```python
def planetary_msb_analysis(
    signal: np.ndarray,
    fs: float,
    rot_freq: float,
    gear_teeth: Dict,
) -> Dict
```

**功能**：Level 5 — 调制信号双谱分析（MSB）。分段FFT估计三阶谱，在特征切片位置提取残余边频带信息。

**MSB 定义**：$B(f_c, f_\Delta) = E[X(f_c+f_\Delta) \cdot \text{conj}(X(f_c-f_\Delta)) \cdot X(f_c)]$

**参数**：同 `planetary_envelope_order_analysis`

**返回值** (`dict`)：

| 字段 | 类型 | 说明 |
|------|------|------|
| `method` | `str` | `"planetary_msb"` |
| `msb_se_sun` | `float` | 太阳轮MSB-SE SNR |
| `msb_se_planet` | `float` | 行星轮MSB-SE SNR |
| `residual_sideband_ratio` | `float` | 残余边频带比 |
| `fault_indicators` | `dict` | 故障指示器汇总 |

---

### `planetary_cvs_med_analysis`

```python
def planetary_cvs_med_analysis(
    signal: np.ndarray,
    fs: float,
    rot_freq: float,
    gear_teeth: Dict,
) -> Dict
```

**功能**：Level 5 — 连续振动分离+MED增强（CVS+MED）。利用行星运动周期性分离单个行星轮啮合段，MED增强故障冲击，再做包络分析。

**参数**：同 `planetary_envelope_order_analysis`

**返回值**：同结构，`method` 为 `"planetary_cvs_med"`

---

### `evaluate_planetary_demod_results`

```python
def evaluate_planetary_demod_results(
    narrowband_result: Dict,
    vmd_result: Dict,
) -> Dict
```

**功能**：将多级解调结果（窄带包络、VMD解调等）聚合映射到统一的 `fault_indicators`。

**参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `narrowband_result` | `Dict` | 窄带包络分析结果 |
| `vmd_result` | `Dict` | VMD解调分析结果 |

**返回值**：`dict` — 统一的故障指示器字典

---

## 2. 定轴齿轮VMD解调 (vmd_demod.py)

### 模块概述

定轴齿轮箱 VMD 幅频联合解调分析模块。与行星齿轮箱的区别：
- 边频带间隔 = 转频（非 carrier_order）
- 啮合频率 = gear_teeth × rot_freq（整数阶次）
- SER 正常 < 1.5，> 3.0 为严重故障

---

### `vmd_fixed_axis_demod_analysis`

```python
def vmd_fixed_axis_demod_analysis(
    signal: np.ndarray,
    fs: float,
    rot_freq: float,
    gear_teeth: Dict,
    max_K: int = 5,
    alpha: float = 2000,
) -> Dict
```

**功能**：VMD 幅频联合解调分析（定轴齿轮箱专用）。

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `signal` | `np.ndarray` | — | 输入时域信号 |
| `fs` | `float` | — | 采样率 Hz |
| `rot_freq` | `float` | — | 转频 Hz |
| `gear_teeth` | `Dict` | — | 齿轮参数（需含 input 齿数） |
| `max_K` | `int` | `5` | VMD模态数上限 |
| `alpha` | `float` | `2000` | VMD惩罚因子 |

**返回值** (`dict`)：

| 字段 | 类型 | 说明 |
|------|------|------|
| `method` | `str` | `"vmd_fixed_axis_demod"` |
| `sensitive_mode_index` | `int` | 敏感模态索引 |
| `amp_demod` | `dict` | 幅值解调谱结果（含 SER、边频带列表） |
| `freq_demod` | `dict` | 频率解调谱结果（含 SER、边频带列表） |
| `ser_amp` | `float` | 幅值解调SER |
| `ser_freq` | `float` | 频率解调SER |
| `fault_indicators` | `dict` | 故障指示器汇总 |

---

### `_analyze_fixed_axis_sidebands`

```python
def _analyze_fixed_axis_sidebands(
    amp_freq: np.ndarray,
    amp_spectrum: np.ndarray,
    freq_freq: np.ndarray,
    freq_spectrum: np.ndarray,
    mesh_freq: float,
    rot_freq: float,
    fs: float,
    n_sidebands: int = 6,
    sideband_bw_hz: float = 2.0,
) -> Dict
```

**功能**：在幅值和频率解调谱中搜索 `mesh_freq ± n × rot_freq` 边频带。

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `amp_freq` | `np.ndarray` | — | 幅值解调谱频率轴 |
| `amp_spectrum` | `np.ndarray` | — | 幅值解调谱幅值 |
| `freq_freq` | `np.ndarray` | — | 频率解调谱频率轴 |
| `freq_spectrum` | `np.ndarray` | — | 频率解调谱幅值 |
| `mesh_freq` | `float` | — | 啮合频率 Hz |
| `rot_freq` | `float` | — | 转频 Hz |
| `fs` | `float` | — | 采样率 |
| `n_sidebands` | `int` | `6` | 搜索边频带阶数 |
| `sideband_bw_hz` | `float` | `2.0` | 边频带搜索带宽 Hz |

**返回值**：`dict` — 边频带分析结果（含 SER、显著边频数、各边频幅值）

---

### `_evaluate_fixed_axis_indicators`

```python
def _evaluate_fixed_axis_indicators(
    ser: float,
    significant_count: int,
    mesh_energy: float,
    demod_type: str,
) -> Dict
```

**功能**：根据 SER 和显著边频数评估定轴齿轮故障严重度。

**参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `ser` | `float` | 边频带能量比 |
| `significant_count` | `int` | 显著边频带数量 |
| `mesh_energy` | `float` | 啮合频率能量 |
| `demod_type` | `str` | 解调类型标识 |

**返回值**：`dict` — 故障指示器（含 severity、confidence、description）

---

## 3. MSB残余边频带分析 (msb.py)

### 模块概述

调制信号双谱（MSB）残余边频带分析模块。利用三阶谱估计提取二次相位耦合（QPC）信息，从边频带中分离故障调制分量，不受制造/装配误差干扰。

---

### `msb_residual_sideband_analysis`

```python
def msb_residual_sideband_analysis(
    signal: np.ndarray,
    fs: float,
    mesh_freq: float,
    carrier_freq: float = None,
    n_segments: int = 8,
) -> Dict
```

**功能**：MSB 残余边频带分析入口。分段 FFT 估计 MSB 三阶谱，在特征切片位置提取残余边频带信息。

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `signal` | `np.ndarray` | — | 输入时域信号 |
| `fs` | `float` | — | 采样率 Hz |
| `mesh_freq` | `float` | — | 啮合频率 Hz |
| `carrier_freq` | `float` | `None` | 载波频率（可选） |
| `n_segments` | `int` | `8` | 分段数（类似Welch法） |

**返回值** (`dict`)：

| 字段 | 类型 | 说明 |
|------|------|------|
| `method` | `str` | `"msb_residual_sideband"` |
| `msb_se_slice` | `np.ndarray` | MSB-SE 切片 |
| `fc_axis` | `np.ndarray` | 特征频率轴 |
| `sun_msb_snr` | `float` | 太阳轮 MSB SNR |
| `planet_msb_snr` | `float` | 行星轮 MSB SNR |
| `residual_sideband_ratio` | `float` | 残余边频带比 |
| `fault_indicators` | `dict` | 故障指示器汇总 |

---

### `_compute_slice_snr`

```python
def _compute_slice_snr(
    msb_se_slice: np.ndarray,
    fc_axis: np.ndarray,
    target_freq: float,
    df: float,
    background: float,
) -> float
```

**功能**：从 MSB-SE 切片中指定频率位置计算 SNR。

**参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `msb_se_slice` | `np.ndarray` | MSB-SE 切片幅值 |
| `fc_axis` | `np.ndarray` | 频率轴 |
| `target_freq` | `float` | 目标频率 Hz |
| `df` | `float` | 频率分辨率 |
| `background` | `float` | 背景幅值 |

**返回值**：`float` — SNR 值

---

### `_get_slice_value`

```python
def _get_slice_value(
    msb_se_slice: np.ndarray,
    fc_axis: np.ndarray,
    target_freq: float,
    df: float,
) -> float
```

**功能**：从 MSB-SE 切片中指定频率位置提取幅值。

**参数**：同 `_compute_slice_snr`（不含 background）

**返回值**：`float` — 幅值
