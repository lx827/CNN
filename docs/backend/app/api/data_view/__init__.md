# `__init__.py` — 路由初始化 + 公共函数

**对应源码**：`cloud/app/api/data_view/__init__.py` | `prefix=/api/data` | `tags=[振动数据查看]`

## 函数

### `prepare_signal`

```python
def prepare_signal(signal, detrend: bool = False) -> np.ndarray
```

- **返回值**：`np.ndarray`
- **说明**：信号预处理。实际实现在 `app/services/diagnosis/signal_utils.py`，此处重导出以保持 data_view 子模块兼容。

### `_extract_device_param`

```python
def _extract_device_param(params, device_keys)
```

- **说明**：兼容前端通道级格式 `{"1": {input: 18}}` 与后端设备级格式 `{input: 18}`。统一入口，消除 gear.py / envelope.py 中的重复。

### `_sanitize_for_json`

```python
def _sanitize_for_json(obj) -> Any
```

- **说明**：递归将 numpy 类型转换为 Python 原生类型。统一入口，消除 diagnosis_ops.py 中的重复。

### `_compute_cepstrum`

```python
def _compute_cepstrum(
    sig: np.ndarray,
    fs: float,
    max_quefrency_ms: float = 500.0
) -> Tuple[np.ndarray, np.ndarray, list]
```

- **参数**：
  - `sig: np.ndarray` — 输入信号
  - `fs: float` — 采样率
  - `max_quefrency_ms: float` — 最大倒频率（ms）
- **返回值**：`(quefrency_ms, cepstrum, peaks)` — 倒频率轴、倒谱幅值、峰值列表
- **说明**：计算功率倒谱（加窗 + 对数谱去均值，消除 quefrency=0 处虚假长竖线）

### `_get_channel_name`

```python
def _get_channel_name(device: Device, channel_num: int) -> str
```

- **返回值**：`str` — 通道名称
- **说明**：从设备配置获取通道名称，未配置则使用默认名称
