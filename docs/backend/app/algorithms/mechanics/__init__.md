# `mechanics/__init__.py` — 机械运动学模型

**对应源码**：`cloud/app/algorithms/mechanics/__init__.py`

## `BearingGeometry`

```python
BearingGeometry(
    roller_count: int,
    roller_diameter: float,
    pitch_diameter: float,
    contact_angle_deg: float = 0.0,
)
```

- `fault_frequencies(rot_frequency_hz)`：返回 BPFO、BPFI、BSF、FTF，单位均为 Hz。
- `diameter_ratio`：无量纲 `d/D*cos(alpha)`。
- 滚动体数量必须是整数；直径为有限正数；直径比必须满足 `1e-12 < ratio < 1`；转频必须是有限正数。
- 非整数数量、NaN/inf、非法直径比和非法接触角显式抛出 `ValueError`。

设备字典转换不属于纯算法层：`services/diagnosis/engine.py::bearing_geometry_from_config` 在业务适配层完成。只有缺失配置才表示无参数，缺失必需字段或畸形配置会报错。
