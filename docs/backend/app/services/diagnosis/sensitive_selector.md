# `sensitive_selector.py` — 敏感分量选择


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/sensitive_selector.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `score_components` | `score_components(components, original, fs, target_freq, weights) -> List[float]` | 综合评分 |
| `select_top_components` | `select_top_components(...) -> List[Tuple]` | 选择 Top-K 敏感分量 |
| `select_wp_sensitive_nodes` | `select_wp_sensitive_nodes(signal, fs, level=3) -> List[int]` | 选择小波包敏感节点 |
| `select_emd_sensitive_imfs` | `select_emd_sensitive_imfs(imfs, original, fs) -> List[int]` | 选择 EMD 敏感 IMF |
| `select_vmd_sensitive_modes` | `select_vmd_sensitive_modes(modes, original, fs) -> List[int]` | 选择 VMD 敏感模态 |


## 内部辅助函数

### `compute_correlation`

```python
def compute_correlation(component: np.ndarray, original: np.ndarray) -> float
```

- **参数**:
  - `component` (`np.ndarray`): 待评估分量
  - `original` (`np.ndarray`): 原始信号
- **返回值**：`float` — 分量与原始信号的皮尔逊互相关系数绝对值
- **说明**：计算分量与原始信号的归一化互相关，衡量分量对原始信号的信息保留程度。若任一方标准差过小，返回 0.0

### `compute_excess_kurtosis`

```python
def compute_excess_kurtosis(component: np.ndarray) -> float
```

- **参数**:
  - `component` (`np.ndarray`): 待评估分量
- **返回值**：`float` — 超峭度（正态分布 = 0）
- **说明**：计算四阶统计量（excess kurtosis），故障冲击分量通常具有高峭度值。长度不足 4 或方差过小时返回 0.0

### `compute_envelope_entropy`

```python
def compute_envelope_entropy(component: np.ndarray) -> float
```

- **参数**:
  - `component` (`np.ndarray`): 待评估分量
- **返回值**：`float` — Shannon 包络熵
- **说明**：利用 Hilbert 变换求包络后计算 Shannon 熵。熵越小表示包络越周期性，故障信息越丰富。长度不足 8 时返回 10.0（使其不被选中）

### `compute_energy_ratio`

```python
def compute_energy_ratio(component: np.ndarray, total_energy: float) -> float
```

- **参数**:
  - `component` (`np.ndarray`): 待评估分量
  - `total_energy` (`float`): 原始信号总能量
- **返回值**：`float` — 能量占比 (0~1)
- **说明**：衡量分量的能量贡献，用于判断分量是否包含显著能量信息

### `compute_center_freq`

```python
def compute_center_freq(component: np.ndarray, fs: float) -> float
```

- **参数**:
  - `component` (`np.ndarray`): 待评估分量
  - `fs` (`float`): 采样率 (Hz)
- **返回值**：`float` — 功率谱加权平均中心频率 (Hz)
- **说明**：通过 FFT 功率谱加权平均计算分量的主频率，反映分量的频带位置

### `compute_freq_match_score`

```python
def compute_freq_match_score(center_freq: float, target_freq: float) -> float
```

- **参数**:
  - `center_freq` (`float`): 分量中心频率
  - `target_freq` (`float`): 目标频率（如啮合频率、共振频率）
- **返回值**：`float` — 匹配得分 (0~1)
- **说明**：计算中心频率与目标频率的相对偏差，偏差 <5% 得 1.0，>50% 得 0.0，中间线性衰减。目标频率 ≤0 时返回 0.0

### `_normalize`

```python
def _normalize(values: List[float]) -> List[float]
```

- **参数**:
  - `values` (`List[float]`): 原始值列表
- **返回值**：`List[float]` — Min-max 归一化后的值
- **说明**：将一组值映射到 [0, 1]；若所有值相同则返回全 0.5 列表，避免除零
