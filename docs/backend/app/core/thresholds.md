# `thresholds.py` — 全局阈值配置

**对应源码**：`cloud/app/core/thresholds.py`

## 常量

### `FEATURE_THRESHOLDS`

振动特征阈值（rms, peak, kurtosis, crest_factor, skewness, impulse_factor），每项含 `baseline/warning/critical` 三级。

**关键阈值**：
| 指标 | baseline | warning | critical |
|------|----------|---------|----------|
| rms | 0.008 | 0.015 | 0.030 |
| kurtosis | 4.0 | 5.5 | 7.0 |
| crest_factor | 7.5 | 9.0 | 10.5 |

### `ALARM_THRESHOLDS`

告警阈值：FEATURE_THRESHOLDS 的 warning/critical + ser, fm0, car, sideband_count

### `DEVICE_DEFAULT_THRESHOLDS`

设备默认告警阈值：rms, peak, kurtosis, crest_factor 的 warning/critical
