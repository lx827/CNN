# `ds_fusion.py` — D-S 证据理论融合

**对应源码**：`cloud/app/services/diagnosis/fusion/ds_fusion.py`

## 类

### `EvidenceFrame`

```python
class EvidenceFrame
```

- **说明**：证据框架类

### `BPA`

```python
class BPA
```

- **说明**：基本概率分配类

## 函数

### `dempster_combination`

```python
def dempster_combination(bpa1: BPA, bpa2: BPA) -> Tuple[BPA, float]
```

- **返回值**：`(combined_bpa, conflict)`
- **说明**：Dempster 组合规则

### `murphy_average_combination`

```python
def murphy_average_combination(bpas: List[BPA]) -> Tuple[BPA, float]
```

- **返回值**：`(avg_bpa, conflict)`
- **说明**：Murphy 平均法（高冲突回退）

### `build_bpa_from_method`

```python
def build_bpa_from_method(hits, method_key) -> BPA
```

- **说明**：从方法结果构建 BPA

### `build_time_domain_bpa`

```python
def build_time_domain_bpa(time_features) -> BPA
```

- **说明**：时域特征 BPA

### `dempster_shafer_fusion`

```python
def dempster_shafer_fusion(method_results, time_features=None) -> dict
```

- **返回值**：`{dominant_fault, dominant_probability, uncertainty, conflict_coefficient, fault_probabilities}`
- **说明**：D-S 融合入口
