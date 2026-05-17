# `trend_prediction.py` — 趋势预测

**对应源码**：`cloud/app/services/diagnosis/trend_prediction.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `holt_winters_forecast` | `holt_winters_forecast(data, horizon=5, seasonal_period) -> List[float]` | Holt-Winters 三阶指数平滑预测 |
| `kalman_smooth_health_scores` | `kalman_smooth_health_scores(scores, process_var=1.0, measure_var=4.0) -> List[float]` | Kalman 滤波平滑健康度 |
