# `__init__.py` — 路由初始化 + 公共函数

**对应源码**：`cloud/app/api/data_view/__init__.py` | `prefix=/api/data` | `tags=[振动数据查看]`

## 函数

### `prepare_signal`

```python
def prepare_signal(signal, detrend: bool = False) -> np.ndarray
```

- **返回值**：`np.ndarray`
- **说明**：信号预处理。`detrend=False` 去直流（零均值化），`detrend=True` 线性去趋势

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
