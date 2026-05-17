# `emd_denoise.py` — EMD/CEEMDAN 分解

**对应源码**：`cloud/app/services/diagnosis/emd_denoise.py`

## 函数

### `emd_decompose`

```python
def emd_decompose(
    signal: np.ndarray,
    max_imfs: int = 10,
    max_sifts: int = 100,
    ...
) -> List[np.ndarray]
```

- **返回值**：`List[np.ndarray]` — IMF 列表
- **说明**：EMD 分解

### `ceemdan_decompose`

```python
def ceemdan_decompose(
    signal: np.ndarray,
    ensemble_size: int = 50,
    noise_std: float = 0.2,
    ...
) -> List[np.ndarray]
```

- **说明**：CEEMDAN 分解（抑制模态混叠）

### `eemd_decompose`

```python
def eemd_decompose(
    signal: np.ndarray,
    ensemble_size: int = 100,
    noise_std: float = 0.2,
    ...
) -> List[np.ndarray]
```

- **说明**：EEMD 分解

### `compute_imf_energy_entropy`

```python
def compute_imf_energy_entropy(imfs: List[np.ndarray]) -> Dict
```

- **返回值**：`Dict` — IMF 能量熵
- **说明**：IMF 能量熵计算

### `emd_denoise`

```python
def emd_denoise(
    signal: np.ndarray,
    method: str = "ceemdan",
    corr_threshold: float = 0.35,
    kurt_threshold: float = 3.5,
) -> Tuple[np.ndarray, Dict]
```

- **返回值**：`(去噪信号, 元信息)`
- **说明**：EMD/CEEMDAN/EEMD 降噪入口
