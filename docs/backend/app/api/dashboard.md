# `dashboard.py` — 设备总览

**对应源码**：`cloud/app/api/dashboard.py` | `prefix=/api/dashboard` | `tags=[设备总览]`

## 常量

| 常量 | 说明 |
|------|------|
| `VALID_FAULT_TYPES` | 17 种有效故障类型白名单 |
| `BEARING_FAULT_MAP` | BPFO→外圈, BPFI→内圈, BSF→滚动体 |

## 路由端点

### `GET /api/dashboard/`

```python
@router.get("/")
def get_dashboard(db: Session = Depends(get_db)) -> dict
```

- **参数**：无（需认证）
- **响应**：`{code: 200, data: {devices, diagnosis, alarm_stats}}`
- **说明**：设备总览数据（设备列表 + 最新诊断 + 告警统计）
- **2026-10-21 读路径**：通过 `services/diagnosis_queries.py` 批量读取每设备最新摘要，不读取完整算法 JSON；告警统计合并为一次条件聚合。有设备时总计三次 SELECT，查询数不随设备数增加。最新记录按 `analyzed_at` 再按 `id` 降序选择。
