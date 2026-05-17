# `trend_prediction.py` — 趋势预测


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/trend_prediction.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `holt_winters_forecast` | `holt_winters_forecast(data, horizon=5, seasonal_period) -> List[float]` | Holt-Winters 三阶指数平滑预测 |
| `kalman_smooth_health_scores` | `kalman_smooth_health_scores(scores, process_var=1.0, measure_var=4.0) -> List[float]` | Kalman 滤波平滑健康度 |

| `_simple_linear_regression` | `_simple_linear_regression(x: np.ndarray, y: np.ndarray) -> tuple` | 简单线性回归（斜率、截距） |

### `_simple_linear_regression`

```python
def _simple_linear_regression(x: np.ndarray, y: np.ndarray) -> tuple
```

- **参数**:
  - `x` (`np.ndarray`): 自变量序列
  - `y` (`np.ndarray`): 因变量序列
- **返回值**：`tuple` — `(slope, intercept)`，斜率与截距
- **说明**：最小二乘法简单线性回归，用于 Holt-Winters 趋势初始化和短序列退化预测。
