# `pipelines/bearing/__init__.py` — 标准轴承包络 Pipeline

**对应源码**：`cloud/app/algorithms/pipelines/bearing/__init__.py`

## `BearingEnvelopePipeline`

```python
pipeline = BearingEnvelopePipeline(geometry=None, parameters=None)
```

- `analyze(signal, sample_rate_hz, rot_frequency_hz=None, rot_frequency_std_hz=0.0)`：执行包络计算和指标提取，返回 `BearingEnvelopeAnalysis`。
- `evaluate(analysis)`：直接评估已有指标，不重新执行滤波或 FFT。
- `run(...)`：依次调用 `analyze` 和 `evaluate`，返回 `BearingEnvelopeDiagnosis`。

`BearingEnvelopeAnalysis` 同时保存 `EnvelopeRepresentation` 和 `EnvelopeAnalysis`；`BearingEnvelopeDiagnosis` 增加 `EnvelopeEvaluation`。分析和评估始终使用完整有效频谱，展示截断由 Engine 在评估完成后执行。转频标准差必须是有限非负数。业务层负责把结构化对象转换为响应或缓存数据。
