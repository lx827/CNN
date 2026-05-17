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
