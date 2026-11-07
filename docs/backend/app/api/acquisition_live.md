# `acquisition_live.py` — 实时示波、示波中保存与 WS 实时窗口

**对应源码**：`cloud/app/api/acquisition_live.py` | `prefix=/api/acquisition` | `tags=[实时示波]`

> 复用现有认证与采集任务。网页读取实时窗口：REST `GET /sessions/{id}/view` 轮询（保留兼容）与 `WS /ws/acquisition/sessions/{id}/view` 推送（2026-11 新增，issue #51）共用同一套 `build_view_payload()` 计算；边端上报保持 HTTP 不变。

## 辅助

| 名称 | 说明 |
|------|------|
| `online_agent(db, agent_id)` | 校验边端在线（15 秒心跳）、source 为 `dc24_tcp`（禁止文件回放示波）、边端版本 ≥3（新输入配置） |
| `build_view_payload(s, options, wave_seconds)` | 实时窗口计算（REST 与 WS 共用）：取最近连续 ≤2 秒窗口 → `analyze_counts`（线程池）→ 附加波形抽点、均值、RMS 曲线、session 快照与 fresh 标记 |

## 路由端点

| 端点 | 说明 |
|------|------|
| `GET /capabilities` | 服务能力：原厂 12 档采样率、4 通道、hostname、version=2 |
| `POST /sessions` | 启动示波会话（校验在线 + 原厂档位 + 无未完成保存任务） |
| `GET /sessions/{id}` / `POST /sessions/{id}/stop` | 会话状态 / 请求停止（联动停止录制） |
| `POST /sessions/{id}/record` | 示波中保存：创建 `waiting_device` 任务，`duration=0` 表示手动结束；校验包络频带与互斥 |
| `POST /sessions/{id}/record/stop` | 请求结束当前录制 |
| `GET /sessions/{id}/view` | REST 轮询实时窗口（选项 fft/rms/envelope/band/wave_seconds） |
| `GET /agents/{id}/control`（edge_only） | 边端控制轮询：当前 session 快照 + 目录选择器状态 |
| `GET /agents/{id}/session` | 边端当前活跃会话 |
| `POST /agents/{id}/select-directory` / `POST /agents/{id}/directory-result`（edge_only）/ `GET /agents/{id}/directory` | 现场保存目录选择：发起 → 边端回传结果 → 前端查询 |
| `POST /sessions/{id}/state`（edge_only） | 边端上报会话/录制状态 |
| `POST /sessions/{id}/frames`（edge_only） | 边端流式上报四通道原始计数帧（16 字节/点组，24 位范围校验），写入内存窗口 |
| `PUT /jobs/{id}/stream-files/{name}`（edge_only） | 逐文件流式接收（`.part` 临时文件原子改名），白名单含 `counts.i32` |
| `POST /jobs/{id}/finish-stream`（edge_only） | 流式上传收尾：校验五件齐全、元数据与 `counts.i32` 尺寸一致后置 completed/failed，并回写示波录制状态 |

## WebSocket 端点（`ws_router`，main.py 挂载）

### `WS /ws/acquisition/sessions/{session_id}/view?token={token}`

- 鉴权：`token` 查询参数 + `verify_token_string`（浏览器 WS 无法携带 HTTP 头，与 `/ws/monitor` 同法）；失败以 1008 关闭
- 会话不存在：接受握手后以 4404 关闭，前端回退 REST 恢复
- 客户端消息：`{"type":"ping"}` → pong；`{"type":"options", fft/rms/envelope/band_low/band_high/wave_seconds}` → 更新计算选项
- 服务端推送：`{"type":"session"}`（快照变化）与 `{"type":"view"}`（新数据/选项变化），均按 `WS_PUSH_INTERVAL=0.4s` 限频（2G 红线）；计算异常时关闭连接，前端回退 REST 轮询
