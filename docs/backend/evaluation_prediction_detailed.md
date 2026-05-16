# 评估与预测模块详细文档

> 本文档详细说明 `cloud/app/services/diagnosis/` 目录下与健康度评分、概率校准、趋势预测及诊断建议相关的四个核心模块。

---

## 文件：`health_score_continuous.py`

> 连续衰减扣分函数模块。将 `health_score.py` 中原有的离散阶梯扣分替换为连续衰减函数，消除阈值边界处的不连续跳变。

**模块常量**

| 常量名 | 类型 | 值 | 说明 |
|--------|------|-----|------|
| `DEFAULT_SLOPE` | `float` | `2.0` | 默认 sigmoid 过渡斜率，控制过渡带宽度。slope=2.0 时过渡带约 ±3 个单位。 |

---

### sigmoid_deduction

```python
def sigmoid_deduction(
    value: float,
    threshold: float,
    max_deduction: float,
    slope: float = DEFAULT_SLOPE,
) -> float
```

**功能说明**

连续 sigmoid 衰减扣分函数。核心公式为 `f(x) = max_deduction × sigmoid((x - threshold) × slope)`，其中 `sigmoid(t) = 1 / (1 + exp(-t))`。

特性：
- 当 `value < threshold` 时，扣分趋近于 0；
- 当 `value > threshold` 时，扣分趋近于 `max_deduction`；
- 在 `threshold` 附近平滑过渡，无阶跃跳变；
- 对极端值做防溢出处理（`t > 20` 直接返回 `max_deduction`，`t < -20` 直接返回 `0.0`）。

**参数说明**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `value` | `float` | — | 当前指标值（如峭度 `kurtosis=5.01`） |
| `threshold` | `float` | — | 阈值（如 `5.0`） |
| `max_deduction` | `float` | — | 最大扣分值（如 `15.0`） |
| `slope` | `float` | `DEFAULT_SLOPE`（`2.0`） | 过渡斜率。越大过渡越陡，越小越缓。`slope=1` 约 ±6 单位过渡带；`slope=2` 约 ±3 单位；`slope=3` 约 ±2 单位。 |

**返回值说明**

- **类型**：`float`
- **说明**：连续扣分值，范围在 `0 ~ max_deduction` 之间。当指标值远低于阈值时接近 0，远高于阈值时接近最大扣分值，在阈值附近平滑过渡。

---

### multi_threshold_deduction

```python
def multi_threshold_deduction(
    value: float,
    thresholds: list,
    max_deductions: list,
    slope: float = DEFAULT_SLOPE,
) -> float
```

**功能说明**

多阈值连续扣分函数，用于替代传统的 `if/elif` 阶梯链扣分逻辑。原阶梯逻辑（如峭度 `kurt > 20` 扣 40 分、`kurt > 12` 扣 30 分等）在阈值边界处存在跳变，本函数通过取各阈值 sigmoid 扣分的最大值实现平滑过渡。

实现方式：将 `thresholds` 与 `max_deductions` 配对后从小到大排序，依次计算每级 sigmoid 扣分，最终取所有级别中的最大扣分值。这样可确保低阈值在指标值远高于高阈值时仍能贡献扣分。

**参数说明**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `value` | `float` | — | 当前指标值 |
| `thresholds` | `list` | — | 阈值列表，应从小到大排列（如 `[5, 8, 12, 20]`） |
| `max_deductions` | `list` | — | 与阈值列表对应的扣分列表（如 `[15, 22, 30, 40]`） |
| `slope` | `float` | `DEFAULT_SLOPE`（`2.0`） | 过渡斜率，传给底层的 `sigmoid_deduction` |

**返回值说明**

- **类型**：`float`
- **说明**：连续扣分值。若 `thresholds` 或 `max_deductions` 为空，则返回 `0.0`。

---

### cascade_deduction

```python
def cascade_deduction(
    value: float,
    thresholds: list,
    max_deductions: list,
    slope: float = DEFAULT_SLOPE,
) -> float
```

**功能说明**

