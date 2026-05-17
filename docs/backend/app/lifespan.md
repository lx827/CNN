# `lifespan.py` — 应用生命周期管理

**对应源码**：`cloud/app/lifespan.py`

## 全局变量

| 变量 | 类型 | 说明 |
|------|------|------|
| `ANALYSIS_SEM` | `asyncio.Semaphore(1)` | 一次只允许一个分析批次运行，防止 OOM |

## 函数

### `analysis_worker`

```python
async def analysis_worker() -> None
```

- **参数**：无
- **返回值**：`None`
- **说明**：后台协程：每 30s 扫描未分析批次 → `analyze_device` → 写诊断 → 生成告警 → WebSocket 推送

### `lifespan`

```python
async def lifespan(app: FastAPI) -> AsyncGenerator
```

- **参数**：`app: FastAPI` — FastAPI 应用实例
- **返回值**：`AsyncGenerator`
- **说明**：
  - **启动**：初始化 DB、创建默认设备、限制线程池=2、启动 analysis_worker + offline_monitor_worker
  - **关闭**：取消任务、关闭线程池
