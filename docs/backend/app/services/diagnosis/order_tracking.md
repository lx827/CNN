# `order_tracking.py` — 阶次跟踪算法


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/order_tracking.py`

## 函数

### `_compute_order_spectrum`

```python
def _compute_order_spectrum(
    signal: np.ndarray,
    fs: float,
    rot_freq: float,
    samples_per_rev: int = 1024,
    max_order: int = 50,
) -> Tuple[np.ndarray, np.ndarray]
```

- **返回值**：`(order_axis, spectrum)`
- **说明**：单帧阶次跟踪（恒速）

### `_compute_order_spectrum_multi_frame`

```python
def _compute_order_spectrum_multi_frame(
    signal: np.ndarray,
    fs: float,
    freq_range: Tuple[float, float],
    samples_per_rev: int,
    max_order: int,
    frame_duration: float = 1.0,
    overlap: float = 0.5,
) -> Tuple[np.ndarray, np.ndarray, float, float]
```

- **返回值**：`(order_axis, spectrum, rot_freq, rot_std)`
- **说明**：多帧平均阶次跟踪（返回转频估计及标准差）

### `_compute_order_spectrum_varying_speed`

```python
def _compute_order_spectrum_varying_speed(
    signal: np.ndarray,
    fs: float,
    freq_range: Tuple[float, float],
    samples_per_rev: int,
    max_order: int,
) -> Tuple[np.ndarray, np.ndarray, float, float]
```

- **返回值**：`(order_axis, spectrum, rot_freq, rot_std)`
- **说明**：变速阶次跟踪（STFT + 等相位重采样）

### `_order_tracking`

```python
def _order_tracking(
    signal: np.ndarray,
    fs: float,
    rot_freq: float,
    samples_per_rev: int,
    max_order: int,
) -> Tuple
```

- **说明**：底层阶次跟踪实现
