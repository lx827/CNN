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
- **说明**：后台协程：每 30s 扫描未分析批次 → `analyze_device` → 保存批次级诊断 + **通道级 `full_analysis`**（含集成证据/投票/最佳算法/D-S 融合） → 生成告警 → WebSocket 推送

> **通道级 `full_analysis` 保存**（2025-05 新增）：后台分析完成后，遍历 `order_analysis.channels` 为每个通道创建独立的 `Diagnosis` 记录（`channel=ch_num`），将完整的 `run_research_ensemble()` 结果（含 `ensemble`、`bearing`、`gear`、`time_features` 等）存入 `full_analysis` 列。已有记录则覆盖更新。

### `lifespan`

```python
async def lifespan(app: FastAPI) -> AsyncGenerator
```

- **参数**：`app: FastAPI` — FastAPI 应用实例
- **返回值**：`AsyncGenerator`
- **说明**：
  - **启动**：初始化 DB、创建默认设备、限制线程池=2、启动 analysis_worker + offline_monitor_worker
  - **关闭**：取消任务、关闭线程池
