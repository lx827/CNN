# `ds_fusion.py` — D-S 证据理论融合


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/fusion/ds_fusion.py`

## 类

### `EvidenceFrame`

```python
class EvidenceFrame
```

- **说明**：证据框架类

#### `__init__`

```python
def __init__(self, fault_types: List[str])
```

| 参数 | 类型 | 说明 |
|------|------|------|
| fault_types | `List[str]` | 故障类型字符串列表 |

- **说明**：初始化识别框架，去重并排序故障类型，Θ 用 `"Θ"` 标签表示全集

#### `all_elements`

```python
@property
def all_elements(self) -> List[str]
```

- **返回值**：`List[str]`
- **说明**：识别框架的全部元素（故障类型列表）

#### `make_singleton_key`

```python
def make_singleton_key(self, fault: str) -> FrozenSet[str]
```

| 参数 | 类型 | 说明 |
|------|------|------|
| fault | `str` | 单个故障类型名称 |

- **返回值**：`FrozenSet[str]`
- **说明**：生成单元素焦元键（frozenset 包装），用于 D-S 理论中的单点假设

#### `make_full_key`

```python
def make_full_key(self) -> FrozenSet[str]
```

- **返回值**：`FrozenSet[str]`
- **说明**：生成 Θ 焦元键（全集 = Ω = 所有故障类型的集合）。Θ 在 D-S 理论中表示“不确定性”，用 `frozenset(fault_types)` 表示使得交集运算正确：`A∩Θ=A`, `Θ∩Θ=Θ`, `A∩B=∅`（当 A,B 无公共元素）

### `BPA`

```python
class BPA
```

- **说明**：基本概率分配类

#### `__init__`

```python
def __init__(self, frame: EvidenceFrame, masses: Dict[FrozenSet[str], float])
```

| 参数 | 类型 | 说明 |
|------|------|------|
| frame | `EvidenceFrame` | 所属识别框架 |
| masses | `Dict[FrozenSet[str], float]` | 焦元到质量的原始映射 |

- **说明**：初始化 BPA 并自动归一化。确保 `sum(m(A)) = 1` 且 `m(∅)=0`；若当前和小于 1.0，补齐 Θ；若大于 1.0，重新归一化

#### `get_mass`

```python
def get_mass(self, focal: FrozenSet[str]) -> float
```

| 参数 | 类型 | 说明 |
|------|------|------|
| focal | `FrozenSet[str]` | 焦元键 |

- **返回值**：`float`
- **说明**：获取指定焦元的质量（mass），若不存在则返回 0.0

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

### `_classify_method`

```python
def _classify_method(method_key: str) -> str
```

| 参数 | 类型 | 说明 |
|------|------|------|
| method_key | `str` | 方法键，格式如 `"none:envelope"`、`"wavelet:cpw"` |

- **返回值**：`str` — `"bearing"`、`"gear"` 或 `"unknown"`
- **说明**：通过关键词匹配判断诊断方法类型。轴承方法关键词包括 `envelope`、`kurtogram`、`cpw`、`med`、`teager`、`spectral_kurtosis`、`bearing` 等；齿轮方法关键词包括 `standard`、`advanced`、`gear`

### `_map_hits_to_faults`

```python
def _map_hits_to_faults(hits: List[str], method_type: str, fault_types: List[str]) -> List[str]
```

| 参数 | 类型 | 说明 |
|------|------|------|
| hits | `List[str]` | 诊断指标命中列表（如 `["bpfo"]`、`["ser"]`） |
| method_type | `str` | 方法类型 `"bearing"` 或 `"gear"` |
| fault_types | `List[str]` | 当前识别框架中的有效故障类型 |

- **返回值**：`List[str]` — 映射后的具体故障类型列表
- **说明**：将诊断指标名称映射到故障类型集合中的具体故障。根据 `BEARING_FAULT_NAMES` 或 `GEAR_FAULT_NAMES` 查找对应关系，并过滤掉不在当前识别框架中的故障

### `compute_belief`

```python
def compute_belief(bpa: BPA, focal: FrozenSet[str]) -> float
```

| 参数 | 类型 | 说明 |
|------|------|------|
| bpa | `BPA` | 基本概率分配对象 |
| focal | `FrozenSet[str]` | 目标焦元 |

- **返回值**：`float` — 信念值 Bel(A)
- **说明**：计算 D-S 信念函数 `Bel(A) = Σ_{B⊆A} m(B)`，表示对目标假设 A 的最低置信度

### `compute_plausibility`

```python
def compute_plausibility(bpa: BPA, focal: FrozenSet[str]) -> float
```

| 参数 | 类型 | 说明 |
|------|------|------|
| bpa | `BPA` | 基本概率分配对象 |
| focal | `FrozenSet[str]` | 目标焦元 |

- **返回值**：`float` — 似然值 Pl(A)
- **说明**：计算 D-S 似然函数 `Pl(A) = Σ_{B∩A≠∅} m(B)`，表示对目标假设 A 的最高可能置信度