级联连续扣分函数，是 `multi_threshold_deduction` 的更精确版本，专门用于替代 `elif` 阶梯链。在原阶梯逻辑中，总扣分等于指标值所跨越的最高阶梯的扣分值；而级联替代的逻辑是：每级 sigmoid 扣分贡献的是"本级增量"（即本级 `max_deduction` 减去上一级 `max_deduction` 的差值），最终总扣分为各级增量乘以对应 sigmoid 的累加和。

示例（轴承峭度 `thresholds=[5,8,12,20]`, `deductions=[15,22,30,40]`）：
- `kurt=4.5`：所有 sigmoid ≈ 0 → 总扣分 ≈ 0
- `kurt=6.0`：sigmoid(6,5)≈0.73（增量15），sigmoid(6,8)≈0（增量7） → ≈ 15×0.73 = 10.95
- `kurt=10`：≈ 15 + 7×0.73 = 20.1
- `kurt=25`：≈ 15 + 7 + 8 + 10 = 40

**参数说明**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `value` | `float` | — | 当前指标值 |
| `thresholds` | `list` | — | 阈值列表，从小到大排列 |
| `max_deductions` | `list` | — | 对应扣分列表 |
| `slope` | `float` | `DEFAULT_SLOPE`（`2.0`） | 过渡斜率 |

**返回值说明**

- **类型**：`float`
- **说明**：连续扣分值，不会超过 `max(max_deductions)`。若输入列表为空则返回 `0.0`。

---

### compute_continuous_deductions

```python
def compute_continuous_deductions(
    time_features: Dict,
    gear_teeth: Optional[Dict],
    bearing_result: Dict,
    gear_result: Dict,
) -> list
```

**功能说明**

连续衰减扣分计算的主入口函数，用于替代 `health_score.py` 中的离散阶梯扣分逻辑。函数接收时域特征、齿轮参数、轴承诊断结果和齿轮诊断结果，综合计算出一组连续扣分项。

返回格式与 `health_score.py` 中原有的 `deductions` 列表保持一致：`[("deduction_name", float_deduction_value), ...]`，因此可直接替换调用而不改变下游逻辑。

扣分逻辑涵盖以下维度：
1. **时域特征**：峭度（kurtosis）连续扣分、峰值因子（crest_factor）连续扣分；
2. **动态基线/趋势**：基于 `rms_mad_z`、`kurtosis_mad_z`、`ewma_drift`、`cusum_score` 的基线偏离和趋势漂移扣分（需时域冲击证据门控）；
3. **轴承故障**：频率匹配路径（需峭度门控）、统计路径、边带密度/不对称增强扣分、SC/SCoh 循环平稳补充扣分；
4. **齿轮故障**：SER 边频带、边频数量、FM0/CAR、阶次统计指标、TSA 残差峭度、NA4/NB4 趋势指标、小波包能量熵；
5. **门控策略**：齿轮设备与轴承设备使用不同的峭度/峰值因子阈值；`rotation_dominant` 时降权；时域证据不足时抑制非时域扣分。

**参数说明**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `time_features` | `Dict` | — | 时域特征字典，应包含 `kurtosis`、`crest_factor`、`rms`、`rms_mad_z`、`kurtosis_mad_z`、`ewma_drift`、`cusum_score` 等键 |
| `gear_teeth` | `Optional[Dict]` | `None` | 齿轮齿数参数字典。若包含 `"input"` 键且值大于 0，则判定为齿轮设备，使用齿轮设备的阈值策略 |
| `bearing_result` | `Dict` | — | 轴承诊断结果字典，通常包含 `fault_indicators`、`method`、`sc_max_value` 等键 |
| `gear_result` | `Dict` | — | 齿轮诊断结果字典，通常包含 `fault_indicators`、`planetary_tsa_demod`、`na4`、`nb4`、`wavelet_packet_entropy` 等键 |

**返回值说明**

- **类型**：`list`
- **说明**：扣分列表，每个元素为 `(deduction_name: str, deduction_value: float)` 元组。`deduction_name` 根据扣分严重程度精细标注（如 `kurtosis_extreme`、`kurtosis_high`、`kurtosis_moderate`、`kurtosis_mild` 等）。

---

## 文件：`probability_calibration.py`

