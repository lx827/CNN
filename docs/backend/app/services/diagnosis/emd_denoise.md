# `emd_denoise.py` — EMD/CEEMDAN 分解


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
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


### `_find_extrema`

```python
def _find_extrema(signal: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]
```

- **参数**:
  - `signal` (`np.ndarray`): 输入信号
- **返回值**：`(maxima_idx, minima_idx, zero_cross)` — 局部极大值索引、局部极小值索引、过零点索引
- **说明**：通过一阶差分符号变化定位局部极值点和过零点，为 EMD 筛分提供极值位置基础

### `_refine_extrema_parabolic`

```python
def _refine_extrema_parabolic(signal: np.ndarray, idx: np.ndarray) -> np.ndarray
```

- **参数**:
  - `signal` (`np.ndarray`): 输入信号
  - `idx` (`np.ndarray`): 极值点整数索引
- **返回值**：`np.ndarray` — 精化后的浮点极值位置
- **说明**：对每三个相邻点（i-1, i, i+1）做抛物线插值求顶点，得到更精确的极值位置，提高包络插值精度

### `_pad_extrema_rilling`

```python
def _pad_extrema_rilling(
    signal: np.ndarray,
    max_idx: np.ndarray,
    min_idx: np.ndarray,
    pad_width: int = 3,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]
```

- **参数**:
  - `signal` (`np.ndarray`): 输入信号
  - `max_idx` (`np.ndarray`): 极大值索引
  - `min_idx` (`np.ndarray`): 极小值索引
  - `pad_width` (`int`): 每侧镜像填充极值数量
- **返回值**：`(max_locs, max_mags, min_locs, min_mags)` — 填充后的极值位置与幅值
- **说明**：Rilling 边界镜像填充。根据信号端点值与最近极值的大小关系确定对称轴，向两侧镜像延拓极值，缓解 EMD 端点效应

### `_compute_envelope_mean`

```python
def _compute_envelope_mean(
    signal: np.ndarray,
    max_idx: np.ndarray,
    min_idx: np.ndarray,
    use_pchip: bool = True,
    pad_width: int = 3,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]
```

- **参数**:
  - `signal` (`np.ndarray`): 输入信号
  - `max_idx` (`np.ndarray`): 极大值索引
  - `min_idx` (`np.ndarray`): 极小值索引
  - `use_pchip` (`bool`): True 使用 PchipInterpolator（保守无过冲），False 使用 CubicSpline
  - `pad_width` (`int`): 边界填充宽度
- **返回值**：`(envelope_mean, upper_env, lower_env)` — 上下包络均值、上包络、下包络
- **说明**：先精化极值位置并做 Rilling 边界填充，再插值得到上下包络，最后取平均得到局部均值，用于 EMD 筛分

### `_stop_sd`

```python
def _stop_sd(proto_imf: np.ndarray, old: np.ndarray) -> float
```

- **参数**:
  - `proto_imf` (`np.ndarray`): 当前筛分结果
  - `old` (`np.ndarray`): 上一轮筛分结果
- **返回值**：`float` — 标准差比值
- **说明**：Huang 1998 标准 SD 停止准则。计算两轮差值的能量比 `Σ(proto_imf - old)² / Σ(old²)`，小于阈值则停止筛分

### `_stop_rilling`

```python
def _stop_rilling(
    upper_env: np.ndarray,
    lower_env: np.ndarray,
    sd1: float = 0.05,
    sd2: float = 0.5,
    tol: float = 0.05,
) -> bool
```

- **参数**:
  - `upper_env` (`np.ndarray`): 上包络
  - `lower_env` (`np.ndarray`): 下包络
  - `sd1` (`float`): 严格阈值（默认 0.05）
  - `sd2` (`float`): 宽松阈值（默认 0.5）
  - `tol` (`float`): 允许超过 sd1 的比例上限（默认 0.05 = 5%）
- **返回值**：`bool` — 是否停止筛分
- **说明**：Rilling 停止准则。评估包络对称性 `E(t) = |avg_env(t)| / amp(t)`。停止条件为：(E < sd1 的比例 ≥ 1-tol) 且 (所有点 E < sd2)

### `_excess_kurtosis`

```python
def _excess_kurtosis(x: np.ndarray) -> float
```

- **参数**:
  - `x` (`np.ndarray`): 输入序列
- **返回值**：`float` — 超峭度（正态分布 = 0）
- **说明**：计算四阶中心矩标准化后的超峭度，与 scipy.stats.kurtosis(fisher=True) 一致。长度不足 4 或方差过小时返回 0.0
