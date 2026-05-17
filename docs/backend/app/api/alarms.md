# `alarms.py` — 告警管理

**对应源码**：`cloud/app/api/alarms.py` | `prefix=/api/alarms` | `tags=[告警管理]`

## 路由端点

### `GET /api/alarms/`

```python
@router.get("/")
def get_alarms(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    level: Optional[str] = Query(default=None),
    resolved: Optional[int] = Query(default=None),
    device_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
) -> dict
```

- **响应**：`{code, data: {total, page, size, items}}`
- **说明**：分页告警列表

### `POST /api/alarms/{alarm_id}/resolve`

```python
@router.post("/{alarm_id}/resolve")
def resolve_alarm(alarm_id: int, db: Session = Depends(get_db)) -> dict
```

- **响应**：`{code: 200, message: "告警已处理"}`
- **说明**：标记告警已处理

### `DELETE /api/alarms/{alarm_id}`

```python
@router.delete("/{alarm_id}")
def delete_alarm(alarm_id: int, db: Session = Depends(get_db)) -> dict
```

- **响应**：`{code: 200, message: "告警已删除"}`
- **说明**：删除告警记录
