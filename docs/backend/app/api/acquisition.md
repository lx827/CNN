# `acquisition.py` — DC24 完整原始采集任务

**对应源码**：`cloud/app/api/acquisition.py` | `prefix=/api/acquisition` | `tags=[真实采集]`

> 沿用系统认证（`optional_auth`），独立于历史回放/物理量诊断。边端专用接口经 `edge_only` 依赖校验（仅 `X-Edge-Key` 认证的边端可调用）。落盘根目录由环境变量 `ACQUISITION_DATA_DIR` 控制（默认 `<仓库根>/data/acquisitions/<任务ID>/`）。

## 常量与辅助

| 名称 | 说明 |
|------|------|
| `ACTIVE` | 活跃状态集合：pending / waiting_device / configuring / capturing / uploading / analyzing |
| `NATIVE_RATES` | 原厂 12 档采样率，读自 `dc24/dc24_profiles.json` |
| `ANALYSIS_LOCK` | `asyncio.Semaphore(1)`，串行化归档校验与分析（2G 红线） |
| `storage()` | 采集落盘根目录（读 `ACQUISITION_DATA_DIR`，默认 `data/acquisitions`） |
| `save_archive(job, archive)` | 校验 ZIP/CSV/元数据（24 位计数范围、点数与任务一致、无帧序号缺口）后完整落盘，并另存 `counts.npz`；不进入旧回放诊断流水线 |

## 请求模型

- `AnalysisOptions`：`fft=True, rms=True, envelope=False, band_low/band_high=None`；开包络时须满足 `0 < band_low < band_high < sample_rate/2`
- `CreateJob`：`agent_id`、`sample_rate`（须为原厂档位）、`duration>=1`、`analysis`
- `Heartbeat`：`agent_id`、`source`（`dc24_tcp|recording_replay`）、`state`
- `Progress`：`stage`、`samples_per_channel`、`message`

## 路由端点

### `POST /api/acquisition/agents/heartbeat`（edge_only）

边端心跳，首次自动注册 `AcquisitionAgent`，15 秒内有心跳视为在线。

### `GET /api/acquisition/agents`

边端列表（id、source、state、online、last_seen_at）。

### `POST /api/acquisition/jobs`

创建采集任务。要求边端在线；回放源采样率必须与原记录一致；同一边端同时只允许一个活跃任务。

### `GET /api/acquisition/jobs`

最近 30 条任务历史（snapshot 列表）。

### `GET /api/acquisition/agents/{agent_id}/next`（edge_only）

边端领取最早 pending 任务（CAS 更新为 waiting_device，无任务返回 `data: null`）。

### `GET /api/acquisition/jobs/{job_id}` / `POST /api/acquisition/jobs/{job_id}/cancel`

任务详情 / 请求取消（pending 直接取消，进行中置 `cancel_requested`）。

### `POST /api/acquisition/jobs/{job_id}/progress`（edge_only）

边端上报阶段进度，返回 `cancel_requested` 供边端及时停止。

### `POST /api/acquisition/jobs/{job_id}/upload`（edge_only）

边端整包上传 ZIP 归档（≤32MB）。流式接收后在 `ANALYSIS_LOCK` 内完成：`save_archive` 校验落盘 → 状态 analyzing → `analyze_counts` 计算 → 写 `analysis.json` / `analysis_arrays.npz` → completed（或 cancelled）。校验失败置 failed 并返回 422。重复上传（completed）幂等返回。

### `GET /api/acquisition/jobs/{job_id}/analysis`

返回已生成的 `analysis.json`；未完成返回 404。

### `GET /api/acquisition/jobs/{job_id}/waveform`

原始计数波形片段。参数 `channel(0~3)`、`start>=0`、`seconds(0,5]`，返回 `[time_s, counts]` 点列（数据来自 `counts.i32` memmap 或 `counts.npz`）。

### `GET /api/acquisition/jobs/{job_id}/files/{name}`

下载任务文件。白名单：`samples.csv`、`metadata.json`、`rx_stream.bin`、`commands.jsonl`、`analysis.json`、`analysis_arrays.npz`。
