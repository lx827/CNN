# Data View API — 振动数据查看模块

> 本文档说明 `cloud/app/api/data_view/` 模块的所有 RESTful 端点、参数与缓存策略。

---

## 1. 模块概述

Data View 是前端 **DataView.vue** 页面的后端支撑，提供：

- **数据查询**：原始时域波形、设备批次列表
- **实时频谱计算**：FFT、STFT、包络谱、阶次谱、倒谱
- **诊断分析**：齿轮诊断、综合诊断、全算法对比分析
- **诊断缓存**：`/analyze` 和 `/full-analysis` 的结果自动持久化到 `diagnosis` 表
- **数据导出**：CSV 格式下载

**设计原则**：所有频谱计算都是请求时实时计算（不预存），计算结果限制最多处理 **5 秒数据**（`sample_rate * 5` 个采样点）。只有诊断分析结果会被缓存到数据库。

---

## 2. 目录结构

```
data_view/
├── __init__.py       # router 注册 + prepare_signal + _compute_cepstrum + _get_channel_name
├── core.py           # 设备/批次/原始数据/删除
├── spectrum.py       # FFT / STFT / 统计指标
├── envelope.py       # 包络谱（支持多种轴承方法）
├── order.py          # 阶次跟踪（恒定/缓变/变速）
├── cepstrum.py       # 倒谱分析
├── gear.py           # 齿轮诊断 / 综合分析 / 全算法分析
├── export.py         # CSV 导出
└── diagnosis_ops.py  # 诊断缓存查询 / 更新 / 重新诊断
```

---

## 3. 公共函数

### `prepare_signal(signal, detrend=False)`

信号预处理：
- `detrend=False`（默认）：去直流（零均值化）
- `detrend=True`：线性去趋势（消除 `y=kx+b` 漂移）

### `_get_channel_name(device, channel_num)`

从设备配置获取通道名称，未配置时返回默认值：
- `1` → "通道1-轴承附近"
- `2` → "通道2-驱动端"
- `3` → "通道3-风扇端"

---

## 4. 端点列表

### 4.1 数据查询

#### `GET /api/data/devices`
获取所有设备的批次列表（表格展示用）。

**响应**：每个设备的所有批次，含时间、特殊标记、通道数。

---

#### `GET /api/data/{device_id}/batches`
获取某设备的所有批次。

**响应**：批次列表，含 `batch_index`、`created_at`、`is_special`、`channel_count`、`health_score`、`status`。

---

#### `GET /api/data/{device_id}/{batch_index}/{channel}`
获取某批次某通道的原始时域数据。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `detrend` | `bool` | `false` | 是否线性去趋势 |

**响应**：`{ data: [...], sample_rate, time: [...], channel, channel_name }`

---

#### `DELETE /api/data/{device_id}/special`
删除某设备所有特殊批次（`batch_index >= 101`）。

---

#### `DELETE /api/data/{device_id}/{batch_index}`
删除某设备的整条批次数据（所有通道 + 诊断记录 + 告警）。

---

### 4.2 频谱计算（实时，不缓存）

#### `GET /api/data/{device_id}/{batch_index}/{channel}/fft`
实时 FFT 频谱。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `max_freq` | `int` | `5000` | 返回的最大频率 (Hz) |
| `detrend` | `bool` | `false` | 是否线性去趋势 |

---

#### `GET /api/data/{device_id}/{batch_index}/{channel}/stft`
STFT 时频图。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `max_freq` | `int` | `5000` | 最大频率 (Hz) |
| `nperseg` | `int` | `512` | 每段长度 |
| `noverlap` | `int` | `256` | 重叠长度 |
| `detrend` | `bool` | `false` | 是否线性去趋势 |

---

#### `GET /api/data/{device_id}/{batch_index}/{channel}/stats`
统计指标（含滑窗统计）。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `window_size` | `int` | `1024` | 滑窗大小 |
| `step` | `int` | `null` | 滑窗步长（默认 window_size/2） |
| `detrend` | `bool` | `false` | 是否线性去趋势 |

**响应**：`{ rms, peak, peak_to_peak, mean, std, skewness, kurtosis, crest_factor, margin, shape_factor, impulse_factor, windowed: { rms, peak, crest_factor, margin, shape_factor, impulse_factor } }`

---

#### `GET /api/data/{device_id}/{batch_index}/{channel}/envelope`
包络谱分析。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `max_freq` | `int` | `1000` | 最大频率 (Hz) |
| `detrend` | `bool` | `false` | 是否线性去趋势 |
| `method` | `str` | `"envelope"` | 方法：envelope / kurtogram / cpw / med |

---

#### `GET /api/data/{device_id}/{batch_index}/{channel}/order`
阶次跟踪分析。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `freq_min` | `float` | `10.0` | 转频搜索下限 (Hz) |
| `freq_max` | `float` | `100.0` | 转频搜索上限 (Hz) |
| `samples_per_rev` | `int` | `1024` | 每转采样点数 |
| `max_order` | `int` | `50` | 返回的最大阶次 |
| `rot_freq` | `float` | `null` | 直接指定转频 (Hz)，传入则跳过自动估计 |
| `detrend` | `bool` | `false` | 是否线性去趋势 |

---