> 置信度概率校准模块。将原始 SNR/指标值映射的"概率"校准为真实似然，使用 sigmoid 映射将连续值压缩到 `[0, 1]` 区间，并确保 `fault_probabilities` 总和 ≤ 1.0。

**模块常量**

| 常量名 | 类型 | 值 | 说明 |
|--------|------|-----|------|
| `CALIB_THRESHOLD` | `float` | `5.0` | SNR 校准阈值，健康/故障分界点 |
| `CALIB_MAX_PROB` | `float` | `0.85` | 即使 SNR 很高，单指标概率上限（避免过度自信） |
| `CALIB_SLOPE` | `float` | `1.5` | 默认过渡斜率，过渡带约 ±4 SNR 单位 |

---

### _sigmoid_prob

```python
def _sigmoid_prob(
    value: float,
    threshold: float = CALIB_THRESHOLD,
    max_prob: float = CALIB_MAX_PROB,
    slope: float = CALIB_SLOPE,
) -> float
```

**功能说明**

内部辅助函数，执行 sigmoid 校准：将连续值（通常是 SNR 或原始概率）映射为 `[0, max_prob]` 区间内的概率值。对极端值做防溢出处理（`t > 20` 直接返回 `max_prob`，`t < -20` 直接返回 `0.0`）。

**参数说明**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `value` | `float` | — | 待校准的连续值 |
| `threshold` | `float` | `CALIB_THRESHOLD`（`5.0`） | sigmoid 中心阈值 |
| `max_prob` | `float` | `CALIB_MAX_PROB`（`0.85`） | 概率上限 |
| `slope` | `float` | `CALIB_SLOPE`（`1.5`） | 过渡斜率 |

**返回值说明**

- **类型**：`float`
- **说明**：校准后的概率值，范围在 `[0.0, max_prob]` 之间。

---

### calibrate_fault_probabilities

```python
def calibrate_fault_probabilities(
    raw_probs: Dict[str, float],
    calibration_map: Dict[str, Tuple[float, float, float]] = None,
) -> Dict[str, float]
```

**功能说明**

校准故障概率的主函数。将原始概率（通常通过 `SNR/10` 简单映射得到）转换为更接近真实故障似然的概率值。

处理流程：
1. 遍历 `raw_probs` 中的每种故障类型（跳过 `"正常运行"`）；
2. 若提供了 `calibration_map` 且故障类型在其中，则使用自定义的 `(threshold, max_prob, slope)` 参数进行校准；否则使用默认参数（`threshold=0.2, max_prob=0.85, slope=6.0`）进行 sigmoid 映射；
3. 若所有故障概率之和超过 `1.0`，则按比例压缩归一化；
4. 最后计算 `"正常运行"` 的概率为 `1.0 - 所有故障概率之和`。

**参数说明**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `raw_probs` | `Dict[str, float]` | — | 原始故障概率字典，格式如 `{"轴承外圈故障": 0.5, "齿轮磨损": 0.3, ...}` |
| `calibration_map` | `Dict[str, Tuple[float, float, float]]` | `None` | 自定义校准参数字典。键为故障类型，值为 `(threshold, max_prob, slope)` 三元组。若为 `None` 则使用默认参数。 |

**返回值说明**

- **类型**：`Dict[str, float]`
- **说明**：校准后的概率字典。所有故障概率之和 ≤ 1.0，并包含 `"正常运行"` 键表示正常运行的概率。每个值保留 4 位小数。

---

### calibrate_snr_to_prob

```python
def calibrate_snr_to_prob(
    snr: float,
    fault_type: str = "generic",
) -> float
```

**功能说明**

将 SNR（信噪比）值直接校准为故障概率。主要用于 `ensemble.py` 中替代原有的 `SNR → probability` 简单线性映射。基于健康数据 SNR 中位数 ≈ 2.0、故障数据 SNR 中位数 ≈ 8.0 的统计规律，以 `threshold=5.0` 作为分界点进行 sigmoid 校准。

**参数说明**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `snr` | `float` | — | 信噪比（包络谱峰值 SNR） |
| `fault_type` | `str` | `"generic"` | 故障类型（预留参数，用于未来选择不同校准参数） |

**返回值说明**

- **类型**：`float`
- **说明**：校准后的概率值，范围在 `0.0 ~ 0.85` 之间。

