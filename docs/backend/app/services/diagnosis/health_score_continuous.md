# `health_score_continuous.py` — 连续衰减扣分


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/health_score_continuous.py`

## 函数

### `sigmoid_deduction`

```python
def sigmoid_deduction(
    value: float,
    threshold: float,
    max_deduction: float,
    slope: float = 2.0,
) -> float
```

- **返回值**：`float` (0 ~ max_deduction)
- **说明**：连续 sigmoid 衰减扣分，消除阈值边界跳变

### `multi_threshold_deduction`

```python
def multi_threshold_deduction(
    value: float,
    thresholds: list,
    max_deductions: list,
    slope: float = 2.0,
) -> float
```

- **说明**：多阈值连续扣分（取各阈值 sigmoid 最大值的组合）

### `cascade_deduction`

```python
def cascade_deduction(
    value: float,
    thresholds: list,
    max_deductions: list,
    slope: float = 2.0,
) -> float
```

- **说明**：级联连续扣分（每级 sigmoid 贡献增量，不超过最高阶梯）

### `compute_continuous_deductions`

```python
def compute_continuous_deductions(
    time_features: Dict,
    gear_teeth: Optional[Dict],
    bearing_result: Dict,
    gear_result: Dict,
) -> list
```

- **返回值**：`[("deduction_name", float_value), ...]`
- **说明**：连续扣分计算入口

**扣分路径**：
1. 时域特征（kurtosis/crest_factor）
2. 动态基线/趋势（rms_mad_z/kurtosis_mad_z/ewma_drift/cusum_score）
3. 轴承故障（频率匹配 + 统计）
4. 齿轮故障（SER/sideband/TSA残差峭度）
5. SC/SCoh 循环平稳补充
6. NA4/NB4 趋势指标
7. 小波包能量熵
