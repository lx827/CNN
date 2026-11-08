# `bearing/` — 轴承包络算法与分析

**对应源码**：`cloud/app/algorithms/bearing/__init__.py`

- [`envelope.md`](envelope.md)：带通、Hilbert、低通和完整有效单边幅值谱。
- [`analysis.md`](analysis.md)：唯一局部峰归属、能量、谐波、边带和统计原始指标。
- [`evaluation.md`](evaluation.md)：可评估性、阈值、证据融合与统计评分。

标准对象化组合入口位于 `algorithms/pipelines/bearing/`。分析与展示分离，算法层不读取 `max_freq` 展示参数。