---

## 文件：`trend_prediction.py`

> 健康度趋势预测模块。提供 Holt-Winters 三阶指数平滑和 Kalman 滤波两种趋势预测算法，用于预测设备健康度变化趋势和退化速率。仅依赖 `numpy`，无第三方库依赖。

---

### holt_winters_forecast

```python
def holt_winters_forecast(
    health_scores: List[float],
    timestamps: List[float],
    forecast_steps: int = 3,
    alpha: float = 0.3,
    beta: float = 0.1,
    gamma: float = 0.05,
    season_length: int = None,
) -> Dict[str, Any]
```

**功能说明**

Holt-Winters 三阶指数平滑预测健康度趋势。使用加法模型：
- 水平分量：`l(t) = α·y(t) + (1-α)·(l(t-1) + b(t-1))`
- 趋势分量：`b(t) = β·(l(t) - l(t-1)) + (1-β)·b(t-1)`
- 季节分量：`s(t) = γ·(y(t) - l(t)) + (1-γ)·s(t-m)`
- 预测值：`y(t+h) = l(t) + h·b(t) + s(t+h-m)`

当 `season_length=None` 时，退化为 Holt 双指数平滑（线性趋势预测）。

安全退化处理：
- 空序列：返回全空结果，`trend_direction="stable"`，`confidence=0.0`；
- 单点：返回常数预测，`confidence=0.1`；
- 2~4 个点：使用简单线性回归作为退化预测，`confidence=0.3`。

**参数说明**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `health_scores` | `List[float]` | — | 历史健康度序列，值域通常为 0~100 |
| `timestamps` | `List[float]` | — | 对应的时间戳序列（秒或 Unix 时间戳） |
| `forecast_steps` | `int` | `3` | 向前预测的步数 |
| `alpha` | `float` | `0.3` | 水平平滑系数 |
| `beta` | `float` | `0.1` | 趋势平滑系数 |
| `gamma` | `float` | `0.05` | 季节平滑系数（仅在 `season_length` 非 `None` 时生效） |
| `season_length` | `int` | `None` | 季节周期长度。`None` 表示无季节性 |

**返回值说明**

- **类型**：`Dict[str, Any]`
- **说明**：包含以下键的字典：

| 键 | 类型 | 说明 |
|----|------|------|
| `forecast_values` | `List[float]` | 预测的健康度值（已限制在 0~100） |
| `forecast_timestamps` | `List[float]` | 预测对应的时间戳 |
| `level_series` | `List[float]` | 水平分量序列 |
| `trend_series` | `List[float]` | 趋势分量序列 |
| `season_series` | `List[float]` | 季节分量序列（无季节性时全为 0） |
| `trend_direction` | `str` | 趋势方向：`"improving"`（改善）、`"stable"`（稳定）、`"degrading"`（退化） |
| `estimated_degradation_rate` | `float` | 估计退化速率（健康度/时间单位） |
| `confidence` | `float` | 预测置信度（0~1），基于残差方差计算。残差方差越小，置信度越高 |

---

### kalman_smooth_health_scores

```python
def kalman_smooth_health_scores(
    health_scores: List[float],
    process_noise: float = 1.0,
    measurement_noise: float = 5.0,
) -> Dict[str, Any]
```

**功能说明**

Kalman 滤波平滑 `health_score` 序列。使用二维状态向量 `x = [health_score, degradation_rate]`，状态转移矩阵 `F = [[1, dt], [0, 1]]`，观测矩阵 `H = [[1, 0]]`。

采用 Joseph 形式进行协方差更新以保证数值稳定性。过程噪声 `Q` 和观测噪声 `R` 可调，默认值适合健康度 0~100 的场景。

安全退化处理：
- 空序列：返回全空结果，`current_trend="stable"`，`prediction_confidence=0.0`；
- 少于 5 个点：使用简单移动平均作为平滑结果，`prediction_confidence=0.3`。

**参数说明**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `health_scores` | `List[float]` | — | 历史健康度序列，值域通常为 0~100 |
| `process_noise` | `float` | `1.0` | 过程噪声标准差。控制状态转移的不确定性 |
| `measurement_noise` | `float` | `5.0` | 观测噪声标准差。控制观测值的不确定性 |

