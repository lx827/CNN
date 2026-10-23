# `lifespan.py` — 应用生命周期管理

**对应源码**：`cloud/app/lifespan.py`

**2026-10-21 依赖调整**：JSON 转换直接来自 `app.core.json_utils`，不再通过 `app.api.data_view` 路由包导入。线程池仍为两线程，后台分析仍使用原有串行信号量。

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

**2026-10-23 JSON 入库修复**：`analyze_device` 返回后立即用 `sanitize_for_json` 递归转换完整结果，再供批次诊断、通道缓存、告警及推送共用。NumPy 布尔/整数/浮点和数组转换为 JSON 原生类型，非有限数值按既有约定转换为 `null`；不修改原算法返回对象。不再仅转换通道 `full_analysis`，避免批次 `order_analysis` 中的 NumPy 布尔导致整个事务失败、原始数据长期未分析。函数签名、状态评分规则和线程限制均不变。

验证：`tests/backend/test_analysis_worker_json.py` 使用实际 worker 与内存 SQLite，覆盖通道记录新增/更新、批次实际提交、已分析标记及设备健康度更新、告警输入和严格 JSON 推送；算法与特征计算使用固定替身，不代表真实数据诊断准确率。

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