#### `GET /api/data/{device_id}/{batch_index}/{channel}/cepstrum`
倒谱分析。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `max_quefrency` | `float` | `500.0` | 最大倒频率 (ms) |
| `detrend` | `bool` | `false` | 是否线性去趋势 |

---

### 4.3 诊断分析（结果自动缓存）

#### `GET /api/data/{device_id}/{batch_index}/{channel}/gear`
齿轮诊断分析。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `detrend` | `bool` | `false` | 是否线性去趋势 |
| `method` | `str` | `"standard"` | 方法：standard / advanced |
| `denoise` | `str` | `"none"` | 去噪：none / wavelet / vmd |

**响应**：`{ rot_freq_hz, mesh_freq_hz, mesh_order, ser, sidebands, fm0, fm4, car, m6a, m8a, fault_indicators }`

> **注意**：此端点不缓存结果，每次都是实时计算。

---

#### `GET /api/data/{device_id}/{batch_index}/{channel}/analyze`
综合故障诊断（轴承 + 齿轮 + 时域特征 + 健康度评分）。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `detrend` | `bool` | `false` | 是否线性去趋势 |
| `strategy` | `str` | `"standard"` | 诊断策略：standard / advanced / expert |
| `bearing_method` | `str` | `"envelope"` | 轴承方法：envelope / kurtogram / cpw / med |
| `gear_method` | `str` | `"standard"` | 齿轮方法：standard / advanced |
| `denoise` | `str` | `"none"` | 去噪：none / wavelet / vmd |

**缓存行为**：计算完成后自动写入 `diagnosis` 表的 `engine_result` 字段，键为 `(device_id, batch_index, channel, denoise_method)`。

---

#### `GET /api/data/{device_id}/{batch_index}/{channel}/full-analysis`
全算法对比分析（运行所有轴承方法和所有齿轮方法）。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `detrend` | `bool` | `false` | 是否线性去趋势 |
| `denoise` | `str` | `"none"` | 去噪：none / wavelet / vmd |

**缓存行为**：计算完成后自动写入 `diagnosis` 表的 `full_analysis` 字段，键为 `(device_id, batch_index, channel, denoise_method)`。

---

#### `GET /api/data/{device_id}/{batch_index}/{channel}/diagnosis`
查询缓存的诊断结果（不重新计算）。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `denoise_method` | `str` | `null` | 去噪方法过滤：none / wavelet / vmd / med |

**查询优先级**：
1. 若指定了 `denoise_method`，先精确匹配 `(device, batch, channel, denoise_method)`
2. 无精确匹配时，返回该通道最新诊断记录（不限去噪方法）
3. 仍无结果时，返回批次级诊断记录（兼容旧数据）
4. 都没有则返回 `404`

---

#### `PUT /api/data/{device_id}/{batch_index}/diagnosis`
更新批次诊断结果（主要用于阶次追踪重新计算后写回转频）。

| 参数 | 类型 | 说明 |
|------|------|------|
| `order_analysis` | `dict` | 阶次分析结果（增量更新） |
| `rot_freq` | `float` | 转频 Hz |

---

#### `POST /api/data/{device_id}/{batch_index}/reanalyze`
重新诊断某批次的所有通道数据。

- 跳过耗时去噪（使用 `none`）
- 分析完成后更新 `diagnosis` 表、设备健康度、告警记录
- 标记批次为已分析

---

### 4.4 数据导出

#### `GET /api/data/{device_id}/{batch_index}/{channel}/export`
导出时域数据为 CSV。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `detrend` | `bool` | `false` | 是否线性去趋势 |

**响应**：`text/csv` 文件，格式 `时间(s),振幅`。

---

## 5. 诊断缓存策略详解

### 5.1 缓存键

```
(device_id, batch_index, channel, denoise_method)
```

- 同一组合的新结果会**覆盖**旧记录
- 不同 `denoise_method` 的结果**独立保存**
- 旧数据（无 `denoise_method` 字段）仍可通过批次级回退查询读取

### 5.2 前端缓存查询流程

```
用户点击"计算" / 切换去噪方法
    │
    ▼
GET /{device}/{batch}/{channel}/diagnosis?denoise_method=xxx
    │
    ├── 200 有缓存 ──→ 直接显示缓存结果
    │
    └── 404 无缓存 ──→ GET /{device}/{batch}/{channel}/full-analysis
                           │
                           ▼
                      实时计算并保存到数据库
```

### 5.3 切换通道行为

- 切换通道时**不自动实时计算**全分析
- 自动查询新通道的缓存诊断结果，有则显示，无则收起
- FFT、STFT 等其他分析状态会被重置，需用户手动重新展开

### 5.4 切换去噪方法行为

- 若全分析区域已展开，切换去噪方法后自动查询该方法的缓存
- 有缓存则显示，无缓存则自动触发实时计算
- 计算结果按新去噪方法保存，不影响其他去噪方法的缓存

---

## 6. 性能限制

- **信号长度截断**：所有实时计算最多处理 5 秒数据
- **线程池**：`ThreadPoolExecutor(max_workers=2)`，CPU 密集型计算放入线程池
- **后台分析串行化**：`asyncio.Semaphore(1)`，一次只分析一个批次
- **全算法分析最耗时**：同时运行 4 种轴承方法 + 2 种齿轮方法，约 3~10 秒
