# `acquisition_live.py` — 示波有界内存窗口

**对应源码**：`cloud/app/services/acquisition_live.py`

> 示波的有界内存窗口；不把示波样本写到文件或业务数据库。模块级单例 `live = LiveStore()`，被 `api/acquisition_live.py` 使用。

## `class LiveStore`

线程安全（`threading.RLock`）的示波会话存储。

| 方法 | 说明 |
|------|------|
| `create(agent_id, rate)` | 新建会话；同一边端同时仅一个活跃会话；清理已结束会话（保留最近 10 个）；窗口 `chunks` 与 `rms_history`（`maxlen=240`）有界 |
| `get(session_id)` | 取会话，不存在抛 `KeyError`（路由转 404） |
| `snapshot(s)` | 深拷贝会话公开字段（剔除 `chunks`/`rms_history`/`last_upload`） |
| `current(agent_id)` | 该边端最近一个未停止/未失败的会话 |
| `push(s, values, start, sequence)` | 边端帧写入：丢弃乱序/重复（`start < samples_received`），只保留最近 2 秒数据，累计去均值 RMS 曲线，`revision += 1` |
| `window(s)` | 最近**连续**片段（网络缺口不拼接）≤2 秒，返回 `(窗口起点, 数组)` |

会话 dict 关键字段：`id`、`agent_id`、`sample_rate`、`status`（waiting_device/configuring/streaming/stopping/stopped/failed）、`recording`（示波中保存任务）、`revision`（新数据版本号，WS 推送依据）、`frame_sequence`、`rms_history`。
