# `pipelines/` — 对象化 Pipeline

**对应源码**：`cloud/app/algorithms/pipelines/__init__.py`

Pipeline 只组合纯计算，不处理设备、数据库、缓存、告警或 HTTP。不同机械对象拥有不同 Pipeline，不使用统一固定流水线套所有算法。

当前实现：`bearing/BearingEnvelopePipeline`。