**返回值说明**

- **类型**：`Dict[str, Any]`
- **说明**：包含以下键的字典：

| 键 | 类型 | 说明 |
|----|------|------|
| `smoothed_scores` | `List[float]` | Kalman 滤波平滑后的健康度序列 |
| `estimated_rates` | `List[float]` | 估计的退化速率序列 |
| `prediction_confidence` | `float` | 预测置信度（0~1），基于最终状态协方差的 health 分量计算。方差越小，置信度越高 |
| `current_trend` | `str` | 当前趋势方向：`"improving"`、`"stable"` 或 `"degrading"` |

---

### _simple_linear_regression

```python
def _simple_linear_regression(
    x: np.ndarray,
    y: np.ndarray,
) -> tuple
```

**功能说明**

简单线性回归辅助函数，使用最小二乘法拟合 `y = slope * x + intercept`。用于短序列的退化预测和 Holt-Winters 趋势初始化。若输入长度小于 2，则返回退化值（斜率为 0，截距为单点值或 0）；若 `x` 的方差为 0，则返回斜率为 0、截距为 `y` 均值。

**参数说明**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `x` | `np.ndarray` | — | 自变量数组 |
| `y` | `np.ndarray` | — | 因变量数组 |

**返回值说明**

- **类型**：`tuple`
- **说明**：`(slope, intercept)` 二元组。`slope` 为回归斜率，`intercept` 为截距。

---

## 文件：`recommendation.py`

> 诊断建议生成模块。根据诊断结果中的 `deductions`、故障指示器、D-S 冲突标记等信息生成面向运维人员的维护建议文本。

**模块常量**

| 常量名 | 类型 | 说明 |
|--------|------|------|
| `SUGGESTION_MAP` | `Dict[tuple, str]` | 精确建议映射表。键为排序后的扣分名称元组（长度 1~3），值为对应的精确建议字符串。 |

`SUGGESTION_MAP` 中预置的典型映射包括：
- `("kurtosis_high", "bearing_multi_freq")` → 轴承复合故障建议
- `("gear_ser_critical", "gear_tsa_residual_kurtosis_critical")` → 齿轮断齿建议
- `("gear_ser_warning", "gear_car_warning")` → 齿轮磨损建议
- `("bearing_sc_scoh_evidence",)` → 早期微弱轴承故障建议
- `("ds_conflict_penalty",)` → D-S 高冲突人工复核建议
- 等

---

### _match_suggestion

```python
def _match_suggestion(
    deductions: list,
) -> Optional[str]
```

**功能说明**

从 `deductions` 列表中匹配最精确的建议。提取所有扣分名称后排序，然后从长到短（优先最长组合，最大长度 3）依次尝试匹配 `SUGGESTION_MAP` 中的键。这种策略确保在存在多个扣分项时，优先返回最具体的组合建议而非通用建议。

**参数说明**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `deductions` | `list` | — | deductions 列表，每个元素通常为 `(name: str, value: float)` 元组 |

**返回值说明**

- **类型**：`Optional[str]`
- **说明**：匹配到的精确建议字符串；若没有任何匹配则返回 `None`。

---

### _generate_recommendation

```python
def _generate_recommendation(
    bearing_result: Dict,
    gear_result: Dict,
    status: str,
    ds_conflict_high: bool = False,
    deductions: Optional[list] = None,
) -> str
```

**功能说明**

生成单方法/单通道的诊断建议。采用四层优先级策略：
1. **精确建议映射表**（最高优先级）：基于 `deductions` 组合从 `SUGGESTION_MAP` 中匹配最精确的建议；若同时存在 `ds_conflict_high`，则在建议末尾追加冲突提示；
2. **D-S 高冲突提示**：若 `ds_conflict_high=True`，提示多种诊断方法结果不一致，建议人工复核；
3. **传统条件分支建议**：依次检查轴承故障特征、齿轮 SER/边频/FM0/CAR 等指标的严重程度，生成对应的维护建议；
4. **通用兜底**：若以上均未生成建议，则返回通用异常提示。

当 `status == "normal"` 时，直接返回正常运行建议。

