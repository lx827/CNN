# `collect.py` — 采集任务

**对应源码**：`cloud/app/api/collect.py` | `prefix=/api/collect` | `tags=[采集任务]`

## 路由端点

### `POST /api/collect/request`

```python
@router.post("/request")
def request_collection(
    device_id: str,
    sample_rate: int = 25600,
    duration: int = 10,
    db: Session = Depends(get_db)
) -> dict
```

- **响应**：`{code, message, data: {task_id, status, ...}}`
- **说明**：前端请求手动采集

### `GET /api/collect/tasks`

```python
@router.get("/tasks")
def get_pending_tasks(device_id: str, db: Session = Depends(get_db)) -> dict
```

- **响应**：`{code, data: {has_task, task_id, ...}}`
- **说明**：边端轮询待执行任务

### `POST /api/collect/tasks/{task_id}/complete`

```python
@router.post("/tasks/{task_id}/complete")
def complete_task(task_id: int, batch_index: int, db: Session = Depends(get_db)) -> dict
```

- **说明**：边端上报任务完成

### `GET /api/collect/tasks/{task_id}/status`

```python
@router.get("/tasks/{task_id}/status")
def get_task_status(task_id: int, db: Session = Depends(get_db)) -> dict
```

- **响应**：`{code, data: {task_id, status, ...}}`
- **说明**：前端查询任务状态

### `GET /api/collect/history`

```python
@router.get("/history")
def get_collection_history(
    device_id: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db)
) -> dict
```

- **响应**：`{code, data: items}`
- **说明**：采集历史
