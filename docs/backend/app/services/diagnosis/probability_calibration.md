# `probability_calibration.py` — 概率校准


> **算法原理**: 详见 [小波与模态分解算法文档](../../algorithms/wavelet_and_modality_decomposition.md) 与 [系统算法总览](../../../../ALGORITHMS.md)。
**对应源码**：`cloud/app/services/diagnosis/probability_calibration.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `calibrate_fault_probabilities` | `calibrate_fault_probabilities(raw_probs, time_features) -> dict` | 故障概率校准 |
| `calibrate_snr_to_prob` | `calibrate_snr_to_prob(snr, fault_type="generic") -> float` | SNR 转概率 |


## 内部辅助函数

### `_sigmoid_prob`

```python
def _sigmoid_prob(
    value: float,
    threshold: float = CALIB_THRESHOLD,
    max_prob: float = CALIB_MAX_PROB,
    slope: float = CALIB_SLOPE,
) -> float
```

- **参数**:
  - `value` (`float`): 输入原始值（如 SNR 或概率等效值）
  - `threshold` (`float`): sigmoid 中心点，value 低于此值时概率趋近于 0
  - `max_prob` (`float`): 最大输出概率上限，避免算法过度自信
  - `slope` (`float`): 过渡带斜率，越大过渡越陡峭
- **返回值**：`float` — 校准后的概率 (0.0 ~ max_prob)
- **说明**：使用 sigmoid 函数 `max_prob / (1 + exp(-(value-threshold)*slope))` 将连续指标映射为概率。当指数项超出 ±20 时直接截断到边界值，避免数值溢出