**参数说明**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `bearing_result` | `Dict` | — | 轴承诊断结果字典，通常包含 `fault_indicators`、`method`、`features` 等 |
| `gear_result` | `Dict` | — | 齿轮诊断结果字典，通常包含 `fault_indicators` 及各类齿轮指标 |
| `status` | `str` | — | 设备综合状态，如 `"normal"`、`"warning"`、`"critical"` |
| `ds_conflict_high` | `bool` | `False` | D-S 证据理论融合冲突标记。为 `True` 时表示多种方法结果冲突严重（冲突系数 > 0.8） |
| `deductions` | `Optional[list]` | `None` | 连续扣分列表，用于精确建议映射。若为 `None` 则跳过精确匹配层 |

**返回值说明**

- **类型**：`str`
- **说明**：诊断建议文本。可能包含多条建议，以空格连接。若设备正常则返回 `"设备运行正常，建议按周期继续监测。"`。

---

### _generate_recommendation_all

```python
def _generate_recommendation_all(
    bearing_results: Dict,
    gear_results: Dict,
    status: str,
) -> str
```

**功能说明**

基于所有诊断方法的结果生成综合建议。与 `_generate_recommendation` 不同，本函数汇总多个轴承方法和多个齿轮方法的检出结论，生成更全面的维护建议。

处理逻辑：
- 统计各轴承方法检出的显著故障特征及其出现次数，按检出方法数排序描述；
- 统计齿轮指标中的 `critical` 和 `warning` 级别，分别给出"立即检查"和"关注啮合状态"的建议；
- 若未检出任何显著特征，则返回通用提示。

当 `status == "normal"` 时，直接返回正常运行建议。

**参数说明**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `bearing_results` | `Dict` | — | 所有轴承方法的结果字典，键为方法名（如 `"envelope"`、`"kurtogram"` 等），值为对应结果字典 |
| `gear_results` | `Dict` | — | 所有齿轮方法的结果字典，键为方法名（如 `"standard"`、`"advanced"` 等），值为对应结果字典 |
| `status` | `str` | — | 设备综合状态 |

**返回值说明**

- **类型**：`str`
- **说明**：综合诊断建议文本，汇总了所有方法的检出结论。

---

### _summarize_all_methods

```python
def _summarize_all_methods(
    bearing_results: Dict,
    gear_results: Dict,
) -> Dict[str, Any]
```

**功能说明**

汇总所有诊断方法的检出结论，生成结构化的汇总字典。对每种轴承方法和齿轮方法，提取其检出的故障指标、显著标记、理论频率、检测频率、SNR 等详细信息。

轴承方法名称映射：
- `envelope` → `"标准包络分析"`
- `kurtogram` → `"Fast Kurtogram"`
- `cpw` → `"CPW预白化+包络"`
- `med` → `"MED最小熵解卷积+包络"`
- `mckd` → `"MCKD最大相关峭度解卷积+包络"`
- `teager` → `"Teager能量算子+包络"`
- `spectral_kurtosis` → `"自适应谱峭度包络"`
- `sc_scoh` → `"谱相关/谱相干分析"`

齿轮方法名称映射：
- `standard` → `"标准边频带分析"`
- `advanced` → `"高级时域指标"`

**参数说明**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `bearing_results` | `Dict` | — | 所有轴承方法的结果字典 |
| `gear_results` | `Dict` | — | 所有齿轮方法的结果字典 |

**返回值说明**

- **类型**：`Dict[str, Any]`
- **说明**：结构化汇总字典，包含以下顶层键：

| 键 | 类型 | 说明 |
|----|------|------|
| `bearing_detections` | `List[Dict]` | 各轴承方法的检出详情列表。每个元素包含 `method`（中文名）、`method_key`、`detected_faults`（检出的故障列表，含 `fault_type`、`theory_hz`、`detected_hz`、`snr`）、`features` |
| `gear_detections` | `List[Dict]` | 各齿轮方法的检出详情列表。每个元素包含 `method`、`method_key`、`detected_indicators`（含 `indicator`、`value`、`level`）、`ser`、`sideband_count`、`sidebands`、`fm0`、`fm4`、`car`、`m6a`、`m8a` |
